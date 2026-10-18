"""Samplers on equal grids share one point lookup, and every value is unchanged (#242)."""

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core import fds_sampling
from pyfds_evac.core.fds_sampling import SliceFieldSampler

_REPO = Path(__file__).resolve().parents[1]
XS = np.arange(0.0, 10.01, 0.5)
YS = np.array([0.0, 0.1, 0.3, 0.7, 1.5, 3.1, 6.3, 12.7])


@pytest.fixture(autouse=True)
def _empty_pool():
    fds_sampling._GRID_POOL.clear()
    yield
    fds_sampling._GRID_POOL.clear()


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    def __init__(self, xs, ys, data, cell_centered=False):
        self.mesh = SimpleNamespace(
            coordinates={
                "x": np.asarray(xs, dtype=float),
                "y": np.asarray(ys, dtype=float),
                "z": np.array([0.0, 1.0]),
            }
        )
        self.extent = _Extent(xs, ys)
        self.cell_centered = cell_centered
        self.data = data


class _Slice:
    def __init__(self, subslices, n_frames=3):
        self.subslices = subslices
        self.times = np.arange(n_frames, dtype=float)
        self.quantity = SimpleNamespace(name="VOLUME FRACTION")

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _sampler(seed, xs=XS, ys=YS, cell_centered=False):
    """One slice on the given axes, filled with its own random data."""
    data = np.random.default_rng(seed).random((3, len(xs), len(ys)))
    return SliceFieldSampler(_Slice([_SubSlice(xs, ys, data, cell_centered)]))


def _grid_of(sampler):
    return sampler._grid(sampler._subslices[0])


def _reference_sample(sampler, time_s, x, y):
    """``SliceFieldSampler.sample`` as it was before #242: numpy lookups."""
    t_index = sampler._time_index(float(time_s))
    subslice = sampler._find_subslice(float(x), float(y))
    xs, ys = sampler._axes(subslice)
    i_index = SliceFieldSampler._nearest_index(xs, float(x))
    j_index = SliceFieldSampler._nearest_index(ys, float(y))
    return float(subslice.data[t_index, i_index, j_index])


def test_equal_axes_share_one_grid():
    first, second = _sampler(1), _sampler(2)
    assert _grid_of(first) is _grid_of(second)
    assert len(fds_sampling._GRID_POOL) == 1


def test_axes_that_differ_in_one_ulp_do_not_share():
    nudged = XS.copy()
    nudged[3] = np.nextafter(nudged[3], np.inf)
    assert _grid_of(_sampler(1)) is not _grid_of(_sampler(2, xs=nudged))


def test_axes_that_differ_in_one_ulp_in_y_do_not_share():
    nudged = YS.copy()
    nudged[3] = np.nextafter(nudged[3], np.inf)
    assert _grid_of(_sampler(1)) is not _grid_of(_sampler(2, ys=nudged))


def test_equal_x_axes_with_different_y_axes_read_their_own_cells():
    other_ys = np.array([0.0, 0.5, 0.9, 1.3, 2.0, 4.0, 8.0, 12.7])
    first, second = _sampler(1), _sampler(2, ys=other_ys)
    for sampler in (first, second, first, second):
        for y in (0.4, 1.0, 3.5, 6.0, 11.0):
            assert sampler.sample(1.0, 2.2, y) == _reference_sample(
                sampler, 1.0, 2.2, y
            )


def test_a_cell_centred_twin_does_not_share():
    node = _sampler(1)
    centred = _sampler(2, cell_centered=True)
    assert _grid_of(node) is not _grid_of(centred)


def test_the_second_species_at_a_point_reuses_the_indices(monkeypatch):
    species = [_sampler(seed) for seed in range(4)]
    calls = []
    real = fds_sampling._nearest_index_scalar
    monkeypatch.setattr(
        fds_sampling,
        "_nearest_index_scalar",
        lambda coords, value: calls.append(value) or real(coords, value),
    )
    for sampler in species:
        sampler.sample(1.0, 2.2, 1.0)
    assert len(calls) == 2
    species[0].sample(1.0, 2.3, 1.0)
    assert len(calls) == 4
    species[0].sample(1.0, 2.3, 1.0)
    assert len(calls) == 4
    # the same x at another y, in another y cell, is a new lookup
    value = species[0].sample(1.0, 2.3, 6.0)
    assert len(calls) == 6
    assert value == _reference_sample(species[0], 1.0, 2.3, 6.0)


def test_values_match_the_reference_for_interleaved_species():
    species = [_sampler(seed) for seed in range(4)]
    rng = np.random.default_rng(11)
    points = rng.uniform([0.0, 0.0], [10.0, 12.7], size=(1500, 2))
    for x, y in points:
        for sampler in species:
            assert sampler.sample(1.0, x, y) == _reference_sample(sampler, 1.0, x, y)
    for x, y in points[:300]:  # the same point again after other points
        for sampler in reversed(species):
            assert sampler.sample(2.0, x, y) == _reference_sample(sampler, 2.0, x, y)


