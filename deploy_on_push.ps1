#Requires -Version 5.1
<#
    main 이 바뀌면 정적 사이트를 다시 올린다 — 푸시 연동 배포

    작업 스케줄러가 10분마다 부른다. origin/main 이 마지막으로 배포한 소스와 다르면
    작업 트리를 따라 올리고(fast-forward) sync_static.ps1 을 돌린다. 같으면 아무것도
    하지 않고 로그도 남기지 않는다.

    사용:
      .\deploy_on_push.ps1              한 번 본다
      .\deploy_on_push.ps1 -Quiet       스케줄러용. 화면에 찍지 않는다(로그는 남긴다)
      .\deploy_on_push.ps1 -Repo <경로>  다른 체크아웃을 본다(시험용)

    ## 왜 git hook 이 아니라 감시인가

    이 저장소의 main 은 **거의 전부 GitHub 에서 PR 머지로** 바뀐다. 로컬 hook
    (pre-push 등)은 그 '푸시' 를 보지 못한다 — 머지 버튼은 이 컴퓨터를 지나가지
    않는다. 그렇다고 GitHub Actions 로 옮길 수도 없다. 배포에는 실거래 DB
    (backend/data/apt.db, 저장소 밖)와 적합이 필요해서 이 컴퓨터에서만 돈다.
    그래서 **origin/main 이 바뀌었나** 를 이쪽에서 본다. 로컬에서 main 에 직접
    푸시한 것도 같은 길로 잡힌다.

    ## 작업 트리가 main 이 아니면 미룬다

    이 폴더는 여러 세션이 같이 쓴다. 누가 피처 브랜치에서 일하는 중이면 브랜치를
    바꾸지 않는다 — 남의 작업 트리를 건드리는 것은 배포보다 나쁘다. '미룸' 을
    로그에 남기고 다음 차례에 다시 본다. main 으로 돌아오면 그때 올라간다.
    더러운 트리도 같다(sync_static.ps1 의 배포 전제와 같은 이유).

    미룸은 **이유가 바뀔 때만** 적는다. 10분마다 같은 줄을 쓰면 하루 144줄이고,
    그러면 정작 실패가 로그에 묻힌다.

    ## 실패하면 한 시간 쉰다

    내보내기는 4분쯤 걸린다. 고장 난 채로 10분마다 다시 돌면 컴퓨터가 하루 종일
    내보내기만 한다. 같은 소스로 실패했으면 한 시간 동안 다시 시도하지 않는다.
    실패는 종료 코드 1 로 올라가 스케줄러의 마지막 결과에 보인다.

    ## 무엇을 성공으로 보나

    sync_static.ps1 은 배포를 건너뛸 때도 0 으로 끝난다(거짓 실패를 남기지 않으려고).
    그래서 종료 코드만으로는 '올렸다' 와 '건너뛰었다' 가 구분되지 않는다. 이번 실행이
    sync_static.log 에 덧붙인 줄에서 **"배포 완료 … (소스 <해시>)"** 를 찾는다.
    찾았을 때만 상태 파일을 고친다 — 못 찾았는데 고치면 그 커밋은 영영 안 올라간다.

    UTF-8 with BOM 으로 저장해야 한다 — setup.ps1 의 주석 참조.
#>
[CmdletBinding()]
param(
    [switch]$Quiet,
    [string]$Repo = ''
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

if (-not $Repo) { $Repo = Split-Path -Parent $MyInvocation.MyCommand.Definition }
$Sync      = Join-Path $Repo 'sync_static.ps1'
$SyncLog   = Join-Path $Repo 'sync_static.log'
$LogFile   = Join-Path $Repo 'deploy_on_push.log'
# 상태 파일은 **.git 안에** 둔다. 작업 트리에 두면 untracked 파일이 되어 트리가
# '더러워지고', 그러면 이 스크립트와 sync_static.ps1 이 둘 다 배포를 미룬다.
# 이 컴퓨터가 무엇을 올렸는지는 저장소 이력에 남길 일도 아니다.
$gitDir = (& git -C $Repo rev-parse --git-common-dir 2>$null)
if (-not $gitDir) { Write-Host "[X] git 저장소가 아닙니다: $Repo"; exit 1 }
if (-not [IO.Path]::IsPathRooted($gitDir)) { $gitDir = Join-Path $Repo $gitDir }
$StateFile = Join-Path $gitDir 'deploy_on_push.state'
$RetryAfter = New-TimeSpan -Hours 1

function Say ($t) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $t"
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    if (-not $Quiet) { Write-Host "  $t" }
}

