# 클라우드 동기화 폴더의 함정과 대처

세 서비스는 "폴더처럼 보이지만 폴더가 아니다." 아래는 실제로 겪은 실패와 그때 통한 방법이다. 새 환경에서는 먼저 각 항목을 1~2개 파일로 확인하고 전체에 적용한다. macOS에서 겪은 것이 바탕이고, 각 절의 **Windows** 항목 중 "검증됨"이라 적은 것은 Windows 11 + Python 3.12에서 실제로 확인한 것이고, 나머지는 같은 원리를 파일 온디맨드(Files On-Demand) 동작에 맞춘 추정이라 더더욱 1~2개 파일로 먼저 확인한다.

## 공통

- **이름 정규화**: 비교·조회는 전부 `unicodedata.normalize("NFC", …)` 후. 디렉터리 안에서 파일을 찾을 때는 `os.listdir` 결과를 NFC로 바꿔 대조한다(`fileorg_lib.resolve_nfc`).
- **읽기 = 다운로드**: 클라우드 전용 파일은 열면 전체를 받는다. 해시·본문 추출은 대상만, 배치마다 디스크 여유를 재고, 가드(8 GiB)를 둔다.
- **크기 먼저**: 중복 판정은 (이름, 크기) → 같은 크기끼리만 sha1. 0바이트는 내용 비교 대상에서 제외한다.
- **mtime 보존**: 복사 후 `os.utime`. 권한 비트는 `shutil.copyfileobj`가 보존하지 않으므로 `os.chmod(dst, st.st_mode & 0o7777)`를 따로 한다(실행 파일이 0644가 되어 git이 모드 변경으로 잡은 사례).
- **복사는 `.part`에 쓰고 성공했을 때만 제 이름으로 바꾼다**(`fileorg_lib.copy_with_retry`): 네트워크가 끊겨도 잘린 파일이 목적지 이름으로 남지 않는다. 목적지에 같은 이름·다른 내용이 있으면 덮어쓰지 않고 "충돌"로 보고한다(`copy_tree`의 오류 목록 CSV).
- **업로드 확인**: 복사 직후 로컬에 생겼다고 서버에 반영된 것이 아니다. 서비스별 표식을 확인하고 배치마다 최대 10분 기다린다.

## Google Drive (Drive for desktop, 스트리밍)

- **0바이트 파일은 이름을 바꾸거나 옮기지 않는다.** rename이 비결정적으로 정착하지 않았다(131초 후에도 미반영). 스텁은 목록으로만 추적하고, 복구본을 원래 위치에 **복사**한다. 스텁 제거는 맨 마지막에 Finder/웹에서.
- **자동 개명**: 확장자 없는 PDF 등에 `.pdf`를 붙이고, 가끔 이름을 바꾼다. 복사 후 "목적지 없음"이 나오면 같은 폴더에서 stem 일치로 찾아 정정(`--reconcile`)한다.
- **업로드 확인**: `xattr -l <file>`에 `com.google.drivefs.item-id#S`(접두 일치)가 생기면 서버 반영. macOS Python에는 `os.getxattr`가 없으니 `xattr` 명령을 쓴다.
- **로컬 캐시가 디스크를 먹는다**: 복사본은 캐시에 남는다(16 GiB까지 쌓인 사례). 축출 API가 없으므로 디스크 가드로 막고, 걸리면 Finder "다운로드 제거" 후 재개.
- **삭제는 휴지통으로**: 로컬에서 지우면 Drive 휴지통(30일). Finder `delete`는 수백 건도 수십 초에 끝난다(40건 배치, `with timeout`). 마운트 안 `.Trash`가 Finder 휴지통에 합산 표시되니, "휴지통 비우기"가 Drive 휴지통까지 비운다는 것을 사용자에게 알린다.
- **마운트 경로(macOS)**: `~/Library/CloudStorage/GoogleDrive-<계정>/내 드라이브/…`. "다른 컴퓨터/" 아래에 PC 백업이 따로 있다.

### Windows (Drive for desktop)

