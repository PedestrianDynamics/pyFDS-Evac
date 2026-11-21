#!/bin/bash
# Shared settings and checks for the FDS 6.7.7 (FDS+Evac) JURECA scripts.
# Sourced, never executed. Nothing here touches shell profiles or the
# existing FDS 6.10.1 install.

# ---- Toolchain ------------------------------------------------------
# TO CONFIRM with `module avail` on JURECA: every name below is a guess
# at the JSC Stages convention, not a verified module name.
#   - Print what exists:  module spider GCC ; module spider OpenMPI ;
#                         module spider ParaStationMPI
#   - The modules must provide `gfortran` and `mpifort` (check with
#     `which gfortran mpifort`).
# If the build fails:
#   - gfortran >= 10 rejects the old MPI call style in 6.7.7; the
#     makefile only adds -fallow-argument-mismatch for gfortran major
#     version 10 exactly, so GFORTRAN_OPTIONS below is passed explicitly.
#     If the compiler is older than 10, set GFORTRAN_OPTIONS="".
#   - A very new gfortran (13 and later) may add errors from -std=f2018;
#     try an older GCC from an older Stage (`module spider GCC`, then
#     STAGES_MODULE=Stages/<older>) and rebuild into a NEW directory.
#   - Intel route: TARGET=impi_intel_linux_64 needs `mpiifort` (classic
#     ifort + Intel MPI). Current oneAPI releases no longer ship ifort,
#     so this works only with an older Stage. Set TOOLCHAIN_MODULES to
#     the Intel compiler + Intel MPI modules.
# shellcheck disable=SC2206
TOOLCHAIN_MODULES=(${TOOLCHAIN_MODULES_OVERRIDE:-GCC ParaStationMPI})   # TO CONFIRM
STAGES_MODULE="${STAGES_MODULE:-}"   # TO CONFIRM, e.g. "Stages/2025"; empty = default stage

# Chosen from the 6.7.7 Build tree (see transfer.md): GNU + mpifort.
TARGET="${TARGET:-mpi_gnu_linux_64}"
GFORTRAN_OPTIONS="${GFORTRAN_OPTIONS--fallow-argument-mismatch}"
FDS_TAG="FDS6.7.7"
FDS_REPO="https://github.com/firemodels/fds.git"

# ---- Paths ----------------------------------------------------------
die() { echo "FAIL: $*" >&2; exit 1; }

require_project() {
  [ -n "${PROJECT:-}" ] || die "\$PROJECT is empty. Run: jutil env activate -p cias-7"
  [ -d "$PROJECT" ] || die "\$PROJECT=$PROJECT is not a directory"
  : "${USER:?USER is not set}"
  FDS_ROOT="${FDS_ROOT:-$PROJECT/$USER/fds-6.7.7}"
  FDS_BIN="$FDS_ROOT/Build/$TARGET/fds_$TARGET"
  FDS_MANIFEST="$FDS_ROOT/build_manifest.txt"
  RUNS_BASE="${RUNS_BASE:-$PROJECT/$USER/fds-evac-runs/cvm2-ballroom}"
  case "$FDS_ROOT" in
    *6.10*|*6.9*|*6.8*) die "FDS_ROOT=$FDS_ROOT looks like another FDS version; refusing" ;;
  esac
}

load_toolchain() {
  type module >/dev/null 2>&1 || die "'module' command not found. Use a login shell (bash -l)."
  # The environment changes only inside this script's process.
  if [ -n "$STAGES_MODULE" ]; then
    module load "$STAGES_MODULE" || die "module load $STAGES_MODULE failed"
  fi
  local m
  for m in "${TOOLCHAIN_MODULES[@]}"; do
    module load "$m" || die "module load $m failed (module names are TO CONFIRM with module avail)"
  done
  # The GNU target links MKL only if MKLROOT is set; keep the build free of it.
  unset MKLROOT
  command -v mpifort >/dev/null || die "mpifort not on PATH after loading ${TOOLCHAIN_MODULES[*]}"
}

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

# ---- Judging a finished FDS run ------------------------------------
# FDS exits 0 on input errors and on a stop file, so the exit status
# alone proves nothing. Success = the STOP line is in the .out file and
# no "Numerical Instability" appears in the .out file or the job log.
chid_of() {
  local c
  c=$(grep -io "CHID *= *'[^']*'" "$1" | head -1 | sed "s/.*'\(.*\)'/\1/")
  [ -n "$c" ] || die "no CHID='...' found in $1"
  echo "$c"
}

judge_run() {   # judge_run <rundir> <chid> [<joblog>]
  local dir="$1" chid="$2" log="${3:-}" out="$1/$2.out" rc=0
  [ -f "$out" ] || { echo "FAIL: $out does not exist" >&2; return 1; }
  if ! grep -q 'STOP: FDS completed successfully' "$out"; then
    echo "FAIL: no 'STOP: FDS completed successfully' in $out; last lines:" >&2
    tail -n 5 "$out" >&2
    rc=1
  fi
  if grep -qi 'Numerical Instability' "$out" ${log:+"$log"}; then
    echo "FAIL: 'Numerical Instability' reported (see $out)" >&2
    rc=1
  fi
  if [ -e "$dir/$chid.stop" ]; then
    echo "FAIL: stop file $dir/$chid.stop present" >&2
    rc=1
  fi
  return $rc
}
