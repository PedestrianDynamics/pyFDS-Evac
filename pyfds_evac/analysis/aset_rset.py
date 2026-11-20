"""ASET, RSET and DIFF maps on a grid: the array layer.

Numpy only. Nothing here reads FDS, JuPedSim or PedPy; the readers are
``fds_fields`` (ASET inputs) and ``rset`` (RSET map). After Schröder, Arnold
and Seyfried, "A map representation of the ASET-RSET concept", Fire Safety
Journal 115 (2020) 103154.

Conventions, fixed here and pinned by tests:

* A map is an array of shape ``(ny, nx)`` in PedPy's orientation: column 0
  at the smallest x, **row 0 at the largest y**.
* ``DIFF = ASET - RSET`` [s]. Negative: the fire wins in that cell.
* NaN means "no data" (no sample point, no floor, nobody visited), never
  "benign". ``inf`` means "not reached by the end of the data": an ASET that
  the fire data never crossed, open beyond ``horizon_s``.
* Time is seconds from ignition on the FDS clock.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np

CELL_RULES = ("exists", "all", "nearest")
EDGE_TOL_M = 1e-3
"""Tolerance on cell edges [m]. fdsreader coordinates are float32 (29.800001)."""

RELEASE_CELL_AREA_M2 = 0.36
RELEASE_BIN_S = 20.0


# --- Grid ----------------------------------------------------------------


@dataclass(frozen=True)
class Grid:
    """Square map cells; ``area`` is the floor area inside each cell [m²].

    ``x_edges`` and ``y_edges`` are ascending. Row ``r`` of a map covers
    ``y_edges[ny - 1 - r] .. y_edges[ny - r]``: row 0 is the largest y.
    ``Grid`` makes no claim about PedPy; ``rset.grid_from_walkable`` builds
    one from PedPy's own output shape.
    """

    cell_m: float
    x_edges: np.ndarray
    y_edges: np.ndarray
    area: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        """The map shape ``(ny, nx)``."""
        return len(self.y_edges) - 1, len(self.x_edges) - 1

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Cell centres of every cell, as ``(x, y)`` arrays of the map shape."""
        xc = 0.5 * (self.x_edges[:-1] + self.x_edges[1:])
        yc = 0.5 * (self.y_edges[:-1] + self.y_edges[1:])[::-1]
        return np.meshgrid(xc, yc)


def _axis_bins(edges: np.ndarray, v: np.ndarray, tol: float):
    """Bins ``[e_k, e_k+1]`` that hold each value, closed on both sides.

    Returns ``(low, high, ok)``: the first and last bin of each value (they
    differ by one on an interior edge, so the value belongs to both bins) and
    whether the value lies inside the edges at all.
    """
    n = len(edges) - 1
    high = np.searchsorted(edges, v + tol, side="right") - 1
    low = np.searchsorted(edges, v - tol, side="left") - 1
    ok = (v >= edges[0] - tol) & (v <= edges[-1] + tol)
    return np.clip(low, 0, n - 1), np.clip(high, 0, n - 1), ok


