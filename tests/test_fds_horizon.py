"""Sampling past the end of the FDS output (#340).

Past the last slice frame there is no smoke data. Nearest-timestep lookup used
to hold the last frame silently, so agents walked through frozen smoke and kept
accumulating dose at the final concentrations. Now a sample more than one
output interval past the end raises ``FdsHorizonError``; the hold is opt-in
through ``--allow-fds-horizon-hold`` and logged once.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import (
    FdsHorizonError,
    SliceFieldSampler,
    fds_output_horizon,
)
from pyfds_evac.core.fed import FdsFedField, FdsHeatField
from pyfds_evac.core.run_config import _check_fds_horizon
from pyfds_evac.core.smoke_speed import ExtinctionField
from pyfds_evac.core.visibility import VisibilityModel, _VisMapCache

_REPO = Path(__file__).resolve().parents[1]
_FDS_DIR = str(_REPO / "assets" / "fed_slice_height" / "fds")  # T_END = 2 s


class _Slice:
    """One-cell slice with frames at 0..10 s whose value is the frame index."""

    def __init__(self, name="SOOT EXTINCTION COEFFICIENT"):
        self.times = np.arange(0.0, 11.0)
        self.quantity = SimpleNamespace(name=name)
        extent = SimpleNamespace(x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0)
        mesh = SimpleNamespace(coordinates={"x": np.array([0.0]), "y": [0.0]})
        data = np.arange(11.0).reshape(11, 1, 1)
        self.subslices = [
            SimpleNamespace(extent=extent, mesh=mesh, cell_centered=False, data=data)
        ]

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _horizon_warnings(caplog):
    return [r for r in caplog.records if "past the FDS output" in r.getMessage()]


def test_within_one_output_interval_passes():
    assert SliceFieldSampler(_Slice()).sample(10.5, 0.5, 0.5) == 10.0


def test_beyond_one_output_interval_raises_naming_quantity_and_times():
    with pytest.raises(FdsHorizonError) as excinfo:
        SliceFieldSampler(_Slice()).sample(30.0, 0.5, 0.5)
    message = str(excinfo.value)
    assert "SOOT EXTINCTION COEFFICIENT" in message
    assert "t=30.0 s" in message
    assert "t=10.0 s" in message
    assert isinstance(excinfo.value, ValueError)


def test_horizon_is_checked_before_the_domain():
    """A point outside the slice past T_END reports the horizon, not the domain."""
    with pytest.raises(FdsHorizonError):
        SliceFieldSampler(_Slice()).sample(30.0, 5.0, 5.0)


def test_flag_holds_the_last_frame_and_warns_once(caplog):
    sampler = SliceFieldSampler(_Slice(), allow_horizon_hold=True)
    with caplog.at_level(logging.WARNING):
        assert sampler.sample(30.0, 0.5, 0.5) == 10.0
        assert sampler.sample(40.0, 0.5, 0.5) == 10.0
    assert len(_horizon_warnings(caplog)) == 1


def test_extinction_field_does_not_turn_the_horizon_into_clear_air():
    field = ExtinctionField(SliceFieldSampler(_Slice()))
    assert field.sample_extinction(5.0, 5.0, 5.0) == 0.0  # out of domain
    with pytest.raises(FdsHorizonError):
        field.sample_extinction(30.0, 0.5, 0.5)


def test_fed_field_does_not_turn_the_horizon_into_zero_dose():
    def sampler(name):
        return SliceFieldSampler(_Slice(name))

    field = FdsFedField(sampler("CO"), sampler("CO2"), sampler("O2"))
    with pytest.raises(FdsHorizonError):
        field.sample_inputs(30.0, 0.5, 0.5)
    field = FdsFedField(
        SliceFieldSampler(_Slice("CO"), allow_horizon_hold=True),
        SliceFieldSampler(_Slice("CO2"), allow_horizon_hold=True),
        SliceFieldSampler(_Slice("O2"), allow_horizon_hold=True),
        hcn=sampler("HCN"),
    )
    with pytest.raises(FdsHorizonError):
        field.sample_inputs(30.0, 0.5, 0.5)


def test_heat_field_does_not_turn_the_horizon_into_no_heat():
    field = FdsHeatField(SliceFieldSampler(_Slice("TEMPERATURE")))
    with pytest.raises(FdsHorizonError):
        field.sample_inputs(30.0, 0.5, 0.5)


def _vis_model(**kwargs):
    cache = _VisMapCache(
        time_points=np.array([0.0, 10.0]),
        x_coords=np.array([0.0, 1.0]),
        y_coords=np.array([0.0]),
        vis=np.ones((2, 1, 1, 2), dtype=bool),
        metres=np.full((2, 1, 1, 2), 12.0),
    )
    signs = {"e0": {"x": 0.0, "y": 0.0}}
    with patch("pyfds_evac.core.visibility._resolve_vis", return_value=cache):
        return VisibilityModel("unused", signs, **kwargs)


def test_visibility_raises_past_the_vismap_time_points():
    model = _vis_model()
    assert model.node_is_visible(20.0, 0.0, 0.0, "e0") is True
    with pytest.raises(FdsHorizonError):
        model.node_is_visible(30.0, 0.0, 0.0, "e0")
    with pytest.raises(FdsHorizonError):
        model.visibility_to_node(30.0, 0.0, 0.0, "e0")


def test_visibility_flag_holds_and_warns_once(caplog):
    model = _vis_model(allow_horizon_hold=True)
    with caplog.at_level(logging.WARNING):
        assert model.node_is_visible(30.0, 0.0, 0.0, "e0") is True
        assert model.visibility_to_node(40.0, 0.0, 0.0, "e0") == 12.0
    assert len(_horizon_warnings(caplog)) == 1


def test_committed_case_horizon():
    last, interval = fds_output_horizon(_FDS_DIR)
    assert last == pytest.approx(2.0)
    assert 0.0 < interval <= 2.0


def _opts(**overrides):
    return SimpleNamespace(**{"fds_dir": _FDS_DIR, **overrides})


def test_run_past_the_fds_output_fails_at_setup():
    with pytest.raises(ValueError) as excinfo:
        _check_fds_horizon(SimpleNamespace(max_simulation_time=300.0), _opts())
    message = str(excinfo.value)
    assert "max_simulation_time=300.0 s" in message
    assert "t=2.0 s" in message
    assert "--allow-fds-horizon-hold" in message


def test_run_within_the_fds_output_passes_setup():
    _check_fds_horizon(SimpleNamespace(max_simulation_time=2.0), _opts())


def test_flag_skips_the_setup_check():
    _check_fds_horizon(
        SimpleNamespace(max_simulation_time=300.0),
        _opts(allow_fds_horizon_hold=True),
    )


def test_cli_exposes_the_flag():
    from run import _build_parser

    parser = _build_parser()
    assert parser.parse_args(["--scenario", "x"]).allow_fds_horizon_hold is False
    args = parser.parse_args(["--scenario", "x", "--allow-fds-horizon-hold"])
    assert args.allow_fds_horizon_hold is True
