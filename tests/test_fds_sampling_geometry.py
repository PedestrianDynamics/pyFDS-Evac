"""Sampling geometry, horizon and slice choice of ``fds_sampling`` (#836).

Synthetic slices on node grids, so every expectation is a count of nodes or
frames. The grid is x = 0..10 and y = 0..4 in steps of 1 m unless a test
builds another; the frame value is the frame index.
"""

import logging
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core import fds_sampling
from pyfds_evac.core.fds_sampling import (
    FdsHorizonError,
    SliceFieldSampler,
    _nearest_indices,
    fds_output_horizon,
    select_horizontal_slice,
)


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    def __init__(self, xs, ys, n_frames=1):
        self.mesh = SimpleNamespace(
            coordinates={
                "x": np.asarray(xs, dtype=float),
                "y": np.asarray(ys, dtype=float),
                "z": np.array([0.0, 1.0]),
            }
        )
        self.extent = _Extent(xs, ys)
        self.cell_centered = False
        frames = np.arange(float(n_frames))[:, None, None]
        self.data = frames * np.ones((1, len(xs), len(ys)))


class _Slice:
    def __init__(self, subslices, times=(0.0,)):
        self.subslices = subslices
        self.times = np.asarray(times, dtype=float)
        self.quantity = SimpleNamespace(name="SOOT EXTINCTION COEFFICIENT")

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


XS = np.arange(11.0)
YS = np.arange(5.0)


def _sampler(subslices=None, **kwargs):
    return SliceFieldSampler(_Slice(subslices or [_SubSlice(XS, YS)]), **kwargs)


def _only_outside(parts):
    assert len(parts) == 1
    assert (parts[0].t_start, parts[0].t_end) == (0.0, 1.0)
    assert parts[0].fractions is None and parts[0].subslice is None


# --- Clipping to the extent -------------------------------------------------


@pytest.mark.parametrize(
    "segment",
    [
        (11.0, 1.0, 11.0, 3.0),  # vertical, right of x_end = 10
        (-1.0, 1.0, -1.0, 3.0),  # vertical, left of x_start = 0
        (2.0, 5.0, 8.0, 5.0),  # horizontal, above y_end = 4
        (2.0, -1.0, 8.0, -1.0),  # horizontal, below y_start = 0
    ],
)
def test_a_segment_parallel_to_and_outside_an_edge_reads_nothing(segment):
    """The y (or x) range of the segment lies inside the extent, its other
    coordinate is one metre beyond an edge: no point of it is covered, so
    the line is one part outside the slice."""
    _only_outside(_sampler().line_parts(*segment))


@pytest.mark.parametrize(
    "segment",
    [
        (10.0, 4.0, 12.0, 6.0),  # touches the corner (10, 4) at t = 0
        (-2.0, -2.0, 0.0, 0.0),  # touches the corner (0, 0) at t = 1
    ],
)
def test_a_segment_touching_a_corner_counts_as_outside(segment):
    """A span of zero length is not a part inside: the line stays one part
    outside, with no zero-length grid part."""
    _only_outside(_sampler().line_parts(*segment))


def test_a_segment_along_an_edge_is_inside():
    """x = 10 is the closed extent's edge: the whole segment is covered, the
    five nodes y = 0..4 give five samples at 0, 1/4, ... 1."""
    (part,) = _sampler().line_parts(10.0, 0.0, 10.0, 4.0)
    assert part.subslice is not None
    assert (part.t_start, part.t_end) == (0.0, 1.0)
    np.testing.assert_allclose(part.fractions, [0.0, 0.25, 0.5, 0.75, 1.0])


# --- Overlapping subslices --------------------------------------------------


def test_the_first_subslice_takes_the_overlap_band():
    """A covers x = 0..6, B covers x = 5..10, the line runs y = 1, x = 0..10.
    A takes 0..0.6 (x = 0..6), B the rest, 0.6..1.0; B does not start at its
    own edge 0.5."""
    a = _SubSlice(np.arange(7.0), YS)
    b = _SubSlice(np.arange(5.0, 11.0), YS)
    first, second = _sampler([a, b]).line_parts(0.0, 1.0, 10.0, 1.0)
    assert (first.subslice, first.t_start, first.t_end) == (a, 0.0, 0.6)
    assert (second.subslice, second.t_start, second.t_end) == (b, 0.6, 1.0)


