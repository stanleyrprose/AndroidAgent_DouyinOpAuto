#!/system/bin/sh
# Y700 Bridge v2 Android-host executor.
#
# Filesystem state is authoritative. v2 jobs are committed by atomic
# .staging -> active rename from the Debian/chroot client. This executor scans
# active only, keeps v1 direct-job compatibility, never blindly replays an
# ambiguous privileged command, and never force-kills generic root_exec.
umask 0077

AGENT_ROOT="$Y700_AGENT_ROOT"
[ -n "$AGENT_ROOT" ] || AGENT_ROOT=/data/local/y700-agent
JOBS="$Y700_BRIDGE_HOST_JOBS"
[ -n "$JOBS" ] || JOBS="$AGENT_ROOT/jobs"
RUNTIME="$Y700_RUNTIME_HOST"
[ -n "$RUNTIME" ] || RUNTIME="$AGENT_ROOT/runtime"
TOYBOX="$Y700_TOYBOX"
[ -n "$TOYBOX" ] || TOYBOX=/system/bin/toybox
HOST_SHELL="$Y700_HOST_SHELL"
[ -n "$HOST_SHELL" ] || HOST_SHELL=/system/bin/sh
AWK="$Y700_AWK"
[ -n "$AWK" ] || AWK=/system/bin/awk
POLL_SEC="$Y700_BRIDGE_POLL_SEC"
[ -n "$POLL_SEC" ] || POLL_SEC=0.25
HEARTBEAT_MS="$Y700_BRIDGE_HEARTBEAT_MS"
[ -n "$HEARTBEAT_MS" ] || HEARTBEAT_MS=2000
LEASE_MS="$Y700_BRIDGE_LEASE_MS"
[ -n "$LEASE_MS" ] || LEASE_MS=15000
RECONCILE_MS="$Y700_BRIDGE_RECONCILE_MS"
[ -n "$RECONCILE_MS" ] || RECONCILE_MS=30000
REQUEST_MAX_BYTES="$Y700_BRIDGE_REQUEST_MAX_BYTES"
[ -n "$REQUEST_MAX_BYTES" ] || REQUEST_MAX_BYTES=262144
ONESHOT="$Y700_BRIDGE_ONESHOT"
[ -n "$ONESHOT" ] || ONESHOT=0
TEST_AFTER_CLAIM_SEC="$Y700_BRIDGE_TEST_AFTER_CLAIM_SEC"
TEST_AFTER_RESULT_SEC="$Y700_BRIDGE_TEST_AFTER_RESULT_SEC"
TEST_MODE="$Y700_BRIDGE_TEST_MODE"
[ -n "$TEST_MODE" ] || TEST_MODE=0
TEST_FAILPOINT="$Y700_BRIDGE_TEST_FAILPOINT"

STAGING="$JOBS/.staging"
ACTIVE="$JOBS/active"
ARCHIVE="$JOBS/archive"
CONTROL="$JOBS/control"
LOG="$RUNTIME/host-executor.log"

SELF_PID=$$
BOOT_ID="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || printf unknown)"
EXECUTOR_ID="host-$BOOT_ID-$SELF_PID"
STARTED_AT=""
LAST_HEARTBEAT_MS=0
LAST_RECONCILE_MS=0
LAST_METRICS_MS=0
RESTART_COUNT=1
LAST_SUBMIT_TO_CLAIM_MS=0
LAST_CLAIM_TO_START_MS=0
LAST_EXECUTION_MS=0
LAST_RESULT_TO_ARCHIVE_MS=0
LAST_ACTIVE_SCAN_MS=0
LAST_ARCHIVE_DIR=""
LIVE_ORPHAN_PID=""
LIVE_ORPHAN_START=""
LIVE_ORPHAN_JOB=""
LIVE_ORPHAN_DIR=""

mkdir700() {
  "$TOYBOX" mkdir -p "$1"
  "$TOYBOX" chmod 700 "$1" 2>/dev/null || true
}

now_iso() {
  "$TOYBOX" date '+%Y-%m-%dT%H:%M:%S%z'
}

uptime_ms() {
  "$AWK" '{printf "%.0f\n",$1*1000}' /proc/uptime
}

atomic_text() {
  path="$1"
  value="$2"
  parent="$("$TOYBOX" dirname "$path")"
  tmp="$path.tmp.$$"
  mkdir700 "$parent"
  printf '%s\n' "$value" >"$tmp" || return 1
  "$TOYBOX" chmod 600 "$tmp" 2>/dev/null || true
  "$TOYBOX" fsync "$tmp" 2>/dev/null || "$TOYBOX" sync
  "$TOYBOX" mv "$tmp" "$path" || return 1
  "$TOYBOX" fsync "$parent" 2>/dev/null || "$TOYBOX" sync
}

append_log() {
  printf '%s %s\n' "$(now_iso)" "$*" >>"$LOG"
  "$TOYBOX" chmod 600 "$LOG" 2>/dev/null || true
}

