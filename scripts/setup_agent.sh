#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y openjdk-21-jdk mysql-client python3-pip curl apt-transport-https ca-certificates gnupg

if ! command -v gcloud >/dev/null 2>&1; then
  curl -sS https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y google-cloud-cli
fi

if ! id jenkins >/dev/null 2>&1; then
  sudo useradd -m -s /bin/bash jenkins
fi

sudo -u jenkins mkdir -p /home/jenkins/.local/bin
sudo -u jenkins python3 -m pip install --user --upgrade pip
sudo -u jenkins python3 -m pip install --user google-cloud-storage google-cloud-bigquery pymysql pandas

sudo mkdir -p /home/jenkins/.ssh
sudo chown -R jenkins:jenkins /home/jenkins/.ssh
sudo chmod 700 /home/jenkins/.ssh
sudo touch /home/jenkins/.ssh/authorized_keys
sudo chown jenkins:jenkins /home/jenkins/.ssh/authorized_keys
sudo chmod 600 /home/jenkins/.ssh/authorized_keys

if ! grep -q '.local/bin' /home/jenkins/.bashrc 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' | sudo tee -a /home/jenkins/.bashrc >/dev/null
fi

echo "Agent setup complete"
