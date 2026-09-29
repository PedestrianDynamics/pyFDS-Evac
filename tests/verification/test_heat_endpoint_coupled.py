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

The runs also check that the endpoint, the validity flag and the unknown
humidity status reach the FED history and the run manifest, that a
non-finite temperature is flagged, and that a run without an endpoint writes
the same FED history CSV and manifest keys as the code before the option
(baseline ``golden/heat_default``, made on main 76c9a76).

API under test, as in ``tests/test_heat_endpoint.py``:
``DefaultHeatFedModel(field, config, endpoint=...)``; FED history rows carry
``heat_endpoint``, ``heat_outside_validity`` and ``heat_humidity``; the
manifest carries ``heat_endpoint`` and ``heat_validity``.
"""

from __future__ import annotations

import csv
import json
import math
import pathlib

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

TABLE_63_21_C = [20.0, 65.0, 125.0, 220.0, 405.0, 405.0]

BASELINE_DIR = pathlib.Path(__file__).parent / "golden" / "heat_default"
# Manifest values that depend on the machine, the time or the checkout.
VOLATILE_MANIFEST_KEYS = (
    "versions",
    "uv_lock_sha256",
    "git_commit",
    "git_dirty",
    "scenario_path",
    "fds_version",
    "created_utc",
)
# JuPedSim builds differ in the last bits between platforms.
FLOAT_REL = 1e-9
FLOAT_ABS = 1e-12


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
    """Design check: the two laws cross > 2 tolerances apart."""
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
    """Control: without an endpoint the run follows Eq. 63.44."""
    result = _run(_table_63_21_field, None)
    try:
        _check_crossings(result, t_eq_63_44_min)
    finally:
        result.cleanup()


def test_tolerance_endpoint_crosses_in_the_fourth_minute():
    result = _run(_table_63_21_field, "tolerance")
    try:
        _check_crossings(result, t_tolerance_min)
    finally:
        result.cleanup()


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


def _check_row_flags(rows):
    """Hot rows are flagged, cool rows are not, humidity is always unknown."""
    for row in rows:
        t_c = float(row["temperature_celsius"])
        assert not (t_c > 250.0 and str(row["heat_outside_validity"]) != "True")
        assert not (t_c < 180.0 and str(row["heat_outside_validity"]) != "False")
    assert {row["heat_endpoint"] for row in rows} == {"fatal"}
    assert {row["heat_humidity"] for row in rows} == {"unknown"}
    assert any(str(row["heat_outside_validity"]) == "True" for row in rows)


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_endpoint_and_validity_flag_reach_the_outputs():
    """FED history rows carry the endpoint and flag T above the data range."""
    result = _run(_table_63_21_field, "fatal", run_s=300.0)
    try:
        assert result.fed_history
        _check_row_flags(result.fed_history)
        manifest = _read_json(result.manifest_file)
        assert manifest["heat_endpoint"] == "fatal"
        assert manifest["heat_validity"]["humidity"] == "unknown"
        assert manifest["heat_validity"]["max_temperature_c"] == 205.0
        # FED = 1 is the fatal endpoint: Eq. 63.47 crosses at about 276 s,
        # Eq. 63.44 at about 203 s.
        _check_crossings(result, t_fatal_min)
    finally:
        result.cleanup()


def _nan_window_field(t, x, y):
    return math.nan if 5.0 <= t < 10.0 else 150.0


def test_non_finite_temperature_is_flagged_and_adds_no_dose():
    """A NaN sample is flagged and contributes nothing to the dose."""
    result = _run(_nan_window_field, "fatal", run_s=20.0)
    try:
        rows = result.fed_history
        bad = [row for row in rows if not math.isfinite(row["temperature_celsius"])]
        good = [row for row in rows if math.isfinite(row["temperature_celsius"])]
        assert bad and good
        assert {row["heat_outside_validity"] for row in bad} == {True}
        assert {row["heat_fed_rate_per_min"] for row in bad} == {0.0}
        assert {row["heat_outside_validity"] for row in good} == {False}
    finally:
        result.cleanup()


def _csv_rows(result, path):
    import run

    run._write_fed_history_csv(result.fed_history, str(path))
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def _renumbered(rows):
    """JuPedSim numbers agents process-wide: count ids from the first one."""
    first = min(int(row["agent_id"]) for row in rows)
    return [{**row, "agent_id": str(int(row["agent_id"]) - first)} for row in rows]


def _same_value(got: str, want: str) -> bool:
    try:
        return math.isclose(
            float(got), float(want), rel_tol=FLOAT_REL, abs_tol=FLOAT_ABS
        )
    except ValueError:
        return got == want


def _assert_rows_match(got_rows, want_rows):
    assert len(got_rows) == len(want_rows)
    for i, (got, want) in enumerate(zip(got_rows, want_rows)):
        mismatched = [k for k in want if not _same_value(got[k], want[k])]
        assert not mismatched, (i, {k: (got[k], want[k]) for k in mismatched})


def _normalised_manifest(path):
    manifest = _read_json(path)
    return {
        key: "<normalised>" if key in VOLATILE_MANIFEST_KEYS else value
        for key, value in manifest.items()
    }


def test_default_outputs_match_the_baseline(tmp_path):
    """Without an endpoint the FED history CSV and manifest are as on main."""
    result = _run(_table_63_21_field, None, run_s=30.0)
    try:
        header, rows = _csv_rows(result, tmp_path / "fed.csv")
        want_header, want_rows = _read_baseline_csv()
        assert header == want_header
        _assert_rows_match(_renumbered(rows), _renumbered(want_rows))
        assert _normalised_manifest(result.manifest_file) == _read_json(
            BASELINE_DIR / "manifest.json"
        )
    finally:
        result.cleanup()


def _read_baseline_csv():
    with open(BASELINE_DIR / "fed_history.csv", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def test_endpoint_fed_history_csv_carries_endpoint_and_flag(tmp_path):
    """``--output-fed-history`` keeps the endpoint, the flag and humidity."""
    result = _run(_table_63_21_field, "fatal", run_s=300.0)
    try:
        header, rows = _csv_rows(result, tmp_path / "fed.csv")
        assert header[-3:] == [
            "heat_endpoint",
            "heat_outside_validity",
            "heat_humidity",
        ]
        _check_row_flags(rows)
    finally:
        result.cleanup()
