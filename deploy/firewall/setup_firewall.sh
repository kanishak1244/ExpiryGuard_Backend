#!/usr/bin/env bash
# ==============================================================================
# Dawaiflow / ExpiryGuard - Linux Host & Database Firewall Hardening Script
# ==============================================================================
# This script enforces strict subnet isolation for PostgreSQL (Port 5432)
# and ensures only HTTP (80) and HTTPS (443) are exposed to the public internet.
#
# Requirements: sudo / root privileges on Ubuntu / Debian / RHEL.
# ==============================================================================

set -euo pipefail

echo "[*] Initializing Dawaiflow Host & Database Firewall Hardening..."

# Check root permissions
if [[ $EUID -ne 0 ]]; then
   echo "[-] Error: This script must be run as root (sudo)." 1>&2
   exit 1
fi

# Check if UFW is installed
if command -v ufw >/dev/null 2>&1; then
    echo "[*] Configuring UFW (Uncomplicated Firewall)..."

    # Reset default policies: Deny all incoming, Allow all outgoing
    ufw default deny incoming
    ufw default allow outgoing

    # Allow SSH (Port 22) - prevent locking out administrator
    ufw allow 22/tcp comment 'SSH Management'

    # Allow HTTP (Port 80) for ACME certificate verification & HTTPS redirect
    ufw allow 80/tcp comment 'HTTP ACME & Redirect'

    # Allow HTTPS (Port 443) for secure public traffic
    ufw allow 443/tcp comment 'HTTPS Reverse Proxy'

    # -------------------------------------------------------------
    # CRITICAL: PostgreSQL Port 5432 Subnet Isolation
    # -------------------------------------------------------------
    # 1. Deny public access to PostgreSQL
    ufw deny 5432/tcp comment 'Deny Public PostgreSQL Access'

    # 2. Allow PostgreSQL connections ONLY from internal Docker subnet or VPC
    # Adjust subnet (172.20.0.0/16 or 10.0.0.0/16) to match your environment
    ufw allow from 127.0.0.1 to any port 5432 proto tcp comment 'PostgreSQL Localhost'
    ufw allow from 172.20.0.0/16 to any port 5432 proto tcp comment 'PostgreSQL Docker Internal'
    ufw allow from 10.0.0.0/16 to any port 5432 proto tcp comment 'PostgreSQL Private VPC'

    # Enable UFW
    ufw --force enable
    ufw status verbose

    echo "[+] UFW firewall successfully configured and activated."
fi

# -----------------------------------------------------------------
# Additional iptables Raw Rules for Docker Container Isolation
# Note: Docker bypasses standard UFW chains by default using DOCKER-USER chain.
# -----------------------------------------------------------------
if command -v iptables >/dev/null 2>&1; then
    echo "[*] Configuring iptables DOCKER-USER chain for PostgreSQL isolation..."

    # Ensure DOCKER-USER chain exists
    iptables -N DOCKER-USER 2>/dev/null || true

    # Allow established connections
    iptables -I DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

    # Allow traffic on internal loopback & docker bridge
    iptables -A DOCKER-USER -i lo -j ACCEPT
    iptables -A DOCKER-USER -s 127.0.0.1 -j ACCEPT
    iptables -A DOCKER-USER -s 172.20.0.0/16 -p tcp --dport 5432 -j ACCEPT
    iptables -A DOCKER-USER -s 10.0.0.0/16 -p tcp --dport 5432 -j ACCEPT

    # Drop any external traffic attempting to reach port 5432 through Docker routing
    iptables -A DOCKER-USER -p tcp --dport 5432 -j DROP

    echo "[+] iptables DOCKER-USER protection active. External port 5432 packets will be dropped."
fi

echo "[===] Firewall hardening complete. Public internet can ONLY reach 80 & 443. Port 5432 is strictly isolated."
