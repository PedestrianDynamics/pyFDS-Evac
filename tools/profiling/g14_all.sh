#!/usr/bin/env bash
# G14 repeat count at main after PR #814 (design decisions 1-3): one detail block in one
# exclusive slot at the main stage wt_b6dff31c, about 5 min of runs. Expected run directories
# (warm-ups included):
#   G14_cnt_W1   W1, variant O_norc, --instrument detail, seeds 1 and 2, warm-up 0, reps 1: 2
# The harness (benchmark.py, attribute.py) runs under the baseline interpreter; the stage arguments
# --wt and --py make run.py execute in the main worktree and its venv. The counts are workload
# properties and no timing claim; the block is record-only in analyse.py and stays out of the
# pooled statistics.
# A run counts as done when its manifest.json ends in completed, flows_closed or
# incomplete_time_limit. A block whose runs are all done is recorded as complete and
# skipped, so a second slot reruns only what is missing. A block with run directories but too few
# done runs is recorded as PARTIAL and not rerun (rerunning would pool reps of two sessions under
# one block name); the maintainer reruns it under another pass tag (G14_PASS=G14b).
# A status file left by an earlier slot is moved to g14_status_<UTC>.tsv before START, so each slot
# file holds one START and one END; commit the rotated files with the slot's results.
# Start detached (never in the foreground of a busy terminal):
#   nohup caffeinate -s bash g14_all.sh > results/blocks/g14_all_<UTC>.log 2>&1 < /dev/null &
# Before each block it polls `benchmark.py check` every 60 s for up to 20 min;
# a block whose slot never passes is recorded as SKIPPED_SLOT and the driver moves on.
# Hard cap: 2 h from start; blocks not started by then are recorded as SKIPPED_CAP.
# Status lines: results/blocks/g14_status.tsv (UTC time, block, case, status, seconds);
# SLOT_RACE_RETRY lines mark a re-check that lost a race. The last line of a complete run is END.
# The horizon step also logs HORIZON_CHECK_FAILED for a run whose horizon.json has
# warning_count >= 1 (as in g3_all.sh).
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
P=/Users/chraibi/profiling-stage
PY=$P/wt_8f7d29a2/.venv/bin/python
STAGE_WT=$P/wt_b6dff31c
STAGE_PY=$STAGE_WT/.venv/bin/python
STAGE=/Users/chraibi/profiling-stage
CAP_S=$((2 * 3600))
T0=$(date +%s)
# Pass tag (env G14_PASS, default G14): prefix of every block name, so run ids look like
# G14_cnt_W1_W1_..., and of the status file (results/blocks/g14_status.tsv).
PASS=${G14_PASS:-G14}
STATUS=$HERE/results/blocks/$(printf '%s' "$PASS" | tr 'A-Z' 'a-z')_status.tsv
# G14_DRY_RUN=1: print the planned blocks and exit without slot polls, runs or status lines.
DRY=${G14_DRY_RUN:-}
[ -n "$DRY" ] && STATUS=/dev/null
mkdir -p "$HERE/results/blocks"
cd "$HERE"

log() { printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$STATUS"; }

SLOT_REASON_PY=$(cat <<'PYEOF'
import json, sys
c = json.load(sys.stdin)
if c["ok"]:
    sys.exit(0)
heavy = ", ".join("%s %.0f%%" % (r["comm"].rsplit("/", 1)[-1], r["pcpu"]) for r in c["foreign_heavy"])
print("slot busy: load1 %.2f ac %s lpm %s heavy [%s]"
      % (c["load_avg"][0], c["ac_power"], c["low_power_mode"], heavy))
sys.exit(1)
PYEOF
)

wait_slot() {  # 60 s polls, max 20 min; a failed poll prints its reason (driver log only)
  for _ in $(seq 1 21); do
    if "$PY" benchmark.py check | "$PY" -c "$SLOT_REASON_PY"; then
      return 0
    fi
    sleep 60
  done
  return 1
}

over_cap() { (( $(date +%s) - T0 > CAP_S )); }

block() {  # block <name> <run-id prefix> <benchmark.py run args...>
  local name=$1 prefix=$2; shift 2
  local case_arg
  case_arg=$(printf '%s ' "$@" | sed -n 's/.*--case \([^ ]*\).*/\1/p')
  if [ -n "$DRY" ]; then echo "DRY block $name: benchmark.py run --block $name --exclusive $*"; return; fi
  if over_cap; then log "$name	$case_arg	SKIPPED_CAP	0"; return; fi
  if ! wait_slot; then log "$name	$case_arg	SKIPPED_SLOT	0"; return; fi
  if over_cap; then log "$name	$case_arg	SKIPPED_CAP	0"; return; fi
  local t=$(date +%s) rc out
  for _try in 1 2 3; do   # benchmark.py re-checks the slot itself; after a full-CPU block load1 may
    out=$("$PY" benchmark.py run --block "$name" --exclusive "$@" 2>&1); rc=$?   # still be decaying
    printf '%s\n' "$out"
    if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q "exclusive slot check failed"; then
      log "$name	$case_arg	SLOT_RACE_RETRY	$_try"; wait_slot || break
      if over_cap; then log "$name	$case_arg	SKIPPED_CAP	0"; return; fi
      continue
    fi
    break
  done
  if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q "exclusive slot check failed"; then
    log "$name	$case_arg	SKIPPED_SLOT	0"; return
  fi
  log "$name	$case_arg	rc=$rc	$(( $(date +%s) - t ))"
  case "$case_arg" in W1|W1_n100|W1_n400|W3|W3b_cmm|W1r)   # horizon criterion (D26), after the block, untimed
    for d in "$HERE"/results/raw/"${prefix}"*/; do
      [ -d "$d" ] || continue
      "$PY" horizon_check.py "$d" > /dev/null 2>&1 || log "$name	$case_arg	HORIZON_CHECK_FAILED	$(basename "$d")"
      # None of the G3 arms writes rc.csv, so horizon.json passes is null; foresight warnings are the signal.
      if grep -Eq '"warning_count": *[1-9]' "$d/horizon.json" 2>/dev/null; then
        log "$name	$case_arg	HORIZON_CHECK_FAILED	$(basename "$d")"
      fi
    done ;;
  esac
}

