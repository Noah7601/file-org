"""Smoke test for the bundled scripts. Run it first in any new environment (macOS, Windows, Linux).

  python3 tests/smoke_test.py                 # temp work dir, scripts from ../scripts
  python3 tests/smoke_test.py --cloud-dir "C:\\Users\\<me>\\OneDrive"   # + read-only lstat check of cloud-only files

Builds a small tree (Korean names incl. an NFD one, identical/different same-name files, a 0-byte file,
an excluded node_modules), then runs inventory → find_dupes → apply_moves --dedupe --mkdir → find_dupes --apply
→ copy_tree twice → copy_tree onto a pre-filled destination (no overwrite, no .part) → disk guard (start/stop/resume, hook) → docset checker, zip extraction, control tower functions. Only the work dir is written; --cloud-dir is never read, only lstat'ed.
Verified 2026-11 on macOS 26 (all items) and Windows 11 / Python 3.12 (the 28 items of 2026-11-13; later checks not yet run on Windows). Exit code 1 on any FAIL."""
import argparse, csv, hashlib, json, os, shutil, subprocess, sys, tempfile, time, unicodedata
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
def run(script, *args, free=100, stdin=None):
    env = dict(os.environ, FILEORG_TEST_FREE_GIB=str(free))   # deterministic disk guard regardless of this machine's disk
    r = subprocess.run([PY, os.path.join(SK, script), *args], capture_output=True, env=env, input=stdin)
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

for d in ("src", "dst", "_정리로그", "격리", "격리2", "inv_log_test"):
    if os.path.isdir(os.path.join(WORK, d)): shutil.rmtree(os.path.join(WORK, d))
A, B, C, D, E, F = (bytes([i]) * 1000 for i in (1, 2, 3, 4, 5, 6))
put("40_프로젝트/2025_프로젝트A/기타/보고서.pdf", A)
put("40_프로젝트/2025_프로젝트A/증빙/견적서.hwp", C)
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
    w.writerow(["00_INBOX/보고서.pdf", "40_프로젝트/2025_프로젝트A/기타", "동일 내용", "✓"])
    w.writerow(["00_INBOX/견적서.hwp", "40_프로젝트/2025_프로젝트A/증빙", "다른 판", "✓"])
    w.writerow([os.path.join("00_INBOX", "카페.txt"), "40_프로젝트/2025_프로젝트A/기타", "NFC + OS 구분자", "✓"])
    w.writerow(["00_INBOX/하위/깊은 폴더/메모.txt", "20_재무_세무/2025", "슬래시 + 신설", "✓"])
    w.writerow(["00_INBOX/빈파일.txt", "99_Archive/기타", "미승인", ""])
Q = os.path.join(WORK, "격리")
base = ["--root", SRC, "--proposals", prop, "--log", LOG, "--dedupe", "--quarantine", Q, "--mkdir", "--sleep", "0.2"]
rc, out = run("apply_moves.py", *base)
check("apply_moves dry-run 대상 4·원본 없음 0", "대상 4 · 원본 없음 0" in out, last(out, 0))
check("apply_moves dry-run은 로그를 안 씀", not os.path.exists(LOG))
check("apply_moves dry-run: 미승인 줄 수와 기준 폴더를 알려 줌, 새 최상위 폴더 경고", "미승인 1" in out and "기준 폴더(--root)" in out and "새 최상위 폴더 '20_재무_세무'" in out)
rc, out = run("apply_moves.py", *base, "--preview")
check("apply_moves --preview: 승인 전 전체 계획(5줄)을 보여 주고 아무것도 안 씀", "대상 5" in out and "미리보기" in out and not os.path.exists(LOG), last(out, 1))
rc, out = run("apply_moves.py", *base, "--preview", "--apply")
check("apply_moves --preview는 --apply와 함께 거부", rc != 0 and os.path.exists(os.path.join(SRC, "00_INBOX", "보고서.pdf")))
prop_out = os.path.join(WORK, "proposals_out.csv")
with open(prop_out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["src", "dest", "why", "approved"]); w.writerow(["00_INBOX/보고서.pdf", "../밖", "기준 밖", "✓"])
rc, out = run("apply_moves.py", "--root", SRC, "--proposals", prop_out, "--log", LOG, "--apply", "--mkdir")
check("apply_moves: 기준 폴더 밖 목적지는 건너뜀", "기준 밖 목적지 1" in out and not os.path.exists(os.path.join(WORK, "밖")) and os.path.exists(os.path.join(SRC, "00_INBOX", "보고서.pdf")), last(out, 1))
rc, out = run("apply_moves.py", *base, "--apply")
check("apply_moves --apply rc=0·오류 0", rc == 0 and "오류 0" in out, " | ".join(l for l in out.splitlines() if "·" in l)[:120])
k = os.path.join(SRC, "40_프로젝트", "2025_프로젝트A", "기타")
check("동일 내용 → 격리 폴더", os.path.exists(os.path.join(Q, "00_INBOX", "보고서.pdf")) and not os.path.exists(os.path.join(SRC, "00_INBOX", "보고서.pdf")))
check("다른 판 → ' (2)' 접미", os.path.exists(os.path.join(SRC, "40_프로젝트", "2025_프로젝트A", "증빙", "견적서 (2).hwp")))
check("원본 덮어쓰기 없음", sha(os.path.join(SRC, "40_프로젝트", "2025_프로젝트A", "증빙", "견적서.hwp")) == hashlib.sha1(C).hexdigest())
check("NFD 파일을 NFC 행으로 찾아 이동", sum(nfc(n) == "카페.txt" for n in os.listdir(k)) == 1 and not any(nfc(n) == "카페.txt" for n in os.listdir(os.path.join(SRC, "00_INBOX"))))
check("슬래시 경로 + --mkdir 신설 이동", os.path.exists(os.path.join(SRC, "20_재무_세무", "2025", "메모.txt")))
check("미승인 행은 그대로", os.path.exists(os.path.join(SRC, "00_INBOX", "빈파일.txt")))
rows = list(csv.DictReader(open(LOG, encoding="utf-8")))
acts = {x: sum(1 for r in rows if r["action"] == x) for x in ("move", "mkdir", "error")}
check("로그 move 4 · mkdir 1 · error 0", acts == {"move": 4, "mkdir": 1, "error": 0}, str(acts))

