#!/usr/bin/env python3
"""Apply user-approved moves inside one volume. Default dry-run.

Proposals CSV columns: src, dest, why [, approved]
  src      file path relative to --root (NFC or NFD both fine)
  dest     destination DIRECTORY relative to --root (created only with --mkdir)
  approved optional; when the column exists only rows marked ✓/V/예 run (blank = not approved)

Never overwrites: a same-name file at dest is skipped and collected. With --dedupe the skipped rows are
compared by sha1: identical → moved to --quarantine/<src rel path>; different → moved to dest as 'name (2).ext'.
Every write is logged to --log (moves_v2.csv format) and verified (dest exists, src gone, size equal)."""
import argparse, csv, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fileorg_lib import nfc, resolve_nfc, sha1, log_row

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True); ap.add_argument("--proposals", required=True); ap.add_argument("--log", required=True)
ap.add_argument("--tag", default="승인 이동"); ap.add_argument("--apply", action="store_true")
ap.add_argument("--mkdir", action="store_true", help="allow creating dest dirs (only when the user approved new folders)")
ap.add_argument("--dedupe", action="store_true"); ap.add_argument("--quarantine", help="dir for identical duplicates")
ap.add_argument("--sleep", type=float, default=0.5, help="settle time after rename on cloud mounts")
a = ap.parse_args()
R = os.path.abspath(a.root); OK = {"✓", "V", "v", "예", "y", "Y"}

plan, missing = [], []
for i, r in enumerate(csv.DictReader(open(a.proposals, encoding="utf-8-sig")), 1):
    if "approved" in r and nfc(r["approved"]).strip() not in OK:
        continue
    src = resolve_nfc(R, r["src"])
    if src is None or not os.path.isfile(src):
        missing.append(r["src"]); continue
    dest_dir = os.path.join(R, r["dest"])
    if nfc(os.path.dirname(src)) == nfc(dest_dir):
        continue  # already there
    plan.append((i, src, os.path.join(dest_dir, os.path.basename(src)), r.get("why", "")))
print(f"대상 {len(plan)} · 원본 없음 {len(missing)} ({'적용' if a.apply else 'dry-run'})")
for m in missing[:5]: print("  원본 없음:", m)

done = errors = 0; collide = []
for i, src, dst, why in plan:
    if os.path.exists(dst):
        collide.append((i, src, dst)); continue
    if not a.apply:
        print(f"  [{i}] {nfc(os.path.relpath(src, R))[:60]}\n       → {nfc(os.path.relpath(dst, R))[:60]}"); continue
    size = os.path.getsize(src)
    try:
        if not os.path.isdir(os.path.dirname(dst)):
            if not a.mkdir: raise OSError("목적지 폴더 없음(--mkdir 미지정)")
            os.makedirs(os.path.dirname(dst)); log_row(a.log, "mkdir", "", os.path.dirname(dst), f"{a.tag}: 폴더 신설")
        os.rename(src, dst); time.sleep(a.sleep)
        if os.path.exists(dst) and not os.path.exists(src) and os.path.getsize(dst) == size:
            done += 1; log_row(a.log, "move", src, dst, f"{a.tag}: {why}")
        else:
            raise OSError("사후 검증 실패")
    except OSError as e:
        errors += 1; log_row(a.log, "error", src, dst, f"{a.tag} 실패: {e}")
        if os.path.exists(dst) and not os.path.exists(src):
            try: os.rename(dst, src); log_row(a.log, "move", dst, src, "실패로 원복")
            except OSError: pass
print(f"이동 {done if a.apply else '(dry)'} · 동명 충돌 {len(collide)} · 오류 {errors}")

if a.dedupe and collide:
    same = diff = 0
    for i, src, dst in collide:
        identical = os.path.getsize(src) == os.path.getsize(dst) and sha1(src) == sha1(dst)
        if identical:
            same += 1
            if not a.quarantine: print(f"  동일: [{i}] {nfc(os.path.relpath(src, R))[:60]} (격리 폴더 미지정)"); continue
            q = os.path.join(a.quarantine, os.path.relpath(src, R))
            if a.apply:
                os.makedirs(os.path.dirname(q), exist_ok=True); os.rename(src, q); time.sleep(a.sleep)
                log_row(a.log, "move", src, q, f"{a.tag}: 동일 내용 중복 격리(보관본 {nfc(os.path.relpath(dst, R))})")
            else: print(f"  동일→격리: [{i}] {nfc(os.path.relpath(src, R))[:60]}")
        else:
            diff += 1; stem, ext = os.path.splitext(dst); k = 2; alt = f"{stem} ({k}){ext}"
            while os.path.exists(alt): k += 1; alt = f"{stem} ({k}){ext}"
            if a.apply:
                size = os.path.getsize(src); os.rename(src, alt); time.sleep(a.sleep)
                if os.path.exists(alt) and os.path.getsize(alt) == size: log_row(a.log, "move", src, alt, f"{a.tag}: 동명 다른 판, 접미")
                else: errors += 1; log_row(a.log, "error", src, alt, f"{a.tag}: 접미 이동 검증 실패")
            else: print(f"  다름→접미: [{i}] {nfc(os.path.relpath(src, R))[:60]} → {os.path.basename(alt)}")
    print(f"동명 충돌 {len(collide)} → 동일 {same} / 다름 {diff} · 오류 {errors}")
print("DONE")
