@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "VENV=%ROOT%\backend\.venv"
set "PY=%VENV%\Scripts\python.exe"

echo ==========================================
echo   PixelForge Local
echo   Local AI pixel art (ComfyUI + SDXL)
echo ==========================================
echo.

rem --- Already running? -------------------------------------------------
netstat -ano | findstr "127.0.0.1:8765" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] PixelForge backend is already running.
  echo        Opening http://127.0.0.1:8765
  start "" "http://127.0.0.1:8765"
  exit /b 0
)

rem --- Python ------------------------------------------------------------
rem Prefer the versions the pinned wheels are verified against. The py
rem launcher's plain "-3" can select a much newer Python without wheels.
set "SYSPY="
where py >nul 2>&1
if not errorlevel 1 (
  for %%V in (3.11 3.12 3.13) do (
    if not defined SYSPY (
      py -%%V --version >nul 2>&1
      if not errorlevel 1 set "SYSPY=py -%%V"
    )
  )
)
if not defined SYSPY (
  where python >nul 2>&1
  if not errorlevel 1 set "SYSPY=python"
)
if not defined SYSPY (
  echo [ERROR] Python 3.11-3.13 was not found.
  echo         Install Python from https://www.python.org/downloads/ and enable "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

if not exist "%PY%" (
  echo [1/4] Creating Python virtual environment...
  %SYSPY% -m venv "%VENV%"
  if errorlevel 1 (
    echo [ERROR] Failed to create the virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [1/4] Python virtual environment ready.
)

echo [2/4] Checking backend dependencies...
"%PY%" -m pip install --disable-pip-version-check --quiet -r "%ROOT%\backend\requirements.txt"
if errorlevel 1 (
  echo [ERROR] Failed to install backend dependencies.
  echo         Check your internet connection, then run scripts\start.bat again.
  pause
  exit /b 1
)

if not exist "%ROOT%\frontend\dist\index.html" (
  echo [3/4] Building the frontend ^(first run only^)...
  where npm >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Node.js/npm was not found.
    echo         Install Node.js 20+ from https://nodejs.org/ and run scripts\start.bat again.
    pause
    exit /b 1
  )
  pushd "%ROOT%\frontend"
  if not exist node_modules (
    call npm install
    if errorlevel 1 (
      popd
      echo [ERROR] npm install failed.
      pause
      exit /b 1
    )
  )
  call npm run build
  if errorlevel 1 (
    popd
    echo [ERROR] Frontend build failed.
    pause
    exit /b 1
  )
  popd
) else (
  echo [3/4] Frontend build found.
)

echo [4/4] Starting backend: http://127.0.0.1:8765
echo        The browser will open automatically. Press Ctrl+C to stop.
echo.
pushd "%ROOT%\backend"
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
set "EXITCODE=%errorlevel%"
popd

if not "%EXITCODE%"=="0" (
  echo.
  echo [ERROR] Backend stopped with exit code %EXITCODE%.
  echo         See logs\backend.log for details.
  pause
)
exit /b %EXITCODE%
