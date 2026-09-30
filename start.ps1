#Requires -Version 5.1
<#
    수원시 아파트 적정 시세 — 개발 서버 실행

    start.bat 이 이 스크립트를 호출한다. 로직이 .bat 이 아닌 이유와
    UTF-8 with BOM 으로 저장해야 하는 이유는 setup.ps1 의 주석 참조.
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$VPy      = Join-Path $Backend '.venv\Scripts\python.exe'

function Write-Info ($t) { Write-Host "  $t" -ForegroundColor Gray }
function Write-Bad  ($t) { Write-Host "  [X] $t" -ForegroundColor Red }

function Test-Port ($port) {
    <#
        IPv4 와 IPv6 를 둘 다 봐야 한다. Vite 는 [::1] 에만, uvicorn 은
        127.0.0.1 에만 바인딩하므로 한쪽만 검사하면 멀쩡히 떠 있는 서버를
        못 찾고 중복 실행하게 된다.

        TcpClient 의 기본 생성자는 IPv4 전용이라 '::1' 로는 연결 시도조차
        못 한다. 리스너 테이블을 직접 조회하는 쪽이 정확하고 빠르다.
    #>
    try {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
        return ($null -ne $conn)
    } catch {
        # Get-NetTCPConnection 이 없는 환경 대비 — 호스트명으로 넘기면
        # TcpClient 가 IPv4/IPv6 주소를 모두 시도한다.
        $c = New-Object System.Net.Sockets.TcpClient
        try {
            $c.Connect('localhost', $port)
            return $c.Connected
        } catch {
            return $false
        } finally {
            $c.Close()
        }
    }
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor White
Write-Host '  수원시 아파트 적정 시세 — 개발 서버' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor White
Write-Host ''

# ---------------------------------------------------------------- 사전 확인
if (-not (Test-Path $VPy)) {
    Write-Bad "가상환경이 없습니다: $Backend\.venv"
    Write-Info '먼저 .\setup.bat 을 실행하세요.'
    exit 1
}
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Write-Bad '프론트엔드 의존성이 없습니다.'
    Write-Info '먼저 .\setup.bat 을 실행하세요.'
    exit 1
}
if (-not (Test-Path (Join-Path $Backend 'data\apt.db'))) {
    Write-Host '  [!] DB 가 없습니다. 합성 데이터를 먼저 생성합니다...' -ForegroundColor Yellow
    Push-Location $Backend
    try {
        & $VPy -m scripts.seed_demo --recreate-schema
        if ($LASTEXITCODE -ne 0) { Write-Bad '시드 생성 실패'; exit 1 }
    } finally {
        Pop-Location
    }
    Write-Host ''
}

# ---------------------------------------------------------------- 실행
$startBackend  = -not $FrontendOnly
$startFrontend = -not $BackendOnly

if ($startBackend) {
    if (Test-Port 8000) {
        Write-Info '백엔드  http://localhost:8000  (이미 실행 중 — 새로 띄우지 않음)'
    } else {
        Write-Host '  백엔드  http://localhost:8000      (API 문서: /docs)' -ForegroundColor White
        $cmd = "chcp 65001 >nul & cd /d ""$Backend"" & "".venv\Scripts\python.exe"" -m uvicorn app.main:app --reload --port 8000"
        Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $cmd | Out-Null
    }
}

if ($startFrontend) {
    if (Test-Port 5173) {
        Write-Info '프론트  http://localhost:5173  (이미 실행 중 — 새로 띄우지 않음)'
    } else {
        Write-Host '  프론트  http://localhost:5173' -ForegroundColor White
        $cmd = "chcp 65001 >nul & cd /d ""$Frontend"" & npm run dev"
        Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $cmd | Out-Null
    }
}

# ---------------------------------------------------------------- 브라우저
<#
    백엔드까지 기다린다.

    예전에는 5173 만 기다리고 브라우저를 열었다. Vite 는 1~2초에 뜨지만 백엔드는
    uvicorn + numpy/pandas/statsmodels import 까지 있어 훨씬 느리다. 그래서 첫
    화면(시장 분석)의 `/api/model/factors` 가 아직 안 뜬 8000 으로 가서 프록시에서
    끊겼고, 화면에는 "모델 의존성이 설치되지 않았습니다 — pip install 하세요" 가
    떴다. 의존성은 멀쩡했다. 사용자가 없는 문제를 쫓게 만든 셈이다.

    포트가 아니라 /api/health 로 확인한다. 리스닝만으로는 부족하다 — uvicorn 은
    소켓을 먼저 열고 앱 import 를 나중에 끝내므로, 포트가 열린 직후의 요청은
    여전히 실패할 수 있다.
#>
function Test-Api {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

if ($startFrontend -and -not $NoBrowser) {
    Write-Host ''
    Write-Info '서버가 뜰 때까지 기다리는 중...'

    $frontReady = $false
    foreach ($i in 1..40) {
        if (Test-Port 5173) { $frontReady = $true; break }
        Start-Sleep -Milliseconds 500
    }

    # 백엔드는 더 오래 준다(최대 60초). 모델 import 가 느린 환경이 있다.
    $apiReady = $false
    if ($startBackend) {
        foreach ($i in 1..120) {
            if (Test-Api) { $apiReady = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if ($apiReady) {
            Write-Info '백엔드 준비됨.'
        } else {
            Write-Host '  [!] 백엔드가 60초 안에 응답하지 않았습니다. 백엔드 창의 로그를 확인하세요.' -ForegroundColor Yellow
        }
    }

    if ($frontReady) {
        Start-Process 'http://localhost:5173'
    } else {
        Write-Host '  [!] 5173 포트 응답이 없습니다. 열린 창의 로그를 확인하세요.' -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  서버는 각각 별도 창에서 실행 중입니다.' -ForegroundColor Green
Write-Host '  종료하려면 해당 창에서 Ctrl+C 를 누르거나 창을 닫으세요.' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
exit 0
