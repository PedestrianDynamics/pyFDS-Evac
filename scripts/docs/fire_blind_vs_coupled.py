"""Evacuation with and without the fire: uncoupled against coupled arms.

Runs the T-junction crowd of ``assets/t_junction/config_initial_pre*.json``
(100 agents placed at t = 0, constant pre-movement 0, 30 or 60 s, 270 s cap)
against the ``fire_2MW_PVC`` FDS output in these arms, one ``run.py`` process
per arm and seed (the familiarity draw is keyed by JuPedSim id, #198):

======  ===============================================================
C       no fire (no ``--fds-dir``)
U       ``--smoke-blind``: fire sampled for the histories only
S       ``--no-enable-rerouting --disable-tenability --replay-exits U``
R       ``--disable-tenability``: smoke acts on speed and routing
R-na    R with ``"routing": {"anticipate": false}`` (#125)
R-det   R with tenability on (deterministic, FED 1)
R-prob  R-det with ``--incapacitation-mode probabilistic``
R+FIC   R-det with ``--enable-fic-speed``
======  ===============================================================

``RUNS`` gets one folder per pre-movement and seed; a run is skipped when its
``.ok`` marker exists. The R-na scenario is written into ``RUNS/scenarios``
with a copy of the geometry. Nothing is written into the repository except
the figures in ``site/static/images/fire-blind/``::

    uv run python scripts/docs/fire_blind_vs_coupled.py \\
        --data FDS --runs RUNS

``FDS`` is the ``t_junction/fire_2MW_PVC`` output. Prints every number of the
study and writes ``RUNS/summary_runs.csv`` and ``RUNS/summary_agents.csv``.
"""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from first_fds_case_aset import (  # noqa: E402
    CRITERIA,
    CT_HCL_PPM_MIN,
    F_FIC_HCL_PPM,
    K_10M,
    _check_slice_height,
    first_crossings,
    location_aset,
)

from pyfds_evac import (  # noqa: E402
    DefaultFedConfig,
    DefaultFedModel,
    ExtinctionField,
    FdsFedField,
    SmokeSpeedConfig,
)

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "assets" / "t_junction"
OUT = ROOT / "site" / "static" / "images" / "fire-blind"

CAP = 270.0  # max_simulation_time of the three configs
FPS = 10.0
PRES = (0, 30, 60)
FIRE_ARMS = ("U", "S", "R", "R-na", "R-det", "R-prob", "R+FIC")
ARMS = ("C", *FIRE_ARMS)
MAIN = ("U", "S", "R")
TENABILITY_ARMS = ("R-det", "R-prob", "R+FIC")
# First-fds-case §6 (K >= 0.3 1/m); the page reuses that table.
EXPECTED_K_ASET = {"junction": 24.0, "exit B": 18.0, "exit A": 45.0}
STUDY_CRITERIA = ("K 0.3", "ISO FEC 0.3", "ISO FEC 1", "FED 0.3")
FIXED_POINTS = ("exit B", "junction", "branch mouth", "exit A")
FN_K = (1.9, 7.4)  # Frantzich and Nilsson, Fig. 14, as on first-fds-case

TEXT = "dimgrey"
STYLE = {  # arm -> colour, line style, marker
    "C": ("#969696", (0, (1, 1)), "x"),
    "U": ("#4575b4", "--", "o"),
    "S": ("#fc8d59", "-.", "s"),
    "R": ("#d73027", "-", "D"),
    "R-na": ("#7f7f7f", ":", "^"),
    "R-det": ("#91bfdb", "-", "v"),
    "R-prob": ("#1a1a1a", "--", "P"),
    "R+FIC": ("#fee090", "-", "X"),
}
LABEL = {
    "C": "C: no fire",
    "U": "U: smoke-blind (uncoupled)",
    "S": "S: speed only, U's exits",
    "R": "R: speed and routing",
    "R-na": "R-na: R without foresight",
    "R-det": "R-det: R, FED 1 incapacitates",
    "R-prob": "R-prob: per-agent thresholds",
    "R+FIC": "R+FIC: R-det, HCl slowdown",
}


# --- Runs ---


def scenario_path(arm, pre, runs):
    if arm == "R-na":
        return runs / "scenarios" / f"config_initial_pre{pre}_noanticipate.json"
    return ASSET / f"config_initial_pre{pre}.json"


def write_noanticipate(runs):
    """R-na scenarios: the asset config with route-cost foresight off."""
    folder = runs / "scenarios"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSET / "geometry.wkt", folder / "geometry.wkt")
    for pre in PRES:
        config = json.loads((ASSET / f"config_initial_pre{pre}.json").read_text())
        config["routing"]["anticipate"] = False
        path = scenario_path("R-na", pre, runs)
        path.write_text(json.dumps(config, indent=2) + "\n")


def run_dir(runs, pre, seed):
    return runs / f"pre{pre:02d}" / f"seed{seed:02d}"


def stem(arm):
    return arm.replace("+", "p").replace("-", "_")


def arm_flags(arm, folder):
    """The flags that make each arm, on top of the common outputs."""
    flags = {
        "U": ["--smoke-blind"],
        "S": [
            "--no-enable-rerouting",
            "--disable-tenability",
            "--replay-exits",
            str(folder / "U_exits.csv"),
        ],
        "R": ["--disable-tenability"],
        "R-na": ["--disable-tenability"],
        "R-det": [],
        "R-prob": ["--incapacitation-mode", "probabilistic"],
        # No --disable-tenability: it would turn the FIC slowdown off.
        "R+FIC": ["--enable-fic-speed"],
    }
    return flags[arm]


def command(arm, pre, seed, runs, fds):
    folder = run_dir(runs, pre, seed)
    base = folder / stem(arm)
    cmd = [
        sys.executable,
        str(ROOT / "run.py"),
        "--scenario",
        str(scenario_path(arm, pre, runs)),
        "--seed",
        str(seed),
        "--output-sqlite",
        f"{base}.sqlite",
        "--output-exit-history",
        f"{base}_exits.csv",
    ]
    if arm == "C":
        return cmd
    return [
        *cmd,
        "--fds-dir",
        str(fds),
        "--output-fed-history",
        f"{base}_fed.csv",
        "--output-smoke-history",
        f"{base}_smoke.csv",
        *arm_flags(arm, folder),
    ]


