"""A/B two checkouts on one deck: trajectories row by row, and wall time.

Runs ``run.py`` from a baseline and a candidate checkout with the same
arguments, then compares ``trajectory_data`` (``frame, id, pos_x, pos_y,
ori_x, ori_y``, ordered by ``frame, id``) for exact equality. Each side runs
in its own interpreter with ``PYTHONPATH`` and working directory set to its
checkout, so relative asset paths resolve per side and an editable install of
another branch is not picked up. The module path each side imports is printed
as a check.

The baseline should be a clean checkout of the commit the candidate
branches from, e.g. a detached worktree::

    git worktree add --detach /tmp/fds-evac-main origin/main

Usage::

    python scripts/ab_trajectories.py --base /tmp/fds-evac-main --cand . \\
        [--repeat 3] [--out DIR] -- --scenario assets/t_junction/config_full.json \\
        --fds-dir $D/t_junction/fire_2MW_PVC

Everything after ``--`` goes to ``run.py``; ``--output-sqlite`` is added by
this script. Outputs go to ``--out`` or a temporary directory, never into
either checkout. Exit status is 0 if every candidate run matches the first
baseline run, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

COLUMNS = ("frame", "id", "pos_x", "pos_y", "ori_x", "ori_y")


def _env(checkout: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(checkout)
    return env


def _imported_from(python: str, checkout: Path) -> str:
    """Import what run.py imports once, untimed, and return the module path.

    This also warms the interpreter, bytecode and matplotlib caches, so the
    first timed run of a side is not a cold start.
    """
    code = (
        "import matplotlib.pyplot, pyfds_evac, pyfds_evac.core.scenario; "
        "print(pyfds_evac.__file__)"
    )
    out = subprocess.run(
        [python, "-c", code],
        cwd=checkout,
        env=_env(checkout),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _run(python: str, checkout: Path, run_args: list[str], sqlite: Path) -> float:
    cmd = [python, "run.py", *run_args, "--output-sqlite", str(sqlite)]
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=checkout,
        env=_env(checkout),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    wall = time.perf_counter() - start
    # 2: the run reached its time limit with agents inside (#443); its
    # trajectories are written and are compared like any other run.
    if proc.returncode not in (0, 2):
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f"run.py failed in {checkout} (exit {proc.returncode})")
    return wall


def _rows(sqlite: Path) -> list[tuple]:
    con = sqlite3.connect(sqlite)
    try:
        cols = ", ".join(COLUMNS)
        return con.execute(
            f"SELECT {cols} FROM trajectory_data ORDER BY frame, id"
        ).fetchall()
    finally:
        con.close()


def compare(a: Path, b: Path) -> tuple[bool, str]:
    """Return (identical, message) for two trajectory databases."""
    rows_a, rows_b = _rows(a), _rows(b)
    for i, (ra, rb) in enumerate(zip(rows_a, rows_b)):
        if ra != rb:
            return False, (
                f"first difference at row {i}:\n"
                f"  base {dict(zip(COLUMNS, ra))}\n"
                f"  cand {dict(zip(COLUMNS, rb))}"
            )
    if len(rows_a) != len(rows_b):
        return False, f"row counts differ: base {len(rows_a)}, cand {len(rows_b)}"
    return True, f"identical ({len(rows_a)} rows)"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    run_args: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, run_args = argv[:split], argv[split + 1 :]
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", type=Path, required=True, help="baseline checkout")
    parser.add_argument("--cand", type=Path, required=True, help="candidate checkout")
    parser.add_argument("--repeat", type=int, default=3, help="runs per side")
    parser.add_argument("--python", default=sys.executable, help="interpreter")
    parser.add_argument("--out", type=Path, help="output dir (default: temp dir)")
    args = parser.parse_args(argv)
    if not run_args:
        parser.error("pass run.py arguments after --")
    if "--output-sqlite" in run_args:
        parser.error("--output-sqlite is set by this script")

    out = args.out or Path(tempfile.mkdtemp(prefix="ab-trajectories-"))
    out.mkdir(parents=True, exist_ok=True)
    # One matplotlib cache for every run, so no run rebuilds the font cache.
    os.environ.setdefault("MPLCONFIGDIR", str(out / "mplconfig"))
    sides = {"base": args.base.resolve(), "cand": args.cand.resolve()}
    for name, checkout in sides.items():
        print(f"{name}: {checkout}\n  imports {_imported_from(args.python, checkout)}")

    walls: dict[str, list[float]] = {name: [] for name in sides}
    dbs: dict[str, list[Path]] = {name: [] for name in sides}
    for i in range(args.repeat):
        # Alternate the order so a warm cache does not favour one side.
        order = ("base", "cand") if i % 2 == 0 else ("cand", "base")
        for name in order:
            sqlite = out / f"{name}_{i}.sqlite"
            walls[name].append(_run(args.python, sides[name], run_args, sqlite))
            dbs[name].append(sqlite)
            print(f"  {name} run {i}: {walls[name][-1]:.2f} s", flush=True)

    ok = True
    reference = dbs["base"][0]
    for name in sides:
        for i, db in enumerate(dbs[name]):
            if db == reference:
                continue
            same, message = compare(reference, db)
            ok &= same
            print(f"base_0 vs {name}_{i}: {message}")

    for name in sides:
        runs = ", ".join(f"{w:.2f}" for w in walls[name])
        print(f"{name} wall times: {runs} s")
    base_best, cand_best = min(walls["base"]), min(walls["cand"])
    print(
        "wall time (best of {n}): base {b:.2f} s, cand {c:.2f} s, {d:+.1f} %".format(
            n=args.repeat,
            b=base_best,
            c=cand_best,
            d=100.0 * (cand_best - base_best) / base_best,
        )
    )
    print(f"outputs in {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
