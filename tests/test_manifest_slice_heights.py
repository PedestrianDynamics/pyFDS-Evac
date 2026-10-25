"""The run manifest records the slice height each model actually read (#165)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac import cli
from pyfds_evac.config.effective import effective_configuration, run_record
from pyfds_evac.core import manifest
from pyfds_evac.core.fds_sampling import load_slice_sampler
from pyfds_evac.core.fed import FdsHeatField
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.visibility import VisibilityModel, _VisMapCache

EXTINCTION = "SOOT EXTINCTION COEFFICIENT"
TABLE21_FDS = "assets/iso_table21_coupled/fds"
TABLE22_SCENARIO = "assets/iso_table22_coupled/config_a.json"
TABLE22_FDS = "assets/iso_table22_coupled/fds/a"


def _settings(*argv: str) -> dict:
    opts = cli._build_parser().parse_args(list(argv))
    kwargs = build_run_kwargs(load_scenario(opts.scenario), opts)
    return manifest.run_settings(
        seed=1,
        smoke_speed_model=kwargs["smoke_speed_model"],
        fed_model=kwargs["fed_model"],
        heat_fed_model=kwargs["heat_fed_model"],
    )


@pytest.mark.parametrize("requested, read", [(1.6, 1.5), (2.0, 2.0)])
def test_a_sampler_reports_its_slice_height(requested, read):
    sampler = load_slice_sampler(TABLE21_FDS, EXTINCTION, slice_height_m=requested)
    assert sampler.slice_z_m == pytest.approx(read)


def test_the_manifest_records_the_heights_read():
    settings = _settings("--scenario", TABLE22_SCENARIO, "--fds-dir", TABLE22_FDS)
    assert settings["smoke_speed"]["slice_heights_m"] == {
        EXTINCTION: pytest.approx(1.5)
    }
    assert settings["gas_fed"]["slice_heights_m"] == {
        "CARBON MONOXIDE VOLUME FRACTION": pytest.approx(1.5),
        "CARBON DIOXIDE VOLUME FRACTION": pytest.approx(1.5),
        "OXYGEN VOLUME FRACTION": pytest.approx(1.5),
    }


def test_heat_records_temperature():
    settings = _settings(
        "--scenario",
        "assets/fed_incap_heat_150c",
        "--fds-dir",
        "assets/heat_only_no_soot/fds",
        "--enable-heat-fed",
        "--allow-fds-horizon-hold",
    )
    assert settings["heat_fed"]["slice_heights_m"] == {
        "TEMPERATURE": pytest.approx(2.0)
    }


def test_constant_extinction_records_none():
    settings = _settings("--scenario", TABLE22_SCENARIO, "--constant-extinction", "1.0")
    assert "slice_heights_m" not in settings["smoke_speed"]


def _vismap_from(fds_dir: str, slice_height_m: float) -> VisibilityModel:
    cache = _VisMapCache(
        time_points=np.array([0.0, 10.0]),
        x_coords=np.array([0.0, 1.0]),
        y_coords=np.array([0.0]),
        vis=np.ones((2, 1, 1, 2), dtype=bool),
        metres=np.full((2, 1, 1, 2), 12.0),
        output_interval_s=5.0,
    )
    signs = {"e0": {"x": 0.0, "y": 0.0}}
    with patch("pyfds_evac.core.visibility._resolve_vis", return_value=cache):
        return VisibilityModel(fds_dir, signs, slice_height_m=slice_height_m)


@pytest.mark.parametrize("requested, read", [(1.6, 1.5), (2.0, 2.0)])
def test_visibility_records_the_extinction_slice_it_reads(requested, read):
    model = _vismap_from(TABLE21_FDS, requested)
    recorded = manifest.run_settings(seed=1, vis_model=model)["visibility"]
    assert recorded["slice_heights_m"] == {EXTINCTION: pytest.approx(read)}
    assert recorded["slice_height_m"] == requested


def test_the_heights_stay_out_of_the_vismap_cache_key():
    model = _vismap_from(TABLE21_FDS, 1.6)
    assert "slice_heights_m" not in model.parameters


def test_the_heights_do_not_make_the_options_differ_from_the_run():
    """The heights are read from the FDS output, not predicted from the options."""
    opts = cli._build_parser().parse_args(
        ["--scenario", TABLE22_SCENARIO, "--fds-dir", TABLE22_FDS]
    )
    scenario = load_scenario(opts.scenario)
    kwargs = build_run_kwargs(scenario, opts)
    used = manifest.run_settings(
        seed=scenario.seed,
        **{
            k: v for k, v in kwargs.items() if k in manifest.run_settings.__kwdefaults__
        },
    )
    record = run_record(effective_configuration(opts, scenario), used, opts, scenario)
    assert "slice_heights_m" in record["run"]["smoke_speed"]
    assert record["source"] == "run"


def test_heat_with_integrated_intensity_records_both_slices():
    field = FdsHeatField.from_fds(
        "assets/heat_integrated_intensity/fds", integrated_intensity=True
    )
    settings = manifest.run_settings(
        seed=1, heat_fed_model=SimpleNamespace(field=field)
    )
    assert settings["heat_fed"]["slice_heights_m"] == {
        "TEMPERATURE": pytest.approx(1.6),
        "INTEGRATED INTENSITY": pytest.approx(1.6),
    }


def test_heat_layer_regime_records_the_layer_slice():
    settings = _settings(
        "--scenario",
        "assets/fed_incap_heat_150c",
        "--fds-dir",
        "assets/heat_integrated_intensity/fds",
        "--enable-heat-fed",
        "--heat-fed-method",
        "total-flux",
        "--heat-regime",
        "layer",
        "--heat-layer-height",
        "0.4",
        "--heat-view-factor",
        "0.5",
        "--heat-layer-emissivity",
        "0.9",
        "--allow-fds-horizon-hold",
    )
    assert settings["heat_fed"]["slice_heights_m"] == {
        "TEMPERATURE": pytest.approx(1.6),
        "TEMPERATURE (layer)": pytest.approx(0.4),
    }
