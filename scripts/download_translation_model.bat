@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

set "PY=backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] backend\.venv not found. Run start.bat first.
  pause
  exit /b 1
)

echo Downloading the Korean -> English translation model...
"%PY%" scripts\download_translation_model.py %*
echo.
pause
