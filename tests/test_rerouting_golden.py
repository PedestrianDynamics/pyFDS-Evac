"""Golden snapshots of rerouting decisions, for a refactor that keeps results.

Issue #187 restructures ``rank_routes``, ``evaluate_route``,
``evaluate_and_reroute`` and the rerouting calls in ``run_scenario``. Its first
stage must not change a single result. These tests pin the current behaviour
so that any change shows up as a failing snapshot.

There are three layers:

* **Scenario runs.** Small asset decks run through ``run_scenario`` with a
  synthetic, time-dependent extinction field, so the runs need no FDS output.
  Each snapshot holds the exact sequence of route switches (time, agent, old
  exit, new exit, reason, old and new cost), a de-duplicated trace of how each
  agent's candidate exits were ranked and why each was refused, and the egress
  totals.
* **``rank_routes`` units.** Hand-built graphs with smoke and FED fields, one
  case per ordering, rejection and fallback branch.
* **``evaluate_and_reroute`` units.** One case per decision branch: explore,
  wander, initial, ``better_path``, anchor allow and refuse, must-flee,
  fallback, and the early returns.

Discrete fields must match exactly. Floats are stored rounded and compared
with an absolute tolerance of ``FLOAT_ABS``, so a rounding boundary does not
flip a snapshot. The order of the switch and ranking sequences is the order
the simulation produced them in and is part of the snapshot.

The unit snapshots hold on every platform. The scenario snapshots are stored
per platform under ``tests/golden/scenarios/<sys.platform>-<machine>/``: the
JuPedSim builds differ in the last bits, and over a minute of walking that is
enough to move an arrival across a one-second reevaluation boundary. The
scenario tests skip on a platform with no snapshots. Each deck runs in its own
interpreter, because JuPedSim numbers agents process-wide and the snapshots
record agent ids. Per-agent draws are seeded from the spawn order, not the id
(#198), so only the labels would differ in a shared process.

Regenerating
------------
Run with ``PYFDS_EVAC_REGEN_GOLDEN=1`` to rewrite every snapshot under
``tests/golden/`` from the current code instead of comparing against it::

    PYFDS_EVAC_REGEN_GOLDEN=1 uv run pytest tests/test_rerouting_golden.py

That writes the scenario snapshots of the current platform only. The CI
platform (``linux-x86_64``) is regenerated from the repository root with::

    docker run --rm --platform linux/amd64 -v "$PWD":/work -w /work \\
        -e UV_PROJECT_ENVIRONMENT=/tmp/venv -e PYFDS_EVAC_REGEN_GOLDEN=1 \\
        ghcr.io/astral-sh/uv:python3.11-bookworm-slim sh -c \\
        "apt-get update -qq && apt-get install -y -qq git && \\
         uv run pytest tests/test_rerouting_golden.py -k scenario"

Only do that when a change of behaviour is intended, and review the diff of
``tests/golden/`` as part of the change. A refactor that is meant to keep the
behaviour must pass without regenerating.

If the refactor changes how a *fallback* route is represented (for example,
keeping ``rejected=True`` and marking the fallback separately), adapt
``_route_status`` and ``_rank_status`` only. They are the one place that maps
the route representation onto the snapshot vocabulary: ``ok``, ``tau``,
``fed``, ``nonvisible``, and ``fallback/<why>``.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, box

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.cognitive_map import AgentCognitiveMap
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCost,
    RouteCostConfig,
    StageGraph,
    evaluate_and_reroute,
    rank_routes,
)
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel
from pyfds_evac.core.visibility import VisibilityModel, extract_sign_descriptors

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets"
GOLDEN = Path(__file__).resolve().parent / "golden"
REGEN = os.environ.get("PYFDS_EVAC_REGEN_GOLDEN") == "1"
FLOAT_DIGITS = 4
FLOAT_ABS = 1e-3
# Scenario runs are stored per platform: the JuPedSim builds for different
# platforms differ in the last bits, and over a minute of simulated walking
# that moves an arrival across a one-second reevaluation boundary.
PLATFORM = f"{sys.platform}-{platform.machine()}"


# ── Snapshot plumbing ─────────────────────────────────────────────────


def _r(value: float | None, digits: int = FLOAT_DIGITS) -> float | None:
    """Round a float for a snapshot; infinities and None pass through."""
    if value is None:
        return None
    value = float(value)
    if math.isinf(value) or math.isnan(value):
        return value
    return round(value, digits)


def _mismatch(expected: Any, actual: Any, where: str) -> str | None:
    """Describe the first difference between two snapshot values, if any."""
    if isinstance(expected, float) or isinstance(actual, float):
        return _float_mismatch(expected, actual, where)
    if isinstance(expected, dict) and isinstance(actual, dict):
        return _dict_mismatch(expected, actual, where)
    if isinstance(expected, list) and isinstance(actual, list):
        return _list_mismatch(expected, actual, where)
    if expected != actual:
        return f"{where}: expected {expected!r}, got {actual!r}"
    return None


def _float_mismatch(expected: Any, actual: Any, where: str) -> str | None:
    both_numbers = isinstance(expected, (int, float)) and isinstance(
        actual, (int, float)
    )
    if not both_numbers:
        return f"{where}: expected {expected!r}, got {actual!r}"
    if expected == actual:
        return None
    if abs(expected - actual) <= FLOAT_ABS:
        return None
    return f"{where}: expected {expected!r}, got {actual!r}"


def _dict_mismatch(expected: dict, actual: dict, where: str) -> str | None:
    if expected.keys() != actual.keys():
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        return f"{where}: keys differ, missing {missing}, extra {extra}"
    for key in expected:
        found = _mismatch(expected[key], actual[key], f"{where}.{key}")
        if found:
            return found
    return None


def _list_mismatch(expected: list, actual: list, where: str) -> str | None:
    for index, (exp, act) in enumerate(zip(expected, actual)):
        found = _mismatch(exp, act, f"{where}[{index}]")
        if found:
            return found
    if len(expected) != len(actual):
        return f"{where}: length {len(actual)}, expected {len(expected)}"
    return None


def _check_golden(relpath: str, actual: dict) -> None:
    """Compare *actual* with the stored snapshot, or rewrite it under REGEN."""
    path = GOLDEN / relpath
    # A JSON round trip gives the same types the stored file will have
    # (tuples become lists), so the comparison is like for like.
    actual = json.loads(json.dumps(actual, sort_keys=True))
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(actual, indent=1, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8")
        return
    assert path.is_file(), (
        f"missing snapshot {path}; run with PYFDS_EVAC_REGEN_GOLDEN=1 to create it"
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    found = _mismatch(expected, actual, relpath)
    assert found is None, found


# ── Route status vocabulary ───────────────────────────────────────────


def _category(reason: str) -> str:
    """Why a route was refused, reduced to its kind."""
    if reason.startswith("FED"):
        return "fed"
    if reason.startswith("tau"):
        return "tau"
    if "visible" in reason:
        return "nonvisible"
    return reason


def _rank_status(rejected: bool, reason: str | None) -> str:
    """Map a route's refusal state onto the snapshot vocabulary."""
    reason = reason or ""
    if reason.startswith("fallback: "):
        return "fallback/" + _category(reason.removeprefix("fallback: "))
    if not rejected:
        return "ok"
    return _category(reason)


