"""The ASET/RSET array layer, on hand-calculable fields (#210)."""

import numpy as np
import pytest

from pyfds_evac.analysis import (
    AsetMap,
    CellState,
    Grid,
    PointCrossing,
    PointSeries,
    RsetMap,
    aset_map,
    binned_c,
    bootstrap_ci,
    cell_membership,
    convergence_curve,
    diff_map,
    first_crossing_dose,
    first_crossing_level,
    measures,
    pool_rset,
    pool_seeds,
    reduce_to_cells,
    release_measures,
)

INF = np.inf
NAN = np.nan


def _grid(nx=3, ny=2, cell=1.0, area=None):
    area = np.full((ny, nx), cell * cell) if area is None else area
    return Grid(cell, np.arange(nx + 1) * cell, np.arange(ny + 1) * cell, area)


def _nodes(grid, step=0.5):
    x = np.arange(0.0, grid.x_edges[-1] + 1e-9, step)
    y = np.arange(0.0, grid.y_edges[-1] + 1e-9, step)
    gx, gy = np.meshgrid(x, y)
    return gx.ravel(), gy.ravel()


def _uniform(grid, per_time):
    """A PointSeries with the same value at every node, one frame per time."""
    x, y = _nodes(grid)
    times = np.arange(len(per_time), dtype=float)
    frames = np.repeat(np.asarray(per_time, dtype=float)[:, None], len(x), axis=1)
    return PointSeries(x, y, times, np.arange(len(times)), frames)


# --- uniform fields: every cell, every rule, one answer -------------------


@pytest.mark.parametrize("rule", ["exists", "all", "nearest"])
def test_uniform_extinction_ramp_gives_the_same_aset_in_every_cell(rule):
    grid = _grid()
    series = _uniform(grid, np.arange(11) / 10.0)  # K(t) = t / 10
    first = first_crossing_level(series, 0.3)
    aset = reduce_to_cells(grid, series.x, series.y, first, rule)
    assert (aset == 3.0).all()


def test_uniform_temperature_ramp_gives_ten_seconds():
    grid = _grid()
    series = _uniform(grid, 20.0 + 4.0 * np.arange(11))
    first = first_crossing_level(series, 60.0)  # an exact hit crosses
    assert (reduce_to_cells(grid, series.x, series.y, first) == 10.0).all()


def test_level_crossing_is_kept_when_the_value_dips_again():
    series = _uniform(_grid(), [0.0, 0.5, 0.0, 0.0])
    assert (first_crossing_level(series, 0.3) == 1.0).all()


def test_level_crossing_reads_the_frame_of_each_step():
    """Steps 0..5 share two frames: the engine takes the nearest frame."""
    x, y = _nodes(_grid(1, 1))
    frames = np.repeat(np.array([[0.0], [1.0]]), len(x), axis=1)
    series = PointSeries(x, y, np.arange(6.0), np.array([0, 0, 0, 1, 1, 1]), frames)
    assert (first_crossing_level(series, 1.0) == 3.0).all()


# --- dose: the engine's right-endpoint rule -------------------------------


def test_constant_rate_crosses_at_five_seconds():
    series = _uniform(_grid(), np.full(11, 3.75))  # 0.0625 per second
    assert (first_crossing_dose(series, 0.3) == 5.0).all()  # 0.3125 at n = 5


def test_ramp_rate_crosses_by_the_right_endpoint_not_the_left():
    """rate(t_k) = 7.5 k per min gives dose(t_k) = 0.0625 k (k + 1).

    The right endpoint counts the rate at the step that ends the interval:
    0.375 at k = 2. A left-endpoint sum, 0.0625 k (k - 1), needs k = 3.
    """
    series = _uniform(_grid(), 7.5 * np.arange(11))
    assert (first_crossing_dose(series, 0.3) == 2.0).all()


def test_dose_starts_at_zero_so_the_first_step_adds_nothing():
    series = _uniform(_grid(), np.full(4, 600.0))  # 10 per second
    assert (first_crossing_dose(series, 5.0) == 1.0).all()  # not 0.0


def test_dose_needs_a_positive_threshold():
    with pytest.raises(ValueError, match="positive"):
        first_crossing_dose(_uniform(_grid(), np.ones(3)), 0.0)


