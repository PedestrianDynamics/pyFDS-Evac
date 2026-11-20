#!/usr/bin/env python3
"""Scorers for the Station study's owed pre-registration items (#950).

The frozen scorer ``validate.py`` produces V1 to V3m. This module adds the
items the pre-registration (tag ``station-prereg-v1``, sections 2 and 3)
requires and the frozen tree has no scorer for. It reuses the frozen
functions (door attribution, censoring, W, T1) and changes none of them.

Every definition below is the registered one; a reading the registration
leaves open is named in the docstring of the function that makes it and is
reported with the result. Nothing is tuned to Fahy, NCSTAR or Galea.

Subcommands, each printing Markdown to stdout (paths are arguments):

* ``tabulate SCORES_DIR``: censored shares and t_jam splits from the
  ``validate.py`` score files.
* ``trajectory``: vestibule count at t_jam, V5 and the V4 NIST construct.
* ``scalars``: heat-FED availability and FED of agents on raised floors.
* ``resample``: the survival of W differences under resampling of Fahy.
* ``fire``: V6, the realised HRR, T5 and T6 (needs the FDS slices).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import fahy_table2 as F
import validate as V

# --- registered geometry (fire_inputs.md section 4, assumption A4) ----------
# Boxes read from the deck plan and NCSTAR Fig. 1-5: (x0, x1, y0, y1) in the
# FDS frame that the run trajectories share. The "approximately" entries are
# the ones the source marks with a tilde.
DANCE_FLOOR_BOX = (10.45, 14.45, -11.31, -4.66)
ZONE_BOXES = {
    "dance_floor": DANCE_FLOOR_BOX,
    "sunroom": (4.4, 15.45, -17.92, -12.51),
    "foyer": (2.44, 4.34, -17.31, -12.5),
    "main_bar": (-6.1, 2.4, -17.3, -9.4),
    "dart_room": (-6.1, 6.6, -9.4, -2.6),
}
# NIST's construct counts people stopped "in the entry and sunroom" (plan, V4).
ENTRY_AND_SUNROOM = (ZONE_BOXES["foyer"], ZONE_BOXES["sunroom"])
# Raised floors (A4 table): platform 0.574 m, alcove 0.87-1.06 m, rear strip 0.184 m.
RAISED_FLOORS = {
    "platform": (14.35, 17.76, -10.11, -4.66),
    "alcove": (17.76, 20.36, -9.41, -5.89),
    "rear_strip": (6.65, 17.76, -4.81, -2.68),
}
# Vestibule, station_nist (b11 contract, line definitions): from the
# interior-door line y = -14.36 to the exterior strip at y = -17.11, across
# the front-door width x 2.44 to 4.34.
VESTIBULE_BOX = (2.44, 4.34, -17.11, -14.36)
INTERIOR_DOOR_Y = -14.36
INTERIOR_DOOR_X = (2.44, 4.34)

V5_WINDOW_S = 60.0
V5_BAND = (0.9, 1.5)
T5_C, T5_FRACTIONS = 120.0, (0.5, 0.1, 0.9)
T6_O2, T6_FRACTION = 0.12, 0.95
T5_BAND, T6_BAND = (65.0, 100.0), (65.0, 115.0)
V3_MIN_SEEDS, V3_MIN_DIFFERENCE = 15, 0.03


def _in_box(x, y, box) -> bool:
    x0, x1, y0, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


# --- tabulation of validate.py score files -----------------------------------

_NUM = r"([0-9.]+|n/a)"
_PATTERNS = {
    "t1": re.compile(r"^T1\s+front share of door users, placed rows:\s+" + _NUM + "%?"),
    "w": re.compile(r"^W\s+door-user-weighted TVD over \d+ rows:\s+" + _NUM),
    "censored": re.compile(r"^censored: (\d+) of (\d+) placed agents"),
    "before": re.compile(
        r"^exit before t_jam = (\S+) s\s+T1\s+" + _NUM + r"%?\s+W " + _NUM
    ),
    "after": re.compile(r"^exit at or after t_jam\s+T1\s+" + _NUM + r"%?\s+W " + _NUM),
}


def _num(text: str) -> float | None:
    return None if text == "n/a" else float(text)


def parse_score_text(text: str) -> dict:
    """The censored count and the t_jam split of one ``validate.py`` output.

    Keys: ``censored`` and ``placed`` (agents, summed over the runs of the
    file), ``t_jam``, ``before`` and ``after`` as ``(T1 %, W)``. A key is
    absent when the output has no such line, as for a run without --t-jam.
    """
    out: dict = {}
    for line in text.splitlines():
        for key, pattern in _PATTERNS.items():
            match = pattern.match(line)
            if match is None:
                continue
            if key == "censored":
                out["censored"], out["placed"] = map(int, match.groups())
            elif key == "before":
                out["t_jam"] = float(match.group(1))
                out["before"] = (_num(match.group(2)), _num(match.group(3)))
            elif key == "after":
                out["after"] = (_num(match.group(1)), _num(match.group(2)))
            elif key in ("t1", "w"):
                out[key] = _num(match.group(1))
    return out


def _fmt_split(split) -> str:
    if split is None:
        return "not split"
    t1, w = split
    return f"T1 {'n/a' if t1 is None else f'{t1:.1f} %'}, W {'n/a' if w is None else f'{w:.3f}'}"


def tabulate_scores(scores_dir: Path) -> str:
    """Markdown table: censored share and t_jam split of every score file."""
    lines = [
        "| Score file | Censored | Before t_jam | At or after t_jam |",
        "|---|---|---|---|",
    ]
    for path in sorted(scores_dir.glob("[0-9][0-9]_*.txt")):
        s = parse_score_text(path.read_text())
        if "censored" not in s:
            raise ValueError(f"{path}: no 'censored:' line; not a validate.py output")
        share = s["censored"] / s["placed"] if s["placed"] else float("nan")
        t_jam = f" (t_jam {s['t_jam']:g} s)" if "t_jam" in s else ""
        lines.append(
            f"| {path.stem} | {s['censored']} of {s['placed']} ({share:.1%}) | "
            f"{_fmt_split(s.get('before'))}{t_jam} | {_fmt_split(s.get('after'))} |"
        )
    return "\n".join(lines)


# --- trajectories ------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    """The trajectories of one run: ``tracks[id]`` is a (n, 3) frame, x, y array."""

    fps: float
    tracks: Mapping[int, np.ndarray]
    last_frame: int
    remaining: int | None

    def agents_at(self, t_s: float) -> list[int]:
        """Ids with a row at the recorded frame nearest *t_s*."""
        frames = np.unique(np.concatenate([tr[:, 0] for tr in self.tracks.values()]))
        target = frames[np.argmin(np.abs(frames - t_s * self.fps))]
        return [i for i, tr in self.tracks.items() if (tr[:, 0] == target).any()]

    def position_at(self, agent: int, frame: float) -> tuple[float, float]:
        tr = self.tracks[agent]
        row = tr[np.argmin(np.abs(tr[:, 0] - frame))]
        return float(row[1]), float(row[2])


def load_run(sqlite_path: Path) -> Run:
    """Read a run's trajectories and, if a manifest sits beside it, the agents left."""
    con = sqlite3.connect(sqlite_path)
    try:
        fps = V._fps(con)
        rows = np.array(
            con.execute(
                "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY id, frame"
            ).fetchall(),
            dtype=float,
        )
    finally:
        con.close()
    if rows.size == 0:
        raise ValueError(f"{sqlite_path}: no trajectory rows")
    ids = rows[:, 0].astype(int)
    cuts = np.flatnonzero(np.diff(ids)) + 1
    tracks = {int(chunk[0, 0]): chunk[:, 1:] for chunk in np.split(rows, cuts, axis=0)}
    manifest = sqlite_path.with_name(
        sqlite_path.name.replace(".sqlite", ".manifest.json")
    )
    remaining = None
    if manifest.exists():
        outcome = json.loads(manifest.read_text()).get("outcome", {})
        remaining = outcome.get("agents_remaining")
    return Run(fps, tracks, int(rows[:, 1].max()), remaining)


