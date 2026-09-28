"""Pin the speed each agent enters every JuPedSim step with (#240).

The unit tests in ``tests/test_speed_update_pin.py`` pin
``update_checkpoint_speed``; these pin its two call sites in
``run_scenario``, so a skip added in the run loop is caught as well.

``jps.Simulation.iterate`` is wrapped to record every agent's position and
``desired_speed`` just before each step. At that point the speed must equal
the closed form ``v0 * zone(x, y) * smoke(t) * fic(t)``, where ``smoke`` and
``fic`` are the factors last logged for that agent. The check is exact per
step and position, so it does not depend on trajectory noise.
"""

from __future__ import annotations

import jupedsim as jps
import pytest
from harness import (
    CorridorSpec,
    after,
    corridor_scenario,
    make_fed_model,
    make_smoke_model,
    uniform,
)

from pyfds_evac.core.fed import TenabilityConfig
from pyfds_evac.core.scenario import run_scenario

V0 = 1.2
# Two overlapping slow zones: in 12 <= x <= 15 the 0.5 zone wins over 0.8.
ZONES = {
    "slow_a": (10.0, 15.0, 0.5),
    "slow_b": (12.0, 20.0, 0.8),
}


def _spec() -> CorridorSpec:
    return CorridorSpec(
        length_m=30.0,
        width_m=4.0,
        num_agents=6,
        v0=V0,
        seed=7,
        max_simulation_time=60.0,
    )


PREMOVEMENT_S = 2.0


def _scenario(with_zones: bool, premovement: bool = False):
    spec = _spec()
    scenario = corridor_scenario(spec)
    if premovement:
        scenario.raw["distributions"]["spawn_near"]["parameters"].update(
            use_premovement=True,
            premovement_distribution="constant",
            premovement_param_a=PREMOVEMENT_S,
        )
    if with_zones:
        scenario.raw["zones"] = {
            key: {
                "coordinates": [[x0, 0.0], [x1, 0.0], [x1, 4.0], [x0, 4.0], [x0, 0.0]],
                "speed_factor": factor,
            }
            for key, (x0, x1, factor) in ZONES.items()
        }
    return spec, scenario


def _zone_factor(x: float, y: float, with_zones: bool) -> float:
    if not with_zones:
        return 1.0
    best = 1.0
    for x0, x1, factor in ZONES.values():
        if x0 <= x <= x1 and 0.0 <= y <= 4.0 and abs(factor - 1.0) > abs(best - 1.0):
            best = factor
    return best


class _Recorder:
    def __init__(self):
        self.rows: list[tuple[float, int, float, float, float]] = []


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()

    class RecordingSimulation(jps.Simulation):
        def iterate(self, count: int = 1):
            t = self.elapsed_time()
            for agent in self.agents():
                pos = agent.position
                rec.rows.append(
                    (t, int(agent.id), pos[0], pos[1], agent.model.desired_speed)
                )
            return super().iterate(count)

    monkeypatch.setattr(jps, "Simulation", RecordingSimulation)
    return rec


def _factor_lookup(history, key):
    """Return f(agent_id, t) -> last logged factor at or before t (1 before any)."""
    per_agent: dict[int, list[tuple[float, float]]] = {}
    for row in history or []:
        per_agent.setdefault(row["agent_id"], []).append(
            (float(row["time_s"]), float(row[key]))
        )

    def lookup(agent_id: int, t: float) -> float:
        value = 1.0
        for time_s, factor in per_agent.get(agent_id, []):
            if time_s > t + 1e-9:
                break
            value = factor
        return value

    return lookup


def _assert_closed_form(rows, with_zones, smoke, fic, *, min_zone_rows=0, start_s=0.0):
    """Before ``start_s`` (pre-movement) agents stand still."""
    assert rows, "no step was recorded"
    in_zone = 0
    for t, agent_id, x, y, speed in rows:
        zone = _zone_factor(x, y, with_zones)
        in_zone += zone != 1.0
        v0 = V0 if t >= start_s - 1e-9 else 0.0
        expected = v0 * zone * smoke(agent_id, t) * fic(agent_id, t)
        assert speed == pytest.approx(expected, rel=1e-9, abs=1e-12), (
            f"t={t} agent={agent_id} x={x:.3f} zone={zone}"
        )
    assert in_zone >= min_zone_rows


