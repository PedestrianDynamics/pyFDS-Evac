"""Golden runs of the FDS-backed decks, for the rerouting refactor (#187).

The CI golden test (tests/test_rerouting_golden.py) runs small decks on a
synthetic smoke field. This script runs the full decks against their real FDS
output, which lives in sciebo and not in the repository, and records what a
behaviour-preserving refactor must leave unchanged. Every deck runs twice, with
the route-cost history on and off: the history ranking shares the segment
cache with rerouting and can be the first to write an entry, so the two modes
exercise different cache contents::

    <out>/<deck>/<mode>/route_history.csv       every route switch
    <out>/<deck>/<mode>/route_cost_history.csv  every ranked candidate, every
                                                tick (mode "history_on" only)
    <out>/<deck>/<mode>/egress_summary.json     run metrics and per-agent egress
    <out>/manifest.json                         commit, runs and data root

The familiarity decks come from the repository's ``assets/`` and need no FDS
run; they include the #168 sweep of the clear-air visibility grid.

Each deck runs in its own interpreter: JuPedSim numbers agents process-wide
and the agent id seeds the reevaluation stagger, so a deck run after another
in the same process would not reproduce.

Usage::

    uv run python scripts/golden_rerouting.py --out DIR [--decks a b ...]
    uv run python scripts/golden_rerouting.py --compare DIR_A DIR_B

``--data-root`` defaults to the maintainer's sciebo ``fds-evac-data`` folder.
A deck whose files are missing there is reported and skipped. ``--compare``
reports, per run and file, which columns differ and where the first
difference is. Both runs and compare check the full inventory of the selected
decks times both history modes, and exit non-zero if a run or a file is
missing on either side, or if anything differs.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = Path(
    "/Users/chraibi/sciebo - ped23 (ped23.pbox@fz-juelich.de)"
    "@fz-juelich.sciebo.de/fds-evac-data"
)
# Route-cost history on and off. With it on, run_scenario ranks every agent's
# routes once more before rerouting, into the same segment cache.
MODES: dict[str, tuple[str, ...]] = {
    "history_on": (
        "route_history.csv",
        "route_cost_history.csv",
        "egress_summary.json",
    ),
    "history_off": ("route_history.csv", "egress_summary.json"),
}


@dataclass(frozen=True)
class GoldenDeck:
    """A deck: its config, geometry, FDS run and extra command-line options.

    Paths are relative to the data root, or to the repository when *in_repo*
    is set. A deck without *fds_dir* runs in clear air.
    """

    config: str
    geometry: str
    fds_dir: str | None
    seed: int | None = None
    in_repo: bool = False
    extra_args: tuple[str, ...] = ()


DECKS: dict[str, GoldenDeck] = {
    # Seed 1, as the archived l_corridor results were run.
    "l_corridor_gate": GoldenDeck(
        "l_corridor/evac/deck_gate/config.json",
        "l_corridor/evac/deck_gate/geometry.wkt",
        "l_corridor/fire_1MW_west",
        seed=1,
    ),
    "l_corridor_additive": GoldenDeck(
        "l_corridor/evac/deck_additive/config.json",
        "l_corridor/evac/deck_additive/geometry.wkt",
        "l_corridor/fire_1MW_west",
        seed=1,
    ),
    "world100_stream_east": GoldenDeck(
        "world100/evac_4exits/deck_config_stream_east.json",
        "world100/evac_4exits/deck_geometry.wkt",
        "world100/fire_4p5MW",
    ),
    "world100_stream_oval": GoldenDeck(
        "world100/evac_4exits/deck_config_stream_oval.json",
        "world100/evac_4exits/deck_geometry.wkt",
        "world100/fire_4p5MW",
    ),
    "world77": GoldenDeck(
        "world77/evac/deck_config.json",
        "world77/evac/deck_geometry.wkt",
        "world77/fire_2MW",
    ),
    "t_junction": GoldenDeck(
        "t_junction/evac/deck_config.json",
        "t_junction/evac/deck_geometry.wkt",
        "t_junction/fire_2MW_PVC",
    ),
    # Familiarity tiers, clear air, as docs/testing-familiarity.md runs them.
    "familiarity_test_full": GoldenDeck(
        "assets/familiarity_test_full/config.json",
        "assets/familiarity_test_full/geometry.wkt",
        None,
        seed=420,
        in_repo=True,
        extra_args=("--enable-rerouting", "--reroute-interval", "1"),
    ),
    "familiarity_test_discovery": GoldenDeck(
        "assets/familiarity_test_discovery/config.json",
        "assets/familiarity_test_discovery/geometry.wkt",
        None,
        seed=420,
        in_repo=True,
        extra_args=("--enable-rerouting", "--reroute-interval", "1"),
    ),
}
# The #168 sweep: the discovery tier's time depends on the visibility grid.
for _cell in ("0.25", "0.1", "0.05", "0.025"):
    DECKS[f"familiarity_test_discovery_cell{_cell}"] = GoldenDeck(
        "assets/familiarity_test_discovery/config.json",
        "assets/familiarity_test_discovery/geometry.wkt",
        None,
        seed=420,
        in_repo=True,
        extra_args=("--vis-cell-size", _cell),
    )


# ── Running ───────────────────────────────────────────────────────────


def _inventory(names: list[str]) -> list[tuple[str, str]]:
    """Every run the selected decks must produce: deck times history mode."""
    return [(name, mode) for name in names for mode in MODES]


def _base(deck: GoldenDeck, root: Path) -> Path:
    return REPO if deck.in_repo else root


def _missing(deck: GoldenDeck, root: Path) -> list[Path]:
    base = _base(deck, root)
    paths = [base / deck.config, base / deck.geometry]
    if deck.fds_dir is not None:
        paths.append(root / deck.fds_dir)
    return [p for p in paths if not p.exists()]


def _stage_bundle(deck: GoldenDeck, root: Path, into: Path) -> Path:
    """Copy config and geometry under the names ``load_scenario`` expects."""
    into.mkdir(parents=True, exist_ok=True)
    base = _base(deck, root)
    shutil.copy(base / deck.config, into / "config.json")
    shutil.copy(base / deck.geometry, into / "geometry.wkt")
    return into


def _run_one(name: str, mode: str, root: Path, out: Path) -> None:
    """Run one deck in one history mode, in this process, and write its outputs."""
    sys.path.insert(0, str(REPO))
    import run as cli
    from pyfds_evac.core import load_scenario, run_scenario
    from pyfds_evac.core.run_config import build_run_kwargs

    deck = DECKS[name]
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = _stage_bundle(deck, root, Path(tmp) / name)
        argv = [
            "--scenario",
            str(bundle),
            "--output-route-history",
            str(out / "route_history.csv"),
        ]
        if deck.fds_dir is not None:
            argv += ["--fds-dir", str(root / deck.fds_dir)]
        if mode == "history_on":
            argv += [
                "--output-route-cost-history",
                str(out / "route_cost_history.csv"),
            ]
        if deck.seed is not None:
            argv += ["--seed", str(deck.seed)]
        argv += list(deck.extra_args)
        opts = cli._build_parser().parse_args(argv)
        scenario = load_scenario(opts.scenario)
        result = run_scenario(scenario, **build_run_kwargs(scenario, opts, log=print))
        try:
            cli.apply_outputs(result, scenario, opts, log=print)
            summary = _egress_summary(result, scenario, deck)
            (out / "egress_summary.json").write_text(
                json.dumps(summary, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        finally:
            result.cleanup()


def _egress_summary(result, scenario, deck: GoldenDeck) -> dict:
    metrics = {k: v for k, v in result.metrics.items() if k != "walkable_polygon"}
    return {
        "deck": {
            "config": deck.config,
            "fds_dir": deck.fds_dir,
            "seed": deck.seed,
            "extra_args": list(deck.extra_args),
        },
        "metrics": metrics,
        "agents": _per_agent_egress(
            result.sqlite_file, scenario, result.agents_remaining == 0
        ),
    }


def _per_agent_egress(sqlite_file: str | None, scenario, all_out: bool) -> list[dict]:
    """First and last recorded frame per agent, and the exit it ended at.

    The trajectory is written every tenth step, so times are to 0.1 s. An
    agent counts as out when everyone got out, or when its last frame
    precedes the run's last frame.
    """
    if not sqlite_file:
        return []
    from shapely.geometry import Point, Polygon

    exits = {
        exit_id: Polygon(data["coordinates"])
        for exit_id, data in scenario.raw.get("exits", {}).items()
    }
    with sqlite3.connect(sqlite_file) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()[0]
        )
        last_frame = con.execute("SELECT MAX(frame) FROM trajectory_data").fetchone()[0]
        rows = con.execute(
            "SELECT t.id, MIN(t.frame), MAX(t.frame), e.pos_x, e.pos_y "
            "FROM trajectory_data t JOIN trajectory_data e "
            "ON e.id = t.id AND e.frame = "
            "(SELECT MAX(frame) FROM trajectory_data WHERE id = t.id) "
            "GROUP BY t.id ORDER BY t.id"
        ).fetchall()
    agents = []
    for agent_id, first, last, x, y in rows:
        position = Point(x, y)
        nearest = min(exits, key=lambda e: exits[e].distance(position), default="")
        agents.append(
            {
                "agent_id": agent_id,
                "first_time_s": round(first / fps, 2),
                "last_time_s": round(last / fps, 2),
                "evacuated": all_out or last < last_frame,
                "final_exit": nearest,
                "final_x": round(x, 3),
                "final_y": round(y, 3),
            }
        )
    return agents


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def _run_all(names: list[str], root: Path, out: Path) -> int:
    """Run the inventory of *names*; non-zero if any run could not be made."""
    out.mkdir(parents=True, exist_ok=True)
    ran, skipped = [], {}
    for name, mode in _inventory(names):
        missing = _missing(DECKS[name], root)
        if missing:
            skipped[f"{name}/{mode}"] = [str(p) for p in missing]
            print(f"MISSING {name}/{mode}: {', '.join(map(str, missing))}")
            continue
        print(f"run  {name}/{mode}")
        subprocess.run(
            [
                sys.executable,
                __file__,
                "--run-one",
                name,
                "--mode",
                mode,
                "--data-root",
                str(root),
                "--out",
                str(out / name / mode),
            ],
            check=True,
            cwd=REPO,
            stdout=subprocess.DEVNULL,
        )
        ran.append(f"{name}/{mode}")
    manifest = {
        "commit": _git("rev-parse", "HEAD"),
        "pyfds_evac_dirty": bool(_git("status", "--porcelain", "--", "pyfds_evac")),
        "data_root": str(root),
        "decks": {name: vars(DECKS[name]) for name in names},
        "runs": ran,
        "skipped": skipped,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    if skipped:
        print(f"{len(skipped)} of {len(ran) + len(skipped)} runs missing")
        return 1
    return 0


# ── Comparing ─────────────────────────────────────────────────────────


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _compare_csv(a: Path, b: Path) -> list[str]:
    cols_a, rows_a = _read_csv(a)
    cols_b, rows_b = _read_csv(b)
    report = []
    if cols_a != cols_b:
        report.append(f"columns differ: {cols_a} vs {cols_b}")
    if len(rows_a) != len(rows_b):
        report.append(f"row count {len(rows_a)} vs {len(rows_b)}")
    columns = [c for c in cols_a if c in cols_b]
    per_column: dict[str, int] = {}
    first: tuple[int, str, str, str] | None = None
    for index, (ra, rb) in enumerate(zip(rows_a, rows_b)):
        for column in columns:
            if ra[column] == rb[column]:
                continue
            per_column[column] = per_column.get(column, 0) + 1
            if first is None:
                first = (index, column, ra[column], rb[column])
    if per_column:
        counts = ", ".join(f"{c}={n}" for c, n in sorted(per_column.items()))
        report.append(f"differing cells per column: {counts}")
    if first is not None:
        index, column, va, vb = first
        report.append(
            f"first difference at row {index + 1}, {column}: {va!r} vs {vb!r}"
        )
    return report


def _flatten(value, prefix: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        flat: dict[str, object] = {}
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return flat
    if isinstance(value, list):
        flat = {}
        for index, item in enumerate(value):
            flat.update(_flatten(item, f"{prefix}[{index}]"))
        return flat
    return {prefix: value}


def _compare_json(a: Path, b: Path) -> list[str]:
    fa = _flatten(json.loads(a.read_text(encoding="utf-8")))
    fb = _flatten(json.loads(b.read_text(encoding="utf-8")))
    keys = sorted(set(fa) | set(fb))
    diffs = [k for k in keys if fa.get(k, "<missing>") != fb.get(k, "<missing>")]
    report = [
        f"{k}: {fa.get(k, '<missing>')!r} vs {fb.get(k, '<missing>')!r}"
        for k in diffs[:20]
    ]
    if len(diffs) > 20:
        report.append(f"... and {len(diffs) - 20} more")
    return report


def _compare_file(a: Path, b: Path) -> list[str]:
    if not a.exists() or not b.exists():
        return [f"missing: {a if not a.exists() else b}"]
    if a.suffix == ".csv":
        return _compare_csv(a, b)
    return _compare_json(a, b)


def _compare(dir_a: Path, dir_b: Path, names: list[str]) -> int:
    """Compare the full inventory of *names*; a missing file is a difference."""
    differs = False
    for deck, mode in _inventory(names):
        for name in MODES[mode]:
            where = f"{deck}/{mode}/{name}"
            report = _compare_file(dir_a / where, dir_b / where)
            status = "DIFF" if report else "same"
            print(f"{status}  {where}")
            for line in report:
                print(f"      {line}")
            differs = differs or bool(report)
    print("differences found" if differs else "identical")
    return 1 if differs else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="Folder to write the runs to")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="The fds-evac-data folder holding the decks and FDS runs",
    )
    parser.add_argument(
        "--decks",
        nargs="+",
        choices=sorted(DECKS),
        default=sorted(DECKS),
        help="Decks to run (default: all)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        type=Path,
        metavar=("A", "B"),
        help="Compare two output folders instead of running",
    )
    parser.add_argument("--run-one", choices=sorted(DECKS), help=argparse.SUPPRESS)
    parser.add_argument(
        "--mode", choices=sorted(MODES), default="history_on", help=argparse.SUPPRESS
    )
    args = parser.parse_args()

    if args.compare:
        return _compare(*args.compare, args.decks)
    if args.out is None:
        parser.error("--out is required unless --compare is given")
    if args.run_one:
        _run_one(args.run_one, args.mode, args.data_root, args.out)
        return 0
    return _run_all(args.decks, args.data_root, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
