#!/usr/bin/env bash
# Install gVisor on the Ubuntu runner for the native lifecycle suites.
set -e

sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg
curl --fail --silent --show-error --location --max-time 60 https://gvisor.dev/archive.key \
    | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
printf '%s\n' 'deb [arch=amd64 signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main' \
    | sudo tee /etc/apt/sources.list.d/gvisor.list >/dev/null
sudo apt-get update
sudo apt-get install -y runsc
sudo runsc install -- --platform=systrap --fdlimit=4096
sudo systemctl restart docker
runsc --version
