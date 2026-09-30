#!/usr/bin/env python3
"""Compare a run against Fahy Table 2, row by row.

Usage:
    .venv/bin/python assets/station_fahy/validate.py RUN.sqlite [RUN.sqlite ...] \\
        --config assets/station_fahy/config.json [--t-jam 86] \\
        [--against OTHER.sqlite ...] [--noise-draws 20000] [--noise-seed 0]

Each agent is attributed to the spawn area whose polygon contains its **first**
recorded position, and to the door whose polygon it finished nearest (within
``--reach``). That gives an observed origin->exit matrix directly comparable to
the paper's, with two rules that keep the comparison honest:

* Rows are renormalised over the four modelled doors, **per row** -- see
  :mod:`fahy_table2`. Windows carried 27.9 % of real egress and 45 of the 75
  people by the stage; comparing raw counts would make that row unmatchable.
* Agents that never reach a door are reported separately and excluded from the
  shares, rather than being silently dropped or counted against a door.

The registered statistics of the Station validation study are printed below
the table, over the agents of every run given, pooled:

* **T1**, the front-door share of door users over the placed rows, against
  Fahy's 117/229 = 51.1 % (:func:`fahy_table2.placed_door_shares`), with the
  signed bias.
* **W**, the door-user-weighted total variation distance: per scored row
  ½ Σ_doors |model share - Fahy share|, averaged with Fahy's door users as
  weights. Rows with fewer than :data:`MIN_DOOR_USERS` Fahy door users are
  pooled into one row, model agents from those areas with them. A scored row
  with no model door user counts as fully wrong (distance 1).
* The **noise floor** of W: Fahy resampled multinomially against itself.
* With several runs (one per seed), the per-run spread of T1 and W.
* With ``--t-jam``, T1 and W for agents whose exit time (their last recorded
  frame) is before t_jam and for those at or after it.
* With ``--against``, the paired difference W(run) - W(other) per seed, the
  n-th run against the n-th other, on the **same agents**: those that reached
  a door in both. The two runs must spawn the same agents (same ids, areas
  and start positions).
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fahy_table2 as F

DOOR_BY_EXIT_ID = {
    "jps-exits_0": "front",
    "jps-exits_1": "bar_door",
    "jps-exits_2": "kitchen",
    "jps-exits_3": "stage",
}

# Rows with fewer Fahy door users than this are pooled into POOLED_ROW.
MIN_DOOR_USERS = 10
POOLED_ROW = "Pooled small rows"
NOISE_DRAWS = 20_000


@dataclass(frozen=True)
class AgentExit:
    """One agent: where it started and which door, if any, it finished at."""

    agent_id: int
    origin: str | None
    door: str | None
    exit_time: float
    start: tuple[float, float]


def _load(config_path: Path):
    import json

    from shapely.geometry import Polygon

    cfg = json.loads(config_path.read_text())
    exits = {k: Polygon(v["coordinates"]) for k, v in cfg["exits"].items()}
    areas = {
        k: (Polygon(v["coordinates"]), v["parameters"].get("fahy_row", k))
        for k, v in cfg["distributions"].items()
    }
    return exits, areas


def _fps(con: sqlite3.Connection) -> float:
    row = con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()
    if row is None:
        raise ValueError("sqlite metadata table has no 'fps' row")
    return float(row[0])


def _origin(point, areas) -> str | None:
    return next((label for poly, label in areas.values() if poly.contains(point)), None)


def _door(point, exits, reach: float) -> str | None:
    exit_id, poly = min(exits.items(), key=lambda kv: point.distance(kv[1]))
    if point.distance(poly) > reach:
        return None
    return DOOR_BY_EXIT_ID[exit_id]


def observed_agents(
    sqlite_path: Path, config_path: Path, reach: float
) -> list[AgentExit]:
    """Every agent of a run, with its area, door and exit time in seconds.

    The exit time is the agent's last recorded frame, so it is only as fine
    as the trajectory's output interval.
    """
    from shapely.geometry import Point

    exits, areas = _load(config_path)
    con = sqlite3.connect(sqlite_path)
    fps = _fps(con)
    rows = con.execute(
        "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY id, frame"
    ).fetchall()
    con.close()

    first: dict[int, tuple[float, float]] = {}
    last: dict[int, tuple[int, float, float]] = {}
    for aid, frame, x, y in rows:
        first.setdefault(aid, (x, y))
        last[aid] = (frame, x, y)
    return [
        AgentExit(
            agent_id=aid,
            origin=_origin(Point(*start), areas),
            door=_door(Point(*last[aid][1:]), exits, reach),
            exit_time=last[aid][0] / fps,
            start=start,
        )
        for aid, start in first.items()
    ]


def _scored(agent: AgentExit, ids, t_from: float, t_to: float) -> bool:
    if agent.origin is None or agent.door is None:
        return False
    if ids is not None and agent.agent_id not in ids:
        return False
    return t_from <= agent.exit_time < t_to


def door_matrix(
    agents, ids=None, t_from: float = -math.inf, t_to: float = math.inf
) -> dict[str, dict[str, int]]:
    """Origin -> door counts of the placed agents that reached a door.

    *ids* restricts the agents (the same-agent set); *t_from* <= exit time
    < *t_to* restricts their exit times.
    """
    matrix: dict[str, dict[str, int]] = {}
    for agent in (a for a in agents if _scored(a, ids, t_from, t_to)):
        row = matrix.setdefault(agent.origin, {})
        row[agent.door] = row.get(agent.door, 0) + 1
    return matrix


def stuck_counts(agents) -> dict[str, int]:
    """Placed agents per origin that never reached a door."""
    stuck = Counter(a.origin for a in agents if a.origin and a.door is None)
    return dict(stuck)


def observed_matrix(sqlite_path: Path, config_path: Path, reach: float):
    agents = observed_agents(sqlite_path, config_path, reach)
    return door_matrix(agents), stuck_counts(agents)


def fahy_targets() -> dict[str, dict[str, int]]:
    """Fahy's door counts for the placed rows: the table W is scored against."""
    return {row: F.door_counts(row) for row in F.PLACEABLE}