def test_each_sampler_reads_its_own_data_on_a_shared_grid():
    first, second = _sampler(1), _sampler(2)
    a = first.sample(1.0, 2.2, 1.0)
    b = second.sample(1.0, 2.2, 1.0)
    assert a != b
    assert (a, b) == (
        _reference_sample(first, 1.0, 2.2, 1.0),
        _reference_sample(second, 1.0, 2.2, 1.0),
    )


def test_a_shared_grid_with_another_subslice_split_keeps_each_choice():
    """Equal axes, but one sampler holds two subslices: the border rule is its own."""
    left = np.arange(0.0, 5.01, 0.5)
    right = np.arange(5.0, 10.01, 0.5)
    rng = np.random.default_rng(5)
    split = SliceFieldSampler(
        _Slice(
            [
                _SubSlice(left, YS, rng.random((3, len(left), len(YS)))),
                _SubSlice(right, YS, rng.random((3, len(right), len(YS)))),
            ]
        )
    )
    whole = _sampler(9)
    for sampler in (split, whole, split):
        for x in (2.2, 5.0, 7.3):
            assert sampler.sample(1.0, x, 1.0) == _reference_sample(
                sampler, 1.0, x, 1.0
            )


def test_the_pool_is_bounded_and_refills(monkeypatch):
    monkeypatch.setattr(fds_sampling, "_GRID_POOL_SIZE", 2)
    samplers = [
        _sampler(seed, xs=np.arange(0.0, 10.01, step))
        for seed, step in enumerate((0.5, 0.25, 0.2, 0.1))
    ]
    for sampler in samplers:
        assert sampler.sample(1.0, 2.2, 1.0) == _reference_sample(
            sampler, 1.0, 2.2, 1.0
        )
    assert len(fds_sampling._GRID_POOL) == 2
    # a grid cleared from the pool is entered again by the next sampler
    again = _sampler(7)
    assert again.sample(1.0, 2.2, 1.0) == _reference_sample(again, 1.0, 2.2, 1.0)
    assert list(fds_sampling._GRID_POOL.values()) == [_grid_of(again)]


# --- equality on an FDS-backed deck ------------------------------------------

_T_JUNCTION_FDS = Path(
    os.environ.get(
        "T_JUNCTION_FDS",
        Path.home()
        / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
        / "fds-evac-data"
        / "t_junction"
        / "fire_2MW_PVC",
    )
)


def _run_t_junction(tmp_path, fds_dir, name):
    from pyfds_evac.core import load_scenario, run_scenario
    from pyfds_evac.core.run_config import build_run_kwargs
    from run import _build_parser

    asset = _REPO / "assets" / "t_junction"
    deck = tmp_path / name
    deck.mkdir()
    shutil.copy(asset / "config_full.json", deck / "config.json")
    shutil.copy(asset / "geometry.wkt", deck / "geometry.wkt")
    scenario = load_scenario(str(deck))
    opts = _build_parser().parse_args(
        ["--scenario", str(deck), "--fds-dir", str(fds_dir), "--seed", "1"]
    )
    result = run_scenario(scenario, **build_run_kwargs(scenario, opts))
    try:
        # JuPedSim numbers agents across runs in one process; rebase the ids
        # to the first agent of each run so the histories are comparable.
        first = min(row["agent_id"] for row in result.exit_history)
        return (
            [{**r, "agent_id": r["agent_id"] - first} for r in result.route_history],
            [{**r, "agent_id": r["agent_id"] - first} for r in result.exit_history],
            result.metrics["evacuation_time"],
        )
    finally:
        result.cleanup()


@pytest.mark.slow
@pytest.mark.external_data
@pytest.mark.skipif(
    not (_T_JUNCTION_FDS / "t_junction.smv").is_file(),
    reason="t_junction FDS output absent",
)
def test_t_junction_decisions_equal_the_numpy_lookup(
    tmp_path, monkeypatch, fds_read_only
):
    fds_dir = fds_read_only(_T_JUNCTION_FDS)
    new = _run_t_junction(tmp_path, fds_dir, "new")
    grids = len(fds_sampling._GRID_POOL)
    assert grids == 4
    monkeypatch.setattr(SliceFieldSampler, "sample", _reference_sample_checked)
    old = _run_t_junction(tmp_path, fds_dir, "old")
    assert new == old


def _reference_sample_checked(self, time_s, x, y):
    subslice = self._find_subslice(float(x), float(y))
    if subslice is None:
        raise ValueError(f"Point ({x}, {y}) is outside the sampled FDS slice domain")
    return _reference_sample(self, time_s, x, y)