def test_dose_is_integrated_per_point_not_from_the_block_maximum():
    """Node A burns in steps 1-2, node B in steps 3-4, 0.5 per step each.

    Each reaches 1.0 and never 1.5, so the cell stays open. The maximum
    rate over the two nodes burns in all four steps and would cross at 3.
    """
    grid = _grid(1, 1)
    x = np.array([0.25, 0.75])
    y = np.array([0.5, 0.5])
    frames = np.zeros((5, 2))
    frames[1:3, 0] = 30.0
    frames[3:5, 1] = 30.0
    times = np.arange(5.0)
    series = PointSeries(x, y, times, np.arange(5), frames)
    first = first_crossing_dose(series, 1.5)
    assert np.isinf(first).all()
    assert np.isinf(reduce_to_cells(grid, x, y, first)).all()
    peak = frames.max(axis=1)[:, None]
    block_max = PointSeries(x[:1], y[:1], times, np.arange(5), peak)
    assert first_crossing_dose(block_max, 1.5)[0] == 3.0
    first = first_crossing_dose(series, 1.0)  # the cell takes the earlier node
    assert list(first) == [2.0, 4.0]
    assert reduce_to_cells(grid, x, y, first)[0, 0] == 2.0


# --- cell rules ------------------------------------------------------------


def test_cell_rules_differ_when_one_node_of_the_cell_is_hot():
    grid = _grid(1, 1)
    x = np.array([0.5, 0.1, 0.9])  # centre, hot corner, other corner
    y = np.array([0.5, 0.1, 0.9])
    first = np.array([INF, 5.0, INF])
    assert reduce_to_cells(grid, x, y, first, "exists")[0, 0] == 5.0
    assert np.isinf(reduce_to_cells(grid, x, y, first, "all")[0, 0])
    assert np.isinf(reduce_to_cells(grid, x, y, first, "nearest")[0, 0])
    first = np.array([7.0, 5.0, 9.0])
    assert reduce_to_cells(grid, x, y, first, "all")[0, 0] == 9.0
    assert reduce_to_cells(grid, x, y, first, "nearest")[0, 0] == 7.0


def test_unknown_cell_rule_is_refused():
    with pytest.raises(ValueError, match="cell rule"):
        reduce_to_cells(_grid(), np.zeros(1), np.zeros(1), np.zeros(1), "centre")


def test_a_node_on_a_cell_edge_belongs_to_both_cells():
    grid = _grid(2, 1)
    x = np.array([1.0000001, 0.5])  # float32-sized noise on the edge at 1.0
    point, _, col = cell_membership(grid, x, np.array([0.5, 0.5]))
    assert sorted(zip(point.tolist(), col.tolist())) == [(0, 0), (0, 1), (1, 0)]


def test_a_point_outside_the_grid_belongs_to_no_cell():
    point, _, _ = cell_membership(
        _grid(2, 1), np.array([5.0, 0.5]), np.array([0.5, 3.0])
    )
    assert len(point) == 0


def test_row_zero_is_the_largest_y():
    grid = _grid(1, 2)
    first = np.array([10.0, 20.0])  # a node low (y = 0.5) and one high (y = 1.5)
    aset = reduce_to_cells(grid, np.array([0.5, 0.5]), np.array([0.5, 1.5]), first)
    assert list(aset[:, 0]) == [20.0, 10.0]


def test_cells_without_a_node_or_floor_are_no_data_not_open():
    grid = _grid(3, 1, area=np.array([[1.0, 1.0, 0.0]]))
    x, y, first = np.array([0.5]), np.array([0.5]), np.array([4.0])
    aset = reduce_to_cells(grid, x, y, first)
    assert aset[0, 0] == 4.0
    assert np.isnan(aset[0, 1])  # floor, no node
    assert np.isnan(aset[0, 2])  # no floor
    fallback = reduce_to_cells(grid, x, y, first, fallback_nearest=True)
    assert fallback[0, 1] == 4.0 and np.isnan(fallback[0, 2])


