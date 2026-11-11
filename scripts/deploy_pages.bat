@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Install Node.js 20 or newer.
  exit /b 1
)

echo [1/3] Building frontend for GitHub Pages...
pushd "%ROOT%\frontend"
call npm run build:pages
if errorlevel 1 (
  popd
  echo [ERROR] Frontend build failed.
  exit /b 1
)
popd

set "REMOTE="
for /f "delims=" %%i in ('git remote get-url origin 2^>nul') do set "REMOTE=%%i"
if not defined REMOTE (
  echo [ERROR] git remote "origin" is not configured.
  exit /b 1
)

set "GIT_NAME="
for /f "delims=" %%i in ('git config --get user.name 2^>nul') do set "GIT_NAME=%%i"
if not defined GIT_NAME set "GIT_NAME=bgm5768"
set "GIT_EMAIL="
for /f "delims=" %%i in ('git config --get user.email 2^>nul') do set "GIT_EMAIL=%%i"
if not defined GIT_EMAIL set "GIT_EMAIL=bgm5768@users.noreply.github.com"

set "PAGES_DIR=%TEMP%\pix-pages-%RANDOM%%RANDOM%"
mkdir "%PAGES_DIR%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Could not create %PAGES_DIR%
  exit /b 1
)

echo [2/3] Preparing gh-pages content...
xcopy "%ROOT%\frontend\dist\*" "%PAGES_DIR%\" /E /I /Y >nul
if errorlevel 1 goto :fail
type nul > "%PAGES_DIR%\.nojekyll"

pushd "%PAGES_DIR%"
git init -b gh-pages >nul
git config user.name "%GIT_NAME%"
git config user.email "%GIT_EMAIL%"
git add -A
git commit -m "deploy: GitHub Pages UI %DATE% %TIME%" >nul
if errorlevel 1 goto :fail_pop
git remote add origin "%REMOTE%"
echo [3/3] Pushing gh-pages...
git push --force origin gh-pages
if errorlevel 1 goto :fail_pop
popd
rmdir /S /Q "%PAGES_DIR%"
echo.
echo [OK] Deployed to https://bgm5768.github.io/pix/
echo      GitHub Pages may take a minute to update.
exit /b 0

:fail_pop
popd
:fail
rmdir /S /Q "%PAGES_DIR%" >nul 2>&1
echo [ERROR] Deployment failed.
exit /b 1
