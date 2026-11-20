#!/usr/bin/env python3
"""Cloud-aware tree copy: file by file, read-then-write immediately (no pre-hydration), retries for
cloud-only sources, resumable (same size + mtime → skip), symlinks recreated, excluded dirs pruned,
permission bits and mtime preserved, size verified. Never deletes or overwrites anything in DST: a same-name file
with different size/mtime is left as is and reported as 충돌; copies land via .part + rename so no truncated file.

Disk guard: before starting, the bytes still to copy are compared with local free space; if the copy would
leave less than --min-free GiB (default 8) it does not start (exit 2) unless --allow-tight. While running,
free space is re-measured and the copy stops cleanly below --min-free (exit 3, prints STOPPED_DISK);
re-running the same command resumes (finished files are skipped). --min-free 0 turns the guard off.

  copy_tree.py SRC DST [--exclude node_modules .venv ...] [--workers 8] [--errors errors.csv] [--retry 0 15 30 60 120]
                       [--min-free 8] [--allow-tight]
Prints progress every 1000 files and 'ALL_DONE' at the end (wait for it when run in the background)."""
import argparse, csv, os, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import walk_files, copy_with_retry, nfc, EXCLUDE_DIRS, RETRY, MIN_FREE_GIB, DiskGuard, local_free_gib

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst")
ap.add_argument("--exclude", nargs="*", default=sorted(EXCLUDE_DIRS))
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--errors", default="copy_tree_errors.csv")
ap.add_argument("--retry", nargs="*", type=float, default=list(RETRY), help="seconds between attempts")
ap.add_argument("--min-free", type=float, default=MIN_FREE_GIB, help="GiB of local free space to keep (0 = off)")
ap.add_argument("--allow-tight", action="store_true", help="start even if the estimate says space is short (the running guard still stops)")
a = ap.parse_args()
S, D = os.path.abspath(a.src), os.path.abspath(a.dst)

items = [(p, os.path.join(D, rel)) for p, rel, _ in walk_files(S, set(a.exclude))]
print(f"{nfc(S)} → {nfc(D)}: 파일 {len(items):,} (제외: {', '.join(a.exclude)})", flush=True)
need = sum(os.lstat(sp).st_size for sp, dp in items if not os.path.islink(sp) and not os.path.lexists(dp))
free = local_free_gib(D)
print(f"  복사할 양 {need/2**30:.2f} GiB · 로컬 여유 {free:.1f} GiB · 지킬 여유 {a.min_free:g} GiB", flush=True)
if a.min_free > 0 and free - need / 2**30 < a.min_free:
    msg = (f"여유 부족: 복사 후 예상 여유 {free - need/2**30:.1f} GiB < 기준 {a.min_free:g} GiB"
           f" (최소 {a.min_free - (free - need/2**30):.1f} GiB를 더 비우거나, 하위 폴더별로 나눠 실행)")
    if not a.allow_tight:
        print(msg + ". 시작하지 않음. 목적지가 클라우드라 캐시가 비워지며 실제 소모가 적을 수 있으면 --allow-tight(진행 중 가드는 그대로).", flush=True)
        sys.exit(2)
    print(msg + ". --allow-tight로 시작, 진행 중 가드가 지킴.", flush=True)
guard = DiskGuard(a.min_free, D)
t0 = time.time(); counts = {"ok": 0, "skip": 0, "link": 0, "conflict": 0, "stopped": 0}; errs = []; conflicts = []; stopped = set()

def one(pair):
    sp, dp = pair
    if not guard.ok(0 if os.path.islink(sp) or os.path.lexists(dp) else os.lstat(sp).st_size):
        return "stopped", sp, ""
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
            if res == "stopped": stopped.add(sp)
        if n % 1000 == 0: print(f"  {n:,}/{len(items):,} · {time.time()-t0:.0f}s", flush=True)

bad = 0; conf = set(conflicts)
for sp, dp in items:
    if os.path.islink(sp) or sp in conf or sp in stopped: continue
    if not os.path.exists(dp) or os.path.getsize(dp) != os.path.getsize(sp): bad += 1
if errs or conflicts:
    with open(a.errors, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["src", "error"]); w.writerows(errs); w.writerows((c, "충돌: 목적지에 같은 이름의 다른 파일(그대로 둠)") for c in conflicts)
print(f"완료: 복사 {counts['ok']:,} · 건너뜀 {counts['skip']:,} · 링크 {counts['link']:,} · 충돌 {counts['conflict']:,} · 오류 {len(errs)} · 검증 불일치 {bad} · {time.time()-t0:.0f}s"
      + (f" · 목록 {a.errors}" if errs or conflicts else ""))
if stopped:
    print(f"디스크 가드로 중단: 여유 {guard.low:.1f} GiB < 기준 {a.min_free:g} GiB · 남은 파일 {len(stopped):,}."
          " 공간을 비운 뒤(클라우드 캐시 '다운로드 제거'·'온라인 전용' 등) 같은 명령을 다시 실행하면 이어서 복사합니다.", flush=True)
    print("STOPPED_DISK", flush=True); sys.exit(3)
print("ALL_DONE", flush=True)
