#!/usr/bin/env python3
"""Optional Claude Code PreToolUse hook: refuse to start a file-org copy/hash/move script when the local disk
is below the guard (default 8 GiB, env FILEORG_MIN_FREE_GIB). It only adds a check before the command starts;
the scripts themselves keep guarding while they run, for any agent or a person. Standard library only.

settings.json (user or project):
  {"hooks": {"PreToolUse": [{"matcher": "Bash",
     "hooks": [{"type": "command", "command": "python3 ~/.claude/skills/file-org/hooks/disk_guard_hook.py"}]}]}}
Exit 0 = allow, exit 2 = block (the message on stderr is shown to the agent)."""
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from fileorg_lib import local_free_gib, MIN_FREE_GIB

WATCHED = re.compile(r"\b(copy_tree|find_dupes|apply_moves|extract_zip_only)\.py\b")
try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
cmd = str((data.get("tool_input") or {}).get("command", ""))
if not WATCHED.search(cmd):
    sys.exit(0)
limit = float(os.environ.get("FILEORG_MIN_FREE_GIB", MIN_FREE_GIB))
free = local_free_gib()
if free < limit:
    print(f"file-org 디스크 가드: 로컬 여유 {free:.1f} GiB < 기준 {limit:g} GiB. 이 작업을 시작하지 않습니다. "
          "사용자에게 공간 확보(클라우드 캐시 비우기 등)를 요청한 뒤 다시 실행하세요.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
