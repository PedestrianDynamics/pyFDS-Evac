"""The FDS adapter of the ASET maps reads what the engine reads (#210).

A standing person at a node, run through the engine's own FED model with its
clock and rule, crosses when the map says it does.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.analysis import AsetCriteria, aset_map, fds_fields, grid_from_walkable
from pyfds_evac.analysis.fds_fields import (
    _fed_crossing,
    _heat_crossing,
    _level_crossing,
)
from pyfds_evac.core import fed as engine_fed
from pyfds_evac.core.fds_sampling import SliceFieldSampler
from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultFedModel,
    DefaultHeatFedModel,
    FdsFedField,
    FdsHeatField,
)

THRESHOLD = 1.0
XS = np.arange(0.0, 2.01, 0.5)
YS = np.arange(0.0, 1.51, 0.5)
FRAME_TIMES = np.arange(0.0, 31.0, 5.0)


class _Slice:
    def __init__(self, name, data):
        self.times = FRAME_TIMES
        self.quantity = SimpleNamespace(name=name)
        self.extent = SimpleNamespace(z_start=1.6, z_end=1.6)
        self.subslices = [
            SimpleNamespace(
                extent=SimpleNamespace(
                    x_start=XS[0], x_end=XS[-1], y_start=YS[0], y_end=YS[-1]
                ),
                mesh=SimpleNamespace(coordinates={"x": XS, "y": YS}),
                cell_centered=False,
                data=data,
            )
        ]

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _field(name, low, high, seed):
    """A smooth-in-time, spatially varying field, data[frame, ix, iy]."""
    rng = np.random.default_rng(seed)
    base = rng.uniform(0.0, 1.0, (1, len(XS), len(YS)))
    ramp = np.linspace(0.0, 1.0, len(FRAME_TIMES))[:, None, None]
    data = low + (high - low) * np.clip(ramp * (0.4 + 1.2 * base), 0.0, 1.0)
    return SliceFieldSampler(_Slice(name, data.astype(np.float32)))


@pytest.fixture(scope="module")
def gas():
    return FdsFedField(
        _field("CARBON MONOXIDE VOLUME FRACTION", 0.0, 0.02, 1),
        _field("CARBON DIOXIDE VOLUME FRACTION", 0.0004, 0.05, 2),
        _field("OXYGEN VOLUME FRACTION", 0.209, 0.15, 3),
        hcn=_field("HYDROGEN CYANIDE VOLUME FRACTION", 0.0, 0.0004, 4),
    )


def _held(model_advance, x, y, threshold, horizon_s):
    """The engine's rule for someone held at (x, y): first update at dt = 0."""
    fed, t = 0.0, 0.0
    while t <= horizon_s:
        fed = model_advance(t, x, y, 0.0 if t == 0.0 else 1.0, fed)
        if fed >= threshold:
            return t
        t += 1.0
    return np.inf


def test_toxic_fed_crossing_equals_the_engines_held_agent_at_every_node(gas):
    model = DefaultFedModel(gas, DefaultFedConfig())

    def advance(t, x, y, dt, fed):
        return model.advance(t, x, y, dt_s=dt, current_fed=fed)[2]

    crossing = _fed_crossing(gas, THRESHOLD, DefaultFedConfig(), 1.0)
    expected = np.array(
        [_held(advance, x, y, THRESHOLD, 30.0) for x, y in zip(crossing.x, crossing.y)]
    )
    assert np.isfinite(expected).sum() > 5 and np.isinf(expected).sum() > 2, (
        "the fixture should have nodes on both sides of the threshold"
    )
    assert (crossing.first_s == expected).all()
    assert crossing.horizon_s == 30.0 and crossing.z_m == 1.6


def test_heat_fed_crossing_equals_the_engines_held_agent_at_every_node():
    sampler = _field("TEMPERATURE", 20.0, 320.0, 5)
    model = DefaultHeatFedModel(FdsHeatField(sampler), DefaultFedConfig())

    def advance(t, x, y, dt, fed):
        return model.advance(t, x, y, dt_s=dt, current_fed=fed)[2]

    crossing = _heat_crossing(sampler, 0.3, "clothed", 1.0)
    expected = np.array(
        [_held(advance, x, y, 0.3, 30.0) for x, y in zip(crossing.x, crossing.y)]
    )
    assert np.isfinite(expected).sum() > 5 and np.isinf(expected).sum() > 2
    assert (crossing.first_s == expected).all()


def test_level_crossing_reads_the_first_frame_at_or_above_the_limit():
    sampler = _field("SOOT EXTINCTION COEFFICIENT", 0.0, 1.0, 6)
    crossing = _level_crossing(sampler, "K", 0.5, "K")
    for x, y, first in zip(crossing.x, crossing.y, crossing.first_s):
        values = [sampler.sample(t, x, y) for t in FRAME_TIMES]
        hit = [t for t, v in zip(FRAME_TIMES, values) if v >= 0.5]
        assert first == (hit[0] if hit else np.inf)
    assert crossing.horizon_s == FRAME_TIMES[-1]


def test_the_fed_rates_are_the_engines_functions_not_a_copy():
    assert (
        fds_fields.default_fed_rate_per_minute is engine_fed.default_fed_rate_per_minute
    )
    assert (
        fds_fields.default_heat_fed_rate_per_minute
        is engine_fed.default_heat_fed_rate_per_minute
    )


