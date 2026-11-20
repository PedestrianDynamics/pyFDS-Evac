"""Radiometer radiant source against the FDS data of #224 and #308 (#276, V3-V7).

FDS output: ``fds-evac-data/heat_radiometer/{layer,uniform,burner,layer_308}``
(sciebo, or ``$HEAT_RADIOMETER_DATA``); every test skips when it is absent and
reads through the ``fds_read_only`` mirror, never the data folder itself.

Devices at z = 1.6 m on y = 2.05 m, 7 points (burner: 5) with ``&PROP``
``GAUGE_TEMPERATURE=35`` and ``HEAT_TRANSFER_COEFFICIENT=8``; the model uses
h = 8 and T_s = 35 C. FDS UG 6.10.1 Eqs. 22.35 and 22.36 with emissivity 1:

- gauge = R + h (T_dev - T_s) / 1000, R the radiometer reading [kW/m2];
- the model: q = R + h (T_slice - T_s) / 1000.

Checks (contract §4.5):

- V3: the radiometer term the model reads equals an independent linear
  interpolation in time of ``RAD_z16_<o>-k`` (1e-6 kW/m2).
- V4 (gate): q - gauge = h (T_slice - T_dev) / 1000 (1e-6 kW/m2), an identity
  of Eq. 22.35 given V3.
- V5 (report, not gated): |q / q_gauge - 1| at t = 3, 6, 9 s per orientation.
- V6: the 21 #308 cases (up, px, mx at 7 positions), sampled through the
  model at the device positions; V4 is the gate, the ratio to the gauge is
  reported beside the layer term's 54 of 63.
- V7: where the net reading is >= 2.5 kW/m2 the dose rate has the radiation
  in it, below that it is convection only (burner).

The reports print with ``pytest -s``.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np
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
    heat_flux_row_fields,
)
from pyfds_evac.core.radiometer_grid import RadiometerGrid, RadiometerSource
from pyfds_evac.core.scenario import run_scenario

REPO = Path(__file__).resolve().parents[2]
SCIEBO = Path.home() / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
DATA_ROOT = Path(
    os.environ.get("HEAT_RADIOMETER_DATA", SCIEBO / "fds-evac-data" / "heat_radiometer")
)
SCENARIO_308 = REPO / "assets" / "heat_radiometer_layer_308"

H = 8.0
T_SKIN = 35.0
D_FATAL = 16.7
ORIENTATIONS = {
    "up": "0,0,1",
    "px": "1,0,0",
    "mx": "-1,0,0",
    "dn": "0,0,-1",
}
Y = 2.05
X_LAYER = [0.45 + 0.5 * k for k in range(7)]
X_BURNER = [0.35 + 0.5 * k for k in range(5)]
TIMES = (3.0, 6.0, 9.0)
IDENTITY_TOL = 1e-6  # kW/m2
BAND = 0.30  # the radiant band of docs/testing-heat.md


def _case(name: str, mirror) -> Path:
    path = DATA_ROOT / name
    if not (path / f"heat_radiometer_{name}_devc.csv").is_file():
        pytest.skip(f"#224 radiometer data not found under {DATA_ROOT}")
    return mirror(path)


def _devc(path: Path) -> dict[str, np.ndarray]:
    """The ``_devc.csv`` of a case folder (the mirror keeps its name) as columns."""
    with (path / f"heat_radiometer_{path.name}_devc.csv").open(newline="") as handle:
        rows = list(csv.reader(handle))
    names = [n.strip().strip('"') for n in rows[1]]
    data = np.array([[float(v) for v in row] for row in rows[2:]])
    return {name: data[:, i] for i, name in enumerate(names)}


def _at(dev: dict[str, np.ndarray], name: str, t: float) -> float:
    """Linear interpolation in time of a device column (independent of the model)."""
    return float(np.interp(t, dev["Time"], dev[name]))


def _model(path: Path, orientation: str) -> DefaultHeatFedModel:
    field = FdsHeatField.from_fds(
        str(path),
        slice_height_m=1.6,
        radiometer_orientation=ORIENTATIONS[orientation],
        skin_temperature_celsius=T_SKIN,
    )
    return DefaultHeatFedModel(
        field,
        DefaultFedConfig(fds_dir=str(path), update_interval_s=1.0),
        method="total-flux",
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
        radiant_source="radiometer",
        radiometer_orientation=ORIENTATIONS[orientation],
    )


def _row(model, t: float, x: float) -> dict:
    """The history fields the run writes for one agent at one update."""
    inputs = model.sample_inputs(t, x, Y)
    row = heat_flux_row_fields(
        model,
        inputs.temperature_celsius,
        radiometer_kw_m2=inputs.radiometer_kw_m2,
    )
    return {**row, "temperature_celsius": inputs.temperature_celsius}


# --- coupled corridor (synthetic fields, no external data) ---------------------


def _corridor_model(reading: float, t_gas: float):
    xs, ys = np.array([0.0, 120.0]), np.array([0.0, 4.0])
    times = np.array([0.0, 1000.0])
    source = RadiometerSource(
        grid=RadiometerGrid(xs, ys, times, np.full((2, 2, 2), reading)),
        orientation=(0.0, 0.0, 1.0),
        z_m=1.6,
        gauge_temperature_c=T_SKIN,
        gauge_emissivity=1.0,
        n_devices=4,
        deck_path=Path("case.fds"),
        deck_sha256="ab" * 32,
    )
    field = FdsHeatField(
        SyntheticSampler(lambda t, x, y: t_gas),  # type: ignore[arg-type]
        radiometer=source,
    )
    return DefaultHeatFedModel(
        field,
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        method="total-flux",
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
        radiant_source="radiometer",
        radiometer_orientation="0,0,1",
    )


def _corridor_run(model, run_s: float):
    spec = CorridorSpec(
        length_m=120.0,
        width_m=4.0,
        num_agents=2,
        v0=0.3,
        seed=11,
        max_simulation_time=run_s,
    )
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


def test_coupled_run_dose_history_and_manifest():
    """R = 3.0, T_g = 60 C: q = 3.2 kW/m2, fatal after D / q^1.33 = 3.57 min;
    the history and the manifest carry the source."""
    q = 3.0 + H * (60.0 - T_SKIN) / 1000.0
    expected_s = 60.0 * D_FATAL / q**1.33
    result = _corridor_run(_corridor_model(3.0, 60.0), run_s=expected_s + 25.0)
    try:
        times = first_incapacitation_times(result)
        assert times, "no agent incapacitated"
        starts = {}
        for row in result.fed_history:
            starts.setdefault(row["agent_id"], float(row["time_s"]))
        for agent, t_stop in times.items():
            assert abs(t_stop - starts[agent] - expected_s) <= 1.5, agent
        for row in result.fed_history:
            assert row["heat_flux_kw_m2"] == pytest.approx(q, rel=1e-12)
            assert row["heat_radiometer_kw_m2"] == pytest.approx(3.0, rel=1e-12)
            assert row["heat_radiometer_incident_kw_m2"] == pytest.approx(
                3.511, abs=1e-3
            )
        with open(result.manifest_file, encoding="utf-8") as handle:
            recorded = json.load(handle)["heat_flux_parameters"]
        assert recorded["radiant_source"] == "radiometer"
        assert recorded["radiometer_orientation"] == [0.0, 0.0, 1.0]
        assert recorded["radiometer_device_count"] == 4
        assert recorded["fds_deck_sha256"] == "ab" * 32
    finally:
        result.cleanup()


def test_coupled_run_below_the_threshold_counts_convection_only():
    """R = 2.4 (< 2.5): the radiation is not counted; q = h dT = 0.200 kW/m2
    gives a rate of 0.2^1.33 / 16.7 per minute."""
    result = _corridor_run(_corridor_model(2.4, 60.0), run_s=30.0)
    try:
        for row in result.fed_history:
            assert row["heat_fed_rate_per_min"] == pytest.approx(
                0.2**1.33 / D_FATAL, rel=1e-12
            )
            assert row["heat_flux_kw_m2"] == pytest.approx(2.6, rel=1e-12)
    finally:
        result.cleanup()


# --- V3, V4, V5 on the layer and uniform decks -------------------------------

UPDATE_TIMES = (1.0, 2.5, 3.0, 4.37, 6.0, 7.77, 9.0, 9.99)


@pytest.mark.external_data
@pytest.mark.parametrize("case", ["layer", "uniform"])
@pytest.mark.parametrize("orientation", list(ORIENTATIONS))
def test_v3_the_radiant_term_is_the_interpolated_device(
    case, orientation, fds_read_only
):
    path = _case(case, fds_read_only)
    dev = _devc(path)
    model = _model(path, orientation)
    for t in UPDATE_TIMES:
        for k, x in enumerate(X_LAYER, start=1):
            row = _row(model, t, x)
            expected = _at(dev, f"RAD_z16_{orientation}-{k}", t)
            assert row["heat_radiometer_kw_m2"] == pytest.approx(
                expected, abs=IDENTITY_TOL
            ), (t, k)


@pytest.mark.external_data
@pytest.mark.parametrize("case", ["layer", "uniform"])
@pytest.mark.parametrize("orientation", list(ORIENTATIONS))
def test_v4_q_minus_gauge_is_the_slice_against_device_convection(
    case, orientation, fds_read_only
):
    """Gate: q - GAUGE = h (T_slice - T_dev) / 1000, an identity of Eq. 22.35."""
    path = _case(case, fds_read_only)
    dev = _devc(path)
    model = _model(path, orientation)
    for t in UPDATE_TIMES:
        for k, x in enumerate(X_LAYER, start=1):
            row = _row(model, t, x)
            gauge = _at(dev, f"GAUGE_z16_{orientation}-{k}", t)
            t_dev = _at(dev, f"T_z16-{k}", t)
            expected = H * (row["temperature_celsius"] - t_dev) / 1000.0
            assert row["heat_flux_kw_m2"] - gauge == pytest.approx(
                expected, abs=IDENTITY_TOL
            ), (t, k)


@pytest.mark.external_data
def test_v5_report_q_against_the_gauge(fds_read_only):
    """Report only: |q / q_gauge - 1| per orientation at t = 3, 6, 9 s, with the
    h dT / q the slice-against-device temperature difference alone predicts."""
    lines = ["V5: |q/q_gauge - 1| [%] and expected h dT/q [%], min / median / max"]
    for case in ("layer", "uniform"):
        path = _case(case, fds_read_only)
        dev = _devc(path)
        for orientation in ORIENTATIONS:
            model = _model(path, orientation)
            for t in TIMES:
                miss, pred = [], []
                for k, x in enumerate(X_LAYER, start=1):
                    row = _row(model, t, x)
                    gauge = _at(dev, f"GAUGE_z16_{orientation}-{k}", t)
                    miss.append(abs(row["heat_flux_kw_m2"] / gauge - 1.0) * 100.0)
                    t_dev = _at(dev, f"T_z16-{k}", t)
                    shift = H * (row["temperature_celsius"] - t_dev) / 1000.0
                    pred.append(abs(shift / gauge) * 100.0)
                lines.append(
                    f"V5 {case:8s} {orientation} t={t:g}: "
                    f"miss {min(miss):.2f} / {statistics.median(miss):.2f} / "
                    f"{max(miss):.2f}; expected "
                    f"{min(pred):.2f} / {statistics.median(pred):.2f} / "
                    f"{max(pred):.2f}"
                )
    print("\n" + "\n".join(lines))


# --- V7: the threshold on real data ------------------------------------------


@pytest.mark.external_data
@pytest.mark.parametrize("orientation", ["px", "up"])
def test_v7_threshold_on_the_burner_data(orientation, fds_read_only):
    """Net reading >= 2.5 kW/m2: radiation counts; below it only convection."""
    path = _case("burner", fds_read_only)
    model = _model(path, orientation)
    above = below = 0
    for t in np.arange(1.0, 30.0, 0.5):
        for x in X_BURNER:
            inputs, rate = model.sample_rate(float(t), x, Y)
            reading = inputs.radiometer_kw_m2
            conv = H * (inputs.temperature_celsius - T_SKIN) / 1000.0
            counted = reading if reading >= 2.5 else 0.0
            q = counted + conv
            expected = q**1.33 / D_FATAL if q > 0.0 else 0.0
            assert rate == pytest.approx(expected, rel=1e-12, abs=0.0), (t, x)
            if reading >= 2.5:
                above += 1
            else:
                below += 1
    if orientation == "px":
        assert above > 0 and below > 0, "the data must hold both branches"


# --- V6: the 21 #308 runs ---------------------------------------------------

V6_ORIENTATIONS = ("up", "px", "mx")


@pytest.mark.external_data
def test_v6_the_308_positions_with_the_radiometer_source(fds_read_only):
    """Gate: the V4 identity at each of the 21 (orientation, position) runs.
    Reported: the ratio to the gauge at t = 3, 6, 9 s beside the layer term's
    54 of 63 within +-30 % (docs/testing-heat.md).

    The agents of ``assets/heat_radiometer_layer_308`` spawn anywhere in
    0.22 m boxes, off the one-row radiometer grid, so the points are sampled
    at the device positions through the model, as in V3.
    """
    path = _case("layer_308", fds_read_only)
    dev = _devc(path)
    lines = ["V6: q_model / q_FDS gauge - 1 [%], 7 positions x t = 3, 6, 9 s"]
    total = within = 0
    for orientation in V6_ORIENTATIONS:
        model = _model(path, orientation)
        misses = []
        for k, x in enumerate(X_LAYER, start=1):
            for t in TIMES:
                row = _row(model, t, x)
                gauge = _at(dev, f"GAUGE_z16_{orientation}-{k}", t)
                t_dev = _at(dev, f"T_z16-{k}", t)
                identity = H * (row["temperature_celsius"] - t_dev) / 1000.0
                assert row["heat_flux_kw_m2"] - gauge == pytest.approx(
                    identity, abs=IDENTITY_TOL
                ), (orientation, k, t)
                ratio = row["heat_flux_kw_m2"] / gauge - 1.0
                misses.append(ratio * 100.0)
                total += 1
                within += abs(ratio) <= BAND
        lines.append(
            f"V6 {orientation}: min {min(misses):+.2f} / median "
            f"{statistics.median(misses):+.2f} / max {max(misses):+.2f} %"
        )
    lines.append(f"V6: {within} of {total} within +-{BAND:.0%} (layer term: 54 of 63)")
    print("\n" + "\n".join(lines))


@pytest.mark.external_data
def test_the_308_scenario_off_the_grid_row_stops_with_the_coverage_error(
    fds_read_only,
):
    """The #308 agents start off the one-row grid: an error, not a zero (D4)."""
    path = _case("layer_308", fds_read_only)
    command = [
        sys.executable,
        "-m",
        "pyfds_evac.cli",
        "--scenario",
        str(SCENARIO_308),
        "--seed",
        "42",
        "--fds-dir",
        str(path),
        "--enable-heat-fed",
        "--heat-fed-method",
        "total-flux",
        "--heat-radiant-source",
        "radiometer",
        "--heat-radiometer-orientation",
        "0,0,1",
    ]
    done = subprocess.run(command, capture_output=True, text=True, cwd=REPO)
    assert done.returncode == 1
    assert "outside the radiometer grid" in done.stderr
