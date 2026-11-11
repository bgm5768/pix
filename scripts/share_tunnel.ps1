$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Stop-TunnelProcess {
    param($TunnelProcess)
    if ($TunnelProcess -and -not $TunnelProcess.HasExited) {
        Stop-Process -Id $TunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "=========================================="
Write-Host "  PixelForge - share this PC's GPU"
Write-Host "=========================================="
Write-Host ""

# 0. The backend must already be running on this PC.
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 5 | Out-Null
} catch {
    Write-Host "[ERROR] Backend is not running." -ForegroundColor Red
    Write-Host "        Start start.bat first, then run this script again."
    exit 1
}

# 1. Start a Cloudflare Quick Tunnel (no account required).
$log = Join-Path $env:TEMP "pixelforge-cloudflared.log"
Remove-Item -LiteralPath $log -Force -ErrorAction SilentlyContinue
Write-Host "[1/4] Starting Cloudflare Quick Tunnel..."

$cloudflaredArgs = "tunnel --url http://127.0.0.1:8765 --no-autoupdate --logfile `"$log`" --loglevel info"
$cf = Start-Process -FilePath "cloudflared" -ArgumentList $cloudflaredArgs -PassThru -WindowStyle Hidden

$tunnelUrl = $null
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $log) {
        try {
            $content = Get-Content -LiteralPath $log -Raw -ErrorAction Stop
        } catch {
            $content = ""
        }
        if ($content) {
            $match = [regex]::Match($content, "https://[a-z0-9-]+\.trycloudflare\.com")
            if ($match.Success) {
                $tunnelUrl = $match.Value
                break
            }
        }
    }
    if ($cf.HasExited) { break }
}

if (-not $tunnelUrl) {
    Write-Host "[ERROR] Could not get a tunnel URL from cloudflared." -ForegroundColor Red
    Write-Host "        Log: $log"
    Stop-TunnelProcess $cf
    exit 1
}

Write-Host "        Tunnel: $tunnelUrl" -ForegroundColor Cyan
try { Set-Clipboard -Value $tunnelUrl } catch { }

# 2. Build the static Pages UI with the tunnel URL baked in.
Write-Host "[2/4] Building the GitHub Pages UI..."
$env:VITE_API_BASE = $tunnelUrl
Push-Location (Join-Path $root "frontend")
& npm run build:pages
$buildCode = $LASTEXITCODE
Pop-Location
if ($buildCode -ne 0) {
    Write-Host "[ERROR] Frontend build failed." -ForegroundColor Red
    Stop-TunnelProcess $cf
    exit 1
}

# 3. Publish the build to the gh-pages branch.
Write-Host "[3/4] Deploying to GitHub Pages..."
$remote = (git remote get-url origin).Trim()
if (-not $remote) {
    Write-Host "[ERROR] git remote origin is not configured." -ForegroundColor Red
    Stop-TunnelProcess $cf
    exit 1
}
$gitName = (git config --get user.name).Trim()
if (-not $gitName) { $gitName = "bgm5768" }
$gitEmail = (git config --get user.email).Trim()
if (-not $gitEmail) { $gitEmail = "bgm5768@users.noreply.github.com" }

$pagesDir = Join-Path $env:TEMP ("pix-pages-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $pagesDir | Out-Null
Copy-Item -Path (Join-Path $root "frontend\dist\*") -Destination $pagesDir -Recurse -Force
New-Item -ItemType File -Path (Join-Path $pagesDir ".nojekyll") | Out-Null

Push-Location $pagesDir
git init -b gh-pages | Out-Null
git config user.name $gitName
git config user.email $gitEmail
git add -A
git commit -m "deploy: Pages UI with tunnel" | Out-Null
git remote add origin $remote
git push --force origin gh-pages
$pushCode = $LASTEXITCODE
Pop-Location
Remove-Item -LiteralPath $pagesDir -Recurse -Force -ErrorAction SilentlyContinue
if ($pushCode -ne 0) {
    Write-Host "[ERROR] GitHub Pages deploy failed." -ForegroundColor Red
    Stop-TunnelProcess $cf
    exit 1
}

# 4. Put the local frontend back on its normal root base.
Write-Host "[4/4] Restoring the local frontend build..."
Push-Location (Join-Path $root "frontend")
Remove-Item Env:VITE_API_BASE -ErrorAction SilentlyContinue
& npm run build | Out-Null
$localCode = $LASTEXITCODE
Pop-Location
if ($localCode -ne 0) {
    Write-Host "[WARN] Local build restore failed. Run npm run build in frontend." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Remote UI: https://bgm5768.github.io/pix/" -ForegroundColor Green
Write-Host "Tunnel:    $tunnelUrl" -ForegroundColor Green
Write-Host ""
Write-Host "Open the Remote UI on any PC. Keep this window open while using it." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop sharing. The tunnel URL changes every run." -ForegroundColor Yellow
Write-Host ""

try {
    Wait-Process -Id $cf.Id
} finally {
    Stop-TunnelProcess $cf
    Write-Host "Tunnel stopped."
}