def pooling(targets, min_n: int = MIN_DOOR_USERS) -> dict[str, str]:
    """Row -> the row it is scored as: itself, or :data:`POOLED_ROW`."""
    return {
        row: row if sum(counts.values()) >= min_n else POOLED_ROW
        for row, counts in targets.items()
    }


def pool(matrix, groups: dict[str, str]) -> dict[str, Counter]:
    """Sum the rows of *matrix* by *groups*; rows not in *groups* are dropped."""
    pooled: dict[str, Counter] = {}
    for row in (r for r in matrix if r in groups):
        pooled.setdefault(groups[row], Counter()).update(matrix[row])
    return pooled


def tvd(model, target) -> float:
    """Total variation distance of two door-count rows; 1 if *model* is empty."""
    n_model = sum(model.values())
    n_target = sum(target.values())
    if n_model == 0:
        return 1.0
    doors = set(model) | set(target)
    return 0.5 * sum(
        abs(model.get(d, 0) / n_model - target.get(d, 0) / n_target) for d in doors
    )


def w_statistic(matrix, targets, min_n: int = MIN_DOOR_USERS) -> float:
    """W: the Fahy-door-user-weighted mean of the per-row TVD, rows pooled."""
    groups = pooling(targets, min_n)
    model = pool(matrix, groups)
    target = {g: c for g, c in pool(targets, groups).items() if sum(c.values())}
    total = sum(sum(c.values()) for c in target.values())
    return (
        sum(sum(c.values()) * tvd(model.get(g, {}), c) for g, c in target.items())
        / total
    )


def empty_rows(matrix, targets, min_n: int = MIN_DOOR_USERS) -> list[str]:
    """Scored rows without a model door user, which W counts as distance 1."""
    groups = pooling(targets, min_n)
    model = pool(matrix, groups)
    return [g for g in dict.fromkeys(groups.values()) if not model.get(g)]


def t1(matrix, rows=F.PLACEABLE) -> float | None:
    """Front-door share of the door users in *rows*; None without any."""
    counts = pool(matrix, {r: "all" for r in rows}).get("all", Counter())
    n = sum(counts.values())
    if n == 0:
        return None
    return counts["front"] / n


