"""Route smoke is read once per FDS grid cell along a line (#653).

With a fixed step measured from the agent, samples slid on and off a plume
narrower than the step: route tau jumped from 0 to 18.0 when the agent moved
0.1 m, through a plume whose optical depth is 10.0. FDS+Evac ``See_door``
reads one value per cell of the grid along the line instead. These tests
use synthetic slices in a real ``ExtinctionField``, so every expected value
is a count of grid cells.

The band field: node-centred values every 0.25 m on x = 0..20, K = 10 /m
at the four nodes 10.00..10.75 and 0 elsewhere, so a 1.0 m core under
nearest-node lookup, and an optical depth of 10.0 across it.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import FdsDomainError, SliceFieldSampler
from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    _FedRateAsExtinction,
    _foresight_clock,
    _los_stats,
    _polyline_stats,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField, ExtinctionField

STEP_M = 2.0  # sampling_step_m of the shipped decks


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    """Node-centred horizontal subslice; ``values[i, j]`` at node (xs[i], ys[j])."""

    def __init__(self, xs, ys, values, n_frames=1):
        self.mesh = SimpleNamespace(
            coordinates={
                "x": np.asarray(xs, dtype=float),
                "y": np.asarray(ys, dtype=float),
                "z": np.array([0.0, 1.0]),
            }
        )
        self.extent = _Extent(xs, ys)
        self.cell_centered = False
        self.data = np.repeat(np.asarray(values, dtype=float)[None], n_frames, 0)


class _Slice:
    def __init__(self, subslices, n_frames=1):
        self.subslices = subslices
        self.times = np.arange(float(n_frames))
        self.quantity = SimpleNamespace(name="SOOT EXTINCTION COEFFICIENT")

    def get_nearest_timestep(self, time_s):
        return int(np.clip(round(time_s), 0, len(self.times) - 1))


def _field(subslices, n_frames=1, **kwargs):
    return ExtinctionField(SliceFieldSampler(_Slice(subslices, n_frames)), **kwargs)


BAND_XS = np.arange(81) * 0.25
BAND_YS = np.arange(-16, 17) * 0.25


def _band_subslice(n_frames=1):
    core = (BAND_XS >= 10.0) & (BAND_XS <= 10.75)
    values = np.where(core[:, None], 10.0, 0.0) * np.ones(len(BAND_YS))
    return _SubSlice(BAND_XS, BAND_YS, values, n_frames)


def _band():
    return _field([_band_subslice()])


def _tau(field, x0, y0, x1, y1, clock=None):
    length = math.hypot(x1 - x0, y1 - y0)
    k_avg, k_max = _los_stats(x0, y0, x1, y1, 0.0, field, STEP_M, length, clock)
    return k_avg * length, k_max


def _node(v):
    return int(np.argmin(np.abs(BAND_XS - v)))


def test_band_fixed_position_counts_the_cells():
    # Nodes 2.00..20.00 are 73 cells, four of them at K = 10: tau = 18*40/73.
    # The 2 m step reads 10 samples, one on node 10.0, and gives 18.0.
    tau, k_max = _tau(_band(), 2.0, 0.0, 20.0, 0.0)
    assert tau == pytest.approx(18.0 * 40.0 / 73.0, abs=1e-6)
    assert k_max == 10.0
    assert abs(tau - 10.0) <= 0.25


def test_band_sliding_agent_keeps_every_cell():
    # At x_a = 1.9 the 2 m step missed the core (tau 0); here every position
    # reads all four core cells, and tau = 40 * L / n with n the cells from
    # the agent's cell to the end cell.
    field = _band()
    for x_a in np.round(np.arange(0.0, 9.41, 0.1), 10):
        tau, k_max = _tau(field, float(x_a), 0.0, 20.0, 0.0)
        n_cells = _node(20.0) - _node(x_a) + 1
        assert k_max == 10.0, x_a
        assert tau == pytest.approx(40.0 * (20.0 - x_a) / n_cells, rel=1e-12), x_a


def test_band_diagonal_leg_does_not_skip_the_plume():
    # A 30 degree leg marches the x columns; the core is crossed over
    # 1.0 / cos 30 = 1.155 m, so tau is near K * w / cos 30 = 11.55.
    angle = math.radians(30.0)
    x0, x1 = 4.0, 16.0
    y0 = -0.5 * (x1 - x0) * math.tan(angle)
    tau, k_max = _tau(_band(), x0, y0, x1, -y0)
    assert k_max == 10.0
    assert abs(tau - 10.0 / math.cos(angle)) <= 10.0 * 0.25 / math.cos(angle)


def test_band_along_y_is_marched_by_rows():
    # The same band across y: x and y swapped, so a leg along y (and one
    # steeper than 45 degrees) marches rows; tau = 18 * 40 / 73 again.
    core = (BAND_XS >= 10.0) & (BAND_XS <= 10.75)
    values = np.where(core[None, :], 10.0, 0.0) * np.ones((len(BAND_YS), 1))
    field = _field([_SubSlice(BAND_YS, BAND_XS, values)])
    tau, k_max = _tau(field, 0.0, 2.0, 0.0, 20.0)
    assert tau == pytest.approx(18.0 * 40.0 / 73.0, abs=1e-6)
    assert k_max == 10.0
    tau, k_max = _tau(field, -1.0, 4.0, 1.0, 16.0)
    assert k_max == 10.0
    assert tau == pytest.approx(10.0 * math.hypot(2.0, 12.0) / 12.0, abs=2.5)


def test_lines_from_one_start_are_kept_apart():
    # Grid parts are cached per line; a line sharing only its start with
    # another must not reuse that line's cells.
    field = _band()
    assert _tau(field, 2.0, 0.0, 20.0, 0.0)[1] == 10.0
    tau, k_max = _tau(field, 2.0, 0.0, 9.0, 0.0)
    assert (tau, k_max) == (0.0, 0.0)
    parts = field.line_parts(2.0, 0.0, 9.0, 0.0)
    assert len(parts) == 1 and len(parts[0].fractions) == _node(9.0) - _node(2.0) + 1


def test_cell_centred_band_reads_cell_centres():
    # CELL_CENTERED=T: values sit at the midpoints of the 0.25 m cells,
    # 0.125..19.875; the core is the four cells 10.0..11.0, centres
    # 10.125..10.875. (2.1, 0)-(20, 0) runs from the cell centred at 2.125
    # to the one at 19.875, 72 cells: tau = 17.9 * 40 / 72.
    centres = 0.5 * (BAND_XS[:-1] + BAND_XS[1:])
    ys = 0.5 * (BAND_YS[:-1] + BAND_YS[1:])
    core = (centres > 10.0) & (centres < 11.0)
    sub = _SubSlice(
        BAND_XS, BAND_YS, np.outer(np.where(core, 10.0, 0.0), np.ones(len(ys)))
    )
    sub.cell_centered = True
    tau, k_max = _tau(_field([sub]), 2.1, 0.0, 20.0, 0.0)
    assert tau == pytest.approx(17.9 * 40.0 / 72.0, abs=1e-9)
    assert k_max == 10.0


def test_line_parts_are_read_only():
    parts = _band().line_parts(2.0, 0.0, 20.0, 0.0)
    assert isinstance(parts, tuple)
    with pytest.raises(ValueError):
        parts[0].fractions[0] = 0.5


def test_constant_slice_reads_its_value():
    field = _field([_SubSlice(BAND_XS, BAND_YS, np.full((81, 33), 0.7))])
    k_avg, k_max = _los_stats(0.3, -1.1, 17.9, 2.2, 0.0, field, STEP_M, 17.9)
    assert k_avg == pytest.approx(0.7, abs=1e-15)
    assert k_max == pytest.approx(0.7, abs=1e-15)


def test_samplers_without_a_grid_keep_the_step():
    # ConstantExtinctionField and the FED rate of the #171 walk dose have no
    # grid: they are read every sampling_step_m, as before.
    assert not hasattr(ConstantExtinctionField(0.7), "line_parts")
    fed = _FedRateAsExtinction(SimpleNamespace(sample_fed_rate=lambda t, x, y: x))
    assert not hasattr(fed, "line_parts")
    k_avg, _ = _los_stats(0.0, 0.0, 10.0, 0.0, 0.0, fed, STEP_M, 10.0)
    assert k_avg == pytest.approx(5.0)  # samples at x = 0, 2, ..., 10


class _Recording:
    """A sampler wrapper that records every (time, fraction) it reads."""

    def __init__(self, sampler):
        self._sampler = sampler
        self.calls = []
        self.quantity = sampler.quantity

    def sample(self, time_s, x, y):
        self.calls.append((time_s, x))
        return self._sampler.sample(time_s, x, y)

    def line_parts(self, *line):
        return self._sampler.line_parts(*line)

    def read_cells(self, part, times):
        self.calls.extend(zip(times.tolist(), part.fractions.tolist()))
        return self._sampler.read_cells(part, times)

    def covers(self, x, y):
        return self._sampler.covers(x, y)


def test_foresight_reads_each_cell_when_it_is_reached():
    # #650 kept: each sample is read at clock.at(s) for its own arc length.
    config = RouteCostConfig(anticipate=True, base_speed_m_per_s=1.0)
    clock = _foresight_clock(0.0, 0.0, config, math.inf, None)
    band = SliceFieldSampler(_Slice([_band_subslice(50)], 50))
    recorder = _Recording(band)
    _los_stats(2.1, 0.0, 20.0, 0.0, 0.0, ExtinctionField(recorder), STEP_M, 17.9, clock)
    xs = [2.1 + f * 17.9 for _, f in recorder.calls]
    assert xs[0] == 2.1
    assert xs[1:-1] == pytest.approx(list(BAND_XS[9:80]), abs=1e-12)
    assert xs[-1] == pytest.approx(20.0, abs=1e-12)
    for time_s, f in recorder.calls:
        assert time_s == clock.at(f * 17.9)


def test_two_subslices_are_marched_on_their_own_grids():
    # x = 0..10 at 0.5 m, then 10..20 at 0.25 m; K = x^2 reads the position.
    xs_a, xs_b = np.arange(21) * 0.5, 10.0 + np.arange(41) * 0.25
    ys = np.array([-1.0, 0.0, 1.0])
    recorder = _Recording(
        SliceFieldSampler(
            _Slice(
                [
                    _SubSlice(xs_a, ys, np.outer(xs_a**2, np.ones(3))),
                    _SubSlice(xs_b, ys, np.outer(xs_b**2, np.ones(3))),
                ]
            )
        )
    )
    k_avg, k_max = _los_stats(
        0.0, 0.0, 20.0, 0.0, 0.0, ExtinctionField(recorder), STEP_M, 20.0
    )
    assert len(recorder.calls) == 21 + 41
    mean_a, mean_b = np.mean(xs_a**2), np.mean(xs_b**2)
    assert k_avg == pytest.approx(0.5 * mean_a + 0.5 * mean_b, rel=1e-12)
    assert k_max == 400.0


def _short_slice(**kwargs):
    xs = np.arange(21) * 0.5  # x = 0..10
    ys = np.array([-1.0, 0.0, 1.0])
    return _field([_SubSlice(xs, ys, np.ones((21, 3)))], **kwargs)


def test_line_leaving_the_slice_reads_clear_air_there():
    # 10 m on the grid at K = 1, then 4 m outside sampled every 2 m at
    # x = 10 (still on the slice), 12 and 14 (clear air).
    k_avg, k_max = _los_stats(0.0, 0.0, 14.0, 0.0, 0.0, _short_slice(), STEP_M, 14.0)
    assert k_avg == pytest.approx((1.0 * 10.0 + (1.0 / 3.0) * 4.0) / 14.0)
    assert k_max == 1.0


def test_line_leaving_the_slice_raises_in_strict_mode():
    with pytest.raises(FdsDomainError):
        _los_stats(
            0.0,
            0.0,
            14.0,
            0.0,
            0.0,
            _short_slice(require_fds_coverage=True),
            STEP_M,
            14.0,
        )


def test_polyline_through_the_band_is_length_weighted():
    # Two legs on the grid: (2, 0)-(10.5, 0) holds two core cells of 35,
    # (10.5, 0)-(20, 0) two of 39 (10.5 is read by both legs).
    waypoints = [(2.0, 0.0), (10.5, 0.0), (20.0, 0.0)]
    k_avg, k_max = _polyline_stats(waypoints, 0.0, _band(), STEP_M)
    first = 10.0 * 3 / 35  # nodes 2.0..10.5, core 10.0, 10.25, 10.5
    second = 10.0 * 2 / 39  # nodes 10.5..20.0, core 10.5, 10.75
    expected = (first * 8.5 + second * 9.5) / 18.0
    assert k_avg == pytest.approx(expected, rel=1e-12)
    assert k_max == 10.0


@pytest.mark.parametrize(
    "frame_times",
    [np.arange(0.0, 11.0), np.array([0.0, 0.5, 2.0, 2.25, 7.0]), np.array([1.0, 3.0])],
)
def test_frames_of_many_times_match_fdsreader(frame_times):
    # Foresight reads each cell at its own time; the frames are looked up
    # for all of them at once and must be those fdsreader picks one by one.
    from fdsreader.slcf.slice import Slice

    from pyfds_evac.core.fds_sampling import _nearest_frames

    times = np.concatenate(
        (
            np.linspace(-1.0, frame_times[-1] + 2.0, 997),
            frame_times,
            0.5 * (frame_times[:-1] + frame_times[1:]),
        )
    )
    fake = SimpleNamespace(times=frame_times)
    expected = [Slice.get_nearest_timestep(fake, float(t)) for t in times]
    assert _nearest_frames(frame_times, times).tolist() == expected
