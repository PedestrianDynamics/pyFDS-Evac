"""Shared FDS slice sampling via fdsreader.

Provides nearest-neighbor spatial and temporal lookup on horizontal FDS
slice files.  Used by both the smoke-speed model (extinction) and the
FED model (gas concentrations).
"""

from __future__ import annotations

try:
    from fdsreader import Simulation
except ModuleNotFoundError:
    Simulation = None


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


def load_slice_sampler(
    fds_dir: str,
    quantity: str,
    *,
    simulation=None,
    slice_height_m: float | None = None,
) -> SliceFieldSampler:
    """Load one FDS slice quantity and return a ready-to-use sampler.

    Parameters
    ----------
    simulation : optional
        A pre-loaded ``fdsreader.Simulation`` instance.  When provided the
        expensive directory parse is skipped.
    slice_height_m : optional
        Desired z-height for horizontal slices.  When given, the slice
        whose z-extent is closest to this value is selected.

    Raises ModuleNotFoundError if fdsreader is not installed, or
    IndexError if the requested quantity is not found in the FDS case.
    """
    if simulation is not None:
        sim = simulation
    else:
        if Simulation is None:
            raise ModuleNotFoundError("fdsreader is required to load FDS slice data.")
        sim = Simulation(str(fds_dir))
    matches = sim.slices.filter_by_quantity(quantity)
    if not matches:
        raise IndexError(f"No slice with quantity '{quantity}' found in {fds_dir}")
    if slice_height_m is not None and len(matches) > 1:
        best = min(
            matches,
            key=lambda s: abs((s.extent.z_start + s.extent.z_end) / 2 - slice_height_m),
        )
        return SliceFieldSampler(best)
    return SliceFieldSampler(matches[0])
