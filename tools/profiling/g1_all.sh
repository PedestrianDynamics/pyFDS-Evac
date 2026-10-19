#!/usr/bin/env bash
# G1 driver: runs every G1 block serially in README order, unattended.
# Start detached (never in the foreground of a busy terminal):
#   nohup caffeinate -s bash g1_all.sh > results/blocks/g1_all_<UTC>.log 2>&1 < /dev/null &
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

wait_slot() {  # 60 s polls, max 20 min
  for _ in $(seq 1 21); do
    if "$PY" benchmark.py check | "$PY" -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["ok"] else 1)'; then
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

vblock() {  # vblock <name> <vbuild_bench.py args...>: V-build runner, same slot/cap rules
  local name=$1; shift
  if [ -n "$DRY" ]; then echo "DRY vblock $name: vbuild_bench.py --block $name --exclusive $*"; return; fi
  if (( $(date +%s) - T0 > CAP_S )); then log "$name	VBUILD	SKIPPED_CAP	0"; return; fi
  if ! wait_slot; then log "$name	VBUILD	SKIPPED_SLOT	0"; return; fi
  local t=$(date +%s)
  "$PY" vbuild_bench.py --block "$name" --exclusive "$@"
  local rc=$?
  log "$name	VBUILD	rc=$rc	$(( $(date +%s) - t ))"
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

[ -n "$DRY" ] || updates_off || { log "ABORT	g1_all	software_update	-"; exit 1; }
log "START	g1_all	pid=$$	cap_s=$CAP_S"

# 1. determinism gate (W3 with result capture on both runs: not measurements, C1/O8)
block ${PASS}_det --case W1 --warmup 0 --reps 2 --label determinism
block ${PASS}_det --case W3 --warmup 0 --reps 2 --vis-cache noflag --capture-result --label determinism
gate ${PASS}_det W1
gate ${PASS}_det W3

# 2. W1 baseline (no application cache state, D13), headline seeds
block ${PASS}_base  --case W1 --label baseline
block ${PASS}_seeds --case W1 --seeds 2,3 --reps 3 --label baseline

# 3. W2 clear air
block ${PASS}_w2 --case W2 --label baseline

# 3b. W1r (end-to-end, different workload, 300 s / 4 GB like W1) and the #739 fixture (120 s / 2 GB)
block ${PASS}_w1r  --case W1r --timeout 300 --label end-to-end
block ${PASS}_flow --case W4_flow_saturated --warmup 1 --reps 5 --timeout 120 --label controlled-cost

# 3c. V-build kernel experiment (D15, D24): own runner, 1 warm-up + 5 plain + 1 instrumented diagnostic
vblock ${PASS}_vbuild --n 1001

# 4. W3 and W3b visibility cache states
block ${PASS}_w3first  --case W3 --warmup 0 --reps 3 --vis-cache first --label controlled-cost
block ${PASS}_w3rep    --case W3 --vis-cache repeated --label controlled-cost
block ${PASS}_w3noflag --case W3 --vis-cache noflag --label controlled-cost
block ${PASS}_w3seeds  --case W3 --seeds 43,44 --reps 3 --vis-cache repeated --label baseline
block ${PASS}_w3bfirst --case W3b_cmm --warmup 0 --reps 3 --vis-cache first --label controlled-cost
block ${PASS}_w3brep   --case W3b_cmm --vis-cache repeated --label controlled-cost

# 5. instrumentation overhead and equivalence: plain run.py vs counters, interleaved
block ${PASS}_ovh   --case W1 --instrument none,counters --label controlled-cost
block ${PASS}_ovhW3 --case W3 --instrument none,counters --vis-cache repeated --label controlled-cost
block ${PASS}_ovhD  --case W1 --instrument none,counters,detail --order abba --label controlled-cost

# 6. output variants: untimed-purpose equivalence check of O_min first, then timed ABAB
block ${PASS}_outchk --case W1 --variants O_min_check --warmup 0 --reps 1 --label equivalence
block ${PASS}_out    --case W1 --variants O_study,O_norc,O_min --label controlled-cost

# 7. scaling (N=200 is ${PASS}_base)
block ${PASS}_scale100 --case W1_n100 --label end-to-end
block ${PASS}_scale400 --case W1_n400 --label end-to-end

# 8. W4 fixtures (correctness only, never timed)
block ${PASS}_w4 --case W4_iso21 --warmup 0 --reps 1 --label fixture
if [ -n "$DRY" ]; then
  echo "DRY W4 extras: iso22 a-d, cmm arm A, 26-file pytest; then comparisons ${PASS}_ovh/_ovhD/_ovhW3/_out/_outchk and analyse.py"
  exit 0
fi
W4OUT=$STAGE/runs/${PASS}_w4_extra_$(date -u +%Y%m%dT%H%M%S); mkdir -p "$W4OUT"
REC=$HERE/results/raw/${PASS}_w4_extra; mkdir -p "$REC"
if (( $(date +%s) - T0 <= CAP_S )); then
  (cd "$WT" && for c in a b c d; do
     PYTHONHASHSEED=0 "$PY" run.py --scenario assets/iso_table22_coupled/config_$c.json --seed 420 \
       --fds-dir $STAGE/fds/iso_table22_$c --output-fed-history "$W4OUT/fed_$c.csv" \
       --output-sqlite "$W4OUT/t22_$c.sqlite" --cleanup > "$REC/iso22_$c.log" 2>&1
     echo "iso22_$c rc=$?" >> "$REC/status.txt"; done)
  (cd "$WT" && PYTHONHASHSEED=0 "$PY" run.py --scenario assets/cognitive_map_memory/config.json --seed 5150 \
     --fds-dir $STAGE/fds/cmm_clear_air --allow-fds-horizon-hold --vis-cache "$W4OUT/vis_cmm_A.npz" \
     --output-sqlite "$W4OUT/cmm_A.sqlite" --cleanup --output-route-history "$W4OUT/cmm_A_routes.csv" \
     --output-exit-history "$W4OUT/cmm_A_exit.csv" > "$REC/cmm_armA.log" 2>&1
   echo "cmm_armA rc=$?" >> "$REC/status.txt")
  (cd "$WT" && git status --porcelain --ignored --untracked-files=all > "$REC/worktree_before_pytest.txt"
   PYTHONHASHSEED=0 "$PY" -m pytest -q -rs tests/test_iso_table21_coupled.py tests/test_iso_table22_coupled.py \
     tests/test_thin_exit.py tests/test_direct_steering_runtime.py tests/test_direct_steering_fallbacks.py \
     tests/test_exit_door_width.py tests/test_scheduled_exits.py tests/test_rerouting_golden.py \
     tests/test_route_graph.py tests/test_fds_sampling.py tests/test_fds_horizon.py tests/test_visibility.py \
     tests/test_cognitive_map_memory.py tests/test_cognitive_map_history.py tests/test_exit_visibility_alpha.py \
     tests/test_initial_exit_from_cognitive_map.py tests/test_skimage_line_contract.py tests/test_agent_seed.py \
     tests/test_manifest.py tests/test_route_grid_sampling.py tests/test_foresight_arrival_time.py \
     tests/test_flow_spawn_spacing.py tests/test_flow_window_end.py tests/test_fdsreader_adapter.py \
     tests/test_fds_read_only.py tests/test_fdsvismap_adapter.py > "$REC/pytest.log" 2>&1
   echo "pytest rc=$?" >> "$REC/status.txt"
   git status --porcelain --ignored --untracked-files=all > "$REC/worktree_after_pytest.txt")
  echo "outputs $W4OUT" >> "$REC/status.txt"
  log "${PASS}_w4_extra	W4	done	-"
else
  log "${PASS}_w4_extra	W4	SKIPPED_CAP	0"
fi

# 9. analysis after all runs (no timed work left)
ref=$(first_id ${PASS}_ovh W1); [ -n "$ref" ] && "$PY" compare.py --block ${PASS}_ovh --ref "$ref" --out results/equivalence/${PASS}_ovh_W1.json > /dev/null 2>&1
ref=$(first_id ${PASS}_ovhD W1); [ -n "$ref" ] && "$PY" compare.py --block ${PASS}_ovhD --ref "$ref" --out results/equivalence/${PASS}_ovhD_W1.json > /dev/null 2>&1
ref=$(first_id ${PASS}_ovhW3 W3); [ -n "$ref" ] && "$PY" compare.py --block ${PASS}_ovhW3 --ref "$ref" --out results/equivalence/${PASS}_ovh_W3.json > /dev/null 2>&1
ref=$(first_id ${PASS}_base W1); [ -n "$ref" ] && for b in ${PASS}_outchk ${PASS}_out; do
  "$PY" compare.py --block "$b" --ref "$ref" --out "results/equivalence/${b}_vs_${PASS}_base.json" > /dev/null 2>&1; done
"$PY" analyse.py > results/blocks/analyse_${PASS}.txt 2>&1
log "END	g1_all	elapsed_s=$(( $(date +%s) - T0 ))"
