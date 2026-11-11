@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

net session >nul 2>&1
if errorlevel 1 (
  echo [INFO] Requesting administrator permission...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

echo ==========================================
echo   PixelForge - allow LAN access
echo ==========================================
echo.
echo Adding an inbound firewall rule for TCP 8765.
echo It is limited to this PC's local subnet.
echo.

netsh advfirewall firewall delete rule name="PixelForge Backend (TCP 8765)" >nul 2>&1
netsh advfirewall firewall add rule name="PixelForge Backend (TCP 8765)" dir=in action=allow protocol=TCP localport=8765 profile=any remoteip=LocalSubnet >nul
if errorlevel 1 (
  echo [ERROR] Could not add the firewall rule.
  pause
  exit /b 1
)

echo [OK] Other PCs on the same LAN can now connect to this PC.
echo.
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } ^| ForEach-Object { $_.IPAddress }" 2^>nul') do echo        LAN: http://%%i:8765
echo.
echo Keep start.bat running while other PCs use the backend.
echo.
pause