# Refuse to start while macOS may install software in the background (G1b pass 2, 2026-10-16:
# an automatic update ran from 12:20 UTC, contaminated one block and blocked the slot for five).
updates_off() {
  local k v
  for k in AutomaticallyInstallMacOSUpdates AutomaticDownload; do
    v=$(defaults read /Library/Preferences/com.apple.SoftwareUpdate "$k" 2>/dev/null || echo 0)
    [ "$v" = "0" ] || { echo "software update: $k=$v (must be 0)"; return 1; }
  done
  local busy
  busy=$(ps -Ao pcpu=,comm= | awk '/(installd|appstoreagent|softwareupdated)$/ && $1 > 5.0 {print $2}' | head -1)
  [ -z "$busy" ] || { echo "software update: $busy busy"; return 1; }
  return 0
}

# Refuse to start while a launchd job of this user is in a respawn loop: not running, last exit
# non-zero, and launchd has its next spawn scheduled (KeepAlive). Such a job starts a short-lived
# process every ThrottleInterval seconds and fails the slot check at random polls.
agents_quiet() {
  local uid label pid status info bad=0
  uid=$(id -u)
  while read -r pid status label; do
    [ "$pid" = "-" ] && [ "$status" != "0" ] || continue
    info=$(launchctl print "gui/$uid/$label" 2>/dev/null)
    printf '%s' "$info" | grep -q 'state = spawn scheduled' || continue
    printf '%s' "$info" | grep -q 'properties = .*keepalive' || continue
    echo "launch agent respawn loop: $label (last exit $status); stop it: launchctl bootout gui/$uid/$label"
    bad=1
  done < <(launchctl list | tail -n +2)
  return $bad
}

done_runs() {  # done_runs <prefix>: number of run directories with that prefix whose manifest ended normally
  local d n=0
  for d in "$HERE"/results/raw/"$1"*/; do
    [ -f "$d/manifest.json" ] || continue
    grep -Eq '"termination": *"(completed|flows_closed|incomplete_time_limit)"' "$d/manifest.json" && n=$((n + 1))
  done
  echo "$n"
}

gblock() {  # gblock <name> <prefix> <expected> <benchmark.py run args...>: block unless already complete
  local name=$1 prefix=$2 expected=$3; shift 3
  local case_arg n dirs
  case_arg=$(printf '%s ' "$@" | sed -n 's/.*--case \([^ ]*\).*/\1/p')
  if [ -z "$DRY" ]; then
    n=$(done_runs "$prefix")
    dirs=$(ls "$HERE/results/raw" | grep -c "^$prefix")
    if [ "$n" -ge "$expected" ]; then log "$name	$case_arg	ALREADY_COMPLETE	$n"; return; fi
    if [ "$dirs" -gt 0 ]; then log "$name	$case_arg	PARTIAL	$n/$expected (dirs $dirs)"; return; fi
  fi
  block "$name" "$prefix" "$@"
}

[ -n "$DRY" ] || updates_off || { log "ABORT	g14_all	software_update	-"; exit 1; }
[ -n "$DRY" ] || agents_quiet || { log "ABORT	g14_all	launch_agent_loop	-"; exit 1; }
if [ -z "$DRY" ] && [ -s "$STATUS" ]; then mv "$STATUS" "${STATUS%.tsv}_$(date -u +%Y%m%dT%H%M%SZ).tsv"; fi
STAGE_ARGS="--wt $STAGE_WT --py $STAGE_PY"
log "START	g14_all	pid=$$	cap_s=$CAP_S"
gblock ${PASS}_cnt_W1 ${PASS}_cnt_W1_W1_ 2 --case W1 --variants O_norc --instrument detail --seeds 1,2 --warmup 0 --reps 1 --label diagnostic $STAGE_ARGS
[ -n "$DRY" ] && exit 0
log "END	g14_all	elapsed_s=$(( $(date +%s) - T0 ))"