- 스트리밍 모드면 드라이브 문자(기본 `G:\내 드라이브\…`)로 붙는다. 미러 모드면 보통 폴더이고 전부 로컬에 있다(디스크 가드 불필요, 대신 동기화 충돌 사본 `이름 (1)`이 생긴다).
- 클라우드 전용 여부가 파일 속성으로 **잡히지 않는다**(검증됨: 스트리밍 모드 폴더의 400개 파일 전부 속성 `0x80` 보통 파일, `is_dataless` 0). 탐색기의 상태 아이콘(구름/체크)으로만 알 수 있고, 스크립트는 "읽으면 내려받는다"는 전제로 짠다(`copy_tree.py`는 그 전제다). `inventory.py`의 "클라우드 전용" 수치는 Drive에서는 항상 0이니 믿지 않는다. `shutil.disk_usage('G:')`는 로컬 디스크 여유를 돌려주므로 디스크 가드는 그대로 동작한다.
- 로컬 캐시는 `%LOCALAPPDATA%\Google\DriveFS\`에 쌓인다. 비우려면 파일·폴더 우클릭 → "오프라인 액세스" → "온라인 전용". CLI가 없으니 디스크 가드로 막고, 걸리면 사용자에게 이 동작을 요청한 뒤 재개한다.
- `G:`에서 지우면 Windows 휴지통이 아니라 **Drive 휴지통**(30일)으로 간다. 복구 경로를 로그 사유에 적는다.
- 업로드 확인: xattr가 없다. 트레이 아이콘의 "동기화 완료" 또는 Drive 웹에서 표본을 확인하고, 자동 확인 수단이 없으면 배치마다 10분을 기다린다.
- 0바이트 스텁을 옮기지 않는다는 규칙은 같다.

## OneDrive

- **Errno 60 (Operation timed out)**: 클라우드 전용 파일을 열 때. 0/30/60/120초 간격 재시도(`fileorg_lib.copy_with_retry`).
- 0바이트 "원본"도 많다(841건). 소스로 쓸 때 크기 > 0만 후보.
- 마운트 경로(macOS) `~/Library/CloudStorage/OneDrive-개인/`. Finder로 지운 항목은 마운트 안 `.Trash`로 간다.

### Windows (OneDrive, Files On-Demand)

- 폴더는 `%USERPROFILE%\OneDrive\`(개인) 또는 `OneDrive - <조직명>\`. **바탕 화면·문서·사진이 OneDrive로 옮겨져 있을 수 있다**(알려진 폴더 이동). 그러면 macOS의 iCloud `Documents`와 같은 함정이라 개발 프로젝트·스크립트를 거기 두지 않는다.
- 클라우드 전용 판정: `attrib <file>`에 `O`(오프라인)·`U`(온라인 전용)가 보이면 로컬에 내용이 없다. Python은 `os.lstat(p).st_file_attributes & 0x400000`(`fileorg_lib.is_dataless`가 이미 본다. 검증됨: 실제 OneDrive 최상위 56개 중 40개가 클라우드 전용, 속성 플래그와 `is_dataless` 판정 일치). 읽으면 내려받고, 네트워크가 끊기면 타임아웃이 난다(재시도 0/15/30/60/120초 그대로).
- **로컬 사본 비우기**: `attrib +U -P "<file>"`, 폴더 전체는 `attrib +U -P /S /D "<folder>\*"`. 항상 보관은 `attrib +P -U`. 클라우드 원본은 그대로다(macOS의 `evict_icloud`에 해당).
- 저장소 센스(Storage Sense)가 "n일 안 연 파일을 온라인 전용으로" 자동 전환한다. iCloud의 '저장 공간 최적화'와 같은 이유로 **사전 하이드레이션은 무효**, 파일 단위로 읽은 즉시 쓴다.
- 지우면 Windows 휴지통 + OneDrive 온라인 휴지통(30일) 둘 다에 남는다. 1개 파일로 어느 쪽에 가는지 확인하고 로그에 적는다.

## iCloud Drive (Desktop & Documents 동기화 포함)

- **"Mac 저장 공간 최적화"가 켜져 있으면 파일은 dataless**: `os.lstat(p).st_flags & 0x40000000`, `ls -lO`에 `dataless`. 읽으면 전체를 받고, **몇 시간 안에 OS가 다시 비운다.** 그래서:
  - **사전 하이드레이션은 무효.** 26,588건을 11시간 받아 둔 뒤 rsync를 돌리니 전부 다시 비워져 `mmap: Operation timed out`(rc 20)으로 첫 파일에서 중단됐다.
  - **파일 단위로 읽은 즉시 쓰기**(`copy_tree.py`): 재시도 0/15/30/60/120초, 크기 검증, 재개 가능. 처리량은 순간 9/s, 지속 0.7~6/s로 병렬 수에 거의 무관하다. 시간이 걸리는 것을 미리 말한다.
  - rsync는 dataless 파일에서 죽는다. 쓰지 않는다.
- **로컬 사본 축출**: `FileManager.evictUbiquitousItem` (`scripts/evict_icloud.swift`, `evict_icloud <path>…` → `evicted N failed M`). 클라우드 원본은 그대로. `.git/config`·Xcode 번들 안 소형 파일은 항상 로컬에 남는다(실패로 찍혀도 무시).
- **Finder 휴지통은 iCloud 밖이다**: 클라우드 전용 항목을 휴지통에 넣으려면 전부 다운로드해야 해서 `-8013 해당 항목을 다운로드해야 하기 때문에`로 거부된다. 대안은 (a) 로컬 `rm`(unlink는 즉시, 클라우드에서도 삭제되어 iCloud.com '최근 삭제된 항목'에 30일 보관) (b) iCloud.com에서 삭제. 어느 쪽이든 **사용자가 복구 경로를 알고 고르게** 한다.
- iCloud가 만든 동일 사본(`이름 2.pdf`)이 갑자기 생길 수 있다. 삭제 직전 재검증에서 걸러진다.
- `~/Documents`·`~/Desktop`이 동기화 대상이면 개발 프로젝트는 거기 두지 않는다(`node_modules` 8만 파일이 올라간다).

### Windows (iCloud for Windows)

- 폴더는 `%USERPROFILE%\iCloudDrive\`(구버전은 `iCloud Drive`). iCloud for Windows 12 이상 + Windows 10 1709 이상이면 파일 온디맨드라 OneDrive와 같은 속성(`O`·`U`)으로 클라우드 전용을 알 수 있고, `fileorg_lib.is_dataless`가 같은 방법으로 본다.
- 로컬 사본 비우기는 우클릭 → "공간 확보"(Free up space). `attrib +U -P`가 통하는지는 파일 1개로 먼저 확인한다(같은 Cloud Files API를 쓰지만 보장은 없다).
- 지운 파일이 Windows 휴지통과 iCloud.com '최근 삭제된 항목'(30일) 중 어디에 남는지 1개로 확인한 뒤 로그에 적는다.
- macOS에서 만든 한글 이름은 NFD로 들어올 수 있다. NFC 비교 규칙은 그대로 적용한다.

## 디스크 여유가 줄어드는 다른 원인

작업과 무관하게 줄 때가 있다: APFS 로컬 스냅샷(`tmutil listlocalsnapshots /`), macOS 업데이트 준비(`com.apple.os.update-MSUPrepareUpdate`). 내가 지운 것이 클라우드 전용이면 로컬 공간은 애초에 안 돌아온다. 원인을 확인하고 사용자에게 말한다.

## 로컬 쪽 주의 (macOS)

- `~/.Trash`는 셸에서 못 읽는다(TCC). 휴지통 내용은 Finder AppleScript로 본다(`name of every item of trash`).
- 큰 항목의 Finder `delete`는 AppleEvent 기본 2분 타임아웃을 넘긴다. `with timeout of 3000 seconds`로 감싸고, 백그라운드로 돌린 뒤 로그 파일을 기다린다.
- AppleScript 안에서 `delete POSIX file p`는 핸들러 안에서 실패한다(-1728). `set f to POSIX file p as alias` 후 `delete f`.

## 로컬 쪽 주의 (Windows)

- **Python 실행**: `py -3 scripts\inventory.py <root>`. Microsoft Store 스텁 `python`이 잡힐 수 있으니 `py` 런처를 쓴다(스텁은 호출하면 Store를 열고 멈춘다). Python이 없는 PC면 python.org의 임베디드 zip(≈11 MB, 설치·레지스트리·PATH 변경 없음)을 작업 폴더에 풀어 쓰고, 받은 뒤 `certutil -hashfile <zip> MD5`로 게시된 해시와 대조한다. 한글 출력은 `fileorg_lib`가 콘솔을 UTF-8로 바꾼다(안 되면 `set PYTHONUTF8=1` 또는 `chcp 65001`). 검증됨: 번들 스크립트 4종(`inventory`·`find_dupes`·`apply_moves --dedupe --mkdir`·`copy_tree`)이 Windows 11 + Python 3.12에서 macOS와 같은 결과 — NFD 이름, `/`·`\` 혼용 경로, 격리, ` (2)` 접미, 로그, 재개 모두 통과.
- **경로 길이 260자**: 깊은 한글 경로는 넘기기 쉽다(검증됨: `LongPathsEnabled=0`에서 384자 경로 생성은 `WinError 206 파일 이름이나 확장명이 너무 깁니다`로 실패, `\\?\` 접두를 붙이면 성공). 그룹 정책/레지스트리 `LongPathsEnabled=1`을 켜거나, 넘는 파일만 목록으로 내서 사용자에게 보고한다. `\\?\` 접두는 최후 수단.
- **금지 문자** `\ / : * ? " < > |`와 끝의 점·공백: macOS에서 만든 이름이 Windows로 동기화되면 클라이언트가 이름을 바꾸거나 동기화를 거부한다. 이름 대조에서 이런 건은 "교정 대상"이 아니라 "동기화 불가 목록"으로 따로 낸다.
- **대소문자**: 로컬은 무시하지만 Drive 서버는 구별한다. 서버에 `a.pdf`와 `a.PDF`가 같이 있으면 로컬에 하나만 보이거나 ` (1)`이 붙는다.
- **휴지통으로 보내기**(복구 가능): 표준 라이브러리에 없다. PowerShell로:
  ```powershell
  Add-Type -AssemblyName Microsoft.VisualBasic
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("C:\path\file.pdf", 'OnlyErrorDialogs', 'SendToRecycleBin')
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory("C:\path\folder", 'OnlyErrorDialogs', 'SendToRecycleBin')
  ```
  검증됨: 위 한 줄로 파일이 휴지통에 들어가고 `Shell.Application`의 `NameSpace(10)`에서 보인다. `del`·`Remove-Item`은 휴지통을 거치지 않으므로 쓰지 않는다.
- **심볼릭 링크**: 만들려면 개발자 모드나 관리자 권한이 필요하다. `copy_tree.py`는 실패를 오류 목록에 남기므로 그대로 보고한다.
- **디스크 여유**: `shutil.disk_usage`(`fileorg_lib.free_gib`). 저장소 센스가 임시 파일을 지우며 수치가 오르내릴 수 있다.
