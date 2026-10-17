# Starts the DawaiFlow backend on this PC for phone testing and links every USB-connected phone to it.
#
#   cd C:\Users\vashi\OneDrive\Desktop\ExpiryGuard_Backend
#   .\scripts\dev_local.ps1
#
# What it does
#   1. Starts the backend in its own window (port 8000), scheduler OFF (ENABLE_SCHEDULER=0), logging to server.log
#   2. Waits until the server answers
#   3. Runs `adb reverse tcp:8000 tcp:8000` for every connected phone (phone 127.0.0.1:8000 -> this PC)
#   4. Prints a status summary
#
# NOTE: the backend uses the LIVE Supabase database from .env. Treat everything you do in the app as real data.
# It starts nothing outside this PC and spends nothing.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\python.exe"
$adb  = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
$log  = Join-Path $root "server.log"

function Test-Server {
    try { (Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
    catch { $false }
}

if (-not (Test-Path $py))  { throw "Python not found at $py" }
if (-not (Test-Path $adb)) { Write-Warning "adb not found at $adb : phones cannot be linked." }

# 1. backend
if (Test-Server) {
    Write-Host "[1/3] Backend already running on port 8000 (left as is)." -ForegroundColor Green
} else {
    Write-Host "[1/3] Starting backend (scheduler OFF), log: $log" -ForegroundColor Cyan
    $cmd = "`$env:ENABLE_SCHEDULER='0'; `$host.UI.RawUI.WindowTitle='DawaiFlow backend (local)'; " +
           "Set-Location '$root'; & '$py' start_server.py 2>&1 | Tee-Object -FilePath '$log'"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd | Out-Null
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Server) { $ok = $true; break }
    }
    if (-not $ok) { throw "Backend did not answer within 60 s. Look at the 'DawaiFlow backend (local)' window." }
    Write-Host "      Backend is up." -ForegroundColor Green
}

# 2. phones
Write-Host "[2/3] Linking phones..." -ForegroundColor Cyan
$linked = 0
if (Test-Path $adb) {
    & $adb start-server | Out-Null
    $devices = (& $adb devices) | Select-Object -Skip 1 | Where-Object { $_ -match "\sdevice$" } | ForEach-Object { ($_ -split "\s+")[0] }
    if (-not $devices) { Write-Warning "No phone found. Plug it in, accept the USB debugging prompt, run this script again." }
    foreach ($d in $devices) {
        & $adb -s $d reverse tcp:8000 tcp:8000 | Out-Null
        $list = (& $adb -s $d reverse --list) -join " "
        Write-Host "      $d -> $list"
        $linked++
    }
}

# 3. summary
Write-Host "[3/3] Status" -ForegroundColor Cyan
Write-Host ("      Backend reachable : {0}" -f (Test-Server))
Write-Host ("      Phones linked     : {0}" -f $linked)
Write-Host "      The app must be built with: flutter run --release --dart-define-from-file=dart_defines.json"
Write-Host "      Server log (for debugging): $log"
