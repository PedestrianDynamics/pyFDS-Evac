"""Radiant flux from ``INTEGRATED INTENSITY``: coupled runs and FDS data (#221).

Law and API as in ``tests/test_heat_integrated_intensity.py``: with
``radiant_source="integrated-intensity"`` the total-flux method (#223,
spec 016) uses

    q = f U - sigma T_s^4 / 1000 + h (T_g - T_s) / 1000   [kW/m2], net
    t = D / q^1.33                         [min]   (SFPE Ch. 63, Eq. 63.43)

Three levels:

- **Coupled corridor** (``run_scenario``, synthetic fields): T_g = T_s, so
  there is no convection, and U constant; the crossing time is the hand
  formula. Outputs carry U, q, the source and the net basis.
- **Committed FDS case** ``assets/heat_integrated_intensity`` (FDS 6.10.1,
  one mesh, 1 s): a 300 deg C sooty layer above 1.2 m, clear 20 deg C air
  below, INTEGRATED INTENSITY and TEMPERATURE slices at 0.4 and 1.6 m (the
  low ones and a vertical one declared first), and devices at (1.1, 1.1) at
  both heights. The reader must take the 1.6 m slice; the expected values
  are FDS's own devices.
- **Radiometer data of #224** (sciebo ``fds-evac-data/heat_radiometer``, or
  ``$HEAT_RADIOMETER_DATA``; skipped when absent). In the uniform (isotropic)
  room the model's flux with f = 1/4, h = 8, T_s = 35 deg C must equal the
  FDS skin gauge in every orientation. With emissivity 1, FDS UG 6.10.1
  Eq. 22.35 gives GAUGE = (q_inc - sigma T_s^4) + h (T_g - T_s), the same
  net basis as the model, so GAUGE is the expected value as written. The
  layer case records where [0.25, 1] brackets the gauge and where it does
  not.
"""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path

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
TIMING_TOL_S = 1.5  # right-point sampling on 1 s updates
SIGMA = 5.67e-8
KELVIN = 273.15
# Fatal: D = 16.7 as printed in SFPE Ch. 63, p. 2384 (Eq. 63.49 D values);
# Purser's spreadsheet uses 16.667, the code follows the Handbook.
DOSE = {"tolerance": 1.33, "fatal": 16.7}

ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = ROOT / "assets" / "heat_integrated_intensity" / "fds"
CASE_DEVC = CASE_DIR / "heat_integrated_intensity_devc.csv"
SCIEBO = (
    Path.home()
    / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
    / "fds-evac-data"
    / "heat_radiometer"
)
RADIOMETER_DATA = Path(os.environ.get("HEAT_RADIOMETER_DATA", SCIEBO))


def q_u_hand(t_gas_c, u_kw_m2, *, f, h, t_skin_c):
    skin_emission = SIGMA * (t_skin_c + KELVIN) ** 4 / 1000.0
    return f * u_kw_m2 - skin_emission + h * (t_gas_c - t_skin_c) / 1000.0


def t_hand_min(q, dose):
    return dose / q**1.33


def _read_devc(path: Path) -> tuple[list[str], list[list[float]]]:
    with path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    header = [name.strip().strip('"') for name in rows[1]]
    return header, [[float(value) for value in row] for row in rows[2:]]


def _devc_at(path: Path, time_s: float) -> dict[str, float]:
    header, data = _read_devc(path)
    row = min(data, key=lambda r: abs(r[0] - time_s))
    return dict(zip(header, row))


# --- coupled corridor ------------------------------------------------------------

U_CONST = 10.0
F = 0.5
T_SKIN = 35.0
H = 8.0


def _model(t_c, u, *, f=F, endpoint=None):
    field = FdsHeatField(  # type: ignore[call-arg]
        SyntheticSampler(lambda t, x, y: t_c),  # type: ignore[arg-type]
        intensity_sampler=SyntheticSampler(lambda t, x, y: u),
    )
    return DefaultHeatFedModel(
        field,
        DefaultFedConfig(fds_dir="", update_interval_s=UPDATE_S),
        endpoint=endpoint,
        method="total-flux",
        emissivity=0.5,
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
        radiant_source="integrated-intensity",  # type: ignore[call-arg]
        u_factor=f,  # type: ignore[call-arg]
    )


def _run(model, *, run_s):
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
        heat_fed_model=model,
        tenability_config=TenabilityConfig(
            enable_fic_speed=False,
            enable_incapacitation=False,
            enable_heat_incapacitation=True,
            heat_fed_threshold=1.0,
            heat_incapacitation_mode="deterministic",
        ),
    )


