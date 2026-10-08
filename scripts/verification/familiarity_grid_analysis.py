"""Judge the #168 grid study from the lines of ``familiarity_grid_study.py``.

The rule was fixed before the run. Metric: the discovery tier's
evacuation time per run (simulation clock), an incomplete run counted as
300 s, over seeds 1-30. A halving of the grid passes when both the median
and the 90th percentile (numpy's default, linear) change by less than 5 %.
Judged halvings: 0.1 -> 0.05 m and 0.05 -> 0.025 m; 0.25 m does not
resolve the deck's walls and is reported only. The 90 % intervals are
bootstrap percentiles over 10 000 resamples (generator seed 168), paired by
seed when both samples hold all 30 runs. "Complete runs only" and the
``default_route`` arm are reported, not judged; seed 420 is reported only.

Run from the repository root::

    uv run python scripts/verification/familiarity_grid_analysis.py OUT/results.jsonl
"""

import json
import sys

import numpy as np

SEEDS = list(range(1, 31))
JUDGED = [(0.1, 0.05), (0.05, 0.025)]
TOL = 0.05
N_BOOT = 10000


def sample(rows, mode, cell, complete_only=False):
    """Per seed 1-30, the last-out time with incomplete runs at 300 s."""
    by = {
        r["seed"]: r
        for r in rows
        if r["mode"] == mode and r["cell"] == cell and r["seed"] in SEEDS
    }
    if sorted(by) != SEEDS:
        raise SystemExit(f"{mode} {cell} m: seeds {sorted(by)}, expected 1-30")
    return np.array(
        [by[s]["last_out_300"] for s in SEEDS if by[s]["complete"] or not complete_only]
    )


def stats(x):
    return np.percentile(x, 50), np.percentile(x, 90)


def boot(rng, a, b, q):
    """Bootstrap 90 % interval of the relative change of percentile q."""
    if len(a) == len(b) == len(SEEDS):
        ia = rng.integers(0, len(a), (N_BOOT, len(a)))
        ib = ia
    else:
        ia = rng.integers(0, len(a), (N_BOOT, len(a)))
        ib = rng.integers(0, len(b), (N_BOOT, len(b)))
    pa = np.percentile(a[ia], q, axis=1)
    pb = np.percentile(b[ib], q, axis=1)
    d = (pb - pa) / pa
    return np.percentile(d, 5), np.percentile(d, 95)


def report_cells(rows, mode, cells, complete_only):
    for c in cells:
        x = sample(rows, mode, c, complete_only)
        m, p = stats(x)
        mine = [
            r
            for r in rows
            if r["mode"] == mode and r["cell"] == c and r["seed"] in SEEDS
        ]
        inc = [r["seed"] for r in mine if not r["complete"]]
        tb = sum(r["turnbacks"] for r in mine)
        wd = sum(r["wander"] for r in mine)
        print(
            f"  {c:>6} m  n={len(x):2d}  median {m:6.1f}  P90 {p:6.1f}  "
            f"max {x.max():6.1f}  incomplete {inc}  wander {wd} turnbacks {tb}"
        )


def report_halvings(rng, rows, mode, cells, complete_only):
    for a_c, b_c in JUDGED:
        if a_c not in cells or b_c not in cells:
            continue
        a = sample(rows, mode, a_c, complete_only)
        b = sample(rows, mode, b_c, complete_only)
        (ma, pa), (mb, pb) = stats(a), stats(b)
        dm, dp = (mb - ma) / ma, (pb - pa) / pa
        verdict = "PASS" if abs(dm) < TOL and abs(dp) < TOL else "FAIL"
        cm, cp = boot(rng, a, b, 50), boot(rng, a, b, 90)
        print(
            f"  {a_c} -> {b_c} m: dmedian {dm:+.1%} [90% CI {cm[0]:+.1%}, "
            f"{cm[1]:+.1%}]  dP90 {dp:+.1%} [90% CI {cp[0]:+.1%}, {cp[1]:+.1%}]"
            f"  -> {verdict}"
        )


def main() -> int:
    with open(sys.argv[1]) as fh:
        rows = [json.loads(line) for line in fh]
    rng = np.random.default_rng(168)
    for mode in ("explore", "default_route"):
        cells = sorted({r["cell"] for r in rows if r["mode"] == mode}, reverse=True)
        print(f"\n== {mode} ==")
        for complete_only in (False, True):
            if complete_only:
                label = "complete runs only"
            elif mode == "explore":
                label = "all runs, incomplete = 300 s (JUDGED)"
            else:
                label = "all runs, incomplete = 300 s"
            print(f"-- {label}")
            report_cells(rows, mode, cells, complete_only)
            report_halvings(rng, rows, mode, cells, complete_only)
    print("\n-- seed 420 (deck baseSeed, reported only)")
    for r in sorted(
        (r for r in rows if r["seed"] == 420), key=lambda r: (r["mode"], -r["cell"])
    ):
        print(
            f"  {r['mode']:13s} {r['cell']:>6} m  {r['out']}/{r['total']}  "
            f"last out {r['t_end']}  wander {r['wander']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
