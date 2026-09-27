"""`SliceFieldSampler` reads the FDS node nearest to the query point (#212).

FDS slices are node-centred by default: fdsreader gives n+1 values at
`start + i*(end-start)/n`, i.e. `subslice.get_coordinates()`. The sampler used
to space `shape` cells over the extent with half-cell offsets, which picks the
wrong node for about a quarter of positions, up to almost one spacing away.

The fake slices store `x_i + 100*y_j` at node (i, j), so the returned value
names the node that was read.
"""

from pathlib import Path

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import SliceFieldSampler


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    def __init__(self, xs, ys, extent_xs=None, extent_ys=None, cell_centered=False):
        self._coords = {"x": np.asarray(xs), "y": np.asarray(ys)}
        self.extent = _Extent(
            xs if extent_xs is None else extent_xs,
            ys if extent_ys is None else extent_ys,
        )
        self.cell_centered = cell_centered
        self.shape = (len(xs), len(ys))
        grid = np.add.outer(np.asarray(xs), 100.0 * np.asarray(ys))
        self.data = grid[np.newaxis, :, :]

    def get_coordinates(self, ignore_cell_centered=False):
        return self._coords


class _Slice:
    def __init__(self, subslice):
        self.subslices = [subslice]

    def get_nearest_timestep(self, time_s):
        return 0


def _sampler(subslice):
    return SliceFieldSampler(_Slice(subslice))


def _nearest(values, v):
    return values[int(np.argmin(np.abs(values - v)))]


# Offsets avoid exact midpoints between nodes, where either neighbour is right.
_QUERIES = np.linspace(0.013, 4.987, 211)


def test_node_centred_slice_reads_the_nearest_node():
    xs = np.linspace(0.0, 5.0, 11)  # 10 intervals of 0.5 m, 11 nodes
    ys = np.linspace(0.0, 2.0, 5)
    sampler = _sampler(_SubSlice(xs, ys))
    for x in _QUERIES:
        y = 0.37 + 0.3 * (x % 1.0)
        expected = _nearest(xs, x) + 100.0 * _nearest(ys, y)
        assert sampler.sample(0.0, x, y) == pytest.approx(expected), (x, y)


def test_cell_centred_slice_reads_the_nearest_centre():
    edges = np.linspace(0.0, 5.0, 11)
    xs = 0.5 * (edges[:-1] + edges[1:])  # 10 cell centres
    ys = np.array([0.25, 0.75, 1.25, 1.75])
    sub = _SubSlice(
        xs, ys, extent_xs=edges, extent_ys=np.linspace(0.0, 2.0, 5), cell_centered=True
    )
    sampler = _sampler(sub)
    for x in _QUERIES:
        y = 0.41 + 0.3 * (x % 1.0)
        expected = _nearest(xs, x) + 100.0 * _nearest(ys, y)
        assert sampler.sample(0.0, x, y) == pytest.approx(expected), (x, y)


def test_axes_are_not_swapped_on_a_non_square_slice():
    xs = np.linspace(0.0, 6.0, 13)
    ys = np.linspace(0.0, 2.0, 5)
    sampler = _sampler(_SubSlice(xs, ys))
    assert sampler.sample(0.0, 5.0, 1.5) == pytest.approx(5.0 + 150.0)


_ISO21 = Path("assets/iso_table21_coupled/fds")


@pytest.mark.skipif(not _ISO21.is_dir(), reason="committed ISO 21 FDS output absent")
def test_committed_fds_grid_reads_the_nearest_node():
    """Real FDS node geometry; values encode the node, since the prescribed
    smoke is uniform and would hide a wrong index."""
    fdsreader = pytest.importorskip("fdsreader")
    sim = fdsreader.Simulation(str(_ISO21))
    real = sim.slices.filter_by_quantity("SOOT EXTINCTION COEFFICIENT")[0].subslices[0]
    coords = real.get_coordinates()
    xs, ys = coords["x"], coords["y"]
    ext = real.extent
    sub = _SubSlice(
        xs, ys, extent_xs=[ext.x_start, ext.x_end], extent_ys=[ext.y_start, ext.y_end]
    )
    sampler = _sampler(sub)
    y = 0.5 * (ext.y_start + ext.y_end) + 0.013
    for x in np.linspace(ext.x_start + 0.013, ext.x_end - 0.013, 997):
        expected = _nearest(xs, x) + 100.0 * _nearest(ys, y)
        assert sampler.sample(0.0, x, y) == pytest.approx(expected), x
