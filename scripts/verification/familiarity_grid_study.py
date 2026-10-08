"""Run the #168 grid study: discovery egress on the familiarity deck, per seed.

The study (Verification > Familiarity, criterion 6) asks whether the
discovery tier's egress time converges with the clear-air sight grid. It
runs ``assets/familiarity_test_discovery`` as shipped (``no_known_exit:
explore``, reroute pass every 1 s, clear air, 300 s limit) on one grid for
the given seeds, and appends one JSON line per run to ``--out``.
``--mode default_route`` replaces the deck's ``no_known_exit`` for the
comparison arm; nothing else changes. ``familiarity_grid_analysis.py``
reads the lines.

Settings fixed before the run: seeds 1-30 judged (420, the deck's
baseSeed, reported only), grids 0.25, 0.1, 0.05 and 0.025 m, an
incomplete run counted as 300 s. Each line holds the commit, grid, mode,
seed, agents out, the clock at the end (``RunResult.evacuation_time``),
the route-change reasons and the CP3 turn-backs (a ``wander`` right
after reaching CP3).

Run from the repository root, one grid and mode per process (they run in
parallel), with ``PYTHONHASHSEED=0``::

    for c in 0.25 0.1 0.05 0.025; do for m in explore default_route; do
      PYTHONHASHSEED=0 uv run python scripts/verification/familiarity_grid_study.py \\
          --cell $c --mode $m --out OUT/results.jsonl $(seq 1 30) 420 &
    done; done; wait
    uv run python scripts/verification/familiarity_grid_analysis.py OUT/results.jsonl

``--keep-dir`` keeps the SQLite trajectory of every incomplete run.
"""

import argparse
import collections
import contextlib
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import run  # noqa: E402

SCENARIO = "assets/familiarity_test_discovery"
CP3 = "jps-checkpoints_3"


def commit() -> str:
    """The checked-out commit, with ``-dirty`` when the tree has changes."""
    sha = subprocess.run(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return f"{sha}-dirty" if dirty else sha


def turnbacks(route_history: list[dict]) -> int:
    """Route changes to ``wander`` right after a change to CP3, per agent."""
    by_agent = collections.defaultdict(list)
    for row in route_history:
        by_agent[row["agent_id"]].append(row)
    return sum(
        1
        for rows in by_agent.values()
        for p, q in zip(rows, rows[1:])
        if p["new_exit"] == CP3 and q["reason"] == "wander"
    )


def run_seed(scenario, kwargs, seed, cell, mode, head, max_t, keep_dir):
    """Run one seed and return its JSON record."""
    t0 = time.monotonic()
    kwargs["seed"] = seed
    with contextlib.redirect_stdout(io.StringIO()):
        result = run.run_scenario(scenario, **kwargs)
    try:
        history = result.route_history or []
        reasons = collections.Counter(row["reason"] for row in history)
        complete = result.agents_evacuated == result.total_agents
        kept = None
        if not complete and keep_dir is not None:
            kept = str(keep_dir / f"{mode}_{cell}_{seed}.sqlite")
            shutil.copy(result.sqlite_file, kept)
        t_end = round(result.evacuation_time, 2)
        return {
            "head": head,
            "cell": float(cell),
            "mode": mode,
            "seed": seed,
            "out": result.agents_evacuated,
            "total": result.total_agents,
            "complete": complete,
            "t_end": t_end,
            "last_out_300": t_end if complete else max_t,
            "reasons": dict(reasons),
            "wander": reasons.get("wander", 0),
            "turnbacks": turnbacks(history),
            "kept": kept,
            "wall": round(time.monotonic() - t0, 1),
        }
    finally:
        result.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cell", required=True, help="clear-air sight grid [m]")
    parser.add_argument(
        "--mode",
        choices=("explore", "default_route"),
        default="explore",
        help="no_known_exit of the deck's spawn groups (explore: as shipped)",
    )
    parser.add_argument("--out", type=Path, required=True, help="JSON lines, appended")
    parser.add_argument(
        "--keep-dir", type=Path, help="keep the SQLite file of incomplete runs here"
    )
    parser.add_argument("seeds", nargs="+", type=int)
    args = parser.parse_args()

    scenario = run.load_scenario(str(ROOT / SCENARIO))
    for dist in scenario.raw["distributions"].values():
        if dist["parameters"]["no_known_exit"] != "explore":
            raise SystemExit(f"{SCENARIO}: expected no_known_exit 'explore'")
        dist["parameters"]["no_known_exit"] = args.mode
    run_args = run._build_parser().parse_args(
        ["--scenario", str(ROOT / SCENARIO), "--vis-cell-size", args.cell]
    )
    with contextlib.redirect_stdout(io.StringIO()):
        kwargs = run.build_run_kwargs(scenario, run_args, log=print)
    if kwargs["reroute_config"].reevaluation_interval_s != 1.0:
        raise SystemExit(f"{SCENARIO}: expected a reroute pass every 1 s")
    max_t = float(scenario.sim_params.get("max_simulation_time", 300))
    if args.keep_dir is not None:
        args.keep_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    head = commit()
    for seed in args.seeds:
        rec = run_seed(
            scenario, kwargs, seed, args.cell, args.mode, head, max_t, args.keep_dir
        )
        with args.out.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
