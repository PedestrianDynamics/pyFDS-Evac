"""Route choice in smoke after Schröder et al. (2015): evacuation tables and figures.

Geometry after B. Schröder, D. Haensel, M. Chraibi, L. Arnold, A. Seyfried,
E. Andresen, "Knowledge- and perception-based route choice modelling in case
of fire", Proc. 6th Int. Symp. Human Behaviour in Fire (2015), pp. 327-338,
Fig. 6 (p. 335), https://juser.fz-juelich.de/record/255940. No data from
the authors is used: the fire, the FDS runs and the evacuation runs are ours.
The inputs are in ``assets/schroeder2015_route/``.

``DATA`` is the study folder with the finished runs:

* ``p1_<fire>[_<commit>]/<arm>_s<seed>.*``: arms ``nf`` (no fire, main
  fire folder only), ``sb`` (smoke-blind), ``gate`` and ``add`` (additive),
  written by ``assets/schroeder2015_route/run_p1.sh``;
* optional: ``p0a_nofire_100e91dd/nf_s<seed>.sqlite``, the clear-air runs
  of the study (identical to the ``nf`` arm, which is used without it), and
  ``p0a_nofire/``, the same before the fix of #350 (commit b42f07ef);
* ``<fire>/``: the FDS output of the three fires (for the heat estimate and
  the route figure).

Run from the repository root::

    uv run python scripts/docs/schroeder2015_route.py --data DATA [--cache DIR]

``--cache`` keeps the per-agent table between runs (about 2 min to build).
The script prints every number of the page's evacuation sections as
Markdown tables and writes the figures to
``site/static/images/studies/schroeder2015/``.

Measures. Door: the first trajectory point with x < 0.1 m, door A if its
y < 12 m, else B. Exit: the exit history (taken, or headed for at 400 s).
50 % boundary: logistic fit of P(door B | start y) per seed (Nelder-Mead),
95 % CI by a percentile bootstrap over agents (400 resamples); a seed with
fewer than 5 agents on the minority door is censored. Shift: dy =
boundary(arm, seed) - boundary(clear air, seed), positive toward door B,
i.e. more agents use door A; t-based 95 % CI over seeds. Criterion 2: the
mean paired change of the exit-E share against smoke-blind exceeds 2 x SD of
the smoke-blind per-seed E shares. Post hoc, added after the numbers were
seen: the sign count, the door share by movement start, the door
predictors, the boundary validity and the heat estimate.
"""

import argparse
import gzip
import importlib.util
import sqlite3
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import fdsreader
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import BoundaryNorm
from scipy import stats
from scipy.optimize import brentq, minimize

from pyfds_evac.core.fed import HEAT_CLOTHING_LAWS

fdsreader.settings.ENABLE_CACHING = False

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "studies" / "schroeder2015"
MAIN = "a047_pvc_h40"
COMPARE = ["a012_pvc_h30", "a047_pvc_h35"]
FIRES = [MAIN, "a047_pvc_h35", "a012_pvc_h30"]
ARMS = {"nf": "no fire", "sb": "smoke-blind", "gate": "gate", "add": "additive"}
SEEDS = range(1, 11)
CAP = 400.0
FPS = 10.0
HALL = "jps-distributions_0"
DOOR_XY = {"A": (0.1, 1.6), "B": (0.1, 21.6)}
EXIT_XY = {"E": (-2.6, -10.0), "F": (-2.6, 35.0)}
N_BOOT = 400
MIN_MINORITY = 5
BINS = np.arange(0, 391, 30.0)
MIN_POOLED = 20
# The bootstrap consumes this generator in groupby order (clear air first);
# the reviewed tables were made with the same order.
RNG = np.random.default_rng(20261001)
JITTER = np.random.default_rng(1)
LEGEND = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)
ARM_COL = {"nf": "#999999", "sb": "#4575b4", "gate": "#d73027", "add": "#7b3294"}
ARM_LS = {"nf": ":", "sb": "--", "gate": "-", "add": "-."}
ARM_MK = {"nf": "", "sb": "", "gate": "o", "add": "s"}
FIRE_MK = {MAIN: "o", "a012_pvc_h30": "s", "a047_pvc_h35": "^"}
FIRE_LABEL = {
    MAIN: "a047_pvc_h40 (main fire)",
    "a047_pvc_h35": "a047_pvc_h35",
    "a012_pvc_h30": "a012_pvc_h30",
}


