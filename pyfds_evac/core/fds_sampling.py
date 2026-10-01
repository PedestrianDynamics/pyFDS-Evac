"""Shared FDS slice sampling via fdsreader.

Provides nearest-neighbor spatial and temporal lookup on horizontal FDS
slice files.  Used by both the smoke-speed model (extinction) and the
FED model (gas concentrations).
"""

from __future__ import annotations

import logging

import numpy as np

try:
    from fdsreader import Simulation
except ModuleNotFoundError:
    Simulation = None


_logger = logging.getLogger(__name__)

# How far the selected slice may sit from the requested height before the
# mismatch is worth reporting.  A slice this far off samples a different part
# of the smoke layer than the caller asked for, which silently changes every
# extinction and gas reading downstream.
_SLICE_HEIGHT_TOLERANCE_M = 0.5


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
        self._axes_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

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

    @property
    def end_time_s(self) -> float:
        """Return the time of the last slice frame [s]."""
        return float(self._slice.times[-1])

    @property
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

    def sample(self, time_s: float, x: float, y: float) -> float:
        """Return the sampled scalar value at one time and x/y point.

        Raises ``FdsHorizonError`` past the FDS output (see the class), and
        ``ValueError`` for a point outside the slice.
        """
        ts = float(time_s)
        if ts != self._cached_time_s:
            self._check_horizon(ts)
            self._cached_time_s = ts
            self._cached_t_index = int(self._slice.get_nearest_timestep(ts))
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
    if simulation is not None:
        sim = simulation
    else:
        if Simulation is None:
            raise ModuleNotFoundError("fdsreader is required to load FDS slice data.")
        sim = Simulation(str(fds_dir))
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
    sim = simulation if simulation is not None else Simulation(str(fds_dir))
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