def noise_floor(
    targets,
    draws: int = NOISE_DRAWS,
    seed: int = 0,
    min_n: int = MIN_DOOR_USERS,
):
    """W of *draws* multinomial resamples of *targets* against themselves."""
    import numpy as np

    groups = pooling(targets, min_n)
    target = {g: c for g, c in pool(targets, groups).items() if sum(c.values())}
    doors = sorted({d for c in target.values() for d in c})
    total = sum(sum(c.values()) for c in target.values())
    rng = np.random.default_rng(seed)
    w = np.zeros(draws)
    for counts in target.values():
        n = sum(counts.values())
        p = np.array([counts.get(d, 0) for d in doors]) / n
        resampled = rng.multinomial(n, p, size=draws) / n
        w += n * 0.5 * np.abs(resampled - p).sum(axis=1)
    return w / total


def _check_same_spawn(a: AgentExit, b: AgentExit | None) -> None:
    if b is None:
        raise ValueError(f"agent {a.agent_id} is missing from the other run")
    if a.origin != b.origin or math.dist(a.start, b.start) > 1e-6:
        raise ValueError(f"agent {a.agent_id} spawns differently in the two runs")


def same_agents(agents_a, agents_b) -> set[int]:
    """Ids of the placed agents that reached a door in both runs.

    Raises ValueError unless both runs hold the same agents, in the same areas
    and start positions: the ids of two arms must name the same people.
    """
    by_id = {b.agent_id: b for b in agents_b}
    if len(by_id) != len(agents_a):
        raise ValueError("the two runs hold different numbers of agents")
    for a in agents_a:
        _check_same_spawn(a, by_id.get(a.agent_id))
    return {
        a.agent_id
        for a in agents_a
        if a.origin and a.door and by_id[a.agent_id].door is not None
    }


def paired_w(agents_a, agents_b, targets) -> tuple[float, float, int]:
    """W of each run on their same-agent set, and the size of that set."""
    ids = same_agents(agents_a, agents_b)
    w_a = w_statistic(door_matrix(agents_a, ids), targets)
    w_b = w_statistic(door_matrix(agents_b, ids), targets)
    return w_a, w_b, len(ids)


def pooled_matrix(matrices) -> dict[str, dict[str, int]]:
    """Sum origin -> door matrices, e.g. of the runs of several seeds."""
    total: dict[str, Counter] = {}
    for matrix in matrices:
        for row, counts in matrix.items():
            total.setdefault(row, Counter()).update(counts)
    return {row: dict(counts) for row, counts in total.items()}


def report(matrix, stuck) -> int:
    print(
        f"{'area at ignition':32s} {'n':>4s}  " + "".join(f"{d:>10s}" for d in F.DOORS)
    )
    print(f"{'':32s} {'':>4s}  " + "".join(f"{'obs / Fahy':>10s}" for _ in F.DOORS))
    print("-" * 84)

    worst = 0.0
    for row in F.PLACEABLE:
        target = F.door_shares(row)
        if not target:
            continue
        obs = matrix.get(row, {})
        n = sum(obs.values())
        if n == 0:
            print(f"{row:32s} {0:4d}   (no agent reached a door)")
            continue
        cells = []
        for d in F.DOORS:
            o = obs.get(d, 0) / n
            cells.append(f"{o:4.0%}/{target[d]:<5.0%}")
            worst = max(worst, abs(o - target[d]))
        print(f"{row:32s} {n:4d}  " + "".join(f"{c:>10s}" for c in cells))

    total = sum(sum(v.values()) for v in matrix.values())
    front = sum(v.get("front", 0) for v in matrix.values())
    print("-" * 84)
    print(f"agents reaching a door: {total}   never reached one: {sum(stuck.values())}")
    if total:
        print(
            f"front-door share: {front / total:.1%}   "
            f"(Fahy: {F.aggregate_door_shares()['front']:.1%} of door users, "
            f"and >= {F.front_door_attempt_floor():.0%} of all survivors tried it)"
        )
    print(f"largest per-row deviation: {worst:.0%}")
    return 0


def _pct(share: float | None) -> str:
    return "n/a" if share is None else f"{share:.1%}"


def _line(label: str, matrix, targets) -> str:
    n = sum(sum(v.values()) for v in matrix.values())
    w = w_statistic(matrix, targets)
    return f"{label:28s} T1 {_pct(t1(matrix)):>6s}   W {w:.3f}   (n = {n})"


def _spread(values) -> str:
    values = sorted(v for v in values if v is not None)
    if not values:
        return "n/a"
    return f"{values[0]:.3f} / {statistics.median(values):.3f} / {values[-1]:.3f}"


