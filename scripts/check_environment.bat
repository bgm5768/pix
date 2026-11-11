@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "SHARED=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models"
set "COMFY=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI"
set "FAIL=0"

echo ==========================================
echo   PixelForge Local - environment check
echo ==========================================
echo.

echo [Python]
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
if not defined SYSPY goto :python_missing
echo   Selected runtime:
call %SYSPY% --version
goto :python_done
:python_missing
echo   MISSING: Python 3.11-3.13  https://www.python.org/downloads/
set "FAIL=1"
:python_done
echo.

echo [Node.js / npm]
where node >nul 2>&1
if errorlevel 1 (
  echo   MISSING: Node.js 20+  https://nodejs.org/
  set "FAIL=1"
) else (
  node --version
  call npm --version
)
echo.

echo [ComfyUI installation]
if exist "%COMFY%\ComfyUI\main.py" (
  echo   OK: %COMFY%\ComfyUI\main.py
) else (
  echo   NOT FOUND: %COMFY%\ComfyUI\main.py
  echo   If ComfyUI is installed elsewhere, edit config\settings.yaml.
  set "FAIL=1"
)
if exist "%COMFY%\ComfyUI\.venv\Scripts\python.exe" (
  echo   OK: ComfyUI Python runtime
) else (
  echo   NOT FOUND: ComfyUI .venv Python runtime
  set "FAIL=1"
)
echo.

echo [ComfyUI API - 127.0.0.1:8188]
curl.exe -s -m 5 http://127.0.0.1:8188/system_stats >nul 2>&1
if errorlevel 1 (
  echo   Not responding. PixelForge will try to start ComfyUI automatically.
) else (
  echo   OK: API is responding.
)
echo.

echo [Models]
if exist "%SHARED%\checkpoints\sd_xl_base_1.0.safetensors" (
  echo   OK: sd_xl_base_1.0.safetensors
) else (
  echo   MISSING: %SHARED%\checkpoints\sd_xl_base_1.0.safetensors
  echo   Download: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
  set "FAIL=1"
)
if exist "%SHARED%\loras\pixel-art-xl.safetensors" (
  echo   OK: pixel-art-xl.safetensors
) else (
  echo   MISSING: %SHARED%\loras\pixel-art-xl.safetensors
  echo   Download: https://huggingface.co/nerijs/pixel-art-xl/resolve/main/pixel-art-xl.safetensors
  set "FAIL=1"
)
if exist "%SHARED%\checkpoints\lustifySDXLNSFWSFW_v20.safetensors" (
  echo   OK: lustifySDXLNSFWSFW_v20.safetensors
) else (
  echo   OPTIONAL: LUSTIFY! v2.0 not installed - download it from the app model list.
)
if exist "%SHARED%\loras\sexy.safetensors" (
  echo   OK: sexy.safetensors
) else (
  echo   OPTIONAL: sexy LoRA not installed - download it from the app model list.
)
echo.

echo [GPU]
where nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo   nvidia-smi not found. Install/update the NVIDIA driver.
) else (
  nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
)
echo.

echo [Backend port 8765]
netstat -ano | findstr "127.0.0.1:8765" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  echo   Free.
) else (
  echo   In use - PixelForge is probably already running: http://127.0.0.1:8765
)
echo.

if "%FAIL%"=="1" (
  echo ==========================================
  echo   Some checks failed. See the messages above.
  echo ==========================================
) else (
  echo ==========================================
  echo   Everything looks ready. Run start.bat.
  echo ==========================================
)
echo.
pause
exit /b %FAIL%
