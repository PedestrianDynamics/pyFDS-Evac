#!/usr/bin/env bash
# Start one measured block detached, as plan.md requires: nohup + caffeinate -s,
# display put to sleep, so no agent or terminal process is busy during the runs.
#
# Usage: ./launch_detached.sh <benchmark.py run arguments>
#   e.g. ./launch_detached.sh --block G1base --case W1 --exclusive
# Log: results/blocks/<block>_<UTC time>.log ; PID file next to it.
# With --dry-run the block is planned in the foreground and the display is not touched.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PROF_PY:-/Users/chraibi/profiling-stage/wt_8f7d29a2/.venv/bin/python}
block=unnamed
prev=""
for a in "$@"; do [ "$prev" = "--block" ] && block=$a; prev=$a; done
if [[ " $* " == *" --dry-run "* ]]; then
  exec "$PY" "$HERE/benchmark.py" run "$@"
fi
mkdir -p "$HERE/results/blocks"
log="$HERE/results/blocks/${block}_$(date -u +%Y%m%dT%H%M%SZ).log"
cd "$HERE"
nohup caffeinate -s "$PY" "$HERE/benchmark.py" run "$@" > "$log" 2>&1 < /dev/null &
echo $! > "$log.pid"
echo "started block $block, pid $(cat "$log.pid"), log $log"
sleep 2
pmset displaysleepnow