def vestibule_count(run: Run, t_s: float, box=VESTIBULE_BOX) -> int:
    """Agents inside *box* at the recorded frame nearest *t_s*."""
    return sum(1 for a in run.agents_at(t_s) if _in_box(*_last_xy(run, a, t_s), box))


def _last_xy(run: Run, agent: int, t_s: float) -> tuple[float, float]:
    return run.position_at(agent, t_s * run.fps)


def outbound_crossing_times(
    run: Run, line_y: float = INTERIOR_DOOR_Y, x_range=INTERIOR_DOOR_X
) -> list[float]:
    """Time [s] of each agent's first crossing of ``y = line_y`` toward smaller y.

    A crossing is a step from ``y >= line_y`` to ``y < line_y`` with the
    crossing point inside *x_range*; its time is interpolated linearly. Each
    agent counts once, at its first outbound crossing.
    """
    times = []
    for tr in run.tracks.values():
        t = _first_crossing(tr, line_y, x_range, run.fps)
        if t is not None:
            times.append(t)
    return sorted(times)


def _first_crossing(tr: np.ndarray, line_y: float, x_range, fps: float):
    y = tr[:, 2]
    for i in np.flatnonzero((y[:-1] >= line_y) & (y[1:] < line_y)):
        frac = (y[i] - line_y) / (y[i] - y[i + 1])
        x = tr[i, 1] + frac * (tr[i + 1, 1] - tr[i, 1])
        if x_range[0] <= x <= x_range[1]:
            return float((tr[i, 0] + frac * (tr[i + 1, 0] - tr[i, 0])) / fps)
    return None


