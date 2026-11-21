#!/bin/bash
# Copy ballroom results from JURECA to a local folder (read-only on the cluster).
#   bash fetch_ballroom.sh LOCAL_DIR [--dry-run] [--with-eff-fed]
# LOCAL_DIR e.g. ~/sciebo/fds-evac-data/cvm2-ballroom. Remote host: ssh alias
# jureca. Remote base defaults to
# /p/project1/cias-7/<remote user>/fds-evac-runs/cvm2-ballroom (override with
# REMOTE_BASE). Run directories: phase1, phase2, rep01..rep10, and the
# optional fire-test*, evac-dx050. Fetches slices (*.sf), *.smv, *.out,
# *_hrr.csv, *_devc.csv, *_evac.csv, per-repeat *_evmc.csv, decks, job logs
# and run_record/. pyFDS-Evac must read the slices of phase2, not of the
# stand-alone fire test. Skips boundary, 3D, particle and restart data.
# Evac .eff/.fed/.xyz files only with --with-eff-fed.
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
INC=(--include='*/' --include='*.sf' --include='*_evac.csv' --include='*_evmc.csv' --include='*_devc.csv' --include='*.out' --include='*.smv'
     --include='*_hrr.csv' --include='*.fds' --include='*.log' --include='*.stdout'
     --include='run_record/***')
[ "$EFF" -eq 0 ] || INC+=(--include='*.eff' --include='*.fed' --include='*.xyz')
rsync -av --partial "${DRY[@]}" "${INC[@]}" --exclude='*' "jureca:$REMOTE_BASE/" "$LOCAL/"
echo "Fetched into $LOCAL. Verdict per run directory (judged from the .out STOP line):"
for d in "$LOCAL"/*/; do
  o=$(find "$d" -maxdepth 1 -name '*.out' ! -name '*_info.out' | head -1)
  if [ -n "$o" ] && grep -q 'STOP: FDS completed successfully' "$o"; then
    echo "OK    $(basename "$d")"
  else
    echo "CHECK $(basename "$d") (no successful .out)"
  fi
done
echo "Phase 2 slices (the ones pyFDS-Evac reads): $(find "$LOCAL/phase2" -maxdepth 1 -name '*.sf' 2>/dev/null | wc -l) files"
# The seed comes from the wall clock: the repeats must differ.
shopt -s nullglob
EV=("$LOCAL"/rep*/*_evmc.csv)
echo "Repeats with an _evmc.csv: ${#EV[@]}"
if [ "${#EV[@]}" -gt 1 ]; then
  DUP=$(sha256sum "${EV[@]}" | sort | uniq -w64 -D)
  [ -z "$DUP" ] && echo "OK    the _evmc.csv files all differ" \
    || { echo "CHECK identical _evmc.csv files (same seed?):"; echo "$DUP"; }
fi