def _check_crossing(result, expected_s):
    times = first_incapacitation_times(result)
    starts: dict[int, float] = {}
    for row in result.fed_history:
        aid = row["agent_id"]
        starts[aid] = min(starts.get(aid, math.inf), float(row["time_s"]))
    assert times, "no agent incapacitated"
    for aid, t_stop in times.items():
        assert abs(t_stop - starts[aid] - expected_s) <= TIMING_TOL_S, (
            aid,
            t_stop - starts[aid],
            expected_s,
        )


def test_design_crossing_times():
    """q = f U - sigma T_s^4 = 5 - 0.511 = 4.489 kW/m2: fatal after 136.0 s,
    tolerance after 10.8 s."""
    q = q_u_hand(T_SKIN, U_CONST, f=F, h=H, t_skin_c=T_SKIN)
    assert q == pytest.approx(4.4888, abs=1e-4)
    assert 60.0 * t_hand_min(q, DOSE["fatal"]) == pytest.approx(136.0, abs=0.1)
    assert 60.0 * t_hand_min(q, DOSE["tolerance"]) == pytest.approx(10.8, abs=0.1)


def test_fatal_crossing_radiant_only():
    q = q_u_hand(T_SKIN, U_CONST, f=F, h=H, t_skin_c=T_SKIN)
    expected = 60.0 * t_hand_min(q, DOSE["fatal"])
    result = _run(_model(T_SKIN, U_CONST), run_s=160.0)
    try:
        _check_crossing(result, expected)
    finally:
        result.cleanup()


def test_crossing_scales_with_the_factor():
    """f = 1 on the same U: q = 10 - 0.511 = 9.489 kW/m2, fatal after 50.3 s."""
    q = q_u_hand(T_SKIN, U_CONST, f=1.0, h=H, t_skin_c=T_SKIN)
    expected = 60.0 * t_hand_min(q, DOSE["fatal"])
    assert expected == pytest.approx(50.3, abs=0.1)
    result = _run(_model(T_SKIN, U_CONST, f=1.0), run_s=70.0)
    try:
        _check_crossing(result, expected)
    finally:
        result.cleanup()


def test_outputs_record_u_flux_and_source():
    t_c = 100.0
    q = q_u_hand(t_c, U_CONST, f=F, h=H, t_skin_c=T_SKIN)
    result = _run(_model(t_c, U_CONST), run_s=10.0)
    try:
        rows = result.fed_history
        assert rows
        for row in rows:
            assert row["heat_integrated_intensity_kw_m2"] == pytest.approx(U_CONST)
            assert row["heat_flux_kw_m2"] == pytest.approx(q, rel=1e-9)
        with open(result.manifest_file, encoding="utf-8") as handle:
            recorded = json.load(handle)["heat_flux_parameters"]
        assert recorded["radiant_source"] == "integrated-intensity"
        assert recorded["u_factor"] == F
        assert recorded["radiant_flux"] == "net"
        assert "u_factor" not in recorded["assumed"]
    finally:
        result.cleanup()


# --- committed FDS case ------------------------------------------------------------

CASE_TIME_S = 1.0
CASE_XY = (1.1, 1.1)


def test_case_devices_separate_the_heights():
    """Design check on FDS's own output: U differs by more than 2x."""
    devc = _devc_at(CASE_DEVC, CASE_TIME_S)
    assert devc["U_z16"] > 2.0 * devc["U_z04"]
    assert devc["T_z16"] > 250.0 > 50.0 > devc["T_z04"]


def _case_field():
    return FdsHeatField.from_fds(  # type: ignore[call-arg]
        str(CASE_DIR), slice_height_m=1.6, integrated_intensity=True
    )


def test_case_reader_takes_the_head_height_intensity_slice():
    devc = _devc_at(CASE_DEVC, CASE_TIME_S)
    inputs = _case_field().sample_inputs(CASE_TIME_S, *CASE_XY)
    assert inputs.integrated_intensity_kw_m2 == pytest.approx(devc["U_z16"], rel=0.05)
    assert inputs.temperature_celsius == pytest.approx(devc["T_z16"], rel=0.02)


def test_case_model_flux_from_fds_devices():
    """Whole chain: slices -> model flux, against the hand law on FDS devices."""
    devc = _devc_at(CASE_DEVC, CASE_TIME_S)
    model = DefaultHeatFedModel(
        _case_field(),
        DefaultFedConfig(fds_dir=str(CASE_DIR), update_interval_s=1.0),
        method="total-flux",
        convective_coefficient=8.0,
        skin_temperature_celsius=35.0,
        radiant_source="integrated-intensity",  # type: ignore[call-arg]
        u_factor=0.25,  # type: ignore[call-arg]
    )
    inputs = model.sample_inputs(CASE_TIME_S, *CASE_XY)
    got = model.heat_flux_kw_m2(
        inputs.temperature_celsius,
        integrated_intensity_kw_m2=inputs.integrated_intensity_kw_m2,  # type: ignore[call-arg]
    )
    expected = q_u_hand(devc["T_z16"], devc["U_z16"], f=0.25, h=8.0, t_skin_c=35.0)
    assert got == pytest.approx(expected, rel=0.05)


