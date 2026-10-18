#Requires -Version 5.1
<#
    해마다 한 번 뜨는 전수 스냅샷 — 멸실을 직접 관측하기 위한 것

    멸실은 **시군구로 공표되지 않는다.** R-ONE·KOSIS·통계누리 셋 다 시도 단위다.
    그래서 전수를 해마다 떠서 사라진 것을 센다 — 지난번에 있었는데 이번에 없으면
    그 사이 멸실된 것이다(멸실의 법적 정의가 '건축물대장 말소').

      scripts.ingest_kapt_all   의무관리대상 아파트 1,945곳     25분
      scripts.ingest_bldrgst    건축물대장 전수 323,915동       50분

    **이것만은 놓치면 복구할 수 없다.** 다른 적재는 늦게 돌려도 과거 값이 그대로
    오지만, 스냅샷은 '그때 무엇이 있었나' 라서 지나가면 그해는 영영 빈칸이 된다.
    그래서 작업 스케줄러에 올려 둔다.

    사용:
      .\snapshot_yearly.ps1            둘 다
      .\snapshot_yearly.ps1 -Only kapt 하나만
      .\snapshot_yearly.ps1 -Quiet     스케줄러용

    등록 명령은 맨 아래 주석에 있다(왜 해마다 뜨는지는 docs/data/south-supply.md).
    UTF-8 with BOM 으로 저장해야 한다 — sync_static.ps1 과 같은 이유.
#>
[CmdletBinding()]
param(
    [ValidateSet('kapt', 'bld', 'both')]
    [string]$Only = 'both',
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Root    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Backend = Join-Path $Root 'backend'
$VPy     = Join-Path $Backend '.venv\Scripts\python.exe'
$LogFile = Join-Path $Root 'snapshot_yearly.log'

function Say ($t) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $t"
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    if (-not $Quiet) { Write-Host "  $t" }
}

<#
    외부 명령 실행. native 명령의 stderr 한 줄마다 ErrorRecord 가 만들어지므로
    $ErrorActionPreference = 'Stop' 아래에서는 진행 메시지만으로도 죽는다.
    **종료 코드로만 판정한다** — sync_static.ps1 의 Run 과 같은 이유다.
#>
function Run ([string[]]$argList) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $VPy @argList 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    foreach ($l in ($out -split "`r?`n")) {
        if ($l.Trim()) { Say "  $l" }
    }
    return $code
}

Say '=== 연 1회 스냅샷 시작 ==='
if (-not (Test-Path $VPy)) {
    Say "[X] 가상환경이 없습니다: $Backend\.venv"
    exit 1
}

Push-Location $Backend
$bad = 0
try {
    if ($Only -in @('kapt', 'both')) {
        Say 'K-apt 전수(25분쯤)...'
        # --missing-only 를 쓰지 않는다. 해마다 **전부 다시 봐야** 사라진 것이 드러난다.
        $code = Run @('-m', 'scripts.ingest_kapt_all', '--quiet')
        if ($code -ne 0) { Say "[X] K-apt 실패 (exit $code)"; $bad++ }
    }
    if ($Only -in @('bld', 'both')) {
        Say '건축물대장 전수(50분쯤)...'
        $code = Run @('-m', 'scripts.ingest_bldrgst')
        if ($code -ne 0) {
            # 끊겨도 받은 것은 법정동 단위로 커밋돼 있다. 한 번 이어받아 본다.
            Say "  끊겼습니다(exit $code) — 이어받기를 한 번 시도합니다"
            $code = Run @('-m', 'scripts.ingest_bldrgst', '--resume')
            if ($code -ne 0) { Say "[X] 건축물대장 실패 (exit $code)"; $bad++ }
        }
    }
} finally {
    Pop-Location
}

# PowerShell 5.1 에는 터너리(?:)가 없다. 시험 삼아 돌렸다가 파서 오류로 잡혔다.
if ($bad -eq 0) { Say '=== 완료 ===' } else { Say "=== 완료(실패 $bad) ===" }
exit $bad

<#
    작업 스케줄러 등록 (해마다 10월 14일 03:00)

    PowerShell 에서 한 번만 실행한다. 관리자 권한은 필요 없다.
    `-Weekly -WeeksInterval 52` 를 쓰는 이유: Register-ScheduledTask 에 '연 1회'
    트리거가 없다. 52주면 해마다 며칠씩 당겨지지만, 연 단위 통계라 상관없다.

      $act = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument '-NoProfile -ExecutionPolicy Bypass -File "E:\workspace\apt-price\snapshot_yearly.ps1" -Quiet'
      # **첫 실행을 1년 뒤로 민다.** -At 에 시각만 주면 이번 주 월요일에 돌아
      # 바로 두 번째 스냅샷이 떠 버린다(75분과 API 한도를 헛되이 쓴다).
      $when = Get-Date -Year 2027 -Month 10 -Day 11 -Hour 3 -Minute 0 -Second 0
      $trg = New-ScheduledTaskTrigger -Weekly -WeeksInterval 52 -DaysOfWeek Monday -At $when
      $set = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 4)
      Register-ScheduledTask -TaskName 'apt-price 연 1회 전수 스냅샷' `
        -Action $act -Trigger $trg -Settings $set `
        -Description '멸실을 직접 관측하기 위한 K-apt·건축물대장 전수 스냅샷'

    -StartWhenAvailable: 그날 컴퓨터가 꺼져 있었으면 켜진 뒤에 돌린다.
    ExecutionTimeLimit 4시간: 둘 합쳐 75분쯤이지만 API 가 느릴 때를 본다.

    로그는 snapshot_yearly.log 에 쌓인다(.gitignore 의 *.log 에 걸린다).
    해제: Unregister-ScheduledTask -TaskName 'apt-price 연 1회 전수 스냅샷'

    잊어도 `python -m scripts.checkup` 이 400일을 넘기면 알려 준다.
#>