def execute(job):
    arm, pre, seed, runs, fds = job
    folder = run_dir(runs, pre, seed)
    base = folder / stem(arm)
    ok = Path(f"{base}.ok")
    if ok.exists():
        return arm, pre, seed, "skipped", 0.0
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with open(f"{base}.log", "w") as log:
        code = subprocess.call(
            command(arm, pre, seed, runs, fds),
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    wall = time.perf_counter() - start
    if code == 0:
        ok.write_text(f"{wall:.1f}\n")
    return arm, pre, seed, "ok" if code == 0 else f"crashed ({code})", wall


def run_all(jobs_by_phase, workers):
    """Phase 1: every arm but S; phase 2: S, which replays U's exits."""
    status = {}
    start = time.perf_counter()
    for jobs in jobs_by_phase:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for arm, pre, seed, state, wall in pool.map(execute, jobs):
                status[(arm, pre, seed)] = state
                if state != "skipped":
                    print(
                        f"  pre{pre:02d} seed{seed:02d} {arm:6s} {state} {wall:.1f} s"
                    )
    return status, time.perf_counter() - start


def report_compute(runs):
    """Single-process wall seconds per arm and pre-movement, from .ok markers."""
    print("\n== Compute: wall seconds per run (one process each) ==")
    total = 0.0
    for pre in PRES:
        cells = []
        for arm in ARMS:
            oks = sorted((runs / f"pre{pre:02d}").glob(f"seed*/{stem(arm)}.ok"))
            walls = [float(p.read_text()) for p in oks]
            total += sum(walls)
            if walls:
                cells.append(f"{arm} {np.median(walls):.0f}")
        print(f"  pre{pre:2d} median per run: " + ", ".join(cells))
    print(f"  sum over all runs: {total:.0f} s ({total / 60:.1f} min)")


# --- Loading one run ---


def evacuated_in_log(path):
    text = Path(path).read_text(errors="replace")
    found = re.findall(r"\((\d+)/(\d+) evacuated[,)]", text)
    return int(found[-1][0]) if found else None


def people_of(base):
    """Exit time per agent (NaN if still inside at the cap), paired keys."""
    import sqlite3

    with sqlite3.connect(f"{base}.sqlite") as con:
        fps = float(
            con.execute("select value from metadata where key = 'fps'").fetchone()[0]
        )
        df = pd.read_sql(
            "select id, min(frame) as first, max(frame) as last "
            "from trajectory_data group by id",
            con,
        )
    assert fps == FPS
    exits = pd.read_csv(f"{base}_exits.csv").set_index("agent_id")
    last = df.set_index("id")["last"] / FPS
    people = pd.DataFrame(index=pd.Index(last.index, name="agent_id"))
    people["last"] = last
    # Censor only agents whose own trajectory reaches the cap.
    people["exit"] = last.where(last < CAP - 0.5 / FPS)
    people = people.join(exits[["origin", "spawn_index", "exit_id"]])
    assert people.spawn_index.notna().all()
    return people


def records_of(base):
    """Per agent and second: K, HCl, FED, FIC and speed factors."""
    fed = pd.read_csv(f"{base}_fed.csv")
    smoke = pd.read_csv(f"{base}_smoke.csv")
    # HCl is the only irritant of this deck (as in first_fds_case_aset).
    assert (fed[["hcn_ppm", "no_ppm", "no2_ppm"]].to_numpy() == 0).all()
    hcl = F_FIC_HCL_PPM * fed.fic
    assert np.allclose(hcl, CT_HCL_PPM_MIN * fed.fld_rate_per_min, atol=1e-6)
    merged = fed.assign(hcl=hcl).merge(
        smoke[["time_s", "agent_id", "extinction_per_m", "speed_factor"]],
        on=["time_s", "agent_id"],
        suffixes=("_fed", ""),
        validate="one_to_one",
    )
    return pd.DataFrame(
        {
            "time_s": merged.time_s,
            "agent_id": merged.agent_id,
            "k": merged.extinction_per_m,
            "hcl": merged.hcl,
            "co": 1e4 * merged.co_percent,
            "fed": merged.fed_cumulative,
            "fic": merged.fic,
            "speed_factor": merged.speed_factor,
            "fic_speed_factor": merged.fic_speed_factor,
            "incapacitated": merged.incapacitated.astype(str) == "True",
        }
    )


def agent_table(people, rec, pre):
    """Per-agent dose and crossings, keyed by (origin, spawn_index)."""
    criteria = {key: CRITERIA[key] for key in STUDY_CRITERIA}
    cross = first_crossings(rec, people, criteria)
    inside = rec.join(people["exit"], on="agent_id")
    inside = inside[~(inside.time_s > inside["exit"])]
    grouped = inside.groupby("agent_id")
    table = people[["origin", "spawn_index", "exit_id", "exit"]].copy()
    table["max_fic"] = grouped.fic.max()
    table["max_fed"] = grouped.fed.max()
    table["s_hcl300"] = inside[inside.hcl >= 300.0].groupby("agent_id").size()
    table["s_hcl1000"] = inside[inside.hcl >= 1000.0].groupby("agent_id").size()
    table["s_k03"] = inside[inside.k >= K_10M].groupby("agent_id").size()
    table["incapacitated"] = grouped.incapacitated.any()
    table["min_fic_speed"] = grouped.fic_speed_factor.min()
    for key in STUDY_CRITERIA:
        table[f"cross {key}"] = cross[key]
        # Per-agent margin: first crossing - exit (< 0: crossed while inside).
        table[f"margin {key}"] = cross[key] - people["exit"]
    fill = ["s_hcl300", "s_hcl1000", "s_k03"]
    table[fill] = table[fill].fillna(0)
    table["incapacitated"] = table["incapacitated"].fillna(False).astype(bool)
    moving = rec[rec.time_s >= pre]
    shares = {
        "share_k74": float((moving.k > FN_K[1]).mean()),
        "share_floor": float((moving.speed_factor <= 0.1 + 1e-9).mean()),
        "share_k_below_fn": float((moving.k < FN_K[0]).mean()),
    }
    return table, shares, moving.k.to_numpy()


def rset(people):
    """Last exit and p95; censored (inf) when anyone is inside at the cap."""
    t = people["exit"].fillna(np.inf).sort_values().to_numpy()
    p95 = t[math.ceil(0.95 * len(t)) - 1]
    return t[-1], p95


def summarise_run(arm, pre, seed, base, loc):
    people = people_of(base)
    logged = evacuated_in_log(f"{base}.log")
    n_out = int(people["exit"].notna().sum())
    assert logged is None or logged == n_out, (base, logged, n_out)
    last, p95 = rset(people)
    row = {
        "arm": arm,
        "pre": pre,
        "seed": seed,
        "n": len(people),
        "n_out": n_out,
        "n_inside": len(people) - n_out,
        "rset_last": last,
        "rset_p95": p95,
        "last_exit_out": people["exit"].max(),
        "exit_A": int((people.exit_id == "exit_A_left").sum()),
        "exit_B": int((people.exit_id == "exit_B_right").sum()),
    }
    for point in FIXED_POINTS:
        for key in ("K 0.3", "ISO FEC 0.3"):
            aset = loc.loc[point, key]
            row[f"inside@{point}|{key}"] = int(
                (people["exit"].fillna(np.inf) > aset).sum()
            )
    if arm == "C":
        return row, None, None
    rec = records_of(base)
    # Incapacitated agents are censored, never counted as out (Galea 2008 T. 4).
    down = rec[rec.incapacitated].agent_id.unique()
    assert people.loc[down, "exit"].isna().all(), (base, "incapacitated agent left")
    table, shares, k_moving = agent_table(people, rec, pre)
    row.update(shares)
    row["n_incap"] = int(table.incapacitated.sum())
    row["max_fed"] = table.max_fed.max()
    row["median_max_fic"] = table.max_fic.median()
    row["agent_s_hcl300"] = table.s_hcl300.sum()
    row["agent_s_hcl1000"] = table.s_hcl1000.sum()
    row["agent_s_k03"] = table.s_k03.sum()
    row["n_fic_floor"] = int((table.min_fic_speed <= 0.3 + 1e-9).sum())
    for key in STUDY_CRITERIA:
        before_out = table[f"cross {key}"].notna()
        row[f"crossed {key}"] = int(before_out.sum())
    table = table.assign(arm=arm, pre=pre, seed=seed)
    return row, table, k_moving


def position_difference(folder):
    """Max distance between C's and U's agents, paired by spawn order."""
    import sqlite3

    tracks = []
    for arm in ("C", "U"):
        base = folder / stem(arm)
        with sqlite3.connect(f"{base}.sqlite") as con:
            tr = pd.read_sql("select frame, id, pos_x, pos_y from trajectory_data", con)
        keys = pd.read_csv(f"{base}_exits.csv").set_index("agent_id")
        tr = tr.join(keys[["origin", "spawn_index"]], on="id")
        tracks.append(tr.drop(columns="id"))
    merged = tracks[0].merge(
        tracks[1], on=["frame", "origin", "spawn_index"], how="outer", indicator=True
    )
    unmatched = int((merged["_merge"] != "both").sum())
    both = merged[merged["_merge"] == "both"]
    dist = np.hypot(both.pos_x_x - both.pos_x_y, both.pos_y_x - both.pos_y_y)
    return float(dist.max()), unmatched


# --- Location ASET ---


def fixed_point_aset(fds):
    sim = _check_slice_height(fds)
    k_field = ExtinctionField.from_fds(str(fds), simulation=sim)
    fed_field = FdsFedField.from_fds(str(fds), simulation=sim)
    fed_model = DefaultFedModel(fed_field, DefaultFedConfig())
    criteria = {key: CRITERIA[key] for key in STUDY_CRITERIA}
    loc = location_aset(k_field, fed_model, criteria)
    for point, expected in EXPECTED_K_ASET.items():
        assert loc.loc[point, "K 0.3"] == expected, (point, loc.loc[point])
    return loc


def longest_route_m(config):
    """Upper bound of the lookahead distance: farthest walkable point to A."""
    node = np.mean(config["checkpoints"]["jps-checkpoints_0"]["coordinates"][:4], 0)
    exits = {k: np.mean(v["coordinates"][:4], 0) for k, v in config["exits"].items()}
    starts = [
        *config["distributions"]["jps-distributions_0"]["coordinates"][:4],
        exits["exit_B_right"],
    ]
    to_node = max(np.hypot(*(np.asarray(p) - node)) for p in starts)
    to_exit = max(np.hypot(*(e - node)) for e in exits.values())
    return to_node + to_exit, to_node, to_exit


# --- Statistics ---


def sign_test(diff):
    """Two-sided sign test on non-zero paired differences."""
    d = np.asarray(diff, dtype=float)
    d = d[d != 0]
    pos, neg = int((d > 0).sum()), int((d < 0).sum())
    n = pos + neg
    if n == 0:
        return pos, neg, 1.0
    tail = sum(math.comb(n, k) for k in range(min(pos, neg) + 1)) / 2**n
    return pos, neg, min(1.0, 2 * tail)


def paired(runs_df, metric, x, y, pre):
    """Per-seed x - y; censored values give a known sign, no size."""
    sub = runs_df[runs_df.pre == pre].pivot(index="seed", columns="arm", values=metric)
    if x not in sub or y not in sub:
        return pd.Series(dtype=float), pd.Series(dtype=bool)
    diff = sub[x] - sub[y]
    censored = ~np.isfinite(sub[x]) | ~np.isfinite(sub[y])
    return diff, censored


def fmt_range(values):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return "censored"
    return f"{np.median(v):6.1f} [{v.min():.1f}, {v.max():.1f}]"


# --- Report ---


def report_runs(runs_df, status, loc, route, checks):
    print("\n== Setup ==")
    total, to_node, to_exit = route
    print(
        f"longest lookahead route: {to_node:.1f} m to the junction node + "
        f"{to_exit:.1f} m to the farther exit = {total:.1f} m "
        f"({total / 1.3:.0f} s at 1.3 m/s; headroom {300 - CAP:.0f} s)"
    )
    crashed = {k: v for k, v in status.items() if v.startswith("crashed")}
    print(f"runs: {len(status)}, crashed: {len(crashed)}")
    for (arm, pre, seed), state in sorted(crashed.items()):
        print(f"  CRASHED pre{pre} seed{seed} {arm}: {state}")
    print("\nlocation ASET [s from ignition] (same FDS output for every arm)")
    print(loc[list(STUDY_CRITERIA)].to_string(float_format=lambda v: f"{v:.0f}"))
    print("\n== Checkpoint: U against C (same seed) ==")
    for pre in PRES:
        sub = checks[checks.pre == pre]
        print(
            f"  pre{pre}: max position difference {sub.max_dist.max():.3g} m over "
            f"{len(sub)} seeds, unmatched rows {sub.unmatched.sum()}"
        )


def report_rset(runs_df):
    print("\n== RSET [s from ignition]: median [min, max] over seeds ==")
    for pre in PRES:
        print(f"-- pre {pre} s")
        for arm in ARMS:
            sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
            if sub.empty:
                continue
            cens = int((~np.isfinite(sub.rset_last)).sum())
            a_share = sub.exit_A / sub.n
            print(
                f"  {arm:6s} last {fmt_range(sub.rset_last)}  "
                f"p95 {fmt_range(sub.rset_p95)}  censored {cens}/{len(sub)}  "
                f"exit A {a_share.median():.0%} [{a_share.min():.0%}, "
                f"{a_share.max():.0%}]"
            )
    print("\n== Paired RSET_last differences, per seed ==")
    for pre in PRES:
        for x, y in (("S", "U"), ("R", "U"), ("R", "S"), ("R-na", "R"), ("R-na", "U")):
            diff, cens = paired(runs_df, "rset_last", x, y, pre)
            if diff.empty:
                continue
            pos, neg, p = sign_test(diff.fillna(0))
            finite = diff[~cens]
            print(
                f"  pre{pre:2d} {x}-{y:4s} median {finite.median():6.1f} "
                f"[{finite.min():.1f}, {finite.max():.1f}]  {x}>{y} in "
                f"{int((diff > 0).sum())}/{len(diff)}, {x}<{y} "
                f"{int((diff < 0).sum())}, sign p = {p:.3g}"
            )


def report_additivity(runs_df):
    print("\n== Additivity: RSET(pre) - pre - RSET(0), same seed ==")
    base = runs_df[runs_df.pre == 0].set_index(["arm", "seed"]).rset_last
    for arm in ARMS:
        for pre in PRES[1:]:
            sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
            dev = [
                r.rset_last - pre - base.get((arm, r.seed), np.nan)
                for r in sub.itertuples()
            ]
            dev = np.asarray(dev, dtype=float)
            dev = dev[np.isfinite(dev)]
            if len(dev):
                print(
                    f"  {arm:6s} pre{pre}: median {np.median(dev):6.2f}, "
                    f"range [{dev.min():.2f}, {dev.max():.2f}] s over {len(dev)} seeds"
                )


def report_tenability(runs_df, agents_df):
    print("\n== Tenability arms: n incapacitated, n inside at 270 s, last exit ==")
    for pre in PRES:
        for arm in TENABILITY_ARMS:
            sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
            if sub.empty:
                continue
            print(
                f"  pre{pre:2d} {arm:6s} incap total {int(sub.n_incap.sum())} "
                f"(seeds with any {int((sub.n_incap > 0).sum())}/{len(sub)}), "
                f"inside total {int(sub.n_inside.sum())} "
                f"(seeds {int((sub.n_inside > 0).sum())}), last exit among the "
                f"rest {fmt_range(sub.last_exit_out)}, agents at FIC floor "
                f"{fmt_range(sub.n_fic_floor)}"
            )


def report_margins(runs_df, loc):
    print("\n== Location margin ASET_loc - RSET_last [s], median over seeds ==")
    for key in ("K 0.3", "ISO FEC 0.3", "ISO FEC 1", "FED 0.3"):
        print(f"-- {key}")
        for pre in PRES:
            cells = []
            for arm in ("U", "S", "R", "R-na"):
                sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
                m = [
                    f"{loc.loc[p, key] - sub.rset_last.median():6.0f}"
                    for p in FIXED_POINTS
                ]
                cells.append(f"{arm}:" + "/".join(s.strip() for s in m))
            print(f"  pre{pre:2d} " + "  ".join(cells))
    print(f"   (points: {' / '.join(FIXED_POINTS)}; nan: limit not met by 300 s)")
    print("\n== Seeds with a positive location margin (pass), per point ==")
    for key in ("K 0.3", "ISO FEC 0.3", "ISO FEC 1", "FED 0.3"):
        for pre in PRES:
            cells = []
            for arm in ("U", "S", "R", "R-na", "R+FIC"):
                sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
                aset = loc.loc[list(FIXED_POINTS), key].fillna(np.inf).to_numpy()
                passes = aset[None, :] > sub.rset_last.to_numpy()[:, None]
                cells.append(f"{arm}:" + "/".join(str(int(n)) for n in passes.sum(0)))
            print(f"  {key:11s} pre{pre:2d} n={len(sub)} " + "  ".join(cells))
    print("\n== N inside at the location ASET, median over seeds ==")
    for pre in PRES:
        for key in ("K 0.3", "ISO FEC 0.3"):
            cells = []
            for arm in ("U", "S", "R", "R-na"):
                sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
                m = [f"{sub[f'inside@{p}|{key}'].median():.0f}" for p in FIXED_POINTS]
                cells.append(f"{arm}:" + "/".join(m))
            print(f"  pre{pre:2d} {key:11s} " + "  ".join(cells))


def report_dose(runs_df, agents_df):
    print("\n== Per-agent dose, pooled over seeds: median / p90 / max ==")
    cols = ("max_fic", "s_hcl300", "s_hcl1000", "max_fed", "s_k03")
    for pre in PRES:
        print(f"-- pre {pre} s")
        for arm in FIRE_ARMS:
            sub = agents_df[(agents_df.pre == pre) & (agents_df.arm == arm)]
            if sub.empty:
                continue
            parts = [
                f"{c} {sub[c].median():.2f}/{sub[c].quantile(0.9):.2f}/"
                f"{sub[c].max():.2f}"
                for c in cols
            ]
            exposed = int((sub.s_hcl300 > 0).sum())
            print(f"  {arm:6s} " + "  ".join(parts) + f"  exposed@300 {exposed}")
    print("\n== Agents crossing a limit before getting out, per seed: median ==")
    for pre in PRES:
        for arm in FIRE_ARMS:
            sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
            if sub.empty:
                continue
            parts = [f"{k} {sub[f'crossed {k}'].median():.0f}" for k in STUDY_CRITERIA]
            print(f"  pre{pre:2d} {arm:6s} " + "  ".join(parts))
    print("\n== Extrapolated share of moving agent-seconds (S and R) ==")
    for pre in PRES:
        for arm in ("S", "R", "R-na"):
            sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
            print(
                f"  pre{pre:2d} {arm:5s} K > 7.4: {sub.share_k74.median():.1%}  "
                f"at 0.1 floor: {sub.share_floor.median():.1%}  "
                f"K < 1.9: {sub.share_k_below_fn.median():.1%}"
            )


def report_agent_margins(agents_df):
    """Per-agent ASET - RSET: first crossing - own exit, among those crossing."""
    print("\n== Per-agent margin, first crossing - exit [s] ==")
    print("   (crossed: limit met while inside; the rest have a censored margin > 0)")
    for key in ("K 0.3", "ISO FEC 0.3", "ISO FEC 1"):
        print(f"-- {key}")
        for pre in PRES:
            for arm in FIRE_ARMS:
                sub = agents_df[(agents_df.pre == pre) & (agents_df.arm == arm)]
                if sub.empty:
                    continue
                m = sub[f"margin {key}"].dropna()
                crossed = int(sub[f"cross {key}"].notna().sum())
                print(
                    f"  pre{pre:2d} {arm:6s} crossed {crossed}/{len(sub)}  "
                    f"margin {fmt_range(m)}"
                )
        for pre in PRES:
            for x in ("S", "R", "R-na"):
                more, same, less = per_agent_paired(
                    agents_df, x, pre, f"cross {key}", paired_margin=True
                )
                print(
                    f"  pre{pre:2d} paired U vs {x:5s} agents crossing: U only "
                    f"{more}, both {same}, {x} only {less}"
                )


def per_agent_paired(agents_df, x, pre, column, paired_margin=False):
    """Per agent, U against x, paired by (origin, spawn_index) and seed."""
    keys = ["seed", "origin", "spawn_index"]
    a = agents_df[(agents_df.arm == "U") & (agents_df.pre == pre)]
    b = agents_df[(agents_df.arm == x) & (agents_df.pre == pre)]
    m = a.merge(b, on=keys, suffixes=("_u", "_x"), validate="one_to_one")
    u, v = m[f"{column}_u"], m[f"{column}_x"]
    if paired_margin:  # crossing indicators: U only, both, X only
        cu, cx = u.notna(), v.notna()
        return int((cu & ~cx).sum()), int((cu & cx).sum()), int((~cu & cx).sum())
    return int((u > v).sum()), int((u == v).sum()), int((u < v).sum())


def verdict(u, v):
    """Seeds with U > X (conservative), U = X (tie) and U < X (not)."""
    more, same, less = int((u > v).sum()), int((u == v).sum()), int((u < v).sum())
    return f"U>X {more}, U=X {same}, U<X {less} of {len(u)}"


def report_conservative(runs_df, agents_df):
    """U is conservative relative to X when its error shrinks the margin."""
    print("\n== Is U conservative relative to X? (per pre-movement, per seed) ==")
    rows = []
    for pre in PRES:
        for x in ("S", "R", "R-na"):
            rows.extend(_conservative_rows(runs_df, agents_df, pre, x))
    table = pd.DataFrame(rows)
    for (metric, rule), sub in table.groupby(["metric", "rule"], sort=False):
        print(f"-- {metric}  [U conservative if {rule}]")
        for r in sub.itertuples():
            print(f"  pre{r.pre:2d} vs {r.x:5s} {r.result}")
    print("-- exit usage: not conservative or not; differs, see the RSET table")


def _conservative_rows(runs_df, agents_df, pre, x):
    runs = runs_df[runs_df.pre == pre]
    rows = []
    run_metrics = (
        ("RSET_last", "rset_last", "U >= X", 1),
        ("RSET_p95", "rset_p95", "U >= X", 1),
        ("N inside at junction K-ASET", "inside@junction|K 0.3", "U >= X", 1),
        ("agent-s at HCl >= 300 ppm", "agent_s_hcl300", "U >= X", 1),
        ("agent-s at HCl >= 1000 ppm", "agent_s_hcl1000", "U >= X", 1),
        ("median max FIC", "median_max_fic", "U >= X", 1),
        ("max FED", "max_fed", "U >= X", 1),
        ("agents crossing K 0.3 before out", "crossed K 0.3", "U >= X", 1),
        ("agents crossing ISO FEC 0.3 before out", "crossed ISO FEC 0.3", "U >= X", 1),
        ("agent-s at K >= 0.3 (secondary)", "agent_s_k03", "U >= X", 1),
    )
    for metric, column, rule, _ in run_metrics:
        sub = runs.pivot(index="seed", columns="arm", values=column)
        u, v = sub["U"], sub[x]
        text = verdict(u, v) + (
            f"; median X-U {np.nanmedian((v - u).replace([np.inf, -np.inf], np.nan)):.2f}"
        )
        rows.append(
            {"metric": metric, "rule": rule, "pre": pre, "x": x, "result": text}
        )
    for column, metric in (
        ("max_fic", "per agent max FIC (paired agents)"),
        ("s_hcl300", "per agent s at HCl >= 300 ppm (paired agents)"),
    ):
        more, same, less = per_agent_paired(agents_df, x, pre, column)
        rows.append(
            {
                "metric": metric,
                "rule": "U_i >= X_i",
                "pre": pre,
                "x": x,
                "result": f"U>X {more}, U=X {same}, U<X {less}",
            }
        )
    return rows


# --- Figures ---


def _style(ax, grid_axis=None):
    ax.grid(False)
    if grid_axis is not None:
        ax.grid(True, alpha=0.7, linewidth=1, axis=grid_axis)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    sns.despine(ax=ax, left=True, bottom=True)


def _frame(ax):
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)