journal() {
  dir="$1"
  event="$2"
  detail="$3"
  path="$dir/journal.jsonl"
  if [ -n "$detail" ]; then
    printf '{"timestamp":"%s","event":"%s","detail":"%s"}\n' \
      "$(now_iso)" "$event" "$detail" >>"$path"
  else
    printf '{"timestamp":"%s","event":"%s"}\n' "$(now_iso)" "$event" >>"$path"
  fi
  "$TOYBOX" chmod 600 "$path" 2>/dev/null || true
  "$TOYBOX" fsync "$path" 2>/dev/null || true
}

test_failpoint() {
  point="$1"
  dir="$2"
  [ "$TEST_MODE" = 1 ] || return 0
  [ "$TEST_FAILPOINT" = "$point" ] || return 0
  [ -z "$dir" ] || journal "$dir" TEST_FAILPOINT "$point"
  append_log "test_failpoint point=$point"
  exit 86
}

json_string() {
  file="$1"
  key="$2"
  "$TOYBOX" sed -n \
    "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" \
    "$file" 2>/dev/null | "$TOYBOX" head -1
}

json_int() {
  file="$1"
  key="$2"
  "$TOYBOX" sed -n \
    "s/.*\"$key\"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p" \
    "$file" 2>/dev/null | "$TOYBOX" head -1
}

request_sha256() {
  file="$1"
  set -- $("$TOYBOX" sha256sum "$file" 2>/dev/null)
  printf '%s\n' "$1"
}

proc_start_ticks() {
  pid="$1"
  [ -r "/proc/$pid/stat" ] || return 1
  "$AWK" '{print $22}' "/proc/$pid/stat" 2>/dev/null
}

proc_state() {
  pid="$1"
  [ -r "/proc/$pid/stat" ] || return 1
  "$AWK" '{print $3}' "/proc/$pid/stat" 2>/dev/null
}

process_identity_matches() {
  pid="$1"
  expected="$2"
  [ -n "$pid" ] || return 1
  [ -n "$expected" ] || return 2
  [ -r "/proc/$pid/stat" ] || return 1
  actual="$(proc_start_ticks "$pid" 2>/dev/null || true)"
  [ -n "$actual" ] || return 2
  [ "$actual" = "$expected" ] || return 1
  pstate="$(proc_state "$pid" 2>/dev/null || true)"
  [ "$pstate" != Z ] || return 1
  return 0
}

job_name() {
  "$TOYBOX" basename "$1"
}

safe_v2_job_dir() {
  dir="$1"
  [ -d "$dir" ] || return 1
  [ ! -L "$dir" ] || return 1
  job="$(job_name "$dir")"
  case "$job" in
    ''|.|..|active|archive|control|.staging|*[!A-Za-z0-9._-]*) return 1 ;;
  esac
  resolved="$("$TOYBOX" realpath "$dir" 2>/dev/null || true)"
  active_resolved="$("$TOYBOX" realpath "$ACTIVE" 2>/dev/null || true)"
  [ -n "$resolved" ] && [ -n "$active_resolved" ] || return 1
  parent="$("$TOYBOX" dirname "$resolved")"
  [ "$parent" = "$active_resolved" ] || return 1
  return 0
}

write_protocol() {
  atomic_text "$CONTROL/protocol.json" \
    '{"bridge":"y700-bridge","supported_protocol_versions":[1,2],"preferred_protocol_version":2,"transport":"filesystem"}'
}

write_executor_heartbeat() {
  now_ms="$(uptime_ms)"
  if [ "$LAST_HEARTBEAT_MS" -ne 0 ] &&
     [ $((now_ms - LAST_HEARTBEAT_MS)) -lt "$HEARTBEAT_MS" ]; then
    return 0
  fi
  LAST_HEARTBEAT_MS="$now_ms"
  blocked=false
  [ -z "$LIVE_ORPHAN_PID" ] || blocked=true
  ts="$(now_iso)"
  payload="$(printf '{"executor_id":"%s","pid":%s,"started_at":"%s","heartbeat_at":"%s","heartbeat_interval_ms":%s,"lease_timeout_ms":%s,"supported_protocol_versions":[1,2],"dispatch_blocked_by_live_orphan":%s}' \
    "$EXECUTOR_ID" "$SELF_PID" "$STARTED_AT" "$ts" "$HEARTBEAT_MS" "$LEASE_MS" "$blocked")"
  atomic_text "$CONTROL/executor.json" "$payload"
}

write_state_v1() {
  dir="$1"
  value="$2"
  atomic_text "$dir/state.json" "$(printf '{"status":"%s"}' "$value")"
}

write_state_v2() {
  dir="$1"
  value="$2"
  cancel_flag="$3"
  [ -n "$cancel_flag" ] || cancel_flag=false
  job="$(job_name "$dir")"
  ts="$(now_iso)"
  payload="$(printf '{"protocol_version":2,"job_id":"%s","state":"%s","updated_at":"%s","attempt":1,"cancel_requested":%s}' \
    "$job" "$value" "$ts" "$cancel_flag")"
  atomic_text "$dir/state.json" "$payload"
}

