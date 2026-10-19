#!/usr/bin/env bash
# G2 attribution slot (design decision 4): six experiment blocks in one exclusive slot, about
# 55 min of runs. Expected run directories per block (warm-ups included):
#   G2_prof_W3      W3, --vis-cache first, --profiler none,pyinstrument, abba, warm-up 0, reps 2: 4
#   G2_prof_W1r     W1r, --profiler none,pyinstrument, abba, warm-up 1, reps 2: 6
#   G2_prof_W4flow  W4_flow_saturated, --profiler none,pyinstrument, warm-up 0, reps 1: 2
#   G2_prof_W1      W1, --profiler none,pyinstrument, abba, warm-up 1, reps 2: 6
#   G2_rc_cprof     W1 O_study and W1 O_norc, --profiler cprofile, warm-up 0, reps 1: 1 + 1
#   G2_ctr_scale    --instrument counters on W1_n100, W1, W1_n400, warm-up 1, reps 3: 4 + 4 + 4
# A run counts as done when its manifest.json ends in completed, flows_closed or
# incomplete_time_limit. A block whose runs are all done is recorded as complete and
# skipped, so a second slot reruns only what is missing. A block with run directories but too few
# done runs is recorded as PARTIAL and not rerun (rerunning would pool reps of two sessions under
# one block name); the maintainer reruns it under another pass tag (G2_PASS=G2b).
# A status file left by an earlier slot is moved to g2_status_<UTC>.tsv before START, so each slot
# file holds one START and one END; commit the rotated files with the slot's results.
# Start detached (never in the foreground of a busy terminal):
#   nohup caffeinate -s bash g2_all.sh > results/blocks/g2_all_<UTC>.log 2>&1 < /dev/null &
# Before each block it polls `benchmark.py check` every 60 s for up to 20 min;
# a block whose slot never passes is recorded as SKIPPED_SLOT and the driver moves on.
# Hard cap: 2 h from start; blocks not started by then are recorded as SKIPPED_CAP.
# Status lines: results/blocks/g2_status.tsv (UTC time, block, case, status, seconds);
# SLOT_RACE_RETRY lines mark a re-check that lost a race. The last line of a complete run is END.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
P=/Users/chraibi/profiling-stage
PY=$P/wt_8f7d29a2/.venv/bin/python
WT=$P/wt_8f7d29a2
STAGE=/Users/chraibi/profiling-stage
CAP_S=$((2 * 3600))
T0=$(date +%s)
# Pass tag (env G2_PASS, default G2): prefix of every block name, so run ids look like
# G2_prof_W1_W1_..., and of the status file (results/blocks/g2_status.tsv).
PASS=${G2_PASS:-G2}
STATUS=$HERE/results/blocks/$(printf '%s' "$PASS" | tr 'A-Z' 'a-z')_status.tsv
# G2_DRY_RUN=1: print the planned blocks and exit without slot polls, runs or status lines.
DRY=${G2_DRY_RUN:-}
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

[ -n "$DRY" ] || updates_off || { log "ABORT	g2_all	software_update	-"; exit 1; }
[ -n "$DRY" ] || agents_quiet || { log "ABORT	g2_all	launch_agent_loop	-"; exit 1; }
if [ -z "$DRY" ] && [ -s "$STATUS" ]; then mv "$STATUS" "${STATUS%.tsv}_$(date -u +%Y%m%dT%H%M%SZ).tsv"; fi
log "START	g2_all	pid=$$	cap_s=$CAP_S"
gblock ${PASS}_prof_W3     ${PASS}_prof_W3_     4 --case W3 --vis-cache first --profiler none,pyinstrument --order abba --warmup 0 --reps 2 --label diagnostic
gblock ${PASS}_prof_W1r    ${PASS}_prof_W1r_    6 --case W1r --profiler none,pyinstrument --order abba --warmup 1 --reps 2 --label diagnostic
gblock ${PASS}_prof_W4flow ${PASS}_prof_W4flow_ 2 --case W4_flow_saturated --profiler none,pyinstrument --warmup 0 --reps 1 --label diagnostic
gblock ${PASS}_prof_W1     ${PASS}_prof_W1_     6 --case W1 --profiler none,pyinstrument --order abba --warmup 1 --reps 2 --label diagnostic
gblock ${PASS}_rc_cprof    ${PASS}_rc_cprof_W1_O_study_ 1 --case W1 --variants O_study --profiler cprofile --warmup 0 --reps 1 --label diagnostic
gblock ${PASS}_rc_cprof    ${PASS}_rc_cprof_W1_O_norc_  1 --case W1 --variants O_norc  --profiler cprofile --warmup 0 --reps 1 --label diagnostic
# The W1 counters prefix ends in O_study: ${PASS}_ctr_scale_W1_ alone would also match the W1_n100 and W1_n400 run ids.
gblock ${PASS}_ctr_scale   ${PASS}_ctr_scale_W1_n100_ 4 --case W1_n100 --instrument counters --warmup 1 --reps 3 --label diagnostic
gblock ${PASS}_ctr_scale   ${PASS}_ctr_scale_W1_O_study 4 --case W1      --instrument counters --warmup 1 --reps 3 --label diagnostic
gblock ${PASS}_ctr_scale   ${PASS}_ctr_scale_W1_n400_ 4 --case W1_n400 --instrument counters --warmup 1 --reps 3 --label diagnostic
[ -n "$DRY" ] && { echo "DRY: then analyse.py"; exit 0; }
"$PY" analyse.py > results/blocks/analyse_${PASS}.txt 2>&1
log "END	g2_all	elapsed_s=$(( $(date +%s) - T0 ))"
