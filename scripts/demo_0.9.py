"""Show the 0.9.0 fixes as one figure each.

Every panel runs a small built-in room (the rooms of the tests) on the current
code and writes one PNG. Only panel 6 reads FDS output (``--thinwall-dir``):
run ``scripts/demo_0.9_thinwall.fds`` with FDS (a few seconds) and pass its
output directory. The rooms come from the test modules, so the dev group must
be installed.
Where the behaviour before a fix cannot be reproduced on this code, the caption
says so; nothing here fakes a "before".

    python scripts/demo_0.9.py --out artifacts/demo_0.9 --seeds 10
    python scripts/demo_0.9.py --only fed queue
    python scripts/demo_0.9.py --thinwall-dir path/to/thinwall_output
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
DPI = 150
GREY = "dimgrey"
PAL = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
# ColorBrewer RdYlBu (colour-blind safe), the house diverging set.
RED, ORANGE, YELLOW, BLUE = "#d73027", "#fc8d59", "#fee090", "#4575b4"
LEGEND = {
    "frameon": True,
    "facecolor": "white",
    "framealpha": 0.8,
    "edgecolor": "lightgrey",
    "labelcolor": GREY,
}


# --- shared helpers ----------------------------------------------------------


def _setup_style() -> None:
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")


def _tidy(*axes, frame: bool = True) -> None:
    """Apply the house axes cleanup: no spines, no grid, quiet ticks."""
    sns.despine(left=True, bottom=True)
    for ax in axes:
        ax.grid(False)
        ax.tick_params(axis="both", which="both", length=0, labelcolor=GREY)
        if frame:
            ax.patch.set_edgecolor("lightgrey")
            ax.patch.set_linewidth(0.8)


def _note(ax, x: float, y: float, text: str, **kwargs) -> None:
    kwargs.setdefault("ha", "left")
    kwargs.setdefault("va", "top")
    ax.text(x, y, text, transform=ax.transAxes, fontsize=9, color=GREY, **kwargs)


def _caption(fig, text: str) -> None:
    fig.text(0.01, -0.02, text, ha="left", va="top", fontsize=8.5, color=GREY)


def _save(fig, out: Path, name: str) -> Path:
    path = out / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def _use_worktree_code() -> None:
    """Put the repo and its tests first on the path, and say which code runs."""
    for entry in (str(TESTS), str(ROOT)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import pyfds_evac

    package = Path(pyfds_evac.__file__).resolve()
    if ROOT not in package.parents:
        raise SystemExit(f"pyfds_evac comes from {package}, not from {ROOT}")


def _quiet(call: Callable, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


# --- 1. FED activity level (#135, PR 966) ------------------------------------

FED_THRESHOLD = 1.0
FED_LEVELS = ("rest", "light", "heavy")
FED_STYLES = {
    "rest": (BLUE, ":", "o"),
    "light": (PAL[3], "-", "s"),
    "heavy": (RED, "--", "^"),
}


class _ConstantGas:
    """A constant exposure with O2 at ambient, so CO is the only narcotic term."""

    def sample_inputs(self, time_s, x, y):
        from pyfds_evac.core.fed import DefaultFedInputs

        return DefaultFedInputs(
            co_volume_fraction_percent=0.3,
            co2_volume_fraction_percent=2.0,
            o2_volume_fraction_percent=20.9,
        )


def _fed_curve(level: str, horizon_s: float) -> tuple[np.ndarray, np.ndarray]:
    from pyfds_evac.core.fed import DefaultFedConfig, DefaultFedModel

    model = DefaultFedModel(_ConstantGas(), DefaultFedConfig(activity_level=level))
    times = np.arange(0.0, horizon_s + 1.0, 1.0)
    fed, values = 0.0, [0.0]
    for t in times[:-1]:
        _, _, fed = model.advance(t, 0.0, 0.0, dt_s=1.0, current_fed=fed)
        values.append(fed)
    return times / 60.0, np.asarray(values)


def _first_crossing_min(minutes: np.ndarray, fed: np.ndarray) -> float:
    above = np.nonzero(fed >= FED_THRESHOLD)[0]
    return float(minutes[above[0]]) if above.size else float("nan")


def panel_fed(out: Path, seeds: int) -> Path:
    horizon_s = 45 * 60.0
    curves = {lvl: _fed_curve(lvl, horizon_s) for lvl in FED_LEVELS}
    cross = {lvl: _first_crossing_min(*curves[lvl]) for lvl in FED_LEVELS}
    xmax = 1.25 * cross["rest"]

    fig, ax = plt.subplots(figsize=(10, 6), dpi=DPI)
    ax.axhline(FED_THRESHOLD, color=GREY, linewidth=1.0, zorder=1)
    for lvl in FED_LEVELS:
        colour, style, marker = FED_STYLES[lvl]
        minutes, fed = curves[lvl]
        ax.plot(minutes, fed, color=colour, linestyle=style, linewidth=2.5, zorder=3)
        ax.scatter(
            cross[lvl], FED_THRESHOLD, color=colour, marker=marker, s=70,
            edgecolors="white", linewidths=0.8, zorder=4,
        )  # fmt: skip
        ax.annotate(
            f"{lvl}: {cross[lvl]:.1f} min",
            (cross[lvl], FED_THRESHOLD),
            xytext=(6, 10) if lvl == "heavy" else (8, -16),
            textcoords="offset points",
            fontsize=10,
            color=colour,
            weight="semibold",
        )
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, 1.25)
    ax.text(
        xmax * 0.99, FED_THRESHOLD + 0.03, "incapacitation, FED = 1",
        ha="right", va="bottom", fontsize=9, color=GREY,
    )  # fmt: skip
    ax.set_xlabel("Time in the smoke [min]", fontsize=12, labelpad=8, color=GREY)
    ax.set_ylabel("Cumulative FED [-]", fontsize=12, labelpad=8, color=GREY)
    ax.set_title(
        "FED activity level: one agent, one gas exposure", loc="left", fontsize=14,
        pad=7, color=GREY,
    )  # fmt: skip
    ratio = cross["light"] / cross["heavy"]
    _note(
        ax, 0.32, 0.97,
        f"Heavy work reaches FED = 1 {ratio:.1f}x sooner than light work\n"
        f"(rest: {cross['rest'] / cross['light']:.1f}x later), through the CO term only.",
        style="italic",
    )  # fmt: skip
    handles = [
        Line2D([0], [0], color=FED_STYLES[lvl][0], linestyle=FED_STYLES[lvl][1],
               marker=FED_STYLES[lvl][2], linewidth=2.5, label=lvl)
        for lvl in FED_LEVELS
    ]  # fmt: skip
    legend = ax.legend(
        handles=handles, title="activity_level", loc="center right", **LEGEND
    )
    legend.get_title().set_color(GREY)
    _tidy(ax)
    _caption(
        fig,
        "Constant exposure: CO 0.3 % (3000 ppm), CO2 2 %, O2 20.9 %, stepped through "
        "DefaultFedModel.advance (dt 1 s).\nWith O2 at ambient CO is the only "
        "narcotic term that depends on activity, so the ratios are V_E/D "
        "relative to light work (PR 966). Light is the default.",
    )
    return _save(fig, out, "01_fed_activity_level.png")


# --- 2. per-exit familiarity (#136, PR 968) ----------------------------------

FAMILIARITY = {"exit_1": 0.8, "exit_2": 0.2}
FAMILIARITY_AGENTS = 30


def _familiarity_scenario(seed: int):
    from shapely.geometry import box
    from test_iso_test_16_familiar_exit import _coords, _scenario

    scenario = _scenario(
        seed, {"familiarity": FAMILIARITY, "number": FAMILIARITY_AGENTS}
    )
    spawn = box(3.0, 5.5, 7.0, 9.5)  # symmetric between the two doors
    scenario.raw["distributions"]["occupant"]["coordinates"] = _coords(spawn)
    scenario.sim_params["max_simulation_time"] = 120.0
    return scenario


def _familiarity_run(seed: int) -> dict:
    from test_iso_test_16_familiar_exit import REROUTE

    from pyfds_evac.core.scenario import run_scenario

    result = _quiet(
        run_scenario,
        _familiarity_scenario(seed),
        seed=seed,
        reroute_config=REROUTE,
        collect_cognitive_map_history=True,
    )
    try:
        used = Counter(r["exit_id"] for r in result.exit_history)
        known = {
            exit_id: len(
                {
                    r["agent_id"]
                    for r in result.knowledge_history
                    if r["how"] == "familiarity_draw" and r["exit_id"] == exit_id
                }
            )
            for exit_id in FAMILIARITY
        }
        return {"used": used, "known": known, "n": sum(used.values())}
    finally:
        result.cleanup()


def _share_rows(runs: list[dict], key: str) -> dict[str, list[float]]:
    return {e: [r[key][e] / r["n"] for r in runs] for e in FAMILIARITY}


def panel_familiarity(out: Path, seeds: int) -> Path:
    runs = [_familiarity_run(seed) for seed in range(1, seeds + 1)]
    n_agents = sum(r["n"] for r in runs)
    known = _share_rows(runs, "known")
    used = _share_rows(runs, "used")
    pooled = {
        "known": {e: sum(r["known"][e] for r in runs) / n_agents for e in FAMILIARITY},
        "used": {e: sum(r["used"][e] for r in runs) / n_agents for e in FAMILIARITY},
    }

    fig, ax = plt.subplots(figsize=(10, 6), dpi=DPI)
    width = 0.26
    spec = (
        ("configured", PAL[5], "//", -width),
        ("known at t = 0", PAL[2], "..", 0.0),
        ("used to leave", RED, "", width),
    )
    rng = np.random.default_rng(0)
    for i, exit_id in enumerate(FAMILIARITY):
        values = (
            FAMILIARITY[exit_id], pooled["known"][exit_id], pooled["used"][exit_id]
        )  # fmt: skip
        per_seed = (None, known[exit_id], used[exit_id])
        for (label, colour, hatch, shift), value, dots in zip(spec, values, per_seed):
            kwargs = (
                {"facecolor": "none"}
                if label == "configured"
                else {"facecolor": colour}
            )
            ax.bar(
                i + shift, value, width=width * 0.92, edgecolor=colour, hatch=hatch,
                linewidth=1.4, alpha=0.9, zorder=2, **kwargs,
            )  # fmt: skip
            ax.text(
                i + shift, 0.02, f"{value:.2f}", ha="center", va="bottom",
                fontsize=10, weight="semibold", color=GREY,
                bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 1.5},
                zorder=5,
            )  # fmt: skip
            if dots is not None:
                jitter = rng.uniform(-width * 0.25, width * 0.25, len(dots))
                ax.scatter(
                    i + shift + jitter, dots, s=14, color="white", edgecolors=GREY,
                    linewidths=0.7, zorder=4,
                )  # fmt: skip
    ax.set_xticks(range(len(FAMILIARITY)))
    ax.set_xticklabels(
        [f"{e}   (p = {p})" for e, p in FAMILIARITY.items()], fontsize=11
    )
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Share of agents", fontsize=12, labelpad=8, color=GREY)
    ax.set_title(
        "Per-exit familiarity {exit_1: 0.8, exit_2: 0.2}", loc="left", fontsize=14,
        pad=7, color=GREY,
    )  # fmt: skip
    handles = [
        Patch(
            facecolor="none" if lbl == "configured" else c,
            edgecolor=c,
            hatch=h,
            label=lbl,
        )
        for lbl, c, h, _ in spec
    ]
    handles.append(
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
               markeredgecolor=GREY, markersize=5, label="one seed")
    )  # fmt: skip
    ax.legend(handles=handles, loc="upper right", fontsize=10, **LEGEND)
    _note(
        ax, 0.02, 0.97,
        f"The known share follows the configured p (n = {n_agents} agents, "
        f"{seeds} seeds).\nThe exit share is not p: an agent that knows both or "
        "neither exit\ntakes the nearest one (here that happens to give 0.8 / 0.2).",
        style="italic",
    )  # fmt: skip
    _tidy(ax)
    _caption(
        fig,
        f"10 x 15 m room, doors at x = 0 and x = 10, {FAMILIARITY_AGENTS} agents per "
        "seed in a spawn area centred between the doors (the room of the ISO 20414 "
        "test 16 deck).\nNo 'before' is drawn: the dict form did not exist (PR 968).",
    )
    return _save(fig, out, "02_per_exit_familiarity.png")


# --- 3. queue ahead-count (#89, PR 970) --------------------------------------

QUEUE_CAPACITY = 1.3
QUEUE_AGENTS = 40


def _queue_run(tmp: Path) -> dict:
    from test_queue_ahead import CORRIDOR_POINTS, _corridor, _positions, _run

    result = _run(_corridor(tmp), 1, w_queue=1.0)
    try:
        spawn = {int(r["agent_id"]): int(r["spawn_index"]) for r in result.exit_history}
        switched = {
            spawn[int(r["agent_id"])]
            for r in result.route_history
            if r["reason"] == "congestion"
        }
        rows = [r for r in result.route_cost_history if r["exit_id"] == "exit_B_right"]
        first = min(float(r["time_s"]) for r in rows)
        positions = _positions(result, first)
        centre = CORRIDOR_POINTS["exit_B_right"]
        at_first = [
            {
                "k": spawn[int(r["agent_id"])],
                "ahead": int(r["exit_queue_ahead"]),
                "distance": float(
                    np.hypot(*(np.subtract(positions[int(r["agent_id"])], centre)))
                ),
            }
            for r in rows
            if float(r["time_s"]) == first and int(r["agent_id"]) in positions
        ]
        series: dict[int, list[tuple[float, int]]] = {}
        for r in rows:
            series.setdefault(spawn[int(r["agent_id"])], []).append(
                (float(r["time_s"]), int(r["exit_queue_ahead"]))
            )
        return {
            "first_s": first,
            "first": at_first,
            "switched": switched,
            "series": series,
        }
    finally:
        result.cleanup()


def panel_queue(out: Path, seeds: int) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        data = _queue_run(Path(tmp))
    first = sorted(data["first"], key=lambda r: r["k"])
    stayed = [r for r in first if r["k"] not in data["switched"]]
    moved = [r for r in first if r["k"] in data["switched"]]

    fig = plt.figure(figsize=(14, 6), dpi=DPI)
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.15, 1.0], wspace=0.18)
    ax1, ax2 = plt.subplot(gs[0]), plt.subplot(gs[1])

    ax1.plot(
        [r["distance"] for r in first], [r["k"] for r in first], color="lightgrey",
        linewidth=1.5, zorder=1,
    )  # fmt: skip
    ax1.scatter(
        [r["distance"] for r in stayed], [r["ahead"] for r in stayed], color=PAL[4],
        marker="o", s=45, edgecolors="white", linewidths=0.7, zorder=3,
        label="stays on B",
    )  # fmt: skip
    ax1.scatter(
        [r["distance"] for r in moved], [r["ahead"] for r in moved], color=RED,
        marker="^", s=60, edgecolors="white", linewidths=0.7, zorder=4,
        label="switches to A (congestion)",
    )  # fmt: skip
    ax1.set_xlabel("Distance to exit B [m]", fontsize=12, labelpad=8, color=GREY)
    ax1.set_ylabel("Agents ahead at exit B", fontsize=12, labelpad=8, color=GREY)
    ax1.set_title(
        r"$\bf{(a)}$" + f"  First pass, t = {data['first_s']:.0f} s", loc="left",
        fontsize=12, pad=7, color=GREY,
    )  # fmt: skip
    handles, labels = ax1.get_legend_handles_labels()
    handles.append(Line2D([0], [0], color="lightgrey", linewidth=1.5))
    labels.append("k, agents ahead at t = 0")
    ax1.legend(handles, labels, loc="lower right", fontsize=10, **LEGEND)
    ahead_max = max(r["ahead"] for r in first)
    _note(
        ax1, 0.02, 0.97,
        "The count follows the distance to B: the agent at the head sees 0, not\n"
        f"all {QUEUE_AGENTS} holders of B. Each switcher sees {ahead_max}: the others "
        "have left B,\nso only the agents that stay are ahead of it.",
        style="italic",
    )  # fmt: skip

    ks = sorted(data["series"])
    chosen = [k for k in (5, 10, 15, 20) if k in ks]
    colours = sns.cubehelix_palette(len(chosen), rot=-0.25, light=0.7)
    for k, colour, style in zip(chosen, colours, ("-", "--", "-.", ":")):
        times, ahead = zip(*data["series"][k])
        ax2.step(times, ahead, where="post", color=colour, linewidth=2.3,
                 linestyle=style, zorder=3)  # fmt: skip
        ax2.text(times[-1] + 0.3, 0.3, f"agent {k}", fontsize=9, color=colour,
                 ha="left", va="bottom")  # fmt: skip
    ax2.set_xlabel("Time [s]", fontsize=12, labelpad=8, color=GREY)
    ax2.set_title(
        r"$\bf{(b)}$" + "  Agents ahead at B, four agents that stay on B", loc="left",
        fontsize=12, pad=7, color=GREY,
    )  # fmt: skip
    ax2.set_xlim(0, max(t for k in chosen for t, _ in data["series"][k]) + 3.5)
    ax2.set_ylim(bottom=0)
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
    _tidy(ax1, ax2)
    _caption(
        fig,
        "Corridor 44 x 3 m of tests/test_queue_ahead.py: exit A west, exit B east, 40 agents "
        "in a line, all nearer to B; w_queue = 1, capacity 1.3 agents/s, seed 1.\n"
        "Agent k has k agents strictly closer to B at the start (grey line). The "
        "old global tally charged every agent all 40 holders; that is not rerun "
        "here, the code no longer has it.",
    )
    return _save(fig, out, "03_queue_ahead_count.png")


# --- 4. AVM seed (#758, PR 972) ----------------------------------------------

AVM_SEED = 5
AVM_OTHER_SEED = 6

# One process runs the 10 x 6 m two-door room of test_run_log with the AVM and
# writes its trajectories (frame, id, x, y) next to a hash of them.
_AVM_CHILD = """
import contextlib, hashlib, io, json, sqlite3, sys
sys.path.insert(0, {tests!r})
sys.path.insert(0, {root!r})
import numpy as np
import pyfds_evac
from test_run_log import _scenario
from pyfds_evac.core.scenario import run_scenario