def _route_status(row: dict) -> str:
    """The same vocabulary for one row of ``route_cost_history``."""
    return _rank_status(bool(row["rejected"]), row["rejection_reason"])


# ── Synthetic fields ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Blob:
    """Extinction on a rectangle, ramping up from *t_on* at *rate* to *cap*.

    A large rate makes it a step. The blob vanishes at *t_off*.
    """

    x0: float
    x1: float
    y0: float
    y1: float
    t_on: float
    rate: float
    cap: float
    t_off: float = math.inf

    def extinction(self, time_s: float, x: float, y: float) -> float:
        if not (self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1):
            return 0.0
        if time_s >= self.t_off:
            return 0.0
        return min(self.cap, max(0.0, self.rate * (time_s - self.t_on)))


@dataclass(frozen=True)
class BlobField:
    """Sum of blobs; the extinction sampler for scenario runs."""

    blobs: tuple[Blob, ...]

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return sum(b.extinction(time_s, x, y) for b in self.blobs)


# ── Scenario runs ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Deck:
    """One small deterministic scenario run."""

    config: str
    cost_model: str
    blobs: tuple[Blob, ...]
    agents: int = 30
    flow_end_s: float | None = 20.0
    max_time_s: float = 60.0
    # Extinction of the clear-air sign-visibility model; None builds none.
    vis_extinction: float | None = None
    seed: int = 1
    # Overrides the deck's familiarity when set.
    familiarity: float | str | None = None

    def describe(self) -> dict:
        return {
            "config": self.config,
            "cost_model": self.cost_model,
            "blobs": [list(vars(b).values()) for b in self.blobs],
            "agents": self.agents,
            "flow_end_s": self.flow_end_s,
            "max_time_s": self.max_time_s,
            "vis_extinction": self.vis_extinction,
            "seed": self.seed,
            "familiarity": self.familiarity,
        }


# T-junction: exit B 10 m right of the junction, exit A 20 m left.
_TJ_RIGHT = (21.0, 31.0, -1.0, 20.0)
_TJ_LEFT = (-1.0, 16.0, -1.0, 20.0)
_TJ_ALL = (-1.0, 31.0, -1.0, 20.0)
_TJ_RAMP = (
    Blob(*_TJ_RIGHT, t_on=12.0, rate=0.3, cap=4.0),
    Blob(*_TJ_LEFT, t_on=20.0, rate=0.2, cap=4.0),
    Blob(*_TJ_ALL, t_on=28.0, rate=0.3, cap=5.0),
)
# The right arm is hazy from the start, so agents take the left exit; then the
# left arm fills at once and every route is refused, leaving the right exit as
# the least-bad one -- and the quicker one, which the anchor needs.
_TJ_FALLBACK = (
    Blob(*_TJ_RIGHT, t_on=0.0, rate=100.0, cap=1.0),
    Blob(*_TJ_LEFT, t_on=12.0, rate=100.0, cap=5.0),
)
# familiarity_test: smoke on the direct leg to the exit's last checkpoint
# pushes committed agents onto another path to the same exit.
_FT_DETOUR = (Blob(16.5, 20.0, 6.0, 12.0, t_on=4.0, rate=100.0, cap=2.0),)
_FT_ROOM = (
    Blob(4.0, 10.0, 0.0, 8.0, t_on=5.0, rate=0.3, cap=4.0),
    Blob(14.0, 20.0, 8.0, 18.0, t_on=15.0, rate=0.3, cap=4.0),
)
# blind_spawn_discovery: smoke in the west wing once agents have explored.
_BS_WEST = (Blob(0.0, 12.0, 19.0, 30.0, t_on=10.0, rate=0.2, cap=2.0),)
_CM_SIDE = (Blob(3.0, 5.0, 17.0, 23.0, t_on=8.0, rate=100.0, cap=3.0),)
_EVA_NEAR = (Blob(0.0, 4.0, 0.0, 6.0, t_on=5.0, rate=0.3, cap=3.0),)