def _geometry():
    path = ROOT / "assets" / "schroeder2015_route" / "geometry.py"
    spec = importlib.util.spec_from_file_location("schroeder2015_geometry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def share(x, signed=False):
    """Round half up to three decimals.

    The E shares are exact multiples of 1/2000 (counts of 200 agents, mean
    of 10 seeds), so 0.6775 must print as 0.678 on every platform.
    """
    q = Decimal(repr(round(float(x), 9))).quantize(Decimal("0.001"), ROUND_HALF_UP)
    return f"{q:+}" if signed and q > 0 else f"{q}"


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    print("\n".join(lines) + "\n")


def heading(text):
    print(f"\n### {text}\n")


# --- Data --------------------------------------------------------------------


def route_len(y, door, exit_):
    """Straight legs from x = 5.4 m via the door to the exit."""
    p = np.array([5.4, y])
    d, e = np.array(DOOR_XY[door]), np.array(EXIT_XY[exit_])
    return float(np.linalg.norm(d - p) + np.linalg.norm(e - d))


def clear_air_dir(data):
    """The study's clear-air runs, or else the no-fire arm (identical)."""
    p0a = data / "p0a_nofire_100e91dd"
    return p0a if p0a.is_dir() else run_dir(data, MAIN)


def run_dir(data, fire):
    found = sorted(data.glob(f"p1_{fire}*"))
    if len(found) != 1:
        raise SystemExit(f"expected one p1_{fire}_* folder, found {found}")
    return found[0]


def agents(db, exit_csv=None, fed_gz=None):
    """One row per agent: start, door, exit, times, evacuation status."""
    t = pd.read_sql(
        "select frame, id, pos_x x, pos_y y from trajectory_data", sqlite3.connect(db)
    ).sort_values(["id", "frame"])
    last_frame = t.frame.max()
    rows = []
    for i, g in t.groupby("id"):
        x, y, f = g.x.values, g.y.values, g.frame.values
        moved = np.hypot(x - x[0], y - y[0]) > 0.2
        cross = np.flatnonzero(x < 0.1)
        door = "-" if cross.size == 0 else ("A" if y[cross[0]] < 12 else "B")
        evac = f[-1] < last_frame or last_frame < CAP * FPS - 1
        w = f >= f[-1] - 30 * FPS
        rows.append(
            dict(
                id=i,
                x0=x[0],
                y0=y[0],
                door=door,
                t_move=f[np.argmax(moved)] / FPS if moved.any() else np.nan,
                t_door=f[cross[0]] / FPS if cross.size else np.nan,
                evacuated=evac,
                t_out=f[-1] / FPS if evac else np.nan,
                exit_pos="E" if y[-1] < 12 else "F",
                last30=float(np.hypot(x[w][-1] - x[w][0], y[w][-1] - y[w][0])),
            )
        )
    a = pd.DataFrame(rows)
    if exit_csv is not None and exit_csv.exists():
        e = pd.read_csv(exit_csv)
        a["exit"] = a.id.map(dict(zip(e.agent_id, e.exit_id.str[-1])))
    else:
        a["exit"] = a.exit_pos
    a["incap"] = False
    if fed_gz is not None and fed_gz.exists():
        fd = pd.read_csv(fed_gz, usecols=["agent_id", "incapacitated"])
        inc = fd.groupby("agent_id").incapacitated.max()
        a["incap"] = a.id.map(inc).fillna(False).astype(bool)
    a["stalled"] = ~a.evacuated & ~a.incap & (a.last30 < 0.3)
    return a


def read_rh(path):
    """Route history; smoke-blind runs reroute nothing and write none."""
    if not path.exists():
        return pd.DataFrame(columns=["time_s", "agent_id", "reason"])
    return pd.read_csv(path)


def load_all(data):
    """Agent table for every fire, arm and seed, plus clear air."""
    frames = []
    for s in SEEDS:
        a = agents(clear_air_dir(data) / f"nf_s{s}.sqlite")
        frames.append(a.assign(fire="-", arm="p0a", seed=s))
    main_dir = run_dir(data, MAIN)
    for fire in [MAIN] + COMPARE:
        d = run_dir(data, fire)
        for arm in ARMS:
            src = main_dir if arm == "nf" else d
            for s in SEEDS:
                a = agents(
                    src / f"{arm}_s{s}.sqlite",
                    src / f"{arm}_s{s}_exit.csv",
                    src / f"{arm}_s{s}_fed.csv.gz",
                )
                rh = read_rh(src / f"{arm}_s{s}_rh.csv")
                counts = rh.agent_id.value_counts()
                a["n_reroute"] = a.id.map(counts).fillna(0).astype(int)
                frames.append(a.assign(fire=fire, arm=arm, seed=s))
    return pd.concat(frames, ignore_index=True)


def reroutes(data):
    """Route-history rows by reason, per fire, arm and seed."""
    rows = []
    main_dir = run_dir(data, MAIN)
    for fire in [MAIN] + COMPARE:
        for arm in ARMS:
            src = main_dir if arm == "nf" else run_dir(data, fire)
            for s in SEEDS:
                rh = read_rh(src / f"{arm}_s{s}_rh.csv")
                c = rh.reason.value_counts().to_dict()
                rows.append(
                    dict(
                        fire=fire,
                        arm=arm,
                        seed=s,
                        reroutes=len(rh),
                        rerouted_agents=rh.agent_id.nunique(),
                        **{f"rr_{k}": n for k, n in c.items()},
                    )
                )
    return pd.DataFrame(rows).fillna(0)


# --- Statistics --------------------------------------------------------------


def fit_boundary(y, b):
    """50 % point and slope of a logistic fit of b (0/1) on y."""

    def nll(p):
        z = np.clip(p[1] * (y - p[0]), -30, 30)
        return np.sum(np.log1p(np.exp(-z)) * b + np.log1p(np.exp(z)) * (1 - b))

    return minimize(nll, [12.0, 2.0], method="Nelder-Mead").x


def boundary_ci(a):
    """Boundary, slope and bootstrap 95 % CI; NaN when censored."""
    a = a[a.door != "-"]
    y, b = a.y0.values, (a.door == "B").values.astype(float)
    if min(b.sum(), (1 - b).sum()) < MIN_MINORITY:
        return np.nan, np.nan, np.nan, np.nan, True
    yb, k = fit_boundary(y, b)
    idx = RNG.integers(0, len(y), (N_BOOT, len(y)))
    boot = [fit_boundary(y[i], b[i])[0] for i in idx]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return yb, k, lo, hi, False


def per_seed(ag, rr):
    rows = []
    for (fire, arm, s), a in ag.groupby(["fire", "arm", "seed"]):
        yb, k, lo, hi, cens = boundary_ci(a)
        combo = (a.door + a.exit).value_counts()
        rows.append(
            dict(
                fire=fire,
                arm=arm,
                seed=s,
                boundary=yb,
                slope=k,
                b_lo=lo,
                b_hi=hi,
                censored=cens,
                no_door=int((a.door == "-").sum()),
                n_A=int((a.door == "A").sum()),
                n_B=int((a.door == "B").sum()),
                n_E=int((a.exit == "E").sum()),
                n_F=int((a.exit == "F").sum()),
                E_share=float((a.exit == "E").mean()),
                **{f"n_{c}": int(combo.get(c, 0)) for c in ["AE", "AF", "BE", "BF"]},
                evacuated=int(a.evacuated.sum()),
                remaining=int((~a.evacuated).sum()),
                incapacitated=int(a.incap.sum()),
                stalled=int(a.stalled.sum()),
                t_last_out=float(a.t_out.max()),
            )
        )
    ps = pd.DataFrame(rows)
    p0a = ps[ps.arm == "p0a"].set_index("seed")
    ps["dy"] = ps.boundary - ps.seed.map(p0a.boundary)
    sb = ps[ps.arm == "sb"].set_index(["fire", "seed"]).E_share
    nf = ps[(ps.arm == "nf") & (ps.fire == MAIN)].set_index("seed").E_share
    ps["dE_vs_sb"] = [
        r.E_share - (sb.get((r.fire, r.seed), np.nan) if r.arm != "nf" else nf[r.seed])
        for r in ps.itertuples()
    ]
    return ps.merge(rr, on=["fire", "arm", "seed"], how="left")


def tci(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if v.size < 2:
        return np.nan, np.nan, np.nan, v.size
    h = stats.t.ppf(0.975, v.size - 1) * v.std(ddof=1) / np.sqrt(v.size)
    return v.mean(), v.mean() - h, v.mean() + h, v.size


def per_arm(ps):
    rows = []
    counts = ["n_A", "n_B", "n_E", "n_F", "n_AE", "n_AF", "n_BE", "n_BF"]
    counts += ["no_door", "evacuated", "remaining", "incapacitated", "stalled"]
    counts += ["reroutes", "rerouted_agents"]
    for (fire, arm), g in ps.groupby(["fire", "arm"], sort=False):
        m, lo, hi, n = tci(g.dy)
        e, elo, ehi, _ = tci(g.dE_vs_sb)
        rows.append(
            dict(
                fire=fire,
                arm=arm,
                n_fit=n,
                n_censored=int(g.censored.sum()),
                boundary_mean=g.boundary.mean(),
                boundary_sd=g.boundary.std(ddof=1),
                dy_mean=m,
                dy_lo=lo,
                dy_hi=hi,
                E_share_mean=g.E_share.mean(),
                E_share_sd=g.E_share.std(ddof=1),
                E_share_min=g.E_share.min(),
                E_share_max=g.E_share.max(),
                dE_mean=e,
                dE_lo=elo,
                dE_hi=ehi,
                **{f"{c}_mean": g[c].mean() for c in counts if c in g},
                **{c: g[c].mean() for c in g if c.startswith("rr_")},
                t_last_out_max=g.t_last_out.max(),
            )
        )
    return pd.DataFrame(rows)


def valid_boundary(g):
    """Seeds whose boundary and bootstrap CI lie inside the hall (0-24 m)."""
    inside = g.boundary.between(0, 24) & (g.b_lo >= 0) & (g.b_hi <= 24)
    return inside & ~g.censored.astype(bool)


def share_by_start(ag):
    """Door-B and exit-E share per movement-start bin, per seed, then per arm."""
    rows = []
    for (fire, arm, seed), g in ag.groupby(["fire", "arm", "seed"]):
        g = g.dropna(subset=["t_move"])
        b = pd.cut(g.t_move, BINS)
        d = g[g.door != "-"]
        door = (
            (d.door == "B")
            .groupby(pd.cut(d.t_move, BINS), observed=False)
            .agg(["mean", "size"])
        )
        ex = (g.exit == "E").groupby(b, observed=False).agg(["mean", "size"])
        for iv in door.index:
            rows.append(
                dict(
                    fire=fire,
                    arm=arm,
                    seed=seed,
                    t_lo=iv.left,
                    t_hi=iv.right,
                    door_B=door.loc[iv, "mean"],
                    exit_E=ex.loc[iv, "mean"],
                    n=int(ex.loc[iv, "size"]),
                )
            )
    s = pd.DataFrame(rows)
    out = []
    for (fire, arm, lo, hi), g in s.groupby(["fire", "arm", "t_lo", "t_hi"]):
        r = dict(fire=fire, arm=arm, t_lo=lo, t_hi=hi, n_pooled=int(g.n.sum()))
        for col in ["door_B", "exit_E"]:
            v = g[col].dropna().values
            m = v.mean() if v.size else np.nan
            h = np.nan
            if v.size > 1:
                h = stats.t.ppf(0.975, v.size - 1) * v.std(ddof=1) / np.sqrt(v.size)
            r |= {
                f"{col}_mean": m,
                f"{col}_lo": max(m - h, 0.0),
                f"{col}_hi": min(m + h, 1.0),
            }
        r["shown"] = r["n_pooled"] >= MIN_POOLED
        out.append(r)
    return pd.DataFrame(out)


def read_rc(data, fire, arm, seed, cols):
    path = run_dir(data, fire) / f"{arm}_s{seed}_rc.csv.gz"
    return pd.read_csv(path, usecols=cols, low_memory=False)


def switch_times(data):
    """Hall-wide re-path and fallback times per fire, arm and seed."""
    cols = ["time_s", "source", "route_rank", "exit_id", "path", "rejection_reason"]
    rows = []
    for fire in FIRES:
        for arm in ["gate", "add"]:
            for seed in SEEDS:
                h = read_rc(data, fire, arm, seed, cols)
                h = h[h.source == HALL]
                via_a = h.path.str.contains("doorA")
                f_via_a = h[(h.exit_id == "exit_F") & via_a].time_s
                e_via_b = h[(h.exit_id == "exit_E") & ~via_a].time_s
                r1 = h[h.route_rank == 1]
                reason = r1.rejection_reason.fillna("").astype(str)
                fb = r1[reason.str.startswith("fallback")].time_s
                rows.append(
                    dict(
                        fire=fire,
                        arm=arm,
                        seed=seed,
                        F_path_via_A=f_via_a.min() if len(f_via_a) else np.nan,
                        E_path_via_B=e_via_b.min() if len(e_via_b) else np.nan,
                        first_fallback=fb.min() if len(fb) else np.nan,
                    )
                )
    return pd.DataFrame(rows)


def _mcfadden(X, b):
    """McFadden R^2 of a logistic model of b on the standardised columns of X."""

    def nll(Z):
        Z = np.column_stack([np.ones(len(b)), Z])

        def f(w):
            return np.sum(
                np.logaddexp(0, -(Z @ w)) * b + np.logaddexp(0, Z @ w) * (1 - b)
            )

        return minimize(f, np.zeros(Z.shape[1]), method="BFGS").fun

    Xs = (X - X.mean(0)) / X.std(0)
    return 1 - nll(Xs) / nll(np.empty((len(b), 0)))


def door_predictors(ag):
    rows = []
    for (fire, arm), a in ag[ag.arm.isin(["nf", "gate", "add"])].groupby(
        ["fire", "arm"]
    ):
        a = a[(a.door != "-")].dropna(subset=["t_move"])
        b = (a.door == "B").values.astype(float)
        pairs = b.sum() * (1 - b).sum()

        def auc(x):
            return stats.mannwhitneyu(x[b == 1], x[b == 0]).statistic / pairs

        rows.append(
            dict(
                fire=fire,
                arm=arm,
                n=len(b),
                AUC_y0=auc(a.y0.values),
                AUC_t_move=auc(a.t_move.values),
                R2_y0=_mcfadden(a[["y0"]].values, b),
                R2_t_move=_mcfadden(a[["t_move"]].values, b),
                R2_both=_mcfadden(a[["y0", "t_move"]].values, b),
            )
        )
    return pd.DataFrame(rows)


# --- Report ------------------------------------------------------------------


def report_clear_air(data, ps, ag):
    heading("Clear air (P0a) and the #350 bias")
    y_sp = brentq(lambda y: route_len(y, "A", "E") - route_len(y, "B", "F"), 2, 22)
    p0a = ps[ps.arm == "p0a"]
    a = ag[ag.arm == "p0a"]
    pooled = fit_boundary(a.y0.values, (a.door == "B").values.astype(float))[0]
    old_b = [np.nan]
    if (data / "p0a_nofire").is_dir():
        old = pd.concat(
            agents(data / "p0a_nofire" / f"nf_s{s}.sqlite").assign(seed=s)
            for s in SEEDS
        )
        old_b = [
            fit_boundary(g.y0.values, (g.door == "B").values.astype(float))[0]
            for _, g in old.groupby("seed")
        ]
    routes = sorted((a.door + a.exit_pos).unique())
    md_table(
        ["Quantity", "Value"],
        [
            ["shortest-path boundary (straight legs from x = 5.4 m)", f"{y_sp:.2f} m"],
            [
                "boundary per seed, mean ± SD (n = 10)",
                f"{p0a.boundary.mean():.2f} ± {p0a.boundary.std(ddof=1):.2f} m",
            ],
            ["boundary, seeds pooled", f"{pooled:.2f} m"],
            [
                "bias = per-seed mean − shortest path",
                f"{p0a.boundary.mean() - y_sp:+.2f} m "
                f"(unrounded {p0a.boundary.mean() - y_sp:+.4f} m)",
            ],
            [
                "bias before the fix of #350 (b42f07ef)",
                f"{np.mean(old_b) - y_sp:+.2f} m"
                if np.isfinite(old_b[0])
                else "no p0a_nofire folder in DATA",
            ],
            [
                "exit-E share pooled (per-seed range)",
                f"{share((a.exit_pos == 'E').mean())} "
                f"({p0a.E_share.min():.2f}–{p0a.E_share.max():.2f})",
            ],
            ["routes used", ", ".join(routes)],
            [
                "last agent out, per seed",
                f"{p0a.t_last_out.min():.0f}–{p0a.t_last_out.max():.0f} s",
            ],
        ],
    )
    nf = ps[(ps.arm == "nf") & (ps.fire == MAIN)].set_index("seed")
    same = (
        np.allclose(nf.boundary, p0a.set_index("seed").boundary)
        and (nf.E_share.values == p0a.set_index("seed").E_share.values).all()
    )
    print(f"no-fire arm reproduces P0a: {same}")
    for fire in FIRES:
        sb = ag[(ag.fire == fire) & (ag.arm == "sb")]
        nf_a = ag[(ag.fire == fire) & (ag.arm == "nf")]
        cols = ["seed", "id", "door", "exit", "t_out"]
        eq = sb[cols].reset_index(drop=True).equals(nf_a[cols].reset_index(drop=True))
        print(f"{fire}: smoke-blind agents identical to no fire: {eq}")
    return y_sp


def report_main(pa, ps):
    heading("Result in brief and exit shares (mean of 10 seeds)")
    rows = []
    for fire in FIRES:
        for arm in ["nf", "sb", "gate", "add"]:
            r = pa[(pa.fire == fire) & (pa.arm == arm)].iloc[0]
            g = ps[(ps.fire == fire) & (ps.arm == arm)]
            dy = ""
            if arm == "add":
                dy = f"{r.dy_mean:+.2f} m ({r.dy_lo:+.2f}, {r.dy_hi:+.2f})"
            if arm == "gate":
                npos, n = int((g.dy > 0).sum()), int(g.dy.notna().sum())
                p = stats.binomtest(npos, n).pvalue
                dy = (
                    f"dy > 0 in {npos} of {n} (sign test p = {p:.3f}); not identifiable"
                )
            de = "0"
            if arm in ("gate", "add"):
                de = (
                    f"{share(r.dE_mean, True)} ({share(r.dE_lo, True)}, "
                    f"{share(r.dE_hi, True)})"
                )
            rows.append(
                [
                    fire,
                    ARMS[arm],
                    share(r.E_share_mean),
                    de,
                    f"{r.n_A_mean:.0f} / {r.n_B_mean:.0f}",
                    f"{r.n_AE_mean:.1f} / {r.n_AF_mean:.1f} / {r.n_BE_mean:.1f} / "
                    f"{r.n_BF_mean:.1f}",
                    dy,
                    f"{int(valid_boundary(g).sum())} of {len(g)}",
                ]
            )
    md_table(
        [
            "Fire",
            "Arm",
            "E share",
            "ΔE vs smoke-blind (95 % CI)",
            "A / B",
            "AE / AF / BE / BF",
            "Δy (95 % CI) or sign count",
            "valid boundary",
        ],
        rows,
    )
    heading("Criterion 2 threshold (2 × SD of the smoke-blind E shares)")
    rows = []
    for fire in FIRES:
        sd = ps[(ps.fire == fire) & (ps.arm == "sb")].E_share.std(ddof=1)
        for arm in ["gate", "add"]:
            r = pa[(pa.fire == fire) & (pa.arm == arm)].iloc[0]
            ok = "pass" if abs(r.dE_mean) > 2 * sd else "fail"
            rows.append([fire, ARMS[arm], share(r.dE_mean, True), share(2 * sd), ok])
    md_table(["Fire", "Arm", "ΔE", "threshold", "criterion 2"], rows)
    heading("Additive Δy per seed: sign count")
    rows = []
    for fire in FIRES:
        g = ps[(ps.fire == fire) & (ps.arm == "add")]
        rows.append(
            [
                fire,
                f"{int((g.dy < 0).sum())} negative, {int((g.dy > 0).sum())} positive",
            ]
        )
    md_table(["Fire", "additive Δy"], rows)
    heading("Reroutes per seed, main fire")
    rows = []
    for arm in ["gate", "add"]:
        r = pa[(pa.fire == MAIN) & (pa.arm == arm)].iloc[0]
        by = {c[3:]: f"{r[c]:.1f}" for c in pa if c.startswith("rr_") and r[c] > 0}
        rows.append(
            [ARMS[arm], f"{r.reroutes_mean:.1f}", f"{r.rerouted_agents_mean:.1f}", by]
        )
    md_table(["Arm", "switches", "agents", "by reason"], rows)


def report_door_by_start(sh, dp, sw):
    heading("Door-B share by movement start (gate, post hoc)")
    rows = []
    for fire in FIRES:
        for arm in ["nf", "gate", "add"]:
            m = sh[(sh.fire == fire) & (sh.arm == arm) & sh.shown]
            early = m[(m.t_lo >= 30) & (m.t_hi <= 120)].door_B_mean.mean()
            late = m[m.t_lo >= 150].door_B_mean.mean()
            rows.append([fire, ARMS[arm], f"{early:.2f}", f"{late:.2f}"])
    md_table(["Fire", "Arm", "starts 30–120 s", "starts after 150 s"], rows)
    heading("Door predictors (pooled seeds, post hoc)")
    rows = [
        [
            r.fire,
            ARMS[r.arm],
            f"{r.AUC_y0:.2f}",
            f"{r.AUC_t_move:.2f}",
            f"{r.R2_y0:.2f}",
            f"{r.R2_t_move:.2f}",
            f"{r.R2_both:.2f}",
        ]
        for r in dp.itertuples()
    ]
    md_table(
        ["Fire", "Arm", "AUC start y", "AUC start time", "R² y", "R² time", "R² both"],
        rows,
    )
    heading("Hall-wide re-path times (min–max over 10 seeds)")
    rows = []
    for (fire, arm), g in sw.groupby(["fire", "arm"], sort=False):
        cell = []
        for c in ["F_path_via_A", "E_path_via_B", "first_fallback"]:
            v = g[c].dropna()
            cell.append("–" if v.empty else f"{v.min():.0f}–{v.max():.0f} s")
        rows.append([fire, ARMS[arm], *cell])
    md_table(["Fire", "Arm", "F via door A", "E via door B", "first fallback"], rows)


def report_mechanism(data, ag, sw):
    """The numbers of the 47 s and 145 s re-paths on the main fire (gate)."""
    heading("Mechanism, main fire, gate")
    t1 = int(sw[(sw.fire == MAIN) & (sw.arm == "gate")].F_path_via_A.median())
    t2 = int(sw[(sw.fire == MAIN) & (sw.arm == "gate")].E_path_via_B.median())
    cols = ["time_s", "agent_id", "source", "exit_id", "path", "path_length_m"]
    cols += ["tau_route"]
    rc = pd.concat(read_rc(data, MAIN, "gate", s, cols).assign(seed=s) for s in SEEDS)
    h = rc[rc.source == HALL].copy()
    h["route"] = np.where(h.path.str.contains("doorA"), "A", "B") + h.exit_id.str[-1]

    def med(route, t, col):
        v = h[(h.route == route) & (h.time_s == t)][col]
        return v.median() if len(v) else np.nan

    def rng(route, t0, t1_, col):
        v = h[(h.route == route) & h.time_s.between(t0, t1_)]
        v = v.groupby("time_s")[col].median()
        return f"{v.min():.2f}–{v.max():.2f}" if len(v) else "–"

    rh = pd.concat(
        read_rh(run_dir(data, MAIN) / f"gate_s{s}_rh.csv").assign(seed=s) for s in SEEDS
    )
    at_t1 = rh[rh.time_s == t1]
    rows = [
        ["first pass with exit F via door A", f"{t1} s"],
        [
            "path length F via B, one pass earlier",
            f"{med('BF', t1 - 1, 'path_length_m'):.1f} m",
        ],
        ["path length F via A", f"{med('AF', t1, 'path_length_m'):.1f} m"],
        ["path length E via A", f"{med('AE', t1, 'path_length_m'):.1f} m"],
        [
            "router τ of B→F, one pass earlier (median)",
            f"{med('BF', t1 - 1, 'tau_route'):.2f}",
        ],
        ["router τ of A→F at the switch (median)", f"{med('AF', t1, 'tau_route'):.1e}"],
        [
            f"exit changes at {t1} s, 10 seeds (reason)",
            f"{len(at_t1)} ({', '.join(sorted(at_t1.reason.unique()))})",
        ],
        ["first pass with exit E via door B", f"{t2} s"],
        [
            "router τ of A→E, one pass earlier (median)",
            f"{med('AE', t2 - 1, 'tau_route'):.2f}",
        ],
        [
            f"router τ of B→E, {t2}–{t2 + 5} s (median per pass)",
            rng("BE", t2, t2 + 5, "tau_route"),
        ],
    ]
    # Fallback switches: the new exit's route against the old one, same pass.
    fb = rh[rh.reason == "fallback"]
    rcs = rc.set_index(["seed", "time_s", "agent_id"]).sort_index()
    n_lower, n_bb = 0, 0
    for r in fb.itertuples():
        c = rcs.loc[(r.seed, r.time_s, r.agent_id)]
        new = c[c.exit_id == r.new_exit]
        old = c[c.exit_id == r.old_exit]
        if new.empty or old.empty:
            continue
        n_lower += int(new.tau_route.iloc[0] < old.tau_route.iloc[0])
        both_b = "doorB" in new.path.iloc[0] and "doorB" in old.path.iloc[0]
        n_bb += int(both_b)
    rows += [
        ["fallback switches, 10 seeds", f"{len(fb)}"],
        ["… of them with both routes via door B", f"{n_bb}"],
        ["… of them with lower τ on the new exit's route", f"{n_lower}"],
    ]
    g = ag[(ag.fire == MAIN) & (ag.arm == "gate")]
    be = g[(g.door == "B") & (g.exit == "E")]
    rows += [
        ["B→E agents per seed (mean)", f"{len(be) / len(SEEDS):.1f}"],
        ["B→E agents pass door B", f"{be.t_door.min():.0f}–{be.t_door.max():.0f} s"],
    ]
    md_table(["Quantity", "Value"], rows)


def report_comparison_order(ag, sw):
    heading("a012_pvc_h30, gate: B users and the F re-path")
    g = ag[(ag.fire == "a012_pvc_h30") & (ag.arm == "gate")]
    t1 = sw[(sw.fire == "a012_pvc_h30") & (sw.arm == "gate")].F_path_via_A.median()
    b = g[g.door == "B"]
    md_table(
        ["Quantity", "Value"],
        [
            ["door-B users per seed (mean)", f"{len(b) / len(SEEDS):.1f}"],
            [f"… of them starting before {t1:.0f} s", f"{(b.t_move < t1).mean():.2f}"],
            ["exit-E share", share((g.exit == "E").mean())],
        ],
    )


def report_still_walking(data, ag):
    heading("Agents still walking at 400 s")
    rows = []
    for fire in FIRES:
        row = [fire]
        for arm in ["gate", "add"]:
            g = ag[(ag.fire == fire) & (ag.arm == arm)]
            per = (~g.evacuated).groupby(g.seed).sum()
            row.append(f"{per.min()}–{per.max()} ({per.sum()})")
        rows.append(row)
    md_table(["Fire", "gate: per run (total in 10 runs)", "additive"], rows)
    left = ag[ag.arm.isin(["gate", "add"]) & ~ag.evacuated]
    fed_max, sf = 0.0, []
    for fire in FIRES:
        d = run_dir(data, fire)
        for arm in ["sb", "gate", "add"]:
            for s in SEEDS:
                cols = ["time_s", "agent_id", "fed_cumulative", "speed_factor"]
                f = pd.read_csv(d / f"{arm}_s{s}_fed.csv.gz", usecols=cols)
                fed_max = max(fed_max, f.fed_cumulative.max())
                if arm == "sb":
                    continue
                ids = left[
                    (left.fire == fire) & (left.arm == arm) & (left.seed == s)
                ].id
                last = f[f.agent_id.isin(ids)].sort_values("time_s").groupby("agent_id")
                sf += list(last.speed_factor.last())
    md_table(
        ["Quantity", "Value"],
        [
            [
                "movement start of those still walking",
                f"{left.t_move.min():.0f}–{left.t_move.max():.0f} s "
                f"(median {left.t_move.median():.0f} s; "
                f"{int((left.t_move >= 250).sum())} of {len(left)} at 250 s or later)",
            ],
            ["their speed factor at the last sample", f"{min(sf):.2f}–{max(sf):.2f}"],
            ["smallest distance walked in the last 30 s", f"{left.last30.min():.2f} m"],
            [
                "stalled (< 0.3 m in 30 s) or incapacitated",
                f"{int(left.stalled.sum())}, {int(left.incap.sum())}",
            ],
            ["largest gas FED of any agent in any fire run", f"{fed_max:.3f}"],
        ],
    )


def report_summary(pa, sh):
    """The lines the downloadable README.txt names as the expected result."""
    heading("Summary")
    arm = pa[pa.fire == MAIN].set_index("arm")
    m = sh[(sh.fire == MAIN) & (sh.arm == "gate") & sh.shown]
    early = m[(m.t_lo >= 30) & (m.t_hi <= 120)].door_B_mean.mean()
    late = m[m.t_lo >= 150].door_B_mean.mean()
    add = arm.loc["add"]
    print(
        f"main fire, exit-E share: no fire {share(arm.loc['nf'].E_share_mean)}, "
        f"gate {share(arm.loc['gate'].E_share_mean)}, "
        f"additive {share(add.E_share_mean)}"
    )
    print(
        f"main fire, additive dy: {add.dy_mean:+.2f} m "
        f"({add.dy_lo:+.2f}, {add.dy_hi:+.2f})"
    )
    print(
        f"main fire, gate door-B share: {early:.2f} for starts 30-120 s, "
        f"{late:.2f} after 150 s"
    )


def report_logs(data):
    """Heat FED status and horizon errors, from the logs of the fire arms."""
    heading("Run logs of the fire arms")
    n, heat_off, horizon = 0, 0, 0
    for fire in FIRES:
        for arm in ["sb", "gate", "add"]:
            for s in SEEDS:
                path = run_dir(data, fire) / f"{arm}_s{s}_log.txt.gz"
                text = gzip.open(path, "rt").read()
                n += 1
                heat_off += "Heat FED is off" in text
                horizon += "FdsHorizonError" in text
    md_table(
        ["Quantity", "Value"],
        [
            ["fire-arm runs", n],
            ["logs with 'Heat FED is off'", heat_off],
            ["logs with FdsHorizonError", horizon],
        ],
    )


def report_heat(data):
    """Post hoc: FDS temperature at 1.6 m at the agents' positions, every 1 s."""
    heading("Heat, post hoc (heat FED was off in the runs)")
    rows = []
    for fire in FIRES:
        sim = fdsreader.Simulation(str(data / fire))
        sl = [
            s
            for s in sim.slices
            if s.quantity.name == "TEMPERATURE" and s.orientation == 3
        ]
        sl = min(sl, key=lambda s: abs(s.extent.z_start - 1.6))
        T, c = sl.to_global(masked=True, fill=np.nan, return_coordinates=True)
        times, xs, ys = np.asarray(sl.times), c["x"], c["y"]
        for arm in ["sb", "gate", "add"]:
            per_run = []
            for s in SEEDS:
                f = pd.read_csv(
                    run_dir(data, fire) / f"{arm}_s{s}_fed.csv.gz",
                    usecols=["time_s", "agent_id", "x", "y"],
                )
                it = np.abs(times[None, :] - f.time_s.values[:, None]).argmin(1)
                ix = np.abs(xs[None, :] - f.x.values[:, None]).argmin(1)
                iy = np.abs(ys[None, :] - f.y.values[:, None]).argmin(1)
                f["T"] = T[it, ix, iy]
                dt = 1.0 / 60.0
                for law, (a, b) in HEAT_CLOTHING_LAWS.items():
                    f[law] = np.clip(f["T"], 0, None) ** b / a * dt
                dose = f.groupby("agent_id")[list(HEAT_CLOTHING_LAWS)].sum()
                hot = (f.groupby("agent_id")["T"].max() > 60).sum()
                per_run.append((f["T"].max(), hot, *dose.max().values))
            p = np.array(per_run, float)
            rows.append(
                [
                    fire,
                    ARMS[arm],
                    f"{sl.extent.z_start:.2f} m",
                    f"{p[:, 0].max():.0f} °C",
                    f"{p[:, 1].mean():.1f}",
                    f"{p[:, 2].max():.3f}",
                    f"{p[:, 3].max():.3f}",
                ]
            )
    md_table(
        [
            "Fire",
            "Arm",
            "slice",
            "highest T met",
            "agents above 60 °C per run (mean)",
            "largest dose, clothed",
            "largest dose, unclothed",
        ],
        rows,
    )


# --- Plot helpers ------------------------------------------------------------


def style(ax):
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT / name}.png")


def fig_counts(ag):
    t = np.arange(0, CAP + 1, 2.0)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True, sharey=True)
    a = ag[ag.fire == MAIN]
    names = {"sb": "smoke-blind (= no fire)", "gate": "gate", "add": "additive"}
    for ax, key in zip(axes.flat, ["A", "B", "E", "F"]):
        style(ax)
        for arm in names:
            curves = []
            for s in SEEDS:
                g = a[(a.arm == arm) & (a.seed == s)]
                if key in "AB":
                    tt = g.t_door[g.door == key].values
                else:
                    tt = g.t_out[g.evacuated & (g.exit == key)].values
                curves.append([(tt <= x).sum() for x in t])
            c = np.array(curves)
            ax.fill_between(t, c.min(0), c.max(0), color=ARM_COL[arm], alpha=0.15, lw=0)
            ax.plot(
                t,
                c.mean(0),
                color=ARM_COL[arm],
                ls=ARM_LS[arm],
                lw=1.8,
                label=names[arm],
            )
            ax.annotate(
                f"{c[:, -1].mean():.0f}",
                (t[-1], c[:, -1].mean()),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                fontsize=9,
                color=ARM_COL[arm],
            )
        kind = "door" if key in "AB" else "exit"
        ax.set_title(f"{kind} {key}", loc="left", fontsize=11, color="dimgrey")
        ax.set_xlim(0, 425)
    for ax in axes[1]:
        ax.set_xlabel("time [s] (number at the right: mean at 400 s)", color="dimgrey")
    for ax in axes[:, 0]:
        ax.set_ylabel("agents through, cumulative", color="dimgrey")
    axes[0, 0].legend(loc="upper left", fontsize=8.5, **LEGEND)
    sns.despine(left=True, bottom=True)
    fig.tight_layout()
    save(fig, "p1_counts")


