@echo off
rem ===========================================================================
rem  Suwon apartment price PoC - environment setup (launcher)
rem
rem  Usage:
rem    setup.bat            interactive
rem    setup.bat /y         no prompts
rem    setup.bat /check     diagnose only, install nothing
rem    setup.bat /recreate  rebuild the venv from scratch (stop servers first)
rem
rem  This file is intentionally ASCII-only. cmd.exe parses batch files byte by
rem  byte in the console code page; any multi-byte character (e.g. Korean)
rem  desyncs the parser and truncates commands mid-line. All logic and all
rem  Korean output live in setup.ps1 instead.
rem ===========================================================================
setlocal

rem Capture the script directory BEFORE the parse loop: `shift` also shifts %0,
rem so %~dp0 would resolve against the wrong argument afterwards.
set "HERE=%~dp0"

set "ARGS="
:parse
if "%~1"=="" goto run
if /i "%~1"=="/y"        set "ARGS=%ARGS% -Yes"
if /i "%~1"=="/yes"      set "ARGS=%ARGS% -Yes"
if /i "%~1"=="/check"    set "ARGS=%ARGS% -Check"
if /i "%~1"=="/recreate" set "ARGS=%ARGS% -Recreate"
shift
goto parse

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%setup.ps1"%ARGS%
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo Setup did not finish successfully. See the messages above.
)

rem One-time script: always pause so the summary stays readable when the file
rem is double-clicked from Explorer.
pause

endlocal & exit /b %RC%