DECKS: dict[str, Deck] = {
    "tj_full_gate_ramp": Deck("t_junction/config_full.json", "gate", _TJ_RAMP),
    "tj_full_additive_ramp": Deck("t_junction/config_full.json", "additive", _TJ_RAMP),
    "tj_full_gate_fallback": Deck("t_junction/config_full.json", "gate", _TJ_FALLBACK),
    "tj_discovery_gate_ramp": Deck(
        "t_junction/config_discovery.json", "gate", _TJ_RAMP, vis_extinction=0.0
    ),
    "tj_discovery_additive_ramp": Deck(
        "t_junction/config_discovery.json",
        "additive",
        _TJ_RAMP,
        vis_extinction=0.0,
    ),
    "ft_full_gate_detour": Deck(
        "familiarity_test_full/config.json", "gate", _FT_DETOUR, flow_end_s=10.0
    ),
    "ft_full_additive_detour": Deck(
        "familiarity_test_full/config.json",
        "additive",
        _FT_DETOUR,
        flow_end_s=10.0,
    ),
    "ft_discovery_gate_room": Deck(
        "familiarity_test_discovery/config.json",
        "gate",
        _FT_ROOM,
        agents=6,
        vis_extinction=0.0,
    ),
    "ft_discovery_additive_room": Deck(
        "familiarity_test_discovery/config.json",
        "additive",
        _FT_ROOM,
        agents=6,
        vis_extinction=0.0,
    ),
    "bs_discovery_gate_west": Deck(
        "blind_spawn_discovery/config_discovery.json",
        "gate",
        _BS_WEST,
        agents=10,
        flow_end_s=None,
        vis_extinction=0.0,
    ),
    # Signs illegible everywhere: the map never grows past the first doorway,
    # the frontier runs out, and agents patrol what they know.
    "bs_discovery_gate_fog": Deck(
        "blind_spawn_discovery/config_discovery.json",
        "gate",
        _BS_WEST,
        agents=10,
        flow_end_s=None,
        vis_extinction=1.0,
    ),
    # Scalar familiarity: each agent knows each exit with probability 0.5.
    "tj_mixed_additive_ramp": Deck(
        "t_junction/config_discovery.json",
        "additive",
        _TJ_RAMP,
        vis_extinction=0.0,
        familiarity=0.5,
    ),
    "cm_memory_gate_side": Deck(
        "cognitive_map_memory/config.json",
        "gate",
        _CM_SIDE,
        agents=6,
        flow_end_s=10.0,
        vis_extinction=0.0,
    ),
    "eva_visible_gate_near": Deck(
        "exit_visibility_alpha/config_visible.json",
        "gate",
        _EVA_NEAR,
        agents=10,
        flow_end_s=None,
        vis_extinction=0.0,
    ),
    "eva_hidden_additive_near": Deck(
        "exit_visibility_alpha/config_hidden.json",
        "additive",
        _EVA_NEAR,
        agents=10,
        flow_end_s=None,
        vis_extinction=0.0,
    ),
}


def _prepare_scenario(deck: Deck):
    scenario = load_scenario(str(ASSETS / deck.config))
    for dist in scenario.raw["distributions"].values():
        params = dist.setdefault("parameters", {})
        params["number"] = deck.agents
        params["distribution_mode"] = "by_number"
        params["use_premovement"] = False
        params["use_flow_spawning"] = deck.flow_end_s is not None
        if deck.familiarity is not None:
            params["familiarity"] = deck.familiarity
        if deck.flow_end_s is not None:
            params["flow_start_time"] = 0
            params["flow_end_time"] = deck.flow_end_s
    scenario = scenario.copy()
    scenario.set_max_time(deck.max_time_s)
    return scenario


def _vis_model(scenario, extinction: float | None):
    if extinction is None:
        return None
    walkable = shapely_wkt.loads(scenario.walkable_area_wkt)
    return VisibilityModel.clear_air(
        walkable,
        extract_sign_descriptors(scenario.raw),
        cell_size_m=0.25,
        extinction_per_m=extinction,
    )


def _run_deck(deck: Deck) -> dict:
    scenario = _prepare_scenario(deck)
    routing = {**scenario.raw.get("routing", {}), "cost_model": deck.cost_model}
    cost_config = RouteCostConfig.from_routing_params(routing)
    smoke = SmokeSpeedModel(
        BlobField(deck.blobs), SmokeSpeedConfig(fds_dir=".", update_interval_s=1.0)
    )
    # The engine and the visibility model both print progress; keep the test
    # output readable.
    with contextlib.redirect_stdout(io.StringIO()):
        vis = _vis_model(scenario, deck.vis_extinction)
        result = run_scenario(
            scenario,
            seed=deck.seed,
            smoke_speed_model=smoke,
            reroute_config=RerouteConfig(
                reevaluation_interval_s=1.0, cost_config=cost_config
            ),
            collect_route_cost_history=True,
            vis_model=vis,
        )
    try:
        return {
            "deck": deck.describe(),
            "summary": {
                "total_agents": result.total_agents,
                "agents_evacuated": result.agents_evacuated,
                "evacuation_time": _r(result.evacuation_time, 2),
            },
            "switches": [_switch_row(row) for row in result.route_history or []],
            "rankings": _ranking_trace(result.route_cost_history or []),
        }
    finally:
        result.cleanup()


def _switch_row(row: dict) -> dict:
    old_cost = row["old_cost"]
    return {
        "time_s": _r(row["time_s"], 2),
        "agent_id": row["agent_id"],
        "old_exit": row["old_exit"],
        "new_exit": row["new_exit"],
        "reason": row["reason"],
        "old_cost": None if old_cost == "" else _r(old_cost, 3),
        "new_cost": _r(row["new_cost"], 3),
    }


