#!/usr/bin/env bash
# G1b pass-2 continuation 2 (2026-10-16): the four blocks g1_resume4.sh recorded as SKIPPED_SLOT
# plus G1b_scale400, whose six runs were all flagged (foreign python/launchd), rerun as
# G1b_scale400b so the flagged block stays a record. The slot blocker was a user launch agent
# in a launchd respawn loop (KeepAlive, ThrottleInterval 30 s): every 31 s a short-lived python
# above 20 % CPU. agents_quiet() refuses to start while any launchd job is in that state, and a
# failed slot poll now prints its reason to the driver log.
# Start detached (never in the foreground of a busy terminal):
#   nohup caffeinate -s bash g1_resume5.sh > results/blocks/g1_all_<UTC>.log 2>&1 < /dev/null &
# Before each block it polls `benchmark.py check` every 60 s for up to 20 min;
# a block whose slot never passes is recorded as SKIPPED_SLOT and the driver moves on.
# Hard cap: 4 h from start; blocks not started by then are recorded as SKIPPED_CAP.
# Status lines: results/blocks/<pass>_status.tsv, g1b_status.tsv by default (UTC time, block,
# case, status, seconds); SLOT_RACE_RETRY lines mark a re-check that lost a race.
# The determinism gate (two plain runs of W1 and W3 through compare.py, plus the negative
# control) runs before any other block; a failed gate stops the driver (exit 1).
# Other equivalence comparisons and analyse.py run after all timed blocks.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
P=/Users/chraibi/profiling-stage
PY=$P/wt_8f7d29a2/.venv/bin/python
WT=$P/wt_8f7d29a2
STAGE=/Users/chraibi/profiling-stage
CAP_S=$((4 * 3600))
T0=$(date +%s)
# Pass tag (env G1_PASS, default G1b): prefix of every block name, so run ids look like
# G1b_base_W1_..., and of the status file (results/blocks/g1b_status.tsv). Pass 1 used
# G1base, G1det, ... and g1v2_status.tsv; first_id picks the alphabetically first run, so a
# new pass must never share a prefix with an old one.
PASS=${G1_PASS:-G1b}
STATUS=$HERE/results/blocks/$(printf '%s' "$PASS" | tr 'A-Z' 'a-z')_status.tsv
# G1_DRY_RUN=1: print the planned blocks and exit without slot polls, runs or status lines.
DRY=${G1_DRY_RUN:-}
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

block() {  # block <name> <benchmark.py run args...>
  local name=$1; shift
  local case_arg
  case_arg=$(printf '%s ' "$@" | sed -n 's/.*--case \([^ ]*\).*/\1/p')
  if [ -n "$DRY" ]; then echo "DRY block $name: benchmark.py run --block $name --exclusive $*"; return; fi
  if (( $(date +%s) - T0 > CAP_S )); then log "$name	$case_arg	SKIPPED_CAP	0"; return; fi
  if ! wait_slot; then log "$name	$case_arg	SKIPPED_SLOT	0"; return; fi
  local t=$(date +%s) rc out
  for _try in 1 2 3; do   # benchmark.py re-checks the slot itself; after a full-CPU block load1 may
    out=$("$PY" benchmark.py run --block "$name" --exclusive "$@" 2>&1); rc=$?   # still be decaying
    printf '%s\n' "$out"
    if [ $rc -eq 1 ] && printf '%s' "$out" | grep -q "exclusive slot check failed"; then
      log "$name	$case_arg	SLOT_RACE_RETRY	$_try"; wait_slot || break; continue
    fi
    break
  done
  log "$name	$case_arg	rc=$rc	$(( $(date +%s) - t ))"
  case "$case_arg" in W1|W1_n100|W1_n400|W3|W3b_cmm|W1r)   # horizon criterion (D26), after the block, untimed
    for d in "$HERE"/results/raw/"${name}_${case_arg}_"*/; do
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

first_id() { ls "$HERE/results/raw" | grep "^$1_$2_" | sort | head -1; }