def v5_max_moving_mean(
    crossings: Sequence[float],
    t_jam: float,
    window_s: float = V5_WINDOW_S,
    step_s: float = 0.1,
) -> dict:
    """Highest *window_s* moving mean of the crossing rate, first arrival to t_jam.

    Registered: "highest 60 s moving mean through the 914 mm door, from the
    first arrival to t_jam". The first arrival is the first crossing. Every
    window lies inside [first arrival, t_jam]; if no window of that length
    fits the result is ``None`` (undefined), not a shortened window. Returns
    the first arrival, the span available, the crossings up to t_jam and the
    maximum mean rate [person/s]. ``rate_window_to_t_jam`` is a second
    reading, not the registered one: windows may start before the first
    arrival (the flow there is zero), so the last 60 s before t_jam hold
    every crossing and the rate is at least their count over 60 s.
    """
    inside = [t for t in crossings if t < t_jam]
    if not inside:
        return {
            "first": None,
            "span": None,
            "count": 0,
            "rate": None,
            "rate_window_to_t_jam": None,
        }
    first = min(inside)
    span = t_jam - first
    out = {"first": first, "span": span, "count": len(inside), "rate": None}
    out["rate_window_to_t_jam"] = _best_window(inside, 0.0, t_jam, window_s, step_s)
    if span < window_s:
        return out
    out["rate"] = _best_window(inside, first, t_jam, window_s, step_s)
    return out


def _best_window(times, start: float, end: float, window_s: float, step_s: float):
    """Highest mean rate of a window that starts at or after *start* and ends
    at or before *end*; None if no window of *window_s* fits."""
    if end - start < window_s:
        return None
    arr = np.asarray(times)
    starts = np.arange(start, end - window_s + 1e-9, step_s)
    counts = [(arr[(arr >= s) & (arr < s + window_s)]).size for s in starts]
    return max(counts) / window_s


def stopped_ids(run: Run) -> set[int]:
    """Agents still on the grid when the run ended.

    Only a run that ended with agents inside (manifest ``agents_remaining``
    above zero) has any; a run without a manifest is refused; they are the agents present at its last frame. The
    count must equal the manifest's, else the run is refused.
    """
    if run.remaining is None:
        raise ValueError("no manifest beside the run: the agents left are unknown")
    if run.remaining == 0:
        return set()
    present = {a for a, tr in run.tracks.items() if tr[-1, 0] == run.last_frame}
    if len(present) != run.remaining:
        raise ValueError(
            f"{len(present)} agents present at the last frame, the manifest "
            f"says {run.remaining} remained"
        )
    return present


def nist_construct(agents: Sequence[V.AgentExit], run: Run) -> dict:
    """V4, NIST's construct, beside the first-target share.

    Registered (plan line 138): (agents who exited by the front + agents
    stopped in the entry and sunroom) / (door users + stopped agents). All
    agents count, whatever their population. "Stopped" are the agents left
    on the grid at the end; "exited" are the others, so an agent stopped by
    the front door is not an exit by it. "Door user" is an agent that is not
    stopped and finished within the scorer's reach of a door. The entry and
    sunroom are the A4 boxes; the sunroom and foyer coordinates are
    approximate in their source.
    """
    stopped = stopped_ids(run)
    exited = [a for a in agents if a.agent_id not in stopped]
    users = [a for a in exited if a.door is not None]
    front = sum(1 for a in users if a.door == "front")
    in_entry = sum(
        1
        for a in stopped
        if any(
            _in_box(*run.position_at(a, run.last_frame), b) for b in ENTRY_AND_SUNROOM
        )
    )
    denominator = len(users) + len(stopped)
    return {
        "front_exits": front,
        "door_users": len(users),
        "stopped": len(stopped),
        "stopped_in_entry_sunroom": in_entry,
        "construct": (front + in_entry) / denominator if denominator else None,
        "agents": len(agents),
    }


def first_target_front_share(first_target: Mapping[int, str]) -> float:
    """V4: share of all agents whose first target is the front door.

    *first_target* maps agent id to the exit its initial route chose. The
    frozen runs did not record it (``output_route_history`` unset), so the
    study cannot call this; the function is here for a run that does.
    """
    if not first_target:
        raise ValueError("first_target is empty")
    return sum(1 for e in first_target.values() if e == "front") / len(first_target)