def _ranking_trace(rows: list[dict]) -> list[list]:
    """Each agent's candidate ordering, recorded only when it changes.

    One entry is ``[time, agent, source, current exit, ranking]`` where the
    ranking lists ``exit:status`` in rank order. Discrete only, so it is
    robust to float noise, and de-duplicated per agent to keep it small.
    """
    evaluations: list[tuple[float, int, str, str, list[str]]] = []
    for row in rows:
        key = (row["time_s"], row["agent_id"])
        entry = f"{row['exit_id']}:{_route_status(row)}"
        if evaluations and evaluations[-1][:2] == key:
            evaluations[-1][4].append(entry)
            continue
        evaluations.append(
            (key[0], key[1], row["source"], row["current_exit"], [entry])
        )
    trace: list[list] = []
    last: dict[int, tuple] = {}
    for time_s, agent_id, source, current, ranking in evaluations:
        state = (source, current, tuple(ranking))
        if last.get(agent_id) == state:
            continue
        last[agent_id] = state
        trace.append([_r(time_s, 2), agent_id, source, current, " > ".join(ranking)])
    return trace


def _run_deck_isolated(name: str, tmp_path: Path) -> dict:
    """Run one deck in a fresh interpreter.

    JuPedSim numbers agents process-wide, so a deck run after another in the
    same process labels its agents with other ids than the same deck run
    alone. The snapshots record ids, so each deck gets its own process.
    """
    out = tmp_path / f"{name}.json"
    subprocess.run(
        [sys.executable, __file__, name, str(out)],
        check=True,
        cwd=REPO,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(DECKS))
def test_scenario_decisions_match_golden(name, tmp_path):
    if not REGEN and not (GOLDEN / "scenarios" / PLATFORM).is_dir():
        pytest.skip(f"no scenario snapshots for {PLATFORM}")
    _check_golden(
        f"scenarios/{PLATFORM}/{name}.json", _run_deck_isolated(name, tmp_path)
    )


# ── Hand-built graphs for the unit layers ─────────────────────────────


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    return box(cx - half, cy - half, cx + half, cy + half)


# Exits on the four arms of a star around a spawn area at the origin.
_ARM_XY = {
    "west": (-1.0, 0.0),
    "east": (1.0, 0.0),
    "north": (0.0, 1.0),
    "south": (0.0, -1.0),
}


def _star(lengths: dict[str, float]) -> StageGraph:
    """Spawn at the origin and one exit per arm at the given distance."""
    stages = {}
    for arm, length in lengths.items():
        ux, uy = _ARM_XY[arm]
        stages[arm] = {"polygon": _box(ux * length, uy * length), "stage_type": "exit"}
    return StageGraph.from_scenario(
        stages, [], distributions={"spawn": {"polygon": _box(0.0, 0.0)}}
    )


def _arm_of(x: float, y: float) -> str:
    # The spawn area belongs to no arm, so an arm's smoke stays on its arm.
    if max(abs(x), abs(y)) <= 1.0:
        return "spawn"
    if abs(x) >= abs(y):
        return "west" if x < 0 else "east"
    return "south" if y < 0 else "north"


@dataclass(frozen=True)
class ArmField:
    """Constant extinction per arm of the star, optionally from *t_on*."""

    k: dict[str, float]
    t_on: float = -math.inf

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        if time_s < self.t_on:
            return 0.0
        return self.k.get(_arm_of(x, y), 0.0)


@dataclass(frozen=True)
class ArmFed:
    """Constant FED rate per minute per arm of the star."""

    rate: dict[str, float]

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        del time_s
        return self.rate.get(_arm_of(x, y), 0.0)


@dataclass(frozen=True)
class HalfPlane:
    """Extinction *k* where ``y < 0``, clear air elsewhere."""

    k: float

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        del time_s, x
        return self.k if y < 0.0 else 0.0


@dataclass(frozen=True)
class LateSmoke:
    """Extinction *k* where ``x >= x_min``, from *t_on* on."""

    k: float
    x_min: float
    t_on: float

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        del y
        return self.k if time_s >= self.t_on and x >= self.x_min else 0.0


_CLEAR = ArmField({})
_LATE = LateSmoke(k=0.8, x_min=11.0, t_on=6.0)


def _graph(nodes: dict, transitions: list) -> StageGraph:
    """A graph from ``{id: (cx, cy, type)}`` and a spawn area D0 at the origin."""
    stages = {
        nid: {"polygon": _box(cx, cy), "stage_type": st}
        for nid, (cx, cy, st) in nodes.items()
    }
    dists = {"D0": {"coordinates": list(_box(0.0, 0.0).exterior.coords)}}
    return StageGraph.from_scenario(stages, transitions, dists)


def _edges(*pairs: tuple[str, str]) -> list[dict]:
    return [{"from": a, "to": b} for a, b in pairs]


def _linear() -> StageGraph:
    """D0 -> C0 -> E0 on a straight line."""
    return _graph(
        {"C0": (10, 0, "checkpoint"), "E0": (20, 0, "exit")},
        _edges(("D0", "C0"), ("C0", "E0")),
    )


def _dead_end() -> StageGraph:
    """D0 -> C0, and an exit E0 that only an unconnected C1 leads to."""
    return _graph(
        {
            "C0": (10, 0, "checkpoint"),
            "C1": (0, 10, "checkpoint"),
            "E0": (0, 20, "exit"),
        },
        _edges(("D0", "C0"), ("C1", "E0")),
    )


