#!/usr/bin/env bash
# Run the evacuation arms x 10 seeds on one FDS output (no FDS run is started).
#
# Usage, from the repository root or the unpacked zip:
#   assets/schroeder2015_route/run_p1.sh FDS_DIR OUT [JOBS] [--with-nofire]
#
# FDS_DIR holds the finished FDS run of one deck (a047_pvc_h40, a047_pvc_h35
# or a012_pvc_h30). OUT is a new folder outside the repository. Set PY to the
# Python of the pyFDS-Evac environment (default: python). Writes, per arm and
# seed, <arm>_s<seed>.sqlite, .manifest.json, _rh.csv (route history),
# _exit.csv (exit history), _fed.csv.gz, _rc.csv.gz (route costs, coupled
# arms) and _log.txt.gz. Arms: nf (no fire, only with --with-nofire), sb
# (smoke-blind), gate, add (additive).
set -euo pipefail
FDS=$(cd "$1" && pwd); OUT=$2; JOBS=${3:-6}; NOFIRE=${4:-}
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-python}
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
cp "$HERE/evac/config_gate.json" "$HERE/evac/config_additive.json" "$HERE/evac/geometry.wkt" "$OUT/"

run() {  # arm seed
  local arm=$1 s=$2 cfg=config_gate.json extra=()
  case $arm in
    nf) ;;
    sb) extra=(--fds-dir "$FDS" --smoke-blind) ;;
    gate) extra=(--fds-dir "$FDS" --output-route-cost-history "$OUT/${arm}_s${s}_rc.csv") ;;
    add) cfg=config_additive.json
         extra=(--fds-dir "$FDS" --output-route-cost-history "$OUT/${arm}_s${s}_rc.csv") ;;
  esac
  [ "$arm" = nf ] || extra+=(--output-fed-history "$OUT/${arm}_s${s}_fed.csv")
  $PY run.py --scenario "$OUT/$cfg" --seed "$s" "${extra[@]}" \
     --output-sqlite "$OUT/${arm}_s${s}.sqlite" --cleanup \
     --output-route-history "$OUT/${arm}_s${s}_rh.csv" \
     --output-exit-history "$OUT/${arm}_s${s}_exit.csv" > "$OUT/${arm}_s${s}_log.txt" 2>&1 \
     || [ $? -eq 2 ] \
     || echo "FAILED $arm s$s" >> "$OUT/failures.txt"  # 2: incomplete run, not a failure
  gzip -f "$OUT/${arm}_s${s}_log.txt"
  for f in "$OUT/${arm}_s${s}_fed.csv" "$OUT/${arm}_s${s}_rc.csv"; do [ -f "$f" ] && gzip -f "$f"; done
  return 0
}
export -f run; export OUT FDS PY

ARMS="sb gate add"; [ "$NOFIRE" = --with-nofire ] && ARMS="nf $ARMS"
# One sequential FDS read first, so fdsreader's cache exists before parallel reads.
run sb 1
for a in $ARMS; do for s in $(seq 1 10); do
  [ "$a $s" = "sb 1" ] || echo "$a $s"; done; done | xargs -P "$JOBS" -n 2 bash -c 'run "$0" "$1"'
if [ -f "$OUT/failures.txt" ]; then
  cat "$OUT/failures.txt" >&2
  echo "some runs failed; see $OUT/<arm>_s<seed>_log.txt.gz" >&2
  exit 1
fi
echo "done $OUT"
