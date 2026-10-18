"""A mesh-border point reads the lowest-index subslice, whatever came before (#239)."""

from types import SimpleNamespace

import numpy as np

from pyfds_evac.core.fds_sampling import SliceFieldSampler


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    def __init__(self, xs, ys, value):
        self.mesh = SimpleNamespace(
            coordinates={
                "x": np.asarray(xs, dtype=float),
                "y": np.asarray(ys, dtype=float),
                "z": np.array([0.0, 1.0]),
            }
        )
        self.extent = _Extent(xs, ys)
        self.cell_centered = False
        self.data = np.full((1, len(xs), len(ys)), float(value))


class _Slice:
    def __init__(self, subslices):
        self.subslices = subslices
        self.times = np.array([0.0])
        self.quantity = SimpleNamespace(name="SOOT EXTINCTION COEFFICIENT")

    def get_nearest_timestep(self, time_s):
        return 0


YS = [0.0, 1.0, 2.0]


def _two_meshes():
    """Mesh A x 0..5 holds 1.0, mesh B x 5..10 holds 2.0; x = 5 is shared."""
    a = _SubSlice([0.0, 2.5, 5.0], YS, 1.0)
    b = _SubSlice([5.0, 7.5, 10.0], YS, 2.0)
    return SliceFieldSampler(_Slice([a, b])), a, b


def test_border_reads_the_first_subslice_after_a_read_in_the_second():
    sampler, _a, _b = _two_meshes()
    sampler.sample(0.0, 7.5, 1.0)  # primes the remembered subslice with B
    assert sampler.sample(0.0, 5.0, 1.0) == 1.0


def test_border_reads_the_first_subslice_after_a_read_in_the_first():
    sampler, _a, _b = _two_meshes()
    sampler.sample(0.0, 2.5, 1.0)
    assert sampler.sample(0.0, 5.0, 1.0) == 1.0


def test_border_value_does_not_depend_on_history():
    sampler, _a, _b = _two_meshes()
    seen = set()
    for prime in ((2.5, 1.0), (7.5, 1.0), (5.0, 0.0), (10.0, 2.0)):
        sampler.sample(0.0, *prime)
        seen.add(sampler.sample(0.0, 5.0, 1.0))
    assert seen == {1.0}


def test_interior_point_keeps_the_remembered_subslice():
    sampler, _a, b = _two_meshes()
    sampler.sample(0.0, 7.5, 1.0)
    assert sampler._last_subslice is b
    assert sampler.sample(0.0, 7.0, 1.0) == 2.0
    assert sampler._last_subslice is b


def test_covers_is_unchanged_on_the_border():
    sampler, _a, _b = _two_meshes()
    assert sampler.covers(5.0, 1.0)
    assert not sampler.covers(10.5, 1.0)


def test_overlap_band_reads_the_first_subslice_after_a_read_in_the_second():
    a = _SubSlice([0.0, 3.0, 6.0], YS, 1.0)
    b = _SubSlice([5.0, 7.5, 10.0], YS, 2.0)
    sampler = SliceFieldSampler(_Slice([a, b]))
    assert sampler.sample(0.0, 5.5, 1.0) == 1.0
    sampler.sample(0.0, 7.5, 1.0)  # primes the remembered subslice with B
    assert sampler.sample(0.0, 5.5, 1.0) == 1.0


def test_interior_point_skips_the_ordered_scan():
    sampler, _a, b = _two_meshes()
    sampler.sample(0.0, 7.5, 1.0)

    class _NoScan:
        def __iter__(self):
            raise AssertionError("interior point went through the ordered scan")

    sampler._subslices = _NoScan()
    assert sampler.sample(0.0, 7.0, 1.0) == 2.0
