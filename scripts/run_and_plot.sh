#!/usr/bin/env bash
# Run one smoke-coupled simulation and produce the full plot set.
#
# Usage:
#   scripts/run_and_plot.sh <scenario.json> <fds-dir> <results-dir>
#
# Example:
#   scripts/run_and_plot.sh assets/demo/config.json fds_directory/demo results/demo
#
# See docs/usage.md for the per-script options.

set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "usage: $0 <scenario.json> <fds-dir> <results-dir>" >&2
    exit 2
fi

SCENARIO="$1"
FDS_DIR="$2"
RESULTS_DIR="$3"

mkdir -p "$RESULTS_DIR" "$RESULTS_DIR/fed_per_agent"

SQLITE="$RESULTS_DIR/trajectory.sqlite"
SMOKE_CSV="$RESULTS_DIR/smoke.csv"
FED_CSV="$RESULTS_DIR/fed.csv"
ROUTES_CSV="$RESULTS_DIR/routes.csv"
ROUTE_COSTS_CSV="$RESULTS_DIR/route_costs.csv"
VIS_CACHE="$FDS_DIR/vismap_cache.pkl"

echo "==> Simulation"
uv run python run.py \
    --scenario "$SCENARIO" \
    --fds-dir "$FDS_DIR" \
    --output-sqlite "$SQLITE" \
    --output-smoke-history "$SMOKE_CSV" \
    --output-fed-history "$FED_CSV" \
    --output-route-history "$ROUTES_CSV" \
    --output-route-cost-history "$ROUTE_COSTS_CSV" \
    --enable-rerouting \
    --vis-cache "$VIS_CACHE"

echo "==> FED spaghetti"
uv run python scripts/plot_fed_history.py "$FED_CSV" \
    --output "$RESULTS_DIR/fed.png"

echo "==> FED rate"
uv run python scripts/plot_fed_history.py "$FED_CSV" --show-rate \
    --output "$RESULTS_DIR/fed_rate.png"

echo "==> Per-agent FED stacks"
uv run python scripts/plot_fed_history.py "$FED_CSV" \
    --stack-all "$RESULTS_DIR/fed_per_agent"

echo "==> Speed vs FED"
uv run python scripts/plot_fed_history.py "$FED_CSV" --speed-vs-fed \
    --output "$RESULTS_DIR/speed_vs_fed.png"

echo "==> Trajectories coloured by speed"
uv run python scripts/plot_trajectories_by_speed.py "$FED_CSV" \
    --sqlite "$SQLITE" \
    --output "$RESULTS_DIR/trajectories_by_speed.png"

echo "==> Smoke history (aggregate)"
uv run python scripts/plot_smoke_history.py \
    --input "$SMOKE_CSV" --output "$RESULTS_DIR/smoke.png"

echo "==> Route costs"
uv run python scripts/plot_route_costs.py \
    "$ROUTE_COSTS_CSV" "$ROUTES_CSV" || true

echo "==> Exit choice"
uv run python scripts/plot_exit_choice.py \
    "$ROUTE_COSTS_CSV" "$ROUTES_CSV" "$SCENARIO" || true

echo "==> Trajectories by exit"
uv run python scripts/plot_trajectories.py \
    "$SQLITE" "$SCENARIO" "$ROUTE_COSTS_CSV" \
    "$RESULTS_DIR/trajectories_by_exit.png" || true

echo
echo "Done. Artefacts written to: $RESULTS_DIR"