function GitOut ([string[]]$argList) {
    # native 명령은 stderr 한 줄마다 ErrorRecord 를 만든다(sync_static.ps1 의 Run 주석).
    # 잠시 Continue 로 두고 종료 코드로만 판정한다.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = (& git -C $Repo @argList 2>&1 | Out-String)
        $script:GitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
    return $out.Trim()
}

function Load-State {
    $s = @{ deployed = ''; deferred = ''; failed = ''; failed_at = '' }
    if (Test-Path $StateFile) {
        try {
            $j = Get-Content $StateFile -Raw -Encoding utf8 | ConvertFrom-Json
            foreach ($k in @($s.Keys)) { if ($j.$k) { $s[$k] = [string]$j.$k } }
        } catch { Say "[!] 상태 파일을 읽지 못해 처음부터 봅니다: $_" }
    }
    return $s
}

function Save-State ($s) {
    ($s | ConvertTo-Json) | Set-Content -Path $StateFile -Encoding utf8
}

if (-not (Test-Path $Sync)) { Say "[X] sync_static.ps1 이 없습니다: $Sync"; exit 1 }

# ------------------------------------------------------------ 1) 무엇이 올라가 있어야 하나
$null = GitOut @('fetch', '-q', 'origin', 'main')
if ($GitCode -ne 0) { Say '[X] origin main 을 받아 오지 못했습니다 (네트워크?)'; exit 1 }
$target = GitOut @('rev-parse', 'origin/main')
$short  = GitOut @('rev-parse', '--short', 'origin/main')

$state = Load-State

# 처음 도는 것이면 지금 공개된 것의 소스를 gh-pages 커밋 메시지에서 읽는다
# ("스냅샷 … (소스 2243d1c)"). 안 읽으면 첫 차례에 이미 올라간 것을 또 올린다.
if (-not $state.deployed) {
    $null = GitOut @('fetch', '-q', 'origin', 'gh-pages')
    $subject = GitOut @('log', '-1', '--format=%s', 'origin/gh-pages')
    if ($subject -match '\(소스 ([0-9a-f]{7,40})\)') {
        $full = GitOut @('rev-parse', '--verify', '--quiet', "$($Matches[1])^{commit}")
        if ($GitCode -eq 0 -and $full) {
            $state.deployed = $full
            Save-State $state
            Say "상태 파일을 만들었습니다 — 지금 공개된 소스 $($Matches[1])"
        }
    }
}

if ($state.deployed -eq $target) { exit 0 }   # 할 일 없음. 로그도 남기지 않는다.

# ------------------------------------------------------------ 2) 올려도 되는 상태인가
$why = @()
$branchNow = GitOut @('rev-parse', '--abbrev-ref', 'HEAD')
if ($branchNow -ne 'main') { $why += "작업 트리가 '$branchNow' 입니다" }
if (GitOut @('status', '--porcelain')) { $why += '커밋되지 않은 변경이 있습니다' }
$ahead = GitOut @('rev-list', '--count', 'origin/main..HEAD')
if ($ahead -match '^[0-9]+$' -and [int]$ahead -gt 0) { $why += "origin/main 에 없는 커밋이 $ahead 개 있습니다" }

