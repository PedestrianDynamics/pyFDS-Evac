"""D -- the extinction a walker meets is sampled at its live position.

Every uniform-field test is position-blind. Here K varies along a 30 m
corridor, ``K(x) = 0.2 x`` (treatment), ``K(x) = 6 - 0.2 x`` (mirrored) or
``0`` (control), and the agent's *true* position is recorded by wrapping
``jps.Simulation.iterate`` just before each step. Comparing the logged K with
the logged ``x`` would be circular, so the expected K and Lund factor are
computed from the recorded position at the same instant.

Aggregate tolerance and the aggregate-only rule follow
``test_s2_corridor_speed.py`` (ratio ``rel=0.08``, README rule 3): per-agent
trajectories are not reproducible, so only the history rows, trends and
egress times are asserted.
"""

from __future__ import annotations

import jupedsim as jps
import pytest
from harness import (
    CorridorSpec,
    corridor_scenario,
    lund_speed_factor,
    make_smoke_model,
    ramp_x,
    uniform,
)

from pyfds_evac.core.scenario import run_scenario

SLOPE = 0.2  # 1/m per m; K = 0.2 .. 5.8 over 29 m
V0 = 1.2
SPEC = CorridorSpec(
    length_m=30.0, width_m=4.0, num_agents=5, v0=V0, seed=42, max_simulation_time=120.0
)
# Back-step allowance between consecutive 1 s rows: an agent in a crowd can be
# nudged backwards (engineering allowance, not a model constant). Observed in
# 16 runs (seeds 1-7 and 42, treatment and mirrored arms): no agent moved
# backwards between rows at all (largest back-step 0.0 m), so the 0.3 m
# allowance has a margin of 0.3 m.
BACKSTEP_M = 0.3
MIN_PROGRESS_M = 10.0
ARMS = {
    "treatment": (ramp_x(SLOPE), lambda x: SLOPE * x),
    "mirrored": (ramp_x(-SLOPE, intercept=6.0), lambda x: 6.0 - SLOPE * x),
    "control": (uniform(0.0), lambda x: 0.0),
    "null_ramp": (ramp_x(0.0), lambda x: 0.0),
}


@pytest.fixture
def positions(monkeypatch):
    """Each agent's true (time, x, y), recorded before every JuPedSim step."""
    rows: dict[int, list[tuple[float, float, float]]] = {}

    class RecordingSimulation(jps.Simulation):
        def iterate(self, count: int = 1):
            t = self.elapsed_time()
            for agent in self.agents():
                pos = agent.position
                rows.setdefault(int(agent.id), []).append((t, pos[0], pos[1]))
            return super().iterate(count)

    monkeypatch.setattr(jps, "Simulation", RecordingSimulation)
    return rows


def _run(arm: str):
    field, _ = ARMS[arm]
    return run_scenario(
        corridor_scenario(SPEC),
        seed=SPEC.seed,
        smoke_speed_model=make_smoke_model(field, speed_law="lund"),
    )


def _true_position(track, time_s):
    """The recorded (x, y) at the step closest to ``time_s``, and its gap."""
    t, x, y = min(track, key=lambda r: abs(r[0] - time_s))
    return x, y, abs(t - time_s)


def _per_agent_rows(result):
    by_agent: dict[int, list[dict]] = {}
    for row in result.smoke_history:
        by_agent.setdefault(row["agent_id"], []).append(row)
    for rows in by_agent.values():
        rows.sort(key=lambda r: r["time_s"])
    return by_agent


def _assert_sampled_at_the_true_position(result, positions, k_of_x):
    assert result.smoke_history, "smoke model produced no history rows"
    for row in result.smoke_history:
        x, y, gap = _true_position(positions[row["agent_id"]], row["time_s"])
        assert gap < 1e-6
        assert row["x"] == pytest.approx(x, abs=1e-6)
        assert row["y"] == pytest.approx(y, abs=1e-6)
        assert row["extinction_per_m"] == pytest.approx(k_of_x(x), abs=1e-9)
        assert row["speed_factor"] == pytest.approx(
            lund_speed_factor(k_of_x(x)), rel=1e-9
        )


def _assert_trend(result, direction):
    """K moved by >= 0.2 * 10 along the walk, in ``direction`` (+1 or -1)."""
    for rows in _per_agent_rows(result).values():
        first, last = rows[0], rows[-1]
        delta_k = direction * (last["extinction_per_m"] - first["extinction_per_m"])
        assert delta_k >= SLOPE * MIN_PROGRESS_M
        delta_f = direction * (last["speed_factor"] - first["speed_factor"])
        assert delta_f * -1 >= 0.2  # factor falls where K rises
        # Per agent, in x order, K and the factor are monotone exactly.
        by_x = sorted(rows, key=lambda r: r["x"])
        for a, b in zip(by_x, by_x[1:], strict=False):
            assert direction * (b["extinction_per_m"] - a["extinction_per_m"]) >= -1e-12
            assert direction * (b["speed_factor"] - a["speed_factor"]) <= 1e-12
        # In time, K does not run backwards by more than the allowance.
        for a, b in zip(rows, rows[1:], strict=False):
            step = direction * (b["extinction_per_m"] - a["extinction_per_m"])
            assert step >= -SLOPE * BACKSTEP_M


def test_treatment_samples_k_at_the_live_position(positions):
    result = _run("treatment")
    try:
        _assert_sampled_at_the_true_position(result, positions, ARMS["treatment"][1])
        _assert_trend(result, +1)
    finally:
        result.cleanup()


def test_mirrored_ramp_reverses_the_trend(positions):
    """K falls along the walk: a fixed-coordinate or swapped sampler cannot pass."""
    result = _run("mirrored")
    try:
        _assert_sampled_at_the_true_position(result, positions, ARMS["mirrored"][1])
        _assert_trend(result, -1)
    finally:
        result.cleanup()


@pytest.mark.parametrize("arm", ["control", "null_ramp"])
def test_zero_field_arms_apply_no_slowdown(positions, arm):
    result = _run(arm)
    try:
        _assert_sampled_at_the_true_position(result, positions, ARMS[arm][1])
        for row in result.smoke_history:
            assert row["extinction_per_m"] == 0.0
            assert row["speed_factor"] == pytest.approx(1.0, rel=1e-9)
    finally:
        result.cleanup()


def test_gradient_egress_lies_between_free_walk_and_the_slowest_bound():
    """Aggregate: free < gradient < every metre walked at the end-of-corridor speed."""
    control = _run("control")
    treatment = _run("treatment")
    try:
        assert control.metrics["agents_remaining"] == 0
        assert treatment.metrics["agents_remaining"] == 0
        free_s = control.metrics["evacuation_time"]
        gradient_s = treatment.metrics["evacuation_time"]
        # Everyone walks at least the last 26 m (spawn x <= ~4, exit x >= 29)
        # at no better than f(K(29)); the all-slow bound uses the whole 30 m.
        slowest_s = SPEC.length_m / (V0 * lund_speed_factor(SLOPE * 29.0))
        assert free_s < gradient_s < slowest_s
    finally:
        control.cleanup()
        treatment.cleanup()