def cell_membership(
    grid: Grid, x: np.ndarray, y: np.ndarray, *, tol_m: float = EDGE_TOL_M
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cells that hold each point: ``(point, row, col)`` index arrays.

    A point on a cell edge belongs to both cells. A point outside the grid
    belongs to none.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ny = len(grid.y_edges) - 1
    c0, c1, ok_x = _axis_bins(grid.x_edges, x, tol_m)
    b0, b1, ok_y = _axis_bins(grid.y_edges, y, tol_m)
    ok = ok_x & ok_y
    points, rows, cols = [], [], []
    for dc in (0, 1):
        for db in (0, 1):
            col, bin_y = c0 + dc, b0 + db
            keep = ok & (col <= c1) & (bin_y <= b1)
            idx = np.flatnonzero(keep)
            points.append(idx)
            cols.append(col[idx])
            rows.append(ny - 1 - bin_y[idx])
    return np.concatenate(points), np.concatenate(rows), np.concatenate(cols)


# --- ASET ----------------------------------------------------------------


@dataclass(frozen=True)
class PointSeries:
    """A field at sample points over time, as the engine would read it.

    ``frames[frame[k]]`` is the value of every point at time ``times_s[k]``:
    the engine takes the nearest slice frame (no interpolation), so several
    steps can share one frame. ``frames`` has shape ``(n_frames, n_points)``.
    """

    x: np.ndarray
    y: np.ndarray
    times_s: np.ndarray
    frame: np.ndarray
    frames: np.ndarray

    def __post_init__(self) -> None:
        if len(self.times_s) != len(self.frame):
            raise ValueError("PointSeries: times_s and frame differ in length")
        if self.frames.shape[1] != len(self.x) or len(self.x) != len(self.y):
            raise ValueError("PointSeries: frames, x and y disagree on the points")


def first_crossing_level(series: PointSeries, limit: float) -> np.ndarray:
    """First time each point's value reaches *limit* (``>=``); inf if never.

    A later dip below the limit does not undo the crossing.
    """
    n_frames = series.frames.shape[0]
    first_step = np.full(n_frames, np.inf)
    for k in range(len(series.times_s) - 1, -1, -1):
        first_step[series.frame[k]] = series.times_s[k]
    exceed = series.frames >= limit
    first: np.ndarray = np.where(exceed, first_step[:, None], np.inf).min(axis=0)
    return first


def first_crossing_dose(
    series: PointSeries, threshold: float, *, rate_unit_s: float = 60.0
) -> np.ndarray:
    """First time a dose accumulated from the first time step reaches *threshold*.

    ``series.frames`` holds the dose rate per ``rate_unit_s`` seconds (FED
    rates are per minute). The rule is the engine's, right endpoint:
    ``dose(t_0) = 0`` and ``dose(t_k) = dose(t_k-1) + rate(t_k) (t_k - t_k-1)``,
    so the rate at a step counts for the interval that ends there.
    ``dose >= threshold`` crosses; an exact hit counts.
    """
    if threshold <= 0:
        raise ValueError(f"dose threshold must be positive, got {threshold}")
    times = series.times_s
    dose = np.zeros(series.frames.shape[1])
    first = np.full(dose.shape, np.inf)
    for k in range(1, len(times)):
        dose += series.frames[series.frame[k]] * (times[k] - times[k - 1]) / rate_unit_s
        newly = (dose >= threshold) & np.isinf(first)
        first[newly] = times[k]
    return first


@dataclass(frozen=True)
class PointCrossing:
    """First-crossing time of one criterion at its sample points.

    ``first_s`` is inf where the criterion is not met by ``horizon_s``, the
    last time the fire data cover. ``z_m`` is the height of the slice read.
    """

    name: str
    x: np.ndarray
    y: np.ndarray
    first_s: np.ndarray
    horizon_s: float
    z_m: float = float("nan")
    description: str = ""


def reduce_to_cells(
    grid: Grid,
    x: np.ndarray,
    y: np.ndarray,
    first_s: np.ndarray,
    rule: str = "exists",
    *,
    fallback_nearest: bool = False,
    tol_m: float = EDGE_TOL_M,
) -> np.ndarray:
    """Cell ASET from per-point first-crossing times, by a cell rule.

    * ``exists`` (default): the earliest point of the cell, so a cell is
      untenable as soon as any sample point in it is (block maximum).
    * ``all``: the latest point, so every point has crossed.
    * ``nearest``: the point nearest the cell centre.

    Cells without a point, and cells without floor (``grid.area == 0``), are
    NaN. With *fallback_nearest* a cell with floor but no point takes the
    nearest point of the whole set (coarse FDS meshes).
    """
    if rule not in CELL_RULES:
        raise ValueError(f"cell rule {rule!r} not one of {CELL_RULES}")
    first_s = np.asarray(first_s, dtype=float)
    point, row, col = cell_membership(grid, x, y, tol_m=tol_m)
    out = _rule_over_members(grid, rule, first_s, point, row, col, x, y)
    if fallback_nearest:
        out = _nearest_fallback(grid, out, first_s, x, y)
    return np.where(grid.area > 0, out, np.nan)


def _rule_over_members(grid, rule, first_s, point, row, col, x, y):
    shape = grid.shape
    if rule == "nearest":
        return _nearest_member(grid, first_s, point, row, col, x, y)
    count = np.zeros(shape)
    np.add.at(count, (row, col), 1.0)
    if rule == "exists":
        out = np.full(shape, np.inf)
        np.minimum.at(out, (row, col), first_s[point])
    else:
        out = np.full(shape, -np.inf)
        np.maximum.at(out, (row, col), first_s[point])
    return np.where(count > 0, out, np.nan)


def _nearest_member(grid, first_s, point, row, col, x, y):
    xc, yc = grid.centres()
    dist = np.hypot(
        np.asarray(x)[point] - xc[row, col], np.asarray(y)[point] - yc[row, col]
    )
    order = np.lexsort((dist, col, row))
    cell = row[order] * grid.shape[1] + col[order]
    keep = np.r_[True, cell[1:] != cell[:-1]]
    out = np.full(grid.shape, np.nan)
    out[row[order][keep], col[order][keep]] = first_s[point[order][keep]]
    return out


def _nearest_fallback(grid, out, first_s, x, y):
    out = out.copy()
    xc, yc = grid.centres()
    missing = np.isnan(out) & (grid.area > 0)
    for r, c in zip(*np.nonzero(missing)):
        out[r, c] = first_s[np.hypot(x - xc[r, c], y - yc[r, c]).argmin()]
    return out


@dataclass(frozen=True)
class AsetMap:
    """ASET per cell: the earliest of the selected criteria.

    ``time_s`` is NaN without data, inf where no criterion is met by
    ``horizon_s``. ``per_criterion`` keeps every criterion's own map.
    """

    time_s: np.ndarray
    horizon_s: float
    per_criterion: Mapping[str, np.ndarray] = field(default_factory=dict)
    z_m: Mapping[str, float] = field(default_factory=dict)
    cell_rule: str = "exists"

    @property
    def no_data(self) -> np.ndarray:
        """Cells without an ASET value (no sample point, or no floor)."""
        return np.asarray(np.isnan(self.time_s))

    @property
    def open(self) -> np.ndarray:
        """Cells the fire data never made untenable by ``horizon_s``."""
        return np.asarray(np.isinf(self.time_s))

    def deciding(self) -> np.ndarray:
        """Name of the criterion that sets each cell's ASET (a str array).

        The names are the keys of ``per_criterion``, the ``PointCrossing``
        names (``K 0.3``, ``T 45``, ``FED 0.3``, ``heat FED 0.3``). Criteria
        that tie are joined with ``+`` in ``per_criterion`` order. Cells
        without data, or never untenable, are the empty string.
        """
        out = np.full(self.time_s.shape, "", dtype=object)
        decided = np.isfinite(self.time_s)
        for name, first in self.per_criterion.items():
            hit = decided & (first == self.time_s)
            joined = np.where(out == "", name, out + "+" + name)
            out = np.where(hit, joined, out)
        return out.astype(str)


def aset_map(
    grid: Grid,
    crossings: Sequence[PointCrossing],
    *,
    cell_rule: str = "exists",
    fallback_nearest: bool = False,
) -> AsetMap:
    """Combine criteria into a cell ASET: the earliest crossing of any.

    All criteria are cut at the earliest ``horizon_s``: a crossing after it
    counts as open, because the criterion with the shorter data cannot say
    what it would have done there. A cell never crossing stays inf, never the
    horizon.
    """
    if not crossings:
        raise ValueError("aset_map needs at least one criterion")
    horizon = min(c.horizon_s for c in crossings)
    per, z = {}, {}
    for c in crossings:
        first = np.where(c.first_s > horizon, np.inf, c.first_s)
        per[c.name] = reduce_to_cells(
            grid, c.x, c.y, first, cell_rule, fallback_nearest=fallback_nearest
        )
        z[c.name] = c.z_m
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        combined = np.fmin.reduce(list(per.values()))
    return AsetMap(combined, horizon, per, z, cell_rule)


# --- RSET ----------------------------------------------------------------


@dataclass(frozen=True)
class RsetMap:
    """RSET per cell: the last time anyone is in it; NaN if nobody was.

    ``censored`` marks cells that hold the last position of an agent that
    never left: its RSET is a lower bound, ``>= horizon_s`` (the run end).
    """

    time_s: np.ndarray
    censored: np.ndarray
    horizon_s: float


class CellState(IntEnum):
    """The state of a cell in a DIFF map."""

    NONE = -1  # neither ASET nor RSET
    PASS = 0  # DIFF >= 0, both exact
    FAIL = 1  # DIFF < 0, both exact
    ASET_OPEN = 2  # ">= bound": ASET not reached by the fire data
    RSET_CENSORED = 3  # "<= bound": an agent never left
    UNDETERMINED = 4  # both open
    ASET_ONLY = 5  # fire data but nobody visited: no DIFF, cannot fail
    RSET_ONLY = 6  # visited but no ASET: a data gap, never a pass


@dataclass(frozen=True)
class DiffMap:
    """``DIFF = ASET - RSET`` with a state for every cell.

    ``diff_s`` is set only for the exact states (pass, fail). ``bound_s`` is
    set for the two bounded states: ``DIFF > bound`` for ``ASET_OPEN`` and
    ``DIFF < bound`` for ``RSET_CENSORED``.
    """

    diff_s: np.ndarray
    state: np.ndarray
    bound_s: np.ndarray
    area: np.ndarray
    aset_horizon_s: float
    rset_horizon_s: float


def diff_map(
    aset: AsetMap, rset: RsetMap, grid: Grid, *, zero_fails: bool = False
) -> DiffMap:
    """Subtract RSET from ASET and classify every cell.

    DIFF = 0 passes unless *zero_fails* (the release's counting).
    """
    if aset.time_s.shape != rset.time_s.shape or aset.time_s.shape != grid.shape:
        raise ValueError(
            f"ASET {aset.time_s.shape}, RSET {rset.time_s.shape} and grid "
            f"{grid.shape} differ in shape; build them on one Grid"
        )
    a, r = aset.time_s, rset.time_s
    a_known, r_known = ~np.isnan(a), ~np.isnan(r)
    both = a_known & r_known
    a_open, r_cens = np.isinf(a), rset.censored & r_known
    exact = both & ~a_open & ~r_cens
    raw = np.where(both, a - r, np.nan)
    fail = exact & ((raw <= 0) if zero_fails else (raw < 0))
    state = np.full(a.shape, int(CellState.NONE), dtype=np.int8)
    state[a_known & ~r_known] = CellState.ASET_ONLY
    state[r_known & ~a_known] = CellState.RSET_ONLY
    state[exact] = CellState.PASS
    state[fail] = CellState.FAIL
    state[both & a_open & ~r_cens] = CellState.ASET_OPEN
    state[both & ~a_open & r_cens] = CellState.RSET_CENSORED
    state[both & a_open & r_cens] = CellState.UNDETERMINED
    bound = np.full(a.shape, np.nan)
    open_c = state == CellState.ASET_OPEN
    cens_c = state == CellState.RSET_CENSORED
    bound[open_c] = aset.horizon_s - r[open_c]
    bound[cens_c] = a[cens_c] - r[cens_c]
    diff = np.where(exact, raw, np.nan)
    return DiffMap(diff, state, bound, grid.area, aset.horizon_s, rset.horizon_s)


# --- Measures ------------------------------------------------------------


@dataclass(frozen=True)
class Measures:
    """What a DIFF map says, on the cells where DIFF exists.

    ``c_m2s`` is bin-free: the sum of DIFF times the floor area over the
    failing cells (m² s, negative). ``c_binned_m2s`` uses 20 s bins at the
    bin centre as the release does, for comparison with the paper only.
    ``support`` is ``intersection`` (cells with both maps) or ``union``
    (those plus cells with only one map); the failing area and C are the same
    on both, the shares and the coverage differ.
    """

    support: str
    min_diff_s: float
    min_cell: tuple[int, int] | None
    n_fail: int
    fail_area_m2: float
    c_m2s: float
    c_binned_m2s: float
    support_area_m2: float
    fail_share_of_support: float
    counts: Mapping[str, int]
    n_open_bound_negative: int
    n_censored_bound_negative: int
    n_aset_only: int
    n_rset_only: int
    aset_only_area_m2: float
    rset_only_area_m2: float


def binned_c(diff_s: np.ndarray, area_m2: np.ndarray, bin_s: float = RELEASE_BIN_S):
    """C with *bin_s* bins at the bin centre: ``sum((floor(d/b)+0.5) b * area)``."""
    d = np.asarray(diff_s, dtype=float)
    centres = (np.floor(d / bin_s) + 0.5) * bin_s
    return float(np.sum(centres * np.asarray(area_m2)))


_SUPPORTS = ("intersection", "union")
_INTERSECTION = (
    CellState.PASS,
    CellState.FAIL,
    CellState.ASET_OPEN,
    CellState.RSET_CENSORED,
    CellState.UNDETERMINED,
)


def measures(diff: DiffMap, *, support: str = "intersection") -> Measures:
    """Min DIFF, failing area, C and the state counts of a DIFF map."""
    if support not in _SUPPORTS:
        raise ValueError(f"support {support!r} not one of {_SUPPORTS}")
    st, area = diff.state, diff.area
    fail = st == CellState.FAIL
    inter = np.isin(st, [int(s) for s in _INTERSECTION])
    only_a, only_r = st == CellState.ASET_ONLY, st == CellState.RSET_ONLY
    support_area = float(
        area[inter | ((only_a | only_r) if support == "union" else False)].sum()
    )
    exact = np.isfinite(diff.diff_s)
    min_cell = None
    min_diff = float("nan")
    if exact.any():
        flat = np.where(exact, diff.diff_s, np.inf)
        row, col = np.unravel_index(flat.argmin(), flat.shape)
        min_cell = (int(row), int(col))
        min_diff = float(flat.min())
    fail_area = float(area[fail].sum())
    open_c, cens_c = st == CellState.ASET_OPEN, st == CellState.RSET_CENSORED
    return Measures(
        support=support,
        min_diff_s=min_diff,
        min_cell=min_cell,
        n_fail=int(fail.sum()),
        fail_area_m2=fail_area,
        c_m2s=float(np.sum(diff.diff_s[fail] * area[fail])),
        c_binned_m2s=binned_c(diff.diff_s[fail], area[fail]),
        support_area_m2=support_area,
        fail_share_of_support=fail_area / support_area
        if support_area
        else float("nan"),
        counts={s.name.lower(): int((st == s).sum()) for s in CellState},
        n_open_bound_negative=int((open_c & (diff.bound_s < 0)).sum()),
        n_censored_bound_negative=int((cens_c & (diff.bound_s < 0)).sum()),
        n_aset_only=int(only_a.sum()),
        n_rset_only=int(only_r.sum()),
        aset_only_area_m2=float(area[only_a].sum()),
        rset_only_area_m2=float(area[only_r].sum()),
    )


@dataclass(frozen=True)
class ReleaseMeasures:
    """The measures of a DIFF map by the release's rules, for comparison only."""

    min_diff_s: float
    n_le0: int
    n_lt0: int
    area_le0_m2: float
    c_binned_m2s: float
    c_free_m2s: float


def release_measures(
    diff: np.ndarray,
    *,
    cell_area_m2: float = RELEASE_CELL_AREA_M2,
    bin_s: float = RELEASE_BIN_S,
    lowest_s: float = -120.0,
) -> ReleaseMeasures:
    """Measures of a finished DIFF map as the release's ``diff_map.py`` counts.

    DIFF <= 0 fails, 20 s bins from *lowest_s* to 0 with the last bin closed,
    the nominal cell area. Not the default rules (DIFF = 0 passes, true area,
    bin-free C); ``c_free_m2s`` and ``n_lt0`` give those on the same map.
    """
    flat = np.asarray(diff, dtype=float)
    flat = flat[np.isfinite(flat)]
    bins = np.arange(lowest_s, 0.01, bin_s)
    freqs, edges = np.histogram(flat, bins=bins)
    c = float(np.sum(freqs * (edges[1:] - bin_s / 2))) * cell_area_m2
    n_le0 = int(freqs.sum())
    return ReleaseMeasures(
        min_diff_s=float(flat.min()),
        n_le0=n_le0,
        n_lt0=int((flat < 0).sum()),
        area_le0_m2=n_le0 * cell_area_m2,
        c_binned_m2s=c,
        c_free_m2s=float(flat[flat < 0].sum()) * cell_area_m2,
    )


# --- Seeds ---------------------------------------------------------------

POOLS = ("p95", "max")


@dataclass(frozen=True)
class Pooled:
    """A map pooled over seeds, with how and over how many.

    A maximum over *n* seeds grows with *n*: quote it with ``label``.
    """

    values: np.ndarray
    how: str
    n_seeds: int

    @property
    def label(self) -> str:
        """``"p95 over n=10"`` or ``"max over n=10"``."""
        return f"{self.how} over n={self.n_seeds}"


def pool_seeds(maps: Sequence[np.ndarray], how: str = "p95") -> Pooled:
    """Pool per-seed maps per cell over the seeds that visit it.

    ``p95`` is the 95th percentile (``nanpercentile``, linear, as the
    release); with few seeds it lies near the maximum. NaN where no seed
    visits the cell.
    """
    if how not in POOLS:
        raise ValueError(f"pool {how!r} not one of {POOLS}")
    if not maps:
        raise ValueError("pool_seeds needs at least one map")
    stack = np.dstack(maps)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells
        values = (
            np.nanmax(stack, axis=2)
            if how == "max"
            else np.nanpercentile(stack, 95, axis=2)
        )
    return Pooled(values, how, len(maps))


def pool_rset(rsets: Sequence[RsetMap], how: str = "p95") -> tuple[RsetMap, Pooled]:
    """Pool per-seed RSET maps; a cell censored in any seed stays censored."""
    pooled = pool_seeds([r.time_s for r in rsets], how)
    censored = np.any([r.censored for r in rsets], axis=0)
    horizon = max(r.horizon_s for r in rsets)
    return RsetMap(pooled.values, censored, horizon), pooled


@dataclass(frozen=True)
class Interval:
    """Mean of per-seed values with a percentile-bootstrap interval."""

    mean: float
    low: float
    high: float
    n: int


def bootstrap_ci(
    values: Sequence[float], *, n_boot: int = 4000, level: float = 0.95, seed: int = 0
) -> Interval:
    """Mean and percentile-bootstrap interval of per-seed values.

    Resamples with replacement from a generator seeded with *seed*, so the
    interval is reproducible.
    """
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        raise ValueError("bootstrap_ci needs at least one value")
    rng = np.random.default_rng(seed)
    means = rng.choice(v, (n_boot, v.size)).mean(axis=1)
    tail = 50 * (1 - level)
    lo, hi = np.percentile(means, [tail, 100 - tail])
    return Interval(float(v.mean()), float(lo), float(hi), int(v.size))


def seed_measures(
    per_seed: Sequence[Measures],
    names: Sequence[str] = ("min_diff_s", "fail_area_m2", "c_m2s"),
    **bootstrap_kwargs,
) -> dict[str, Interval]:
    """Bootstrap interval of each named measure over the seeds."""
    return {
        n: bootstrap_ci([getattr(m, n) for m in per_seed], **bootstrap_kwargs)
        for n in names
    }


def convergence_curve(
    values: Sequence[float], **bootstrap_kwargs
) -> tuple[np.ndarray, np.ndarray]:
    """Half-width of the interval of the first *n* values, for n = 2..N.

    Choose the number of seeds where the half-width stops falling. There is
    no automatic stop; the order of *values* is the order of the seeds.
    """
    v = np.asarray(values, dtype=float)
    ns = np.arange(2, v.size + 1)
    half = [
        0.5 * (i.high - i.low)
        for i in (bootstrap_ci(v[:n].tolist(), **bootstrap_kwargs) for n in ns)
    ]
    return ns, np.asarray(half)