def test_open_cells_stay_open_and_criteria_are_cut_at_the_shorter_horizon():
    grid = _grid(1, 1)
    x, y = np.array([0.5]), np.array([0.5])
    long = PointCrossing("long", x, y, np.array([70.0]), 100.0)
    short = PointCrossing("short", x, y, np.array([INF]), 50.0)
    aset = aset_map(grid, [long, short])
    assert aset.horizon_s == 50.0
    assert np.isinf(aset.time_s[0, 0]) and aset.open[0, 0]  # not 50, not 70
    assert aset.per_criterion["long"][0, 0] == INF
    other = PointCrossing("other", x, y, np.array([40.0]), 100.0)
    assert aset_map(grid, [long, other]).time_s[0, 0] == 40.0  # the earliest wins


def test_aset_map_needs_a_criterion():
    with pytest.raises(ValueError, match="at least one"):
        aset_map(_grid(), [])


# --- states, DIFF -----------------------------------------------------------


def _maps(aset, rset, cens=None, a_h=100.0, r_h=40.0, area=0.36):
    aset, rset = np.array([aset], float), np.array([rset], float)
    grid = _grid(aset.shape[1], 1, area=np.full(aset.shape, area))
    cens = np.zeros(rset.shape, bool) if cens is None else np.array([cens], bool)
    return diff_map(AsetMap(aset, a_h), RsetMap(rset, cens, r_h), grid)


def test_every_state_and_its_diff_or_bound():
    diff = _maps(
        [12.0, 30.0, 20.0, INF, 25.0, INF, 5.0, NAN, NAN],
        [20.0, 20.0, 20.0, 20.0, 40.0, 40.0, NAN, 7.0, NAN],
        [0, 0, 0, 0, 1, 1, 0, 0, 0],
    )
    names = [CellState(s).name for s in diff.state[0]]
    assert names == [
        "FAIL",
        "PASS",
        "PASS",
        "ASET_OPEN",
        "RSET_CENSORED",
        "UNDETERMINED",
        "ASET_ONLY",
        "RSET_ONLY",
        "NONE",
    ]
    assert diff.diff_s[0, 0] == -8.0 and diff.diff_s[0, 1] == 10.0
    assert diff.diff_s[0, 2] == 0.0  # DIFF = 0 passes
    assert diff.bound_s[0, 3] == 100.0 - 20.0  # DIFF > T_F - RSET
    assert diff.bound_s[0, 4] == 25.0 - 40.0  # DIFF < ASET - T_R
    assert np.isnan(diff.bound_s[0, 5]) and np.isnan(diff.diff_s[0, 5])


def test_diff_zero_fails_only_in_the_release_counting():
    grid = _grid(1, 1)
    aset = AsetMap(np.array([[20.0]]), 100.0)
    rset = RsetMap(np.array([[20.0]]), np.zeros((1, 1), bool), 40.0)
    assert diff_map(aset, rset, grid).state[0, 0] == CellState.PASS
    assert diff_map(aset, rset, grid, zero_fails=True).state[0, 0] == CellState.FAIL


def test_diff_refuses_maps_of_different_shape():
    rset = RsetMap(np.zeros((1, 3)), np.zeros((1, 3), bool), 1.0)
    with pytest.raises(ValueError, match="differ in shape"):
        diff_map(AsetMap(np.zeros((1, 3)), 1.0), rset, _grid(2, 1))


def test_known_negative_cell_measures():
    """ASET 12 s against an agent standing until 20 s: DIFF -8, C = -8 * area."""
    diff = _maps([12.0, 30.0, INF, 25.0], [20.0, 20.0, 20.0, 40.0], [0, 0, 0, 1])
    m = measures(diff)
    assert (m.n_fail, m.min_diff_s, m.min_cell) == (1, -8.0, (0, 0))
    assert m.fail_area_m2 == pytest.approx(0.36)
    assert m.c_m2s == pytest.approx(-8.0 * 0.36)
    assert m.counts["pass"] == 1 and m.counts["aset_open"] == 1
    assert m.counts["rset_censored"] == 1
    assert m.n_censored_bound_negative == 1  # DIFF < -15: certain, but not exact
    assert m.n_open_bound_negative == 0  # bound is +80
    assert m.support_area_m2 == pytest.approx(4 * 0.36)