def fig_door_by_start(sh, sw):
    fig, axes = plt.subplots(2, 3, figsize=(14, 7.6), sharex=True, sharey=True)
    swg = (
        sw[sw.arm == "gate"]
        .groupby("fire")[["F_path_via_A", "E_path_via_B", "first_fallback"]]
        .median()
    )
    names = {
        "F_path_via_A": "F via A",
        "E_path_via_B": "E via B",
        "first_fallback": "fallback",
    }
    labels = iter("abcdef")
    arms = {"nf": "no fire (= smoke-blind)", "gate": "gate", "add": "additive"}
    for row, (col, ylab) in enumerate(
        [("door_B", "share via door B"), ("exit_E", "share via exit E")]
    ):
        for j, fire in enumerate(FIRES):
            ax = axes[row][j]
            style(ax)
            marks = swg.loc[fire].dropna().sort_values()
            xs = list(marks.values)
            for k, (name, x) in enumerate(marks.items()):
                ax.axvline(x, color="dimgrey", lw=0.8, ls=(0, (2, 2)), zorder=1)
                if row:
                    continue
                near_next = k + 1 < len(xs) and xs[k + 1] - x < 30
                near_prev = k > 0 and x - xs[k - 1] < 30
                ha = "right" if near_next else "left" if near_prev else "center"
                ax.annotate(
                    f"{names[name]}\n{x:.0f} s",
                    (x, 1.05),
                    xytext=({"right": -2, "left": 2, "center": 0}[ha], 1.05),
                    textcoords=("offset points", "data"),
                    ha=ha,
                    va="bottom",
                    fontsize=8,
                    color="dimgrey",
                    annotation_clip=False,
                )
            for arm in arms:
                g = sh[(sh.fire == fire) & (sh.arm == arm) & sh.shown]
                mid = 0.5 * (g.t_lo + g.t_hi)
                ax.fill_between(
                    mid,
                    g[f"{col}_lo"],
                    g[f"{col}_hi"],
                    color=ARM_COL[arm],
                    alpha=0.18,
                    lw=0,
                )
                ax.plot(
                    mid,
                    g[f"{col}_mean"],
                    color=ARM_COL[arm],
                    ls=ARM_LS[arm],
                    marker=ARM_MK[arm],
                    ms=4,
                    lw=1.8,
                    label=arms[arm],
                )
            ax.set_ylim(-0.03, 1.05)
            ax.set_xlim(0, 310)
            ax.set_title(
                f"({next(labels)}) {FIRE_LABEL[fire]}",
                loc="left",
                fontsize=10.5,
                color="dimgrey",
                pad=28 if row == 0 else 6,
            )
            if j == 0:
                ax.set_ylabel(ylab, color="dimgrey")
            if row == 1:
                ax.set_xlabel("movement start [s] (30 s bins)", color="dimgrey")
    axes[1][0].legend(loc="lower left", fontsize=8.5, **LEGEND)
    sns.despine(left=True, bottom=True)
    fig.tight_layout()
    save(fig, "p1_door_by_start")