@pytest.mark.parametrize("with_zones", [True, False], ids=["zones", "no_zones"])
def test_smoke_and_zones_reach_every_step(recorder, with_zones):
    """Smoke that thickens over time, with and without active zones.

    Without zones this is the common FDS-coupled case: the update runs only
    because a smoke model is present.
    """
    spec, scenario = _scenario(with_zones)

    def extinction(t, x, y):
        if t < 3.0:
            return 0.0
        return 1.0 if t < 8.0 else 2.0

    result = run_scenario(
        scenario, seed=spec.seed, smoke_speed_model=make_smoke_model(extinction)
    )
    try:
        assert result.smoke_history
        _assert_closed_form(
            recorder.rows,
            with_zones,
            _factor_lookup(result.smoke_history, "speed_factor"),
            lambda agent_id, t: 1.0,
            min_zone_rows=100 if with_zones else 0,
        )
    finally:
        result.cleanup()


def test_zones_without_smoke(recorder):
    spec, scenario = _scenario(True)
    result = run_scenario(scenario, seed=spec.seed)
    try:
        _assert_closed_form(
            recorder.rows,
            True,
            lambda agent_id, t: 1.0,
            lambda agent_id, t: 1.0,
            min_zone_rows=100,
        )
    finally:
        result.cleanup()


def test_fic_inside_zones_keeps_the_zone_factor(recorder):
    """FIC rewrites the speed without the zone factor every FED update.

    The factors themselves do not change, so an update that returns early on
    unchanged inputs would leave agents in a zone at the wrong speed.
    """
    spec, scenario = _scenario(True)
    # 450 ppm HCl gives FIC 0.5, so the FIC speed factor is 1 - 0.7 * 0.5.
    fed = make_fed_model(
        co_volume_fraction=uniform(0.0),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        hcl=uniform(450e-6),
    )
    tenability = TenabilityConfig(enable_fic_speed=True, enable_incapacitation=False)
    result = run_scenario(
        scenario,
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(after(2.0, uniform(1.0))),
        fed_model=fed,
        tenability_config=tenability,
    )
    try:
        fic_rows = [r for r in result.fed_history if r["fic_speed_factor"] != 1.0]
        assert fic_rows
        assert fic_rows[0]["fic_speed_factor"] == pytest.approx(0.65)
        _assert_closed_form(
            recorder.rows,
            True,
            _factor_lookup(result.smoke_history, "speed_factor"),
            _factor_lookup(result.fed_history, "fic_speed_factor"),
            min_zone_rows=100,
        )
    finally:
        result.cleanup()


def test_premovement_activation_sets_the_baseline(recorder):
    """Agents stand at 0 until pre-movement ends, then walk at the closed form.

    Activation changes ``original_speed`` while the smoke factor is already
    below 1, so the update must pick up the new baseline at once.
    """
    spec, scenario = _scenario(True, premovement=True)
    result = run_scenario(
        scenario,
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(uniform(1.0)),
    )
    try:
        assert any(t < PREMOVEMENT_S for t, *_ in recorder.rows)
        _assert_closed_form(
            recorder.rows,
            True,
            _factor_lookup(result.smoke_history, "speed_factor"),
            lambda agent_id, t: 1.0,
            min_zone_rows=100,
            start_s=PREMOVEMENT_S,
        )
    finally:
        result.cleanup()


@pytest.mark.parametrize("with_zones", [True, False], ids=["zones", "no_zones"])
def test_smoke_clearing_restores_full_speed(recorder, with_zones):
    """Smoke that clears to K = 0 gives agents outside every zone v0 back (#246)."""
    spec, scenario = _scenario(with_zones)

    def extinction(t, x, y):
        return 1.0 if 2.0 <= t < 5.0 else 0.0

    result = run_scenario(
        scenario, seed=spec.seed, smoke_speed_model=make_smoke_model(extinction)
    )
    try:
        smoke = _factor_lookup(result.smoke_history, "speed_factor")
        assert any(smoke(r[1], r[0]) < 1.0 for r in recorder.rows)
        cleared = [
            r
            for r in recorder.rows
            if r[0] >= 6.0 and _zone_factor(r[2], r[3], with_zones) == 1.0
        ]
        assert cleared
        assert all(speed == pytest.approx(V0) for *_, speed in cleared)
        _assert_closed_form(recorder.rows, with_zones, smoke, lambda agent_id, t: 1.0)
    finally:
        result.cleanup()
