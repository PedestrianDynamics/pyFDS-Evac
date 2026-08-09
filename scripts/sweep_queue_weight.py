#!/usr/bin/env python3
"""Sweep the route-cost queue weight against Fahy Table 2's front-door share.

    .venv/bin/python scripts/sweep_queue_weight.py

The Station asset ships no ``routing`` block, so it runs on the library
defaults. This script writes one scenario bundle per (w_queue, seed) into the
output directory -- the committed asset is never edited -- runs each with
``run.py``, and scores it with ``assets/station_fahy/validate.py``'s own
``observed_matrix``, so the curve is directly comparable to the shares reported
in the validation table.

``w_queue`` is read from the scenario in exactly one place
(``RouteCostConfig.from_routing_params``), and the initial exit assignment uses
the same config object as rerouting (``scenario.py``), so injecting the block
sweeps both the opening choice and every re-evaluation.

Outputs, under ``--out``:

    sweep.csv          one row per (w_queue, seed): front-door share, per-door
                       shares, evacuation counts
    summary.csv        mean/min/max front-door share per w_queue
    sweep.png          front-door share vs w_queue, with Fahy's 52.9 % marked
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSET = REPO / "assets" / "station_fahy"
sys.path.insert(0, str(ASSET))

import fahy_table2 as F  # noqa: E402
import validate as V  # noqa: E402

# The grid reported in docs/routing.md and on #88. The cluster between 0.02 and
# 0.05 is where the front-door share crosses Fahy's 52.9 %, so the calibrated
# 0.03 is a point the defaults actually visit -- running this script with no
# flags reproduces the published table.
DEFAULT_WEIGHTS = (0.0, 0.02, 0.03, 0.035, 0.04, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0)
DEFAULT_SEEDS = (420, 421, 422)


def write_variant(out_dir: Path, w_queue: float, seed: int) -> tuple[Path, str]:
    """Write a scenario bundle whose only change is ``routing.w_queue``.

    Returns the bundle and a digest of what was written, so a reused trajectory
    can be checked against the deck it actually came from.
    """
    bundle = out_dir / "variants" / f"wq{w_queue:g}_seed{seed}"
    bundle.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((ASSET / "config.json").read_text())
    cfg["routing"] = dict(cfg.get("routing") or {}, w_queue=w_queue)
    config_text = json.dumps(cfg)
    geometry_text = (ASSET / "geometry.wkt").read_text()
    (bundle / "config.json").write_text(config_text)
    (bundle / "geometry.wkt").write_text(geometry_text)
    digest = hashlib.sha256(f"{config_text}{geometry_text}{seed}".encode()).hexdigest()
    return bundle, digest


def run_one(job: tuple[float, int, str, bool]) -> dict:
    """Run one (w_queue, seed) point and return its scored row.

    A run that dies inside the solver (JuPedSim can push an agent outside the
    accessible area on this geometry) is reported as a failed point rather than
    taking the whole sweep down with it -- one lost seed should not cost the
    other twenty-six.
    """
    w_queue, seed, out, reuse = job
    out_dir = Path(out)
    bundle, digest = write_variant(out_dir, w_queue, seed)
    sqlite = bundle / "run.sqlite"
    log = bundle / "run.log"
    stamp = bundle / "deck.sha256"
    # Only reuse a trajectory that came from this exact deck and seed. Rebuilding
    # the asset (build_scenario.py) changes the digest, so a stale run.sqlite is
    # rerun instead of being silently scored against labels it never saw.
    reusable = (
        reuse
        and sqlite.exists()
        and stamp.exists()
        and stamp.read_text().strip() == digest
    )
    if not reusable:
        with log.open("w") as handle:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "run.py"),
                    "--scenario",
                    str(bundle),
                    "--seed",
                    str(seed),
                    "--output-sqlite",
                    str(sqlite),
                    "--cleanup",
                ],
                cwd=REPO,
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode != 0:
            return {"w_queue": w_queue, "seed": seed, "status": f"see {log}"}
        stamp.write_text(digest)
    matrix, stuck = V.observed_matrix(sqlite, ASSET / "config.json", reach=2.0)
    total = sum(sum(v.values()) for v in matrix.values())
    row = {
        "w_queue": w_queue,
        "seed": seed,
        "status": "ok",
        "source": "reused" if reusable else "fresh",
        "reached_door": total,
        "never_reached": sum(stuck.values()),
        "row_mad": row_deviations(matrix),
    }
    for door in F.DOORS:
        n = sum(v.get(door, 0) for v in matrix.values())
        row[f"share_{door}"] = n / total if total else 0.0
    return row


def row_deviations(matrix: dict) -> float:
    """Mean |observed - Fahy| over every scored (origin row, door) cell.

    The front-door share is an aggregate, so a weight can hit it while getting
    the origin-to-door structure wrong. This is the companion number that says
    whether it did.
    """
    devs = []
    for row in F.PLACEABLE:
        target = F.door_shares(row)
        obs = matrix.get(row, {})
        n = sum(obs.values())
        if not target or not n:
            continue
        devs += [abs(obs.get(d, 0) / n - target[d]) for d in F.DOORS]
    return sum(devs) / len(devs) if devs else 0.0


def summarise(rows: list[dict]) -> list[dict]:
    """Collapse the per-seed rows to one row per ``w_queue``."""
    by_weight: dict[float, list[dict]] = {}
    for row in rows:
        if row["status"] != "ok":
            continue
        by_weight.setdefault(row["w_queue"], []).append(row)
    out = []
    for w_queue in sorted(by_weight):
        group = by_weight[w_queue]
        shares = [r["share_front"] for r in group]
        mads = [r["row_mad"] for r in group]
        out.append(
            {
                "w_queue": w_queue,
                "n_seeds": len(shares),
                "front_mean": sum(shares) / len(shares),
                "front_min": min(shares),
                "front_max": max(shares),
                "row_mad_mean": sum(mads) / len(mads),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        fields += [k for k in row if k not in fields]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)


def plot(summary: list[dict], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    target = F.aggregate_door_shares()["front"]
    weights = [s["w_queue"] for s in summary]
    means = [s["front_mean"] for s in summary]
    lo = [s["front_mean"] - s["front_min"] for s in summary]
    hi = [s["front_max"] - s["front_mean"] for s in summary]

    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    ax.errorbar(
        weights,
        means,
        yerr=[lo, hi],
        marker="o",
        capsize=3,
        color="#1f77b4",
        label="front-door share",
    )
    ax.axhline(target, color="#d62728", ls="--", label=f"Fahy {target:.1%}")
    ax.set_xlabel("$w_{queue}$")
    ax.set_ylabel("front-door share of door users")
    ax.set_title("Station: front-door share vs queue weight (rerouting on)")

    twin = ax.twinx()
    twin.plot(
        weights,
        [s["row_mad_mean"] for s in summary],
        marker="s",
        ls=":",
        color="#7f7f7f",
        label="mean row deviation",
    )
    twin.set_ylabel("mean |observed - Fahy| per row/door cell")
    handles, labels = ax.get_legend_handles_labels()
    h2, l2 = twin.get_legend_handles_labels()
    ax.legend(handles + h2, labels + l2, loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "results" / "queue_weight_sweep")
    ap.add_argument("--weights", type=float, nargs="+", default=list(DEFAULT_WEIGHTS))
    ap.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument(
        "--reuse-existing",
        action="store_true",
        help="score a point from its existing run.sqlite instead of rerunning it",
    )
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    jobs = [
        (w, s, str(args.out), args.reuse_existing)
        for w in args.weights
        for s in args.seeds
    ]
    print(f"{len(jobs)} runs, {args.jobs} at a time -> {args.out}", flush=True)

    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(run_one, jobs):
            rows.append(row)
            detail = (
                f"front={row['share_front']:.1%}  "
                f"(n={row['reached_door']}, stuck={row['never_reached']}, "
                f"{row['source']})"
                if row["status"] == "ok"
                else f"FAILED, {row['status']}"
            )
            print(
                f"  w_queue={row['w_queue']:<5g} seed={row['seed']}  {detail}",
                flush=True,
            )

    rows.sort(key=lambda r: (r["w_queue"], r["seed"]))
    write_csv(args.out / "sweep.csv", rows)
    summary = summarise(rows)
    write_csv(args.out / "summary.csv", summary)
    plot(summary, args.out / "sweep.png")

    target = F.aggregate_door_shares()["front"]
    print(
        f"\n{'w_queue':>8s} {'front (mean)':>13s} {'range':>16s} "
        f"{'row MAD':>9s}   Fahy {target:.1%}"
    )
    for s in summary:
        print(
            f"{s['w_queue']:8g} {s['front_mean']:12.1%}  "
            f"{s['front_min']:6.1%}-{s['front_max']:<6.1%} "
            f"{s['row_mad_mean']:9.1%}  n={s['n_seeds']}"
        )
    failed = [r for r in rows if r["status"] != "ok"]
    if failed:
        print(f"\n{len(failed)} run(s) failed and are excluded from the means:")
        for r in failed:
            print(f"  w_queue={r['w_queue']:g} seed={r['seed']}  {r['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