write_owner_v2() {
  dir="$1"
  req_sha="$2"
  claimed_at="$3"
  child_pid="$4"
  pgid="$5"
  start_ticks="$6"
  command_started="$7"
  session_id="$(job_name "$dir")"
  if [ -n "$child_pid" ]; then
    payload="$(printf '{"executor_id":"%s","executor_pid":%s,"child_pid":%s,"pgid":%s,"process_session_id":"%s","process_start_ticks":"%s","claimed_at":"%s","command_started_at":"%s","request_sha256":"%s"}' \
      "$EXECUTOR_ID" "$SELF_PID" "$child_pid" "$pgid" "$session_id" \
      "$start_ticks" "$claimed_at" "$command_started" "$req_sha")"
  else
    payload="$(printf '{"executor_id":"%s","executor_pid":%s,"process_session_id":"%s","claimed_at":"%s","request_sha256":"%s"}' \
      "$EXECUTOR_ID" "$SELF_PID" "$session_id" "$claimed_at" "$req_sha")"
  fi
  atomic_text "$dir/claim/owner.json" "$payload"
}

write_job_heartbeat() {
  dir="$1"
  child_pid="$2"
  value="$3"
  ts="$(now_iso)"
  payload="$(printf '{"protocol_version":2,"job_id":"%s","state":"%s","child_pid":%s,"updated_at":"%s"}' \
    "$(job_name "$dir")" "$value" "$child_pid" "$ts")"
  atomic_text "$dir/heartbeat.json" "$payload"
}

archive_class() {
  case "$1" in
    SUCCEEDED) printf succeeded ;;
    FAILED) printf failed ;;
    CANCELLED) printf cancelled ;;
    RECONCILE_REQUIRED) printf reconcile_required ;;
    *) printf failed ;;
  esac
}

archive_v2() {
  dir="$1"
  terminal="$2"
  class="$(archive_class "$terminal")"
  job="$(job_name "$dir")"
  dest="$ARCHIVE/$class/$job"
  start_ms="$(uptime_ms)"
  if [ -e "$dest" ]; then
    append_log "archive_conflict job=$job dest=$dest"
    LAST_ARCHIVE_DIR="$dir"
    return 1
  fi
  "$TOYBOX" mv "$dir" "$dest" || return 1
  "$TOYBOX" fsync "$ARCHIVE/$class" 2>/dev/null || "$TOYBOX" sync
  LAST_RESULT_TO_ARCHIVE_MS=$(( $(uptime_ms) - start_ms ))
  LAST_ARCHIVE_DIR="$dest"
  return 0
}

finish_v2() {
  dir="$1"
  terminal="$2"
  rc="$3"
  reason="$4"
  child_alive="$5"
  [ -n "$child_alive" ] || child_alive=false
  cancel_flag=false
  [ -f "$dir/cancel.json" ] && cancel_flag=true
  write_state_v2 "$dir" "$terminal" "$cancel_flag"
  [ ! -f "$dir/stdout.log" ] ||
    "$TOYBOX" fsync "$dir/stdout.log" 2>/dev/null || true
  [ ! -f "$dir/stderr.log" ] ||
    "$TOYBOX" fsync "$dir/stderr.log" 2>/dev/null || true
  journal "$dir" TERMINAL_STATE_WRITTEN "$terminal"
  ts="$(now_iso)"
  payload="$(printf '{"protocol_version":2,"job_id":"%s","status":"%s","exit_code":%s,"reason":"%s","finished_at":"%s","child_alive":%s,"submit_to_claim_ms":%s,"claim_to_start_ms":%s,"execution_ms":%s}' \
    "$(job_name "$dir")" "$terminal" "$rc" "$reason" "$ts" "$child_alive" \
    "$LAST_SUBMIT_TO_CLAIM_MS" "$LAST_CLAIM_TO_START_MS" "$LAST_EXECUTION_MS")"
  # Completion marker is published last.
  atomic_text "$dir/result.json" "$payload"
  test_failpoint after_result_before_archive "$dir"
  if [ -n "$TEST_AFTER_RESULT_SEC" ]; then
    "$TOYBOX" sleep "$TEST_AFTER_RESULT_SEC"
  fi
  archive_v2 "$dir" "$terminal"
}

count_dirs() {
  path="$1"
  count=0
  for d in "$path"/*; do
    [ -d "$d" ] || continue
    [ ! -L "$d" ] || continue
    count=$((count + 1))
  done
  printf '%s\n' "$count"
}

count_v1_jobs() {
  count=0
  for req in "$JOBS"/*/request.json; do
    [ -f "$req" ] || continue
    count=$((count + 1))
  done
  printf '%s\n' "$count"
}