def _diamond() -> StageGraph:
    """Short path D0-C0-E0 and a long detour D0-C1-E0 to one exit."""
    return _graph(
        {
            "C0": (0, 10, "checkpoint"),
            "C1": (0, 30, "checkpoint"),
            "E0": (20, 10, "exit"),
        },
        _edges(("D0", "C0"), ("D0", "C1"), ("C0", "E0"), ("C1", "E0")),
    )


def _twin() -> StageGraph:
    """Two near-equal paths to E0, south via C1 and north via C0."""
    return _graph(
        {
            "C0": (10, 2, "checkpoint"),
            "C1": (10, -1, "checkpoint"),
            "E0": (20, 0, "exit"),
        },
        _edges(("D0", "C0"), ("D0", "C1"), ("C0", "E0"), ("C1", "E0")),
    )


def _gate(**overrides) -> RouteCostConfig:
    base = RouteCostConfig(
        cost_model="gate", base_speed_m_per_s=1.0, w_smoke=0.0, w_fed=0.0
    )
    return replace(base, **overrides)


def _additive(**overrides) -> RouteCostConfig:
    base = RouteCostConfig(cost_model="additive", base_speed_m_per_s=1.0)
    return replace(base, **overrides)


def _route_snapshot(rc: RouteCost) -> dict:
    return {
        "exit_id": rc.exit_id,
        "path": list(rc.path),
        "status": _rank_status(rc.rejected, rc.rejection_reason),
        "feasible": rc.feasible,
        "clean": rc.clean,
        "tau_route": _r(rc.tau_route),
        "rank_cost": _r(rc.rank_cost),
        "k_max_route": _r(rc.k_max_route),
        "k_leg_max": _r(rc.k_leg_max),
        "fed_max_route": _r(rc.fed_max_route),
        "travel_time_s": _r(rc.travel_time_s),
        "composite_cost": _r(rc.composite_cost),
        "queue_time_s": _r(rc.queue_time_s),
    }


# ── rank_routes units ─────────────────────────────────────────────────


@dataclass(frozen=True)
class RankCase:
    """Arguments for one ``rank_routes`` call on a hand-built graph."""

    graph: Callable[[], StageGraph]
    config: RouteCostConfig
    extinction: Any = _CLEAR
    fed: Any = None
    source: str = "spawn"
    time_s: float = 0.0
    current_fed: float = 0.0
    current_exit: str | None = None
    exit_counts: dict[str, int] | None = None
    cognitive_map: Callable[[], AgentCognitiveMap] | None = None
    agent_position: tuple[float, float] | None = None


def _star2() -> StageGraph:
    return _star({"west": 20.0, "east": 40.0})


def _star3() -> StageGraph:
    return _star({"west": 10.0, "east": 30.0, "north": 50.0})


