#!/bin/bash
set -euo pipefail

PIDFILE=/run/sshd-y700.pid
AUTH_KEYS=/root/.ssh/authorized_keys

echo "Y700 SSH"
echo "---------"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "server: RUNNING"
else
  echo "server: STOPPED"
fi

echo "port: 2222"
ip -4 -brief addr show wlan0 2>/dev/null || true
ip4="$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
if [ -n "${ip4:-}" ]; then
  echo "connect: ssh -p 2222 root@$ip4"
else
  echo "connect: wlan0 has no IPv4 address"
fi

if [ -s "$AUTH_KEYS" ]; then
  echo "authorized_keys: PRESENT"
  ssh-keygen -lf "$AUTH_KEYS" 2>/dev/null || true
else
  echo "authorized_keys: MISSING"
fi
