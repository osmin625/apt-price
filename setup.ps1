#Requires -Version 5.1
<#
    수원시 아파트 적정 시세 — 개발 환경 설치

    setup.bat 이 이 스크립트를 호출한다. 로직이 .bat 이 아니라 여기 있는 이유:
    cmd.exe 는 배치 파일을 콘솔 코드페이지로 바이트 단위 해석하는데, 한글처럼
    멀티바이트 문자가 있으면 파서가 위치를 잃고 명령을 중간에서 잘라 버린다
    (install -> tall, popd -> pd). 인코딩을 CP949 로 바꿔도 마찬가지다.
    그래서 .bat 은 ASCII 런처로만 두고 한글이 필요한 로직은 PowerShell 로 옮겼다.

    이 파일은 반드시 **UTF-8 with BOM** 으로 저장해야 한다.
    Windows PowerShell 5.1 은 BOM 이 없으면 UTF-8 을 ANSI 로 읽어 한글이 깨지고
    문자열 리터럴이 끊겨 파싱 에러가 난다.
#>
[CmdletBinding()]
param(
    [switch]$Yes,      # 확인 없이 진행
    [switch]$Check,    # 설치하지 않고 상태만 점검
    [switch]$Recreate  # 가상환경을 지우고 새로 만든다 (서버가 떠 있으면 실패)
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Venv     = Join-Path $Backend '.venv'
$VPy      = Join-Path $Venv 'Scripts\python.exe'
$PyVer    = '3.11'

function Write-Step  ($n, $t) { Write-Host ''; Write-Host "[$n] $t" -ForegroundColor Cyan }
function Write-Ok    ($t) { Write-Host "  [O] $t" -ForegroundColor Green }
function Write-Warn2 ($t) { Write-Host "  [!] $t" -ForegroundColor Yellow }
function Write-Bad   ($t) { Write-Host "  [X] $t" -ForegroundColor Red }
function Write-Info  ($t) { Write-Host "  $t" -ForegroundColor Gray }

function Test-Cmd ($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-Port ($port) {
    try {
        return ($null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop))
    } catch {
        return $false
    }
}

function New-Venv ($clear) {
    if ($clear) {
        uv venv .venv --python $PyVer --clear
    } else {
        uv venv .venv --python $PyVer --allow-existing
    }
    return ($LASTEXITCODE -eq 0)
}

function Install-Deps {
    uv pip install --python $VPy -r requirements.txt
    return ($LASTEXITCODE -eq 0)
}

function Test-Deps {
    # 실제로 불러와 본다. 메타데이터만 보고 판단하면 반쯤 지워진 환경을 못 잡는다.
    & $VPy -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, dotenv, httpx, numpy, pandas, statsmodels"
    return ($LASTEXITCODE -eq 0)
}

function Update-PathFromEnvironment {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $local   = Join-Path $env:USERPROFILE '.local\bin'
    $env:Path = "$local;$machine;$user"
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor White
Write-Host '  수원시 아파트 적정 시세 — 환경 설치' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor White

# ---------------------------------------------------------------- 0) 사전 점검
Write-Step '0/6' '사전 점검'
if (-not (Test-Cmd 'node')) {
    Write-Bad 'Node.js 를 찾을 수 없습니다. https://nodejs.org 에서 LTS 를 설치하세요.'
    exit 1
}
Write-Ok "Node $(node --version)"
Write-Ok "npm  $(npm --version)"

# 실행 중인 백엔드는 .venv 안의 DLL 을 잡고 있어 가상환경 교체를 막는다.
if (Test-Port 8000) {
    Write-Warn2 '백엔드 서버가 8000 포트에서 실행 중입니다.'
    Write-Info '재사용 모드에서는 문제없지만, /recreate 를 쓰려면 먼저 종료해야 합니다.'
}

if ($Check) {
    if (Test-Cmd 'uv') { Write-Ok "$(uv --version)" } else { Write-Info '[ ] uv 미설치' }
    if (Test-Path $VPy) { Write-Ok "가상환경 $Venv" } else { Write-Info '[ ] 가상환경 없음' }
    if (Test-Path (Join-Path $Backend '.env'))            { Write-Ok 'backend\.env' }        else { Write-Info '[ ] backend\.env 없음' }
    if (Test-Path (Join-Path $Frontend '.env.local'))     { Write-Ok 'frontend\.env.local' } else { Write-Info '[ ] frontend\.env.local 없음' }
    if (Test-Path (Join-Path $Frontend 'node_modules'))   { Write-Ok 'node_modules' }        else { Write-Info '[ ] node_modules 없음' }
    if (Test-Path (Join-Path $Backend 'data\apt.db'))     { Write-Ok 'DB' }                  else { Write-Info '[ ] DB 없음' }
    Write-Host ''
    Write-Info '-Check 모드라 아무것도 설치하지 않았습니다.'
    exit 0
}

# ---------------------------------------------------------------- 1) uv
Write-Step '1/6' 'uv 확인'
if (Test-Cmd 'uv') {
    Write-Ok "이미 설치됨: $(uv --version)"
} else {
    Write-Info 'uv 가 설치돼 있지 않습니다.'
    if (-not $Yes) {
        Write-Host ''
        Write-Info 'winget 으로 설치를 시도하고, 실패하면 Astral 공식 설치 스크립트를 내려받아 실행합니다:'
        Write-Info '  https://astral.sh/uv/install.ps1'
        Write-Host ''
        $ans = Read-Host '  설치할까요? [Y/N]'
        if ($ans -notmatch '^[Yy]') {
            Write-Host ''
            Write-Info '설치를 건너뜁니다. 아래 중 편한 방법으로 직접 설치한 뒤 다시 실행하세요.'
            Write-Info '  winget install --id=astral-sh.uv -e'
            Write-Info '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
            exit 1
        }
    }

    if (Test-Cmd 'winget') {
        Write-Info 'winget 으로 설치 중...'
        winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
        Update-PathFromEnvironment
    }
    if (-not (Test-Cmd 'uv')) {
        Write-Info '공식 설치 스크립트로 재시도합니다...'
        try {
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        } catch {
            Write-Bad "설치 스크립트 실행 실패: $($_.Exception.Message)"
        }
        Update-PathFromEnvironment
    }
    if (-not (Test-Cmd 'uv')) {
        Write-Host ''
        Write-Bad 'uv 설치를 확인하지 못했습니다.'
        Write-Info '새 터미널을 열면 PATH 가 갱신되어 인식될 수 있습니다. 그 뒤 setup.bat 을 다시 실행하세요.'
        exit 1
    }
    Write-Ok "설치 완료: $(uv --version)"
}

Push-Location $Backend
try {
    # ------------------------------------------------------------ 2) 가상환경
    <#
        기본은 기존 가상환경을 **지우지 않고 재사용**한다. 매번 다시 만들면
        느리기도 하지만, 무엇보다 백엔드 서버가 떠 있을 때 .venv\Lib 의 DLL 이
        잠겨 있어 삭제가 거부된다(os error 5). 패키지는 아래 uv pip install 이
        어차피 requirements.txt 기준으로 맞춰 준다.
    #>
    Write-Step '2/6' '파이썬 가상환경 (backend\.venv)'
    $venvExists = Test-Path $Venv
    $venvBroken = $venvExists -and -not (Test-Path $VPy)
    $clear = ($Recreate -or $venvBroken)

    if ($venvBroken) { Write-Warn2 '가상환경이 손상됐습니다 (python.exe 없음) — 새로 만듭니다.' }
    if ($clear -and (Test-Port 8000)) {
        Write-Bad '백엔드 서버가 실행 중이라 가상환경을 지울 수 없습니다.'
        Write-Info '서버 창에서 Ctrl+C 로 종료한 뒤 다시 실행하세요.'
        Write-Info '(지우지 않고 그대로 쓰려면 /recreate 없이 실행하면 됩니다.)'
        exit 1
    }
    if (-not $clear -and $venvExists) {
        Write-Info '기존 가상환경 재사용 (새로 만들려면 setup.bat /recreate)'
    }

    if (-not (New-Venv $clear)) { Write-Bad "가상환경 생성 실패 (Python $PyVer)"; exit 1 }
    Write-Ok $Venv

    # ------------------------------------------------------------ 3) 의존성
    Write-Step '3/6' '파이썬 의존성 설치'
    if (-not (Install-Deps)) { Write-Bad '의존성 설치 실패'; exit 1 }

    <#
        설치했다고 끝이 아니다. 앞서 실패한 재생성이 site-packages 를 반쯤 지우고
        죽으면 .dist-info 만 남아 uv 는 "이미 설치됨"으로 보는데 실제 import 는
        실패한다(ModuleNotFoundError: dotenv). 그래서 실제로 불러와서 확인하고,
        깨졌으면 한 번은 자동으로 갈아엎는다.
    #>
    if (-not (Test-Deps)) {
        Write-Warn2 'import 검증 실패 — site-packages 가 일관되지 않습니다. 가상환경을 다시 만듭니다.'
        if (Test-Port 8000) {
            Write-Bad '백엔드 서버가 실행 중이라 다시 만들 수 없습니다. 종료 후 재실행하세요.'
            exit 1
        }
        if (-not (New-Venv $true))  { Write-Bad '가상환경 재생성 실패'; exit 1 }
        if (-not (Install-Deps))    { Write-Bad '의존성 재설치 실패'; exit 1 }
        if (-not (Test-Deps))       { Write-Bad '재설치 후에도 import 에 실패했습니다.'; exit 1 }
    }
    Write-Ok 'requirements.txt 설치 및 import 검증 완료'

    # ------------------------------------------------------------ 4) .env
    Write-Step '4/6' '환경 변수 파일'
    $beEnv = Join-Path $Backend '.env'
    if (Test-Path $beEnv) {
        Write-Info 'backend\.env 이미 있음 — 건드리지 않음'
    } else {
        Copy-Item (Join-Path $Backend '.env.example') $beEnv
        Write-Ok 'backend\.env 생성 (키는 비어 있음 — 합성 데이터로 동작)'
    }
    $feEnv = Join-Path $Frontend '.env.local'
    if (Test-Path $feEnv) {
        Write-Info 'frontend\.env.local 이미 있음 — 건드리지 않음'
    } else {
        Copy-Item (Join-Path $Frontend '.env.example') $feEnv
        Write-Ok 'frontend\.env.local 생성 (카카오 JS 키 비어 있음 — 지도 탭은 안내 화면)'
    }

    # ------------------------------------------------------------ 5) 데이터
    Write-Step '5/6' '합성 데이터 생성 (단지 - 역 - 도보거리 - 거래)'
    & $VPy -m scripts.seed_demo --recreate-schema
    if ($LASTEXITCODE -ne 0) { Write-Bad '시드 생성 실패'; exit 1 }

    Write-Host ''
    Write-Info '모델 검증 (참값 복원)'
    & $VPy -m scripts.validate_model
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 '검증 실패 — 앱은 동작하지만 모델 결과를 신뢰하기 전에 확인이 필요합니다.'
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 6) 프론트
Write-Step '6/6' '프론트엔드 의존성 설치'
Push-Location $Frontend
try {
    npm install
    if ($LASTEXITCODE -ne 0) { Write-Bad 'npm install 실패'; exit 1 }
    Write-Ok 'node_modules 설치 완료'
} finally {
    Pop-Location
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host '  설치 완료' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host '  실행:  .\start.bat' -ForegroundColor White
Write-Host ''
Write-Info '선택 — 실제 데이터를 쓰려면 backend\.env 에 키를 넣으세요.'
Write-Info '  MOLIT_SERVICE_KEY   국토교통부 실거래가 (없으면 합성 데이터)'
Write-Info '  KAKAO_REST_KEY      단지 수집 + 좌표 조회'
Write-Info '  TMAP_APP_KEY        도보 실거리 (없으면 직선거리 추정)'
Write-Info '지도용 카카오 JS 키는 frontend\.env.local 의 VITE_KAKAO_JS_KEY 입니다.'
Write-Host ''
exit 0