RANK_CASES: dict[str, RankCase] = {
    # Gate: clear air, time decides.
    "gate_clear": RankCase(_star2, _gate()),
    # Gate: tau over budget refuses the smoky near exit.
    "gate_tau_refuses_near": RankCase(_star2, _gate(), ArmField({"west": 0.35})),
    # Gate: the same smoke allows a short route and refuses a long one.
    "gate_tau_length_relative": RankCase(
        _star2, _gate(), ArmField({"west": 0.2, "east": 0.2})
    ),
    # Gate: tau orders feasible routes before time does.
    "gate_tau_orders_feasible": RankCase(
        _star2, _gate(), ArmField({"west": 0.2, "east": 0.04})
    ),
    # Gate: the current exit's tau is discounted and keeps it first.
    "gate_current_exit_discount": RankCase(
        _star2,
        _gate(),
        ArmField({"west": 0.2, "east": 0.105}),
        current_exit="east",
    ),
    "gate_no_current_exit_same_field": RankCase(
        _star2, _gate(), ArmField({"west": 0.2, "east": 0.105})
    ),
    # Gate: a rival is held to tau_max * tau_return_margin.
    "gate_rival_return_margin": RankCase(
        _star2, _gate(), ArmField({"west": 0.28}), current_exit="east"
    ),
    "gate_rival_without_current": RankCase(_star2, _gate(), ArmField({"west": 0.28})),
    # Gate: everything refused, no current exit: least tau is the fallback.
    "gate_fallback_no_current": RankCase(
        _star2, _gate(), ArmField({"west": 0.5, "east": 0.5})
    ),
    # Gate: everything refused, the rival's worst stretch is not 20 % milder:
    # the current exit is kept as the fallback.
    "gate_fallback_margin_keeps_current": RankCase(
        _star2, _gate(), ArmField({"west": 0.5, "east": 0.5}), current_exit="east"
    ),
    # Gate: everything refused, the rival is clearly milder: it wins.
    "gate_fallback_rival_beats_margin": RankCase(
        _star2, _gate(), ArmField({"west": 0.4, "east": 2.0}), current_exit="east"
    ),
    # Gate: FED over the threshold refuses the route.
    "gate_fed_refuses": RankCase(
        _star2, _gate(), fed=ArmFed({"west": 4.0}), current_fed=0.2
    ),
    # Gate: a rival FED between margin and threshold is refused only as a rival.
    "gate_fed_return_margin_rival": RankCase(
        _star2,
        _gate(),
        fed=ArmFed({"west": 2.5}),
        current_fed=0.1,
        current_exit="east",
    ),
    "gate_fed_return_margin_current": RankCase(
        _star2,
        _gate(),
        fed=ArmFed({"west": 2.5}),
        current_fed=0.1,
        current_exit="west",
    ),
    # Gate: FED and tau both fail; the tau reason overwrites the FED one.
    "gate_fed_and_tau": RankCase(
        _star2,
        _gate(),
        ArmField({"west": 0.5}),
        fed=ArmFed({"west": 4.0}),
        current_fed=0.2,
    ),
    # Gate: the clean tier puts a clean long route ahead of a hazy short one.
    "gate_clean_tier": RankCase(
        _star2, _gate(clean_extinction_threshold=0.03), ArmField({"west": 0.05})
    ),
    # Gate: the current exit keeps its clean membership past the threshold.
    "gate_clean_tier_current_margin": RankCase(
        _star2,
        _gate(clean_extinction_threshold=0.03),
        ArmField({"west": 0.05}),
        current_exit="west",
    ),
    # Gate: queue time enters rank_cost.
    "gate_queue": RankCase(
        _star2, _gate(w_queue=1.0), exit_counts={"west": 40, "east": 0}
    ),
    # Gate: smoke on the second leg arrives before the agent does, and is
    # charged only when anticipated within the foresight horizon.
    "gate_anticipate_on": RankCase(_linear, _gate(), _LATE, source="D0"),
    "gate_anticipate_off": RankCase(
        _linear, _gate(anticipate=False), _LATE, source="D0"
    ),
    "gate_foresight_horizon": RankCase(
        _linear, _gate(foresight_horizon_s=5.0), _LATE, source="D0"
    ),
    # Gate: position-aware length from where the agent stands.
    "gate_agent_position": RankCase(
        _star2, _gate(), ArmField({"west": 0.2}), agent_position=(-8.0, 0.0)
    ),
    # Gate: three exits, the ordering beyond the top two.
    "gate_three_exits": RankCase(
        _star3,
        _gate(),
        ArmField({"west": 0.19, "east": 0.07, "north": 0.031}),
        current_exit="east",
    ),
    # A cognitive map restricts the graph to what the agent knows.
    "gate_cognitive_map": RankCase(
        _star2,
        _gate(),
        cognitive_map=lambda: AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"spawn", "east"},
            known_edges={("spawn", "east")},
        ),
    ),
    # The source is an exit: the route is the exit itself.
    "gate_source_is_exit": RankCase(_star2, _gate(), source="west"),
    # No exit reachable from the source.
    "gate_no_route": RankCase(_dead_end, _gate(), source="C0"),
    # Gate: several paths to one exit; Dijkstra on tau picks the clean one.
    "gate_twin_paths_smoke": RankCase(_twin, _gate(), HalfPlane(0.4), source="D0"),
    # Additive: clear air, composite decides.
    "additive_clear": RankCase(_star2, _additive()),
    # Additive: smoke is a toll per metre and can flip the order.
    "additive_smoke_toll": RankCase(
        _star2, _additive(w_smoke=5.0), ArmField({"west": 0.3})
    ),
    # Additive: a route with no visible segment is refused while another is
    # visible.
    "additive_nonvisible": RankCase(_star2, _additive(), ArmField({"west": 0.8})),
    # Additive: every route non-visible, so none is refused for it.
    "additive_all_nonvisible": RankCase(
        _star2, _additive(), ArmField({"west": 0.8, "east": 0.8})
    ),
    # Additive: FED refusal and fallback.
    "additive_fed_refuses": RankCase(
        _star2, _additive(), fed=ArmFed({"west": 4.0}), current_fed=0.2
    ),
    "additive_fed_fallback": RankCase(
        _star2,
        _additive(),
        fed=ArmFed({"west": 4.0, "east": 4.0}),
        current_fed=0.2,
        current_exit="east",
    ),
    # Additive: the current exit gets no tau discount; queue enters composite.
    "additive_queue": RankCase(
        _star2, _additive(w_queue=1.0), exit_counts={"west": 40, "east": 0}
    ),
    "additive_twin_paths_smoke": RankCase(
        _twin, _additive(), HalfPlane(0.4), source="D0"
    ),
}


@pytest.mark.parametrize("name", sorted(RANK_CASES))
def test_rank_routes_matches_golden(name):
    case = RANK_CASES[name]
    ranked = rank_routes(
        case.graph(),
        case.source,
        case.time_s,
        case.current_fed,
        case.extinction,
        case.fed,
        case.config,
        exit_counts=case.exit_counts,
        cognitive_map=case.cognitive_map() if case.cognitive_map else None,
        agent_position=case.agent_position,
        current_exit=case.current_exit,
    )
    _check_golden(
        f"rank_routes/{name}.json",
        {"ranked": [_route_snapshot(rc) for rc in ranked]},
    )


# ── evaluate_and_reroute units ────────────────────────────────────────


def _stage_configs(graph: StageGraph) -> dict:
    return {
        sid: {
            "polygon": _box(node.centroid_x, node.centroid_y),
            "stage_type": node.stage_type,
            "waiting_time": 0.0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 0.0,
            "speed_factor": 1.0,
        }
        for sid, node in graph.nodes.items()
    }


def _wait_info(
    graph: StageGraph,
    origin: str,
    target: str,
    path_choices: dict | None = None,
    state: str = "to_target",
) -> dict:
    node = graph.nodes[target]
    return {
        "mode": "path",
        "path_choices": path_choices or {},
        "stage_configs": _stage_configs(graph),
        "current_origin": origin,
        "current_target_stage": target,
        "target": (node.centroid_x, node.centroid_y),
        "target_assigned": False,
        "state": state,
        "wait_until": None,
        "inside_since": None,
        "reach_penetration": 0.25,
        "reach_dwell_seconds": 0.2,
        "step_index": 0,
        "base_seed": 42,
        "agent_radius": 0.2,
    }


@dataclass(frozen=True)
class RerouteCase:
    """One ``evaluate_and_reroute`` call on a hand-built graph."""

    graph: Callable[[], StageGraph]
    config: RouteCostConfig
    origin: str
    target: str
    current_exit: str | None
    current_path: tuple[str, ...] = ()
    path_choices: dict = field(default_factory=dict)
    state: str = "to_target"
    extinction: Any = _CLEAR
    fed: Any = None
    current_fed: float = 0.0
    time_s: float = 5.0
    wander_step: int = 0
    cognitive_map: Callable[[], AgentCognitiveMap] | None = None
    agent_position: tuple[float, float] | None = None
    anchor: float = 0.9


