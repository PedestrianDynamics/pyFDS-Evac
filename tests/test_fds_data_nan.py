"""A non-finite FDS value inside the slice domain stops the run.

fdsreader fills a point that holds no data with NaN. The readers used to hand
it on: a NaN extinction reads as no smoke, a NaN gas fraction as no dose, a
NaN temperature as no heat, and every comparison with it is false, so the run
went on as if the data were benign. Out-of-domain points keep reading ambient
air; this is about points the slice covers.
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import FdsDataError, SliceFieldSampler
from pyfds_evac.core.fed import FdsFedField, FdsHeatField
from pyfds_evac.core.radiometer_grid import RadiometerGrid, RadiometerSource
from pyfds_evac.core.smoke_speed import ExtinctionField

_REPO = Path(__file__).resolve().parents[1]
TIMES = np.array([0.0, 1.0, 2.0])


class _Slice:
    """A 1 x 2 cell slice, frames 0..2 s; the value at cell j of frame k is 10k+j."""

    def __init__(self, name="SOOT EXTINCTION COEFFICIENT", nan_at=None):
        self.times = TIMES
        self.quantity = SimpleNamespace(name=name)
        extent = SimpleNamespace(x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0)
        mesh = SimpleNamespace(
            id="MESH1", coordinates={"x": np.array([0.0]), "y": np.array([0.0, 1.0])}
        )
        data = 10.0 * np.arange(3.0)[:, None, None] + np.arange(2.0)[None, None, :]
        if nan_at is not None:
            data[nan_at] = np.nan
        self.subslices = [
            SimpleNamespace(extent=extent, mesh=mesh, cell_centered=False, data=data)
        ]

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _sampler(name="SOOT EXTINCTION COEFFICIENT"):
    return SliceFieldSampler(_Slice(name, nan_at=(1, 0, 1)))  # frame 1, y = 1


# --- C1: the sampler --------------------------------------------------------


def test_nan_at_a_read_cell_raises_naming_the_context():
    with pytest.raises(FdsDataError) as excinfo:
        _sampler().sample(1.0, 0.0, 1.0)
    message = str(excinfo.value)
    assert "SOOT EXTINCTION COEFFICIENT" in message
    assert "t=1.0 s" in message
    assert "(0.00, 1.00)" in message
    assert "MESH1" in message
    assert not isinstance(excinfo.value, ValueError)


def test_a_finite_neighbour_and_other_frames_read_unchanged():
    sampler = _sampler()
    assert sampler.sample(1.0, 0.0, 0.0) == 10.0
    assert sampler.sample(0.0, 0.0, 1.0) == 1.0
    assert sampler.sample(2.0, 0.0, 1.0) == 21.0


def test_nan_in_read_cells_raises_and_finite_cells_read_unchanged():
    sampler = _sampler()
    part = sampler.line_parts(0.0, 0.0, 0.0, 1.0)[0]
    assert part.cells is not None
    n = part.cells[0].size
    with pytest.raises(FdsDataError, match="SOOT EXTINCTION COEFFICIENT"):
        sampler.read_cells(part, np.full(n, 1.0))
    values = sampler.read_cells(part, np.full(n, 2.0))
    assert np.isfinite(values).all()


def test_the_domain_rule_is_unchanged():
    with pytest.raises(ValueError, match="outside the sampled FDS slice domain"):
        _sampler().sample(1.0, 5.0, 5.0)


# --- C2: the fields do not turn NaN into ambient values ---------------------


def test_extinction_field_propagates():
    field = ExtinctionField(_sampler())
    assert field.sample_extinction(1.0, 5.0, 5.0) == 0.0  # out of domain
    with pytest.raises(FdsDataError):
        field.sample_extinction(1.0, 0.0, 1.0)


def test_fed_field_propagates():
    field = FdsFedField(
        _sampler("CARBON MONOXIDE VOLUME FRACTION"),
        _sampler("CARBON DIOXIDE VOLUME FRACTION"),
        _sampler("OXYGEN VOLUME FRACTION"),
    )
    with pytest.raises(FdsDataError):
        field.sample_inputs(1.0, 0.0, 1.0)


def test_heat_field_propagates():
    field = FdsHeatField(_sampler("TEMPERATURE"))
    with pytest.raises(FdsDataError):
        field.sample_inputs(1.0, 0.0, 1.0)


class _NanAfterOneSecond:
    """Extinction field whose data turn NaN from t = 1 s."""

    def sample_extinction(self, time_s, x, y):
        if time_s > 1.0:
            raise FdsDataError(f"non-finite value at t={time_s}")
        return 0.0


def test_flow_spawn_does_not_swallow_the_data_error():
    """A flow spawn ranks routes on smoke; a data error must stop the run."""
    from pyfds_evac.core.scenario import Scenario, run_scenario
    from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

    asset = _REPO / "assets" / "t_junction"
    raw = json.loads((asset / "config_full.json").read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    sim_params["max_simulation_time"] = 5.0
    raw["distributions"]["jps-distributions_0"]["parameters"].update(
        {
            "number": 4,
            "use_flow_spawning": True,
            "flow_start_time": 0,
            "flow_end_time": 3,
        }
    )
    scenario = Scenario(
        raw=raw,
        walkable_area_wkt=(asset / "geometry.wkt").read_text(encoding="utf-8").strip(),
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params=sim_params,
        source_path=None,
    )
    smoke = SmokeSpeedModel(
        _NanAfterOneSecond(), SmokeSpeedConfig(update_interval_s=100.0)
    )
    with pytest.raises(FdsDataError):
        run_scenario(scenario, seed=42, smoke_speed_model=smoke)


# --- the radiometer ---------------------------------------------------------


def test_radiometer_non_finite_reading_raises():
    xs = ys = np.array([1.0, 2.0])
    values = np.full((3, 2, 2), 3.0)
    values[2, 0, 0] = np.nan
    source = RadiometerSource(
        grid=RadiometerGrid(xs, ys, TIMES, values),
        orientation=(0.0, 0.0, 1.0),
        z_m=1.6,
        gauge_temperature_c=20.0,
        gauge_emissivity=1.0,
        n_devices=4,
        deck_path=Path("case.fds"),
        deck_sha256="0" * 64,
    )
    assert source.reading(0.0, 1.5, 1.5) == pytest.approx(3.0)
    with pytest.raises(FdsDataError, match="RADIOMETER"):
        source.reading(2.0, 1.5, 1.5)
