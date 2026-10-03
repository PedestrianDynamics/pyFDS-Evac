#!/usr/bin/env bash
# Release gate: run every check of the release checklist on the current commit.
#
# Usage, from anywhere in the repository:
#
#   scripts/release_check.sh [--quick|--full] [--report FILE] [--gates LIST]
#                            [--only PAGE ...] [PYTHON_VERSION ...]
#
#   --quick    analyses on the stored evacuation runs of the data store
#              (default); the studies' run sets are not re-run
#   --full     re-run the studies' evacuations as well (about 1 h more)
#   --report   Markdown report (default: release-check-<commit>.md in the
#              current folder); the step logs go to <report>.logs/
#   --gates    comma-separated subset of tests,install,bundles,docs,site
#              (default: all five)
#   --only     restrict the docs and bundles gates to these pages (names
#              from scripts/release_check.toml or site/data/examples.toml)
#   PYTHON_VERSION  the versions to test (default: the Python classifiers of
#              pyproject.toml that satisfy requires-python)
#
# Gates, in this order:
#   bundles build  scripts/docs/bundle_examples.py, on the clean checkout
#   tests          pytest -q -rs per Python version, external_data included;
#                  a skipped external_data test fails the gate
#   install        uv build --wheel; per Python version a fresh venv and a
#                  plain pip install <wheel>[gui]: pip check, the first
#                  pyfds-evac --help and pyfds-evac-gui --help (cold, FAIL
#                  above 1.0 s), an argument error, python -m pyfds_evac,
#                  the GUI page and a small scenario outside the repository;
#                  without the extra, the install hint of pyfds-evac-gui
#   bundles        each download zip: install requirements.txt, follow
#                  README.txt up to the FDS step
#   docs           the documented commands of scripts/release_check.toml
#   site           hugo --panicOnWarning in site/
#
# Everything runs in a detached worktree of HEAD in a temporary folder, so
# the commands may rewrite figures and assets without touching this tree.
# FDS_EVAC_DATA is the data store (fds-evac-data/); nothing is written to it.
# Exit status: 0 when no check failed, 1 otherwise. STALE checks (pages an
# open issue already lists) do not fail the gate.
set -uo pipefail

MODE=quick
REPORT=
GATES=tests,install,bundles,docs,site
ONLY=()
VERSIONS=()
while [ $# -gt 0 ]; do
  case $1 in
    --quick) MODE=quick ;;
    --full) MODE=full ;;
    --report) REPORT=$2; shift ;;
    --gates) GATES=$2; shift ;;
    --only) shift; while [ $# -gt 0 ] && [ "${1#--}" = "$1" ] && ! [[ $1 =~ ^3\.[0-9]+$ ]]; do ONLY+=("$1"); shift; done; continue ;;
    -h|--help) sed -n '2,/^set -uo/p' "$0" | sed '$d'; exit 0 ;;
    3.*) VERSIONS+=("$1") ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
  shift
done

