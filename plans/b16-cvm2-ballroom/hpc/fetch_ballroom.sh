#!/bin/bash
# Copy ballroom results from JURECA to a local folder (read-only on the cluster).
#   bash fetch_ballroom.sh LOCAL_DIR [--dry-run] [--with-eff-fed]
# LOCAL_DIR e.g. ~/sciebo/fds-evac-data/cvm2-ballroom. Remote host: ssh alias
# jureca. Remote base defaults to
# /p/project1/cias-7/<remote user>/fds-evac-runs/cvm2-ballroom (override with
# REMOTE_BASE). Fetches slices (*.sf), *_evac.csv, *.out, *.smv, *_hrr.csv,
# decks, job logs and run_record/. Skips boundary, 3D, particle and restart
# data. Evac .eff/.fed files only with --with-eff-fed.
set -euo pipefail
LOCAL="${1:?usage: fetch_ballroom.sh LOCAL_DIR [--dry-run] [--with-eff-fed]}"
shift
DRY=()
EFF=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=(-n);;
    --with-eff-fed) EFF=1;;
    *) echo "FAIL: unknown argument $a" >&2; exit 2;;
  esac
done
RUSER="$(ssh jureca 'echo $USER')"
[ -n "$RUSER" ] || { echo "FAIL: cannot read remote user over ssh jureca" >&2; exit 1; }
REMOTE_BASE="${REMOTE_BASE:-/p/project1/cias-7/$RUSER/fds-evac-runs/cvm2-ballroom}"
ssh jureca "test -d '$REMOTE_BASE'" || { echo "FAIL: $REMOTE_BASE missing on jureca" >&2; exit 1; }
mkdir -p "$LOCAL"
INC=(--include='*/' --include='*.sf' --include='*_evac.csv' --include='*.out' --include='*.smv'
     --include='*_hrr.csv' --include='*.fds' --include='*.log' --include='*.stdout'
     --include='run_record/***')
[ "$EFF" -eq 0 ] || INC+=(--include='*.eff' --include='*.fed')
rsync -av --partial "${DRY[@]}" "${INC[@]}" --exclude='*' "jureca:$REMOTE_BASE/" "$LOCAL/"
echo "Fetched into $LOCAL. Verdict per run directory (judged from the .out STOP line):"
for d in "$LOCAL"/*/; do
  o=$(find "$d" -maxdepth 1 -name '*.out' | head -1)
  if [ -n "$o" ] && grep -q 'STOP: FDS completed successfully' "$o"; then
    echo "OK    $(basename "$d")"
  else
    echo "CHECK $(basename "$d") (no successful .out)"
  fi
done
