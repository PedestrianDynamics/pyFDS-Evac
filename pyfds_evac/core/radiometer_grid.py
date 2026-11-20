"""Radiometer devices of an FDS case as a regular grid in space and time.

Reading side of the radiometer radiant source (#276): select the
``RADIOMETER`` points of one orientation and height, look up the ``&PROP`` of
their ``&DEVC`` records in the deck, and interpolate the readings bilinearly
in x, y and linearly in time. Nothing here changes a model result; the heat
model that uses it enforces the ``&PROP`` values.

fdsreader is reached only through ``fdsreader_adapter``. Quantity names are
matched with and without the ``GAS`` suffix: FDS 6.10.1 reports
``RADIOMETER`` for ``QUANTITY='RADIOMETER GAS'``, older names keep ``GAS``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pyfds_evac.core.fds_deck import FdsDeck
from pyfds_evac.core.fdsreader_adapter import DevicePoint, DeviceSet

#: Tolerance (m, or unit-vector component) for orientation, z and grid spacing.
TOLERANCE = 1e-6

RADIOMETER_QUANTITIES = ("RADIOMETER", "RADIOMETER GAS")

#: FDS 6.10.1 UG Sec. 22.10.12, p. 381, and ``&MISC`` ``TMPA`` (deg C).
DEFAULT_GAUGE_EMISSIVITY = 1.0
DEFAULT_HEAT_TRANSFER_COEFFICIENT = 10.0
DEFAULT_TMPA_C = 20.0

_POINT_SUFFIX = re.compile(r"-\d+$")
_MAX_LISTED = 10


class RadiometerGridError(ValueError):
    """The radiometer devices cannot serve the requested reading."""


def _unit(orientation: Sequence[float]) -> tuple[float, float, float]:
    vector = tuple(float(v) for v in orientation)
    norm = math.sqrt(sum(v * v for v in vector))
    if len(vector) != 3 or not math.isfinite(norm) or norm == 0.0:
        raise RadiometerGridError(
            f"radiometer orientation must be a non-zero 3-vector, got {orientation!r}"
        )
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _listed(items: Sequence[object]) -> str:
    shown = ", ".join(str(item) for item in items[:_MAX_LISTED])
    more = len(items) - _MAX_LISTED
    return shown if more <= 0 else f"{shown}, ... ({more} more)"


def select_radiometers(
    devices: DeviceSet, orientation: Sequence[float], z: float
) -> tuple[DevicePoint, ...]:
    """The radiometer points facing *orientation* at height *z* (to 1e-6)."""
    wanted = _unit(orientation)
    radiometers = [p for p in devices.points if p.quantity in RADIOMETER_QUANTITIES]
    if not radiometers:
        raise RadiometerGridError(
            f"no RADIOMETER device in the FDS case in {devices.case_dir}"
        )
    facing = [
        p
        for p in radiometers
        if all(abs(a - b) <= TOLERANCE for a, b in zip(p.orientation, wanted))
    ]
    if not facing:
        found = sorted({p.orientation for p in radiometers})
        raise RadiometerGridError(
            f"no RADIOMETER device with orientation {wanted} in {devices.case_dir}; "
            f"orientations present: {_listed(found)}"
        )
    selected = tuple(p for p in facing if abs(p.xyz[2] - z) <= TOLERANCE)
    if not selected:
        heights = sorted({p.xyz[2] for p in facing})
        raise RadiometerGridError(
            f"no RADIOMETER device with orientation {wanted} at z={z} m in "
            f"{devices.case_dir}; heights present: {_listed(heights)}"
        )
    return selected


@dataclass(frozen=True)
class RadiometerProp:
    """The ``&PROP`` values of one radiometer ``&DEVC`` (FDS defaults filled in)."""

    device_id: str
    prop_id: str | None
    gauge_temperature_c: float
    gauge_emissivity: float
    heat_transfer_coefficient: float


def device_id_of(point_id: str) -> str:
    """The ``&DEVC`` ID of a ``POINTS`` column: ``RAD_up-3`` gives ``RAD_up``."""
    return _POINT_SUFFIX.sub("", point_id)


def radiometer_props(
    deck: FdsDeck, points: Sequence[DevicePoint]
) -> dict[str, RadiometerProp]:
    """The ``&PROP`` of each ``&DEVC`` behind *points*, keyed by ``&DEVC`` ID.

    A ``&DEVC`` without ``PROP_ID``, or a ``&PROP`` without a key, reads as
    the FDS default; ``GAUGE_TEMPERATURE`` then defaults to ``TMPA``.
    """
    misc = deck.first("MISC")
    tmpa = DEFAULT_TMPA_C if misc is None else misc.num("TMPA", DEFAULT_TMPA_C)
    devcs = {r.id: r for r in reversed(deck.group("DEVC")) if r.id is not None}
    props = {r.id: r for r in reversed(deck.group("PROP")) if r.id is not None}
    return {
        device_id: _prop_of(deck, device_id, devcs, props, tmpa)
        for device_id in dict.fromkeys(device_id_of(p.id) for p in points)
    }


def _prop_of(deck, device_id, devcs, props, tmpa) -> RadiometerProp:
    devc = devcs.get(device_id)
    if devc is None:
        raise RadiometerGridError(
            f"cannot read the &PROP of radiometer {device_id!r}: no &DEVC with "
            f"that ID in the deck {deck.path}"
        )
    prop_id = devc.text("PROP_ID")
    prop = None if prop_id is None else props.get(prop_id)
    if prop_id is not None and prop is None:
        raise RadiometerGridError(
            f"cannot read the &PROP of radiometer {device_id!r}: &DEVC names "
            f"PROP_ID {prop_id!r}, which the deck {deck.path} does not define"
        )
    if prop is None:
        return RadiometerProp(
            device_id,
            prop_id,
            tmpa,
            DEFAULT_GAUGE_EMISSIVITY,
            DEFAULT_HEAT_TRANSFER_COEFFICIENT,
        )
    return RadiometerProp(
        device_id,
        prop_id,
        prop.num("GAUGE_TEMPERATURE", tmpa),
        prop.num("GAUGE_EMISSIVITY", DEFAULT_GAUGE_EMISSIVITY),
        prop.num("HEAT_TRANSFER_COEFFICIENT", DEFAULT_HEAT_TRANSFER_COEFFICIENT),
    )


def _axis(values: Sequence[float], name: str) -> np.ndarray:
    """Sorted node coordinates, values within 1e-6 m merged, spacing checked."""
    nodes: list[float] = []
    for value in sorted(values):
        if not nodes or value - nodes[-1] > TOLERANCE:
            nodes.append(value)
    axis = np.asarray(nodes, dtype=float)
    if axis.size < 3:
        return axis
    steps = np.diff(axis)
    if np.max(np.abs(steps - steps.mean())) > TOLERANCE:
        raise RadiometerGridError(
            f"radiometer grid is not uniform in {name}: node spacings "
            f"{_listed([round(float(s), 9) for s in steps])} m differ by more than "
            f"{TOLERANCE} m"
        )
    return axis


def _cell(axis: np.ndarray, coord: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lower node index and fractional position of *coord* on *axis*."""
    if axis.size == 1:
        return np.zeros(coord.shape, dtype=int), np.zeros(coord.shape)
    clamped = np.clip(coord, axis[0], axis[-1])
    index = np.clip(np.searchsorted(axis, clamped, side="right") - 1, 0, axis.size - 2)
    return index, (clamped - axis[index]) / (axis[index + 1] - axis[index])