if ($why.Count) {
    $reason = "$short : " + ($why -join ' · ')
    if ($reason -ne $state.deferred) {
        Say "미룸 — 새 main($short)이 있지만 $($why -join ' · '). main 으로 돌아오면 올립니다."
        $state.deferred = $reason
        Save-State $state
    }
    exit 0
}

if ($state.failed -eq $target -and $state.failed_at) {
    $since = (Get-Date) - [datetime]::Parse($state.failed_at)
    if ($since -lt $RetryAfter) { exit 0 }   # 같은 소스로 방금 실패했다. 쉰다.
}

# ------------------------------------------------------------ 3) 따라가고 올린다
$out = GitOut @('merge', '--ff-only', '-q', 'origin/main')
if ($GitCode -ne 0) { Say "[X] main 을 fast-forward 하지 못했습니다: $out"; exit 1 }

Say "새 main $short — 배포를 시작합니다"
$before = if (Test-Path $SyncLog) { (Get-Item $SyncLog).Length } else { 0 }

& $Sync -Quiet
$code = $LASTEXITCODE

# 이번 실행이 덧붙인 부분만 읽는다. 로그는 UTF-8 이라 바이트로 잘라 디코딩한다.
$added = ''
if (Test-Path $SyncLog) {
    $bytes = [IO.File]::ReadAllBytes($SyncLog)
    if ($bytes.Length -gt $before) {
        $added = [Text.Encoding]::UTF8.GetString($bytes, [int]$before, $bytes.Length - [int]$before)
    }
}

if ($code -eq 0 -and $added -match "배포 완료 .*\(소스 $short\)") {
    $state.deployed = $target
    $state.deferred = ''
    $state.failed = ''
    $state.failed_at = ''
    Save-State $state
    Say "배포 완료 — 소스 $short"
    exit 0
}

if ($code -eq 0 -and $added -match '겹침') {
    # 일일 작업과 겹쳤다. 실패가 아니다 — 다음 차례에 다시 본다.
    Say "다른 동기화가 돌고 있어 다음 차례로 미룹니다 ($short)"
    exit 0
}

$state.failed = $target
$state.failed_at = (Get-Date).ToString('o')
Save-State $state
Say "[X] 배포하지 못했습니다 (sync_static exit $code, 소스 $short) — sync_static.log 를 보세요. 한 시간 뒤 다시 시도합니다."
exit 1

<#
    작업 스케줄러 등록 (10분마다, 현재 사용자 권한)

    PowerShell 에서 한 번만 실행하면 된다. 관리자 권한은 필요 없다.

      $p = 'E:\workspace\apt-price\deploy_on_push.ps1'
      $cmd = "if (Test-Path '$p') { & '$p' -Quiet; exit `$LASTEXITCODE }"
      $act = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"$cmd`""
      $trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 10)
      $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
      Register-ScheduledTask -TaskName 'apt-price 푸시 연동 배포' `
        -Action $act -Trigger $trg -Settings $set -Description 'origin/main 이 바뀌면 정적 사이트 배포'

    -File 이 아니라 Test-Path 로 감싸는 이유: 이 파일이 main 폴더에 없을 때(머지 전,
    다른 브랜치 체크아웃 중) -File 은 매번 실패를 남긴다. 스케줄러에 거짓 실패가
    쌓이면 진짜 실패와 구분할 수 없다(sync_static.ps1 의 Run 주석과 같은 이유).

    -MultipleInstances IgnoreNew: 배포가 10분을 넘겨도 다음 차례가 겹쳐 뜨지 않는다.
    일일 작업('apt-price 정적 사이트 동기화')과 겹치는 것은 sync_static.ps1 의
    뮤텍스가 막는다.

    일일 작업은 그대로 둔다. 실거래 적재처럼 **푸시 없이 데이터만 바뀌는** 경우는
    이것이 못 본다.

    로그는 deploy_on_push.log(.gitignore 의 *.log), 상태는 .git/deploy_on_push.state.
    해제: Unregister-ScheduledTask -TaskName 'apt-price 푸시 연동 배포'
#>
