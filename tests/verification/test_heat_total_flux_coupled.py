"""Coupled runs with the total-flux heat method (#223, spec 016).

Corridor runs through ``run_scenario`` with a uniform temperature field and
``DefaultHeatFedModel(..., method="total-flux")``. The expected crossing time
is the hand formula of Eqs. 63.49 and 63.43 (SFPE Handbook 5th ed. Ch. 63,
pp. 2382-2384; both terms of Eq. 63.49 divided by 1000 together, spec 016):

    q = [eps sigma (T_g^4 - T_s^4) + h (T_g - T_s)] / 1000     [kW/m2]
    t = D / q^1.33                                             [min]

- **Smoke, 200 deg C, tolerance** (eps 0.5, h 8, T_s 35 deg C, D = 1.33):
  q = 2.48 kW/m2, FED = 1 after 24 s. Eq. 63.44 would give 45 s, Eq. 63.45
  about 2.4 min.
- **Clear air, 100 deg C, tolerance** (eps 0.05, h 8): q = 0.55 kW/m2, well
  below the Handbook's 2.5 kW/m2 threshold, which spec 016 drops; FED = 1
  after 177 s. With the threshold there would be no dose at all.
- **Smoke, 200 deg C, fatal** without ``--heat-endpoint`` (FED = 1 = fatal,
  spec 016): threshold scaled so the crossing falls at 90 s.

Every run passes eps, h and T_s explicitly; none depends on their defaults.
Only the "head in smoke" regime is tested; the layer regime needs #222.

API under test, as in ``tests/test_heat_total_flux.py``. The outputs are also
expected to carry the method: FED history rows a ``heat_flux_kw_m2`` column,
the manifest ``heat_fed_method`` and ``heat_flux_parameters``. A run without
the method is covered by the ``golden/heat_default`` baseline in
``test_heat_endpoint_coupled.py``.
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

UPDATE_S = 1.0
# Right-point sampling on 1 s updates: a crossing lands on the update at or
# after the exact time.
TIMING_TOL_S = 1.5
SIGMA = 5.67e-8
KELVIN = 273.15
# Fatal: D = 16.7 as printed in SFPE Ch. 63, p. 2384 (Eq. 63.49 D values);
# Purser's spreadsheet uses 16.667, the code follows the Handbook.
DOSE = {"tolerance": 1.33, "fatal": 16.7}


def q_hand(t_c, *, eps, h, t_skin_c):
    tg, ts = t_c + KELVIN, t_skin_c + KELVIN
    return (eps * SIGMA * (tg**4 - ts**4) + h * (tg - ts)) / 1000.0


def t_flux_min(t_c, dose, **params):
    return dose / q_hand(t_c, **params) ** 1.33


def t_eq_63_44_min(t_c):
    return 5e7 * t_c**-3.4


def t_tolerance_min(t_c):
    return 2e31 * t_c**-16.963 + 4e8 * t_c**-3.7561


SMOKE = dict(eps=0.5, h=8.0, t_skin_c=35.0)
CLEAR_AIR = dict(eps=0.05, h=8.0, t_skin_c=35.0)


def _model(t_c, params, endpoint):
    field = FdsHeatField(SyntheticSampler(lambda t, x, y: t_c))  # type: ignore[arg-type]
    config = DefaultFedConfig(fds_dir="", update_interval_s=UPDATE_S)
    return DefaultHeatFedModel(
        field,
        config,
        endpoint=endpoint,
        method="total-flux",
        emissivity=params["eps"],
        convective_coefficient=params["h"],
        skin_temperature_celsius=params["t_skin_c"],
    )


def _run(t_c, params, endpoint, *, threshold=1.0, run_s=260.0):
    spec = CorridorSpec(
        length_m=120.0,
        width_m=4.0,
        num_agents=2,
        v0=0.3,
        seed=11,
        max_simulation_time=run_s,
    )
    assert spec.free_walk_egress_s > run_s
    return run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        heat_fed_model=_model(t_c, params, endpoint),
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


def _check_crossing(result, expected_s):
    times = first_incapacitation_times(result)
    starts = _start_times(result.fed_history)
    assert times, "no agent incapacitated"
    for aid, t_stop in times.items():
        assert abs(t_stop - starts[aid] - expected_s) <= TIMING_TOL_S, (
            aid,
            t_stop - starts[aid],
            expected_s,
        )


# --- design checks of the hand numbers --------------------------------------


def test_smoke_case_is_distinguishable_from_the_convective_laws():
    flux = 60.0 * t_flux_min(200.0, DOSE["tolerance"], **SMOKE)
    assert flux == pytest.approx(24.0, abs=0.5)
    for other in (t_eq_63_44_min(200.0), t_tolerance_min(200.0)):
        assert abs(60.0 * other - flux) > 2 * TIMING_TOL_S


def test_clear_air_case_is_below_the_handbook_threshold():
    assert q_hand(100.0, **CLEAR_AIR) < 2.5
    flux = 60.0 * t_flux_min(100.0, DOSE["tolerance"], **CLEAR_AIR)
    assert flux == pytest.approx(177.0, abs=1.0)
    assert abs(60.0 * t_tolerance_min(100.0) - flux) > 2 * TIMING_TOL_S


# --- coupled runs -------------------------------------------------------------


def test_smoke_tolerance_crossing():
    expected = 60.0 * t_flux_min(200.0, DOSE["tolerance"], **SMOKE)
    result = _run(200.0, SMOKE, "tolerance", run_s=60.0)
    try:
        _check_crossing(result, expected)
    finally:
        result.cleanup()


def test_clear_air_dose_accumulates_below_2_5_kw():
    expected = 60.0 * t_flux_min(100.0, DOSE["tolerance"], **CLEAR_AIR)
    result = _run(100.0, CLEAR_AIR, "tolerance", run_s=220.0)
    try:
        _check_crossing(result, expected)
    finally:
        result.cleanup()


def test_fatal_dose_without_endpoint():
    target_s = 90.0
    threshold = target_s / 60.0 / t_flux_min(200.0, DOSE["fatal"], **SMOKE)
    # Eq. 63.44 with the same threshold would cross far sooner.
    assert 60.0 * threshold * t_eq_63_44_min(200.0) < target_s / 3.0
    result = _run(200.0, SMOKE, None, threshold=threshold, run_s=130.0)
    try:
        _check_crossing(result, target_s)
    finally:
        result.cleanup()


def test_outputs_record_the_method_and_flux():
    q = q_hand(200.0, **SMOKE)
    result = _run(200.0, SMOKE, "tolerance", run_s=20.0)
    try:
        rows = result.fed_history
        assert rows
        for row in rows:
            assert row["heat_flux_kw_m2"] == pytest.approx(q, rel=1e-9)
        with open(result.manifest_file, encoding="utf-8") as handle:
            manifest = json.load(handle)
        assert manifest["heat_fed_method"] == "total-flux"
        recorded = manifest["heat_flux_parameters"]
        assert recorded["emissivity"] == 0.5
        assert recorded["convective_coefficient"] == 8.0
        assert recorded["skin_temperature_celsius"] == 35.0
    finally:
        result.cleanup()