def test_measures_on_union_add_the_coverage_and_the_share():
    diff = _maps([12.0, 30.0, 5.0, NAN], [20.0, 20.0, NAN, 7.0])
    inter = measures(diff, support="intersection")
    union = measures(diff, support="union")
    assert (inter.n_fail, union.n_fail) == (1, 1)
    assert inter.c_m2s == union.c_m2s
    assert inter.support_area_m2 == pytest.approx(2 * 0.36)
    assert union.support_area_m2 == pytest.approx(4 * 0.36)
    assert inter.fail_share_of_support == pytest.approx(0.5)
    assert union.fail_share_of_support == pytest.approx(0.25)
    assert (union.n_aset_only, union.n_rset_only) == (1, 1)  # reported, never passed
    with pytest.raises(ValueError, match="support"):
        measures(diff, support="both")


def test_c_by_hand_free_and_binned():
    area = np.full(3, 0.36)
    d = np.array([-5.0, -15.0, -25.0])
    assert float(np.sum(d * area)) == pytest.approx(-45 * 0.36)  # -16.2
    assert binned_c(d, area) == pytest.approx(-50 * 0.36)  # centres -10 -10 -30: -18.0
    m = measures(_maps([15.0, 5.0, -5.0], [20.0] * 3))
    assert m.c_m2s == pytest.approx(-16.2)
    assert m.c_binned_m2s == pytest.approx(-18.0)


def test_release_counting_on_a_finished_diff_map():
    d = np.array([[-5.0, -15.0, -25.0, 0.0], [NAN, 10.0, NAN, NAN]])
    r = release_measures(d)
    assert r.min_diff_s == -25.0
    assert (r.n_le0, r.n_lt0) == (4, 3)  # DIFF = 0 fails in the release
    assert r.area_le0_m2 == pytest.approx(4 * 0.36)
    assert r.c_binned_m2s == pytest.approx(-60 * 0.36)  # 0 is in the closed last bin
    assert r.c_free_m2s == pytest.approx(-45 * 0.36)


# --- seeds ------------------------------------------------------------------


def test_pooled_p95_is_nanpercentile_over_the_seeds_that_visit_the_cell():
    maps = [
        np.array([[10.0, 40.0, NAN]]),
        np.array([[20.0, NAN, NAN]]),
        np.array([[30.0, NAN, NAN]]),
    ]
    pooled = pool_seeds(maps, "p95")
    assert pooled.values[0, 0] == pytest.approx(np.nanpercentile([10, 20, 30], 95))
    assert pooled.values[0, 0] == pytest.approx(29.0)
    assert pooled.values[0, 1] == 40.0  # one seed visits it
    assert np.isnan(pooled.values[0, 2])
    assert pooled.label == "p95 over n=3"
    assert pool_seeds(maps, "max").label == "max over n=3"
    assert pool_seeds(maps, "max").values[0, 0] == 30.0
    with pytest.raises(ValueError, match="pool"):
        pool_seeds(maps, "mean")


def test_a_cell_censored_in_any_seed_stays_censored_in_the_pool():
    a = RsetMap(np.array([[10.0, 10.0]]), np.array([[False, True]]), 30.0)
    b = RsetMap(np.array([[12.0, 12.0]]), np.array([[False, False]]), 40.0)
    pooled, _ = pool_rset([a, b])
    assert list(pooled.censored[0]) == [False, True]
    assert pooled.horizon_s == 40.0


def test_bootstrap_is_reproducible_and_exact_on_constants():
    values = [1.0, 2.0, 3.0, 4.0]
    a = bootstrap_ci(values)
    assert a == bootstrap_ci(values)
    assert a.mean == 2.5 and a.low < 2.5 < a.high and a.n == 4
    same = bootstrap_ci([7.0, 7.0, 7.0])
    assert (same.low, same.mean, same.high) == (7.0, 7.0, 7.0)
    rng = np.random.default_rng(0)  # the study's expression: seed 0, 4000 resamples
    means = rng.choice(np.array(values), (4000, 4)).mean(axis=1)
    assert (a.low, a.high) == tuple(np.percentile(means, [2.5, 97.5]))


def test_convergence_curve_runs_from_two_seeds_to_all():
    ns, half = convergence_curve([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert list(ns) == [2, 3, 4, 5, 6] and (half >= 0).all()