def test_a_gas_that_does_not_cover_a_node_raises_instead_of_reading_ambient_air():
    small = _field("HYDROGEN CYANIDE VOLUME FRACTION", 0.0, 0.0004, 4)
    small._subslices[0].extent.x_end = 1.0  # stops short of the CO slice
    field = FdsFedField(
        _field("CARBON MONOXIDE VOLUME FRACTION", 0.0, 0.02, 1),
        _field("CARBON DIOXIDE VOLUME FRACTION", 0.0004, 0.05, 2),
        _field("OXYGEN VOLUME FRACTION", 0.209, 0.15, 3),
        hcn=small,
    )
    with pytest.raises(ValueError, match="outside a slice"):
        _fed_crossing(field, 0.3, DefaultFedConfig(), 1.0)


def test_time_never_runs_past_the_last_slice_frame(gas):
    crossing = _fed_crossing(gas, 100.0, DefaultFedConfig(), 1.0)
    assert np.isinf(crossing.first_s).all()  # open at the horizon, not filled with it
    assert crossing.horizon_s == FRAME_TIMES[-1]


def test_criteria_defaults_and_the_stay_class():
    c = AsetCriteria()
    assert (c.visibility_limit_m, c.visibility_c, c.k_limit_per_m) == (10.0, 3.0, 0.3)
    assert (c.temperature_c, c.fed, c.heat_fed) == (45.0, 0.3, 0.3)
    assert AsetCriteria(extinction_per_m=0.23).k_limit_per_m == 0.23  # Schröder
    assert AsetCriteria.with_stay("<5 min").temperature_c == 50.0
    assert AsetCriteria(visibility_limit_m=None).k_limit_per_m is None
    with pytest.raises(ValueError, match="stay"):
        AsetCriteria.with_stay("1 h")
    with pytest.raises(ValueError, match="positive"):
        AsetCriteria(fed=0.0)


def test_a_requested_criterion_without_its_slice_raises(tmp_path):
    fds = "assets/iso_table22_coupled/fds/a"  # gas and extinction, no TEMPERATURE
    with pytest.raises(IndexError, match="TEMPERATURE"):
        fds_fields.read_crossings(fds, AsetCriteria())


def test_tracked_deck_gives_a_map_with_the_slice_height_recorded():
    fds = "assets/iso_table22_coupled/fds/a"
    criteria = AsetCriteria(temperature_c=None, heat_fed=None, extinction_per_m=0.001)
    found = fds_fields.read_crossings(fds, criteria)
    assert [c.name for c in found] == ["K 0.001", "FED 0.3"]
    assert all(c.z_m == 1.5 for c in found)
    from shapely import box

    grid = grid_from_walkable(box(0, 0, 10, 10), 0.6)
    aset = aset_map(grid, found)
    assert set(aset.per_criterion) == {"K 0.001", "FED 0.3"}
    assert aset.horizon_s == 1150.0
    assert np.isfinite(aset.time_s[~np.isnan(aset.time_s)]).all()


def test_map_crossing_equals_the_fed_history_of_a_held_agent_in_an_engine_run():
    """ISO Table 22 case a: the held occupant reaches FED 1 at 982 s in the run."""
    from pyfds_evac import TenabilityConfig, load_scenario, run_scenario

    fds = "assets/iso_table22_coupled/fds/a"
    criteria = AsetCriteria(
        visibility_limit_m=None, temperature_c=None, heat_fed=None, fed=1.0
    )
    (crossing,) = fds_fields.read_crossings(fds, criteria)
    fed = DefaultFedModel(FdsFedField.from_fds(fds), DefaultFedConfig())
    room = load_scenario("assets/iso_table22_coupled/config_a.json")
    run = run_scenario(
        room,
        seed=420,
        fed_model=fed,
        tenability_config=TenabilityConfig(incapacitation_mode="deterministic"),
    )
    try:
        first = next(r for r in run.fed_history if r["fed_cumulative"] >= 1.0)
    finally:
        run.cleanup()
    assert first["time_s"] == 982.0
    assert (crossing.first_s == first["time_s"]).all()


def test_scaled_level_crossing_reads_a_volume_fraction_in_ppm(monkeypatch):
    sampler = _field("CARBON MONOXIDE VOLUME FRACTION", 0.0, 0.01, 7)
    monkeypatch.setattr(fds_fields, "load_slice_sampler", lambda *a, **k: sampler)
    crossing = fds_fields.read_level_crossing(
        "unused", "CARBON MONOXIDE VOLUME FRACTION", 5000.0, scale=1e6
    )
    for x, y, first in zip(crossing.x, crossing.y, crossing.first_s):
        hit = [t for t in FRAME_TIMES if sampler.sample(t, x, y) * 1e6 >= 5000.0]
        assert first == (hit[0] if hit else np.inf)
    assert np.isfinite(crossing.first_s).any() and np.isinf(crossing.first_s).any()
    assert crossing.name == "CARBON MONOXIDE VOLUME FRACTION 5000"


def test_level_crossing_rejects_a_nonpositive_limit_or_scale():
    with pytest.raises(ValueError, match="positive"):
        fds_fields.read_level_crossing("unused", "TEMPERATURE", 0.0)
    with pytest.raises(ValueError, match="positive"):
        fds_fields.read_level_crossing("unused", "TEMPERATURE", 1.0, scale=-1.0)
