"""Evacuation time t is FDS time t: the FDS output must start at t = 0.

An FDS deck with T_BEGIN > 0 writes its first frame late. The nearest-frame
lookup used to read that first frame for every earlier time, so agents saw
smoke that did not exist yet. A first frame later than the tolerance now stops
the run at setup and at every reader.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac import cli
from pyfds_evac.config import messages
from pyfds_evac.config.effective import effective_configuration
from pyfds_evac.config.rules import FdsFacts
from pyfds_evac.core.fds_sampling import (
    FDS_START_TOLERANCE_S,
    FdsHorizonError,
    FdsStartError,
    SliceFieldSampler,
    fds_output_start,
)
from pyfds_evac.core.fed import FdsFedField, FdsHeatField
from pyfds_evac.core.radiometer_grid import RadiometerGrid, RadiometerSource
from pyfds_evac.core.run_config import _check_fds_start
from pyfds_evac.core.smoke_speed import ExtinctionField
from pyfds_evac.core.visibility import VisibilityModel

TIMES = [5.0, 10.0, 15.0]


class _Slice:
    """One-cell slice with the given frame times; value is the frame index."""

    def __init__(self, name="SOOT EXTINCTION COEFFICIENT", times=TIMES):
        self.times = np.asarray(times, dtype=float)
        self.quantity = SimpleNamespace(name=name)
        extent = SimpleNamespace(
            x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0, z_start=1.8, z_end=1.8
        )
        mesh = SimpleNamespace(coordinates={"x": np.array([0.0]), "y": [0.0]})
        data = np.arange(float(self.times.size)).reshape(-1, 1, 1)
        self.extent = extent
        self.subslices = [
            SimpleNamespace(extent=extent, mesh=mesh, cell_centered=False, data=data)
        ]

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _sampler(name="SOOT EXTINCTION COEFFICIENT", times=TIMES, **kwargs):
    return SliceFieldSampler(_Slice(name, times), **kwargs)


# --- A1: the samplers -------------------------------------------------------


@pytest.mark.parametrize("hold", [False, True])
def test_sample_before_the_first_frame_raises(hold):
    sampler = _sampler(allow_horizon_hold=hold)
    with pytest.raises(FdsStartError, match="T_BEGIN = 0") as excinfo:
        sampler.sample(0.0, 0.5, 0.5)
    assert "t=5.000 s" in str(excinfo.value)
    assert "--allow-fds-horizon-hold" not in str(excinfo.value)
    assert isinstance(excinfo.value, FdsHorizonError)


@pytest.mark.parametrize("hold", [False, True])
def test_read_cells_before_the_first_frame_raises(hold):
    sampler = _sampler(allow_horizon_hold=hold)
    part = sampler.line_parts(0.0, 0.5, 1.0, 0.5)[0]
    assert part.cells is not None
    n = part.cells[0].size
    with pytest.raises(FdsStartError):
        sampler.read_cells(part, np.zeros(n))
    with pytest.raises(FdsStartError):
        sampler.read_cells(part, np.linspace(0.0, 12.0, n))


def test_first_frame_within_the_tolerance_passes():
    sampler = _sampler(times=[0.0005, 1.0, 2.0])
    assert sampler.sample(0.0, 0.5, 0.5) == 0.0
    assert FDS_START_TOLERANCE_S == 1e-3


def test_single_frame_slice_starting_late_raises():
    with pytest.raises(FdsStartError):
        _sampler(times=[5.0]).sample(0.0, 0.5, 0.5)


def test_a_time_from_the_first_frame_on_reads_it():
    assert _sampler().sample(5.0, 0.5, 0.5) == 0.0


def test_the_output_start_is_the_latest_first_frame_of_the_slices():
    sim = SimpleNamespace(
        slices=[_Slice(times=[0.0, 1.0]), _Slice(times=[5.0, 6.0]), _Slice(times=[9.0])]
    )
    assert fds_output_start("unused", simulation=sim) == 5.0
    assert fds_output_start("unused", simulation=SimpleNamespace(slices=[])) is None


# --- A2: the fields do not turn the start into ambient air ------------------


def test_extinction_field_does_not_turn_the_start_into_clear_air():
    field = ExtinctionField(_sampler())
    assert field.sample_extinction(5.0, 5.0, 5.0) == 0.0  # out of domain
    with pytest.raises(FdsStartError):
        field.sample_extinction(0.0, 0.5, 0.5)


def test_fed_field_does_not_turn_the_start_into_zero_dose():
    field = FdsFedField(_sampler("CO"), _sampler("CO2"), _sampler("O2"))
    with pytest.raises(FdsStartError):
        field.sample_inputs(0.0, 0.5, 0.5)


def test_heat_field_does_not_turn_the_start_into_no_heat():
    field = FdsHeatField(_sampler("TEMPERATURE"))
    with pytest.raises(FdsStartError):
        field.sample_inputs(0.0, 0.5, 0.5)


# --- A3: setup --------------------------------------------------------------


def _opts(**overrides):
    return SimpleNamespace(**{"fds_dir": "some/fds", **overrides})


def test_setup_stops_on_a_deck_starting_late():
    sim = SimpleNamespace(slices=[_Slice()])
    with patch("pyfds_evac.core.fds_sampling._open_simulation", return_value=sim):
        with pytest.raises(FdsStartError, match="T_BEGIN = 0") as excinfo:
            _check_fds_start(_opts(allow_fds_horizon_hold=True))
    assert "some/fds" in str(excinfo.value)
    assert "t=5.000 s" in str(excinfo.value)


def test_setup_passes_a_deck_starting_at_zero():
    sim = SimpleNamespace(slices=[_Slice(times=[0.0, 5.0])])
    with patch("pyfds_evac.core.fds_sampling._open_simulation", return_value=sim):
        _check_fds_start(_opts())


def test_config_rule_reports_the_late_start_as_d36():
    opts = cli._build_parser().parse_args(["--scenario", "x", "--fds-dir", "some/fds"])
    facts = FdsFacts(frozenset({"extinction"}), (1000.0, 5.0), start=5.0)
    errors = effective_configuration(opts, {}, fds=facts).errors
    assert [e.rule for e in errors] == ["D36"]
    assert errors[0].message == messages.fds_start_late("some/fds", 5.0)
    ok = FdsFacts(frozenset({"extinction"}), (1000.0, 5.0), start=0.0)
    assert effective_configuration(opts, {}, fds=ok).errors == ()


# --- A4: the radiometer -----------------------------------------------------


def test_radiometer_before_its_first_time_raises():
    xs = ys = np.array([1.0, 2.0])
    times = np.array([5.0, 8.0])
    source = RadiometerSource(
        grid=RadiometerGrid(xs, ys, times, np.full((2, 2, 2), 3.0)),
        orientation=(0.0, 0.0, 1.0),
        z_m=1.6,
        gauge_temperature_c=20.0,
        gauge_emissivity=1.0,
        n_devices=4,
        deck_path=Path("case.fds"),
        deck_sha256="0" * 64,
    )
    with pytest.raises(FdsStartError, match="RADIOMETER"):
        source.reading(0.0, 1.5, 1.5)
    assert source.reading(5.0, 1.5, 1.5) == pytest.approx(3.0)


# --- A5: sign visibility ----------------------------------------------------


class _Collection(list):
    def filter_by_quantity(self, name):
        return [s for s in self if s.quantity.name == name]


def test_visibility_build_raises_on_a_late_extinction_slice(tmp_path):
    sim = SimpleNamespace(slices=_Collection([_Slice()]))
    signs = {"e0": {"x": 0.0, "y": 0.0}}
    cache = tmp_path / "vis.npz"
    with patch(
        "pyfds_evac.core.fdsreader_adapter.open_fds_simulation", return_value=sim
    ):
        with pytest.raises(FdsStartError, match="T_BEGIN = 0"):
            VisibilityModel("some/fds", signs, cache_path=cache)
    assert not cache.exists()


def test_late_start_message_names_the_deck_and_quantity():
    text = messages.fds_start_late(
        "some/fds", 5.0, quantity="SOOT EXTINCTION COEFFICIENT"
    )
    assert "some/fds" in text and "SOOT EXTINCTION COEFFICIENT" in text
    runtime = messages.fds_start_late("some/fds", 5.0, requested_s=0.0)
    assert "Requested at t=0.0 s" in runtime
    assert "allow-fds-horizon-hold" not in runtime