def _legend(target, **kwargs):
    return target.legend(
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        **kwargs,
    )


def _save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)}")


def _arm_handle(arm, **kwargs):
    colour, ls, marker = STYLE[arm]
    style = {"color": colour, "ls": ls, "marker": marker} | kwargs
    return Line2D([], [], label=LABEL[arm], **style)


def evacuated_curves(runs, pre, arm, grid):
    curves = []
    for seed_dir in sorted((runs / f"pre{pre:02d}").glob("seed*")):
        base = seed_dir / stem(arm)
        if not Path(f"{base}.ok").exists():
            continue
        t = people_of(base)["exit"].dropna().to_numpy()
        curves.append(np.searchsorted(np.sort(t), grid, side="right"))
    return np.asarray(curves)


def fig_evacuated(runs, runs_df, loc):
    grid = np.arange(0.0, CAP + 0.1, 0.5)
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), sharey=True, layout="constrained")
    marks = ("exit B", "junction", "exit A")
    last = 0.0
    for ax, pre in zip(axes, PRES, strict=True):
        for name in marks:
            ax.axvline(loc.loc[name, "K 0.3"], color="grey", lw=0.9, ls=":", zorder=0)
        for arm in MAIN:
            colour, ls, _ = STYLE[arm]
            c = evacuated_curves(runs, pre, arm, grid)
            done = (c == c[:, -1:]).argmax(1)  # first index at the final count
            last = max(last, grid[done.max()])
            ax.fill_between(
                grid, c.min(0), c.max(0), color=colour, alpha=0.18, lw=0, zorder=1
            )
            ax.plot(grid, np.median(c, 0), color=colour, ls=ls, lw=1.8, zorder=2)
        ax.set_title(f"pre-movement {pre} s", loc="left", color=TEXT, fontsize=11)
        ax.set_xlabel("time since ignition [s]", color=TEXT)
        _style(ax, "y")
        _frame(ax)
    for ax in axes:
        ax.set_xlim(0, min(CAP, 10 * math.ceil((last + 15) / 10)))
    axes[0].set_ylabel("agents out (of 100)", color=TEXT)
    aset = ", ".join(f"{n} {loc.loc[n, 'K 0.3']:.0f} s" for n in marks)
    latest = max(loc.loc[n, "K 0.3"] for n in marks)
    main = runs_df[runs_df.arm.isin(MAIN)]
    after = int((main.rset_last > latest).sum())
    axes[0].annotate(
        f"dotted: location ASET, K ≥ 0.3 1/m\n({aset});\n"
        f"the last agent leaves after all\nthree in {after} of {len(main)} runs",
        (0.97, 0.3),
        xycoords="axes fraction",
        ha="right",
        fontsize=9,
        color=TEXT,
    )
    handles = [_arm_handle(a, lw=1.8, marker=None) for a in MAIN]
    handles.append(Patch(fc="grey", alpha=0.25, label="min-max over seeds"))
    _legend(fig, handles=handles, loc="outside lower center", ncols=4, fontsize=9)
    _save(fig, "evacuated.png")


