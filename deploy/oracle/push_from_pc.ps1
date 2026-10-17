# Copies the backend from this PC to the Oracle VM and (re)starts it there.
# Nothing is pushed to GitHub: the files go straight to your own server over SSH.
#
# Usage (PowerShell, in the backend folder):
#   .\deploy\oracle\push_from_pc.ps1 -Server <VM public IP> -Key C:\path\to\ssh-key.key
#
# Copies: the code, .env and credentials\ (needed to run). Skips: virtualenvs, caches, local uploads/backups,
# scratch files and the old flutter stub.
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Key,
    [string]$User = "ubuntu"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$archive = Join-Path $env:TEMP "dawaiflow_backend.tgz"

if (-not (Test-Path (Join-Path $root ".env"))) { throw ".env not found in $root" }
if (-not (Test-Path $Key)) { throw "SSH key not found: $Key" }

Write-Host "[1/3] Packing backend..." -ForegroundColor Cyan
Push-Location $root
tar -czf $archive `
    --exclude=.venv --exclude=venv --exclude=.git --exclude=__pycache__ --exclude=flutter `
    --exclude=uploads --exclude=backups --exclude=scratch --exclude=_backup --exclude=temp_import_cache `
    --exclude=temp_migrations --exclude="scratch_*.py" --exclude="*.log" --exclude=server.log `
    .
Pop-Location
Write-Host ("      {0:N1} MB" -f ((Get-Item $archive).Length / 1MB))

Write-Host "[2/3] Uploading to $User@$Server ..." -ForegroundColor Cyan
scp -i $Key -o StrictHostKeyChecking=accept-new $archive "${User}@${Server}:/opt/dawaiflow/backend.tgz"

Write-Host "[3/3] Unpacking and starting containers (first build takes several minutes)..." -ForegroundColor Cyan
$remote = "set -e; cd /opt/dawaiflow; mkdir -p app; tar -xzf backend.tgz -C app; rm backend.tgz; " +
          "cd app/deploy/oracle; sudo docker compose up -d --build; sudo docker compose ps"
ssh -i $Key "${User}@${Server}" $remote

Remove-Item $archive -ErrorAction SilentlyContinue
Write-Host "Done. Check: https://api.dawaiflow.com/  (after DNS points to $Server)" -ForegroundColor Green
