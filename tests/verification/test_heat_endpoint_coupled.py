"""Coupled runs with an endpoint-coherent heat configuration (#220).

Two corridor runs through ``run_scenario`` with a uniform temperature field:

- **Table 63.21 history** (SFPE Handbook 5th ed. Ch. 63, p. 2385): the
  per-minute average temperatures 20, 65, 125, 220, 405, 405 deg C. Under the
  tolerance endpoint (Eq. 63.45) the Handbook predicts FED = 1 during the
  fourth minute. The expected crossing time is integrated here from the hand
  formula; the Eq. 63.44 crossing is computed too and must lie further away
  than the timing tolerance, so the test tells the two laws apart.
- **Constant 150 deg C, fatal endpoint** (Eq. 63.47, p. 2383): the threshold
  is set so the hand formula predicts a crossing mid-run; Eq. 63.44 would
  cross 8.6 times sooner.

The runs also check that the endpoint and the validity flag reach the FED
history and the run manifest.

Assumed API, as in ``tests/test_heat_endpoint.py``:
``DefaultHeatFedModel(field, config, endpoint=...)``; FED history rows carry
``heat_endpoint`` and ``heat_outside_validity``; the manifest carries
``heat_endpoint``. Adapt ``_heat_model`` and the key names if the
implementation differs, then drop the xfail markers.
"""

from __future__ import annotations

import json
import math

import pytest
from harness import (
    CorridorSpec,
    SyntheticSampler,
    corridor_scenario,
    first_incapacitation_times,
)

from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultHeatFedModel,
    FdsHeatField,
    TenabilityConfig,
)
from pyfds_evac.core.scenario import run_scenario

XFAIL_220 = pytest.mark.xfail(strict=True, reason="#220")
UPDATE_S = 1.0
# Right-point sampling on 1 s updates: a crossing lands on the update at or
# after the exact time.
TIMING_TOL_S = 1.5

TABLE_63_21_C = [20.0, 65.0, 125.0, 220.0, 405.0, 405.0]


def t_eq_63_44_min(t_c: float) -> float:
    """Eq. 63.44, p. 2382."""
    return 5e7 * t_c**-3.4


def t_tolerance_min(t_c: float) -> float:
    """Eq. 63.45, p. 2382."""
    return 2e31 * t_c**-16.963 + 4e8 * t_c**-3.7561


def t_fatal_min(t_c: float) -> float:
    """Eq. 63.47, p. 2383."""
    return 2e18 * t_c**-9.0403 + 1e8 * t_c**-3.10898


def _table_63_21_field(t, x, y):
    minute = min(int(t // 60.0), len(TABLE_63_21_C) - 1)
    return TABLE_63_21_C[minute]


def _crossing_s(law, start_s: float, threshold: float = 1.0) -> float:
    """Exact time the piecewise-constant Table 63.21 history reaches *threshold*."""
    dose = 0.0
    t = start_s
    while True:
        minute_end = (math.floor(t / 60.0) + 1) * 60.0
        rate_per_s = 1.0 / law(_table_63_21_field(t, 0, 0)) / 60.0
        step = minute_end - t
        if dose + rate_per_s * step >= threshold:
            return t + (threshold - dose) / rate_per_s
        dose += rate_per_s * step
        t = minute_end


def _heat_model(field_fn, endpoint):
    field = FdsHeatField(SyntheticSampler(field_fn))  # type: ignore[arg-type]
    config = DefaultFedConfig(fds_dir="", update_interval_s=UPDATE_S)
    if endpoint is None:
        return DefaultHeatFedModel(field, config)
    return DefaultHeatFedModel(field, config, endpoint=endpoint)


def _spec(run_s: float) -> CorridorSpec:
    # Slow and long, so nobody leaves the field before the crossing.
    return CorridorSpec(
        length_m=120.0,
        width_m=4.0,
        num_agents=2,
        v0=0.3,
        seed=11,
        max_simulation_time=run_s,
    )


def _run(field_fn, endpoint, *, threshold=1.0, run_s=260.0):
    spec = _spec(run_s)
    assert spec.free_walk_egress_s > run_s
    return run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        heat_fed_model=_heat_model(field_fn, endpoint),
        tenability_config=TenabilityConfig(
            enable_fic_speed=False,
            enable_incapacitation=False,
            enable_heat_incapacitation=True,
            heat_fed_threshold=threshold,
            heat_incapacitation_mode="deterministic",
        ),
    )


def _start_times(rows):
    starts: dict[int, float] = {}
    for row in rows:
        aid = row["agent_id"]
        starts[aid] = min(starts.get(aid, math.inf), float(row["time_s"]))
    return starts


def test_table_63_21_crossings_are_distinguishable():
    """Design check (passes now): the two laws cross > 2 tolerances apart."""
    tolerance = _crossing_s(t_tolerance_min, 0.0)
    default = _crossing_s(t_eq_63_44_min, 0.0)
    assert 180.0 < tolerance < 240.0  # during the fourth minute
    assert abs(tolerance - default) > 2 * TIMING_TOL_S


def _check_crossings(result, law):
    rows = result.fed_history
    times = first_incapacitation_times(result)
    starts = _start_times(rows)
    assert times, "no agent incapacitated"
    for aid, t_stop in times.items():
        expected = _crossing_s(law, starts[aid])
        assert abs(t_stop - expected) <= TIMING_TOL_S, (aid, t_stop, expected)


def test_default_law_crosses_at_eq_63_44():
    """Control (passes now): without an endpoint the run follows Eq. 63.44."""
    result = _run(_table_63_21_field, None)
    try:
        _check_crossings(result, t_eq_63_44_min)
    finally:
        result.cleanup()


@XFAIL_220
def test_tolerance_endpoint_crosses_in_the_fourth_minute():
    result = _run(_table_63_21_field, "tolerance")
    try:
        _check_crossings(result, t_tolerance_min)
    finally:
        result.cleanup()


@XFAIL_220
def test_fatal_endpoint_constant_temperature():
    t_c = 150.0
    target_s = 90.0
    # Threshold reached after target_s under Eq. 63.47.
    threshold = target_s / 60.0 / t_fatal_min(t_c)
    assert 60.0 * threshold * t_eq_63_44_min(t_c) < target_s / 8.0
    result = _run(lambda t, x, y: t_c, "fatal", threshold=threshold, run_s=130.0)
    try:
        rows = result.fed_history
        times = first_incapacitation_times(result)
        starts = _start_times(rows)
        assert times, "no agent incapacitated"
        for aid, t_stop in times.items():
            assert abs(t_stop - starts[aid] - target_s) <= TIMING_TOL_S
    finally:
        result.cleanup()


@XFAIL_220
def test_endpoint_and_validity_flag_reach_the_outputs():
    """FED history rows carry the endpoint and flag T above the data range."""
    result = _run(_table_63_21_field, "fatal", run_s=300.0)
    try:
        rows = result.fed_history
        assert rows
        assert {row["heat_endpoint"] for row in rows} == {"fatal"}
        for row in rows:
            hot = float(row["temperature_celsius"]) > 250.0
            cool = float(row["temperature_celsius"]) < 180.0
            if hot:
                assert row["heat_outside_validity"] is True
            if cool:
                assert row["heat_outside_validity"] is False
        assert any(row["heat_outside_validity"] for row in rows)
        manifest = json.loads(open(result.manifest_file).read())
        assert manifest["heat_endpoint"] == "fatal"
    finally:
        result.cleanup()