def fig_paired(runs_df):
    """Per-seed RSET_last differences against U."""
    pairs = (("S", "U"), ("R", "U"), ("R-na", "U"))
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True, layout="constrained")
    rng = np.random.default_rng(0)
    for ax, pre in zip(axes, PRES, strict=True):
        ax.axhline(0, color="dimgrey", lw=1, zorder=1)
        for i, (x, y) in enumerate(pairs):
            diff, cens = paired(runs_df, "rset_last", x, y, pre)
            colour, _, marker = STYLE[x]
            jitter = rng.uniform(-0.15, 0.15, len(diff))
            finite = diff[~cens]
            ax.scatter(
                i + jitter[~cens.to_numpy()],
                finite,
                color=colour,
                marker=marker,
                s=26,
                edgecolor="white",
                lw=0.4,
                zorder=3,
            )
            ax.hlines(
                finite.median(), i - 0.28, i + 0.28, color="black", lw=1.4, zorder=4
            )
            pos = int((diff > 0).sum())
            ax.annotate(
                f"{pos}/{len(diff)}\nabove 0",
                (i, 1.0),
                xycoords=("data", "axes fraction"),
                ha="center",
                va="top",
                fontsize=8,
                color=TEXT,
            )
        ax.set_xticks(range(len(pairs)), [f"{x} − {y}" for x, y in pairs])
        ax.margins(y=0.18)
        ax.set_title(f"pre-movement {pre} s", loc="left", color=TEXT, fontsize=11)
        _style(ax, "y")
        _frame(ax)
    axes[0].set_ylabel("RSET_last difference per seed [s]", color=TEXT)
    axes[0].annotate(
        "above 0: the uncoupled\nrun U gets out earlier",
        (0.02, 0.02),
        xycoords="axes fraction",
        fontsize=9,
        color=TEXT,
    )
    handles = [
        Line2D([], [], color="black", lw=1.4, label="median over seeds"),
        *[
            Line2D([], [], ls="", marker=STYLE[x][2], color=STYLE[x][0], label=LABEL[x])
            for x, _ in pairs
        ],
    ]
    _legend(fig, handles=handles, loc="outside lower center", ncols=4, fontsize=9)
    _save(fig, "rset_paired.png")