write_metrics() {
  active=0
  queued=0
  running=0
  cancelling=0
  cancel_requested=0
  for d in "$ACTIVE"/*; do
    [ -d "$d" ] || continue
    [ ! -L "$d" ] || continue
    active=$((active + 1))
    [ -f "$d/cancel.json" ] && cancel_requested=$((cancel_requested + 1))
    value="$(json_string "$d/state.json" state)"
    case "$value" in
      QUEUED|CLAIMED) queued=$((queued + 1)) ;;
      RUNNING) running=$((running + 1)) ;;
      CANCELLING) cancelling=$((cancelling + 1)) ;;
    esac
  done

  staging=0
  stale_staging=0
  now_epoch="$("$TOYBOX" date +%s)"
  for d in "$STAGING"/*; do
    [ -d "$d" ] || continue
    [ ! -L "$d" ] || continue
    staging=$((staging + 1))
    mtime="$("$TOYBOX" stat -c %Y "$d" 2>/dev/null || printf %s "$now_epoch")"
    [ $((now_epoch - mtime)) -lt 86400 ] ||
      stale_staging=$((stale_staging + 1))
  done

  cancelled="$(count_dirs "$ARCHIVE/cancelled")"
  reconcile_required="$(count_dirs "$ARCHIVE/reconcile_required")"
  orphaned=0
  [ -z "$LIVE_ORPHAN_PID" ] || orphaned=1
  v1_count="$(count_v1_jobs)"
  ts="$(now_iso)"
  payload="$(printf '{"active_job_count":%s,"queued_job_count":%s,"running_job_count":%s,"cancelling_job_count":%s,"orphaned_job_count":%s,"reconcile_required_count":%s,"cancel_requested_count":%s,"cancelled_count":%s,"staging_job_count":%s,"stale_staging_count":%s,"submit_to_claim_ms":%s,"claim_to_start_ms":%s,"execution_ms":%s,"result_to_archive_ms":%s,"active_scan_ms":%s,"executor_restart_count":%s,"protocol_v1_job_count":%s,"protocol_v2_job_count":%s,"updated_at":"%s"}' \
    "$active" "$queued" "$running" "$cancelling" "$orphaned" \
    "$reconcile_required" "$cancel_requested" "$cancelled" "$staging" \
    "$stale_staging" "$LAST_SUBMIT_TO_CLAIM_MS" "$LAST_CLAIM_TO_START_MS" \
    "$LAST_EXECUTION_MS" "$LAST_RESULT_TO_ARCHIVE_MS" "$LAST_ACTIVE_SCAN_MS" \
    "$RESTART_COUNT" "$v1_count" "$active" "$ts")"
  atomic_text "$CONTROL/metrics.json" "$payload"
}

load_restart_count() {
  file="$RUNTIME/host-executor.restart-count"
  old=0
  [ ! -s "$file" ] || old="$(cat "$file" 2>/dev/null || printf 0)"
  case "$old" in ''|*[!0-9]*) old=0 ;; esac
  RESTART_COUNT=$((old + 1))
  atomic_text "$file" "$RESTART_COUNT"
}

set_live_orphan() {
  LIVE_ORPHAN_PID="$1"
  LIVE_ORPHAN_START="$2"
  LIVE_ORPHAN_JOB="$3"
  LIVE_ORPHAN_DIR="$4"
  ts="$(now_iso)"
  payload="$(printf '{"job_id":"%s","child_pid":%s,"process_start_ticks":"%s","archive_path":"%s","updated_at":"%s"}' \
    "$LIVE_ORPHAN_JOB" "$LIVE_ORPHAN_PID" "$LIVE_ORPHAN_START" \
    "$LIVE_ORPHAN_DIR" "$ts")"
  atomic_text "$CONTROL/live-orphan.json" "$payload"
}

recover_live_orphan_control() {
  record="$CONTROL/live-orphan.json"
  [ -f "$record" ] || return 1
  pid="$(json_int "$record" child_pid)"
  start="$(json_string "$record" process_start_ticks)"
  job="$(json_string "$record" job_id)"
  archive_path="$(json_string "$record" archive_path)"
  if [ -z "$pid" ] || [ -z "$start" ] || [ -z "$job" ]; then
    append_log "live_orphan_control_corrupt dispatch_blocked"
    LIVE_ORPHAN_PID=CORRUPT
    LIVE_ORPHAN_JOB=unknown
    return 0
  fi
  if process_identity_matches "$pid" "$start"; then
    LIVE_ORPHAN_PID="$pid"
    LIVE_ORPHAN_START="$start"
    LIVE_ORPHAN_JOB="$job"
    LIVE_ORPHAN_DIR="$archive_path"
    append_log "live_orphan_recovered job=$job pid=$pid"
    return 0
  fi
  "$TOYBOX" rm -f "$record"
  "$TOYBOX" fsync "$CONTROL" 2>/dev/null || true
  return 1
}

check_live_orphan_block() {
  [ -n "$LIVE_ORPHAN_PID" ] || return 1
  if [ "$LIVE_ORPHAN_PID" = CORRUPT ]; then
    write_executor_heartbeat
    return 0
  fi
  if process_identity_matches "$LIVE_ORPHAN_PID" "$LIVE_ORPHAN_START"; then
    write_executor_heartbeat
    return 0
  fi
  append_log "live_orphan_cleared job=$LIVE_ORPHAN_JOB pid=$LIVE_ORPHAN_PID"
  if [ -n "$LIVE_ORPHAN_DIR" ] && [ -d "$LIVE_ORPHAN_DIR" ]; then
    journal "$LIVE_ORPHAN_DIR" ORPHAN_PROCESS_EXITED "$LIVE_ORPHAN_PID"
  fi
  "$TOYBOX" rm -f "$CONTROL/live-orphan.json"
  "$TOYBOX" fsync "$CONTROL" 2>/dev/null || true
  LIVE_ORPHAN_PID=""
  LIVE_ORPHAN_START=""
  LIVE_ORPHAN_JOB=""
  LIVE_ORPHAN_DIR=""
  return 1
}

reset_metrics_for_job() {
  LAST_SUBMIT_TO_CLAIM_MS=0
  LAST_CLAIM_TO_START_MS=0
  LAST_EXECUTION_MS=0
  LAST_RESULT_TO_ARCHIVE_MS=0
}

reconcile_one_v2() {
  dir="$1"
  [ -d "$dir" ] || return 0
  if ! safe_v2_job_dir "$dir"; then
    append_log "unsafe_v2_job_dir_rejected path=$dir"
    return 0
  fi

  if [ -f "$dir/result.json" ]; then
    terminal="$(json_string "$dir/result.json" status)"
    case "$terminal" in
      SUCCEEDED|FAILED|CANCELLED|RECONCILE_REQUIRED)
        archive_v2 "$dir" "$terminal" || true
        return 0
        ;;
    esac
  fi

  value="$(json_string "$dir/state.json" state)"
  if [ -z "$value" ]; then
    reset_metrics_for_job
    finish_v2 "$dir" RECONCILE_REQUIRED 125 MALFORMED_STATE false
    return 0
  fi

  if [ ! -d "$dir/claim" ]; then
    if [ -f "$dir/cancel.json" ]; then
      reset_metrics_for_job
      journal "$dir" CANCEL_OBSERVED BEFORE_CLAIM
      finish_v2 "$dir" CANCELLED 130 CANCELLED_BEFORE_CLAIM false
    fi
    return 0
  fi

  owner="$dir/claim/owner.json"
  child="$(json_int "$owner" child_pid)"
  start="$(json_string "$owner" process_start_ticks)"
  journal "$dir" ORPHAN_DETECTED "$value"

  if [ -n "$child" ] && [ -n "$start" ] &&
     process_identity_matches "$child" "$start"; then
    job="$(job_name "$dir")"
    append_log "active_orphan job=$job pid=$child"
    reset_metrics_for_job
    finish_v2 "$dir" RECONCILE_REQUIRED 125 \
      EXECUTOR_LOST_CHILD_STILL_RUNNING true
    set_live_orphan "$child" "$start" "$job" "$LAST_ARCHIVE_DIR"
    return 0
  fi

  if [ -n "$child" ] && [ -z "$start" ] && [ -r "/proc/$child/stat" ]; then
    journal "$dir" PROCESS_IDENTITY_UNCERTAIN PID_ONLY
    reason=PROCESS_IDENTITY_UNCERTAIN
  elif [ -n "$child" ] && [ -r "/proc/$child/stat" ]; then
    journal "$dir" PROCESS_IDENTITY_MISMATCH PID_REUSED_OR_DIFFERENT_PROCESS
    reason=PROCESS_IDENTITY_MISMATCH
  elif [ -z "$child" ]; then
    # Claim exists but no child was ever persisted: side-effect start is not
    # proven. Still do not replay; close deterministically as failed.
    reason=EXECUTOR_LOST_BEFORE_CHILD_START
    reset_metrics_for_job
    finish_v2 "$dir" FAILED 125 "$reason" false
    return 0
  else
    reason=STALE_CLAIM_EXECUTOR_RESTART
  fi

  reset_metrics_for_job
  finish_v2 "$dir" RECONCILE_REQUIRED 125 "$reason" false
}

reconcile_v2() {
  target="$1"
  [ -n "$target" ] || target=all
  if [ "$target" != all ]; then
    case "$target" in
      ''|.|..|active|archive|control|.staging|*[!A-Za-z0-9._-]*) return 1 ;;
    esac
    reconcile_one_v2 "$ACTIVE/$target"
    return 0
  fi
  for dir in "$ACTIVE"/*; do
    [ -d "$dir" ] || continue
    reconcile_one_v2 "$dir"
  done
}

handle_reconcile_request() {
  req="$CONTROL/reconcile.request"
  [ -f "$req" ] || return 0
  target="$(json_string "$req" target)"
  if [ -z "$target" ]; then
    append_log "malformed reconcile.request ignored"
  else
    reconcile_v2 "$target"
  fi
  "$TOYBOX" rm -f "$req"
  "$TOYBOX" fsync "$CONTROL" 2>/dev/null || true
}

execute_v2() {
  dir="$1"
  if ! safe_v2_job_dir "$dir"; then
    append_log "unsafe_v2_job_dir_rejected path=$dir"
    return 0
  fi
  req="$dir/request.json"
  [ -f "$req" ] || return 0
  if [ -L "$req" ]; then
    reset_metrics_for_job
    finish_v2 "$dir" RECONCILE_REQUIRED 125 REQUEST_SYMLINK_REJECTED false
    return 0
  fi
  [ ! -f "$dir/result.json" ] || {
    reconcile_one_v2 "$dir"
    return 0
  }

  reset_metrics_for_job
  size="$("$TOYBOX" stat -c %s "$req" 2>/dev/null || printf 0)"
  case "$size" in ''|*[!0-9]*) size=0 ;; esac
  if [ "$size" -le 0 ] || [ "$size" -gt "$REQUEST_MAX_BYTES" ]; then
    finish_v2 "$dir" FAILED 2 JOB_PAYLOAD_TOO_LARGE false
    return 0
  fi

  proto="$(json_int "$req" protocol_version)"
  action="$(json_string "$req" action)"
  request_job="$(json_string "$req" job_id)"
  replay="$(json_string "$req" replay)"
  timeout_ms="$(json_int "$req" timeout_ms)"
  created_mono="$(json_int "$req" created_monotonic_ms)"
  value="$(json_string "$dir/state.json" state)"
  job="$(job_name "$dir")"

  if [ "$proto" != 2 ] || [ "$request_job" != "$job" ] ||
     [ "$action" != root_exec ]; then
    finish_v2 "$dir" FAILED 2 JOB_PAYLOAD_INVALID false
    return 0
  fi
  # Generic root_exec cannot self-declare idempotence.
  if [ "$replay" != NEVER ]; then
    finish_v2 "$dir" FAILED 2 REPLAY_POLICY_NOT_ALLOWED false
    return 0
  fi
  case "$timeout_ms" in ''|*[!0-9]*) timeout_ms=90000 ;; esac
  if [ "$timeout_ms" -lt 1000 ] || [ "$timeout_ms" -gt 3600000 ]; then
    finish_v2 "$dir" FAILED 2 TIMEOUT_OUT_OF_RANGE false
    return 0
  fi
  if [ "$value" != QUEUED ]; then
    if [ -d "$dir/claim" ]; then
      reconcile_one_v2 "$dir"
    else
      finish_v2 "$dir" RECONCILE_REQUIRED 125 INVALID_PRECLAIM_STATE false
    fi
    return 0
  fi

  if [ -f "$dir/cancel.json" ]; then
    journal "$dir" CANCEL_OBSERVED BEFORE_CLAIM
    finish_v2 "$dir" CANCELLED 130 CANCELLED_BEFORE_CLAIM false
    return 0
  fi

  "$TOYBOX" mkdir "$dir/claim" 2>/dev/null || return 0
  "$TOYBOX" chmod 700 "$dir/claim" 2>/dev/null || true
  claim_ms="$(uptime_ms)"
  claim_at="$(now_iso)"
  if [ -n "$created_mono" ] && [ "$claim_ms" -ge "$created_mono" ]; then
    LAST_SUBMIT_TO_CLAIM_MS=$((claim_ms - created_mono))
  fi

  sha="$(request_sha256 "$req")"
  if [ -z "$sha" ]; then
    finish_v2 "$dir" RECONCILE_REQUIRED 125 REQUEST_HASH_FAILED false
    return 0
  fi
  write_owner_v2 "$dir" "$sha" "$claim_at" "" "" "" ""
  write_state_v2 "$dir" CLAIMED false
  journal "$dir" CLAIM_ACQUIRED "$EXECUTOR_ID"
  test_failpoint after_claim_before_start "$dir"
  if [ -n "$TEST_AFTER_CLAIM_SEC" ]; then
    journal "$dir" TEST_HOOK_AFTER_CLAIM "$TEST_AFTER_CLAIM_SEC"
    "$TOYBOX" sleep "$TEST_AFTER_CLAIM_SEC"
  fi

  if [ -f "$dir/cancel.json" ]; then
    journal "$dir" CANCEL_OBSERVED BEFORE_START
    finish_v2 "$dir" CANCELLED 130 CANCELLED_BEFORE_START false
    return 0
  fi

  b64="$(json_string "$req" command_b64)"
  if [ -z "$b64" ]; then
    finish_v2 "$dir" FAILED 2 JOB_PAYLOAD_INVALID false
    return 0
  fi
  printf '%s' "$b64" | "$TOYBOX" base64 -d \
    >"$dir/command.sh" 2>"$dir/stderr.log"
  decode_rc=$?
  if [ "$decode_rc" -ne 0 ]; then
    : >"$dir/stdout.log"
    finish_v2 "$dir" FAILED 2 COMMAND_DECODE_FAILED false
    return 0
  fi
  "$TOYBOX" chmod 700 "$dir/command.sh"
  "$TOYBOX" fsync "$dir/command.sh" 2>/dev/null || true

  sha2="$(request_sha256 "$req")"
  if [ "$sha2" != "$sha" ]; then
    finish_v2 "$dir" RECONCILE_REQUIRED 125 REQUEST_MUTATED_AFTER_CLAIM false
    return 0
  fi
  if [ -f "$dir/cancel.json" ]; then
    journal "$dir" CANCEL_OBSERVED BEFORE_SIDE_EFFECT
    finish_v2 "$dir" CANCELLED 130 CANCELLED_BEFORE_SIDE_EFFECT false
    return 0
  fi

  write_state_v2 "$dir" RUNNING false
  journal "$dir" STATE_RUNNING root_exec
  command_started="$(now_iso)"
  start_ms="$(uptime_ms)"
  LAST_CLAIM_TO_START_MS=$((start_ms - claim_ms))

  "$TOYBOX" setsid "$HOST_SHELL" "$dir/command.sh" \
    >"$dir/stdout.log" 2>"$dir/stderr.log" &
  child=$!
  pgid="$child"
  start_ticks=""
  i=0
  while [ "$i" -lt 20 ]; do
    start_ticks="$(proc_start_ticks "$child" 2>/dev/null || true)"
    [ -n "$start_ticks" ] && break
    "$TOYBOX" usleep 10000 2>/dev/null || "$TOYBOX" sleep 0.01
    i=$((i + 1))
  done
  [ -n "$start_ticks" ] ||
    journal "$dir" PROCESS_IDENTITY_UNCERTAIN START_TICKS_UNAVAILABLE
  write_owner_v2 "$dir" "$sha" "$claim_at" "$child" "$pgid" \
    "$start_ticks" "$command_started"
  write_job_heartbeat "$dir" "$child" RUNNING
  test_failpoint after_child_start "$dir"

  cancel_seen=0
  timed_out=0
  last_job_hb="$start_ms"
  while true; do
    child_state="$(proc_state "$child" 2>/dev/null || true)"
    [ -n "$child_state" ] || break
    [ "$child_state" != Z ] || break

    now_ms="$(uptime_ms)"
    write_executor_heartbeat
    if [ $((now_ms - last_job_hb)) -ge "$HEARTBEAT_MS" ]; then
      hb_state=RUNNING
      [ "$cancel_seen" -eq 0 ] || hb_state=CANCELLING
      write_job_heartbeat "$dir" "$child" "$hb_state"
      last_job_hb="$now_ms"
    fi

    if [ "$cancel_seen" -eq 0 ] && [ -f "$dir/cancel.json" ]; then
      cancel_seen=1
      write_state_v2 "$dir" CANCELLING true
      journal "$dir" CANCEL_OBSERVED RUNNING_NON_PREEMPTIVE
    fi

    if [ $((now_ms - claim_ms)) -ge "$timeout_ms" ]; then
      timed_out=1
      break
    fi
    "$TOYBOX" sleep "$POLL_SEC"
  done

  if [ "$timed_out" -eq 1 ]; then
    LAST_EXECUTION_MS=$(( $(uptime_ms) - start_ms ))
    if [ "$cancel_seen" -eq 1 ]; then
      reason=CANCELLATION_INCOMPLETE_TIMEOUT
    else
      reason=EXECUTION_TIMEOUT_CHILD_STILL_RUNNING
    fi
    journal "$dir" CANCELLATION_INCOMPLETE_TIMEOUT "$reason"
    finish_v2 "$dir" RECONCILE_REQUIRED 125 "$reason" true
    archived="$LAST_ARCHIVE_DIR"
    if [ -n "$start_ticks" ]; then
      set_live_orphan "$child" "$start_ticks" "$job" "$archived"
      while check_live_orphan_block; do
        "$TOYBOX" sleep "$POLL_SEC"
      done
    fi
    wait "$child" 2>/dev/null || true
    append_log "timed_out_child_exited job=$job pid=$child"
    return 0
  fi

  wait "$child"
  rc=$?
  LAST_EXECUTION_MS=$(( $(uptime_ms) - start_ms ))

  sha3="$(request_sha256 "$req")"
  if [ "$sha3" != "$sha" ]; then
    journal "$dir" REQUEST_MUTATED_AFTER_CLAIM DURING_EXECUTION
    finish_v2 "$dir" RECONCILE_REQUIRED 125 \
      REQUEST_MUTATED_DURING_EXECUTION false
    return 0
  fi

  if [ "$rc" -eq 0 ]; then terminal=SUCCEEDED; else terminal=FAILED; fi
  if [ "$cancel_seen" -eq 1 ]; then
    reason=COMMAND_COMPLETED_AFTER_CANCEL_REQUEST
  else
    reason=COMMAND_COMPLETED
  fi
  finish_v2 "$dir" "$terminal" "$rc" "$reason" false
  append_log "v2 job=$job action=$action rc=$rc status=$terminal"
}

execute_v1() {
  req="$1"
  [ -f "$req" ] || return 0
  dir="$("$TOYBOX" dirname "$req")"
  [ -f "$dir/result.json" ] && return 0
  "$TOYBOX" mkdir "$dir/.claim" 2>/dev/null || return 0
  write_state_v1 "$dir" RUNNING

  action="$(json_string "$req" action)"
  rc=127
  case "$action" in
    root_exec)
      b64="$(json_string "$req" command_b64)"
      if [ -n "$b64" ]; then
        printf '%s' "$b64" | "$TOYBOX" base64 -d >"$dir/command.sh"
        "$TOYBOX" chmod 700 "$dir/command.sh"
        "$TOYBOX" setsid "$HOST_SHELL" "$dir/command.sh" \
          >"$dir/stdout.log" 2>"$dir/stderr.log" &
        child=$!
        while true; do
          child_state="$(proc_state "$child" 2>/dev/null || true)"
          [ -n "$child_state" ] || break
          [ "$child_state" != Z ] || break
          write_executor_heartbeat
          "$TOYBOX" sleep "$POLL_SEC"
        done
        wait "$child"
        rc=$?
      else
        printf '%s\n' "missing command_b64" >"$dir/stderr.log"
        : >"$dir/stdout.log"
        rc=2
      fi
      ;;
    *)
      : >"$dir/stdout.log"
      printf 'unsupported action: %s\n' "$action" >"$dir/stderr.log"
      rc=3
      ;;
  esac

  if [ "$rc" -eq 0 ]; then terminal=SUCCEEDED; else terminal=FAILED; fi
  write_state_v1 "$dir" "$terminal"
  atomic_text "$dir/result.json" \
    "$(printf '{"status":"%s","exit_code":%s}' "$terminal" "$rc")"
  append_log "v1 job=$(job_name "$dir") action=$action rc=$rc"
}

reconcile_stale_v1_startup() {
  for claim in "$JOBS"/*/.claim; do
    [ -d "$claim" ] || continue
    dir="$("$TOYBOX" dirname "$claim")"
    [ -f "$dir/result.json" ] && continue
    printf '%s\n' "executor restarted before result; command not replayed" \
      >"$dir/stderr.log"
    : >"$dir/stdout.log"
    write_state_v1 "$dir" FAILED
    atomic_text "$dir/result.json" \
      '{"status":"FAILED","exit_code":125,"reason":"STALE_CLAIM_AFTER_EXECUTOR_RESTART"}'
    append_log "stale_v1_claim job=$(job_name "$dir") marked_failed"
  done
}

