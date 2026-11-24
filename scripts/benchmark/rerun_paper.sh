#!/usr/bin/env bash
# Re-run the runtime table of the paper serially, then summarise it.
#
# Usage: rerun_paper.sh [--dry-run] [--with-w1b] [--outdir DIR] [--commit REV]
#
# Needs an exclusive machine and FDS_EVAC_DATA for the FDS cases (README.md).
# PYTHON selects the interpreter (default: .venv of the repository).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
py="${PYTHON:-$root/.venv/bin/python}"
outdir="$PWD/benchmark-results"
extra=()
dry=()
w1b=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) dry=(--dry-run) ;;
        --with-w1b) w1b=1 ;;
        --outdir) outdir="$2"; shift ;;
        --commit) extra+=(--commit "$2"); shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

batch() {
    "$py" "$here/benchmark.py" batch "$here/$1" --outdir "$outdir" \
        "${extra[@]+"${extra[@]}"}" "${dry[@]+"${dry[@]}"}"
}

batch paper_table.json
if [ "$w1b" = 1 ]; then
    batch paper_table_w1b.json
fi
if [ ${#dry[@]} -gt 0 ]; then
    echo "would run: $py $here/analyse.py --outdir $outdir"
    exit 0
fi
"$py" "$here/analyse.py" --outdir "$outdir"