def fig_additivity(runs_df):
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(7, 5))
    shared = set(runs_df[runs_df.pre == PRES[-1]].seed)
    sub_all = runs_df[runs_df.seed.isin(shared)]
    offsets = {"U": 0.0, "S": -1.5, "R": 1.5}
    for arm in MAIN:
        colour, ls, marker = STYLE[arm]
        sub = sub_all[sub_all.arm == arm]
        for _, s in sub.groupby("seed"):
            s = s.sort_values("pre")
            ax.plot(s.pre + offsets[arm], s.rset_last, color=colour, lw=0.6, alpha=0.35)
        med = sub.groupby("pre").rset_last.median()
        ax.plot(
            med.index + offsets[arm],
            med.values,
            color=colour,
            ls=ls,
            marker=marker,
            lw=2,
            ms=7,
            label=LABEL[arm],
        )
    u0 = sub_all[(sub_all.arm == "U") & (sub_all.pre == 0)].rset_last.median()
    xs = np.array([0, 60])
    ax.plot(xs, u0 + xs, color="black", lw=1, ls=(0, (4, 3)), zorder=0)
    ax.annotate(
        "dashed: slope 1 through U(0). U follows it;\n"
        "S and R rise faster than pre-movement",
        (31, u0 + 31 - 6),
        va="top",
        fontsize=9,
        color=TEXT,
    )
    ax.set_xticks(PRES)
    ax.set_xlabel("constant pre-movement [s]", color=TEXT)
    ax.set_ylabel("RSET_last [s from ignition]", color=TEXT)
    _style(ax, "y")
    _legend(ax, loc="upper left", fontsize=9)
    _save(fig, "additivity.png")


