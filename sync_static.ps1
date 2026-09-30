#Requires -Version 5.1
<#
    정적 사이트 동기화 — 내보내기 → 빌드 → 배포

    로컬은 동적으로 돈다(데이터 적재·모델 적합·매물 붙여넣기). 이 스크립트는 그
    결과를 **읽기 전용 스냅샷**으로 떠서 정적 사이트로 올린다.

    작업 스케줄러가 하루 한 번 부르는 것을 전제로 썼다. 등록 명령은 맨 아래 주석에
    있고, docs/deploy.md 에도 적어 두었다.

    사용:
      .\sync_static.ps1                 내보내기 + 빌드 + 배포
      .\sync_static.ps1 -NoPublish      배포 없이 로컬 확인용 빌드까지만
      .\sync_static.ps1 -NoQuotes       호가(매물 순위·단지 상세)를 뺀다
      .\sync_static.ps1 -Quiet          스케줄러용. 요약만 남긴다

    UTF-8 with BOM 으로 저장해야 한다 — setup.ps1 의 주석 참조.
#>
[CmdletBinding()]
param(
    [switch]$NoPublish,
    [switch]$NoQuotes,
    [switch]$Quiet,
    [string]$Branch = 'gh-pages'
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Dist     = Join-Path $Frontend 'dist'
$VPy      = Join-Path $Backend '.venv\Scripts\python.exe'
$LogFile  = Join-Path $Root 'sync_static.log'

function Say ($t) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $t"
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    if (-not $Quiet) { Write-Host "  $t" }
}
function Die ($t) {
    Say "[X] $t"
    exit 1
}

<#
    외부 명령 실행 — 성공을 실패로 보고하지 않기 위해 필요하다.

    PowerShell 5.1 은 native 명령의 stderr 한 줄마다 ErrorRecord(NativeCommandError)
    를 만든다. 이 스크립트는 $ErrorActionPreference = 'Stop' 이므로, git 이 진행
    상황을 stderr 에 적는 순간 거기서 던진다.

    실제로 그랬다. gh-pages 푸시는 성공했는데 git 이 "remote:" 를 stderr 에 쓰는
    바람에 스크립트가 실패로 끝났다. 스케줄러가 매일 거짓 실패를 남기게 되고, 그러면
    **진짜 실패도 같은 모양이라 구분할 수 없다.** 종료 코드로만 판정한다.
#>
function Run ($exe, [string[]]$argList) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $exe @argList 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    foreach ($l in ($out -split "`r?`n")) {
        if ($l.Trim()) { Say "  $l" }
    }
    return $code
}

Say '=== 동기화 시작 ==='

if (-not (Test-Path $VPy)) { Die "가상환경이 없습니다: $Backend\.venv — setup.bat 을 먼저 실행하세요." }
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) { Die '프론트엔드 의존성이 없습니다 — setup.bat 을 먼저 실행하세요.' }

# ------------------------------------------------------------ 1) 내보내기
<#
    적합이 없으면 여기서 계산한다(기간당 수십 초). 스냅샷 8MB 에 50초쯤 걸린다.
    실패하면 종료 코드로 알려 주므로 그냥 넘기지 않는다 — 스냅샷이 반쪽이면
    화면에는 아무 표시 없이 옛 값이 남는다.
#>
Say '내보내기...'
$exportArgs = @('-m', 'scripts.export_static', '--quiet')
if ($NoQuotes) { $exportArgs += '--no-quotes' }

Push-Location $Backend
try {
    $code = Run $VPy $exportArgs
    if ($code -ne 0) { Die "내보내기 실패 (exit $code)" }
} finally {
    Pop-Location
}

