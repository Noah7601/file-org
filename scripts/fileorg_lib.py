"""Shared helpers for file-org scripts. Standard library only; runs on macOS, Windows and Linux (Python 3.8+).

Rules baked in: NFC comparison, no shell globbing, never overwrite (copies land via .part + rename), retries for
cloud-only files (OneDrive Errno 60, iCloud dataless, Windows Files On-Demand), size verification."""
import csv, hashlib, os, re, shutil, sys, time, unicodedata

DATALESS = 0x40000000          # macOS st_flags bit for iCloud "cloud-only" files
EXCLUDE_DIRS = {"node_modules", ".venv", "venv", "site-packages", "__pycache__", "pydeps"}
SKIP_NAMES = {".DS_Store"}
RETRY = (0, 15, 30, 60, 120)   # seconds between attempts
WIN_CLOUD_ATTRS = 0x400000 | 0x1000  # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_OFFLINE (Windows Files On-Demand)

if os.name == "nt":            # Windows 콘솔(cp949)에서 한글 출력이 깨지지 않게
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def nfc(s):
    return unicodedata.normalize("NFC", str(s))


def is_dataless(path):
    """True if the file is cloud-only: macOS iCloud dataless flag, or Windows Files On-Demand attributes
    (OneDrive / iCloud for Windows placeholders). Reading such a file triggers a download."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if getattr(st, "st_flags", 0) & DATALESS:
        return True
    return bool(getattr(st, "st_file_attributes", 0) & WIN_CLOUD_ATTRS)


def walk_files(root, exclude=EXCLUDE_DIRS, skip_names=SKIP_NAMES):
    """Yield (abs_path, rel_path, lstat) for every file under root, pruning excluded dirs.
    Symlinks are yielded (lstat) but never followed."""
    root = os.path.abspath(root)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in exclude]
        for f in fn:
            if f in skip_names:
                continue
            p = os.path.join(dp, f)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            yield p, os.path.relpath(p, root), st


def sha1(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def size_index(root, exclude=EXCLUDE_DIRS):
    """size -> [paths]; 0-byte files excluded (stubs carry no content to compare)."""
    idx = {}
    for p, _, st in walk_files(root, exclude):
        if st.st_size and not os.path.islink(p):
            idx.setdefault(st.st_size, []).append(p)
    return idx


def find_twin(path, idx):
    """Return a path with identical content elsewhere in idx, or None. Hashes only same-size candidates."""
    size = os.path.getsize(path)
    cands = [c for c in idx.get(size, []) if os.path.abspath(c) != os.path.abspath(path)]
    if not cands:
        return None
    h = sha1(path)
    return next((c for c in cands if sha1(c) == h), None)


def resolve_nfc(root, rel):
    """Resolve rel under root even when stored names are NFD (iCloud/macOS) and rel is NFC."""
    p = root
    seps = os.sep + (os.altsep or "")          # Windows: both '\\' and '/'
    for part in re.split("[" + re.escape(seps) + "]", rel):
        if not part:
            continue
        cand = os.path.join(p, part)
        if os.path.lexists(cand):
            p = cand
            continue
        try:
            hit = next((c for c in os.listdir(p) if nfc(c) == nfc(part)), None)
        except OSError:
            return None
        if hit is None:
            return None
        p = os.path.join(p, hit)
    return p


def copy_with_retry(src, dst, retry=RETRY):
    """Copy one file; retries cover OneDrive Errno 60 and iCloud dataless timeouts.
    Writes to dst + '.part' and renames into place only on success, so a failed copy never leaves a
    truncated file under the real name. Never overwrites: an existing dst with the same size and mtime is
    a finished copy ('skip'); any other existing dst is left untouched ('conflict').
    Preserves mtime and permission bits; verifies size."""
    st = os.lstat(src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(src):
        if not os.path.lexists(dst):
            os.symlink(os.readlink(src), dst)
        return "link"
    if os.path.lexists(dst):
        if os.path.isfile(dst) and os.path.getsize(dst) == st.st_size and abs(os.path.getmtime(dst) - st.st_mtime) < 2:
            return "skip"
        return "conflict"
    part = dst + ".part"
    last = None
    for d in retry:
        if d:
            time.sleep(d)
        try:
            with open(src, "rb") as fi, open(part, "wb") as fo:
                shutil.copyfileobj(fi, fo, 1 << 20)
            if os.path.getsize(part) != st.st_size:
                raise OSError("size mismatch")
            os.utime(part, (st.st_atime, st.st_mtime))
            os.chmod(part, st.st_mode & 0o7777)
            if os.path.lexists(dst):            # appeared meanwhile (another worker or the sync client)
                os.remove(part)                 # our own temp file only, never user data
                return "conflict"
            os.replace(part, dst)
            return "ok"
        except OSError as e:
            last = e
    try:
        os.remove(part)                         # our own temp file only, never user data
    except OSError:
        pass
    raise OSError(f"{src}: {last}")


def log_row(log_path, action, src, dst, reason):
    new = not os.path.exists(log_path)
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    with open(log_path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "action", "src", "dst", "reason"])
        w.writerow([time.strftime("%Y-%m-%dT%H:%M:%S"), action, src, dst, reason])


def free_gib(path="."):
    return shutil.disk_usage(path).free / 2**30   # os.statvfs does not exist on Windows
