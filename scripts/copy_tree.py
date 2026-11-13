#!/usr/bin/env python3
"""Cloud-aware tree copy: file by file, read-then-write immediately (no pre-hydration), retries for
cloud-only sources, resumable (same size + mtime → skip), symlinks recreated, excluded dirs pruned,
permission bits and mtime preserved, size verified. Never deletes or overwrites anything in DST: a same-name file
with different size/mtime is left as is and reported as 충돌; copies land via .part + rename so no truncated file.

  copy_tree.py SRC DST [--exclude node_modules .venv ...] [--workers 8] [--errors errors.csv] [--retry 0 15 30 60 120]
Prints progress every 1000 files and 'ALL_DONE' at the end (wait for it when run in the background)."""
import argparse, csv, os, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import walk_files, copy_with_retry, nfc, EXCLUDE_DIRS, RETRY

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst")
ap.add_argument("--exclude", nargs="*", default=sorted(EXCLUDE_DIRS))
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--errors", default="copy_tree_errors.csv")
ap.add_argument("--retry", nargs="*", type=float, default=list(RETRY), help="seconds between attempts")
a = ap.parse_args()
S, D = os.path.abspath(a.src), os.path.abspath(a.dst)

items = [(p, os.path.join(D, rel)) for p, rel, _ in walk_files(S, set(a.exclude))]
print(f"{nfc(S)} → {nfc(D)}: 파일 {len(items):,} (제외: {', '.join(a.exclude)})", flush=True)
t0 = time.time(); counts = {"ok": 0, "skip": 0, "link": 0, "conflict": 0}; errs = []; conflicts = []

def one(pair):
    sp, dp = pair
    try:
        return copy_with_retry(sp, dp, tuple(a.retry)), sp, ""
    except OSError as e:
        return "err", sp, str(e)

with ThreadPoolExecutor(a.workers) as ex:
    for n, (res, sp, msg) in enumerate(ex.map(one, items), 1):
        if res == "err": errs.append((sp, msg))
        else:
            counts[res] += 1
            if res == "conflict": conflicts.append(sp)
        if n % 1000 == 0: print(f"  {n:,}/{len(items):,} · {time.time()-t0:.0f}s", flush=True)

bad = 0; conf = set(conflicts)
for sp, dp in items:
    if os.path.islink(sp) or sp in conf: continue
    if not os.path.exists(dp) or os.path.getsize(dp) != os.path.getsize(sp): bad += 1
if errs or conflicts:
    with open(a.errors, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["src", "error"]); w.writerows(errs); w.writerows((c, "충돌: 목적지에 같은 이름의 다른 파일(그대로 둠)") for c in conflicts)
print(f"완료: 복사 {counts['ok']:,} · 건너뜀 {counts['skip']:,} · 링크 {counts['link']:,} · 충돌 {counts['conflict']:,} · 오류 {len(errs)} · 검증 불일치 {bad} · {time.time()-t0:.0f}s"
      + (f" · 목록 {a.errors}" if errs or conflicts else ""))
print("ALL_DONE", flush=True)
