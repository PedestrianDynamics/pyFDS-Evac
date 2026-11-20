"""Coupled run: water-vapour humidity check of ``--heat-endpoint`` (#272).

A 120 m corridor with a uniform synthetic field: 150 C and a water-vapour
volume fraction (mol/mol) of 0.05 (inside SFPE Ch. 63 p. 2383, < 10 %) or
0.12 (above). Both agents sit in the field the whole run, so every FED row
carries the status. The dose and the first incapacitation time must not
depend on the humidity.
"""

from __future__ import annotations

import json
import logging

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


def _run(vapour):
    spec = CorridorSpec(
        length_m=120.0,
        width_m=4.0,
        num_agents=2,
        v0=0.3,
        seed=11,
        max_simulation_time=60.0,
    )
    sampler = None if vapour is None else SyntheticSampler(lambda t, x, y: vapour)
    field = FdsHeatField(
        SyntheticSampler(lambda t, x, y: 150.0),  # type: ignore[arg-type]
        water_vapour_sampler=sampler,  # type: ignore[arg-type]
    )
    model = DefaultHeatFedModel(
        field, DefaultFedConfig(fds_dir="", update_interval_s=1.0), endpoint="fatal"
    )
    return run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        heat_fed_model=model,
        tenability_config=TenabilityConfig(
            enable_fic_speed=False,
            enable_incapacitation=False,
            enable_heat_incapacitation=True,
            heat_incapacitation_mode="deterministic",
        ),
    )


def _validity(result):
    with open(result.manifest_file, encoding="utf-8") as handle:
        return json.load(handle)["heat_validity"]


def test_humid_field_flags_rows_and_manifest_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        result = _run(0.12)
    try:
        assert result.fed_history
        assert {r["heat_humidity"] for r in result.fed_history} == {"humid"}
        assert {r["heat_water_vapour_fraction"] for r in result.fed_history} == {0.12}
        validity = _validity(result)
        assert validity["humidity"] == "humid"
        assert validity["humid_rows"] == len(result.fed_history)
        assert validity["humid_agents"] == 2
        assert validity["max_water_vapour_fraction"] == 0.12
        warnings = [r for r in caplog.records if "Water vapour" in r.getMessage()]
        assert len(warnings) == 1
    finally:
        result.cleanup()


def test_dry_field_is_ok_and_silent(caplog):
    with caplog.at_level(logging.WARNING):
        result = _run(0.05)
    try:
        assert {r["heat_humidity"] for r in result.fed_history} == {"ok"}
        validity = _validity(result)
        assert (validity["humidity"], validity["humid_rows"]) == ("ok", 0)
        assert not [r for r in caplog.records if "Water vapour" in r.getMessage()]
    finally:
        result.cleanup()


def test_no_slice_stays_unknown_and_dose_is_independent_of_humidity():
    runs = {v: _run(v) for v in (None, 0.05, 0.12)}
    try:
        assert {r["heat_humidity"] for r in runs[None].fed_history} == {"unknown"}
        assert _validity(runs[None])["humidity"] == "unknown"
        doses = {
            v: [r["heat_fed_cumulative"] for r in run.fed_history]
            for v, run in runs.items()
        }
        assert doses[None] == doses[0.05] == doses[0.12]
        times = {v: first_incapacitation_times(r) for v, r in runs.items()}
        assert times[None] == times[0.05] == times[0.12]
    finally:
        for run in runs.values():
            run.cleanup()
