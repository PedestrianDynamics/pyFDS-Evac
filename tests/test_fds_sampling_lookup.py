"""The scalar point lookup of SliceFieldSampler.sample reads the cell it always did (#242)."""

from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import SliceFieldSampler, _nearest_index_scalar

AXES = {
    "uniform": np.arange(0.0, 10.01, 0.5),
    "stretched": np.array([0.0, 0.1, 0.3, 0.7, 1.5, 3.1, 6.3, 12.7]),
    "two_nodes": np.array([0.0, 1.0]),
    "one_node": np.array([2.0]),
}


def _probe_values(axis):
    """Points around, on and between the nodes, midpoints and their neighbours."""
    mids = 0.5 * (axis[:-1] + axis[1:])
    around = np.concatenate(
        [mids, np.nextafter(mids, -np.inf), np.nextafter(mids, np.inf)]
    )
    sweep = np.linspace(axis[0] - 1.0, axis[-1] + 1.0, 2001)
    return np.concatenate([axis, around, sweep])


@pytest.mark.parametrize("name", sorted(AXES))
def test_scalar_index_equals_the_numpy_index(name):
    axis = AXES[name]
    coords = axis.tolist()
    for value in _probe_values(axis):
        assert _nearest_index_scalar(coords, float(value)) == (
            SliceFieldSampler._nearest_index(axis, float(value))
        ), value


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    def __init__(self, xs, ys, data):
        self.mesh = SimpleNamespace(
            coordinates={
                "x": np.asarray(xs, dtype=float),
                "y": np.asarray(ys, dtype=float),
                "z": np.array([0.0, 1.0]),
            }
        )
        self.extent = _Extent(xs, ys)
        self.cell_centered = False
        self.data = data


class _Slice:
    def __init__(self, subslices, n_frames):
        self.subslices = subslices
        self.times = np.arange(n_frames, dtype=float)
        self.quantity = SimpleNamespace(name="SOOT EXTINCTION COEFFICIENT")

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _two_meshes(seed=3, n_frames=4):
    """Meshes x 0..5 and 5..10 on a stretched y axis, random data in every cell."""
    rng = np.random.default_rng(seed)
    ys = AXES["stretched"]
    meshes = []
    for xs in (np.arange(0.0, 5.01, 0.5), np.arange(5.0, 10.01, 0.25)):
        data = rng.random((n_frames, len(xs), len(ys)))
        meshes.append(_SubSlice(xs, ys, data))
    return SliceFieldSampler(_Slice(meshes, n_frames))


def _reference_sample(sampler, time_s, x, y):
    """``SliceFieldSampler.sample`` as it was before #242: numpy lookups."""
    t_index = sampler._time_index(float(time_s))
    subslice = sampler._find_subslice(float(x), float(y))
    if subslice is None:
        raise ValueError(f"Point ({x}, {y}) is outside the sampled FDS slice domain")
    xs, ys = sampler._axes(subslice)
    i_index = SliceFieldSampler._nearest_index(xs, float(x))
    j_index = SliceFieldSampler._nearest_index(ys, float(y))
    return float(subslice.data[t_index, i_index, j_index])


def test_sample_equals_the_reference_on_random_points():
    sampler = _two_meshes()
    rng = np.random.default_rng(7)
    points = rng.uniform([0.0, 0.0], [10.0, 12.7], size=(3000, 2))
    times = rng.uniform(0.0, 3.0, size=3000)
    for t, (x, y) in zip(times, points):
        assert sampler.sample(t, x, y) == _reference_sample(sampler, t, x, y)


def test_sample_equals_the_reference_on_nodes_midpoints_and_the_border():
    sampler = _two_meshes()
    xs = np.concatenate([np.arange(0.0, 5.01, 0.5), np.arange(5.0, 10.01, 0.25)])
    xs = np.concatenate([xs, 0.5 * (xs[:-1] + xs[1:])])
    ys = _probe_values(AXES["stretched"])
    ys = ys[(ys >= 0.0) & (ys <= 12.7)]
    for x in xs:
        for y in ys[::7]:
            assert sampler.sample(1.0, x, y) == _reference_sample(sampler, 1.0, x, y)


def test_sample_does_not_call_the_numpy_lookup(monkeypatch):
    sampler = _two_meshes()
    expected = _reference_sample(sampler, 1.0, 2.2, 1.0)

    def refuse(*_args):
        raise AssertionError("the numpy lookup was called")

    monkeypatch.setattr(SliceFieldSampler, "_nearest_index", staticmethod(refuse))
    assert sampler.sample(1.0, 2.2, 1.0) == expected


@pytest.mark.parametrize(
    ("x", "y"),
    [
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (-1.0, 1.0),
        (10.5, 1.0),
        (1.0, float("nan")),
        (1.0, float("inf")),
        (1.0, -1.0),
        (1.0, 13.0),
    ],
)
def test_a_point_outside_the_slice_still_raises(x, y):
    sampler = _two_meshes()
    with pytest.raises(ValueError, match="outside the sampled FDS slice domain"):
        sampler.sample(1.0, x, y)
