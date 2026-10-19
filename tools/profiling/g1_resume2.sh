#!/usr/bin/env bash
# G1 driver: runs every G1 block serially in README order, unattended.
# Start detached (never in the foreground of a busy terminal):
#   nohup caffeinate -s bash g1_all.sh > results/blocks/g1_all_<UTC>.log 2>&1 < /dev/null &
# Before each block it polls `benchmark.py check` every 60 s for up to 20 min;
# a block whose slot never passes is recorded as SKIPPED_SLOT and the driver moves on.
# Hard cap: 4 h from start; blocks not started by then are recorded as SKIPPED_CAP.
# Status lines: results/blocks/g1_status.tsv (UTC time, block, case, status, seconds).
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
STATUS=$HERE/results/blocks/g1v2_status.tsv
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
  if (( $(date +%s) - T0 > CAP_S )); then log "$name	$case_arg	SKIPPED_CAP	0"; return; fi
  if ! wait_slot; then log "$name	$case_arg	SKIPPED_SLOT	0"; return; fi
  local t=$(date +%s)
  "$PY" benchmark.py run --block "$name" --exclusive "$@"
  local rc=$?
  log "$name	$case_arg	rc=$rc	$(( $(date +%s) - t ))"
  case "$case_arg" in W1|W3|W3b_cmm|W1r)   # horizon criterion (D26), after the block, untimed
    for d in "$HERE"/results/raw/"${name}_${case_arg}_"*/; do
      "$PY" horizon_check.py "$d" > /dev/null 2>&1 || log "$name	$case_arg	HORIZON_CHECK_FAILED	$(basename "$d")"
    done ;;
  esac
}

vblock() {  # vblock <name> <vbuild_bench.py args...>: V-build runner, same slot/cap rules
  local name=$1; shift
  if (( $(date +%s) - T0 > CAP_S )); then log "$name	VBUILD	SKIPPED_CAP	0"; return; fi
  if ! wait_slot; then log "$name	VBUILD	SKIPPED_SLOT	0"; return; fi
  local t=$(date +%s)
  "$PY" vbuild_bench.py --block "$name" --exclusive "$@"
  local rc=$?
  log "$name	VBUILD	rc=$rc	$(( $(date +%s) - t ))"
}

first_id() { ls "$HERE/results/raw" | grep "^$1_$2_" | sort | head -1; }

gate() {  # gate <block> <case>: all runs equivalent to the first, negative control PASS, else stop
  local ref; ref=$(first_id "$1" "$2")
  if [ -z "$ref" ]; then log "GATE	$1_$2	FAIL(no runs)	-"; exit 1; fi
  "$PY" compare.py --block "${1}_${2}" --ref "$ref" --out "results/equivalence/${1}_${2}.json" > /dev/null 2>&1
  "$PY" compare.py --negative-control "$ref" --out "results/equivalence/${1}_${2}_negative_control.json" > /dev/null 2>&1
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

log "START	g1_resume2(after det gates, D30 load 2.5)	pid=$$	cap_s=$CAP_S"

# 1. determinism gate (W3 with result capture on both runs: not measurements, C1/O8)
gate G1det W1
gate G1det W3

# 2. W1 baseline (no application cache state, D13), headline seeds
block G1base  --case W1 --label baseline
block G1seeds --case W1 --seeds 2,3 --reps 3 --label baseline

# 3. W2 clear air
block G1w2 --case W2 --label baseline

# 3b. W1r (end-to-end, different workload, 300 s / 4 GB like W1) and the #739 fixture (120 s / 2 GB)
block G1w1r  --case W1r --timeout 300 --label end-to-end
block G1flow --case W4_flow_saturated --warmup 1 --reps 5 --timeout 120 --label controlled-cost

# 3c. V-build kernel experiment (D15, D24): own runner, 1 warm-up + 5 plain + 1 instrumented diagnostic
vblock G1vbuild --n 1001

# 4. W3 and W3b visibility cache states
block G1w3first  --case W3 --warmup 0 --reps 3 --vis-cache first --label controlled-cost
block G1w3rep    --case W3 --vis-cache repeated --label controlled-cost
block G1w3noflag --case W3 --vis-cache noflag --label controlled-cost
block G1w3seeds  --case W3 --seeds 43,44 --reps 3 --vis-cache repeated --label baseline
block G1w3bfirst --case W3b_cmm --warmup 0 --reps 3 --vis-cache first --label controlled-cost
block G1w3brep   --case W3b_cmm --vis-cache repeated --label controlled-cost

# 5. instrumentation overhead and equivalence: plain run.py vs counters, interleaved
block G1ovh   --case W1 --instrument none,counters --label controlled-cost
block G1ovhW3 --case W3 --instrument none,counters --vis-cache repeated --label controlled-cost
block G1ovhD  --case W1 --instrument none,counters,detail --order abba --label controlled-cost

# 6. output variants: untimed-purpose equivalence check of O_min first, then timed ABAB
block G1outchk --case W1 --variants O_min_check --warmup 0 --reps 1 --label equivalence
block G1out    --case W1 --variants O_study,O_norc,O_min --label controlled-cost

# 7. scaling (N=200 is G1base)
block G1scale100 --case W1_n100 --label end-to-end
block G1scale400 --case W1_n400 --label end-to-end

# 8. W4 fixtures (correctness only, never timed)
block G1w4 --case W4_iso21 --warmup 0 --reps 1 --label fixture
W4OUT=$STAGE/runs/G1w4_extra_$(date -u +%Y%m%dT%H%M%S); mkdir -p "$W4OUT"
REC=$HERE/results/raw/G1w4_extra; mkdir -p "$REC"
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
  log "G1w4_extra	W4	done	-"
else
  log "G1w4_extra	W4	SKIPPED_CAP	0"
fi

# 9. analysis after all runs (no timed work left)
ref=$(first_id G1ovh W1); [ -n "$ref" ] && "$PY" compare.py --block G1ovh --ref "$ref" --out results/equivalence/G1ovh_W1.json > /dev/null 2>&1
ref=$(first_id G1ovhD W1); [ -n "$ref" ] && "$PY" compare.py --block G1ovhD --ref "$ref" --out results/equivalence/G1ovhD_W1.json > /dev/null 2>&1
ref=$(first_id G1ovhW3 W3); [ -n "$ref" ] && "$PY" compare.py --block G1ovhW3 --ref "$ref" --out results/equivalence/G1ovh_W3.json > /dev/null 2>&1
ref=$(first_id G1base W1); [ -n "$ref" ] && for b in G1outchk G1out; do
  "$PY" compare.py --block "$b" --ref "$ref" --out "results/equivalence/${b}_vs_G1base.json" > /dev/null 2>&1; done
"$PY" analyse.py > results/blocks/analyse_g1.txt 2>&1
log "END	g1_all	elapsed_s=$(( $(date +%s) - T0 ))"
