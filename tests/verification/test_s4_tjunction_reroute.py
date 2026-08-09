"""S4 -- T-junction rerouting: does smoke cost steer agents off the smoky route.

A T-junction with the stem offset so the **right** exit is nearer and is the
default choice.  Localised smoke in the right arm raises that route's cost above
the longer-but-clear left route, and dynamic rerouting must switch agents from
the right exit to the left one.

Arms:

- **control** (no smoke): low density keeps both exits uncongested, so nobody
  reroutes -- ``route_switches == 0``.
- **null-field control** (smoke model present, ``K = 0``): exercises the same
  route-cost-with-extinction wiring with a null field; still no switches.
- **treatment** (smoke in the right arm): most agents switch from the right
  (smoky) exit to the left (clear) one, and never the reverse.

The smoke starts at ``smoke_onset_s``, once the whole population is inside and
still walking. That delay is what makes this a test of *re*-routing: the opening
exit choice is itself ranked on the smoke field, so an agent spawning into smoke
that is already there simply never picks the smoky route and has nothing to
switch away from.

Assertions are aggregate (counts, directions, earliest-switch latency), never
per-agent or trajectory-level -- the coupled run is not bit-reproducible (see
project memory).

Engine note: rerouting only engages on the **flow-spawning** agent-init path;
``t_junction_scenario`` uses it (a by-number population leaves agents out of
route evaluation entirely -- a verified limitation worth its own bug report).
"""

from __future__ import annotations

import pytest
from harness import (
    EXIT_LEFT,
    EXIT_RIGHT,
    TJunctionSpec,
    after,
    make_smoke_model,
    region_x,
    route_switch_count,
    route_switch_directions,
    t_junction_scenario,
    uniform,
)

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import run_scenario

REEVAL_INTERVAL_S = 5.0
# Right-arm extinction: enough that the short smoky route costs more than the
# long clear one (w_smoke = 5 amplifies it in the composite cost).
SMOKE_K = 6.0


def _reroute_config() -> RerouteConfig:
    return RerouteConfig(
        reevaluation_interval_s=REEVAL_INTERVAL_S,
        # w_queue = 0: S4 isolates the *smoke* term. The population now enters
        # over a short window so that everyone is inside before the fire starts,
        # and at that density the queue term alone would shuffle agents between
        # exits -- real behaviour, but not what this scenario is measuring.
        cost_config=RouteCostConfig(w_smoke=5.0, w_fed=10.0, w_queue=0.0),
    )


def _right_arm_smoke(spec: TJunctionSpec):
    return make_smoke_model(
        after(spec.smoke_onset_s, region_x(SMOKE_K, x_min=spec.right_arm_x_min))
    )


def test_control_no_smoke_no_reroute():
    """Uncongested, no smoke: agents keep the near exit, nobody reroutes."""
    spec = TJunctionSpec(seed=42)
    result = run_scenario(
        t_junction_scenario(spec), seed=spec.seed, reroute_config=_reroute_config()
    )
    try:
        assert route_switch_count(result) == 0
        assert result.metrics["agents_remaining"] == 0  # both arms open
    finally:
        result.cleanup()


def test_null_field_control_no_reroute():
    """Behavioral F0: smoke model present but K = 0 -> no cost change, no switch.

    Drives the route-cost-with-extinction sampling with a null field, so a bug
    that perturbs route cost in clear air would show up as spurious switches.
    """
    spec = TJunctionSpec(seed=42)
    result = run_scenario(
        t_junction_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(uniform(0.0)),
        reroute_config=_reroute_config(),
    )
    try:
        assert route_switch_count(result) == 0
    finally:
        result.cleanup()


def test_smoke_forces_switch_to_clear_exit():
    """Smoke in the near arm reroutes agents to the far clear exit -- only that way."""
    spec = TJunctionSpec(seed=42)
    result = run_scenario(
        t_junction_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=_right_arm_smoke(spec),
        reroute_config=_reroute_config(),
    )
    try:
        directions = route_switch_directions(result)
        # Every reroute goes smoky-right -> clear-left; none the other way.
        assert directions == {(EXIT_RIGHT, EXIT_LEFT): route_switch_count(result)}
        # A clear majority of the population actually reroutes (vs control's 0).
        assert route_switch_count(result) >= spec.num_agents // 2
        assert result.metrics["agents_remaining"] == 0
    finally:
        result.cleanup()


def test_reroute_latency_within_interval():
    """Every reroute lands within one interval of smoke onset (B5.2).

    Everyone is inside and walking before the smoke appears at ``smoke_onset_s``,
    so that is the instant the smoky cost becomes visible and each agent must
    reroute by its next reevaluation.  The *last* reroute must therefore occur
    within one interval of onset -- bounding the maximum, not just the minimum
    (a check on ``min`` would pass even if latency blew up, since staggered eval
    offsets guarantee some agent always switches early).
    """
    spec = TJunctionSpec(seed=42)
    result = run_scenario(
        t_junction_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=_right_arm_smoke(spec),
        reroute_config=_reroute_config(),
    )
    try:
        times = [s["time_s"] for s in result.route_history or []]
        assert times, "expected at least one reroute"
        assert max(times) <= spec.smoke_onset_s + REEVAL_INTERVAL_S
    finally:
        result.cleanup()


@pytest.mark.slow
def test_switch_outcome_stable_under_fixed_seed():
    """Same seed -> same qualitative outcome: majority switch, all right->left.

    Not the same *count*. The reroute now happens mid-walk rather than at spawn,
    and by then agents have jostled each other into positions that vary run to
    run, so which of them crosses the cost threshold on which evaluation tick
    varies too. Coupled runs are not bit-reproducible under a fixed seed (see
    project memory); the invariant that holds is the direction and the majority.
    """
    spec = TJunctionSpec(seed=42)

    def _outcome():
        result = run_scenario(
            t_junction_scenario(spec),
            seed=spec.seed,
            smoke_speed_model=_right_arm_smoke(spec),
            reroute_config=_reroute_config(),
        )
        try:
            return route_switch_count(result), set(route_switch_directions(result))
        finally:
            result.cleanup()

    first_count, first_dirs = _outcome()
    second_count, second_dirs = _outcome()
    assert first_dirs == second_dirs == {(EXIT_RIGHT, EXIT_LEFT)}
    assert min(first_count, second_count) >= spec.num_agents // 2
