#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
local_stat="$(cat /proc/1/stat)"
host_stat="$(bash "$root/bridge/root-exec.sh" "cat /proc/1/stat")"
python3 - "$local_stat" "$host_stat" <<'PY'
import json, sys
left, right = sys.argv[1], sys.argv[2]
def parse(row):
    fields = row[row.rfind(")") + 2:].split()
    return {"state": fields[0], "start_ticks": int(fields[19])}
a, b = parse(left), parse(right)
ok = a == b
print(json.dumps({
    "check": "proc-visibility",
    "status": "PASS" if ok else "FAIL",
    "chroot_pid1": a,
    "android_host_pid1": b,
    "same_kernel_identity": ok,
    "required_classifier_states": ["MATCHING","DEAD","PID_REUSED","STOPPED","ZOMBIE","HUNG_OR_UNKNOWN","UNREADABLE"],
}, sort_keys=True, separators=(",", ":")))
raise SystemExit(0 if ok else 1)
PY
