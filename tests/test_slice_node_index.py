"""`SliceFieldSampler` reads the FDS node nearest to the query point (#212).

FDS slices are node-centred by default: fdsreader gives one value per mesh
node inside the slice extent. With CELL_CENTERED=T it gives one value per
cell, at the midpoint of its two nodes. The sampler used to space `shape`
cells over the extent with half-cell offsets, which picks the wrong node for
about a quarter of positions on typical grids (tending to 1/4 as the number of
cells grows), up to almost one spacing from the query point.

The fake slices store `x_i + 100*y_j` at value position (i, j), so the
returned value names the position that was read.
"""

from pathlib import Path

import numpy as np
import pytest
from fdsreader.slcf.slice import SubSlice
from fdsreader.utils import Dimension, Extent

from pyfds_evac.core.fds_sampling import SliceFieldSampler


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _Mesh:
    def __init__(self, x_nodes, y_nodes, z_nodes=(0.0, 1.0)):
        self.coordinates = {
            "x": np.asarray(x_nodes, dtype=float),
            "y": np.asarray(y_nodes, dtype=float),
            "z": np.asarray(z_nodes, dtype=float),
        }


class _SubSlice:
    """Horizontal subslice over mesh nodes; values sit at ``xs`` x ``ys``."""

    def __init__(self, x_nodes, y_nodes, xs, ys, extent=None, cell_centered=False):
        self.mesh = _Mesh(x_nodes, y_nodes)
        self.extent = extent or _Extent(x_nodes, y_nodes)
        self.cell_centered = cell_centered
        self.shape = (len(xs), len(ys))
        grid = np.add.outer(np.asarray(xs), 100.0 * np.asarray(ys))
        self.data = grid[np.newaxis, :, :]


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
    sampler = _sampler(_SubSlice(xs, ys, xs, ys))
    for x in _QUERIES:
        y = 0.37 + 0.3 * (x % 1.0)
        expected = _nearest(xs, x) + 100.0 * _nearest(ys, y)
        assert sampler.sample(0.0, x, y) == pytest.approx(expected), (x, y)


def test_cell_centred_slice_reads_the_nearest_centre():
    edges = np.linspace(0.0, 5.0, 11)
    xs = 0.5 * (edges[:-1] + edges[1:])  # 10 cell centres
    y_edges = np.linspace(0.0, 2.0, 5)
    ys = np.array([0.25, 0.75, 1.25, 1.75])
    sub = _SubSlice(edges, y_edges, xs, ys, cell_centered=True)
    sampler = _sampler(sub)
    for x in _QUERIES:
        y = 0.41 + 0.3 * (x % 1.0)
        expected = _nearest(xs, x) + 100.0 * _nearest(ys, y)
        assert sampler.sample(0.0, x, y) == pytest.approx(expected), (x, y)


def test_axes_are_not_swapped_on_a_non_square_slice():
    xs = np.linspace(0.0, 6.0, 13)
    ys = np.linspace(0.0, 2.0, 5)
    sampler = _sampler(_SubSlice(xs, ys, xs, ys))
    assert sampler.sample(0.0, 5.0, 1.5) == pytest.approx(5.0 + 150.0)


_ISO21 = Path("assets/iso_table21_coupled/fds")


@pytest.mark.skipif(not _ISO21.is_dir(), reason="committed ISO 21 FDS output absent")
def test_committed_fds_grid_reads_the_nearest_node():
    """Real FDS node geometry; values encode the node, since the prescribed
    smoke is uniform and would hide a wrong index."""
    fdsreader = pytest.importorskip("fdsreader")
    sim = fdsreader.Simulation(str(_ISO21))
    real = sim.slices.filter_by_quantity("SOOT EXTINCTION COEFFICIENT")[0].subslices[0]
    assert not real.cell_centered
    coords = real.get_coordinates()
    xs, ys = coords["x"], coords["y"]
    ext = real.extent
    sub = _SubSlice(
        real.mesh.coordinates["x"], real.mesh.coordinates["y"], xs, ys, extent=ext
    )
    sampler = _sampler(sub)
    y = 0.5 * (ext.y_start + ext.y_end) + 0.013
    for x in np.linspace(ext.x_start + 0.013, ext.x_end - 0.013, 997):
        expected = _nearest(xs, x) + 100.0 * _nearest(ys, y)
        assert sampler.sample(0.0, x, y) == pytest.approx(expected), x


def test_midpoint_between_nodes_reads_the_lower_node():
    xs = np.array([0.0, 1.0, 2.0])
    ys = np.array([0.0, 1.0])
    sampler = _sampler(_SubSlice(xs, ys, xs, ys))
    assert sampler.sample(0.0, 1.5, 0.5) == pytest.approx(1.0 + 0.0)


def test_node_axis_is_limited_to_the_slice_extent():
    x_nodes = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    ys = np.array([0.0, 1.0])
    xs = np.array([1.0, 2.0, 3.0])  # the slice spans nodes 1..3 only
    sub = _SubSlice(x_nodes, ys, xs, ys, extent=_Extent([1.0, 3.0], ys))
    assert _sampler(sub).sample(0.0, 2.9, 0.2) == pytest.approx(3.0)


def test_cell_centred_stretched_grid_reads_the_containing_cell():
    """Cell edges [0, 1, 3, 6] have centres [0.5, 2, 4.5]."""
    edges = np.array([0.0, 1.0, 3.0, 6.0])
    y_edges = np.array([0.0, 1.0])
    sub = _SubSlice(edges, y_edges, [0.5, 2.0, 4.5], [0.5], cell_centered=True)
    sampler = _sampler(sub)
    assert sampler.sample(0.0, 3.0, 0.5) == pytest.approx(2.0 + 50.0)
    assert sampler.sample(0.0, 3.4, 0.5) == pytest.approx(4.5 + 50.0)


class _CellCentredParent:
    cell_centered = True


def test_real_cell_centred_subslice_with_one_z_cell():
    """fdsreader's own ``get_coordinates`` fails on this mesh: it shifts every
    axis by the first half-width and indexes a second z node."""
    mesh = _Mesh([0.0, 1.0, 3.0, 6.0], [0.0, 1.0, 2.0], z_nodes=[0.0, 1.0])
    real = SubSlice(
        _CellCentredParent(),
        "unused.sf",
        Dimension(4, 3, 1),
        Extent(0, 6, 0, 2, 1, 1),
        mesh,
    )
    xs, ys = SliceFieldSampler(_Slice(real))._axes(real)
    np.testing.assert_allclose(xs, [0.5, 2.0, 4.5])
    np.testing.assert_allclose(ys, [0.5, 1.5])