def _choices(*path: str) -> dict:
    return {a: [(b, 100.0)] for a, b in zip(path, path[1:])}


def _explore_map() -> AgentCognitiveMap:
    return AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"D0", "C0"},
        known_edges={("D0", "C0")},
        visited_nodes={"D0"},
    )


def _exhausted_map() -> AgentCognitiveMap:
    return AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"D0", "C0"},
        known_edges={("D0", "C0")},
        visited_nodes={"D0", "C0"},
    )


def _lonely_map() -> AgentCognitiveMap:
    return AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"D0"},
        known_edges=set(),
        visited_nodes={"D0"},
    )


REROUTE_CASES: dict[str, RerouteCase] = {
    # Early returns.
    "source_not_in_graph": RerouteCase(_star2, _gate(), "nowhere", "west", "west"),
    "no_route_without_map": RerouteCase(_dead_end, _gate(), "C0", "C0", None),
    "source_is_exit": RerouteCase(_star2, _gate(), "west", "west", "west"),
    # The only route is the exit itself, one node long: nothing to walk.
    "source_is_exit_initial": RerouteCase(_star2, _gate(), "west", "west", None),
    # Discovery with no exit known: head for the frontier.
    "explore_frontier": RerouteCase(
        _linear,
        _gate(),
        "D0",
        "D0",
        None,
        cognitive_map=_explore_map,
    ),
    # Already walking to that frontier: no repeated switch.
    "explore_already_committed": RerouteCase(
        _linear,
        _gate(),
        "D0",
        "C0",
        None,
        current_path=("D0", "C0"),
        path_choices=_choices("D0", "C0"),
        cognitive_map=_explore_map,
    ),
    # Frontier exhausted: patrol the known nodes.
    "wander_patrol": RerouteCase(
        _linear,
        _gate(),
        "C0",
        "C0",
        None,
        state="idle",
        current_path=("D0", "C0"),
        cognitive_map=_exhausted_map,
    ),
    "wander_nowhere": RerouteCase(
        _linear, _gate(), "D0", "D0", None, cognitive_map=_lonely_map
    ),
    # The first choice.
    "initial_gate": RerouteCase(_star2, _gate(), "spawn", "west", None),
    "initial_additive": RerouteCase(_star2, _additive(), "spawn", "west", None),
    # Same exit: a path more than 10 % quicker.
    "better_path_ten_percent": RerouteCase(
        _diamond,
        _gate(),
        "D0",
        "C1",
        "E0",
        current_path=("D0", "C1", "E0"),
        path_choices=_choices("D0", "C1", "E0"),
    ),
    "better_path_additive": RerouteCase(
        _diamond,
        _additive(),
        "D0",
        "C1",
        "E0",
        current_path=("D0", "C1", "E0"),
        path_choices=_choices("D0", "C1", "E0"),
    ),
    # Same exit: the walked path is refused and a feasible one exists.
    "better_path_leaves_rejected": RerouteCase(
        _twin,
        _gate(),
        "D0",
        "C1",
        "E0",
        current_path=("D0", "C1", "E0"),
        path_choices=_choices("D0", "C1", "E0"),
        extinction=HalfPlane(0.4),
    ),
    # Same exit, already on the best path: nothing happens.
    "same_exit_no_change": RerouteCase(
        _diamond,
        _gate(),
        "D0",
        "C0",
        "E0",
        current_path=("D0", "C0", "E0"),
        path_choices=_choices("D0", "C0", "E0"),
    ),
    # Same exit, but the walked path cannot be reconstructed to the exit.
    "same_exit_committed_unknown": RerouteCase(_diamond, _gate(), "D0", "C0", "E0"),
    # Same exit but idle: routed anyway, through the switching branch.
    "same_exit_idle": RerouteCase(
        _star2, _gate(), "spawn", "spawn", "west", state="idle"
    ),
    # Gate anchor: the rival is cleaner by more than the deadband.
    "gate_anchor_cleaner": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "east",
        "east",
        extinction=ArmField({"west": 0.05, "east": 0.12}),
    ),
    # Gate anchor: within the deadband and quicker by more than 10 %.
    "gate_anchor_deadband_quicker": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "east",
        "east",
        extinction=ArmField({"west": 0.08, "east": 0.05}),
    ),
    # Gate anchor: within the deadband but slower; the scan stops at the
    # current exit and the anchor refuses.
    "gate_anchor_deadband_slower": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 0.1, "east": 0.0375}),
    ),
    # Gate: the top-ranked rival is refused, a lower-ranked one is adopted.
    "gate_scan_skips_to_second": RerouteCase(
        _star3,
        _gate(),
        "spawn",
        "east",
        "east",
        extinction=ArmField({"west": 0.19, "east": 0.07, "north": 0.031}),
    ),
    # Gate: the clean tier bypasses the anchor.
    "gate_anchor_clean_bypass": RerouteCase(
        _star2,
        _gate(clean_extinction_threshold=0.03),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 0.05}),
    ),
    # Gate: a clean rival against a current exit past its clean margin.
    "gate_anchor_clean_over_dirty": RerouteCase(
        _star2,
        _gate(clean_extinction_threshold=0.01),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 0.15}),
    ),
    # Gate: every route refused; the fallback winner is quicker: switch.
    "gate_fallback_switch": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "east",
        "east",
        extinction=ArmField({"west": 0.4, "east": 2.0}),
    ),
    # Gate: every route refused; the fallback winner is slower: anchor refuses.
    "gate_fallback_slower_refused": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 2.0, "east": 0.2}),
    ),
    # Gate: the fallback winner is refused, the next candidate is still
    # rejected, and adopting a rejected route is not allowed.
    "gate_scan_lands_on_rejected": RerouteCase(
        _star3,
        _gate(),
        "spawn",
        "east",
        "east",
        extinction=ArmField({"west": 1.2, "east": 0.5, "north": 0.2}),
    ),
    # A FED-lethal current exit is fled whatever the anchor says.
    "must_flee_fed": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "west",
        "west",
        fed=ArmFed({"west": 4.0}),
        current_fed=0.2,
    ),
    "must_flee_fed_additive": RerouteCase(
        _star2,
        _additive(),
        "spawn",
        "west",
        "west",
        fed=ArmFed({"west": 4.0}),
        current_fed=0.2,
    ),
    # Additive: impassable non-visible smoke is fled.
    "must_flee_impassable_additive": RerouteCase(
        _star2,
        _additive(),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 3.5}),
    ),
    # Additive: mild non-visible smoke stays subject to the anchor.
    "additive_mild_nonvisible_anchor": RerouteCase(
        _star2,
        _additive(),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 0.8}),
    ),
    # Additive anchor ratio: switch allowed and refused.
    "additive_anchor_allows": RerouteCase(
        _star2,
        _additive(w_smoke=5.0),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 0.3}),
    ),
    "additive_anchor_refuses": RerouteCase(
        _star2,
        _additive(w_smoke=5.0),
        "spawn",
        "west",
        "west",
        extinction=ArmField({"west": 0.12}),
    ),
    # The old exit is no longer in the graph, so it was never priced.
    "old_exit_unpriced": RerouteCase(_star2, _gate(), "spawn", "west", "gone"),
    # Discovery agent that knows one exit routes inside its map.
    "cognitive_map_known_exit": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "spawn",
        None,
        cognitive_map=lambda: AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"spawn", "east"},
            known_edges={("spawn", "east")},
        ),
    ),
    # Position-aware evaluation from where the agent stands.
    "agent_position_gate": RerouteCase(
        _star2,
        _gate(),
        "spawn",
        "east",
        "east",
        extinction=ArmField({"west": 0.05, "east": 0.12}),
        agent_position=(3.0, 0.0),
    ),
}


