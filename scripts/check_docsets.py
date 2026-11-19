#!/usr/bin/env python3
"""문서세트 완결성 체크기(읽기 전용). 거래 하나 = 하위폴더 하나로 묶인 증빙 폴더를, 규칙 파일의 필수 서류 목록으로 검사한다.

  python3 check_docsets.py --root <증빙 폴더> --rules <규칙.json> [--out <보고서 폴더>] [--name <이름>]

판정은 파일명 기준이다(본문을 읽지 않으므로 클라우드 파일을 내려받지 않는다). 제출용 zip은 목록만 읽는다.
상태: 있음 / zip 안에만(낱개 없음) / 다른 폴더(교차 참조 폴더에 있음) / 부족(개수 모자람) / 없음.
결과: <이름>_check.md(사람용, 관제탑이 읽음) + <이름>_warnings.csv(folder,item,status,detail). 파일은 아무것도 옮기지 않는다.
규칙 파일 형식은 references/docsets.md, 예시는 references/docset_rules.example.json."""
import argparse, csv, json, os, re, sys, zipfile, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import nfc

def zip_members(p):
    try:
        with zipfile.ZipFile(p) as z:
            out = []
            for i in z.infolist():
                n = i.filename
                if not (i.flag_bits & 0x800):
                    try: n = n.encode("cp437").decode("utf-8")
                    except (UnicodeEncodeError, UnicodeDecodeError): pass
                b = os.path.basename(nfc(n))
                if b and not n.startswith("__MACOSX") and not b.startswith("._") and not i.is_dir(): out.append(b)
            return out
    except (zipfile.BadZipFile, OSError): return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", required=True); ap.add_argument("--rules", required=True)
    ap.add_argument("--out", default="."); ap.add_argument("--name"); a = ap.parse_args()
    R = json.load(open(a.rules, encoding="utf-8")); root = os.path.abspath(a.root)
    name = a.name or R.get("name") or nfc(os.path.basename(root))
    TYPES = [(t, re.compile(rx, re.I)) for t, rx in R["types"]]
    dtype = lambda f: next((t for t, rx in TYPES if rx.search(f)), "기타")
    skip = tuple(R.get("skip_dirs", []))
    def walk(d, skip_dirs=skip):
        out = []
        for dp, dn, fn in os.walk(d):
            dn[:] = [x for x in dn if not x.startswith(".") and not nfc(x).startswith(skip_dirs or ("\0",))]
            out += [(nfc(f), nfc(os.path.relpath(os.path.join(dp, f), d))) for f in fn if not f.startswith(".")]
        return out
    xdirs = [os.path.normpath(os.path.join(root, x)) for x in R.get("xref_dirs", [])]
    xfiles = [(f, nfc(os.path.join(os.path.basename(d), rel))) for d in xdirs if os.path.isdir(d) for f, rel in walk(d, ())]
    stop = set(R.get("token_stopwords", [])) | set(R["kinds"].keys())
    report = [f"# {name} 문서세트 완결성 검사 (읽기 전용)\n", f"규칙: {R.get('source', a.rules)}. 판정은 파일명 기준이다.\n"]
    warns = []
    for d in sorted((x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x)) and not x.startswith((".", "_"))), key=nfc):
        d = nfc(d); kind = next((m["kind"] for m in R["folders"] if re.search(m["match"], d)), None)
        if not kind: continue
        files = walk(os.path.join(root, d)); names = {f for f, _ in files}
        types = collections.defaultdict(list); zmem = {}
        for f, rel in files:
            types[dtype(f)].append(rel)
            if f.lower().endswith(".zip"):
                mem = zip_members(os.path.join(root, d, rel))
                if mem is None: warns.append([d, "제출 zip", "읽기 실패", rel])
                for m in mem or []:
                    if m not in names: zmem.setdefault(m, f)
        tokens = [t for t in re.split(r"[_\s·()]+", d) if len(t) >= 2 and not t.isdigit() and t not in stop]
        report.append(f"\n## {d}  ({len(files)}개, {kind})\n\n| 항목 | 상태 | 파일 | 근거 |\n|---|---|---|---|")
        miss = 0
        for req in R["kinds"][kind]:
            item, ok, n = req["item"], req["types"], req.get("min", 1)
            have = [rel for t in ok for rel in types.get(t, [])]
            if len(have) >= n: st, note = "있음", ""
            else:
                zz = [m for m in zmem if dtype(m) in ok]
                xr = [rel for f, rel in xfiles if dtype(f) in ok and any(t.lower() in f.lower() for t in tokens)]
                if len(have) + len(zz) >= n and zz: st, note = "zip 안에만", "낱개 없음: " + "; ".join(zz)[:120]
                elif xr: st, note = "다른 폴더", "; ".join(xr)[:120]
                elif have: st, note = "부족", f"{len(have)}/{n}"
                else: st, note = "없음", ""
                miss += st in ("없음", "부족")
                warns.append([d, item, st, note])
            report.append(f"| {item} | **{st}** | {'; '.join(h[:50] for h in have[:3])} | {req.get('basis', '')}{(' · ' + note) if note else ''} |")
        report.append(f"\n→ 누락 {miss}")
    os.makedirs(a.out, exist_ok=True); stem = re.sub(r"[^\w가-힣-]+", "_", name).strip("_")
    open(os.path.join(a.out, f"{stem}_check.md"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    with open(os.path.join(a.out, f"{stem}_warnings.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["folder", "item", "status", "detail"]); w.writerows(warns)
    folders = sum(l.lstrip("\n").startswith("## ") for l in report)
    print(f"{name}: 거래 폴더 {folders} · 경고 {len(warns)} → {os.path.join(a.out, stem + '_check.md')}")

if __name__ == "__main__":
    main()