def fig_exposure(agents_df):
    columns = (
        ("max_fic", "max FIC per agent"),
        ("s_hcl300", "seconds at HCl ≥ 300 ppm"),
        ("s_k03", "seconds at K ≥ 0.3 1/m (secondary)"),
    )
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(3, 3, figsize=(12, 9.5), layout="constrained")
    for i, pre in enumerate(PRES):
        for j, (column, title) in enumerate(columns):
            ax = axes[i, j]
            for arm in MAIN:
                colour, ls, _ = STYLE[arm]
                v = np.sort(
                    agents_df[(agents_df.pre == pre) & (agents_df.arm == arm)][column]
                )
                ax.step(
                    v,
                    np.arange(1, len(v) + 1) / len(v),
                    where="post",
                    color=colour,
                    ls=ls,
                    lw=1.6,
                )
            ax.set_ylim(0, 1.02)
            if i == 0:
                ax.set_title(title, loc="left", color=TEXT, fontsize=11)
            if j == 0:
                ax.set_ylabel(f"pre {pre} s\nshare of agents ≤ x", color=TEXT)
            _style(ax, "both")
            _frame(ax)
    for j in range(3):
        top = max(axes[i, j].get_xlim()[1] for i in range(3))
        for i in range(3):
            axes[i, j].set_xlim(0, top)
    axes[0, 0].annotate(
        "curve further right:\nmore dose",
        (0.55, 0.15),
        xycoords="axes fraction",
        fontsize=9,
        color=TEXT,
    )
    handles = [_arm_handle(a, lw=1.6, marker=None) for a in MAIN]
    _legend(fig, handles=handles, loc="outside lower center", ncols=3, fontsize=9)
    _save(fig, "exposure.png")