# --- #224 radiometer data (sciebo) ---------------------------------------------------

POINTS_X = [0.45 + 0.5 * k for k in range(7)]
POINTS_Y = 2.05
DATA_TIMES_S = (3.0, 6.0, 9.0)
FACINGS = ("up", "px", "mx", "dn")


def _radiometer(case: str) -> Path:
    path = RADIOMETER_DATA / case
    if not (path / f"heat_radiometer_{case}_devc.csv").is_file():
        pytest.skip(f"#224 radiometer data not found under {RADIOMETER_DATA}")
    return path


def _gauge(devc, facing, k):
    """FDS UG Eq. 22.35, emissivity 1: GAUGE = q_inc - sigma T_s^4 + h dT."""
    return devc[f"GAUGE_z16_{facing}-{k}"]


@pytest.mark.parametrize("case", ["uniform", "layer"])
def test_radiometer_slice_u_matches_devices(case):
    """Slice U at 1.6 m against the ``U_z16`` devices. The slice shows the
    ray effect of the 100-angle solver (about 2 % in the uniform room)."""
    path = _radiometer(case)
    field = FdsHeatField.from_fds(  # type: ignore[call-arg]
        str(path), slice_height_m=1.6, integrated_intensity=True
    )
    for time_s in DATA_TIMES_S:
        devc = _devc_at(path / f"heat_radiometer_{case}_devc.csv", time_s)
        for k, x in enumerate(POINTS_X, start=1):
            inputs = field.sample_inputs(devc["Time"], x, POINTS_Y)
            assert inputs.integrated_intensity_kw_m2 == pytest.approx(
                devc[f"U_z16-{k}"], rel=0.04
            ), (time_s, k)


def test_radiometer_uniform_quarter_u_is_the_gauge():
    """Isotropic room: f = 1/4 reproduces the FDS skin gauge in all four
    orientations (net radiation plus convection)."""
    path = _radiometer("uniform")
    model = DefaultHeatFedModel(
        FdsHeatField.from_fds(  # type: ignore[call-arg]
            str(path), slice_height_m=1.6, integrated_intensity=True
        ),
        DefaultFedConfig(fds_dir=str(path), update_interval_s=1.0),
        method="total-flux",
        convective_coefficient=8.0,
        skin_temperature_celsius=35.0,
        radiant_source="integrated-intensity",  # type: ignore[call-arg]
        u_factor=0.25,  # type: ignore[call-arg]
    )
    for time_s in DATA_TIMES_S:
        devc = _devc_at(path / "heat_radiometer_uniform_devc.csv", time_s)
        for k, x in enumerate(POINTS_X, start=1):
            inputs = model.sample_inputs(devc["Time"], x, POINTS_Y)
            got = model.heat_flux_kw_m2(
                inputs.temperature_celsius,
                integrated_intensity_kw_m2=inputs.integrated_intensity_kw_m2,  # type: ignore[call-arg]
            )
            for facing in FACINGS:
                assert got == pytest.approx(_gauge(devc, facing, k), rel=0.03), (
                    time_s,
                    k,
                    facing,
                )


def test_radiometer_uniform_devices_are_isotropic():
    """Design check on FDS's own devices (no pyfds_evac): in the uniform room
    q_inc = U / 4 for every orientation, the physics the factor rests on."""
    path = _radiometer("uniform")
    devc = _devc_at(path / "heat_radiometer_uniform_devc.csv", 6.0)
    for k in range(1, 8):
        u, t_c = devc[f"U_z16-{k}"], devc[f"T_z16-{k}"]
        for facing in FACINGS:
            expected = q_u_hand(t_c, u, f=0.25, h=8.0, t_skin_c=35.0)
            assert _gauge(devc, facing, k) == pytest.approx(expected, rel=0.01)


def test_radiometer_layer_factor_range_finding():
    """Finding for the maintainer (FDS devices only, no pyfds_evac): below a
    hot layer the crown gauge (facing up) lies inside the band f in
    [0.25, 1], but a plate facing down gets less than f = 0.25 gives, so
    [0.25, 1] is not a bound for every orientation."""
    path = _radiometer("layer")
    devc = _devc_at(path / "heat_radiometer_layer_devc.csv", 6.0)
    for k in range(1, 8):
        u, t_c = devc[f"U_z16-{k}"], devc[f"T_z16-{k}"]
        low = q_u_hand(t_c, u, f=0.25, h=8.0, t_skin_c=35.0)
        high = q_u_hand(t_c, u, f=1.0, h=8.0, t_skin_c=35.0)
        assert low < _gauge(devc, "up", k) < high, k
        assert _gauge(devc, "dn", k) < low, k