class RadiometerGrid:
    """Readings on a full rectilinear grid, interpolated in x, y and time.

    ``values`` has shape ``(n_times, n_y, n_x)``. Bilinear inside the grid and
    exact at the nodes; a grid with one row (or column) holds only agents on
    it, to 1e-6 m. Linear in time between ``times``; outside them is an error,
    never a held value (the horizon rule belongs to the caller).
    """

    def __init__(
        self, xs: np.ndarray, ys: np.ndarray, times: np.ndarray, values: np.ndarray
    ) -> None:
        if values.shape != (times.size, ys.size, xs.size):
            raise RadiometerGridError(
                f"radiometer values have shape {values.shape}, expected "
                f"{(times.size, ys.size, xs.size)}"
            )
        if times.size == 0 or np.any(np.diff(times) <= 0):
            raise RadiometerGridError(
                "radiometer output times must be non-empty and strictly increasing"
            )
        self.xs, self.ys, self.times, self.values = xs, ys, times, values

    @classmethod
    def from_points(
        cls, points: Sequence[DevicePoint], times: np.ndarray
    ) -> RadiometerGrid:
        """Build the grid from selected points; every node must be present."""
        if not points:
            raise RadiometerGridError("no radiometer points to build a grid from")
        times = np.asarray(times, dtype=float)
        xs = _axis([p.xyz[0] for p in points], "x")
        ys = _axis([p.xyz[1] for p in points], "y")
        values = np.full((times.size, ys.size, xs.size), np.nan)
        placed: dict[tuple[int, int], str] = {}
        for point in points:
            ix = int(np.argmin(np.abs(xs - point.xyz[0])))
            iy = int(np.argmin(np.abs(ys - point.xyz[1])))
            if (ix, iy) in placed:
                raise RadiometerGridError(
                    f"radiometer points {placed[(ix, iy)]!r} and {point.id!r} are "
                    f"both at x={xs[ix]}, y={ys[iy]}"
                )
            placed[(ix, iy)] = point.id
            values[:, iy, ix] = point.data
        missing = [
            (float(xs[ix]), float(ys[iy]))
            for iy in range(ys.size)
            for ix in range(xs.size)
            if (ix, iy) not in placed
        ]
        if missing:
            raise RadiometerGridError(
                f"radiometer points do not fill the grid: {len(missing)} missing "
                f"nodes (x, y): {_listed(missing)}"
            )
        return cls(xs, ys, times, values)

    def contains(self, x: np.ndarray | float, y: np.ndarray | float) -> np.ndarray:
        """Which positions lie in the grid (edges and a single row to 1e-6 m)."""
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        return (
            (x >= self.xs[0] - TOLERANCE)
            & (x <= self.xs[-1] + TOLERANCE)
            & (y >= self.ys[0] - TOLERANCE)
            & (y <= self.ys[-1] + TOLERANCE)
        )

    def sample(
        self, time: float, x: np.ndarray | float, y: np.ndarray | float
    ) -> np.ndarray:
        """The reading at *time* for positions *x*, *y*; outside the grid raises."""
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        outside = ~self.contains(x, y)
        if np.any(outside):
            where = [(float(a), float(b)) for a, b in zip(x[outside], y[outside])]
            raise RadiometerGridError(
                f"{len(where)} position(s) outside the radiometer grid "
                f"(x {self.xs[0]} to {self.xs[-1]} m, y {self.ys[0]} to "
                f"{self.ys[-1]} m): {_listed(where)}"
            )
        frame = self._at_time(float(time))
        ix, fx = _cell(self.xs, x)
        iy, fy = _cell(self.ys, y)
        ix1 = np.minimum(ix + 1, self.xs.size - 1)
        iy1 = np.minimum(iy + 1, self.ys.size - 1)
        lower = frame[iy, ix] * (1 - fx) + frame[iy, ix1] * fx
        upper = frame[iy1, ix] * (1 - fx) + frame[iy1, ix1] * fx
        return lower * (1 - fy) + upper * fy

    def _at_time(self, time: float) -> np.ndarray:
        if not self.times[0] <= time <= self.times[-1]:
            raise RadiometerGridError(
                f"time {time} s is outside the radiometer output "
                f"({self.times[0]} to {self.times[-1]} s)"
            )
        if self.times.size == 1:
            return self.values[0]
        k = int(np.searchsorted(self.times, time, side="right")) - 1
        k = min(k, self.times.size - 2)
        w = (time - self.times[k]) / (self.times[k + 1] - self.times[k])
        return self.values[k] * (1 - w) + self.values[k + 1] * w
