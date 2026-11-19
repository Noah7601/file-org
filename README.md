# file-org — 무손실 파일 정리 스킬

흩어진 파일(로컬 · Google Drive · OneDrive · iCloud)을 한 곳의 마스터 폴더 체계로 **복구 → 분류 → 이관 → 정리**하는 방법론과 스크립트 모음입니다. Claude Code / Codex 같은 에이전트가 읽고 따르는 스킬(SKILL.md) 형태이며, 스크립트는 사람이 직접 써도 됩니다.

핵심 원칙 하나: **사용자가 돌이킬 수 없는 일은 하지 않는다.** 삭제 없음(이동·복사·격리만), 덮어쓰기 없음, 모든 쓰기는 dry-run → 사용자 승인 → 적용 → 독립 검증 → 로그.

실제 2개월짜리 정리 프로젝트(저장소 4곳, 2만여 파일)에서 나온 절차이고, macOS와 Windows 11에서 검증했습니다.

설명서·사용 방법(한 페이지, 평이한 말로): [`docs/README.html`](docs/README.html) — 받아서 브라우저로 열면 된다.

## 구성

```
SKILL.md                 절차 전체(원칙 8가지, 작업 흐름, 보고 형식)
references/cloud-fs.md   Google Drive · OneDrive · iCloud의 함정과 대처 (macOS · Windows)
references/classify.md   분류: 근거 추출 → 신뢰도 → 배치 승인 → 적용
references/log-format.md 로그(moves_v2.csv) 스키마와 검증 루틴
references/docsets.md    정리가 끝난 뒤: 거래 폴더 · 필수 서류 체크기 · 제출 zip · 관제탑
references/ontology.md   그 다음: 관계를 그래프로 다루는 최소 온톨로지
scripts/                 inventory · find_dupes · apply_moves · copy_tree · evict_icloud(macOS)
                         check_docsets · extract_zip_only · control_tower(관제탑)
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

임시 폴더에 시험 트리를 만들어 스크립트 네 개를 dry-run → apply로 돌리고 39개 항목(NFD 이름, 동명 충돌, 격리, 덮어쓰기 없음, 재개, 체크기, zip 보관, 관제탑 보안)을 검사합니다. `--cloud-dir <OneDrive·iCloud 폴더>`를 주면 실제 동기화 폴더의 클라우드 전용 판정도 읽기 전용(lstat)으로 확인합니다.

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

정리가 끝난 뒤 증빙 점검과 관제탑:

```bash
python3 scripts/check_docsets.py --root <증빙 폴더> --rules references/docset_rules.example.json --out <보고서 폴더>
python3 scripts/extract_zip_only.py --root <증빙 폴더> --log <moves_v2.csv>        # 제출 zip 안에만 있는 서류(dry-run)
python3 scripts/control_tower.py --root <마스터> --checks <보고서 폴더>           # http://localhost:8765
```

관제탑은 이 컴퓨터에서만 열리는 보기 전용 화면입니다. 폴더 지도(용량 비례), 사업별 완결·누락, 채워야 할 서류, 최근 기록을 보여 주고, 새로고침 버튼은 폴더를 이름·크기로만 다시 셉니다(본문을 읽지 않아 클라우드 파일을 내려받지 않음). 자세한 절차는 `references/docsets.md`.

## 안전하게 쓰기

스크립트에는 삭제 호출이 없습니다(자기 임시 파일 `.part` 정리뿐). 이동은 같은 볼륨 안 rename이고 목적지에 파일이 있으면 건너뜁니다. 복사는 `.part`에 쓴 뒤 이름을 바꾸므로 잘린 파일이 남지 않고, 목적지의 다른 파일은 덮어쓰지 않고 충돌로 보고합니다. 모든 쓰기는 `moves_v2.csv`에 남습니다.

남는 위험은 에이전트가 스크립트 밖에서 `rm`·`rsync --delete`·`mv`를 직접 치는 경우입니다. 스킬 문서는 금지하지만 강제하지는 못하므로, 프로그램 쪽에서 두 겹으로 막아 두기를 권합니다.

**1겹 — 삭제·이동 명령 거부.** 정리 작업을 하는 폴더의 `.claude/settings.json`(또는 `~/.claude/settings.json`)에 넣습니다. 이 명령들은 에이전트가 실행하려 해도 거부됩니다. 스크립트(`python3 …`)는 그대로 돌아갑니다.

```json
{
  "permissions": {
    "deny": [
      "Bash(rm:*)", "Bash(rmdir:*)", "Bash(rsync:*)", "Bash(mv:*)", "Bash(unlink:*)",
      "Bash(find * -delete:*)", "Bash(del:*)", "Bash(robocopy:*)", "Bash(Remove-Item:*)"
    ]
  }
}
```

**2겹 — 쓰기 범위 제한.** Claude Code의 샌드박스(설정의 `sandbox` 항목, 또는 `/sandbox` 명령)를 켜면 셸 명령이 작업 폴더 밖에 쓰지 못합니다. 작업 폴더를 산출물 폴더로 열면, 마스터·원본 폴더에는 승인된 스크립트만 접근하게 됩니다. 설정 방법은 Claude Code 문서의 sandbox 항목을 따릅니다.

이렇게 두면 삭제가 필요한 단계(격리 폴더 비우기, 스텁 제거)는 자연히 에이전트가 목록을 보고하고 사용자가 Finder·탐색기·웹에서 직접 하게 됩니다. 정리가 끝나면 거부 목록을 지워도 됩니다.

## 알려진 한계

- Google Drive for desktop(Windows)은 클라우드 전용 파일을 속성으로 구분할 수 없어 "읽으면 내려받는다"로 가정합니다.
- 마스터를 OneDrive·iCloud로 둘 때의 업로드 확인 요령은 아직 Drive만큼 자세하지 않습니다.
- iCloud for Windows는 미검증입니다.

## 라이선스

MIT — `LICENSE` 참고.
