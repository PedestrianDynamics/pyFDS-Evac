#!/bin/bash
# Run one C/VM2 ballroom deck with FDS 6.7.7. Submit via submit_ballroom.sh
# (or by hand, see transfer.md). Arguments:
#   $1 DECK    path to the .fds deck
#   $2 NMPI    MPI processes: the number of fire meshes for the fire decks
#              (EVACUATION_WRITE_FED, NO_EVACUATION); exactly 1 for
#              EVACUATION_INITIALIZATION and EVACUATION_MC_MODE (evacuation
#              meshes only, serial)
#   $3 LABEL   run directory name under $RUNS_BASE: phase1, phase2, rep01, ...
#   $4...      optional imports, each SRCLABEL:SUFFIX: copies
#              $RUNS_BASE/SRCLABEL/<CHID>SUFFIX into the new run directory,
#              after checking that run succeeded (STOP line). Phase 2 imports
#              phase1:_evac.xyz; a phase 3 repeat imports phase1:_evac.eff
#              and phase2:_evac.fed. Sources are never modified.
# Every run gets its own directory because phase 3 overwrites
# <CHID>_evmc.csv. Wall time is chosen on the command line (-t HH:MM:SS);
# --ntasks must equal NMPI (-n NMPI).
# Partition: TO CONFIRM with `sinfo`; override with sbatch -p <name>.
#SBATCH --job-name=cvm2-ballroom
#SBATCH --account=ias-7
#SBATCH --partition=dc-cpu
#SBATCH --nodes=1
#SBATCH --output=ballroom-%j.log
set -euo pipefail
HPC_DIR="${HPC_DIR:-$SLURM_SUBMIT_DIR}"
[ -f "$HPC_DIR/fds677_common.sh" ] || { echo "FAIL: fds677_common.sh not in $HPC_DIR (submit from the hpc dir or set HPC_DIR)" >&2; exit 1; }
# shellcheck source=fds677_common.sh
. "$HPC_DIR/fds677_common.sh"

DECK="${1:?usage: sbatch -n NMPI -t HH:MM:SS run_ballroom.sbatch DECK NMPI LABEL [SRC:SUFFIX ...]}"
NMPI="${2:?NMPI missing}"
LABEL="${3:?LABEL missing}"
shift 3
IMPORTS=("$@")
[ -f "$DECK" ] || die "deck not found: $DECK"
require_project
[ "$NMPI" -eq "${SLURM_NTASKS:-0}" ] || die "NMPI=$NMPI but --ntasks=${SLURM_NTASKS:-unset}; submit with sbatch -n $NMPI"
MODE=fire
grep -qi 'NO_EVACUATION *= *\.TRUE\.' "$DECK" && MODE=fire-only
grep -qi 'EVACUATION_INITIALIZATION *= *\.TRUE\.' "$DECK" && MODE=phase1
grep -qi 'EVACUATION_WRITE_FED *= *\.TRUE\.' "$DECK" && MODE=phase2
grep -qi 'EVACUATION_MC_MODE *= *\.TRUE\.' "$DECK" && MODE=phase3
case "$MODE" in
  phase1|phase3) [ "$NMPI" -eq 1 ] || die "$MODE is serial (evacuation mesh only); NMPI must be 1" ;;
esac
[ -x "$FDS_BIN" ] || die "binary missing: $FDS_BIN (run setup_fds677_jsc.sh)"
[ -f "$FDS_MANIFEST" ] || die "build manifest missing: $FDS_MANIFEST"
BIN_SHA="$(sha256_of "$FDS_BIN")"
[ "$BIN_SHA" = "$(sed -n 's/^binary sha256: //p' "$FDS_MANIFEST")" ] || die "binary differs from the build manifest"
load_toolchain
export OMP_NUM_THREADS=1

CHID="$(chid_of "$DECK")"
DIR="$RUNS_BASE/$LABEL"
REC="$DIR/run_record"
[ ! -e "$DIR/$CHID.out" ] || die "$DIR already holds $CHID.out; choose a new LABEL (never overwrite a run)"
mkdir -p "$REC"

for imp in ${IMPORTS[@]+"${IMPORTS[@]}"}; do
  SRC="$RUNS_BASE/${imp%%:*}"; FILE="$CHID${imp#*:}"
  [ -f "$SRC/$CHID.out" ] || die "$SRC has no $CHID.out; its run must be finished first"
  grep -q 'STOP: FDS completed successfully' "$SRC/$CHID.out" || die "$SRC is not a successful run"
  [ -s "$SRC/$FILE" ] || die "$SRC/$FILE missing or empty"
  cp -p "$SRC/$FILE" "$DIR/"
done
cp "$DECK" "$DIR/"
cp "$FDS_MANIFEST" "$REC/build_manifest.txt"
cp "$0" "$REC/job_script.sbatch"
cp "$HPC_DIR/fds677_common.sh" "$REC/fds677_common.sh"

record_end() {
  local rc=$?
  {
    echo "end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "script exit status: $rc"
  } >> "$REC/run_record.txt"
}
trap record_end EXIT
{
  echo "job id: $SLURM_JOB_ID"
  echo "label: $LABEL  mode: $MODE  imports: ${IMPORTS[*]:-none}"
  echo "deck: $DECK"
  echo "deck sha256: $(sha256_of "$DECK")"
  echo "binary: $FDS_BIN"
  echo "binary sha256: $BIN_SHA"
  echo "mpi processes: $NMPI"
  echo "node list: $SLURM_JOB_NODELIST"
  echo "start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$REC/run_record.txt"

cd "$DIR"
rc=0
# FDS+Evac has no seed input: the seed is taken from the wall clock at start.
# Record the launch time to the millisecond; nothing is staggered.
echo "fds launch: $(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) (epoch ms $(( $(date +%s%N) / 1000000 )))" >> "$REC/run_record.txt"
srun -n "$NMPI" ${SRUN_MPI:+--mpi="$SRUN_MPI"} "$FDS_BIN" "$(basename "$DECK")" > fds.stdout 2>&1 || rc=$?
echo "srun exit status: $rc" | tee -a "$REC/run_record.txt"
[ "$rc" -eq 0 ] || die "srun failed (rc=$rc); see $DIR/fds.stdout"
if judge_run "$DIR" "$CHID" "$DIR/fds.stdout"; then
  echo "verdict: OK (STOP line found, no instability)" | tee -a "$REC/run_record.txt"
else
  echo "verdict: FAILED" | tee -a "$REC/run_record.txt"
  die "run judged failed; see $DIR/$CHID.out"
fi
[ "$MODE" != phase3 ] || [ -s "$DIR/${CHID}_evmc.csv" ] || echo "WARN: ${CHID}_evmc.csv missing or empty in $DIR" | tee -a "$REC/run_record.txt"
