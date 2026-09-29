"""Coupled runs with the layer regime of the total-flux heat method (#222).

Corridor runs through ``run_scenario`` with two uniform temperature fields,
one at the head and one in the hot layer, and ``DefaultHeatFedModel(...,
method="total-flux", regime="layer")``. The expected crossing time is the
hand formula (SFPE Handbook 5th ed. Ch. 63, Eqs. 63.49 and 63.43,
pp. 2382-2384; spec 016, "Regimes"):

    q = h (T_g - T_s) / 1000 + phi eps_L sigma (T_L^4 - T_s^4) / 1000
    t = D / q^1.33                                             [min]

Case: head in clear air at 120 deg C, layer at 300 deg C, eps_L = 0.9,
phi = 0.5 (face), h = 5, T_s = 35 deg C, fatal D = 16.7, threshold scaled
so the crossing falls at 90 s. The same run in the smoke regime
(eps = 0.5 at the head, no layer) crosses at about 470 s; with the draft's
double counting (layer term on top of the eps = 0.5 term) at about 75 s.
``--heat-emissivity`` is passed as 0.5 so a double-counting model would show.

The layer case of the FDS validation deck is #224; synthetic fields cover
the coupling here without FDS.

API under test, as in ``tests/test_heat_layer_flux.py``. The FED history
``heat_flux_kw_m2`` is the total q including the layer term, and rows carry
``heat_layer_temperature_c`` in the layer regime; the manifest's
``heat_flux_parameters`` records ``regime``, ``view_factor``,
``layer_emissivity`` and ``layer_height_m``.
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
DOSE_FATAL = 16.7  # SFPE Ch. 63 pp. 2382, 2384; Purser's spreadsheet: 16.667
TARGET_S = 90.0

T_HEAD = 120.0
T_LAYER = 300.0
LAYER_HEIGHT = 2.4
PARAMS = dict(eps=0.5, h=5.0, t_skin_c=35.0, phi=0.5, eps_l=0.9)


def radiant(t_c, t_skin_c):
    return SIGMA * ((t_c + KELVIN) ** 4 - (t_skin_c + KELVIN) ** 4) / 1000.0


def convective(t_c, h, t_skin_c):
    return h * (t_c - t_skin_c) / 1000.0


def q_layer(p=PARAMS):
    return convective(T_HEAD, p["h"], p["t_skin_c"]) + p["phi"] * p["eps_l"] * radiant(
        T_LAYER, p["t_skin_c"]
    )


def q_smoke(p=PARAMS):
    return convective(T_HEAD, p["h"], p["t_skin_c"]) + p["eps"] * radiant(
        T_HEAD, p["t_skin_c"]
    )


def q_double_counted(p=PARAMS):
    return q_layer(p) + p["eps"] * radiant(T_HEAD, p["t_skin_c"])


def t_min(q):
    return DOSE_FATAL / q**1.33


THRESHOLD = TARGET_S / 60.0 / t_min(q_layer())


def _model():
    config = DefaultFedConfig(fds_dir="", update_interval_s=UPDATE_S)
    return DefaultHeatFedModel(
        FdsHeatField(SyntheticSampler(lambda t, x, y: T_HEAD)),  # type: ignore[arg-type]
        config,
        method="total-flux",
        emissivity=PARAMS["eps"],
        convective_coefficient=PARAMS["h"],
        skin_temperature_celsius=PARAMS["t_skin_c"],
        regime="layer",
        layer_field=FdsHeatField(SyntheticSampler(lambda t, x, y: T_LAYER)),  # type: ignore[arg-type]
        view_factor=PARAMS["phi"],
        layer_emissivity=PARAMS["eps_l"],
        layer_height_m=LAYER_HEIGHT,
    )


def _run(run_s):
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
        heat_fed_model=_model(),
        tenability_config=TenabilityConfig(
            enable_fic_speed=False,
            enable_incapacitation=False,
            enable_heat_incapacitation=True,
            heat_fed_threshold=THRESHOLD,
            heat_incapacitation_mode="deterministic",
        ),
    )


def _start_times(rows):
    starts: dict[int, float] = {}
    for row in rows:
        aid = row["agent_id"]
        starts[aid] = min(starts.get(aid, math.inf), float(row["time_s"]))
    return starts


# --- design checks of the hand numbers --------------------------------------


def test_layer_case_is_distinguishable_from_smoke_and_double_counting():
    q = q_layer()
    assert q == pytest.approx(2.948, abs=0.002)
    smoke_s = 60.0 * THRESHOLD * t_min(q_smoke())
    double_s = 60.0 * THRESHOLD * t_min(q_double_counted())
    assert smoke_s == pytest.approx(473.0, abs=2.0)
    assert double_s == pytest.approx(75.3, abs=0.5)
    for other in (smoke_s, double_s):
        assert abs(other - TARGET_S) > 4 * TIMING_TOL_S


# --- coupled runs -------------------------------------------------------------


def test_layer_crossing():
    result = _run(130.0)
    try:
        times = first_incapacitation_times(result)
        starts = _start_times(result.fed_history)
        assert times, "no agent incapacitated"
        for aid, t_stop in times.items():
            assert abs(t_stop - starts[aid] - TARGET_S) <= TIMING_TOL_S, (
                aid,
                t_stop - starts[aid],
            )
    finally:
        result.cleanup()


def test_outputs_record_the_layer_regime():
    q = q_layer()
    result = _run(20.0)
    try:
        rows = result.fed_history
        assert rows
        for row in rows:
            assert row["heat_flux_kw_m2"] == pytest.approx(q, rel=1e-9)
            assert row["heat_layer_temperature_c"] == pytest.approx(T_LAYER)
        with open(result.manifest_file, encoding="utf-8") as handle:
            manifest = json.load(handle)
        assert manifest["heat_fed_method"] == "total-flux"
        recorded = manifest["heat_flux_parameters"]
        assert recorded["regime"] == "layer"
        assert recorded["view_factor"] == PARAMS["phi"]
        assert recorded["layer_emissivity"] == PARAMS["eps_l"]
        assert recorded["layer_height_m"] == LAYER_HEIGHT
    finally:
        result.cleanup()


def test_fed_history_csv_has_the_layer_column(tmp_path):
    """run.py's CSV writer accepts the layer-regime rows (DictWriter raises
    on a key missing from its fieldnames)."""
    import csv

    import run

    result = _run(5.0)
    try:
        out = tmp_path / "fed.csv"
        run._write_fed_history_csv(result.fed_history, str(out))
        with out.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        assert float(rows[0]["heat_layer_temperature_c"]) == pytest.approx(T_LAYER)
    finally:
        result.cleanup()
