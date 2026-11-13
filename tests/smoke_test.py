"""Smoke test for the bundled scripts. Run it first in any new environment (macOS, Windows, Linux).

  python3 tests/smoke_test.py                 # temp work dir, scripts from ../scripts
  python3 tests/smoke_test.py --cloud-dir "C:\\Users\\<me>\\OneDrive"   # + read-only lstat check of cloud-only files

Builds a small tree (Korean names incl. an NFD one, identical/different same-name files, a 0-byte file,
an excluded node_modules), then runs inventory → find_dupes → apply_moves --dedupe --mkdir → find_dupes --apply
→ copy_tree twice → copy_tree onto a pre-filled destination (no overwrite, no .part). Only the work dir is written; --cloud-dir is never read, only lstat'ed.
Verified 2026-11 on macOS 26 and Windows 11 (Python 3.12). Exit code 1 on any FAIL."""
import argparse, csv, hashlib, os, shutil, subprocess, sys, tempfile, unicodedata
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError): pass
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--scripts", default=os.path.join(os.path.dirname(HERE), "scripts"))
ap.add_argument("--work", help="work dir (default: a fresh temp dir)")
ap.add_argument("--cloud-dir", help="OneDrive/iCloud folder: top-level files are lstat'ed read-only to check is_dataless")
ap.add_argument("--keep", action="store_true", help="keep the work dir afterwards")
a = ap.parse_args()
SK = os.path.abspath(a.scripts); WORK = os.path.abspath(a.work) if a.work else tempfile.mkdtemp(prefix="fileorg_smoke_")
PY = sys.executable; SRC = os.path.join(WORK, "src"); LOG = os.path.join(WORK, "_정리로그", "moves_v2.csv")
R = []
def check(name, ok, detail=""):
    R.append((name, bool(ok))); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