# 4. find_dupes --apply (keeper = the name without ' (2)')
Q2 = os.path.join(WORK, "격리2")
rc, out = run("find_dupes.py", SRC, "--apply", "--quarantine", Q2, "--log", LOG, "--tag", "시험 승인 '전부 승인'")
check("find_dupes --apply 격리 1/1", "격리 1/1" in out, last(out))
check("find_dupes --tag: 승인 문구가 로그 사유에 남음", any(r["reason"].startswith("시험 승인 '전부 승인'") for r in csv.DictReader(open(LOG, encoding="utf-8"))))
rc, out = run("verify_log.py", "--log", LOG)
check("verify_log: 기록대로 실제 파일이 있는지 다시 세어 봄(불일치 0)", rc == 0 and "불일치 0" in out, last(out, 0))
badlog = os.path.join(WORK, "bad_log.csv")
shutil.copy(LOG, badlog)
with open(badlog, "a", newline="", encoding="utf-8") as f:
    csv.writer(f).writerow(["2099-01-01T00:00:00", "move", os.path.join(SRC, "없음.txt"), os.path.join(SRC, "없는곳", "없음.txt"), "가짜"])
rc, out = run("verify_log.py", "--log", badlog)
check("verify_log: 기록과 다르면 불일치로 잡고 rc=1", rc == 1 and "불일치 1" in out, last(out, 0))
INV = os.path.join(WORK, "inv_log_test"); os.makedirs(os.path.join(INV, "_정리로그"), exist_ok=True)
for rel in ("a.txt", os.path.join("_정리로그", "moves_v2.csv")):
    with open(os.path.join(INV, rel), "w") as f: f.write("x")
rc, out = run("inventory.py", INV)
check("inventory: _정리로그(기록 폴더)는 세지 않음", "파일 1 " in out, last(out, 1))
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

# 5c. disk guard: refuse to start when short, stop cleanly while running, resume after space is freed
DG = os.path.join(WORK, "dst_guard"); eg = os.path.join(WORK, "copy_errors_g.csv")
rc, out = run("copy_tree.py", SRC, DG, "--errors", eg, free=5)
check("디스크 가드: 여유 부족이면 복사를 시작하지 않음(rc=2, 파일 0)", rc == 2 and "시작하지 않음" in out and not os.path.exists(DG), last(out))
rc, out = run("copy_tree.py", SRC, DG, "--errors", eg, "--allow-tight", free=5)
copied = sum(len(fn) for dp, dn, fn in os.walk(DG)) if os.path.isdir(DG) else 0
check("디스크 가드: 진행 중 기준 아래면 멈춤(rc=3, STOPPED_DISK, 복사 0)", rc == 3 and "STOPPED_DISK" in out and copied == 0, last(out))
rc, out = run("copy_tree.py", SRC, DG, "--errors", eg)
check("디스크 가드: 공간 확보 뒤 같은 명령으로 이어서 완료", rc == 0 and "ALL_DONE" in out and "검증 불일치 0" in out, last(out, -2))
rc, out = run("copy_tree.py", SRC, os.path.join(WORK, "dst_guard_off"), "--errors", eg, "--min-free", "0", free=1)
check("디스크 가드: --min-free 0이면 끔", rc == 0 and "ALL_DONE" in out, last(out, -2))
rc, out = run("find_dupes.py", SRC, free=5)
check("디스크 가드: find_dupes는 해시 전에 멈추고 아무것도 안 옮김(rc=3)", rc == 3 and "STOPPED_DISK" in out, last(out))
HOOK = os.path.join(os.path.dirname(SK), "hooks", "disk_guard_hook.py")
def hook(cmd, free):
    env = dict(os.environ, FILEORG_TEST_FREE_GIB=str(free))
    return subprocess.run([PY, HOOK], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}).encode(), capture_output=True, env=env).returncode