def _evaluate(case: RerouteCase) -> dict:
    graph = case.graph()
    wait_info = _wait_info(
        graph,
        case.origin,
        case.target,
        path_choices={k: list(v) for k, v in case.path_choices.items()},
        state=case.state,
    )
    route_state = AgentRouteState(
        current_exit=case.current_exit,
        current_path=list(case.current_path),
        wander_step=case.wander_step,
    )
    cmap = case.cognitive_map() if case.cognitive_map else None
    switch = evaluate_and_reroute(
        agent_id=7,
        wait_info=wait_info,
        route_state=route_state,
        graph=graph,
        current_time_s=case.time_s,
        current_fed=case.current_fed,
        extinction_sampler=case.extinction,
        fed_rate_sampler=case.fed,
        config=RerouteConfig(cost_config=case.config, exit_switch_anchor=case.anchor),
        cached_segments={},
        cognitive_map=cmap,
        agent_position=case.agent_position,
    )
    return {
        "switch": _switch_snapshot(switch),
        "route_state": {
            "current_exit": route_state.current_exit,
            "current_path": list(route_state.current_path),
            "wander_step": route_state.wander_step,
            "last_eval_time_s": _r(route_state.last_eval_time_s),
        },
        "wait_info": {
            "current_origin": wait_info.get("current_origin"),
            "current_target_stage": wait_info.get("current_target_stage"),
            "state": wait_info.get("state"),
            "path_choices": {
                k: [list(v) for v in vs]
                for k, vs in sorted(wait_info.get("path_choices", {}).items())
            },
        },
    }


def _switch_snapshot(switch) -> dict | None:
    if switch is None:
        return None
    return {
        "time_s": _r(switch.time_s),
        "agent_id": switch.agent_id,
        "old_exit": switch.old_exit,
        "new_exit": switch.new_exit,
        "old_cost": _r(switch.old_cost),
        "new_cost": _r(switch.new_cost),
        "reason": switch.reason,
    }


@pytest.mark.parametrize("name", sorted(REROUTE_CASES))
def test_evaluate_and_reroute_matches_golden(name):
    _check_golden(f"evaluate_and_reroute/{name}.json", _evaluate(REROUTE_CASES[name]))


def test_every_switch_reason_is_pinned():
    """The golden set covers every reason ``evaluate_and_reroute`` emits."""
    if REGEN:
        pytest.skip("snapshots are being regenerated")
    reasons: set[str] = set()
    for path in sorted((GOLDEN / "scenarios").glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        reasons.update(row["reason"] for row in data["switches"])
    for path in sorted((GOLDEN / "evaluate_and_reroute").glob("*.json")):
        switch = json.loads(path.read_text(encoding="utf-8"))["switch"]
        if switch is not None:
            reasons.add(switch["reason"])
    expected = {
        "better_path",
        "explore",
        "fallback",
        "initial",
        "smoke_reroute",
        "wander",
    }
    assert expected <= reasons, f"missing reasons: {sorted(expected - reasons)}"


if __name__ == "__main__":
    # Entry point for _run_deck_isolated: run one deck, write its snapshot.
    Path(sys.argv[2]).write_text(
        json.dumps(_run_deck(DECKS[sys.argv[1]]), sort_keys=True), encoding="utf-8"
    )
