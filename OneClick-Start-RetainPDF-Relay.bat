@echo off
setlocal

cd /d "%~dp0"

set "CONFIG=%~dp0retainpdf-relay-proxy.json"
set "SCRIPT=%~dp0src\retainpdf_relay_proxy.py"
set "EXE=%~dp0dist\RetainPdfRelayProxy.exe"

if exist "%EXE%" (
  set "USE_EXE=1"
) else (
  set "USE_EXE=0"
)

if "%USE_EXE%"=="0" (
  where pythonw >nul 2>nul
  if errorlevel 1 (
    echo pythonw.exe was not found. Install Python for Windows or build dist\RetainPdfRelayProxy.exe first.
    pause
    exit /b 1
  )
)

if "%USE_EXE%"=="1" (
  start "" "%EXE%" --configure-and-run --config "%CONFIG%"
) else (
  start "" pythonw "%SCRIPT%" --configure-and-run --config "%CONFIG%"
)

exit /b 0