def test_a_subslice_inside_an_earlier_one_adds_no_part():
    """B (x = 3..10) lies inside A (x = 0..10) and ends where the line ends:
    A takes the whole line and nothing is left for B, not even a part of
    zero length at t = 1."""
    a = _SubSlice(XS, YS)
    b = _SubSlice(np.arange(3.0, 11.0), YS)
    (part,) = _sampler([a, b]).line_parts(0.0, 1.0, 10.0, 1.0)
    assert part.subslice is a
    assert (part.t_start, part.t_end) == (0.0, 1.0)


# --- Samples of one part ----------------------------------------------------


def test_ends_in_one_column_but_two_rows_give_two_samples():
    """(2.0, 0.0)-(2.4, 0.3) on a grid of x = 0..10 and y = 0, 0.25, ...:
    x is the dominant axis and both ends read column 2 (2.4 is nearer 2 than
    3), but the rows differ: 0 (y = 0) and 1 (y = 0.3 is nearer 0.25 than
    0.5). One sample per end, at 0 and 1, and none between."""
    ys = np.arange(0.0, 4.01, 0.25)
    (part,) = _sampler([_SubSlice(XS, ys)]).line_parts(2.0, 0.0, 2.4, 0.3)
    np.testing.assert_allclose(part.fractions, [0.0, 1.0])
    np.testing.assert_array_equal(part.cells[0], [2, 2])
    np.testing.assert_array_equal(part.cells[1], [0, 1])


def test_ends_in_one_cell_give_one_sample():
    """(2.0, 0.0)-(2.1, 0.05): both ends read node (2, 0)."""
    (part,) = _sampler().line_parts(2.0, 0.0, 2.1, 0.05)
    np.testing.assert_allclose(part.fractions, [0.0])


def test_a_start_between_two_nodes_reads_the_lower_one():
    """x = 0.5 and 3.5 sit midway between nodes: ties go to the lower node,
    so the cells along x are 0, 1, 2, 3 (nodes 1 and 2 lie strictly between)."""
    (part,) = _sampler().line_parts(0.5, 0.0, 3.5, 0.0)
    np.testing.assert_array_equal(part.cells[0], [0, 1, 2, 3])


def test_nearest_indices_ties_go_to_the_lower_value_position():
    coords = np.array([0.0, 1.0, 2.0])
    np.testing.assert_array_equal(_nearest_indices(coords, [0.5, 1.5]), [0, 1])


def test_nearest_indices_of_a_single_position_axis_is_zero():
    """With one position every value reads index 0, never the wrap-around -1."""
    result = _nearest_indices(np.array([3.0]), [1.0, 5.0])
    np.testing.assert_array_equal(result, [0, 0])


def test_lines_sharing_start_and_x_end_are_kept_apart():
    """The cache is keyed on the four coordinates. (2, 0)-(8, 0) reads row 0
    at the seven nodes x = 2..8; (2, 0)-(8, 2) rises one third of a metre per
    node: y = 0, 1/3, 2/3, 1, 4/3, 5/3, 2 reads rows 0, 0, 1, 1, 1, 2, 2."""
    sampler = _sampler()
    (flat,) = sampler.line_parts(2.0, 0.0, 8.0, 0.0)
    (rising,) = sampler.line_parts(2.0, 0.0, 8.0, 2.0)
    np.testing.assert_array_equal(flat.cells[1], [0] * 7)
    np.testing.assert_array_equal(rising.cells[1], [0, 0, 1, 1, 1, 2, 2])


# --- Horizon of the sampler -------------------------------------------------

FRAMES = np.arange(0.0, 11.0)  # 0..10 s every 1 s: horizon 10 + 1 = 11 s
CLIPPED = [0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.0]  # horizon 10 + 1.5 = 11.5 s


def _timed(times, **kwargs):
    sub = _SubSlice(XS, YS, n_frames=len(times))
    return SliceFieldSampler(_Slice([sub], times=times), **kwargs)