scenario = _scenario()
scenario.sim_params["max_simulation_time"] = 30.0
scenario.model_type = "AnticipationVelocityModel"
scenario.sim_params["model_type"] = "AnticipationVelocityModel"
with contextlib.redirect_stdout(io.StringIO()):
    result = run_scenario(scenario, seed=int(sys.argv[1]))
try:
    with sqlite3.connect(result.sqlite_file) as db:
        rows = db.execute(
            "SELECT frame, id, pos_x, pos_y FROM trajectory_data ORDER BY frame, id"
        ).fetchall()
    np.save(sys.argv[2], np.asarray(rows, dtype=float))
    digest = hashlib.sha256(repr(rows).encode()).hexdigest()
    print(json.dumps({{"hash": digest, "time": result.evacuation_time,
                      "code": pyfds_evac.__file__}}))
finally:
    result.cleanup()
"""


def _avm_process(seed: int, tmp: Path, tag: str) -> dict:
    target = tmp / f"{tag}.npy"
    code = _AVM_CHILD.format(tests=str(TESTS), root=str(ROOT))
    done = subprocess.run(
        [sys.executable, "-c", code, str(seed), str(target)],
        capture_output=True, text=True, env=os.environ, check=False,
    )  # fmt: skip
    if done.returncode != 0:
        raise RuntimeError(done.stderr)
    info = json.loads(done.stdout.strip().splitlines()[-1])
    if ROOT not in Path(info["code"]).resolve().parents:
        raise RuntimeError(f"child ran {info['code']}, not the worktree code")
    return {**info, "rows": np.load(target)}


def _draw_trajectories(ax, rows: np.ndarray, **style) -> None:
    for agent in np.unique(rows[:, 1]):
        mine = rows[rows[:, 1] == agent]
        ax.plot(mine[:, 2], mine[:, 3], **style)


def panel_avm(out: Path, seeds: int) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        first = _avm_process(AVM_SEED, Path(tmp), "first")
        second = _avm_process(AVM_SEED, Path(tmp), "second")
        other = _avm_process(AVM_OTHER_SEED, Path(tmp), "other")
    same = first["hash"] == second["hash"]
    gap = (
        float(np.abs(first["rows"] - second["rows"]).max())
        if first["rows"].shape == second["rows"].shape
        else float("nan")
    )

    fig = plt.figure(figsize=(13, 5.4), dpi=DPI)
    gs = gridspec.GridSpec(1, 2, width_ratios=[2.4, 1.0], wspace=0.06)
    ax, side = plt.subplot(gs[0]), plt.subplot(gs[1])
    ax.add_patch(Rectangle((0, 0), 10, 6, facecolor="none", edgecolor="lightgrey"))
    for x0 in (-1.0, 10.0):
        ax.add_patch(
            Rectangle(
                (x0, 2.5), 1.0, 1.0, facecolor=PAL[1], edgecolor="none", alpha=0.7
            )
        )
    _draw_trajectories(ax, other["rows"], color="grey", linewidth=1.4, alpha=0.45,
                       linestyle=":", zorder=1)  # fmt: skip
    _draw_trajectories(
        ax, first["rows"], color=PAL[2], linewidth=6, alpha=0.55, zorder=2
    )
    _draw_trajectories(
        ax, second["rows"], color=RED, linewidth=1.3, linestyle="--", zorder=3
    )
    ax.set_xlim(-1.2, 11.2)
    ax.set_ylim(-0.2, 6.2)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]", fontsize=12, labelpad=8, color=GREY)
    ax.set_ylabel("y [m]", fontsize=12, labelpad=8, color=GREY)
    ax.set_title(
        "AnticipationVelocityModel, same seed, two processes", loc="left",
        fontsize=14, pad=7, color=GREY,
    )  # fmt: skip
    handles = [
        Line2D([0], [0], color=PAL[2], linewidth=6, alpha=0.55,
               label=f"process 1, seed {AVM_SEED}"),
        Line2D([0], [0], color=RED, linewidth=1.3, linestyle="--",
               label=f"process 2, seed {AVM_SEED}"),
        Line2D([0], [0], color="grey", linewidth=1.4, linestyle=":",
               label=f"process 3, seed {AVM_OTHER_SEED}"),
    ]  # fmt: skip
    ax.legend(handles=handles, loc="lower center", fontsize=9, **LEGEND)

    side.axis("off")
    verdict = "identical" if same else "DIFFERENT"
    lines = [
        ("Trajectory hash (sha256)", "semibold"),
        (f"seed {AVM_SEED}, process 1\n  {first['hash'][:16]}", "normal"),
        (f"seed {AVM_SEED}, process 2\n  {second['hash'][:16]}", "normal"),
        (f"seed {AVM_OTHER_SEED}, process 3\n  {other['hash'][:16]}", "normal"),
        (f"Runs 1 and 2: {verdict}\nmax |difference| = {gap:g} m", "semibold"),
        (f"Evacuation time: {first['time']:.2f} s, {second['time']:.2f} s,\n"
         f"{other['time']:.2f} s (seed {AVM_OTHER_SEED})", "normal"),
    ]  # fmt: skip
    y = 0.95
    for text, weight in lines:
        side.text(0.0, y, text, transform=side.transAxes, fontsize=10, color=GREY,
                  weight=weight, va="top", family="DejaVu Sans")  # fmt: skip
        y -= 0.06 * (text.count("\n") + 1) + 0.035
    _tidy(ax, frame=False)
    _caption(
        fig,
        "Room of tests/test_run_log.py (10 x 6 m, a door in each end wall, six agents), each run in its own "
        "Python process. Before PR 972 JuPedSim drew the model's rng_seed per process, so\n"
        "the same seed gave different runs; that divergence is not reproduced here "
        "(the code now derives rng_seed from the run seed).",
    )
    return _save(fig, out, "04_avm_seed.png")


# --- 5. sub-second reroute (#660, PR 973) ------------------------------------

REROUTE_INTERVALS = (0.5, 1.0, 10.0)
CLOSE_TIMES_S = (4.1, 4.3, 5.1, 5.3, 6.1, 6.3)
REROUTE_STYLES = {0.5: (RED, "^"), 1.0: (PAL[3], "s"), 10.0: (BLUE, "o")}


def _pass_record(interval_s: float) -> dict:
    """Pass times and the times at which an agent actually re-evaluates."""
    from test_scheduled_exits import _scenario

    from pyfds_evac.core import scenario as scenario_module
    from pyfds_evac.core.route_graph import RerouteConfig
    from pyfds_evac.core.scenario import run_scenario

    passes: set[float] = set()
    evaluations: set[float] = set()
    real = scenario_module.should_reevaluate

    def recording(current_time_s, state, interval):
        due = real(current_time_s, state, interval)
        passes.add(round(current_time_s, 6))
        if due:
            evaluations.add(round(current_time_s, 6))
        return due

    scenario_module.should_reevaluate = recording
    try:
        scenario = _scenario({})
        scenario.sim_params["max_simulation_time"] = 12.0
        result = _quiet(
            run_scenario, scenario,
            reroute_config=RerouteConfig(reevaluation_interval_s=interval_s),
        )  # fmt: skip
        result.cleanup()
    finally:
        scenario_module.should_reevaluate = real
    return {"passes": sorted(passes), "evaluations": sorted(evaluations)}


def _closure_latency(interval_s: float, close_s: float) -> float:
    """Seconds from a west-door closure to the first agent leaving its route."""
    from test_scheduled_exits import _scenario

    from pyfds_evac.core.route_graph import RerouteConfig
    from pyfds_evac.core.scenario import run_scenario

    scenario = _scenario({"west": {"closed_after_s": close_s}})
    scenario.sim_params["max_simulation_time"] = close_s + 3.0
    result = _quiet(
        run_scenario, scenario,
        reroute_config=RerouteConfig(reevaluation_interval_s=interval_s),
    )  # fmt: skip
    try:
        times = [
            float(r["time_s"]) for r in result.route_history or []
            if r["reason"] == "exit_closed"
        ]  # fmt: skip
        return min(times) - close_s if times else float("nan")
    finally:
        result.cleanup()


def panel_reroute(out: Path, seeds: int) -> Path:
    records = {i: _pass_record(i) for i in REROUTE_INTERVALS}
    latency = {
        i: [_closure_latency(i, c) for c in CLOSE_TIMES_S] for i in REROUTE_INTERVALS
    }

    fig = plt.figure(figsize=(14, 6), dpi=DPI)
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.25, 1.0], wspace=0.2)
    ax1, ax2 = plt.subplot(gs[0]), plt.subplot(gs[1])

    for row, interval in enumerate(REROUTE_INTERVALS):
        colour, marker = REROUTE_STYLES[interval]
        passes = np.asarray(records[interval]["passes"])
        evals = np.asarray(records[interval]["evaluations"])
        ax1.scatter(passes, np.full(passes.size, row), s=150, marker="|", color=colour,
                    linewidths=1.8, zorder=3)  # fmt: skip
        ax1.scatter(evals, np.full(evals.size, row + 0.28), s=60, marker=marker,
                    color=colour, edgecolors="white", linewidths=0.6, zorder=4)  # fmt: skip
    ax1.set_yticks(range(len(REROUTE_INTERVALS)))
    ax1.set_yticklabels(
        [
            f"interval {i:g} s\n{len(records[i]['passes'])} passes"
            for i in REROUTE_INTERVALS
        ],
        fontsize=10,
    )
    ax1.set_xlim(-0.2, 12.2)
    ax1.set_ylim(-0.6, len(REROUTE_INTERVALS) + 0.4)
    ax1.set_xlabel("Simulated time [s]", fontsize=12, labelpad=8, color=GREY)
    ax1.set_title(
        r"$\bf{(a)}$" + "  When the reroute pass runs", loc="left", fontsize=12, pad=7,
        color=GREY,
    )  # fmt: skip
    ax1.legend(
        handles=[
            Line2D([0], [0], marker="|", color=GREY, linestyle="none", markersize=9,
                   label="pass (all agents checked)"),
            Line2D([0], [0], marker="o", color=GREY, linestyle="none", markersize=6,
                   label="an agent is due and re-evaluates"),
        ],
        loc="upper right", fontsize=8.5, **LEGEND,
    )  # fmt: skip
    gaps = {
        i: float(np.median(np.diff(records[i]["passes"]))) for i in REROUTE_INTERVALS
    }
    _note(
        ax1, 0.02, 0.97,
        "Pass every min(1 s, interval):\n"
        + ", ".join(f"{gaps[i]:g} s at {i:g} s" for i in REROUTE_INTERVALS)
        + ".\nAn agent is due once per interval.",
        style="italic",
    )  # fmt: skip

    for interval in REROUTE_INTERVALS:
        colour, marker = REROUTE_STYLES[interval]
        shift = (list(REROUTE_INTERVALS).index(interval) - 1) * 0.07
        ax2.scatter(
            np.asarray(CLOSE_TIMES_S) + shift, latency[interval], color=colour,
            marker=marker, s=70, edgecolors="white", linewidths=0.7, zorder=3,
            label=f"interval {interval:g} s",
        )  # fmt: skip
    ax2.axhline(1.0, color="lightgrey", linewidth=0.9, linestyle="--", zorder=1)
    ax2.axhline(0.5, color="lightgrey", linewidth=0.9, linestyle=":", zorder=1)
    ax2.set_ylim(0, 1.15)
    ax2.set_xlabel(
        "Closure time of the west exit [s]", fontsize=12, labelpad=8, color=GREY
    )
    ax2.set_ylabel("Delay until the first agent reroutes [s]", fontsize=11,
                   labelpad=8, color=GREY)  # fmt: skip
    ax2.text(
        6.45, 1.0, "pass every 1 s", fontsize=8, color=GREY, ha="right", va="bottom"
    )
    ax2.text(
        6.45, 0.5, "pass every 0.5 s", fontsize=8, color=GREY, ha="right", va="bottom"
    )
    ax2.set_title(
        r"$\bf{(b)}$" + "  Reaction to a closed exit", loc="left", fontsize=12, pad=7,
        color=GREY,
    )  # fmt: skip
    ax2.legend(loc="lower right", fontsize=9, **LEGEND)
    short = [v for v in latency[0.5] if np.isfinite(v)]
    long_ = [v for v in latency[1.0] if np.isfinite(v)]
    _note(
        ax2, 0.03, 0.97,
        f"Mean delay: {np.mean(short):.2f} s at 0.5 s, {np.mean(long_):.2f} s at 1 s.\n"
        "A closure waits for the next pass, so 10 s equals 1 s.",
        style="italic",
    )  # fmt: skip
    _tidy(ax1, ax2)
    _caption(
        fig,
        "Both panels: 30 x 10 m room of tests/test_scheduled_exits.py, 40 agents; (a) "
        "no closure, (b) the west door closes at the time shown, off the 1 s grid.\n"
        "Before PR 973 the pass ran at most once per second, so 0.5 s behaved as 1 s; "
        "that is not rerun here.",
    )
    return _save(fig, out, "05_subsecond_reroute.png")


# --- 6. fdsvismap thin wall (known limitation, fdsvismap#96) -----------------

THINWALL_SIGNS = {"thin": (2.5, 1.0), "thick": (7.75, 1.0)}
THINWALL_OBST = {  # &OBST XB of the deck: x0, x1, y0, y1
    "divider": (5.0, 5.5, 0.0, 10.0),
    "0.25 m wall": (0.0, 5.0, 5.0, 5.25),
    "0.50 m wall": (5.5, 10.0, 5.0, 5.5),
}


def _thinwall_data(sim_dir: Path) -> dict:
    from fdsvismap import VisMap

    vis = VisMap()
    vis.read_fds_data(str(sim_dir), fds_slc_height=1.75)
    vis.set_time_points([0.0])
    for sign_id, (x, y) in THINWALL_SIGNS.items():
        vis.add_sign(sign_id, x, y, 3, "omni")
    vis.compute_all()
    xs, ys = np.asarray(vis.all_x_coords), np.asarray(vis.all_y_coords)
    visible = {
        sign_id: np.array(
            [
                [bool(vis.get_visibility_to_sign(0.0, x, y, sign_id)) for x in xs]
                for y in ys
            ]
        )
        for sign_id in THINWALL_SIGNS
    }
    return {"xs": xs, "ys": ys, "obstructions": np.asarray(vis.obstructions_array),
            "visible": visible}  # fmt: skip


def _draw_obst(ax) -> None:
    for x0, x1, y0, y1 in THINWALL_OBST.values():
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="none",
                               edgecolor=RED, linewidth=1.6, linestyle="--", zorder=5))  # fmt: skip


def panel_thinwall(out: Path, thinwall_dir: Path | None) -> Path | None:
    if thinwall_dir is None:
        print("  skipped: pass --thinwall-dir with the thinwall FDS output")
        return None
    data = _thinwall_data(thinwall_dir)
    step = float(np.median(np.diff(data["xs"])))
    extent = (data["xs"][0] - step / 2, data["xs"][-1] + step / 2,
              data["ys"][0] - step / 2, data["ys"][-1] + step / 2)  # fmt: skip
    titles = (
        r"$\bf{(a)}$" + "  obstructions_array",
        r"$\bf{(b)}$" + "  NOT visible from sign 'thin'",
        r"$\bf{(c)}$" + "  NOT visible from sign 'thick'",
    )
    grids = (data["obstructions"], ~data["visible"]["thin"], ~data["visible"]["thick"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.6), dpi=DPI, sharey=True)
    for ax, title, grid in zip(axes, titles, grids):
        ax.imshow(grid.astype(float), origin="lower", extent=extent, cmap="Greys",
                  vmin=0, vmax=1.6, interpolation="nearest", zorder=1)  # fmt: skip
        _draw_obst(ax)
        ax.set_title(title, loc="left", fontsize=12, pad=7, color=GREY)
        ax.set_xlabel("x [m]", fontsize=11, labelpad=6, color=GREY)
        ax.set_aspect("equal")
    for ax in axes[1:]:
        for sign_id, (x, y) in THINWALL_SIGNS.items():
            ax.scatter(x, y, marker="*", s=170, color=ORANGE if sign_id == "thin" else BLUE,
                       edgecolors="black", linewidths=0.7, zorder=6)  # fmt: skip
    axes[0].set_ylabel("y [m]", fontsize=11, labelpad=6, color=GREY)
    axes[1].text(2.5, 7.2, "visible through\nthe 0.25 m wall", ha="center", fontsize=9,
                 color=GREY, weight="semibold")  # fmt: skip
    axes[2].text(7.75, 7.2, "hidden behind\nthe 0.50 m wall", ha="center", fontsize=9,
                 color=GREY, weight="semibold")  # fmt: skip
    handles = [
        Patch(facecolor="black", alpha=0.6, label="dark: blocked / not visible"),
        Line2D([0], [0], color=RED, linestyle="--", linewidth=1.6, label="&OBST in the deck"),
        Line2D([0], [0], marker="*", color="none", markerfacecolor=ORANGE,
               markeredgecolor="black", markersize=12, label="sign 'thin'"),
        Line2D([0], [0], marker="*", color="none", markerfacecolor=BLUE,
               markeredgecolor="black", markersize=12, label="sign 'thick'"),
    ]  # fmt: skip
    axes[0].legend(handles=handles, loc="upper left", fontsize=8, **LEGEND)
    fig.suptitle(
        "Known limitation (fdsvismap#96): an OBST thinner than one grid cell is not an obstruction",
        x=0.01, ha="left", fontsize=14, color=GREY, y=0.93,
    )  # fmt: skip
    _tidy(*axes)
    _caption(
        fig,
        "FDS deck thinwall.fds, 0.5 m cells, no fire. FDS keeps the 0.25 m wall one cell "
        "thick; fdsvismap shrinks the &OBST as written by half a cell per side,\n"
        "leaving no cell, so signs show through it (fdsvismap#96, not fixed). "
        "Panels (b) and (c) are get_visibility_to_sign at t = 0 for every cell centre; "
        "dark = sign not visible.",
    )
    return _save(fig, out, "06_thinwall_known_limitation.png")


# --- command line ------------------------------------------------------------

PANELS = {
    "fed": panel_fed,
    "familiarity": panel_familiarity,
    "queue": panel_queue,
    "avm": panel_avm,
    "reroute": panel_reroute,
}


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("artifacts/demo_0.9"),
                        help="output directory")  # fmt: skip
    parser.add_argument("--seeds", type=int, default=10,
                        help="seeds for the familiarity panel")  # fmt: skip
    parser.add_argument("--thinwall-dir", type=Path, default=None,
                        help="FDS output of the thin-wall deck (panel 6)")  # fmt: skip
    parser.add_argument("--only", nargs="+", choices=[*PANELS, "thinwall"],
                        help="panels to draw (default: all)")  # fmt: skip
    return parser.parse_args(argv)


def _timed(name: str, call: Callable[[], Path | None]) -> None:
    start = time.perf_counter()
    path = call()
    print(f"[{name}] {time.perf_counter() - start:5.1f} s  {path or '-'}")


def main(argv: list[str] | None = None) -> None:
    args = _parse(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    _use_worktree_code()
    _setup_style()
    wanted = args.only or [*PANELS, "thinwall"]
    for name in wanted:
        if name == "thinwall":
            _timed(name, lambda: panel_thinwall(args.out, args.thinwall_dir))
            continue
        _timed(name, lambda panel=PANELS[name]: panel(args.out, args.seeds))


if __name__ == "__main__":
    main()