# --- agent_scalars ----------------------------------------------------------


def heat_fed_recorded(sqlite_path: Path) -> int:
    """Rows of ``agent_scalars`` with a heat FED; 0 if the run did not record it."""
    con = sqlite3.connect(sqlite_path)
    try:
        if not V._has_table(con, "agent_scalars"):
            return 0
        (n,) = con.execute(
            "SELECT COUNT(*) FROM agent_scalars WHERE heat_fed IS NOT NULL"
        ).fetchone()
    finally:
        con.close()
    return int(n)


def heat_incapacitated(sqlite_path: Path) -> tuple[int, float | None]:
    """Agents whose recorded heat FED reached 1, and the largest heat FED seen.

    The pre-registration reports heat-incapacitated agents separately: heat
    never reaches route choice. The runs score no heat incapacitation
    (``enable_heat_incapacitation`` is off), so this counts the dose that a
    recorded ``heat_fed`` column reached, not agents that stopped. The
    largest value is None when no row has a heat FED.
    """
    con = sqlite3.connect(sqlite_path)
    try:
        if not V._has_table(con, "agent_scalars"):
            return 0, None
        peak = con.execute("SELECT MAX(heat_fed) FROM agent_scalars").fetchone()[0]
        (n,) = con.execute(
            "SELECT COUNT(DISTINCT id) FROM agent_scalars WHERE heat_fed >= ?",
            (V.FED_INCAPACITATED,),
        ).fetchone()
    finally:
        con.close()
    return int(n), peak


def raised_floor_fed(agents: Sequence[V.AgentExit]) -> dict[str, dict[str, int | None]]:
    """FED >= 1 of placed survivors that start on a raised floor.

    Registered (plan line 311): "FED and K for agents on raised floors";
    which agents are on a raised floor is not defined. This reads it as the
    start position inside a raised-floor box. Groups: each box, all of them
    ("any"), and the placed survivors elsewhere ("elsewhere"). K is not
    recorded in a run's sqlite, so only FED is scored. ``incapacitated`` is
    None for a run without FED.
    """
    groups: dict[str, list[V.AgentExit]] = {name: [] for name in RAISED_FLOORS}
    groups["any"], groups["elsewhere"] = [], []
    for a in (a for a in agents if a.placed and a.origin):
        names = [n for n, box in RAISED_FLOORS.items() if _in_box(*a.start, box)]
        for n in names:
            groups[n].append(a)
        groups["any" if names else "elsewhere"].append(a)
    out: dict[str, dict[str, int | None]] = {}
    for name, members in groups.items():
        recorded = all(a.incapacitated is not None for a in members)
        out[name] = {
            "agents": len(members),
            "incapacitated": sum(bool(a.incapacitated) for a in members)
            if recorded
            else None,
        }
    return out


# --- survival of W differences under resampling of Fahy ---------------------


def _target_layout(targets):
    groups = V.pooling(targets)
    pooled = {g: c for g, c in V.pool(targets, groups).items() if sum(c.values())}
    vectors = {
        g: np.array([c.get(d, 0) for d in F.DOORS], float) for g, c in pooled.items()
    }
    return groups, vectors


def w_draws(matrix, targets, draws: int, rng) -> np.ndarray:
    """W of *matrix* against *draws* multinomial resamples of *targets*.

    One resample of Fahy's table per draw, one multinomial per scored row
    (pooled small rows as one), as in ``validate.noise_floor``. Returns one
    W per draw. With a draw equal to the table it is ``validate.w_statistic``.
    """
    groups, vectors = _target_layout(targets)
    model = V.pool(matrix, groups)
    resampled = {
        g: rng.multinomial(int(v.sum()), v / v.sum(), size=draws).astype(float)
        for g, v in vectors.items()
    }
    return _w_against(model, vectors, resampled)


def _w_against(model, vectors, resampled) -> np.ndarray:
    total = sum(v.sum() for v in vectors.values())
    w = 0.0
    for g, v in vectors.items():
        m = np.array([model.get(g, {}).get(d, 0) for d in F.DOORS], float)
        n = v.sum()
        if m.sum() == 0:
            w = w + n * 1.0
            continue
        t = resampled[g] / n
        w = w + n * 0.5 * np.abs(m / m.sum() - t).sum(axis=1)
    return np.asarray(w) / total


