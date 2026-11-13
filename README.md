# file-org — 무손실 파일 정리 스킬

흩어진 파일(로컬 · Google Drive · OneDrive · iCloud)을 한 곳의 마스터 폴더 체계로 **복구 → 분류 → 이관 → 정리**하는 방법론과 스크립트 모음입니다. Claude Code / Codex 같은 에이전트가 읽고 따르는 스킬(SKILL.md) 형태이며, 스크립트는 사람이 직접 써도 됩니다.

핵심 원칙 하나: **사용자가 돌이킬 수 없는 일은 하지 않는다.** 삭제 없음(이동·복사·격리만), 덮어쓰기 없음, 모든 쓰기는 dry-run → 사용자 승인 → 적용 → 독립 검증 → 로그.

실제 2개월짜리 정리 프로젝트(저장소 4곳, 2만여 파일)에서 나온 절차이고, macOS와 Windows 11에서 검증했습니다.

## 구성

```
SKILL.md                 절차 전체(원칙 8가지, 작업 흐름, 보고 형식)
references/cloud-fs.md   Google Drive · OneDrive · iCloud의 함정과 대처 (macOS · Windows)
references/classify.md   분류: 근거 추출 → 신뢰도 → 배치 승인 → 적용
references/log-format.md 로그(moves_v2.csv) 스키마와 검증 루틴
references/ontology.md   정리가 끝난 뒤: 문서 세트 검증 규칙으로 쓰는 최소 온톨로지
scripts/                 inventory · find_dupes · apply_moves · copy_tree · evict_icloud(macOS)
tests/smoke_test.py      새 환경에서 먼저 돌리는 자체 검사
```

## 설치

Claude Code:

```bash
git clone https://github.com/Noah7601/file-org ~/.claude/skills/file-org
```

Codex는 `~/.codex/skills/file-org`에 같은 내용을 둡니다. 스크립트는 Python 3.8+ 표준 라이브러리만 씁니다(Windows는 `py -3`). iCloud 로컬 사본 축출 도구만 macOS 전용이며 `swiftc -O scripts/evict_icloud.swift -o scripts/evict_icloud`로 빌드합니다.

## 먼저 할 것

```bash
python3 tests/smoke_test.py
```

임시 폴더에 시험 트리를 만들어 스크립트 네 개를 dry-run → apply로 돌리고 20여 개 항목(NFD 이름, 동명 충돌, 격리, 덮어쓰기 없음, 재개)을 검사합니다. `--cloud-dir <OneDrive·iCloud 폴더>`를 주면 실제 동기화 폴더의 클라우드 전용 판정도 읽기 전용(lstat)으로 확인합니다.

## 사용

에이전트에게 "파일 정리해줘", "Drive·OneDrive·iCloud 합쳐줘", "중복 파일 찾아줘"처럼 말하면 스킬이 켜지고, 처음에 세 가지를 묻습니다: 마스터를 어디로 할지, 삭제를 허용할지(기본 불허), 분류를 누가 확정할지(기본: 에이전트 제안, 사용자 승인). 나머지는 측정으로 정합니다. 마스터는 로컬 · Google Drive · OneDrive · iCloud 어디든 됩니다(Google Drive가 가장 자세히 검증됨).

스크립트만 쓰려면:

```bash
python3 scripts/inventory.py <폴더>                                   # 측정(읽기 전용)
python3 scripts/find_dupes.py <폴더> [--quarantine DIR --log LOG --apply]
python3 scripts/apply_moves.py --root R --proposals CSV --log LOG [--apply --dedupe --quarantine DIR --mkdir]
python3 scripts/copy_tree.py SRC DST [--exclude node_modules .venv]
```

전부 dry-run이 기본이고, `--apply`를 붙여야 실제로 씁니다.

## 안전하게 쓰기

스크립트에는 삭제 호출이 없습니다(자기 임시 파일 `.part` 정리뿐). 이동은 같은 볼륨 안 rename이고 목적지에 파일이 있으면 건너뜁니다. 복사는 `.part`에 쓴 뒤 이름을 바꾸므로 잘린 파일이 남지 않고, 목적지의 다른 파일은 덮어쓰지 않고 충돌로 보고합니다. 모든 쓰기는 `moves_v2.csv`에 남습니다.

남는 위험은 에이전트가 스크립트 밖에서 `rm`·`rsync --delete`·`mv`를 직접 치는 경우입니다. 스킬 문서가 금지하지만 강제는 아니므로, Claude Code라면 `settings.json`의 거부 목록으로 막아 두는 것을 권합니다.

```json
{ "permissions": { "deny": ["Bash(rm:*)", "Bash(rsync:*)", "Bash(mv:*)", "Bash(del:*)", "Bash(robocopy:*)", "Bash(Remove-Item:*)"] } }
```

삭제가 필요한 단계(격리 폴더 비우기, 스텁 제거)는 에이전트가 목록을 보고하고 사용자가 Finder·탐색기·웹에서 직접 합니다.

## 알려진 한계

- Google Drive for desktop(Windows)은 클라우드 전용 파일을 속성으로 구분할 수 없어 "읽으면 내려받는다"로 가정합니다.
- 마스터를 OneDrive·iCloud로 둘 때의 업로드 확인 요령은 아직 Drive만큼 자세하지 않습니다.
- iCloud for Windows는 미검증입니다.

## 라이선스

MIT — `LICENSE` 참고.