$snapDir = Join-Path $Frontend 'public\snapshot'
$metaPath = Join-Path $snapDir 'meta.json'
if (-not (Test-Path $metaPath)) { Die "meta.json 이 없습니다: $metaPath" }
$meta = Get-Content $metaPath -Raw -Encoding utf8 | ConvertFrom-Json
Say ("스냅샷 {0}개 파일 · {1:N1}MB · 실거래 {2:N0}건 · 최신 거래 {3}" -f `
    $meta.files, ($meta.bytes / 1MB), $meta.data.trades, $meta.data.latest_deal_date)

# ------------------------------------------------------------ 2) 빌드
Say '빌드...'
Push-Location $Frontend
try {
    # npm 은 .cmd 래퍼라 & 로 직접 부르면 인수 처리가 셸마다 다르다. cmd 로 감싼다.
    $code = Run 'cmd.exe' @('/c', 'npm', 'run', 'build:static')
    if ($code -ne 0) { Die "빌드 실패 (exit $code)" }
} finally {
    Pop-Location
}
if (-not (Test-Path (Join-Path $Dist 'index.html'))) { Die "빌드 결과가 없습니다: $Dist" }
$distJson = @(Get-ChildItem (Join-Path $Dist 'snapshot') -Recurse -Filter *.json -ErrorAction SilentlyContinue).Count
if ($distJson -lt 1) { Die 'dist 에 스냅샷이 복사되지 않았습니다.' }
# ${} 로 감싸는 이유: PowerShell 은 한글도 변수명 문자로 보므로 "$distJson개" 는
# `distJson개` 라는 없는 변수가 된다. 값이 조용히 빈 문자열로 나온다.
Say "빌드 완료 · dist 안 스냅샷 ${distJson}개"

if ($NoPublish) {
    Say '배포 생략(-NoPublish). 확인: cd frontend; npm run preview:static'
    Say '=== 완료 ==='
    exit 0
}

# ------------------------------------------------------------ 3) 배포
<#
    왜 dist 안에서 git 을 새로 만들어 강제 푸시하나

    스냅샷은 8MB 이고 내보낼 때마다 거의 전부 달라진다(적정가가 실거래로 다시
    계산되므로). 그걸 gh-pages 브랜치에 차곡차곡 쌓으면 이력이 **하루 8MB 씩**
    불어난다. 한 달이면 240MB 다.

    그래서 매번 dist 에 빈 저장소를 만들어 커밋 하나만 두고 force push 한다.
    브랜치에는 항상 커밋이 하나뿐이라 이력이 늘지 않는다. 정적 사이트에 이력이
    필요한 경우는 없다 — 필요한 이력은 소스 저장소에 있다.

    .nojekyll: 없으면 GitHub Pages 가 Jekyll 로 처리하면서 `_` 로 시작하는
    파일·디렉터리를 조용히 빼 버린다. 지금 구조에는 없지만, 나중에 생겼을 때
    "파일이 왜 404 지" 로 시간을 버리지 않도록 미리 둔다.
#>
$remote = (git -C $Root remote get-url origin 2>$null)
if (-not $remote) { Die 'origin 리모트가 없습니다.' }

$head = (git -C $Root rev-parse --short HEAD 2>$null)
$msg = "스냅샷 $($meta.generated_at) (소스 $head)"

Say "배포 -> $Branch (강제 푸시, 커밋 1개)"
Push-Location $Dist
try {
    if (Test-Path '.git') { Remove-Item -Recurse -Force '.git' }
    New-Item -ItemType File -Path '.nojekyll' -Force | Out-Null

    $code = Run 'git' @('init', '-q')
    if ($code -ne 0) { Die "git init 실패 (exit $code)" }

    $code = Run 'git' @('checkout', '-q', '-b', $Branch)
    if ($code -ne 0) { Die "브랜치 생성 실패 (exit $code)" }

    $code = Run 'git' @('add', '-A')
    if ($code -ne 0) { Die "git add 실패 (exit $code)" }

    # 커밋 저자는 이 저장소 설정을 그대로 쓴다. 없으면 커밋이 실패하므로 확인한다.
    $code = Run 'git' @('commit', '-q', '-m', $msg)
    if ($code -ne 0) { Die "커밋 실패 (exit $code) — git user.name/user.email 을 확인하세요." }

    $code = Run 'git' @('push', '--force', $remote, "$($Branch):$($Branch)")
    if ($code -ne 0) { Die "푸시 실패 (exit $code)" }
} finally {
    Pop-Location
}

Say "배포 완료 · $msg"
Say '=== 완료 ==='
exit 0

<#
    작업 스케줄러 등록 (매일 06:30, 현재 사용자 권한)

    PowerShell 에서 한 번만 실행하면 된다. 관리자 권한은 필요 없다.

      $act = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument '-NoProfile -ExecutionPolicy Bypass -File "E:\workspace\apt-price\sync_static.ps1" -Quiet'
      $trg = New-ScheduledTaskTrigger -Daily -At 06:30
      $set = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
      Register-ScheduledTask -TaskName 'apt-price 정적 사이트 동기화' `
        -Action $act -Trigger $trg -Settings $set -Description '스냅샷 내보내기 + 빌드 + gh-pages 배포'

    -StartWhenAvailable: 그 시각에 컴퓨터가 꺼져 있었으면 켜진 뒤에 돌린다.
    실거래가는 하루 단위로 갱신되므로 이보다 자주 돌릴 이유가 없다.

    로그는 sync_static.log 에 쌓인다(.gitignore 의 *.log 에 걸린다).
    해제: Unregister-ScheduledTask -TaskName 'apt-price 정적 사이트 동기화'
#>