def paired_draws(runs, others, targets, draws: int, seed: int = 0) -> dict:
    """W(run) - W(other) per seed and draw, on the same-agent set of each pair.

    The same resample of Fahy's table is used for every seed and both arms
    of a draw. Returns ``observed`` (per seed, against the table itself) and
    ``resampled`` (seeds x draws).
    """
    rng = np.random.default_rng(seed)
    groups, vectors = _target_layout(targets)
    table = {g: v[None, :] for g, v in vectors.items()}
    resampled = {
        g: rng.multinomial(int(v.sum()), v / v.sum(), size=draws).astype(float)
        for g, v in vectors.items()
    }
    observed, delta = [], []
    for a, b in zip(runs, others, strict=True):
        ids = V.same_agents(a, b)
        ma = V.pool(V.door_matrix(a, ids), groups)
        mb = V.pool(V.door_matrix(b, ids), groups)
        observed.append(
            float(_w_against(ma, vectors, table)[0] - _w_against(mb, vectors, table)[0])
        )
        delta.append(
            _w_against(ma, vectors, resampled) - _w_against(mb, vectors, resampled)
        )
    return {"observed": np.array(observed), "resampled": np.vstack(delta)}


def survival(paired: dict, threshold: float = V3_MIN_DIFFERENCE) -> dict:
    """How often the registered W differences survive resampling of Fahy.

    Plan line 146: "a difference of 0.03 in W survives resampling of Fahy's
    table in more than 99 % of draws" (spread uniformly over rows). Two
    readings of "survives" are reported:

    * ``sign``: the difference keeps its observed sign (the reading under
      which the plan's 99 % holds; see the test on a uniform shift);
    * ``size``: it keeps its sign and a size of at least *threshold* (the
      first reading, kept so both are on record).

    Each is given per seed (min, median, max over seeds) and for the mean
    over seeds. ``v3_holds`` is the share of draws in which V3 as registered
    holds (the run lower in at least 15 of 20 seeds and a mean difference of
    at least 0.03 lower). These are rates for a difference in W; they say
    nothing about occupants. Whether the plan's rates are the referee's three
    synthetic cases or rates on observed differences is not stated.
    """
    obs, res = paired["observed"], paired["resampled"]
    sign = np.where(obs >= 0, 1.0, -1.0)[:, None]
    signed = res * sign
    mean_obs = obs.mean()
    mean_res = res.mean(axis=0) * (1.0 if mean_obs >= 0 else -1.0)
    lower = (res < 0).sum(axis=0)
    needed = min(V3_MIN_SEEDS, len(obs))
    v3 = ((lower >= needed) & (res.mean(axis=0) <= -threshold)).mean()

    def spread(per_seed):
        return (
            float(per_seed.min()),
            float(np.median(per_seed)),
            float(per_seed.max()),
        )

    return {
        "mean_difference": float(mean_obs),
        "sign_per_seed": spread((signed > 0).mean(axis=1)),
        "sign_mean": float((mean_res > 0).mean()),
        "size_per_seed": spread((signed >= threshold).mean(axis=1)),
        "size_mean": float((mean_res >= threshold).mean()),
        "v3_holds": float(v3),
        "draws": res.shape[1],
    }


# --- V6: realised HRR, T5, T6 -----------------------------------------------


