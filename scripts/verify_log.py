#!/usr/bin/env python3
"""Independent check of what the log says happened ("다시 세어 보기"). Read-only.

  verify_log.py --log <master>/_정리로그/moves_v2.csv [--since 2026-11-20T10:00]

For every row since --since: move → destination exists and source is gone; copy → destination exists and,
if the source still exists, sizes match; mkdir → folder exists. A destination that a later row moved on is
followed, not counted as missing. Prints the counts and every mismatch; exit code 1 if any mismatch."""
import argparse, csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import nfc

ap = argparse.ArgumentParser()
ap.add_argument("--log", required=True)
ap.add_argument("--since", default="", help="only rows whose time >= this ISO prefix")
a = ap.parse_args()
rows = [r for r in csv.DictReader(open(a.log, encoding="utf-8")) if r["time"] >= a.since]
moved_on = {nfc(r["src"]) for r in rows if r["action"] in ("move", "rename", "trash")}
ok = bad = 0; counts = {}; problems = []
for r in rows:
    act, src, dst = r["action"], r["src"], r["dst"]
    if act not in ("move", "rename", "copy", "mkdir"):
        continue
    counts[act] = counts.get(act, 0) + 1
    if act in ("move", "rename", "copy") and nfc(dst) in moved_on and not os.path.exists(dst):
        ok += 1; continue  # moved again by a later row
    if act in ("move", "rename"):
        good = os.path.exists(dst) and not os.path.exists(src); why = "목적지 없음" if not os.path.exists(dst) else "원본이 아직 있음"
    elif act == "copy":
        good = os.path.exists(dst) and (not os.path.exists(src) or os.path.getsize(src) == os.path.getsize(dst)); why = "목적지 없음" if not os.path.exists(dst) else "크기 다름"
    else:
        good = os.path.isdir(dst); why = "폴더 없음"
    if good: ok += 1
    else: bad += 1; problems.append((act, src, dst, why))
print(f"기록 {len(rows)}줄 중 확인 대상 {ok + bad} ({', '.join(f'{k} {v}' for k, v in counts.items())}) · 일치 {ok} · 불일치 {bad}")
for act, src, dst, why in problems[:30]:
    print(f"  ✗ {act} {why}: {nfc(dst)[-90:]}")
sys.exit(1 if bad else 0)
