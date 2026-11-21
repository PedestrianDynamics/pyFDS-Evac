#!/bin/bash
# Print, and with --go submit, the ballroom job chain:
#   fire-only test -> run 1 (fire + evac) -> repeats 2..N (EVACUATION_MC_MODE)
# Each step starts only if the previous one ended OK (afterok); a job that
# fails its own check (see run_ballroom.sbatch) exits non-zero, so the rest
# is cancelled. Without --go nothing is submitted. Run from JURECA after
# `jutil env activate -p cias-7`.
#
#   bash submit_ballroom.sh --fire-deck F.fds --evac-deck E.fds --mc-deck M.fds \
#        --nmpi 8 [--repeats 10] [--wall-fire HH:MM:SS] [--wall-run1 HH:MM:SS] \
#        [--wall-mc HH:MM:SS] [--partition NAME] [--go]
# The fire-only deck must set NO_EVACUATION=.TRUE.; the MC deck is the evac
# deck with EVACUATION_MC_MODE=.TRUE. and the same CHID.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRE=""; EVAC=""; MC=""; NMPI=""; REPEATS=10; GO=0; PART=""
WALL_FIRE="02:00:00"; WALL_RUN1="24:00:00"; WALL_MC="12:00:00"   # starting guesses, adjust
usage() { sed -n '2,13p' "$0"; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --fire-deck) FIRE="${2:?}"; shift 2;;
    --evac-deck) EVAC="${2:?}"; shift 2;;
    --mc-deck) MC="${2:?}"; shift 2;;
    --nmpi) NMPI="${2:?}"; shift 2;;
    --repeats) REPEATS="${2:?}"; shift 2;;
    --partition) PART="${2:?}"; shift 2;;
    --wall-fire) WALL_FIRE="${2:?}"; shift 2;;
    --wall-run1) WALL_RUN1="${2:?}"; shift 2;;
    --wall-mc) WALL_MC="${2:?}"; shift 2;;
    --go) GO=1; shift;;
    *) usage;;
  esac
done
for v in FIRE EVAC MC NMPI; do
  [ -n "${!v}" ] || { echo "FAIL: missing option for $v" >&2; usage; }
done
for f in "$FIRE" "$EVAC" "$MC"; do
  [ -f "$f" ] || { echo "FAIL: no such deck: $f" >&2; exit 1; }
done
[ "$REPEATS" -ge 2 ] || { echo "FAIL: --repeats must be >= 2" >&2; exit 1; }
grep -qi 'NO_EVACUATION *= *\.TRUE\.' "$FIRE" || { echo "FAIL: $FIRE lacks NO_EVACUATION=.TRUE." >&2; exit 1; }
grep -qi 'EVACUATION_MC_MODE *= *\.TRUE\.' "$MC" || { echo "FAIL: $MC lacks EVACUATION_MC_MODE=.TRUE." >&2; exit 1; }
[ -n "${PROJECT:-}" ] || { echo "FAIL: \$PROJECT empty; run jutil env activate -p cias-7" >&2; exit 1; }
FIRE="$(realpath "$FIRE")"; EVAC="$(realpath "$EVAC")"; MC="$(realpath "$MC")"
PARTARG=()
[ -z "$PART" ] || PARTARG=(-p "$PART")

submit() {   # submit <dep-jobid|""> <wall> <deck> <label> [from]; prints the job id
  local dep="$1" wall="$2" deck="$3" label="$4" from="${5:-}"
  local cmd=(sbatch --parsable --account=ias-7 "${PARTARG[@]}" -n "$NMPI" -t "$wall"
             --export="ALL,HPC_DIR=$HERE" --job-name="bw-$label")
  [ -z "$dep" ] || cmd+=(--dependency="afterok:$dep" --kill-on-invalid-dep=yes)
  cmd+=("$HERE/run_ballroom.sbatch" "$deck" "$NMPI" "$label")
  [ -z "$from" ] || cmd+=("$from")
  if [ "$GO" -eq 0 ]; then
    echo "WOULD RUN: ${cmd[*]}" >&2
    echo "DRY-$label"
    return
  fi
  "${cmd[@]}"
}

[ "$GO" -eq 1 ] || echo "Dry run: nothing is submitted. Add --go only after the maintainer's explicit go-ahead." >&2
J0=$(submit "" "$WALL_FIRE" "$FIRE" fire-only)
J1=$(submit "$J0" "$WALL_RUN1" "$EVAC" run01)
for i in $(seq 2 "$REPEATS"); do
  submit "$J1" "$WALL_MC" "$MC" "$(printf 'run%02d' "$i")" run01 >/dev/null
done
if [ "$GO" -eq 1 ]; then
  echo "Submitted: fire-only=$J0 run01=$J1 repeats 2..$REPEATS (afterok run01). Check: squeue -u \$USER"
fi