def run(script, *args):
    r = subprocess.run([PY, os.path.join(SK, script), *args], capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
def put(rel, data):
    p = os.path.join(SRC, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)
def nfd(s): return unicodedata.normalize("NFD", s)
def nfc(s): return unicodedata.normalize("NFC", s)
def sha(p):
    with open(p, "rb") as f: return hashlib.sha1(f.read()).hexdigest()
def last(out, n=-1, w=100):
    ls = [l for l in out.splitlines() if l.strip()]; return ls[n][:w] if ls else ""

for d in ("src", "dst", "_정리로그", "격리", "격리2"):
    if os.path.isdir(os.path.join(WORK, d)): shutil.rmtree(os.path.join(WORK, d))
A, B, C, D, E, F = (bytes([i]) * 1000 for i in (1, 2, 3, 4, 5, 6))
put("40_지원사업/2025_지원사업A/기타/보고서.pdf", A)
put("40_지원사업/2025_지원사업A/집행증빙/견적서.hwp", C)
put("00_INBOX/보고서.pdf", A)                 # same name + content at dest → dedupe quarantine
put("00_INBOX/견적서.hwp", B)                 # same name, different content → ' (2)'
put(nfd("00_INBOX/카페.txt"), D)              # NFD on disk; proposal row uses NFC + OS separator
put("00_INBOX/하위/깊은 폴더/메모.txt", E)     # proposal row uses '/' and a new dest dir (--mkdir)
put("00_INBOX/빈파일.txt", b"")               # 0 bytes; row NOT approved → must stay
put("90_미디어/사진.jpg", F); put("90_미디어/사진 (2).jpg", F)   # for find_dupes --apply
put("node_modules/junk.js", b"x" * 10)        # must be excluded
print("작업 폴더:", WORK, "· 스크립트:", SK, flush=True)

# 1. inventory (read-only, UTF-8 output, exclusion, free_gib)
rc, out = run("inventory.py", SRC)
check("inventory 실행 rc=0", rc == 0, last(out))
check("inventory 한글 출력 깨짐 없음", "파일" in out and "\ufffd" not in out)
check("inventory 파일 수 9(node_modules 제외)", "파일 9 " in out, last(out, 1))
check("inventory 0바이트 1", "0바이트 1 " in out)
check("inventory 디스크 여유 > 0", "디스크 여유" in out and "GiB" in out)

# 2. find_dupes dry-run: 2 groups, nothing moved
rc, out = run("find_dupes.py", SRC)
check("find_dupes dry-run 묶음 2", "중복 묶음 2 " in out, last(out, 0))
check("find_dupes dry-run은 파일을 안 옮김", os.path.exists(os.path.join(SRC, "00_INBOX", "보고서.pdf")))

# 3. apply_moves: dry-run then --apply --dedupe --mkdir
prop = os.path.join(WORK, "proposals.csv")
with open(prop, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["src", "dest", "why", "approved"])
    w.writerow(["00_INBOX/보고서.pdf", "40_지원사업/2025_지원사업A/기타", "동일 내용", "✓"])
    w.writerow(["00_INBOX/견적서.hwp", "40_지원사업/2025_지원사업A/집행증빙", "다른 판", "✓"])
    w.writerow([os.path.join("00_INBOX", "카페.txt"), "40_지원사업/2025_지원사업A/기타", "NFC + OS 구분자", "✓"])
    w.writerow(["00_INBOX/하위/깊은 폴더/메모.txt", "20_재무_세무/2025", "슬래시 + 신설", "✓"])
    w.writerow(["00_INBOX/빈파일.txt", "99_Archive/기타", "미승인", ""])
Q = os.path.join(WORK, "격리")
base = ["--root", SRC, "--proposals", prop, "--log", LOG, "--dedupe", "--quarantine", Q, "--mkdir", "--sleep", "0.2"]
rc, out = run("apply_moves.py", *base)
check("apply_moves dry-run 대상 4·원본 없음 0", "대상 4 · 원본 없음 0" in out, last(out, 0))
check("apply_moves dry-run은 로그를 안 씀", not os.path.exists(LOG))
rc, out = run("apply_moves.py", *base, "--apply")
check("apply_moves --apply rc=0·오류 0", rc == 0 and "오류 0" in out, " | ".join(l for l in out.splitlines() if "·" in l)[:120])
k = os.path.join(SRC, "40_지원사업", "2025_지원사업A", "기타")
check("동일 내용 → 격리 폴더", os.path.exists(os.path.join(Q, "00_INBOX", "보고서.pdf")) and not os.path.exists(os.path.join(SRC, "00_INBOX", "보고서.pdf")))
check("다른 판 → ' (2)' 접미", os.path.exists(os.path.join(SRC, "40_지원사업", "2025_지원사업A", "집행증빙", "견적서 (2).hwp")))
check("원본 덮어쓰기 없음", sha(os.path.join(SRC, "40_지원사업", "2025_지원사업A", "집행증빙", "견적서.hwp")) == hashlib.sha1(C).hexdigest())
check("NFD 파일을 NFC 행으로 찾아 이동", sum(nfc(n) == "카페.txt" for n in os.listdir(k)) == 1 and not any(nfc(n) == "카페.txt" for n in os.listdir(os.path.join(SRC, "00_INBOX"))))
check("슬래시 경로 + --mkdir 신설 이동", os.path.exists(os.path.join(SRC, "20_재무_세무", "2025", "메모.txt")))
check("미승인 행은 그대로", os.path.exists(os.path.join(SRC, "00_INBOX", "빈파일.txt")))
rows = list(csv.DictReader(open(LOG, encoding="utf-8")))
acts = {x: sum(1 for r in rows if r["action"] == x) for x in ("move", "mkdir", "error")}
check("로그 move 4 · mkdir 1 · error 0", acts == {"move": 4, "mkdir": 1, "error": 0}, str(acts))

# 4. find_dupes --apply (keeper = the name without ' (2)')
Q2 = os.path.join(WORK, "격리2")
rc, out = run("find_dupes.py", SRC, "--apply", "--quarantine", Q2, "--log", LOG)
check("find_dupes --apply 격리 1/1", "격리 1/1" in out, last(out))
check("접미 없는 쪽을 보관", os.path.exists(os.path.join(SRC, "90_미디어", "사진.jpg")) and os.path.exists(os.path.join(Q2, "90_미디어", "사진 (2).jpg")))

# 5. copy_tree: copy + verify, then re-run → everything skipped
DST = os.path.join(WORK, "dst"); errs = os.path.join(WORK, "copy_errors.csv")
rc, out = run("copy_tree.py", SRC, DST, "--workers", "4", "--errors", errs)
check("copy_tree 1회차 오류 0·검증 불일치 0", "오류 0 · 검증 불일치 0" in out and "ALL_DONE" in out, last(out, -2))
src_files = sorted(os.path.relpath(os.path.join(dp, f), SRC) for dp, dn, fn in os.walk(SRC) if "node_modules" not in dp for f in fn)
dst_files = sorted(os.path.relpath(os.path.join(dp, f), DST) for dp, dn, fn in os.walk(DST) for f in fn)
check("copy_tree 파일 집합 동일(node_modules 제외, NFD 이름 보존)", src_files == dst_files, f"src {len(src_files)} dst {len(dst_files)}")
check("copy_tree 크기 전부 일치", all(os.path.getsize(os.path.join(SRC, f)) == os.path.getsize(os.path.join(DST, f)) for f in src_files))
rc, out = run("copy_tree.py", SRC, DST, "--workers", "4", "--errors", errs)
check("copy_tree 2회차 전부 건너뜀(재개 가능)", f"복사 0 · 건너뜀 {len(src_files)}" in out, last(out, -2))

# 5b. copy_tree never overwrites a differing same-name file and leaves no .part behind
SC, DC = os.path.join(WORK, "src_c"), os.path.join(WORK, "dst_c"); os.makedirs(SC); os.makedirs(DC)
with open(os.path.join(SC, "x.txt"), "wb") as f: f.write(A)
with open(os.path.join(DC, "x.txt"), "wb") as f: f.write(b"DIFFERENT")       # pre-existing, must survive
with open(os.path.join(SC, "y.txt"), "wb") as f: f.write(B)
unreadable = None
if os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0:
    unreadable = os.path.join(SC, "noread.txt")
    with open(unreadable, "wb") as f: f.write(C)
    os.chmod(unreadable, 0)                                                   # forces a copy failure
rc, out = run("copy_tree.py", SC, DC, "--workers", "2", "--errors", os.path.join(WORK, "copy_errors_c.csv"), "--retry", "0")
with open(os.path.join(DC, "x.txt"), "rb") as f: kept = f.read() == b"DIFFERENT"
check("copy_tree 동명 다른 파일은 덮어쓰지 않고 충돌로 보고", "충돌 1" in out and kept, last(out, -2))
check("copy_tree 충돌 외 파일은 정상 복사", os.path.exists(os.path.join(DC, "y.txt")) and sha(os.path.join(DC, "y.txt")) == hashlib.sha1(B).hexdigest())
if unreadable:
    check("copy_tree 읽기 실패 → 오류 1, 잘린 파일 없음", "오류 1" in out and not os.path.exists(os.path.join(DC, "noread.txt")), last(out, -2))
    os.chmod(unreadable, 0o644)
check("copy_tree .part 잔여 없음", not any(n.endswith(".part") for dp, dn, fn in os.walk(WORK) for n in fn))

# 6. optional: cloud-only detection on a real sync folder, lstat only (nothing is opened)
if a.cloud_dir:
    sys.path.insert(0, SK); import fileorg_lib
    n = dl = flag = 0
    for e in os.scandir(a.cloud_dir):
        if e.is_file(follow_symlinks=False):
            n += 1; st = os.lstat(e.path); dl += fileorg_lib.is_dataless(e.path)
            flag += bool(getattr(st, "st_file_attributes", 0) & fileorg_lib.WIN_CLOUD_ATTRS) or bool(getattr(st, "st_flags", 0) & fileorg_lib.DATALESS)
    check("클라우드 전용 판정 = OS 플래그(읽기 전용 lstat)", n > 0 and dl == flag, f"최상위 파일 {n} · 클라우드 전용 {dl}")
    check("free_gib(cloud-dir) > 0", fileorg_lib.free_gib(a.cloud_dir) > 0, f"{fileorg_lib.free_gib(a.cloud_dir):.1f} GiB")

p = sum(ok for _, ok in R); print(f"\n결과: PASS {p} / FAIL {len(R) - p} / 총 {len(R)} · {sys.platform} Python {sys.version.split()[0]}", flush=True)
if not a.keep and not a.work:
    shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if p == len(R) else 1)