def report_statistic(
    runs, t_jam: float | None, draws: int = NOISE_DRAWS, seed: int = 0
) -> None:
    """Print T1, W, the noise floor, the per-run spread and the t_jam split."""
    targets = fahy_targets()
    matrices = [door_matrix(agents) for agents in runs]
    pooled = pooled_matrix(matrices)
    front = F.placed_door_shares()["front"]
    t1_model = t1(pooled)
    n_fahy = sum(sum(c.values()) for c in targets.values())
    front_fahy = sum(c["front"] for c in targets.values())

    print()
    print(f"registered statistics, {len(runs)} run(s) pooled")
    print(
        f"T1  front share of door users, placed rows: {_pct(t1_model)}   "
        f"Fahy {front:.1%} ({front_fahy}/{n_fahy})"
    )
    if t1_model is not None:
        print(f"    signed bias (model - Fahy): {100 * (t1_model - front):+.1f} points")
    print(
        f"    T1' with the unplaceable rows (not a gate): Fahy "
        f"{F.aggregate_door_shares()['front']:.1%}"
    )
    scored = len(set(pooling(targets).values()))
    print(
        f"W   door-user-weighted TVD over {scored} rows: {w_statistic(pooled, targets):.3f}"
    )
    floor = sorted(noise_floor(targets, draws, seed))
    print(
        f"    noise floor, Fahy against itself ({draws} draws): "
        f"median {statistics.median(floor):.3f}, "
        f"p95 {floor[int(0.95 * (len(floor) - 1))]:.3f}"
    )
    missing = empty_rows(pooled, targets)
    if missing:
        print(f"    rows without a model door user (distance 1): {', '.join(missing)}")
    if len(runs) > 1:
        print("per-run spread, min / median / max:")
        print(f"    T1 {_spread(t1(m) for m in matrices)}")
        print(f"    W  {_spread(w_statistic(m, targets) for m in matrices)}")
    if t_jam is None:
        return
    before = pooled_matrix(door_matrix(a, t_to=t_jam) for a in runs)
    after = pooled_matrix(door_matrix(a, t_from=t_jam) for a in runs)
    print(_line(f"exit before t_jam = {t_jam:g} s", before, targets))
    print(_line("exit at or after t_jam", after, targets))


def report_paired(runs, others) -> None:
    """Print W(run) - W(other) per seed on the same-agent set."""
    targets = fahy_targets()
    deltas = []
    print()
    print("paired W on the same agents: run - other")
    for i, (a, b) in enumerate(zip(runs, others, strict=True)):
        w_a, w_b, n = paired_w(a, b, targets)
        deltas.append(w_a - w_b)
        print(
            f"    pair {i + 1}: W {w_a:.3f} - {w_b:.3f} = {w_a - w_b:+.3f}   (n = {n})"
        )
    lower = sum(d < 0 for d in deltas)
    print(
        f"    run lower in {lower} of {len(deltas)} pairs; "
        f"mean difference {statistics.fmean(deltas):+.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sqlite", type=Path, nargs="+", help="one run per seed")
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument(
        "--reach",
        type=float,
        default=2.0,
        help="metres from a door polygon that counts as using it",
    )
    ap.add_argument(
        "--t-jam",
        type=float,
        default=None,
        help="also split by exit before/after this time (s)",
    )
    ap.add_argument(
        "--against",
        type=Path,
        nargs="+",
        default=None,
        help="runs of another arm, paired with the runs in the same order",
    )
    ap.add_argument("--noise-draws", type=int, default=NOISE_DRAWS)
    ap.add_argument("--noise-seed", type=int, default=0)
    args = ap.parse_args()
    if args.against and len(args.against) != len(args.sqlite):
        ap.error("--against needs as many runs as are scored")
    runs = [observed_agents(p, args.config, args.reach) for p in args.sqlite]
    matrix = pooled_matrix(door_matrix(agents) for agents in runs)
    stuck = dict(sum((Counter(stuck_counts(a)) for a in runs), Counter()))
    report(matrix, stuck)
    report_statistic(runs, args.t_jam, args.noise_draws, args.noise_seed)
    if args.against:
        others = [observed_agents(p, args.config, args.reach) for p in args.against]
        report_paired(runs, others)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
