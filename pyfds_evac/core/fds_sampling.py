"""Shared FDS slice sampling via fdsreader.

Provides nearest-neighbor spatial and temporal lookup on horizontal FDS
slice files.  Used by both the smoke-speed model (extinction) and the
FED model (gas concentrations).
"""

from __future__ import annotations

import logging

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


class SliceFieldSampler:
    """Sample one ``fdsreader`` slice quantity with nearest-neighbor lookup."""

    def __init__(self, slice_obj):
        """Cache the slice object and its subslices for repeated sampling."""
        self._slice = slice_obj
        self._subslices = list(slice_obj.subslices)
        self._last_subslice = None
        self._cached_time_s: float | None = None
        self._cached_t_index: int = 0

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

    @staticmethod
    def _nearest_index(start: float, end: float, count: int, value: float) -> int:
        """Return the nearest cell index along one slice axis."""
        if count <= 1 or end <= start:
            return 0
        dx = (end - start) / count
        center = start + 0.5 * dx
        index = round((value - center) / dx)
        return max(0, min(count - 1, int(index)))

    def sample(self, time_s: float, x: float, y: float) -> float:
        """Return the sampled scalar value at one time and x/y point."""
        subslice = self._find_subslice(float(x), float(y))
        if subslice is None:
            raise ValueError(
                f"Point ({x}, {y}) is outside the sampled FDS slice domain"
            )

        ts = float(time_s)
        if ts != self._cached_time_s:
            self._cached_time_s = ts
            self._cached_t_index = int(self._slice.get_nearest_timestep(ts))
        t_index = self._cached_t_index
        i_index = self._nearest_index(
            subslice.extent.x_start, subslice.extent.x_end, subslice.shape[0], float(x)
        )
        j_index = self._nearest_index(
            subslice.extent.y_start, subslice.extent.y_end, subslice.shape[1], float(y)
        )
        return float(subslice.data[t_index, i_index, j_index])


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
    if slice_height_m is not None and len(matches) > 1:
        chosen = min(matches, key=lambda s: abs(_slice_z_mid(s) - slice_height_m))
    else:
        chosen = matches[0]
    _warn_on_height_mismatch(chosen, slice_height_m, name, len(matches), fds_dir)
    return SliceFieldSampler(chosen)