gate() {  # gate <block> <case>: all runs equivalent to the first, negative control PASS, else stop
  if [ -n "$DRY" ]; then echo "DRY gate $1 $2: compare.py --block ${1}_${2}, negative control, stop on failure"; return; fi
  local ref; ref=$(first_id "$1" "$2")
  if [ -z "$ref" ]; then log "GATE	$1_$2	FAIL(no runs)	-"; exit 1; fi
  # a non-zero compare.py exit is a failed gate; the JSON is read only after both calls succeeded
  "$PY" compare.py --block "${1}_${2}" --ref "$ref" --out "results/equivalence/${1}_${2}.json" > /dev/null 2>&1 \
    || { log "GATE	$1_$2	FAIL(compare.py exit)	-"; exit 1; }
  "$PY" compare.py --negative-control "$ref" --out "results/equivalence/${1}_${2}_negative_control.json" > /dev/null 2>&1 \
    || { log "GATE	$1_$2	FAIL(compare.py exit)	-"; exit 1; }
  if "$PY" - "results/equivalence/${1}_${2}.json" "results/equivalence/${1}_${2}_negative_control.json" <<'PYEOF'
import json, sys
try:
    a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
except Exception:
    sys.exit(1)
ok = len(a) >= 1 and all(r["verdict"] == "equivalent" for r in a) \
    and all(r["negative_control"] == "PASS" for r in b)
sys.exit(0 if ok else 1)
PYEOF
  then log "GATE	$1_$2	PASS	-"; else log "GATE	$1_$2	FAIL	-"; exit 1; fi
}

[ -n "$DRY" ] || updates_off || { log "ABORT	g1_resume5	software_update	-"; exit 1; }
[ -n "$DRY" ] || agents_quiet || { log "ABORT	g1_resume5	launch_agent_loop	-"; exit 1; }
log "START	g1_resume5	pid=$$	cap_s=$CAP_S"

# 1. determinism gate (W3 with result capture on both runs: not measurements, C1/O8)
gate ${PASS}_det W1
gate ${PASS}_det W3

# 5. instrumentation overhead, detail level: rerun of the contaminated ${PASS}_ovhD
block ${PASS}_ovhD2 --case W1 --instrument none,counters,detail --order abba --label controlled-cost

# 6. output variants: untimed-purpose equivalence check of O_min first, then timed ABAB
block ${PASS}_outchk --case W1 --variants O_min_check --warmup 0 --reps 1 --label equivalence
block ${PASS}_out    --case W1 --variants O_study,O_norc,O_min --label controlled-cost

# 7. scaling (N=200 is ${PASS}_base); ${PASS}_scale400 of 2026-10-16T20:54Z is 6/6 flagged
block ${PASS}_scale100  --case W1_n100 --label end-to-end
block ${PASS}_scale400b --case W1_n400 --label end-to-end

# 8. W4 fixtures: done by g1_resume4.sh (G1b_w4 rc=0, G1b_w4_extra done)
if [ -n "$DRY" ]; then
  echo "DRY: then comparisons ${PASS}_ovhD2/_out/_outchk and analyse.py"
  exit 0
fi

# 9. analysis after all runs (no timed work left)
ref=$(first_id ${PASS}_ovhD2 W1); [ -n "$ref" ] && "$PY" compare.py --block ${PASS}_ovhD2 --ref "$ref" --out results/equivalence/${PASS}_ovhD2_W1.json > /dev/null 2>&1
ref=$(first_id ${PASS}_base W1); [ -n "$ref" ] && for b in ${PASS}_outchk ${PASS}_out; do
  "$PY" compare.py --block "$b" --ref "$ref" --out "results/equivalence/${b}_vs_${PASS}_base.json" > /dev/null 2>&1; done
"$PY" analyse.py > results/blocks/analyse_${PASS}.txt 2>&1
log "END	g1_resume5	elapsed_s=$(( $(date +%s) - T0 ))"