init_layout() {
  mkdir700 "$JOBS"
  mkdir700 "$RUNTIME"
  mkdir700 "$STAGING"
  mkdir700 "$ACTIVE"
  mkdir700 "$ARCHIVE"
  mkdir700 "$ARCHIVE/succeeded"
  mkdir700 "$ARCHIVE/failed"
  mkdir700 "$ARCHIVE/cancelled"
  mkdir700 "$ARCHIVE/reconcile_required"
  mkdir700 "$CONTROL"
}

init_layout
STARTED_AT="$(now_iso)"
load_restart_count
write_protocol
recover_live_orphan_control || true
write_executor_heartbeat
append_log "host-executor v2 start pid=$SELF_PID executor_id=$EXECUTOR_ID"
reconcile_stale_v1_startup
reconcile_v2 all
write_metrics

while true; do
  write_executor_heartbeat

  if check_live_orphan_block; then
    [ "$ONESHOT" = 1 ] && exit 0
    "$TOYBOX" sleep "$POLL_SEC"
    continue
  fi

  now_ms="$(uptime_ms)"
  if [ $((now_ms - LAST_RECONCILE_MS)) -ge "$RECONCILE_MS" ]; then
    reconcile_v2 all
    handle_reconcile_request
    LAST_RECONCILE_MS="$now_ms"
  elif [ -f "$CONTROL/reconcile.request" ]; then
    handle_reconcile_request
  fi

  scan_start="$(uptime_ms)"
  for req in "$ACTIVE"/*/request.json; do
    [ -f "$req" ] || continue
    execute_v2 "$("$TOYBOX" dirname "$req")"
    check_live_orphan_block && break
  done
  LAST_ACTIVE_SCAN_MS=$(( $(uptime_ms) - scan_start ))

  if ! check_live_orphan_block; then
    for req in "$JOBS"/*/request.json; do
      [ -f "$req" ] || continue
      execute_v1 "$req"
    done
  fi

  now_ms="$(uptime_ms)"
  if [ $((now_ms - LAST_METRICS_MS)) -ge "$RECONCILE_MS" ]; then
    write_metrics
    LAST_METRICS_MS="$now_ms"
  fi

  [ "$ONESHOT" = 1 ] && exit 0
  "$TOYBOX" sleep "$POLL_SEC"
done
