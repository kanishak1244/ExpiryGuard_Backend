#!/usr/bin/env bash
# One-time setup of a fresh Oracle Cloud Ubuntu VM (ARM, Always Free) for the DawaiFlow backend.
# Run on the VM:  bash setup_server.sh
# Installs Docker, opens ports 80/443 in the VM's own firewall, and creates the app folder.
set -euo pipefail

echo "== Installing Docker =="
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "== Opening ports 80 and 443 in the VM firewall =="
# Oracle's Ubuntu images block incoming traffic with iptables rules; allow web traffic before the final REJECT.
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save

echo "== Creating app folder =="
sudo mkdir -p /opt/dawaiflow
sudo chown "$USER":"$USER" /opt/dawaiflow

echo "Done. Next: from your PC run deploy\\oracle\\push_from_pc.ps1"
