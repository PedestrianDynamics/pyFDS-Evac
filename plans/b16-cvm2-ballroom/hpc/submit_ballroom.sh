#!/bin/bash
# Print, and with --go submit, the ballroom job chain (FDS 6.7.7 / Evac 2.6.1;
# fire and evacuation never run together, see README.md):
#   phase1 (serial, evacuation mesh) -> phase2 (MPI, fire meshes, afterok
#   phase1) -> rep01..rep10 (serial, EVACUATION_MC_MODE, each afterok
#   phase2, each in its own directory)
# Optional, independent submissions: --fire-deck (stand-alone fire test) and
# --dx050-deck (phase 1 on the 0.5 m evacuation grid). A job that fails its
# own check (see run_ballroom.sbatch) exits non-zero, so dependents are
# cancelled. Without --go nothing is submitted. Run from JURECA after
# `jutil env activate -p cias-7`.
#
#   bash submit_ballroom.sh --phase1-deck cvm2_ballroom_evac.fds \
#        --phase2-deck cvm2_ballroom_evac_fed.fds \
#        --phase3-deck cvm2_ballroom_evac_mc.fds [--nmpi 21] [--repeats 10] \
#        [--wall-p1 HH:MM:SS] [--wall-p2 HH:MM:SS] [--wall-p3 HH:MM:SS] \
#        [--fire-deck F.fds [--wall-fire HH:MM:SS] [--fire-label NAME]] \
#        [--dx050-deck D.fds [--wall-dx050 HH:MM:SS]] [--partition NAME] [--go]
# --nmpi is the number of fire meshes (21), used for phase 2 and the fire
# test. Phases 1, 3 and the dx050 drill request 1 task. The fire test
# deck must set NO_EVACUATION; use a make_decks.py --t-end 10 copy first
# (with --fire-label fire-test-short, since a label is never reused).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P1=""; P2=""; P3=""; FIRE=""; DX=""; NMPI=21; REPEATS=10; GO=0; PART=""
FIRE_LABEL="fire-test"
# Wall times: phase 2 from the README estimate (about 65 core-hours, 3 h on
# 21 processes, range 35-130 core-hours, so 1.7-6.2 h); the rest are GUESSES.
WALL_P1="01:00:00"; WALL_P2="08:00:00"; WALL_P3="02:00:00"
WALL_FIRE="08:00:00"; WALL_DX="01:00:00"
usage() { sed -n '2,22p' "$0"; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --phase1-deck) P1="${2:?}"; shift 2;;
    --phase2-deck) P2="${2:?}"; shift 2;;
    --phase3-deck) P3="${2:?}"; shift 2;;
    --fire-deck) FIRE="${2:?}"; shift 2;;
    --fire-label) FIRE_LABEL="${2:?}"; shift 2;;
    --dx050-deck) DX="${2:?}"; shift 2;;
    --nmpi) NMPI="${2:?}"; shift 2;;
    --repeats) REPEATS="${2:?}"; shift 2;;
    --partition) PART="${2:?}"; shift 2;;
    --wall-p1) WALL_P1="${2:?}"; shift 2;;
    --wall-p2) WALL_P2="${2:?}"; shift 2;;
    --wall-p3) WALL_P3="${2:?}"; shift 2;;
    --wall-fire) WALL_FIRE="${2:?}"; shift 2;;
    --wall-dx050) WALL_DX="${2:?}"; shift 2;;
    --go) GO=1; shift;;
    *) usage;;
  esac
done
for v in P1 P2 P3; do
  [ -n "${!v}" ] || { echo "FAIL: missing deck option for $v" >&2; usage; }
done
for f in "$P1" "$P2" "$P3" ${FIRE:+"$FIRE"} ${DX:+"$DX"}; do
  [ -f "$f" ] || { echo "FAIL: no such deck: $f" >&2; exit 1; }
done
[ "$REPEATS" -ge 1 ] || { echo "FAIL: --repeats must be >= 1" >&2; exit 1; }
need() {   # need <deck> <keyword>
  grep -qi "$2 *= *\.TRUE\." "$1" || { echo "FAIL: $1 lacks $2=.TRUE." >&2; exit 1; }
}
chid() { grep -io "CHID *= *'[^']*'" "$1" | head -1 | sed "s/.*'\(.*\)'/\1/"; }
need "$P1" EVACUATION_INITIALIZATION
need "$P2" EVACUATION_WRITE_FED
need "$P3" EVACUATION_MC_MODE
[ -z "$FIRE" ] || need "$FIRE" NO_EVACUATION
[ -z "$DX" ] || need "$DX" EVACUATION_INITIALIZATION
[ "$(chid "$P1")" = "$(chid "$P2")" ] && [ "$(chid "$P1")" = "$(chid "$P3")" ] \
  || { echo "FAIL: the three phase decks must share one CHID" >&2; exit 1; }
[ -n "${PROJECT:-}" ] || { echo "FAIL: \$PROJECT empty; run jutil env activate -p cias-7" >&2; exit 1; }
P1="$(realpath "$P1")"; P2="$(realpath "$P2")"; P3="$(realpath "$P3")"
[ -z "$FIRE" ] || FIRE="$(realpath "$FIRE")"
[ -z "$DX" ] || DX="$(realpath "$DX")"
PARTARG=()
[ -z "$PART" ] || PARTARG=(-p "$PART")

submit() {   # submit <dep-jobid|""> <ntasks> <wall> <deck> <label> [imports...]; prints the job id
  local dep="$1" n="$2" wall="$3" deck="$4" label="$5"; shift 5
  local cmd=(sbatch --parsable --account=ias-7 ${PARTARG[@]+"${PARTARG[@]}"} -n "$n" -t "$wall"
             --export="ALL,HPC_DIR=$HERE" --job-name="bw-$label")
  [ -z "$dep" ] || cmd+=(--dependency="afterok:$dep" --kill-on-invalid-dep=yes)
  cmd+=("$HERE/run_ballroom.sbatch" "$deck" "$n" "$label" "$@")
  if [ "$GO" -eq 0 ]; then
    echo "WOULD RUN: ${cmd[*]}" >&2
    echo "DRY-$label"
    return
  fi
  "${cmd[@]}"
}

[ "$GO" -eq 1 ] || echo "Dry run: nothing is submitted. Add --go only after the maintainer's explicit go-ahead." >&2
J1=$(submit "" 1 "$WALL_P1" "$P1" phase1)
J2=$(submit "$J1" "$NMPI" "$WALL_P2" "$P2" phase2 phase1:_evac.xyz)
for i in $(seq 1 "$REPEATS"); do
  # phase 3 reads .eff (phase 1) and .fed (phase 2); to confirm on the first repeat.
  submit "$J2" 1 "$WALL_P3" "$P3" "$(printf 'rep%02d' "$i")" phase1:_evac.eff phase2:_evac.fed >/dev/null
done
[ -z "$FIRE" ] || submit "" "$NMPI" "$WALL_FIRE" "$FIRE" "$FIRE_LABEL" >/dev/null
[ -z "$DX" ] || submit "" 1 "$WALL_DX" "$DX" evac-dx050 >/dev/null
if [ "$GO" -eq 1 ]; then
  echo "Submitted: phase1=$J1 phase2=$J2 (afterok phase1) rep01..rep$(printf '%02d' "$REPEATS") (afterok phase2). Check: squeue -u \$USER"
fi