def read_fds_hrr(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Time [s] and HRR [kW] of an FDS ``<CHID>_hrr.csv`` (units row, names row)."""
    with open(path) as handle:
        handle.readline()
        names = [n.strip() for n in handle.readline().split(",")]
    if "Time" not in names or "HRR" not in names:
        raise ValueError(f"{path}: no 'Time' and 'HRR' columns in {names}")
    data = np.loadtxt(path, delimiter=",", skiprows=2)
    return data[:, names.index("Time")], data[:, names.index("HRR")]


def read_prescribed_hrr(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Time [s] and HRR [kW] of the digitised Fig. 5-42 (``#`` comments, header)."""
    lines = [ln for ln in Path(path).read_text().splitlines() if not ln.startswith("#")]
    data = np.array(
        [[float(v) for v in ln.split(",")] for ln in lines[1:] if ln.strip()]
    )
    return data[:, 0], data[:, 1]


def hrr_report(real, prescribed) -> dict:
    """Realised against prescribed HRR over the prescribed range; reported, no band.

    The ratio of the time integrals (kJ, trapezoid on the prescribed
    vertices' range, the realised curve interpolated), the peaks with their
    times, and the ratio at each prescribed vertex.
    """
    tr, qr = real
    tp, qp = prescribed
    grid = np.linspace(tp[0], tp[-1], 2000)
    pres = np.interp(grid, tp, qp)
    got = np.interp(grid, tr, qr)
    return {
        "energy_ratio": float(np.trapezoid(got, grid) / np.trapezoid(pres, grid)),
        "peak_prescribed": (float(qp.max()), float(tp[np.argmax(qp)])),
        "peak_realised": (float(got.max()), float(grid[np.argmax(got)])),
        "ratio_at_vertices": [
            (float(t), float(np.interp(t, tr, qr) / q)) for t, q in zip(tp, qp) if q > 0
        ],
    }


def first_time_at_or_above(times, fraction, level: float) -> float | None:
    """First time at which *fraction* is at least *level*; None if it never is."""
    for t, f in zip(times, fraction):
        if f >= level:
            return float(t)
    return None


def interior_mask(free: np.ndarray, seed: np.ndarray) -> tuple[np.ndarray, bool]:
    """Gas cells connected to the *seed* cells through *free* cells (4-neighbours).

    Returns the connected mask and whether it touches the lattice edge,
    which would mean the closed building leaks to the domain boundary.
    """
    ny, nx = free.shape
    mask = np.zeros_like(free, dtype=bool)
    queue = deque(zip(*np.nonzero(seed & free)))
    for j, i in queue:
        mask[j, i] = True
    while queue:
        j, i = queue.popleft()
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nj, ni = j + dj, i + di
            if 0 <= nj < ny and 0 <= ni < nx and free[nj, ni] and not mask[nj, ni]:
                mask[nj, ni] = True
                queue.append((nj, ni))
    edge = mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any()
    return mask, bool(edge)


def box_cells(xc: np.ndarray, yc: np.ndarray, box) -> np.ndarray:
    """Boolean (ny, nx) mask of cells whose centre lies in *box*."""
    x0, x1, y0, y1 = box
    return ((yc >= y0) & (yc <= y1))[:, None] & ((xc >= x0) & (xc <= x1))[None, :]


def exceedance_fractions(frames, cells: np.ndarray, test) -> np.ndarray:
    """Fraction of *cells* for which ``test(value)`` holds, per frame.

    Raises ValueError if a selected cell has no value (NaN): the slice must
    cover every cell of the mask, not silently count it as not satisfying.
    """
    out = []
    for values in frames:
        selected = values[cells]
        if np.isnan(selected).any():
            raise ValueError("the slice has no value in some selected cells")
        out.append(float(test(selected).mean()))
    return np.array(out)


def read_fire_fields(fds_dir: Path, height_m: float = 1.5):
    """Open an FDS case and return what T5 and T6 need at *height_m*.

    Returns ``(times, temperature_frames, o2_frames, xc, yc, free, z)``: slice
    frame times, the (ny, nx) fields per frame at the grid nodes of the
    slice plane, the node coordinates, the gas-node mask of the initial
    (closed) state and the plane height. The slices are node slices, so the
    "cells" of the registration are the nodes of the plane. Uses the repo's
    fdsreader adapter and slice sampler.
    """
    from pyfds_evac.core.fds_sampling import (
        SliceGrid,
        _slice_z_mid,
        load_slice_sampler,
    )
    from pyfds_evac.core.fdsreader_adapter import open_fds_simulation

    sim = open_fds_simulation(str(fds_dir))
    samplers = {
        key: load_slice_sampler(
            str(fds_dir), quantity, simulation=sim, slice_height_m=height_m
        )
        for key, quantity in (
            ("temperature", "TEMPERATURE"),
            ("o2", "OXYGEN VOLUME FRACTION"),
        )
    }
    z = _slice_z_mid(samplers["temperature"]._slice)
    xc, yc, free = _node_lattice_and_free(sim, z)
    fields = {}
    times = None
    for key, sampler in samplers.items():
        grid = SliceGrid(sampler, xc, yc)
        n = len(sampler._slice.times)
        if times is not None and n != len(times):
            raise ValueError(f"{key}: {n} frames, expected {len(times)}")
        times = np.array([grid.frame_time_s(i) for i in range(n)])
        fields[key] = [grid.values(i) for i in range(n)]
    return times, fields["temperature"], fields["o2"], xc, yc, free, z


def _node_lattice_and_free(sim, z_m: float):
    """Global grid nodes of the plane ``z = z_m`` and the gas-node mask, initial state.

    fdsreader's node mask blocks the nodes inside an obstruction and on its
    faces, so a zero-thickness wall blocks the nodes along it. The cell mask
    does not see such a wall, so a flood fill over cells leaks through it.
    A node in several meshes is gas only if no mesh blocks it; a node in no
    mesh is not gas.
    """
    meshes = list(sim.meshes)
    xs = sorted({round(float(c), 6) for m in meshes for c in m.coordinates["x"]})
    ys = sorted({round(float(c), 6) for m in meshes for c in m.coordinates["y"]})
    xc, yc = np.array(xs), np.array(ys)
    free = np.ones((len(ys), len(xs)), dtype=bool)
    covered = np.zeros_like(free)
    for mesh in meshes:
        z = np.asarray(mesh.coordinates["z"], dtype=float)
        k = int(np.argmin(np.abs(z - z_m)))
        mask = mesh.get_obstruction_mask([0.0], cell_centered=False)[0][:, :, k]
        ix = np.searchsorted(xc, np.round(np.asarray(mesh.coordinates["x"], float), 6))
        iy = np.searchsorted(yc, np.round(np.asarray(mesh.coordinates["y"], float), 6))
        free[np.ix_(iy, ix)] &= mask.T
        covered[np.ix_(iy, ix)] = True
    return xc, yc, free & covered


def v6_times(times, temperature, o2, xc, yc, free) -> dict:
    """T5 and T6 and their per-zone times.

    T5 (A7): the first time at which at least 50 % of the dance-floor box's
    gas cells (the unblocked nodes of the slice plane) exceed 120 C; the 10 % and 90 % crossings are
    also given. T6: the first time at which at least 95 % of the masked gas
    cells have X_O2 < 0.12; the mask is the gas cells connected to the dance
    floor in the initial (closed) state, which excludes sealed rooms by
    connectivity and not by coordinates (none are registered). The
    fraction-below-12-% series (``o2_fraction``) is reported beside it.
    """
    dance = box_cells(xc, yc, DANCE_FLOOR_BOX) & free
    mask, leaks = interior_mask(free, dance)
    t5 = {
        f"{int(f * 100)}%": first_time_at_or_above(
            times, exceedance_fractions(temperature, dance, lambda v: v > T5_C), f
        )
        for f in T5_FRACTIONS
    }
    o2_below = lambda v: v < T6_O2  # noqa: E731
    t6 = first_time_at_or_above(
        times, exceedance_fractions(o2, mask, o2_below), T6_FRACTION
    )
    zones = {}
    for name, box in ZONE_BOXES.items():
        cells = box_cells(xc, yc, box) & mask
        if not cells.any():
            zones[name] = {"cells": 0}
            continue
        zones[name] = {
            "cells": int(cells.sum()),
            "t_120C_50%": first_time_at_or_above(
                times, exceedance_fractions(temperature, cells, lambda v: v > T5_C), 0.5
            ),
            "t_o2_95%": first_time_at_or_above(
                times, exceedance_fractions(o2, cells, o2_below), T6_FRACTION
            ),
        }
    return {
        "T5": t5,
        "T6": t6,
        "o2_fraction": [
            (float(t), float(f))
            for t, f in zip(times, exceedance_fractions(o2, mask, o2_below))
        ],
        "unreached": unreached_regions(o2[-1], mask, xc, yc)[:8],
        "mask_cells": int(mask.sum()),
        "gas_cells": int(free.sum()),
        "dance_cells": int(dance.sum()),
        "mask_touches_domain_edge": leaks,
        "zones": zones,
    }


def band_verdict(value: float | None, band, last_time: float | None = None) -> str:
    """pass / fail against a closed band.

    Without a value the verdict is 'undefined', except when *last_time*, the
    end of the data, is past the band: a crossing that has not happened by
    then lies outside the band, which is a fail.
    """
    if value is None:
        return "fail" if last_time is not None and last_time > band[1] else "undefined"
    return "pass" if band[0] <= value <= band[1] else "fail"


def unreached_regions(
    o2_last: np.ndarray, mask: np.ndarray, xc, yc, limit: float = T6_O2
) -> list[dict]:
    """Connected groups of masked nodes still at or above *limit* in the last frame.

    Each group: node count and bounding box (x0, x1, y0, y1). It shows what
    holds a mask back from T6; it is not a rule for leaving them out.
    """
    open_nodes = mask & (o2_last >= limit)
    seen = np.zeros_like(open_nodes)
    groups = []
    for j, i in zip(*np.nonzero(open_nodes)):
        if seen[j, i]:
            continue
        region, _ = interior_mask(open_nodes, _single(open_nodes, j, i))
        seen |= region
        jj, ii = np.nonzero(region)
        groups.append(
            {
                "nodes": int(region.sum()),
                "box": (
                    float(xc[ii.min()]),
                    float(xc[ii.max()]),
                    float(yc[jj.min()]),
                    float(yc[jj.max()]),
                ),
            }
        )
    return sorted(groups, key=lambda g: -g["nodes"])


def _single(like: np.ndarray, j: int, i: int) -> np.ndarray:
    out = np.zeros_like(like)
    out[j, i] = True
    return out


# --- command line -----------------------------------------------------------


def _load_agents(paths, config: Path, horizon):
    return [V.observed_agents(p, config, 2.0, horizon) for p in paths]


def _horizon(args):
    return args.horizon if args.horizon is not None else V.config_horizon(args.config)


def cmd_tabulate(args) -> None:
    print(tabulate_scores(args.scores))


def cmd_trajectory(args) -> None:
    horizon = _horizon(args)
    print(
        "| seed | vestibule at t_jam | first crossing [s] | span [s] | crossings | V5 rate | NIST construct | stopped |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for path in args.sqlite:
        run = load_run(path)
        agents = V.observed_agents(path, args.config, 2.0, horizon)
        v5 = v5_max_moving_mean(outbound_crossing_times(run), args.t_jam)
        nist = nist_construct(agents, run)
        first = "-" if v5["first"] is None else f"{v5['first']:.1f}"
        span = "-" if v5["span"] is None else f"{v5['span']:.1f}"
        rate = "undefined" if v5["rate"] is None else f"{v5['rate']:.3f}"
        relaxed = v5["rate_window_to_t_jam"]
        if relaxed is not None:
            rate += f" (window from {args.t_jam - V5_WINDOW_S:g} s: {relaxed:.3f})"
        construct = "n/a" if nist["construct"] is None else f"{nist['construct']:.3f}"
        print(
            f"| {path.stem} | {vestibule_count(run, args.t_jam)} | {first} | {span} | "
            f"{v5['count']} | {rate} | {construct} ({nist['front_exits']}+"
            f"{nist['stopped_in_entry_sunroom']})/({nist['door_users']}+{nist['stopped']}) "
            f"| {nist['stopped']} |"
        )


def cmd_scalars(args) -> None:
    horizon = _horizon(args)
    heat = sum(heat_fed_recorded(p) for p in args.sqlite)
    print(f"heat FED rows recorded over {len(args.sqlite)} runs: {heat}")
    reached = [heat_incapacitated(p) for p in args.sqlite]
    peaks = [pk for _, pk in reached if pk is not None]
    print(
        f"agents with heat FED >= 1: {sum(n for n, _ in reached)}; "
        f"largest heat FED: {max(peaks) if peaks else 'n/a'}"
    )
    total: Counter = Counter()
    n_total: Counter = Counter()
    for path in args.sqlite:
        for name, g in raised_floor_fed(
            V.observed_agents(path, args.config, 2.0, horizon)
        ).items():
            n_total[name] += g["agents"]
            total[name] += g["incapacitated"] or 0
    for name in n_total:
        print(f"{name}: {n_total[name]} agents, FED >= 1 {total[name]}")


def cmd_resample(args) -> None:
    horizon = _horizon(args)
    runs = _load_agents(args.sqlite, args.config, horizon)
    others = _load_agents(args.against, args.config, horizon)
    paired = paired_draws(runs, others, V.fahy_targets(), args.draws, args.seed)
    print(json.dumps(survival(paired), indent=2))


def cmd_fire(args) -> None:
    real = read_fds_hrr(args.hrr)
    prescribed = read_prescribed_hrr(args.prescribed)
    print(json.dumps(hrr_report(real, prescribed), indent=2))
    times, temperature, o2, xc, yc, free, z_mid = read_fire_fields(args.fds_dir)
    result = v6_times(times, temperature, o2, xc, yc, free)
    result["slice_height_m"] = z_mid
    result["T5_verdict"] = band_verdict(result["T5"]["50%"], T5_BAND, float(times[-1]))
    result["T6_verdict"] = band_verdict(result["T6"], T6_BAND, float(times[-1]))
    print(json.dumps(result, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    def runs_parser(name, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("sqlite", type=Path, nargs="+")
        p.add_argument("--config", type=Path, required=True)
        p.add_argument("--horizon", type=float, default=None)
        return p

    sub.add_parser("tabulate").add_argument("scores", type=Path)
    t = runs_parser("trajectory", "vestibule count, V5, V4 NIST construct")
    t.add_argument("--t-jam", type=float, default=86.0)
    runs_parser("scalars", "heat FED availability, raised-floor FED")
    r = runs_parser("resample", "survival of W differences under Fahy resampling")
    r.add_argument("--against", type=Path, nargs="+", required=True)
    r.add_argument("--draws", type=int, default=2000)
    r.add_argument("--seed", type=int, default=0)
    f = sub.add_parser("fire", help="V6")
    f.add_argument("fds_dir", type=Path)
    f.add_argument("--hrr", type=Path, required=True)
    f.add_argument("--prescribed", type=Path, required=True)
    args = ap.parse_args()
    {
        "tabulate": cmd_tabulate,
        "trajectory": cmd_trajectory,
        "scalars": cmd_scalars,
        "resample": cmd_resample,
        "fire": cmd_fire,
    }[args.command](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
