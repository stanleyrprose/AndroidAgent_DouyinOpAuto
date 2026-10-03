#!/system/bin/sh
umask 0077
JOBS=/data/local/y700-agent/jobs
RUNTIME=/data/local/y700-agent/runtime
LOG=$RUNTIME/host-executor.log
TOYBOX=/system/bin/toybox

$TOYBOX mkdir -p "$JOBS" "$RUNTIME"
SELF_PID=$$
echo "$($TOYBOX date '+%Y-%m-%dT%H:%M:%S%z') host-executor start pid=$SELF_PID" >> "$LOG"

# A previous executor may have died after claiming a job but before writing the
# completion marker result.json. Never replay a privileged command
# automatically: duplicate execution could be destructive.
for claim in "$JOBS"/*/.claim; do
  [ -d "$claim" ] || continue
  dir="${claim%/.claim}"
  [ -f "$dir/result.json" ] && continue
  printf '%s\n' "executor restarted before result; command not replayed" > "$dir/stderr.log"
  : > "$dir/stdout.log"
  printf '{"status":"FAILED"}\n' > "$dir/state.json.tmp"
  $TOYBOX mv "$dir/state.json.tmp" "$dir/state.json"
  # result.json is deliberately last: it is the client completion marker.
  printf '{"status":"FAILED","exit_code":125,"reason":"STALE_CLAIM_AFTER_EXECUTOR_RESTART"}\n' > "$dir/result.json.tmp"
  $TOYBOX mv "$dir/result.json.tmp" "$dir/result.json"
  job="${dir##*/}"
  echo "$($TOYBOX date '+%Y-%m-%dT%H:%M:%S%z') stale_claim job=$job marked_failed" >> "$LOG"
done

write_state() {
  dir="$1"
  status="$2"
  printf '{"status":"%s"}\n' "$status" > "$dir/state.json.tmp"
  $TOYBOX mv "$dir/state.json.tmp" "$dir/state.json"
}

while true; do
  for req in "$JOBS"/*/request.json; do
    [ -f "$req" ] || continue
    dir="${req%/request.json}"
    [ -f "$dir/result.json" ] && continue
    $TOYBOX mkdir "$dir/.claim" 2>/dev/null || continue

    write_state "$dir" RUNNING
    action="$($TOYBOX sed -n 's/.*"action"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$req")"
    rc=127

    case "$action" in
      root_exec)
        b64="$($TOYBOX sed -n 's/.*"command_b64"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$req")"
        if [ -n "$b64" ]; then
          printf '%s' "$b64" | $TOYBOX base64 -d > "$dir/command.sh"
          $TOYBOX chmod 700 "$dir/command.sh"
          /system/bin/sh "$dir/command.sh" > "$dir/stdout.log" 2> "$dir/stderr.log"
          rc=$?
        else
          printf '%s\n' "missing command_b64" > "$dir/stderr.log"
          : > "$dir/stdout.log"
          rc=2
        fi
        ;;
      *)
        : > "$dir/stdout.log"
        printf 'unsupported action: %s\n' "$action" > "$dir/stderr.log"
        rc=3
        ;;
    esac

    if [ "$rc" -eq 0 ]; then status=SUCCEEDED; else status=FAILED; fi

    # Final state is durable before publishing the completion marker.
    write_state "$dir" "$status"
    printf '{"status":"%s","exit_code":%s}\n' "$status" "$rc" > "$dir/result.json.tmp"
    $TOYBOX mv "$dir/result.json.tmp" "$dir/result.json"

    job="${dir##*/}"
    echo "$($TOYBOX date '+%Y-%m-%dT%H:%M:%S%z') job=$job action=$action rc=$rc" >> "$LOG"
  done
  $TOYBOX sleep 0.25
done