def fig_margins(runs_df, loc):
    """Location margin at fixed points, the same points for every arm."""
    keys = (("K 0.3", "K ≥ 0.3 1/m"), ("ISO FEC 0.3", "HCl ≥ 300 ppm"))
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(
        2, 3, figsize=(12, 6), sharex=True, sharey=True, layout="constrained"
    )
    arms = ("U", "S", "R", "R-na")
    offsets = dict(zip(arms, (-0.24, -0.08, 0.08, 0.24), strict=True))
    for i, (key, name) in enumerate(keys):
        for j, pre in enumerate(PRES):
            ax = axes[i, j]
            ax.axvline(0, color="dimgrey", lw=1, zorder=1)
            for arm in arms:
                colour, _, marker = STYLE[arm]
                sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
                for k, point in enumerate(FIXED_POINTS):
                    m = loc.loc[point, key] - sub.rset_last.to_numpy()
                    y = k + offsets[arm]
                    ax.hlines(y, m.min(), m.max(), color=colour, lw=1.2, zorder=2)
                    ax.plot(
                        np.median(m),
                        y,
                        marker=marker,
                        color=colour,
                        ms=6,
                        mec="white",
                        mew=0.4,
                        ls="",
                        zorder=3,
                    )
            ax.set_yticks(range(len(FIXED_POINTS)), FIXED_POINTS)
            if i == 0:
                ax.set_title(
                    f"pre-movement {pre} s", loc="left", color=TEXT, fontsize=11
                )
            if j == 0:
                ax.set_ylabel(name, color=TEXT)
            if i == 1:
                ax.set_xlabel("location ASET − RSET_last [s]", color=TEXT)
            _style(ax, "x")
            _frame(ax)
    shown = runs_df[runs_df.arm.isin(arms)]
    aset = loc.loc[list(FIXED_POINTS), [k for k, _ in keys]].to_numpy()
    margin = aset[None, :, :] - shown.rset_last.to_numpy()[:, None, None]
    n_pos = int((margin >= 0).sum())
    n_nan = int(np.isnan(aset).sum())
    note = (
        f"margin ≥ 0 in {n_pos} of {margin.size}\nrun × point × limit cases"
        if n_pos
        else "negative in every run,\nat every point, for both limits"
    )
    if n_nan:
        note += f"\n({n_nan} point-limit pairs never met, not drawn)"
    axes[0, 0].annotate(
        note,
        (0.03, 0.97),
        xycoords="axes fraction",
        va="top",
        fontsize=9,
        color=TEXT,
    )
    handles = [
        Line2D([], [], ls="", marker=STYLE[a][2], color=STYLE[a][0], label=LABEL[a])
        for a in arms
    ]
    handles.append(Line2D([], [], color="grey", lw=1.2, label="min-max over seeds"))
    _legend(fig, handles=handles, loc="outside lower center", ncols=5, fontsize=9)
    _save(fig, "margins.png")


def fig_exit_usage(runs_df):
    arms = ("C", "U", "S", "R", "R-na", "R-det", "R-prob", "R+FIC")
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True, layout="constrained")
    rng = np.random.default_rng(1)
    for ax, pre in zip(axes, PRES, strict=True):
        for i, arm in enumerate(arms):
            sub = runs_df[(runs_df.pre == pre) & (runs_df.arm == arm)]
            share = 100 * sub.exit_A / sub.n
            colour, _, marker = STYLE[arm]
            ax.bar(i, share.median(), color=colour, alpha=0.55, width=0.7)
            ax.scatter(
                i + rng.uniform(-0.2, 0.2, len(share)),
                share,
                color="black",
                s=8,
                marker=marker,
                lw=0.6,
                zorder=3,
            )
        ax.set_xticks(range(len(arms)), arms, rotation=45)
        ax.set_ylim(0, 105)
        ax.set_title(f"pre-movement {pre} s", loc="left", color=TEXT, fontsize=11)
        _style(ax, "y")
    axes[0].set_ylabel("agents leaving by exit A [%]", color=TEXT)
    all_b = [a for a in arms if (runs_df[runs_df.arm == a].exit_A == 0).all()]
    axes[0].annotate(
        f"{', '.join(all_b)}: every agent of\nevery run leaves by exit B,\n10 m from the junction",
        (-0.4, 45),
        fontsize=9,
        color=TEXT,
    )
    handles = [
        Patch(fc="grey", alpha=0.55, label="median over seeds"),
        Line2D([], [], ls="", marker="o", color="black", ms=3, label="one seed"),
    ]
    _legend(fig, handles=handles, loc="outside lower center", ncols=2, fontsize=9)
    _save(fig, "exit_usage.png")


