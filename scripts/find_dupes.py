#!/usr/bin/env python3
"""Find content-identical duplicates (same size, then sha1). Default dry-run prints groups.
--quarantine DIR --apply moves every non-keeper into DIR/<original relative path> and logs it.
Keeper = the copy whose name has no ' (2)' / ' (iCloud)' style suffix, then the shallowest path."""
import argparse, csv, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import size_index, sha1, nfc, log_row, EXCLUDE_DIRS

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("--quarantine", help="dir to move duplicates into (keeps relative paths)")
ap.add_argument("--apply", action="store_true")
ap.add_argument("--log", help="moves_v2.csv path (required with --apply)")
ap.add_argument("--out", help="write groups CSV")
ap.add_argument("--exclude", nargs="*", default=sorted(EXCLUDE_DIRS))
ap.add_argument("--min-size", type=int, default=1)
a = ap.parse_args()
root = os.path.abspath(a.root)
if a.apply and not (a.quarantine and a.log):
    sys.exit("--apply needs --quarantine and --log")

SUFFIX = re.compile(r" \((\d+|iCloud|OneDrive|복사본)\)(?=\.[^.]*$)|(?:복사본|copy)(?=\.[^.]*$)", re.I)
def rank(p):
    rel = os.path.relpath(p, root)
    return (1 if SUFFIX.search(os.path.basename(rel)) else 0, rel.count(os.sep), len(rel))

groups = []
for size, paths in size_index(root, set(a.exclude)).items():
    if len(paths) < 2 or size < a.min_size:
        continue
    by_hash = {}
    for p in paths:
        by_hash.setdefault(sha1(p), []).append(p)
    for h, ps in by_hash.items():
        if len(ps) > 1:
            ps.sort(key=rank); groups.append((size, ps[0], ps[1:]))

dups = sum(len(d) for _, _, d in groups); wasted = sum(s * len(d) for s, _, d in groups)
print(f"중복 묶음 {len(groups)} · 중복 파일 {dups} · 회수 가능 {wasted/2**30:.2f} GiB ({'적용' if a.apply else 'dry-run'})")
for size, keep, ds in sorted(groups, key=lambda g: -g[0] * len(g[2]))[:15]:
    print(f"  보관 {nfc(os.path.relpath(keep, root))[:70]}")
    for d in ds:
        print(f"    중복 {nfc(os.path.relpath(d, root))[:70]} ({size:,} B)")
if a.out:
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["size", "keeper", "duplicate"])
        for size, keep, ds in groups:
            for d in ds:
                w.writerow([size, nfc(os.path.relpath(keep, root)), nfc(os.path.relpath(d, root))])
    print("CSV:", a.out)
if a.apply:
    moved = 0
    for size, keep, ds in groups:
        for d in ds:
            q = os.path.join(a.quarantine, os.path.relpath(d, root))
            if os.path.exists(q):
                continue
            os.makedirs(os.path.dirname(q), exist_ok=True); os.rename(d, q); time.sleep(0.3)
            if os.path.exists(q) and not os.path.exists(d) and os.path.getsize(q) == size:
                moved += 1; log_row(a.log, "move", d, q, f"동일 내용 중복 격리(보관본 {nfc(os.path.relpath(keep, root))})")
            else:
                log_row(a.log, "error", d, q, "격리 사후 검증 실패")
    print(f"격리 {moved}/{dups} → {a.quarantine}")
