"""Shared FDS slice sampling via fdsreader.

Provides nearest-neighbor spatial and temporal lookup on horizontal FDS
slice files.  Used by both the smoke-speed model (extinction) and the
FED model (gas concentrations).
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import Any, NamedTuple

import numpy as np

_logger = logging.getLogger(__name__)


def _open_simulation(fds_dir):
    """Parse an FDS case with fdsreader, imported here to keep imports cheap."""
    from .fdsreader_adapter import open_fds_simulation

    return open_fds_simulation(fds_dir)


# How far the selected slice may sit from the requested height before the
# mismatch is worth reporting.  A slice this far off samples a different part
# of the smoke layer than the caller asked for, which silently changes every
# extinction and gas reading downstream.
_SLICE_HEIGHT_TOLERANCE_M = 0.5

# Frame indices a sampler remembers by requested time. Route foresight reads
# each sample at its own time (#650), so a single cached time misses on
# nearly every call; the bound only limits memory, a cleared entry is looked
# up again.
_T_INDEX_CACHE_SIZE = 65536

# Lines a sampler remembers the grid parts of (#653). Route edges between
# nodes are asked for again at every evaluation; a walk from an agent's
# position rarely is. The bound only limits memory.
_LINE_CACHE_SIZE = 65536


class LinePart(NamedTuple):
    """A piece of a sampled line, as fractions of its length (#653).

    *fractions* are where its samples sit, one per grid cell, *subslice*
    the slice part they are read from and *cells* the value positions
    ``(i, j)`` they read; all three are None for a piece outside every
    subslice. Parts are cached and shared: never modify their arrays.
    """

    t_start: float
    t_end: float
    fractions: np.ndarray | None = None
    subslice: Any = None
    cells: tuple[np.ndarray, np.ndarray] | None = None


class FdsHorizonError(ValueError):
    """A sample was requested past the end of the FDS output.

    A subclass of ``ValueError`` that callers must not treat as the
    out-of-domain ``ValueError``: past the horizon there is no smoke data, so
    returning clear air or zero dose would be as wrong as holding the last
    frame.
    """


class FdsDomainError(ValueError):
    """A sample was requested outside the FDS slice domain in strict mode.

    Raised only with ``--require-fds-coverage`` (``require_fds_coverage=True``
    in Python). Without it, a point outside the domain reads ambient air and
    clear sight, as in FDS+Evac. Like ``FdsHorizonError``, callers must not
    treat it as the out-of-domain ``ValueError`` they turn into ambient values.
    """


def domain_error_message(quantity: str, time_s: float, x: float, y: float) -> str:
    """Return the error text for a strict-mode sample outside the FDS domain."""
    return (
        f"'{quantity}' requested at ({x:.2f}, {y:.2f}) m, t={time_s:.1f} s, "
        "which lies outside the FDS slice domain (--require-fds-coverage). "
        "Extend the FDS meshes or slices over this point, or run without "
        "--require-fds-coverage to read ambient air and clear sight there."
    )


def sampler_quantity(sampler) -> str:
    """Return the quantity name of a sampler, for error messages.

    Models need only ``sample`` of a sampler, so a stand-in may carry no
    name; it is then named by its type.
    """
    return str(getattr(sampler, "quantity", type(sampler).__name__))


def _output_interval(times) -> float:
    """Return the output interval of a time array, 0 for one frame.

    The largest frame spacing, not the last one: FDS clips the final frame
    at T_END, so the last spacing can be a fraction of the output interval.
    """
    if len(times) < 2:
        return 0.0
    return float(np.max(np.diff(np.asarray(times, dtype=float))))


def horizon_error_message(
    quantity: str, time_s: float, last_s: float, interval_s: float
) -> str:
    """Return the error text for a sample requested past the FDS output."""
    return (
        f"'{quantity}' requested at t={time_s:.1f} s, but the FDS output ends "
        f"at t={last_s:.1f} s (output interval {interval_s:.1f} s). Extend "
        "T_END in the FDS run, shorten the evacuation run, or pass "
        "--allow-fds-horizon-hold to hold the last frame."
    )


class SliceFieldSampler:
    """Sample one ``fdsreader`` slice quantity with nearest-neighbor lookup.

    A time more than one output interval past the last slice frame raises
    ``FdsHorizonError``, unless *allow_horizon_hold* is set: then the last
    frame is held and one warning is logged.
    """

    def __init__(self, slice_obj, *, allow_horizon_hold: bool = False):
        """Cache the slice object and its subslices for repeated sampling."""
        self._slice = slice_obj
        self._allow_horizon_hold = allow_horizon_hold
        self._warned_horizon = False
        self._subslices = list(slice_obj.subslices)
        self._last_subslice = None
        self._cached_time_s: float | None = None
        self._cached_t_index: int = 0
        self._t_index_cache: dict[float, int] = {}
        self._axes_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._line_cache: dict[tuple[float, float, float, float], tuple] = {}

    def _find_subslice(self, x: float, y: float):
        """Return the subslice covering the requested x/y point."""
        last = self._last_subslice
        if last is not None:
            ext = last.extent
            if ext.x_start <= x <= ext.x_end and ext.y_start <= y <= ext.y_end:
                return last
        for subslice in self._subslices:
            extent = subslice.extent
            if (
                extent.x_start <= x <= extent.x_end
                and extent.y_start <= y <= extent.y_end
            ):
                self._last_subslice = subslice
                return subslice
        return None

    def covers(self, x: float, y: float) -> bool:
        """Return whether a subslice covers the x/y point (closed intervals).

        Side-effect free: unlike ``_find_subslice`` it leaves the last-hit
        cache alone, so asking never changes which of two subslices sharing
        a boundary a later ``sample`` reads.
        """
        return any(
            ext.x_start <= x <= ext.x_end and ext.y_start <= y <= ext.y_end
            for ext in (subslice.extent for subslice in self._subslices)
        )

    @property
    def quantity(self) -> str:
        """Return the FDS quantity name of the slice."""
        return str(self._slice.quantity.name)

    def extents(self) -> list[tuple[float, float, float, float]]:
        """Return the (x_start, x_end, y_start, y_end) of every subslice [m]."""
        return [
            (
                float(s.extent.x_start),
                float(s.extent.x_end),
                float(s.extent.y_start),
                float(s.extent.y_end),
            )
            for s in self._subslices
        ]

    @staticmethod
    def _nearest_index(coords: np.ndarray, value: float) -> int:
        """Return the index of the coordinate nearest to ``value``.

        ``coords`` are the positions of the slice values along one axis:
        nodes for FDS's default node-centred slices, cell centres for
        cell-centred ones. Ties go to the lower index.
        """
        count = len(coords)
        if count <= 1:
            return 0
        right = int(np.searchsorted(coords, value))
        if right <= 0:
            return 0
        if right >= count:
            return count - 1
        left = right - 1
        return left if value - coords[left] <= coords[right] - value else right

    @staticmethod
    def _axis_positions(subslice, dim: str) -> np.ndarray:
        """Return the value positions of a subslice along one axis.

        Built from the mesh nodes inside the slice extent rather than
        ``SubSlice.get_coordinates``, which for cell-centred slices shifts
        every axis by the first half-width (wrong on stretched grids) and
        fails on a mesh axis with a single cell.
        """
        nodes = np.asarray(subslice.mesh.coordinates[dim], dtype=float)
        start = getattr(subslice.extent, f"{dim}_start")
        end = getattr(subslice.extent, f"{dim}_end")
        nodes = nodes[(nodes >= start) & (nodes <= end)]
        if subslice.cell_centered and len(nodes) > 1:
            return 0.5 * (nodes[:-1] + nodes[1:])
        return nodes

    def _axes(self, subslice) -> tuple[np.ndarray, np.ndarray]:
        """Return the x and y value positions of a subslice, cached."""
        key = id(subslice)
        axes = self._axes_cache.get(key)
        if axes is None:
            axes = (
                self._axis_positions(subslice, "x"),
                self._axis_positions(subslice, "y"),
            )
            self._axes_cache[key] = axes
        return axes

    def line_parts(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> tuple[LinePart, ...]:
        """Where to sample the segment (x0, y0)-(x1, y1): one point per grid cell.

        Returns the parts that cover the segment in order, as fractions of
        its length. A part inside a subslice carries the fractions of its
        samples (see :func:`_cell_fractions`) and the subslice to read them
        from with :meth:`read_cells`; a part outside every subslice carries
        neither. Where subslices overlap, the first one in order takes the
        overlap (#653). Parts are cached and shared; their arrays are
        read-only.
        """
        key = (x0, y0, x1, y1)
        parts = self._line_cache.get(key)
        if parts is None:
            parts = self._line_parts(x0, y0, x1, y1)
            if len(self._line_cache) >= _LINE_CACHE_SIZE:
                self._line_cache.clear()
            self._line_cache[key] = parts
        return parts

    def _line_parts(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> tuple[LinePart, ...]:
        """:meth:`line_parts`, not cached."""
        dx, dy = x1 - x0, y1 - y0
        covered: list[tuple[float, float, object]] = []
        for subslice in self._subslices:
            span = _clip_to_extent(x0, y0, dx, dy, subslice.extent)
            if span is None:
                continue
            for ta, tb in _subtract(span, [(a, b) for a, b, _ in covered]):
                covered.append((ta, tb, subslice))
        covered.sort(key=lambda part: part[0])
        parts: list[LinePart] = []
        t = 0.0
        for ta, tb, subslice in covered:
            if ta > t:
                parts.append(LinePart(t, ta))
            axes = self._axes(subslice)
            fractions = _cell_fractions(x0, y0, dx, dy, ta, tb, axes)
            cells = (
                _nearest_indices(axes[0], x0 + fractions * dx),
                _nearest_indices(axes[1], y0 + fractions * dy),
            )
            for array in (fractions, *cells):
                array.setflags(write=False)
            parts.append(LinePart(ta, tb, fractions, subslice, cells))
            t = tb
        if t < 1.0:
            parts.append(LinePart(t, 1.0))
        return tuple(parts)

    def read_cells(self, part: LinePart, times: np.ndarray) -> np.ndarray:
        """Values at the samples of a grid *part*, each at its own time.

        The value position nearest each sample and the frame nearest its
        time, as :meth:`sample` reads them, for all samples at once. Every
        sample is read from the part's own subslice, which covers it, so
        none is out of the domain. Raises ``FdsHorizonError`` past the FDS
        output, as :meth:`sample` does.
        """
        if part.cells is None:
            raise ValueError(
                f"read_cells needs a part inside a subslice of '{self.quantity}', "
                f"got the part {part.t_start:g}..{part.t_end:g} outside the slice"
            )
        i_index, j_index = part.cells
        values = part.subslice.data[self._frames(times), i_index, j_index]
        return np.asarray(values, dtype=float)

    def _frames(self, times: np.ndarray) -> np.ndarray | int:
        """The frame of each time, horizon-checked as :meth:`sample` checks it."""
        first = float(times[0])
        if (times == first).all():
            return self._time_index(first)
        self._check_horizon(float(times.max()))
        return _nearest_frames(self._frame_times, times)

    @cached_property
    def _frame_times(self) -> np.ndarray:
        """The times of the slice frames [s]."""
        return np.asarray(self._slice.times, dtype=float)

    @property
    def z_m(self) -> float:
        """Height of the slice [m]: the mid z of its extent."""
        return _slice_z_mid(self._slice)

    def grid(self, x_centres, y_centres) -> SliceGrid:
        """A reader of this slice on a regular grid; see :class:`SliceGrid`."""
        return SliceGrid(self, x_centres, y_centres)

    @cached_property
    def end_time_s(self) -> float:
        """Return the time of the last slice frame [s]."""
        return float(self._slice.times[-1])

    @cached_property
    def output_interval_s(self) -> float:
        """Return the output interval of the slice frames [s]."""
        return _output_interval(self._slice.times)

    def _check_horizon(self, time_s: float) -> None:
        """Raise, or warn once, when *time_s* is past the slice output."""
        last = self.end_time_s
        interval = self.output_interval_s
        if time_s <= last + interval:
            return
        quantity = self._slice.quantity.name
        message = horizon_error_message(quantity, time_s, last, interval)
        if not self._allow_horizon_hold:
            raise FdsHorizonError(message)
        if self._warned_horizon:
            return
        self._warned_horizon = True
        _logger.warning(
            "'%s' past the FDS output (t=%.1f s > %.1f s): holding the last "
            "frame for the rest of the run (--allow-fds-horizon-hold).",
            quantity,
            time_s,
            last,
        )

    def _time_index(self, ts: float) -> int:
        """The nearest frame of *ts*, horizon-checked the first time it is asked."""
        t_index = self._t_index_cache.get(ts)
        if t_index is not None:
            return t_index
        self._check_horizon(ts)
        t_index = int(self._slice.get_nearest_timestep(ts))
        if len(self._t_index_cache) >= _T_INDEX_CACHE_SIZE:
            self._t_index_cache.clear()
        self._t_index_cache[ts] = t_index
        return t_index

    def sample(self, time_s: float, x: float, y: float) -> float:
        """Return the sampled scalar value at one time and x/y point.

        Raises ``FdsHorizonError`` past the FDS output (see the class), and
        ``ValueError`` for a point outside the slice.
        """
        ts = float(time_s)
        if ts != self._cached_time_s:
            self._cached_t_index = self._time_index(ts)
            self._cached_time_s = ts
        t_index = self._cached_t_index
        subslice = self._find_subslice(float(x), float(y))
        if subslice is None:
            raise ValueError(
                f"Point ({x}, {y}) is outside the sampled FDS slice domain"
            )
        xs, ys = self._axes(subslice)
        i_index = self._nearest_index(xs, float(x))
        j_index = self._nearest_index(ys, float(y))
        return float(subslice.data[t_index, i_index, j_index])


def _clip_to_extent(
    x0: float, y0: float, dx: float, dy: float, ext
) -> tuple[float, float] | None:
    """The fractions ``(ta, tb)`` of a segment inside a closed extent, or None.

    Liang-Barsky clipping of ``(x0, y0) + t * (dx, dy)``, ``0 <= t <= 1``.
    A span of zero length (a touched corner or edge) counts as outside.
    """
    ta, tb = 0.0, 1.0
    for p, q in (
        (-dx, x0 - ext.x_start),
        (dx, ext.x_end - x0),
        (-dy, y0 - ext.y_start),
        (dy, ext.y_end - y0),
    ):
        if p == 0.0:
            if q < 0.0:
                return None
            continue
        if p < 0.0:
            ta = max(ta, q / p)
        else:
            tb = min(tb, q / p)
    return (ta, tb) if ta < tb else None


def _subtract(
    span: tuple[float, float], taken: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """The pieces of *span* not inside any interval of *taken*."""
    pieces = [span]
    for a, b in taken:
        pieces = [
            piece
            for ta, tb in pieces
            for piece in ((ta, min(tb, a)), (max(ta, b), tb))
            if piece[0] < piece[1]
        ]
    return pieces


def _nearest_frames(frame_times: np.ndarray, times: np.ndarray) -> np.ndarray:
    """``Slice.get_nearest_timestep`` of fdsreader 1.11.7 for many times.

    The nearer of the two frames around each time, ties to the later one;
    a time of 0 or less takes the first frame at or after it. Pinned
    against fdsreader's own method in ``tests/test_route_grid_sampling.py``.
    """
    count = len(frame_times)
    idx = np.searchsorted(frame_times, times, side="left")
    before = frame_times[idx - 1]
    after = frame_times[np.minimum(idx, count - 1)]
    nearer_before = np.abs(times - before) < np.abs(times - after)
    take_before = (times > 0) & ((idx == count) | nearer_before)
    return np.where(take_before, idx - 1, idx)


def _nearest_indices(coords: np.ndarray, values: np.ndarray) -> np.ndarray:
    """``SliceFieldSampler._nearest_index`` of every value, ties to the lower."""
    values = np.asarray(values, dtype=float)
    if len(coords) <= 1:
        return np.zeros(values.shape, dtype=int)
    right = np.clip(np.searchsorted(coords, values), 1, len(coords) - 1)
    left = right - 1
    take_left = values - coords[left] <= coords[right] - values
    return np.where(take_left, left, right)


def _cell_fractions(
    x0: float,
    y0: float,
    dx: float,
    dy: float,
    ta: float,
    tb: float,
    axes: tuple[np.ndarray, np.ndarray],
) -> np.ndarray:
    """Sample fractions of the part ``ta..tb`` of a segment, one per cell.

    Marches the value positions of the segment's dominant axis, as FDS+Evac
    ``See_door`` marches the cells of its mesh (``evac.f90``): the start of
    the part, every value position strictly between the nearest positions
    of its two ends, and its end. Moving an end within a cell does not move
    the samples between. Two ends that read the same value give one sample.
    """
    along_x = abs(dx) >= abs(dy)
    coords, origin, delta = (axes[0], x0, dx) if along_x else (axes[1], y0, dy)
    nearest = SliceFieldSampler._nearest_index
    i0 = nearest(coords, origin + ta * delta)
    i1 = nearest(coords, origin + tb * delta)
    if i0 == i1 and _same_cell(x0, y0, dx, dy, ta, tb, axes):
        return np.array([ta])
    lo, hi = min(i0, i1), max(i0, i1)
    inner = (coords[lo + 1 : hi] - origin) / delta
    if i1 < i0:
        inner = inner[::-1]
    return np.concatenate(([ta], inner, [tb]))


def _same_cell(
    x0: float,
    y0: float,
    dx: float,
    dy: float,
    ta: float,
    tb: float,
    axes: tuple[np.ndarray, np.ndarray],
) -> bool:
    """Whether the points at fractions *ta* and *tb* read the same value."""
    nearest = SliceFieldSampler._nearest_index
    return nearest(axes[0], x0 + ta * dx) == nearest(axes[0], x0 + tb * dx) and nearest(
        axes[1], y0 + ta * dy
    ) == nearest(axes[1], y0 + tb * dy)


class SliceGrid:
    """Values of a slice at grid cell centres, without touching the sampler.

    Reads ``subslice.data`` directly, nearest value as in
    :meth:`SliceFieldSampler.sample`, and leaves the sampler's caches and
    one-time warnings alone, so reading the grid never changes what a run
    samples or logs. A cell covered by two subslices takes the first one; a
    cell outside the slice is NaN. Past the last frame the last one is read.
    """

    def __init__(self, sampler: SliceFieldSampler, x_centres, y_centres):
        self._sampler = sampler
        xs = np.asarray(x_centres, dtype=float)
        ys = np.asarray(y_centres, dtype=float)
        self.shape = (len(ys), len(xs))
        gx, gy = np.meshgrid(xs, ys)
        free = np.ones(self.shape, dtype=bool)
        self._parts = []
        for subslice in sampler._subslices:
            ext = subslice.extent
            inside = (
                free
                & (gx >= ext.x_start)
                & (gx <= ext.x_end)
                & (gy >= ext.y_start)
                & (gy <= ext.y_end)
            )
            if not inside.any():
                continue
            free &= ~inside
            ax, ay = sampler._axes(subslice)
            cells = np.flatnonzero(inside)
            i = np.array([sampler._nearest_index(ax, v) for v in gx.flat[cells]])
            j = np.array([sampler._nearest_index(ay, v) for v in gy.flat[cells]])
            self._parts.append((subslice, cells, i, j))

    def time_index(self, time_s: float) -> int:
        """Index of the slice frame nearest *time_s*."""
        return int(self._sampler._slice.get_nearest_timestep(float(time_s)))

    def frame_time_s(self, index: int) -> float:
        """Time of slice frame *index* [s]."""
        return float(self._sampler._slice.times[index])

    def values(self, index: int) -> np.ndarray:
        """The grid at slice frame *index*, shape ``(ny, nx)``, NaN outside."""
        out = np.full(self.shape[0] * self.shape[1], np.nan, dtype=np.float32)
        for subslice, cells, i, j in self._parts:
            out[cells] = subslice.data[index][i, j]
        return out.reshape(self.shape)


def _is_horizontal(slice_obj) -> bool:
    """True for a z-normal (PBZ) slice; fdsreader reports it as orientation 3."""
    return getattr(slice_obj, "orientation", 3) == 3


def _slice_z_mid(slice_obj) -> float:
    """Return the mid-height of a slice's z-extent."""
    return (slice_obj.extent.z_start + slice_obj.extent.z_end) / 2


def _warn_on_height_mismatch(
    chosen,
    requested_height_m: float | None,
    quantity: str,
    n_matches: int,
    fds_dir: str,
) -> None:
    """Warn when the selected slice sits far from the requested height.

    Height only ever breaks ties: a case holding a single slice of the
    requested quantity uses it whatever its z, and a multi-slice case picks
    the nearest available, which may still be nowhere near.  Either way the
    caller gets readings from a different part of the smoke layer than it
    asked for, with no other signal that it happened.
    """

    if requested_height_m is None:
        return
    z_mid = _slice_z_mid(chosen)
    if abs(z_mid - requested_height_m) <= _SLICE_HEIGHT_TOLERANCE_M:
        return
    counted = "1 slice" if n_matches == 1 else f"{n_matches} slices"
    _logger.warning(
        "Requested a '%s' slice at z=%.2f m but the nearest available in %s is "
        "at z=%.2f m (%.2f m away; %s of this quantity in the case). "
        "Sampling continues at z=%.2f m, so every reading from this quantity "
        "describes that height, not the one requested.",
        quantity,
        requested_height_m,
        fds_dir,
        z_mid,
        abs(z_mid - requested_height_m),
        counted,
        z_mid,
    )


def load_slice_sampler(
    fds_dir: str,
    quantity: str | tuple[str, ...] | list[str],
    *,
    simulation=None,
    slice_height_m: float | None = None,
    allow_horizon_hold: bool = False,
) -> SliceFieldSampler:
    """Load one FDS slice quantity and return a ready-to-use sampler.

    Parameters
    ----------
    quantity :
        The FDS slice quantity name, or a sequence of candidate names tried
        in order (the first that matches wins), for decks that spell the
        same field differently.  Only list genuine synonyms: FDS's
        ``'EXTINCTION'`` quantity, for example, is an unrelated 0/1/-1
        combustion-suppression flag (User Guide Sec. 22.10.29), not a
        spelling of ``'SOOT EXTINCTION COEFFICIENT'`` (the K [1/m] smoke
        extinction coefficient, Sec. 22.10.5), and must never be used as a
        fallback for it.
    simulation : optional
        A pre-loaded ``fdsreader.Simulation`` instance.  When provided the
        expensive directory parse is skipped.
    slice_height_m : optional
        Desired z-height for horizontal slices.  When given, the slice
        whose z-extent is closest to this value is selected.
    allow_horizon_hold : optional
        Hold the last frame past the FDS output instead of raising
        ``FdsHorizonError`` (see ``SliceFieldSampler``).

    Raises ModuleNotFoundError if fdsreader is not installed, or
    IndexError if none of the requested quantities are found in the FDS case.
    """
    sim = simulation if simulation is not None else _open_simulation(fds_dir)
    candidates = (quantity,) if isinstance(quantity, str) else tuple(quantity)
    matches = []
    for name in candidates:
        matches = sim.slices.filter_by_quantity(name)
        if matches:
            break
    if not matches:
        tried = ", ".join(f"'{c}'" for c in candidates)
        raise IndexError(f"No slice with quantity {tried} found in {fds_dir}")
    chosen = select_horizontal_slice(matches, slice_height_m, name, fds_dir)
    return SliceFieldSampler(chosen, allow_horizon_hold=allow_horizon_hold)


def fds_output_horizon(fds_dir: str, *, simulation=None) -> tuple[float, float] | None:
    """Return (last time, output interval) [s] of the FDS slice output.

    Every slice in the case counts, read or not: the one whose last time
    plus output interval comes first sets the horizon.  A single-frame slice
    has no interval and is skipped (its sampler still raises if read).  None
    when the case has no slice with two frames.
    """
    sim = simulation if simulation is not None else _open_simulation(fds_dir)
    ends = [
        (float(s.times[-1]), _output_interval(s.times))
        for s in sim.slices
        if len(s.times) > 1
    ]
    return min(ends, key=sum) if ends else None


def select_horizontal_slice(
    slices,
    slice_height_m: float | None,
    quantity: str,
    fds_dir,
):
    """Pick the horizontal slice nearest *slice_height_m* from *slices*.

    The one rule for every FDS reading, so that walking speed, FED and sign
    legibility describe the same height.  Declaration order only breaks ties.
    Raises IndexError if *slices* holds no horizontal slice.
    """
    # Agents are sampled on a plane in x/y; a vertical (PBX/PBY) slice would be
    # read as if it were one, and its mid-height can look closest to the
    # requested height.
    matches = [s for s in slices if _is_horizontal(s)]
    if not matches:
        raise IndexError(
            f"No horizontal (PBZ) slice with quantity '{quantity}' found in {fds_dir}"
        )
    if slice_height_m is not None and len(matches) > 1:
        chosen = min(matches, key=lambda s: abs(_slice_z_mid(s) - slice_height_m))
    else:
        chosen = matches[0]
    _warn_on_height_mismatch(chosen, slice_height_m, quantity, len(matches), fds_dir)
    return chosen