def fig_speed_extrapolation(k_samples):
    cfg = SmokeSpeedConfig()
    floor_k = (cfg.min_speed_factor - 1.0) * cfg.alpha / cfg.beta
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, (top, bottom) = plt.subplots(
        1, 2, figsize=(13, 4.6), sharex=True, layout="constrained"
    )
    k = np.linspace(0, 25, 500)
    f = np.clip(1 + cfg.beta * k / cfg.alpha, cfg.min_speed_factor, 1.0)
    inside = (k >= FN_K[0]) & (k <= FN_K[1])
    top.plot(k, np.where(inside, f, np.nan), color="black", lw=2, label="data range")
    top.plot(
        k,
        np.where(inside, np.nan, f),
        color="black",
        lw=1.4,
        ls="--",
        label="extrapolation",
    )
    top.axvspan(*FN_K, color="#4575b4", alpha=0.12, lw=0)
    top.annotate(
        "Frantzich and Nilsson\ndata, K 1.9-7.4 1/m",
        (np.mean(FN_K), 0.32),
        ha="center",
        fontsize=9,
        color=TEXT,
    )
    top.annotate(
        f"floor 0.1 from K = {floor_k:.1f} 1/m",
        (floor_k + 0.4, 0.14),
        fontsize=9,
        color=TEXT,
    )
    top.set_ylabel("speed factor v/v₀", color=TEXT)
    top.set_xlabel("extinction coefficient K [1/m]", color=TEXT)
    top.set_ylim(0, 1.05)
    _style(top, "y")
    _legend(top, loc="upper right", fontsize=9)
    bins = np.linspace(0, 25, 51)
    for arm in ("S", "R"):
        colour, ls, _ = STYLE[arm]
        v = np.clip(np.concatenate(k_samples[arm]), 0, 25)
        bottom.hist(
            v,
            bins=bins,
            histtype="step",
            color=colour,
            ls=ls,
            lw=1.6,
            weights=np.full(len(v), 100 / len(v)),
            label=LABEL[arm],
        )
    bottom.axvspan(*FN_K, color="#4575b4", alpha=0.12, lw=0)
    bottom.axvline(floor_k, color="dimgrey", lw=1, ls=":")
    bottom.set_xlabel(
        "K at the moving agent [1/m] (last bin: ≥ 24.5)",
        color=TEXT,
    )
    bottom.set_ylabel("share of agent-seconds [%]", color=TEXT)
    bottom.set_xlim(0, 25)
    lines = []
    for arm in ("S", "R"):
        v = np.concatenate(k_samples[arm])
        lines.append(
            f"{arm}: {(v > FN_K[1]).mean():.0%} above 7.4 1/m, "
            f"{(v >= floor_k).mean():.0%} at the floor"
        )
    bottom.annotate(
        "moving agent-seconds\n" + "\n".join(lines),
        (0.97, 0.45),
        xycoords="axes fraction",
        ha="right",
        fontsize=9,
        color=TEXT,
    )
    _style(bottom, "y")
    _legend(bottom, loc="upper right", fontsize=9)
    _save(fig, "speed_extrapolation.png")


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data", required=True, type=Path, help="FDS output directory")
    parser.add_argument("--runs", required=True, type=Path, help="run outputs")
    parser.add_argument("--seeds-pre0", default="4-23", help="seed range at pre 0")
    parser.add_argument("--seeds", default="4-13", help="seed range at pre 30, 60")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    runs = args.runs.resolve()
    assert ROOT not in runs.parents, "runs go outside the repository"

    def seeds_of(text):
        lo, hi = (int(v) for v in text.split("-"))
        return range(lo, hi + 1)

    seeds = {
        0: seeds_of(args.seeds_pre0),
        30: seeds_of(args.seeds),
        60: seeds_of(args.seeds),
    }
    write_noanticipate(runs)
    phase1 = [
        (arm, pre, seed, runs, args.data)
        for pre in PRES
        for seed in seeds[pre]
        for arm in ARMS
        if arm != "S"
    ]
    phase2 = [("S", pre, seed, runs, args.data) for pre in PRES for seed in seeds[pre]]
    print("== Runs ==")
    status, wall_runs = run_all((phase1, phase2), args.workers)
    print(f"runs wall time {wall_runs:.0f} s")
    report_compute(runs)

    start = time.perf_counter()
    loc = fixed_point_aset(args.data)
    config = json.loads((ASSET / "config_initial_pre0.json").read_text())
    route = longest_route_m(config)
    rows, tables, k_samples, checks = [], [], {"S": [], "R": []}, []
    for (arm, pre, seed), state in sorted(status.items()):
        if state.startswith("crashed"):
            continue
        base = run_dir(runs, pre, seed) / stem(arm)
        row, table, k_moving = summarise_run(arm, pre, seed, base, loc)
        rows.append(row)
        if table is not None:
            tables.append(table)
        if arm in k_samples:
            k_samples[arm].append(k_moving)
    for pre in PRES:
        for seed in seeds[pre]:
            dist, unmatched = position_difference(run_dir(runs, pre, seed))
            checks.append(
                {"pre": pre, "seed": seed, "max_dist": dist, "unmatched": unmatched}
            )
    runs_df = pd.DataFrame(rows)
    agents_df = pd.concat(tables, ignore_index=True)
    runs_df.to_csv(runs / "summary_runs.csv", index=False)
    agents_df.to_csv(runs / "summary_agents.csv")

    report_runs(runs_df, status, loc, route, pd.DataFrame(checks))
    report_rset(runs_df)
    report_additivity(runs_df)
    report_tenability(runs_df, agents_df)
    report_margins(runs_df, loc)
    report_dose(runs_df, agents_df)
    report_agent_margins(agents_df)
    report_conservative(runs_df, agents_df)

    fig_evacuated(runs, runs_df, loc)
    fig_paired(runs_df)
    fig_additivity(runs_df)
    fig_exposure(agents_df)
    fig_margins(runs_df, loc)
    fig_exit_usage(runs_df)
    fig_speed_extrapolation(k_samples)
    print(f"analysis wall time {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