def fig_tau(data):
    """tau_route as the router computed it, gate, agents in the hall."""
    col = {"AE": "#4575b4", "BE": "#d73027", "AF": "#7f7f7f", "BF": "#fc8d59"}
    ls = {"AE": "-", "BE": "-", "AF": ":", "BF": "--"}
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=True)
    for k, (ax, fire) in enumerate(zip(axes, FIRES)):
        style(ax)
        cols = ["time_s", "source", "exit_id", "path", "tau_route"]
        rc = pd.concat(read_rc(data, fire, "gate", s, cols) for s in SEEDS)
        rc = rc[rc.source == HALL]
        rc["route"] = (
            np.where(rc.path.str.contains("doorA"), "A", "B") + rc.exit_id.str[-1]
        )
        rc["t"] = (rc.time_s // 5) * 5 + 2.5
        q = rc.groupby(["route", "t"]).tau_route.describe(percentiles=[0.25, 0.5, 0.75])
        q = q[q["count"] >= 20].reset_index()
        for r in col:
            g = q[q.route == r]
            if g.empty:
                continue
            seg = np.cumsum(np.r_[False, np.diff(g.t) > 5.1])
            for s in np.unique(seg):
                h = g[seg == s]
                ax.fill_between(h.t, h["25%"], h["75%"], color=col[r], alpha=0.25, lw=0)
                ax.plot(
                    h.t,
                    h["50%"],
                    color=col[r],
                    ls=ls[r],
                    lw=1.8,
                    label=f"{r[0]}→{r[1]}" if s == seg.min() else None,
                )
        ax.axhline(6, color="dimgrey", lw=0.8, ls=":")
        ax.axhline(4.8, color="dimgrey", lw=0.6, ls=(0, (1, 3)))
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_xlim(0, 300)
        ax.set_title(
            f"({'abc'[k]}) {FIRE_LABEL[fire]}",
            loc="left",
            fontsize=10.5,
            color="dimgrey",
        )
        ax.set_xlabel("decision time [s]", color="dimgrey")
    axes[0].set_ylabel(r"route optical depth $\tau$ (router)", color="dimgrey")
    axes[1].annotate(
        "6: refused for the current exit",
        (298, 6),
        xytext=(0, 3),
        ha="right",
        textcoords="offset points",
        color="dimgrey",
        fontsize=8,
    )
    axes[1].annotate(
        "4.8: refused for a rival exit",
        (298, 4.8),
        xytext=(0, -11),
        ha="right",
        textcoords="offset points",
        color="dimgrey",
        fontsize=8,
    )
    axes[2].legend(
        loc="upper left",
        fontsize=8.5,
        title="door → exit",
        title_fontsize=8.5,
        **LEGEND,
    )
    sns.despine(left=True, bottom=True)
    fig.tight_layout()
    save(fig, "p1_tau")


def fig_boundary(ag, ps, pa):
    fig, (ax0, ax1) = plt.subplots(
        1, 2, figsize=(13, 5.4), gridspec_kw={"width_ratios": [1, 1.1]}
    )
    style(ax0)
    style(ax1)
    yy = np.linspace(0, 24, 200)
    a = ag[(ag.fire == MAIN) & (ag.door != "-")]
    bins = np.arange(0, 25, 2.0)
    mid = 0.5 * (bins[1:] + bins[:-1])
    for arm in ["nf", "gate", "add"]:
        g = a[a.arm == arm]
        frac = g.groupby(pd.cut(g.y0, bins), observed=False).door.apply(
            lambda d: (d == "B").mean()
        )
        if arm == "gate":
            label = "gate: no fit (door follows movement start)"
        else:
            yb, k = fit_boundary(g.y0.values, (g.door == "B").values.astype(float))
            ax0.plot(
                yy,
                1 / (1 + np.exp(-k * (yy - yb))),
                color=ARM_COL[arm],
                ls=ARM_LS[arm],
                lw=2,
            )
            name = "no fire" if arm == "nf" else ARMS[arm]
            label = f"{name}: 50 % at y = {yb:.2f} m (seeds pooled)"
        ax0.plot(
            mid,
            frac.values,
            color=ARM_COL[arm],
            marker="o" if arm != "add" else "s",
            ls="",
            ms=5,
            label=label,
        )
    ax0.axhline(0.5, color="lightgrey", lw=0.8)
    ax0.set_xlabel("start y [m] (door A at 1.6 m, door B at 21.6 m)", color="dimgrey")
    ax0.set_ylabel("share via door B", color="dimgrey")
    ax0.set_title(
        "(a) main fire: door choice against start y; dots = 2 m bins",
        loc="left",
        fontsize=10.5,
        color="dimgrey",
    )
    ax0.legend(loc="upper left", fontsize=8.5, **LEGEND)
    arms = ["sb", "add"]
    for j, fire in enumerate(FIRES):
        for i, arm in enumerate(arms):
            x = i + (j - 1) * 0.25
            d = ps[(ps.fire == fire) & (ps.arm == arm)].dy.dropna()
            ax1.scatter(
                x + JITTER.uniform(-0.04, 0.04, d.size),
                d,
                color=ARM_COL[arm],
                marker=FIRE_MK[fire],
                s=14,
                alpha=0.5,
            )
            r = pa[(pa.fire == fire) & (pa.arm == arm)].iloc[0]
            ax1.errorbar(
                x,
                r.dy_mean,
                yerr=[[r.dy_mean - r.dy_lo], [r.dy_hi - r.dy_mean]],
                color="black",
                marker=FIRE_MK[fire],
                ms=7,
                mfc=ARM_COL[arm],
                capsize=3,
                lw=1.2,
            )
    ax1.axhline(0, color="lightgrey", lw=0.8)
    ax1.set_xticks(range(len(arms)), [ARMS[a] for a in arms])
    ax1.set_ylabel(r"$\Delta y$ = boundary $-$ clear-air boundary [m]", color="dimgrey")
    ax1.annotate(
        "↑ Δy > 0: boundary toward door B, more agents use door A",
        (0.02, 0.97),
        xycoords="axes fraction",
        color="dimgrey",
        fontsize=8.5,
        va="top",
    )
    ax1.annotate(
        "↓ Δy < 0: boundary toward door A, more agents use door B",
        (0.02, 0.03),
        xycoords="axes fraction",
        color="dimgrey",
        fontsize=8.5,
    )
    gt = [ps[(ps.fire == f) & (ps.arm == "gate")] for f in FIRES]
    signs = ", ".join(f"{int((g.dy > 0).sum())}/{int(g.dy.notna().sum())}" for g in gt)
    ax1.annotate(
        f"gate not drawn: no boundary in metres.\nΔy > 0 in {signs} seeds\n"
        "(fires in legend order)",
        (0.27, 0.3),
        xycoords="axes fraction",
        color="dimgrey",
        fontsize=8.5,
        va="center",
        ha="center",
    )
    ax1.legend(
        handles=[
            plt.Line2D(
                [],
                [],
                color="black",
                marker=FIRE_MK[f],
                ls="",
                mfc="white",
                label=FIRE_LABEL[f],
            )
            for f in FIRES
        ],
        loc="lower right",
        fontsize=8.5,
        **LEGEND,
    )
    ax1.set_title(
        "(b) shift per seed (small marks), mean and 95 % CI",
        loc="left",
        fontsize=10.5,
        color="dimgrey",
    )
    sns.despine(left=True, bottom=True)
    fig.tight_layout()
    save(fig, "p1_boundary")


def fig_routes(data, ag):
    geo = _geometry()
    sim = fdsreader.Simulation(str(data / MAIN))
    sl = [
        s
        for s in sim.slices
        if s.quantity.name == "SOOT EXTINCTION COEFFICIENT" and s.orientation == 3
    ]
    sl = min(sl, key=lambda s: abs(s.extent.z_start - 2.8))
    K, c = sl.to_global(masked=True, fill=np.nan, return_coordinates=True)
    times = np.asarray(sl.times)
    it = int(np.argmin(np.abs(times - 165.0)))
    levels = [0, 0.23, 0.7, 1.4, 2.3, 2.9]
    cmap = plt.get_cmap("Greys", len(levels) - 1)
    norm = BoundaryNorm(levels, cmap.N)
    d = run_dir(data, MAIN)
    combo_col = {"AE": "#4575b4", "AF": "#999999", "BE": "#d73027", "BF": "#fc8d59"}
    combo_ls = {"AE": "-", "AF": ":", "BE": "-", "BF": "--"}
    walk = geo.walkable()
    fig, axes = plt.subplots(1, 3, figsize=(12, 8.6), sharey=True)
    for k, (ax, arm) in enumerate(zip(axes, ["sb", "gate", "add"])):
        style(ax)
        pm = ax.pcolormesh(
            c["x"],
            c["y"],
            np.minimum(K[it], 2.8).T,
            cmap=cmap,
            norm=norm,
            shading="nearest",
            rasterized=True,
        )
        for ring in [walk.exterior, *walk.interiors]:
            ax.plot(*ring.xy, color="black", lw=0.8)
        t = pd.read_sql(
            "select frame, id, pos_x x, pos_y y from trajectory_data",
            sqlite3.connect(d / f"{arm}_s1.sqlite"),
        )
        a = ag[(ag.fire == MAIN) & (ag.arm == arm) & (ag.seed == 1)].set_index("id")
        for i, g in t[t.frame % 5 == 0].groupby("id"):
            cc = a.door[i] + a.exit[i]
            ax.plot(
                g.x,
                g.y,
                color=combo_col.get(cc, "black"),
                ls=combo_ls.get(cc, "-"),
                lw=0.6,
                alpha=0.7,
            )
        ax.scatter(
            a.x0,
            a.y0,
            s=4,
            c=[combo_col.get(cc, "black") for cc in a.door + a.exit],
            zorder=3,
        )
        n = (a.door + a.exit).value_counts()
        ax.set_title(
            f"({'abc'[k]}) {ARMS[arm]}\n"
            + "  ".join(f"{cc} {n.get(cc, 0)}" for cc in combo_col),
            loc="left",
            fontsize=10.5,
            color="dimgrey",
        )
        for lab, (x, y) in {
            "A": (0.4, 1.6),
            "B": (0.4, 21.6),
            "E": (-2.6, -11.2),
            "F": (-2.6, 35.8),
        }.items():
            ax.text(
                x,
                y,
                lab,
                color="black",
                fontsize=10,
                weight="semibold",
                ha="left" if lab in "AB" else "center",
                va="center",
            )
        ax.set_aspect("equal")
        ax.set_xlim(-5.5, 11)
        ax.set_ylim(-12, 36.8)
        ax.set_xlabel("x [m]", color="dimgrey")
    axes[0].set_ylabel("y [m]", color="dimgrey")
    handles = [
        plt.Line2D(
            [], [], color=combo_col[cc], ls=combo_ls[cc], lw=2, label=f"{cc[0]}→{cc[1]}"
        )
        for cc in combo_col
    ]
    axes[2].legend(
        handles=handles,
        title="door → exit",
        loc="lower right",
        fontsize=8.5,
        title_fontsize=8.5,
        **LEGEND,
    )
    cb = fig.colorbar(pm, ax=axes, shrink=0.5, pad=0.02)
    cb.set_ticks([0.115, 0.465, 1.05, 1.85, 2.6])
    cb.set_ticklabels(["< 0.23", "0.23–0.7", "0.7–1.4", "1.4–2.3", "> 2.3"])
    cb.set_label(
        f"K on the {sl.extent.z_start:.1f} m slice at {times[it]:.0f} s [1/m]"
        " (display only)",
        color="dimgrey",
    )
    cb.ax.tick_params(length=0, labelcolor="dimgrey")
    sns.despine(left=True, bottom=True)
    save(fig, "p1_routes_a047_pvc_h40")


# --- Main --------------------------------------------------------------------


def main():
    """Print the page's evacuation tables and write its P1 figures.

    Parameters
    ----------
    --data : the schroeder2015-route study folder.
    --cache : optional folder for the per-agent table.

    Saves
    -----
    site/static/images/studies/schroeder2015/p1_*.png
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()
    data = args.data.resolve()

    # --- Data ---
    cache = args.cache / "schroeder2015_agents.csv" if args.cache else None
    if cache and cache.exists():
        ag = pd.read_csv(cache, keep_default_na=False, na_values=[""])
    else:
        ag = load_all(data)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            ag.to_csv(cache, index=False)
    ps = per_seed(ag, reroutes(data))
    pa = per_arm(ps)
    nf = ag[(ag.arm == "nf") & (ag.fire == MAIN)]
    by_start = pd.concat(
        [ag[ag.arm.isin(["gate", "add"])]] + [nf.assign(fire=f) for f in FIRES]
    )
    sh = share_by_start(by_start)
    sw = switch_times(data)
    dp = door_predictors(by_start)
    if args.cache:
        for name, df in [
            ("seeds", ps),
            ("arms", pa),
            ("door_by_start", sh),
            ("switch_times", sw),
            ("door_predictors", dp),
        ]:
            df.to_csv(args.cache / f"schroeder2015_{name}.csv", index=False)

    # --- Report ---
    report_clear_air(data, ps, ag)
    report_main(pa, ps)
    report_door_by_start(sh, dp, sw)
    report_mechanism(data, ag, sw)
    report_comparison_order(ag, sw)
    report_still_walking(data, ag)
    report_logs(data)
    report_heat(data)
    report_summary(pa, sh)
    if args.no_figures:
        return

    # --- Plot ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig_counts(ag)
    fig_door_by_start(sh, sw)
    fig_tau(data)
    fig_boundary(ag, ps, pa)
    fig_routes(data, ag)


if __name__ == "__main__":
    main()
