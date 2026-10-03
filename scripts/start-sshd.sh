#!/bin/bash
set -euo pipefail

CONFIG=/opt/y700/workspaces/y700-agent/config/sshd_config
PIDFILE=/run/sshd-y700.pid
LOG=/opt/y700/runtime/sshd.log
AUTH_KEYS=/root/.ssh/authorized_keys

mkdir -p /run/sshd /root/.ssh /opt/y700/runtime
chmod 700 /root/.ssh
if [ -e "$AUTH_KEYS" ]; then
  chmod 600 "$AUTH_KEYS"
fi

if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "SSHD_ALREADY_RUNNING pid=$pid"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

/usr/sbin/sshd -t -f "$CONFIG"
/usr/sbin/sshd -f "$CONFIG" -E "$LOG"

pid="$(cat "$PIDFILE")"
echo "SSHD_STARTED pid=$pid port=2222"
if [ ! -s "$AUTH_KEYS" ]; then
  echo "SSHD_AUTH_KEY_PENDING: add the phone Termux public key to $AUTH_KEYS"
fi
