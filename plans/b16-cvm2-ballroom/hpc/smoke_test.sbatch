#!/bin/bash
# Verify the FDS 6.7.7 build with ONE FDS+Evac guide example deck
# (e.g. evac_example2*.fds; GPL, kept outside the repo).
# Submit BY HAND from the hpc directory, after `jutil env activate -p cias-7`:
#   sbatch -n NMPI -t 00:30:00 smoke_test.sbatch /path/to/evac_example2.fds [NMPI]
# NMPI = MPI processes = number of fire meshes in the deck (default 1).
# Partition: TO CONFIRM with `sinfo`; override with sbatch -p <name>.
#SBATCH --job-name=fds677-smoke
#SBATCH --account=ias-7
#SBATCH --partition=dc-cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:30:00
#SBATCH --output=fds677-smoke-%j.log
set -euo pipefail
HPC_DIR="${HPC_DIR:-$SLURM_SUBMIT_DIR}"
[ -f "$HPC_DIR/fds677_common.sh" ] || { echo "FAIL: fds677_common.sh not in $HPC_DIR (submit from the hpc dir or set HPC_DIR)" >&2; exit 1; }
# shellcheck source=fds677_common.sh
. "$HPC_DIR/fds677_common.sh"

DECK="${1:?usage: sbatch smoke_test.sbatch DECK.fds [NMPI]}"
NMPI="${2:-${SLURM_NTASKS:-1}}"
[ -f "$DECK" ] || die "deck not found: $DECK"
require_project
[ -x "$FDS_BIN" ] || die "binary missing: $FDS_BIN (run setup_fds677_jsc.sh)"
[ -f "$FDS_MANIFEST" ] || die "build manifest missing: $FDS_MANIFEST"
[ "$NMPI" -le "${SLURM_NTASKS:-1}" ] || die "NMPI=$NMPI exceeds --ntasks=${SLURM_NTASKS:-1}; submit with sbatch -n $NMPI"
[ "$(sha256_of "$FDS_BIN")" = "$(sed -n 's/^binary sha256: //p' "$FDS_MANIFEST")" ] || die "binary differs from the build manifest"
load_toolchain
export OMP_NUM_THREADS=1

CHID="$(chid_of "$DECK")"
DIR="$RUNS_BASE/smoke-$(basename "$DECK" .fds)-$SLURM_JOB_ID"
mkdir -p "$DIR"
cp "$DECK" "$DIR/"
cd "$DIR"
echo "build: $(sed -n 's/^git describe: //p' "$FDS_MANIFEST")"

rc=0
srun -n "$NMPI" ${SRUN_MPI:+--mpi="$SRUN_MPI"} "$FDS_BIN" "$(basename "$DECK")" > fds.stdout 2>&1 || rc=$?
echo "srun exit status: $rc (FDS exits 0 on input errors; the .out file decides)"
[ "$rc" -eq 0 ] || die "srun failed (rc=$rc); see $DIR/fds.stdout"
judge_run "$DIR" "$CHID" "$DIR/fds.stdout" || die "smoke test FAILED; see $DIR"
echo "SMOKE TEST PASSED (STOP line found, no instability). Output: $DIR"
echo "Still to check by hand: ${CHID}_evac.csv must show all agents evacuated."
