#!/usr/bin/env bash
# Re-run the runtime table of the paper serially, then summarise it.
#
# Usage: rerun_paper.sh [--dry-run] [--with-w1b] [--outdir DIR] [--commit REV]
#                       [--checkout DIR]
#
# Needs an exclusive machine and FDS_EVAC_DATA for the FDS cases (README.md).
# PYTHON selects the interpreter (default: .venv of the checkout, else of the
# repository holding this script). --checkout runs a checkout of another commit
# (for example the submission tag) with this harness, which that commit lacks.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
outdir="$PWD/benchmark-results"
extra=()
checkout=""
dry=()
w1b=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) dry=(--dry-run) ;;
        --with-w1b) w1b=1 ;;
        --outdir) outdir="$2"; shift ;;
        --commit) extra+=(--commit "$2"); shift ;;
        --checkout) checkout="$2"; extra+=(--checkout "$2"); shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

py="${PYTHON:-${checkout:-$root}/.venv/bin/python}"

batch() {
    "$py" "$here/benchmark.py" batch "$here/$1" --outdir "$outdir" \
        "${extra[@]+"${extra[@]}"}" "${dry[@]+"${dry[@]}"}"
}

rc=0
worst() { [ "$1" -gt "$rc" ] && rc=$1; return 0; }
batch paper_table.json || worst $?
if [ "$w1b" = 1 ]; then
    batch paper_table_w1b.json || worst $?
fi
if [ ${#dry[@]} -gt 0 ]; then
    echo "would run: $py $here/analyse.py --outdir $outdir"
    exit "$rc"
fi
"$py" "$here/analyse.py" --outdir "$outdir" || worst $?
exit "$rc"
