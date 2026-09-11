# ==============================================================================
# Dawaiflow / ExpiryGuard - Windows Defender Firewall Hardening Script
# ==============================================================================
# Enforces database port 5432 isolation and opens ports 80/443 for reverse proxy.
# Run in an elevated PowerShell session (Run as Administrator).
# ==============================================================================

# Ensure Administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This script must be run as Administrator."
    Exit 1
}

Write-Host "[*] Configuring Windows Defender Firewall for Dawaiflow / ExpiryGuard..." -ForegroundColor Cyan

# 1. Allow HTTP (Port 80) and HTTPS (Port 443) Inbound for Reverse Proxy
Write-Host "[*] Allowing Inbound HTTP (80) & HTTPS (443)..." -ForegroundColor Yellow
New-NetFirewallRule -DisplayName "Dawaiflow-ReverseProxy-HTTP-In" `
    -Direction Inbound `
    -LocalPort 80 `
    -Protocol TCP `
    -Action Allow `
    -Profile Any `
    -ErrorAction SilentlyContinue | Out-Null

New-NetFirewallRule -DisplayName "Dawaiflow-ReverseProxy-HTTPS-In" `
    -Direction Inbound `
    -LocalPort 443 `
    -Protocol TCP `
    -Action Allow `
    -Profile Any `
    -ErrorAction SilentlyContinue | Out-Null

# 2. Block Public / Remote Inbound Access to PostgreSQL (Port 5432)
Write-Host "[*] Isolating PostgreSQL Port 5432 from Public Network..." -ForegroundColor Yellow

# Remove any old permissive rules
Remove-NetFirewallRule -DisplayName "PostgreSQL*" -ErrorAction SilentlyContinue | Out-Null
Remove-NetFirewallRule -DisplayName "Dawaiflow-Postgres*" -ErrorAction SilentlyContinue | Out-Null

# Explicitly Block Port 5432 on Public Profile
New-NetFirewallRule -DisplayName "Dawaiflow-Postgres-Block-Public" `
    -Direction Inbound `
    -LocalPort 5432 `
    -Protocol TCP `
    -Action Block `
    -Profile Public `
    -ErrorAction SilentlyContinue | Out-Null

# Allow Port 5432 ONLY on Loopback (127.0.0.1) and Local Private Subnet
New-NetFirewallRule -DisplayName "Dawaiflow-Postgres-Allow-Loopback-Only" `
    -Direction Inbound `
    -LocalPort 5432 `
    -Protocol TCP `
    -Action Allow `
    -RemoteAddress 127.0.0.1, ::1, 172.16.0.0/12, 10.0.0.0/16 `
    -Profile Domain, Private `
    -ErrorAction SilentlyContinue | Out-Null

Write-Host "[+] Windows Defender Firewall configured successfully!" -ForegroundColor Green
Write-Host "[+] Port 5432 is restricted to loopback and internal subnets. Public access blocked." -ForegroundColor Green
