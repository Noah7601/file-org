#!/usr/bin/env python3
"""지속 관리: 마스터(와 흩어지기 쉬운 폴더)를 이름·크기·수정시각으로 사진 찍고 직전 사진과 비교한다. 읽기 전용.

  python3 watch.py --root <마스터> --state <상태 폴더> [--scatter ~/Downloads ~/Desktop] [--keep 60]

잡아내는 것
  사라짐   직전에 있었는데 지금 없는 파일. 같은 이름·크기가 다른 곳에 새로 생겼으면 '이동'으로, 아니면 '사라짐'으로 분류
  새 0바이트  직전에는 내용이 있었거나 없던 파일이 지금 0바이트
  새 파일  어디에 들어왔는지(마스터 맨 위, INBOX, 그 밖) 함께 기록
  새 중복 후보  새 파일과 이름·크기가 같은 파일이 이미 있음(내용 비교는 하지 않음: 다운로드 방지)
  흩어짐   --scatter 폴더에 새로 생긴 문서(pdf·hwp·docx·xlsx·pptx 등)
결과: <상태>/snapshots/<날짜시각>.tsv.gz, <상태>/watch_latest.json(관제탑이 읽음), <상태>/reports/watch_<날짜시각>.md
처음 실행은 기준 사진만 찍는다. 파일은 아무것도 옮기지 않는다."""
import argparse, collections, csv, gzip, io, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import nfc, walk_files, EXCLUDE_DIRS
DOC_EXT = {".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".txt", ".md", ".zip", ".jpg", ".jpeg", ".png", ".heic"}

def snap(root, tag):
    out = {}
    for p, rel, st in walk_files(root, EXCLUDE_DIRS | {"_정리로그"}):
        if os.path.islink(p): continue
        out[f"{tag}/{nfc(rel)}"] = (st.st_size, int(st.st_mtime))
    return out

def save(d, path):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        for k, (s, m) in sorted(d.items()): w.writerow([k, s, m])

def load(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return {r[0]: (int(r[1]), int(r[2])) for r in csv.reader(f, delimiter="\t")}

def where(key):
    tag, _, rel = key.partition("/"); top = rel.split("/")[0]
    if tag != "master": return f"흩어짐({tag})"
    if "/" not in rel: return "마스터 맨 위"
    if top.startswith("00_INBOX"): return "INBOX"
    if not top[:2].isdigit(): return f"번호 없는 폴더({top})"
    return top

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", required=True); ap.add_argument("--state", required=True)
    ap.add_argument("--scatter", nargs="*", default=[]); ap.add_argument("--keep", type=int, default=60)
    ap.add_argument("--against-days", type=int, help="직전 사진 대신 N일 전에 가장 가까운 사진과 비교하고, 새 사진은 저장하지 않는다(주간 정리 제안용). 결과는 watch_week.json")
    a = ap.parse_args()
    sd = os.path.join(a.state, "snapshots"); rd = os.path.join(a.state, "reports"); os.makedirs(sd, exist_ok=True); os.makedirs(rd, exist_ok=True)
    t0 = time.time(); now = time.strftime("%Y%m%d-%H%M%S")
    cur = snap(a.root, "master")
    for s in a.scatter:
        s = os.path.expanduser(s)
        if os.path.isdir(s):                                        # 흩어짐은 맨 위 파일만 본다(하위 폴더는 내려가지 않음)
            for e in os.scandir(s):
                if e.name.startswith(".") or not e.is_file(follow_symlinks=False): continue
                st = e.stat(follow_symlinks=False); cur[f"{os.path.basename(s.rstrip('/'))}/{nfc(e.name)}"] = (st.st_size, int(st.st_mtime))
    prevs = sorted(f for f in os.listdir(sd) if f.endswith(".tsv.gz"))
    if a.against_days:
        cut = time.strftime("%Y%m%d-%H%M%S", time.localtime(time.time() - a.against_days * 86400))
        older = [f for f in prevs if f[:15] <= cut]; prevs = [older[-1]] if older else prevs[:1]
    else:
        save(cur, os.path.join(sd, f"{now}.tsv.gz"))
        for old in prevs[:-max(a.keep - 1, 0)] if len(prevs) >= a.keep else []: os.remove(os.path.join(sd, old))   # 오래된 사진만 정리(자기 산출물)
    res = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": sum(1 for k in cur if k.startswith("master/")), "baseline": not prevs,
           "since": None, "moved": [], "gone": [], "new_zero": [], "new": [], "dup_candidates": [], "scattered": [], "seconds": 0}
    if prevs:
        prev = load(os.path.join(sd, prevs[-1])); res["since"] = prevs[-1][:15]
        added = {k: v for k, v in cur.items() if k not in prev}; removed = {k: v for k, v in prev.items() if k not in cur}
        bykey = collections.defaultdict(list)
        for k, (s, _) in added.items(): bykey[(os.path.basename(k), s)].append(k)
        moved_to = set()
        for k, (s, _) in removed.items():
            hit = [x for x in bykey.get((os.path.basename(k), s), []) if x not in moved_to]
            if hit and s > 0: moved_to.add(hit[0]); res["moved"].append({"from": k, "to": hit[0]})
            elif k.startswith("master/"): res["gone"].append({"path": k, "size": s})
        for k, (s, _) in cur.items():
            if k.startswith("master/") and s == 0 and (k not in prev or prev[k][0] > 0): res["new_zero"].append(k)
        existing = collections.defaultdict(list)
        for k, (s, _) in cur.items():
            if k not in added and s > 0: existing[(os.path.basename(k), s)].append(k)
        for k, (s, _) in sorted(added.items()):
            if k in moved_to: continue
            if k.startswith("master/"):
                res["new"].append({"path": k, "size": s, "where": where(k)})
                if existing.get((os.path.basename(k), s)): res["dup_candidates"].append({"path": k, "same_as": existing[(os.path.basename(k), s)][0]})
            elif os.path.splitext(k)[1].lower() in DOC_EXT: res["scattered"].append({"path": k, "size": s})
    res["seconds"] = round(time.time() - t0, 1)
    json.dump(res, open(os.path.join(a.state, "watch_week.json" if a.against_days else "watch_latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = [f"# 지속 관리 보고 {res['at']}\n", f"마스터 파일 {res['files']:,} · 측정 {res['seconds']}초 · 비교 기준 {res['since'] or '(첫 사진)'}\n"]
    if res["baseline"]: L.append("첫 실행이라 기준 사진만 찍었다. 다음 실행부터 비교한다.\n")
    else:
        L.append("| 구분 | 건수 |\n|---|--:|")
        for k, label in (("gone", "사라짐(확인 필요)"), ("new_zero", "새 0바이트"), ("moved", "이동"), ("new", "새 파일"), ("dup_candidates", "새 중복 후보"), ("scattered", "흩어짐(마스터 밖 새 문서)")):
            L.append(f"| {label} | {len(res[k])} |")
        for k, label in (("gone", "사라짐"), ("new_zero", "새 0바이트"), ("scattered", "흩어짐")):
            if res[k]: L += [f"\n## {label}\n"] + [f"- {x if isinstance(x, str) else x['path']}" for x in res[k][:50]]
        if res["new"]:
            L.append("\n## 새 파일(위치별)\n")
            for w, n in collections.Counter(x["where"] for x in res["new"]).most_common(): L.append(f"- {w}: {n}")
    open(os.path.join(rd, f"{'week' if a.against_days else 'watch'}_{now}.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"마스터 {res['files']:,} · " + ("기준 사진" if res["baseline"] else f"사라짐 {len(res['gone'])} · 새0바이트 {len(res['new_zero'])} · 이동 {len(res['moved'])} · 새 {len(res['new'])} · 중복후보 {len(res['dup_candidates'])} · 흩어짐 {len(res['scattered'])}") + f" · {res['seconds']}초")

if __name__ == "__main__":
    main()
