#!/bin/bash
# Build FDS 6.7.7 (last release with FDS+Evac, Source/evac.f90) on JURECA.
# Run ONCE, BY HAND, on a login node, from a login shell:
#   jutil env activate -p cias-7
#   bash setup_fds677_jsc.sh 2>&1 | tee setup_fds677.log
# Installs to $PROJECT/$USER/fds-6.7.7. Does not touch the FDS 6.10.1
# install or any shell profile. Never deletes anything.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=fds677_common.sh
. "$HERE/fds677_common.sh"

require_project
echo "FDS_ROOT=$FDS_ROOT  TARGET=$TARGET"

# 1. Source at the release tag.
if [ -e "$FDS_ROOT" ]; then
  [ -d "$FDS_ROOT/.git" ] || die "$FDS_ROOT exists and is not a source checkout; move it away first"
  echo "Reusing existing checkout $FDS_ROOT"
else
  mkdir -p "$(dirname "$FDS_ROOT")"
  git clone --depth 1 --branch "$FDS_TAG" "$FDS_REPO" "$FDS_ROOT" \
    || die "clone failed. If the login node has no outbound access, clone on your laptop and rsync the complete directory (with .git) to $FDS_ROOT, then rerun."
fi
cd "$FDS_ROOT"
[ "$(git describe --tags --exact-match 2>/dev/null)" = "$FDS_TAG" ] \
  || die "checkout is not exactly at tag $FDS_TAG"
[ -z "$(git status --porcelain)" ] || die "checkout has local changes (the build would be tagged -dirty)"
[ -f Source/evac.f90 ] || die "Source/evac.f90 missing: this is not an FDS+Evac source tree"
[ -f "Build/$TARGET/make_fds.sh" ] || die "Build/$TARGET not in this tree"
echo "OK: tag $FDS_TAG, Source/evac.f90 present ($(wc -c < Source/evac.f90) bytes)"

# 2. Toolchain.
load_toolchain
echo "gfortran: $(gfortran --version 2>&1 | head -1)"
echo "mpifort : $(mpifort --version 2>&1 | head -1)"

# 3. Build. The makefile runs `git describe`, so make runs inside the clone.
[ ! -e "$FDS_BIN" ] || die "$FDS_BIN already exists; move the install away to rebuild"
cd "$FDS_ROOT/Build/$TARGET"
echo "Building $TARGET; log: $FDS_ROOT/build.log"
if ! make -j4 VPATH="../../Source" -f ../makefile "$TARGET" \
      GFORTRAN_OPTIONS="$GFORTRAN_OPTIONS" > "$FDS_ROOT/build.log" 2>&1; then
  tail -n 40 "$FDS_ROOT/build.log" >&2
  die "build failed; full log $FDS_ROOT/build.log (see 'If the build fails' in fds677_common.sh)"
fi
[ -x "$FDS_BIN" ] || die "make reported success but $FDS_BIN is missing"

# 4. Checks on the binary.
if ldd "$FDS_BIN" | grep -q 'not found'; then
  ldd "$FDS_BIN" | grep 'not found' >&2
  die "binary has unresolved shared libraries"
fi
if command -v nm >/dev/null; then
  n_evac=$(nm "$FDS_BIN" | grep -ci evac || true)
  [ "$n_evac" -gt 0 ] || die "no evac symbols in the binary: Evac not compiled in"
  EVAC_SYMS="yes ($n_evac symbols)"
else
  EVAC_SYMS="not checked (nm missing)"
fi

# 5. Manifest.
{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host: $(hostname)"
  echo "git describe: $(git -C "$FDS_ROOT" describe --long --tags)"
  echo "git commit: $(git -C "$FDS_ROOT" rev-parse HEAD)"
  echo "make target: $TARGET"
  echo "GFORTRAN_OPTIONS: $GFORTRAN_OPTIONS"
  echo "binary: $FDS_BIN"
  echo "binary sha256: $(sha256_of "$FDS_BIN")"
  echo "evac symbols in binary: $EVAC_SYMS"
  echo "gfortran: $(gfortran --version 2>&1 | head -1)"
  echo "mpifort: $(mpifort --version 2>&1 | head -1)"
  echo "mpirun: $(mpirun --version 2>&1 | head -1)"
  echo "modules (STAGES_MODULE='$STAGES_MODULE'; TOOLCHAIN_MODULES='${TOOLCHAIN_MODULES[*]}'):"
  module list 2>&1 | sed 's/^/  /'
} > "$FDS_MANIFEST"
echo "--- $FDS_MANIFEST"
cat "$FDS_MANIFEST"
echo
echo "BUILD CHECKED: binary exists, libraries resolve, Evac symbols: $EVAC_SYMS."
echo "NOT CHECKED: that it runs. Next step: smoke_test.sbatch with a guide example deck."
