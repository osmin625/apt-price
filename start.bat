@echo off
rem ===========================================================================
rem  Suwon apartment price PoC - dev servers (launcher)
rem
rem  Usage:
rem    start.bat              backend + frontend, then open the browser
rem    start.bat /nobrowser   do not open the browser
rem    start.bat /backend     backend only
rem    start.bat /frontend    frontend only
rem
rem  ASCII-only on purpose - see the comment in setup.bat.
rem ===========================================================================
setlocal

rem Capture the script directory BEFORE the parse loop: `shift` also shifts %0.
set "HERE=%~dp0"

set "ARGS="
:parse
if "%~1"=="" goto run
if /i "%~1"=="/nobrowser" set "ARGS=%ARGS% -NoBrowser"
if /i "%~1"=="/backend"   set "ARGS=%ARGS% -BackendOnly"
if /i "%~1"=="/frontend"  set "ARGS=%ARGS% -FrontendOnly"
shift
goto parse

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%start.ps1"%ARGS%
set "RC=%ERRORLEVEL%"

rem The servers get their own windows, so on success this one just closes.
if not "%RC%"=="0" (
  echo.
  echo Could not start the servers. See the messages above.
  pause
)

endlocal & exit /b %RC%
