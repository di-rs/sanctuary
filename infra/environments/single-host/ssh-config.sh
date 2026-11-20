#!/usr/bin/env bash
# Write the pinned production SSH identity into the caller's private temporary directory.
set -euo pipefail
umask 077
directory=$1
host=${2:-${DEPLOY_HOST:-}}
[[ $host =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+$ ]]
# Setup already wrote its Pulumi key and known_hosts here.
if (( $# == 1 )); then
    printf '%s\n' "$DEPLOY_SSH_KEY" > "$directory/key"
    printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$directory/known_hosts"
fi
cat > "$directory/config" <<SSH
Host deployment
  HostName $host
  User root
  IdentityFile $directory/key
  IdentitiesOnly yes
  UserKnownHostsFile $directory/known_hosts
  StrictHostKeyChecking yes
  BatchMode yes
  ConnectTimeout 15
  ServerAliveInterval 30
  ServerAliveCountMax 6
SSH
