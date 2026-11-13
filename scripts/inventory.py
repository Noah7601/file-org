#!/usr/bin/env python3
"""Read-only inventory of a folder tree: counts, bytes, zero-byte files, cloud-only (dataless) files,
extension mix, and an optional per-file CSV. Use it before proposing anything."""
import argparse, collections, csv, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import walk_files, is_dataless, nfc, EXCLUDE_DIRS, free_gib

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("--out", help="write per-file CSV here")
ap.add_argument("--exclude", nargs="*", default=sorted(EXCLUDE_DIRS), help="dir names to prune")
ap.add_argument("--top", type=int, default=12)
a = ap.parse_args()

n = size = zero = dataless = links = 0
ext = collections.Counter(); ext_bytes = collections.Counter(); years = collections.Counter()
rows = []
for p, rel, st in walk_files(a.root, set(a.exclude)):
    n += 1; size += st.st_size
    e = os.path.splitext(rel)[1].lower() or "(없음)"
    ext[e] += 1; ext_bytes[e] += st.st_size
    years[time.strftime("%Y", time.localtime(st.st_mtime))] += 1
    z = st.st_size == 0; d = is_dataless(p); l = os.path.islink(p)
    zero += z; dataless += d; links += l
    if a.out:
        rows.append([nfc(rel), st.st_size, time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)), e, int(z), int(d), int(l)])

print(f"{a.root}\n  파일 {n:,} · {size/2**30:.2f} GiB · 0바이트 {zero:,} · 클라우드 전용 {dataless:,} · 링크 {links:,} · 디스크 여유 {free_gib(a.root):.1f} GiB")
print("  확장자(상위):", ", ".join(f"{k} {v:,}({ext_bytes[k]/2**20:.0f}MB)" for k, v in ext.most_common(a.top)))
print("  수정연도:", ", ".join(f"{k} {v:,}" for k, v in sorted(years.items())))
if a.out:
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["rel", "size", "mtime", "ext", "zero", "dataless", "link"]); w.writerows(rows)
    print("  CSV:", a.out)
