"""Differential test for the rerouting refactor of issue #187.

``_legacy_routing`` is a frozen copy of the decision code at 7a3617d. Every
case here runs that copy and the live ``route_graph`` on two independently
built but identical worlds, and requires the results to be exactly equal:

* the ranked ``RouteCost`` lists;
* the ``RouteSwitch``;
* a deep copy of ``wait_info`` and every ``AgentRouteState`` field;
* ``list(cache.items())``, so the order and the first writer of every shared
  segment entry are the same;
* the calls made to the extinction and FED samplers, in order, which is the
  one direct check that segments are evaluated in the same number and order,
  including the uncached first-leg resample and the walked-path evaluation.

No tolerance: stage 1 changes structure only.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from typing import Any

import _legacy_routing as legacy
import pytest
import test_rerouting_golden as golden

from pyfds_evac.core import route_graph as live
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCost,
    RouteCostConfig,
    StageGraph,
)

_SIDES = {"legacy": legacy, "live": live}
_DECISION_FUNCTIONS = (
    "evaluate_route",
    "rank_routes",
    "_must_flee_rejection",
    "_anchor_allows",
    "_adoptable",
    "evaluate_and_reroute",
)


# ── Recording samplers ────────────────────────────────────────────────


@dataclass
class _RecordingExtinction:
    inner: Any
    log: list

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        self.log.append(("k", time_s, x, y))
        return self.inner.sample_extinction(time_s, x, y)


@dataclass
class _RecordingFed:
    inner: Any
    log: list

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        self.log.append(("fed", time_s, x, y))
        return self.inner.sample_fed_rate(time_s, x, y)


def _samplers(extinction, fed) -> tuple[Any, Any, list]:
    log: list = []
    rec_fed = _RecordingFed(fed, log) if fed is not None else None
    return _RecordingExtinction(extinction, log), rec_fed, log


# ── Time-varying fields ───────────────────────────────────────────────


@dataclass(frozen=True)
class _Ramp:
    """Extinction growing linearly in time where ``x >= x_min``."""

    rate: float
    x_min: float
    base: float = 0.0

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        del y
        if x < self.x_min:
            return self.base
        return self.base + self.rate * time_s


@dataclass(frozen=True)
class _FedRamp:
    """A FED rate growing linearly in time where ``y >= y_min``."""

    rate: float
    y_min: float

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        del x
        return self.rate * time_s if y >= self.y_min else 0.0


# ── Configuration variants ────────────────────────────────────────────

_VARIANTS: dict[str, Callable[[RouteCostConfig], RouteCostConfig]] = {
    "as_is": lambda c: c,
    "unknown_mode": lambda c: replace(c, cost_model="weird"),
    "anticipate_flipped": lambda c: replace(c, anticipate=not c.anticipate),
    "clean_tier_on": lambda c: replace(c, clean_extinction_threshold=0.03),
    "clean_tier_off": lambda c: replace(c, clean_extinction_threshold=0.0),
}


# ── rank_routes ───────────────────────────────────────────────────────


def _rank(side: str, case: golden.RankCase, with_cache: bool) -> dict:
    mod = _SIDES[side]
    extinction, fed, log = _samplers(case.extinction, case.fed)
    cache = {} if with_cache else None
    ranked = mod.rank_routes(
        case.graph(),
        case.source,
        case.time_s,
        case.current_fed,
        extinction,
        fed,
        case.config,
        cached_segments=cache,
        exit_counts=copy.deepcopy(case.exit_counts),
        cognitive_map=case.cognitive_map() if case.cognitive_map else None,
        agent_position=case.agent_position,
        current_exit=case.current_exit,
    )
    return {
        "ranked": ranked,
        "cache": None if cache is None else list(cache.items()),
        "log": log,
    }


def _assert_rank_equal(case: golden.RankCase) -> None:
    for with_cache in (False, True):
        old = _rank("legacy", case, with_cache)
        new = _rank("live", case, with_cache)
        assert new["ranked"] == old["ranked"]
        assert new["cache"] == old["cache"]
        assert new["log"] == old["log"]


def _star2() -> StageGraph:
    return golden._star({"west": 20.0, "east": 40.0})


_EXTRA_RANK_CASES: dict[str, golden.RankCase] = {
    # The current exit is not among the ranked routes.
    "gate_current_exit_absent": golden.RankCase(
        _star2, golden._gate(), golden.ArmField({"west": 0.2}), current_exit="gone"
    ),
    "gate_fallback_current_absent": golden.RankCase(
        _star2,
        golden._gate(),
        golden.ArmField({"west": 0.5, "east": 0.5}),
        current_exit="gone",
    ),
    # Additive: a route refused on sight, with every other route FED-refused.
    "additive_kvis_triggers_fallback": golden.RankCase(
        _star2,
        golden._additive(),
        golden.ArmField({"west": 0.8}),
        fed=golden.ArmFed({"east": 4.0}),
        current_fed=0.2,
    ),
    # A field that changes in time, so anticipation matters.
    "gate_ramp_anticipated": golden.RankCase(
        golden._linear, golden._gate(), _Ramp(0.01, 11.0), source="D0", time_s=30.3
    ),
    "additive_ramp_fed": golden.RankCase(
        golden._linear,
        golden._additive(),
        _Ramp(0.01, 11.0),
        fed=_FedRamp(0.02, -5.0),
        source="D0",
        time_s=30.3,
    ),
}

_ALL_RANK_CASES = {**golden.RANK_CASES, **_EXTRA_RANK_CASES}


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
@pytest.mark.parametrize("name", sorted(_ALL_RANK_CASES))
def test_rank_routes_equivalent(name, variant):
    case = _ALL_RANK_CASES[name]
    _assert_rank_equal(replace(case, config=_VARIANTS[variant](case.config)))


# ── evaluate_and_reroute ──────────────────────────────────────────────


def _reroute_world(case: golden.RerouteCase) -> dict:
    graph = case.graph()
    return {
        "graph": graph,
        "wait_info": golden._wait_info(
            graph,
            case.origin,
            case.target,
            path_choices={k: list(v) for k, v in case.path_choices.items()},
            state=case.state,
        ),
        "route_state": AgentRouteState(
            current_exit=case.current_exit,
            current_path=list(case.current_path),
            wander_step=case.wander_step,
        ),
        "cmap": case.cognitive_map() if case.cognitive_map else None,
    }


def _state_fields(route_state: AgentRouteState) -> dict:
    return {
        f.name: copy.deepcopy(getattr(route_state, f.name)) for f in fields(route_state)
    }


def _reroute(side: str, case: golden.RerouteCase, with_cache: bool) -> dict:
    mod = _SIDES[side]
    world = _reroute_world(case)
    extinction, fed, log = _samplers(case.extinction, case.fed)
    cache = {} if with_cache else None
    switch = mod.evaluate_and_reroute(
        agent_id=7,
        wait_info=world["wait_info"],
        route_state=world["route_state"],
        graph=world["graph"],
        current_time_s=case.time_s,
        current_fed=case.current_fed,
        extinction_sampler=extinction,
        fed_rate_sampler=fed,
        config=RerouteConfig(cost_config=case.config, exit_switch_anchor=case.anchor),
        cached_segments=cache,
        cognitive_map=world["cmap"],
        agent_position=case.agent_position,
    )
    return {
        "switch": switch,
        "wait_info": copy.deepcopy(world["wait_info"]),
        "route_state": _state_fields(world["route_state"]),
        "cache": None if cache is None else list(cache.items()),
        "log": log,
    }


def _assert_reroute_equal(case: golden.RerouteCase) -> None:
    for with_cache in (False, True):
        old = _reroute("legacy", case, with_cache)
        new = _reroute("live", case, with_cache)
        assert new["switch"] == old["switch"]
        assert new["route_state"] == old["route_state"]
        assert new["wait_info"] == old["wait_info"]
        assert new["cache"] == old["cache"]
        assert new["log"] == old["log"]


_EXTRA_REROUTE_CASES: dict[str, golden.RerouteCase] = {
    # A route that is both FED-lethal and over tau: the tau reason wins and
    # the must-flee bypass is lost (#128, kept in stage 1).
    "gate_fed_and_tau_current": golden.RerouteCase(
        _star2,
        golden._gate(),
        "spawn",
        "west",
        "west",
        extinction=golden.ArmField({"west": 0.5}),
        fed=golden.ArmFed({"west": 4.0}),
        current_fed=0.2,
    ),
    # All routes refused and the current exit kept by the fallback margin.
    "gate_fallback_hold": golden.RerouteCase(
        _star2,
        golden._gate(),
        "spawn",
        "east",
        "east",
        extinction=golden.ArmField({"west": 0.5, "east": 0.5}),
    ),
    # Additive: the K_vis screen refuses the current exit; mild smoke.
    "additive_kvis_current": golden.RerouteCase(
        _star2,
        golden._additive(),
        "spawn",
        "east",
        "west",
        extinction=golden.ArmField({"west": 0.8}),
    ),
    # A walking agent and an idle one on a time-varying field.
    "gate_ramp_walking": golden.RerouteCase(
        golden._diamond,
        golden._gate(),
        "D0",
        "C1",
        "E0",
        current_path=("D0", "C1", "E0"),
        path_choices=golden._choices("D0", "C1", "E0"),
        extinction=_Ramp(0.005, 5.0),
        fed=_FedRamp(0.01, 15.0),
        time_s=30.3,
        agent_position=(0.5, 8.0),
    ),
    "gate_ramp_idle": golden.RerouteCase(
        golden._diamond,
        golden._gate(),
        "D0",
        "C0",
        "E0",
        state="idle",
        extinction=_Ramp(0.005, 5.0),
        time_s=30.3,
    ),
    "wander_second_step": golden.RerouteCase(
        golden._linear,
        golden._gate(),
        "C0",
        "C0",
        None,
        state="idle",
        current_path=("C0", "D0"),
        wander_step=1,
        cognitive_map=golden._exhausted_map,
    ),
}

_ALL_REROUTE_CASES = {**golden.REROUTE_CASES, **_EXTRA_REROUTE_CASES}


@pytest.mark.parametrize("variant", sorted(_VARIANTS))
@pytest.mark.parametrize("name", sorted(_ALL_REROUTE_CASES))
def test_evaluate_and_reroute_equivalent(name, variant):
    case = _ALL_REROUTE_CASES[name]
    _assert_reroute_equal(replace(case, config=_VARIANTS[variant](case.config)))


# ── Several agents sharing one cache, as in run_scenario ─────────────


def _merge_graph() -> StageGraph:
    """Three sources whose first legs to M differ by fractions of a metre.

    With anticipation, two agents reach M -> E0 inside the same whole second
    at different exact times, so the first one to evaluate it fixes the cache
    entry the other reads.
    """
    return golden._graph(
        {
            "S1": (9.9, 0.0, "checkpoint"),
            "S2": (20.0, -10.3, "checkpoint"),
            "M": (20.0, 0.0, "checkpoint"),
            "E0": (30.0, 0.0, "exit"),
            "E1": (20.0, 15.0, "exit"),
            "E2": (0.0, -25.0, "exit"),
        },
        golden._edges(
            ("D0", "M"),
            ("S1", "M"),
            ("S2", "M"),
            ("M", "E0"),
            ("M", "E1"),
            ("D0", "E2"),
        ),
    )


@dataclass(frozen=True)
class _Agent:
    agent_id: int
    origin: str
    target: str
    current_exit: str | None
    path: tuple[str, ...] = ()
    state: str = "to_target"
    position: tuple[float, float] | None = None
    current_fed: float = 0.0


_PASS_AGENTS = (
    _Agent(1, "D0", "D0", None),
    _Agent(2, "S1", "M", "E0", ("S1", "M", "E0"), position=(12.0, 0.0)),
    _Agent(3, "S2", "M", "E1", ("S2", "M", "E1"), position=(20.0, -7.0)),
    _Agent(4, "D0", "D0", "E2", state="idle", current_fed=0.3),
    _Agent(5, "S1", "M", "E1", ("S1", "M", "E1"), position=(15.0, 0.0)),
)


@dataclass(frozen=True)
class _Pass:
    config: RouteCostConfig
    history: bool
    times: tuple[float, ...] = (30.0, 31.1, 45.0)
    extinction: Any = field(default_factory=lambda: _Ramp(0.004, 19.0, base=0.01))
    fed: Any = field(default_factory=lambda: _FedRamp(0.03, 5.0))
    anchor: float = 0.9


def _run_passes(side: str, spec: _Pass) -> list:
    mod = _SIDES[side]
    graph = _merge_graph()
    extinction, fed, log = _samplers(spec.extinction, spec.fed)
    config = RerouteConfig(cost_config=spec.config, exit_switch_anchor=spec.anchor)
    agents = {}
    for a in _PASS_AGENTS:
        agents[a.agent_id] = (
            golden._wait_info(
                graph,
                a.origin,
                a.target,
                path_choices=golden._choices(*a.path) if a.path else None,
                state=a.state,
            ),
            AgentRouteState(current_exit=a.current_exit, current_path=list(a.path)),
        )
    exit_counts = {"E0": 3, "E1": 1, "E2": 0}
    trace = []
    for time_s in spec.times:
        cache: dict = {}
        for a in _PASS_AGENTS:
            wait_info, rs = agents[a.agent_id]
            if spec.history:
                source = wait_info.get("current_origin") or wait_info.get(
                    "current_target_stage"
                )
                if source is not None and source in graph.nodes:
                    trace.append(
                        mod.rank_routes(
                            graph,
                            source,
                            time_s,
                            a.current_fed,
                            extinction,
                            fed,
                            spec.config,
                            cached_segments=cache,
                            exit_counts=exit_counts,
                            cognitive_map=None,
                            agent_position=a.position,
                            current_exit=rs.current_exit or None,
                            current_target=wait_info.get("current_target_stage"),
                        )
                    )
            switch = mod.evaluate_and_reroute(
                a.agent_id,
                wait_info,
                rs,
                graph,
                time_s,
                a.current_fed,
                extinction,
                fed,
                config,
                cache,
                exit_counts=exit_counts,
                cognitive_map=None,
                agent_position=a.position,
            )
            if switch is not None and switch.old_exit != switch.new_exit:
                if switch.old_exit in exit_counts:
                    exit_counts[switch.old_exit] -= 1
                exit_counts[switch.new_exit] = exit_counts.get(switch.new_exit, 0) + 1
            trace.append(switch)
            trace.append(copy.deepcopy(wait_info))
            trace.append(_state_fields(rs))
        trace.append(list(cache.items()))
        trace.append(dict(exit_counts))
    trace.append(log)
    return trace


_PASS_CONFIGS = {
    "gate": golden._gate(),
    "gate_clean": golden._gate(clean_extinction_threshold=0.05),
    "gate_no_anticipate": golden._gate(anticipate=False),
    "gate_queue": golden._gate(w_queue=0.5),
    "additive": golden._additive(w_queue=0.5),
    "unknown_mode": golden._gate(cost_model="weird"),
}


def test_shared_cache_is_order_sensitive():
    """The pass field really makes the first writer of a cache key matter."""
    graph = _merge_graph()
    config = golden._gate()
    field_ = _Ramp(0.004, 19.0, base=0.01)
    for time_s in _Pass(config, False).times:
        caches = ({}, {})
        for cache, path in zip(caches, (["S1", "M", "E0"], ["S2", "M", "E0"])):
            live.evaluate_route(
                graph, path, time_s, 0.0, field_, None, config, cached_segments=cache
            )
        shared = [key for key in caches[0] if key in caches[1]]
        assert shared
        assert all(caches[0][key] != caches[1][key] for key in shared)


@pytest.mark.parametrize("history", [False, True], ids=["no_history", "history"])
@pytest.mark.parametrize("name", sorted(_PASS_CONFIGS))
def test_shared_cache_passes_equivalent(name, history):
    spec = _Pass(_PASS_CONFIGS[name], history)
    assert _run_passes("live", spec) == _run_passes("legacy", spec)


# ── Exact threshold equality ──────────────────────────────────────────


def _west(config: RouteCostConfig, extinction, fed=None, current_fed=0.0):
    ranked = live.rank_routes(
        _star2(), "spawn", 0.0, current_fed, extinction, fed, config
    )
    return next(rc for rc in ranked if rc.exit_id == "west")


def _around(value: float) -> list[float]:
    return [
        math.nextafter(value, -math.inf),
        value,
        math.nextafter(value, math.inf),
    ]


_SMOKE = golden.ArmField({"west": 0.2, "east": 0.25})
_DOSE = golden.ArmFed({"west": 2.5, "east": 3.0})


def _limit_cases() -> list[tuple[str, golden.RankCase]]:
    cases = []
    tau = _west(golden._gate(), _SMOKE).tau_route
    for i, limit in enumerate(_around(tau)):
        for current in (None, "west"):
            cases.append(
                (
                    f"tau_max[{i}]-{current}",
                    golden.RankCase(
                        _star2,
                        golden._gate(tau_max=limit),
                        _SMOKE,
                        current_exit=current,
                    ),
                )
            )
    for model in (golden._gate, golden._additive):
        fed_max = _west(model(), _SMOKE, _DOSE, 0.1).fed_max_route
        for i, limit in enumerate(_around(fed_max)):
            for current in (None, "west"):
                cases.append(
                    (
                        f"fed[{i}]-{model.__name__}-{current}",
                        golden.RankCase(
                            _star2,
                            model(fed_rejection_threshold=limit),
                            _SMOKE,
                            fed=_DOSE,
                            current_fed=0.1,
                            current_exit=current,
                        ),
                    )
                )
    k_leg = _west(golden._gate(), _SMOKE).k_leg_max
    for i, limit in enumerate(_around(k_leg)):
        cases.append(
            (
                f"clean[{i}]",
                golden.RankCase(
                    _star2, golden._gate(clean_extinction_threshold=limit), _SMOKE
                ),
            )
        )
    # Fallback: the rival's worst stretch exactly at the margin keeps nothing.
    margin = 1.0 - golden._gate().fallback_switch_margin
    for i, rival in enumerate(_around(0.5 * margin)):
        cases.append(
            (
                f"fallback[{i}]",
                golden.RankCase(
                    _star2,
                    golden._gate(),
                    golden.ArmField({"west": rival, "east": 0.5}),
                    current_exit="east",
                ),
            )
        )
    return cases + _margin_limit_cases()


def _scaled_limit(target: float, factor: float, divide: bool = False) -> float | None:
    """A threshold that, times *factor* (or divided by it), is exactly *target*.

    Searched over a few ulps around the naive quotient, since the code
    multiplies (or divides) and the product has to land on *target* exactly.
    """
    guess = target * factor if divide else target / factor
    candidates = [guess]
    for direction in (-math.inf, math.inf):
        value = guess
        for _ in range(8):
            value = math.nextafter(value, direction)
            candidates.append(value)
    for value in candidates:
        if (value / factor if divide else value * factor) == target:
            return value
    return None


# The limits a rival exit is held to, and the clean limit of the current exit.
# Each case names (config field, margin field, margin, current exit, measure).
_MARGIN_LIMITS = (
    ("fed_rejection_threshold", "fed_return_margin", "east", "fed_max_route"),
    ("tau_max", "tau_return_margin", "east", "tau_route"),
    ("clean_extinction_threshold", "clean_exit_margin", "west", "k_leg_max"),
)


def _margin_config(model, field_name: str, margin_name: str, margin, limit):
    return model(**{field_name: limit, margin_name: margin})


def _margin_limit_cases() -> list[tuple[str, golden.RankCase]]:
    """Rival-adjusted FED and tau limits, and the current exit's clean limit.

    ``current_exit`` is set, so the margin applies to the measured route; the
    threshold is chosen so the adjusted limit lands exactly on the measured
    value, one ulp below it and one above.
    """
    cases = []
    for field_name, margin_name, current, measure in _MARGIN_LIMITS:
        default = getattr(RouteCostConfig(), margin_name)
        divide = margin_name == "clean_exit_margin"
        models = (golden._gate, golden._additive)
        if field_name == "tau_max":
            models = (golden._gate,)
        for model in models:
            for margin in (0.5, default):
                probe = _margin_config(model, field_name, margin_name, margin, 1.0)
                measured = getattr(_west(probe, _SMOKE, _DOSE, 0.1), measure)
                for i, target in enumerate(_around(measured)):
                    limit = _scaled_limit(target, margin, divide)
                    if limit is None:
                        continue
                    config = _margin_config(
                        model, field_name, margin_name, margin, limit
                    )
                    for exit_ in (current, None):
                        cases.append(
                            (
                                f"{field_name}-{model.__name__}-{margin}[{i}]-{exit_}",
                                golden.RankCase(
                                    _star2,
                                    config,
                                    _SMOKE,
                                    fed=_DOSE,
                                    current_fed=0.1,
                                    current_exit=exit_,
                                ),
                            )
                        )
    return cases


_LIMIT_CASES = dict(_limit_cases())


def test_margin_limits_are_hit_exactly():
    """With margin 0.5 every adjusted limit lands on the measured value."""
    for field_name, margin_name, current, measure in _MARGIN_LIMITS:
        divide = margin_name == "clean_exit_margin"
        probe = _margin_config(golden._gate, field_name, margin_name, 0.5, 1.0)
        measured = getattr(_west(probe, _SMOKE, _DOSE, 0.1), measure)
        below, exact, _ = (_scaled_limit(t, 0.5, divide) for t in _around(measured))
        assert below is not None and exact is not None
        ranked = {
            limit: next(
                rc
                for rc in live.rank_routes(
                    _star2(),
                    "spawn",
                    0.0,
                    0.1,
                    _SMOKE,
                    _DOSE,
                    _margin_config(golden._gate, field_name, margin_name, 0.5, limit),
                    current_exit=current,
                )
                if rc.exit_id == "west"
            )
            for limit in (below, exact)
        }
        if field_name == "clean_extinction_threshold":
            assert not ranked[below].clean and ranked[exact].clean
        else:
            prefix = "FED" if field_name.startswith("fed") else "tau"
            reasons = [ranked[limit].rejection_reason or "" for limit in (below, exact)]
            assert prefix in reasons[0] and prefix not in reasons[1], reasons


@pytest.mark.parametrize("name", sorted(_LIMIT_CASES))
def test_threshold_equality_rank_equivalent(name):
    _assert_rank_equal(_LIMIT_CASES[name])


def test_fallback_boundary_is_hit():
    """At the exact margin the rival wins; one ulp above, the current holds."""
    margin = 1.0 - golden._gate().fallback_switch_margin
    _, exact, above = _around(0.5 * margin)
    for rival, winner in ((exact, "west"), (above, "east")):
        ranked = live.rank_routes(
            _star2(),
            "spawn",
            0.0,
            0.0,
            golden.ArmField({"west": rival, "east": 0.5}),
            None,
            golden._gate(),
            current_exit="east",
        )
        west = next(rc for rc in ranked if rc.exit_id == "west")
        assert west.k_max_route == rival
        assert ranked[0].exit_id == winner
        assert ranked[0].rejection_reason.startswith("fallback: ")


def _rc(exit_id: str, **kw) -> RouteCost:
    base = dict(
        exit_id=exit_id,
        path=["spawn", exit_id],
        path_length_m=10.0,
        k_ave_route=0.1,
        travel_time_s=10.0,
        fed_max_route=0.0,
        composite_cost=10.0,
        segments=[],
        rejected=False,
        rejection_reason=None,
    )
    base.update(kw)
    return RouteCost(**base)


def _anchor_cases() -> list[tuple[str, RouteCost, RouteCost | None, RerouteConfig]]:
    out = []
    for model in ("gate", "additive", "weird"):
        cc = replace(golden._gate(), cost_model=model)
        cfg = RerouteConfig(cost_config=cc, exit_switch_anchor=0.9)
        out.append((f"{model}-no_baseline", _rc("a"), None, cfg))
        for i, cost in enumerate(_around(10.0 * 0.9)):
            out.append(
                (
                    f"{model}-ratio[{i}]",
                    _rc("a", rank_cost=cost),
                    _rc("b", rank_cost=10.0),
                    cfg,
                )
            )
        deadband = cc.tau_max * cc.tau_deadband
        for i, old_tau in enumerate(_around(deadband)):
            for cost in (5.0, 9.5):
                out.append(
                    (
                        f"{model}-deadband[{i}]-{cost}",
                        _rc("a", tau_route=0.0, rank_cost=cost),
                        _rc("b", tau_route=old_tau, rank_cost=10.0),
                        cfg,
                    )
                )
            out.append(
                (
                    f"{model}-dirtier[{i}]",
                    _rc("a", tau_route=old_tau, rank_cost=5.0),
                    _rc("b", tau_route=0.0, rank_cost=10.0),
                    cfg,
                )
            )
        out.append(
            (
                f"{model}-clean_over_dirty",
                _rc("a", clean=True, rank_cost=20.0),
                _rc("b", clean=False, rank_cost=10.0),
                cfg,
            )
        )
        out.append(
            (
                f"{model}-infeasible_candidate",
                _rc("a", feasible=False, tau_route=0.0, rank_cost=5.0),
                _rc("b", tau_route=5.0, rank_cost=10.0),
                cfg,
            )
        )
        limit = cc.impassable_extinction_threshold
        for i, k in enumerate(_around(limit)):
            for reason in (
                "all segments non-visible",
                "fallback: all segments non-visible",
                "FED_max 1.2 > 1.0",
                "fallback: FED_max 1.2 > 1.0",
                "tau 7.00 > 6.00 (K_ave 0.300 x 23.3 m)",
            ):
                for rejected in (False, True):
                    out.append(
                        (
                            f"{model}-flee[{i}]-{reason}-{rejected}",
                            _rc("a", rank_cost=20.0, tau_route=3.0),
                            _rc(
                                "b",
                                rank_cost=10.0,
                                k_ave_route=k,
                                rejected=rejected,
                                rejection_reason=reason,
                            ),
                            cfg,
                        )
                    )
    return out


_ANCHOR_CASES = {name: rest for name, *rest in _anchor_cases()}


@pytest.mark.parametrize("name", sorted(_ANCHOR_CASES))
def test_anchor_and_flee_equivalent(name):
    candidate, old_rc, cfg = _ANCHOR_CASES[name]
    assert live._anchor_allows(candidate, old_rc, cfg) == legacy._anchor_allows(
        candidate, old_rc, cfg
    )
    if old_rc is not None:
        assert live._must_flee_rejection(
            old_rc, cfg.cost_config
        ) == legacy._must_flee_rejection(old_rc, cfg.cost_config)
    ranked = [candidate] + ([old_rc] if old_rc is not None else [])
    for current in (None, candidate.exit_id, "b", "gone"):
        rs = AgentRouteState(current_exit=current)
        assert live._adoptable(candidate, ranked, rs, cfg) == legacy._adoptable(
            candidate, ranked, rs, cfg
        )


# ── The harness compares legacy with live, not live with itself ──────


def test_legacy_copy_binds_to_itself():
    for name in _DECISION_FUNCTIONS:
        fn = getattr(legacy, name)
        assert fn is not getattr(live, name), name
        assert fn.__module__ == legacy.__name__, name
        for other in _DECISION_FUNCTIONS:
            if other in fn.__code__.co_names:
                assert fn.__globals__[other] is getattr(legacy, other), (name, other)
    assert legacy.evaluate_and_reroute.__globals__["rank_routes"] is legacy.rank_routes