check("훅 예시: 여유 부족 + copy_tree면 막음(2), 충분하면 통과(0), 관계없는 명령은 통과(0)",
      hook("python3 scripts/copy_tree.py a b", 3) == 2 and hook("python3 scripts/copy_tree.py a b", 50) == 0 and hook("ls -la", 3) == 0)

# 7. 문서세트 체크기 · 제출 zip 낱개 보관 · 관제탑(서버는 띄우지 않고 함수만)
import zipfile
EV = os.path.join(WORK, "ev"); RULES = os.path.join(os.path.dirname(SK), "references", "docset_rules.example.json")
for d in ("외주_디자인_거래처A_2603", "구매_원료_거래처B_2602"): os.makedirs(os.path.join(EV, d))
def ev(rel, data=b"x"):
    p = os.path.join(EV, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)
for f in ("1_과업지시서_거래처A.pdf", "2_계약서_거래처A.pdf", "3_견적서_거래처A.pdf", "4_비교견적서_C.pdf", "4_비교견적서_D.pdf",
          "6_사업자등록증_거래처A.pdf", "8_이체확인증_거래처A.pdf", "9_검수확인서_거래처A.pdf"): ev("외주_디자인_거래처A_2603/" + f)
with zipfile.ZipFile(os.path.join(EV, "외주_디자인_거래처A_2603", "제출본.zip"), "w") as z:
    z.writestr("5_세금계산서_거래처A.pdf", b"tax"); z.writestr("7_통장사본_거래처A.pdf", b"bank")
for f in ("1_구매계획서.pdf", "2_견적서_거래처B.pdf", "3_세금계산서_거래처B.pdf", "입고사진.jpg"): ev("구매_원료_거래처B_2602/" + f)
ev("../계약·변경/사업자등록증_거래처B.pdf")
OUTD = os.path.join(WORK, "checks")
rc, out = run("check_docsets.py", "--root", EV, "--rules", RULES, "--out", OUTD, "--name", "시험")
rows = list(csv.DictReader(open(os.path.join(OUTD, "시험_warnings.csv"), encoding="utf-8-sig")))
st = {(r["folder"][:2], r["item"]): r["status"] for r in rows}
check("체크기 실행 rc=0", rc == 0, last(out))
check("체크기: zip 안에만 있는 서류를 구분", st.get(("외주", "세금계산서 또는 카드전표")) == "zip 안에만" and st.get(("외주", "거래처 통장사본")) == "zip 안에만", str(st))
check("체크기: 교차 폴더에 있는 서류는 '다른 폴더'", st.get(("구매", "거래처 사업자등록증")) == "다른 폴더")
check("체크기: 진짜 누락은 '없음'", st.get(("구매", "이체확인증")) == "없음")
check("체크기는 파일을 안 옮김", len(os.listdir(os.path.join(EV, "외주_디자인_거래처A_2603"))) == 9)
ZLOG = os.path.join(WORK, "zlog.csv")
rc, out = run("extract_zip_only.py", "--root", EV, "--log", ZLOG)
check("zip 꺼내기 dry-run 2건·로그 없음", "꺼낼 파일 2개" in out and not os.path.exists(ZLOG), last(out, 0))
rc, out = run("extract_zip_only.py", "--root", EV, "--log", ZLOG, "--apply")
zdir = os.path.join(EV, "외주_디자인_거래처A_2603")
check("zip 꺼내기 적용: 낱개 2건 복사·zip 유지", "복사 2" in out and os.path.exists(os.path.join(zdir, "5_세금계산서_거래처A.pdf")) and os.path.exists(os.path.join(zdir, "제출본.zip")), last(out))
rc, out = run("check_docsets.py", "--root", EV, "--rules", RULES, "--out", OUTD, "--name", "시험")
st2 = {(r["folder"][:2], r["item"]): r["status"] for r in csv.DictReader(open(os.path.join(OUTD, "시험_warnings.csv"), encoding="utf-8-sig"))}
check("꺼낸 뒤 재검사: '있음'으로 바뀜", ("외주", "세금계산서 또는 카드전표") not in st2)
sys.path.insert(0, SK); import control_tower as ct
tree = ct.scan(SRC)
n_walk = sum(1 for dp, dn, fn in os.walk(SRC) if "node_modules" not in dp for f in fn if not f.startswith("."))
check("관제탑 scan: 파일 수·0바이트가 직접 센 값과 같음", tree["files"] == n_walk and tree["zero"] == 1, f"scan {tree['files']} / walk {n_walk} · zero {tree['zero']}")
progs = ct.read_checks(OUTD)
check("관제탑이 체크기 보고서를 읽음", progs and progs[0]["folders"] and any(f["missing"] for f in progs[0]["folders"]), str([(f["folder"][:8], f["missing"]) for f in progs[0]["folders"]]) if progs else "")
class _A: root = SRC; log = None; checks = OUTD; refresh_cmd = None; graph_url = None; watch = None
tw = ct.Tower(_A())
check("관제탑 파일 열기 제한: 마스터 밖·실행 파일 거부", tw.resolve("../../etc") is None and tw.resolve("x.app") is None and tw.resolve("90_미디어") is not None)
H = ct.make_handler(tw, 8765)
class _R(H):
    def __init__(self, h): self.headers = h
