#!/bin/bash
# Run one C/VM2 ballroom deck with FDS 6.7.7. Submit via submit_ballroom.sh
# (or by hand, see transfer.md). Arguments:
#   $1 DECK    path to the .fds deck
#   $2 NMPI    MPI processes = number of FIRE meshes (evacuation meshes are
#              not parallel)
#   $3 LABEL   run directory name under $RUNS_BASE: fire-only, run01, run02, ...
#   $4 FROM    optional: LABEL of the finished run 1. For an
#              EVACUATION_MC_MODE repeat its output is copied into the new
#              run directory first (without slice and boundary files), so
#              run 1 is never modified.
# Wall time is chosen on the command line (-t HH:MM:SS): the evacuation part
# may take hours. --ntasks must equal NMPI (-n NMPI).
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

DECK="${1:?usage: sbatch -n NMPI -t HH:MM:SS run_ballroom.sbatch DECK NMPI LABEL [FROM]}"
NMPI="${2:?NMPI missing}"
LABEL="${3:?LABEL missing}"
FROM="${4:-}"
[ -f "$DECK" ] || die "deck not found: $DECK"
require_project
[ "$NMPI" -eq "${SLURM_NTASKS:-0}" ] || die "NMPI=$NMPI but --ntasks=${SLURM_NTASKS:-unset}; submit with sbatch -n $NMPI"
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

if [ -n "$FROM" ]; then
  SRC="$RUNS_BASE/$FROM"
  [ -f "$SRC/$CHID.out" ] || die "$SRC has no $CHID.out; run 1 must be finished first"
  grep -q 'STOP: FDS completed successfully' "$SRC/$CHID.out" || die "$SRC is not a successful run"
  # TO CONFIRM against the guide (sec. 9.2): MC mode reads the evacuation flow
  # field (.eff) and FED (.fed) files of run 1; slice and boundary data are not needed.
  rsync -a --exclude='run_record' --exclude='*.sf' --exclude='*.bf' --exclude='*.s3d' \
        --exclude='*.prt5' --exclude="$CHID.out" --exclude='*_evac.csv' --exclude='*.log' \
        --exclude='*.stdout' "$SRC/" "$DIR/"
fi
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
  echo "label: $LABEL  from: ${FROM:-none}"
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
srun -n "$NMPI" ${SRUN_MPI:+--mpi="$SRUN_MPI"} "$FDS_BIN" "$(basename "$DECK")" > fds.stdout 2>&1 || rc=$?
echo "srun exit status: $rc" | tee -a "$REC/run_record.txt"
[ "$rc" -eq 0 ] || die "srun failed (rc=$rc); see $DIR/fds.stdout"
if judge_run "$DIR" "$CHID" "$DIR/fds.stdout"; then
  echo "verdict: OK (STOP line found, no instability)" | tee -a "$REC/run_record.txt"
else
  echo "verdict: FAILED" | tee -a "$REC/run_record.txt"
  die "run judged failed; see $DIR/$CHID.out"
fi
