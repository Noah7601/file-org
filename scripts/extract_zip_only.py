#!/usr/bin/env python3
"""제출용 zip 안에만 있고 낱개 파일이 없는 서류를 같은 폴더에 꺼내 둔다. zip은 그대로 둔다. 기본은 dry-run.

  python3 extract_zip_only.py --root <증빙 폴더> --log <moves_v2.csv> [--apply]

같은 이름이 이미 있으면 건너뛴다(덮어쓰기 없음). .part에 쓴 뒤 크기를 확인하고 이름을 바꾼다. 꺼낸 파일마다 copy 행을 남긴다."""
import argparse, os, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import nfc, log_row
ap = argparse.ArgumentParser(); ap.add_argument("--root", required=True); ap.add_argument("--log", required=True)
ap.add_argument("--apply", action="store_true"); ap.add_argument("--tag", default="제출 zip 낱개 보관"); a = ap.parse_args()
def mname(i):
    n = i.filename
    if not (i.flag_bits & 0x800):
        try: n = n.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError): pass
    return nfc(n)
plan = []
for dp, dn, fn in os.walk(os.path.abspath(a.root)):
    dn[:] = [d for d in dn if not d.startswith(".")]
    have = {nfc(f) for f in fn}
    for z in sorted(f for f in fn if f.lower().endswith(".zip")):
        try: zf = zipfile.ZipFile(os.path.join(dp, z))
        except (zipfile.BadZipFile, OSError): print("  읽기 실패:", nfc(os.path.join(dp, z))); continue
        with zf:
            for i in zf.infolist():
                n = mname(i); b = os.path.basename(n)
                if i.is_dir() or not b or n.startswith("__MACOSX") or b.startswith("._") or b in have: continue
                have.add(b); plan.append((dp, z, i, b))
print(f"{'적용' if a.apply else 'dry-run'}: 꺼낼 파일 {len(plan)}개 · {sum(p[2].file_size for p in plan)/2**20:.1f} MB")
ok = err = 0
for dp, z, i, b in plan:
    dst = os.path.join(dp, b); print(f"  {nfc(os.path.relpath(dst, a.root))[:90]}  ({i.file_size/1024:.0f} KB)")
    if not a.apply or os.path.exists(dst): continue
    with zipfile.ZipFile(os.path.join(dp, z)) as zf, zf.open(i) as fi, open(dst + ".part", "wb") as fo:
        while chunk := fi.read(1 << 20): fo.write(chunk)
    if os.path.getsize(dst + ".part") == i.file_size:
        os.utime(dst + ".part", (time.time(), time.mktime(i.date_time + (0, 0, -1)))); os.replace(dst + ".part", dst); ok += 1
        log_row(a.log, "copy", f"{os.path.join(dp, z)}!{mname(i)}", dst, f"{a.tag}: 제출본에만 있던 서류를 낱개로 보관")
    else:
        os.remove(dst + ".part"); err += 1; log_row(a.log, "error", os.path.join(dp, z), dst, f"{a.tag}: 크기 불일치")
if a.apply: print(f"복사 {ok} · 오류 {err}")