ok_cases = [({"Host": "localhost:8765", "X-Tower": "1", "Sec-Fetch-Site": "same-origin"}, True, True), ({"Host": "localhost:8765", "Sec-Fetch-Site": "cross-site", "X-Tower": "1"}, True, False),
            ({"Host": "localhost:8765"}, True, False), ({"Host": "evil.test:8765"}, False, False), ({"Host": "127.0.0.1:8765"}, False, True)]
check("관제탑 요청 검사(다른 사이트·다른 호스트·헤더 없는 쓰기 거부)", all(_R(h).allowed(m) == want for h, m, want in ok_cases))

# 8. 지속 관리(watch.py): 기준 사진 → 변화 판정
WR, WS = os.path.join(WORK, "wroot"), os.path.join(WORK, "wstate")
def wput(rel, data):
    p = os.path.join(WR, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)
wput("10_회사/a.pdf", b"aaaa"); wput("20_재무/b.pdf", b"bbbb"); wput("20_재무/c.pdf", b"cccc"); wput("30_계약/d.pdf", b"dddd")
rc, out = run("watch.py", "--root", WR, "--state", WS)
check("watch 첫 실행은 기준 사진만", rc == 0 and "기준 사진" in out, last(out))
os.makedirs(os.path.join(WR, "90_보관"), exist_ok=True); os.rename(os.path.join(WR, "20_재무/b.pdf"), os.path.join(WR, "90_보관/b.pdf"))   # 이동
os.remove(os.path.join(WR, "20_재무/c.pdf"))                                    # 사라짐
open(os.path.join(WR, "30_계약/d.pdf"), "wb").close()                            # 0바이트가 됨
wput("새파일.pdf", b"new"); wput("00_INBOX/a.pdf", b"aaaa")                      # 맨 위 새 파일, 중복 후보
time.sleep(1.1)
rc, out = run("watch.py", "--root", WR, "--state", WS)
W = json.load(open(os.path.join(WS, "watch_latest.json"), encoding="utf-8"))
check("watch: 이동을 사라짐과 구분", len(W["moved"]) == 1 and W["moved"][0]["to"].endswith("90_보관/b.pdf"), str(W["moved"]))
check("watch: 진짜 사라진 파일", [g["path"] for g in W["gone"]] == ["master/20_재무/c.pdf"], str(W["gone"]))
check("watch: 새 0바이트", W["new_zero"] == ["master/30_계약/d.pdf"], str(W["new_zero"]))
check("watch: 새 파일 위치·중복 후보", {x["where"] for x in W["new"]} == {"마스터 맨 위", "INBOX"} and len(W["dup_candidates"]) == 1, str(W["new"]))
check("watch는 파일을 안 옮김", os.path.exists(os.path.join(WR, "90_보관/b.pdf")) and not os.path.exists(os.path.join(WR, "20_재무/c.pdf")))
check("관제탑이 watch 결과를 읽음", ct.read_watch(WS) is not None and len(ct.read_watch(WS)["gone"]) == 1)
nsnap = len(os.listdir(os.path.join(WS, "snapshots")))
rc, out = run("watch.py", "--root", WR, "--state", WS, "--against-days", "7")
WK = json.load(open(os.path.join(WS, "watch_week.json"), encoding="utf-8"))
check("watch 주간 비교: 가장 오래된 사진 기준, 새 사진 저장 안 함", len(os.listdir(os.path.join(WS, "snapshots"))) == nsnap and len(WK["gone"]) == 1 and len(WK["new"]) == 2, last(out))

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