SRC=$(git -C "$(dirname "$0")" rev-parse --show-toplevel) || exit 1
SHA=$(git -C "$SRC" rev-parse --short=8 HEAD)
PY_HELPER=${PYTHON:-python3}
HELPER=(env PYTHONDONTWRITEBYTECODE=1 "$PY_HELPER" "$SRC/scripts/release_check.py")
DEFAULT_DATA="$HOME/sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de/fds-evac-data"
export FDS_EVAC_DATA=${FDS_EVAC_DATA:-$DEFAULT_DATA}
export HEAT_RADIOMETER_DATA=${HEAT_RADIOMETER_DATA:-$FDS_EVAC_DATA/heat_radiometer}
[ ${#VERSIONS[@]} -gt 0 ] || read -r -a VERSIONS <<< "$("${HELPER[@]}" versions)"
REPORT=${REPORT:-$PWD/release-check-$SHA.md}
mkdir -p "$(dirname "$REPORT")" || exit 1
REPORT=$(cd "$(dirname "$REPORT")" && pwd)/$(basename "$REPORT")
LOGS=${REPORT%.md}.logs
TMP=$(mktemp -d "${TMPDIR:-/tmp}/release-check.XXXXXX")
REPO=$TMP/repo
RESULTS=$TMP/results.tsv
rm -rf "$LOGS"; mkdir -p "$LOGS"; : > "$RESULTS"

has_gate() { [[ ",$GATES," == *",$1,"* ]]; }
row() { printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >> "$RESULTS"; echo "[$4] $1 / $2 / $3  $6"; }
cleanup() {
  git -C "$SRC" worktree remove --force "$REPO" >/dev/null 2>&1
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "release check of $SHA ($MODE), Python ${VERSIONS[*]}, data: $FDS_EVAC_DATA"
[ -z "$(git -C "$SRC" status --porcelain --untracked-files=no)" ] \
  || echo "note: uncommitted changes are not checked; the check runs on HEAD $SHA"
[ -d "$FDS_EVAC_DATA" ] || row data "$FDS_EVAC_DATA" exists FAIL 0 "data store not found; set FDS_EVAC_DATA"
git -C "$SRC" worktree add --detach --quiet "$REPO" HEAD || exit 1
cd "$REPO" || exit 1

# The wheel of HEAD, built before any gate rewrites files of the checkout.
if has_gate install; then
  start=$SECONDS
  if uv build --wheel --out-dir "$TMP/dist" > "$LOGS/uv_build.log" 2>&1; then
    row install wheel "uv build --wheel" PASS $((SECONDS - start)) "$(basename "$TMP"/dist/*.whl)"
  else
    row install wheel "uv build --wheel" FAIL $((SECONDS - start)) "see $LOGS/uv_build.log"
  fi
fi

# One uv environment per Python version, outside the checkout.
sync_env() {  # version
  export UV_PROJECT_ENVIRONMENT=$TMP/venv-$1
  uv sync --quiet --all-groups --extra gui --python "$1" > "$LOGS/uv_sync_$1.log" 2>&1
}

# --- bundles build (first, so the README.txt files name a clean commit) ----
if has_gate bundles || has_gate site; then
  sync_env "${VERSIONS[0]}" || row setup "uv sync" "Python ${VERSIONS[0]}" FAIL 0 "see $LOGS/uv_sync_${VERSIONS[0]}.log"
  start=$SECONDS
  if uv run python scripts/docs/bundle_examples.py > "$LOGS/bundle_examples.log" 2>&1; then
    row site bundle_examples.py build PASS $((SECONDS - start)) "$(grep -c '^wrote' "$LOGS/bundle_examples.log") zips"
  else
    row site bundle_examples.py build FAIL $((SECONDS - start)) "$(tail -1 "$LOGS/bundle_examples.log")"
  fi
fi

# --- tests -----------------------------------------------------------------
if has_gate tests; then
  for v in "${VERSIONS[@]}"; do
    start=$SECONDS
    if ! sync_env "$v"; then
      row tests "Python $v" "uv sync" FAIL $((SECONDS - start)) "see $LOGS/uv_sync_$v.log"
      continue
    fi
    uv run --python "$v" pytest -q -m external_data --collect-only \
      > "$LOGS/external_ids_$v.txt" 2>&1
    uv run --python "$v" pytest -q -rs -o junit_family=xunit1 \
      --junitxml="$LOGS/pytest_$v.xml" > "$LOGS/pytest_$v.log" 2>&1
    rc=$?
    "${HELPER[@]}" external-skips --junit "$LOGS/pytest_$v.xml" \
      --ids "$LOGS/external_ids_$v.txt" --python "$v" --pytest-rc $rc \
      --seconds $((SECONDS - start)) --results "$RESULTS"
  done
fi

# --- install ---------------------------------------------------------------
if has_gate install && [ -n "$(ls "$TMP"/dist/*.whl 2>/dev/null)" ]; then
  "${HELPER[@]}" install --wheel "$TMP"/dist/*.whl --repo "$REPO" \
    --work "$TMP/work" --logs "$LOGS" --results "$RESULTS" \
    --python "${VERSIONS[@]}"
fi

# --- bundles ---------------------------------------------------------------
if has_gate bundles; then
  "${HELPER[@]}" bundles --repo "$REPO" --work "$TMP/work" --logs "$LOGS" \
    --results "$RESULTS" --python "${VERSIONS[0]}" --only ${ONLY[@]+"${ONLY[@]}"}
fi

# --- docs ------------------------------------------------------------------
if has_gate docs; then
  sync_env "${VERSIONS[0]}"
  "${HELPER[@]}" docs --repo "$REPO" --work "$TMP/work" --logs "$LOGS" \
    --results "$RESULTS" --data "$FDS_EVAC_DATA" --mode "$MODE" \
    --python "${VERSIONS[0]}" --only ${ONLY[@]+"${ONLY[@]}"}
  git status --porcelain > "$LOGS/changed_files.txt"
  echo "files the documented commands changed: $(wc -l < "$LOGS/changed_files.txt") (see $LOGS/changed_files.txt)"
fi

# --- site ------------------------------------------------------------------
if has_gate site; then
  start=$SECONDS
  if (cd site && hugo --panicOnWarning --destination "$TMP/public") > "$LOGS/hugo.log" 2>&1; then
    row site hugo "--panicOnWarning" PASS $((SECONDS - start)) "$(grep -E 'Pages' "$LOGS/hugo.log" | tr -s ' ' | head -1)"
  else
    row site hugo "--panicOnWarning" FAIL $((SECONDS - start)) "$(grep -m1 -E 'ERROR|WARN' "$LOGS/hugo.log")"
  fi
fi

"${HELPER[@]}" report --results "$RESULTS" --out "$REPORT" \
  --title "$SHA ($MODE), Python ${VERSIONS[*]}"
status=$?
echo "report: $REPORT; logs: $LOGS"
exit $status
