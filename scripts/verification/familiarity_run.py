"""Run a deck like ``run.py`` and also write each agent's cognitive-map history.

``run.py`` collects the history (``build_run_kwargs`` always asks for it) but
writes no file for it. The familiarity verification test needs it: it checks
the map at t = 0 and every node an agent learns later. This script takes the
same arguments as ``run.py``, runs the scenario the same way and writes the
usual outputs, plus ``--output-cognitive-map``: one CSV row each time an
agent's map grows (``time_s``, ``agent_id``, ``familiarity``, ``known_nodes``
and ``known_edges``, space-separated; an edge is ``source>target``).

Run one deck per process, from the repository root::

    uv run python scripts/verification/familiarity_run.py \\
        --scenario assets/familiarity_test_discovery --seed 420 \\
        --vis-cell-size 0.05 --output-sqlite OUT/run.sqlite \\
        --output-route-history OUT/routes.csv \\
        --output-cognitive-map OUT/cognitive_map.csv --cleanup
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import run  # noqa: E402


def write_history(rows, path):
    """Write the cognitive-map history rows as CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["time_s", "agent_id", "familiarity", "known_nodes", "known_edges"]
        )
        for r in rows:
            writer.writerow(
                [
                    f"{r['time_s']:.3f}",
                    r["agent_id"],
                    r["familiarity"],
                    " ".join(r["known_nodes"]),
                    " ".join(f"{a}>{b}" for a, b in r["known_edges"]),
                ]
            )


def main() -> int:
    parser = run._build_parser()
    parser.add_argument(
        "--output-cognitive-map",
        required=True,
        help="CSV of every change of an agent's cognitive map",
    )
    args = parser.parse_args()
    scenario = run.load_scenario(args.scenario)
    kwargs = run.build_run_kwargs(scenario, args, log=print)
    result = run.run_scenario(scenario, **kwargs)
    print(run._summary_line(result))
    write_history(result.cognitive_map_history or [], args.output_cognitive_map)
    print(f"Cognitive map rows: {len(result.cognitive_map_history or [])}")
    run.apply_outputs(result, scenario, args, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