@pytest.mark.parametrize(("times", "horizon"), [(FRAMES, 11.0), (CLIPPED, 11.5)])
def test_the_horizon_itself_passes_and_the_next_float_raises(times, horizon):
    """Last frame plus the largest output interval: 10 + 1 and 10 + 1.5."""
    sampler = _timed(times)
    assert sampler.sample(horizon, 1.0, 1.0) == len(times) - 1
    with pytest.raises(FdsHorizonError):
        sampler.sample(float(np.nextafter(horizon, np.inf)), 1.0, 1.0)


def test_read_cells_checks_the_horizon_of_a_time_vector():
    """Five samples along y = 1 read frames nearest 0, 2, 4, 6 and 11 s: the
    last time is the horizon, held at frame 10. One float later it raises."""
    sampler = _timed(FRAMES)
    (part,) = sampler.line_parts(0.0, 1.0, 4.0, 1.0)
    assert len(part.fractions) == 5
    values = sampler.read_cells(part, np.array([0.0, 2.0, 4.0, 6.0, 11.0]))
    np.testing.assert_array_equal(values, [0, 2, 4, 6, 10])
    late = np.array([0.0, 2.0, 4.0, 6.0, np.nextafter(11.0, np.inf)])
    with pytest.raises(FdsHorizonError):
        sampler.read_cells(part, late)


def test_read_cells_holds_the_last_frame_with_the_flag(caplog):
    sampler = _timed(FRAMES, allow_horizon_hold=True)
    (part,) = sampler.line_parts(0.0, 1.0, 4.0, 1.0)
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        values = sampler.read_cells(part, np.array([0.0, 2.0, 4.0, 6.0, 30.0]))
    np.testing.assert_array_equal(values, [0, 2, 4, 6, 10])
    assert caplog.text.count("past the FDS output") == 1


# --- Horizon of a case ------------------------------------------------------


def _case(*time_arrays):
    return SimpleNamespace(
        slices=[SimpleNamespace(times=np.asarray(t, dtype=float)) for t in time_arrays]
    )


def test_the_slice_that_ends_first_sets_the_case_horizon():
    """A ends at 10 s with a 1 s interval (horizon 11 s), B at 20 s with a 5 s
    interval (horizon 25 s): the earlier one wins, in either order."""
    a = np.arange(0.0, 11.0)
    b = np.arange(0.0, 21.0, 5.0)
    assert fds_output_horizon("x", simulation=_case(a, b)) == (10.0, 1.0)
    assert fds_output_horizon("x", simulation=_case(b, a)) == (10.0, 1.0)


def test_a_single_frame_slice_does_not_set_the_case_horizon():
    """The one-frame slice would give (0, 0), the earliest of all; it is
    skipped. With no other slice there is no horizon."""
    a = np.arange(0.0, 11.0)
    assert fds_output_horizon("x", simulation=_case([0.0], a)) == (10.0, 1.0)
    assert fds_output_horizon("x", simulation=_case([0.0])) is None


# --- Choice of the slice ----------------------------------------------------


def _at(z, name):
    return SimpleNamespace(extent=SimpleNamespace(z_start=z, z_end=z), name=name)


def test_the_first_of_two_equally_near_slices_is_chosen():
    """1.0 m and 2.0 m are both 0.5 m from 1.5 m, and two slices share 3.0 m:
    declaration order breaks the tie, in either order."""
    low, high = _at(1.0, "low"), _at(2.0, "high")
    assert select_horizontal_slice([low, high], 1.5, "q", "d") is low
    assert select_horizontal_slice([high, low], 1.5, "q", "d") is high
    first, second = _at(3.0, "first"), _at(3.0, "second")
    assert select_horizontal_slice([first, second], 3.0, "q", "d") is first


def test_the_height_warning_stops_at_the_tolerance(caplog):
    """The tolerance is 0.2 m: a slice 0.2 m from the requested height is
    accepted silently, one 0.21 m away is reported."""
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        select_horizontal_slice([_at(2.0, "a"), _at(9.0, "b")], 1.8, "q", "d")
    assert caplog.text == ""
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        select_horizontal_slice([_at(2.01, "a"), _at(9.0, "b")], 1.8, "q", "d")
    assert "0.21 m away" in caplog.text
