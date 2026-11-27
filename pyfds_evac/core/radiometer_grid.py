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

import hashlib
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pyfds_evac.core.fds_deck import FdsDeck, FdsDeckError, parse_fds_deck
from pyfds_evac.core.fdsreader_adapter import (
    DevicePoint,
    DeviceSet,
    read_fds_devices,
)

_logger = logging.getLogger(__name__)

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


def parse_orientation(text: str) -> tuple[float, float, float]:
    """Parse ``--heat-radiometer-orientation``: ``x,y,z``, not all zero, finite."""
    parts = [part.strip() for part in str(text).split(",")]
    try:
        vector = tuple(float(part) for part in parts)
    except ValueError:
        vector = ()
    if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
        raise RadiometerGridError(
            f"radiometer orientation must be three numbers x,y,z, got {text!r}"
        )
    return _unit(vector)


def _facing(devices: DeviceSet, orientation: Sequence[float]) -> list[DevicePoint]:
    """The radiometer points facing *orientation*, at every height."""
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
    return facing


def radiometer_heights(
    devices: DeviceSet, orientation: Sequence[float]
) -> tuple[float, ...]:
    """The distinct heights (to 1e-6 m) of the radiometers facing *orientation*."""
    heights: list[float] = []
    for z in sorted(p.xyz[2] for p in _facing(devices, orientation)):
        if not heights or z - heights[-1] > TOLERANCE:
            heights.append(z)
    return tuple(heights)


def select_radiometers(
    devices: DeviceSet, orientation: Sequence[float], z: float
) -> tuple[DevicePoint, ...]:
    """The radiometer points facing *orientation* at height *z* (to 1e-6)."""
    facing = _facing(devices, orientation)
    selected = tuple(p for p in facing if abs(p.xyz[2] - z) <= TOLERANCE)
    if not selected:
        heights = sorted({p.xyz[2] for p in facing})
        raise RadiometerGridError(
            f"no RADIOMETER device with orientation {_unit(orientation)} at z={z} m "
            f"in {devices.case_dir}; heights present: {_listed(heights)}"
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


#: Slack [s] on the last output time: absorbs float noise in the clock.
TIME_TOLERANCE_S = 1e-6

_DEVC_EXAMPLE = (
    "&PROP ID='skin', GAUGE_TEMPERATURE={t_skin:g} /   ! = --heat-skin-temperature\n"
    "&DEVC ID='RAD_r01', QUANTITY='RADIOMETER GAS', ORIENTATION={orientation},\n"
    "      PROP_ID='skin', XBP=x0,x1, y1,y1, {z:g},{z:g}, POINTS=nx, TIME_HISTORY=T /"
    "   ! one &DEVC per row y_j\n"
)


def _no_devices_message(
    fds_dir: str, orientation: str, z: float, t_skin: float, reason: str
) -> str:
    """The error for a case without usable radiometers, with the line to add."""
    return (
        f"--heat-radiant-source radiometer: {reason}. Add radiometers facing "
        f"{orientation} at z={z:g} m (the TEMPERATURE slice height) on a regular "
        f"grid, one &DEVC per row, to the FDS case in {fds_dir}:\n"
        + _DEVC_EXAMPLE.format(t_skin=t_skin, orientation=orientation, z=z)
    )


@dataclass
class RadiometerSource:
    """The radiometer readings the heat model uses as its radiant term (#276).

    ``reading`` is the net radiant flux to a plate at the gauge temperature
    (FDS UG 6.10.1 Eq. 22.36, kW/m2), bilinear in x, y and linear in time.
    Time follows the slice rule: a time up to one output interval past the
    last frame holds the last frame; later it is an ``FdsHorizonError``, or,
    with *allow_horizon_hold*, held after one warning. A time before the first
    frame is an ``FdsStartError``.
    """

    grid: RadiometerGrid
    orientation: tuple[float, float, float]
    z_m: float
    gauge_temperature_c: float
    gauge_emissivity: float
    n_devices: int
    deck_path: Path
    deck_sha256: str
    allow_horizon_hold: bool = False
    _warned_horizon: bool = field(default=False, repr=False)

    def covers(self, x: float, y: float) -> bool:
        """Whether the point lies in the radiometer grid."""
        return bool(self.grid.contains(x, y))

    def reading(self, time_s: float, x: float, y: float) -> float:
        """The net reading at one time and x/y point; outside the grid raises."""
        if not self.covers(x, y):
            raise RadiometerGridError(
                f"Point ({x}, {y}) lies in the TEMPERATURE slice but outside the "
                f"radiometer grid (x {self.grid.xs[0]} to {self.grid.xs[-1]} m, "
                f"y {self.grid.ys[0]} to {self.grid.ys[-1]} m); the heat FED needs "
                "a radiometer reading at every agent."
            )
        value = float(self.grid.sample(self._held(float(time_s)), x, y))
        if math.isfinite(value):
            return value
        from pyfds_evac.core.fds_sampling import FdsDataError

        raise FdsDataError(
            f"'RADIOMETER' reading is not a finite number at ({x:.2f}, {y:.2f}) m, "
            f"t={float(time_s):.1f} s, inside the radiometer grid. Check the FDS "
            "device output (a NaN there means the device wrote no value), or "
            "rerun FDS."
        )

    def _before_first(self, time_s: float, first: float) -> float:
        """*first* within the start tolerance of *time_s*; an error before it."""
        from pyfds_evac.config import messages
        from pyfds_evac.core.fds_sampling import FDS_START_TOLERANCE_S, FdsStartError

        if time_s >= first - FDS_START_TOLERANCE_S:
            return first
        raise FdsStartError(
            messages.fds_start_late(
                None, first, quantity="RADIOMETER", requested_s=time_s
            )
        )

    def _held(self, time_s: float) -> float:
        """*time_s* clamped to the output, after the horizon rule."""
        times = self.grid.times
        first, last = float(times[0]), float(times[-1])
        if first <= time_s <= last:
            return time_s
        if time_s < first:
            return self._before_first(time_s, first)
        interval = float(np.max(np.diff(times))) if times.size > 1 else 0.0
        if time_s <= last + interval + TIME_TOLERANCE_S:
            return last
        from pyfds_evac.core.fds_sampling import (
            FdsHorizonError,
            horizon_error_message,
        )

        message = horizon_error_message("RADIOMETER", time_s, last, interval)
        if not self.allow_horizon_hold:
            raise FdsHorizonError(message)
        if not self._warned_horizon:
            self._warned_horizon = True
            _logger.warning(
                "'RADIOMETER' past the FDS output (t=%.1f s > %.1f s): holding "
                "the last frame for the rest of the run (--allow-fds-horizon-hold).",
                time_s,
                last,
            )
        return last

    def manifest_entry(self) -> dict[str, object]:
        """The run-manifest fields of this source."""
        return {
            "radiometer_orientation": list(self.orientation),
            "radiometer_height_m": self.z_m,
            "radiometer_gauge_temperature_celsius": self.gauge_temperature_c,
            "radiometer_gauge_emissivity": self.gauge_emissivity,
            "radiometer_device_count": self.n_devices,
            "radiometer_grid_origin_m": [
                float(self.grid.xs[0]),
                float(self.grid.ys[0]),
            ],
            "radiometer_grid_spacing_m": [
                _spacing(self.grid.xs),
                _spacing(self.grid.ys),
            ],
            "fds_deck_sha256": self.deck_sha256,
        }


def _spacing(axis: np.ndarray) -> float | None:
    """The node spacing of *axis*; None for a single node."""
    return round(float(axis[1] - axis[0]), 9) if axis.size > 1 else None


def load_radiometer_source(
    fds_dir: str | Path,
    *,
    orientation: str,
    skin_temperature_c: float,
    slice_z_m: float,
    half_cell_m: float,
    allow_horizon_hold: bool = False,
) -> RadiometerSource:
    """Read the radiometers of the case in *fds_dir* as the radiant source.

    Selects the radiometers facing *orientation* at the height nearest
    *slice_z_m*, which must lie within *half_cell_m* of it; checks that
    every selected ``&PROP`` has ``GAUGE_TEMPERATURE`` equal to
    *skin_temperature_c* (to 1e-6 deg C) and one emissivity; and records
    the sha256 of the deck. Raises ``RadiometerGridError`` otherwise.
    """
    unit = parse_orientation(orientation)
    try:
        devices = read_fds_devices(fds_dir)
        heights = radiometer_heights(devices, unit)
    except (ValueError, RadiometerGridError) as exc:
        # A case without any device output has no TIME device either.
        raise RadiometerGridError(
            _no_devices_message(
                str(fds_dir), orientation, slice_z_m, skin_temperature_c, str(exc)
            )
        ) from exc
    z = min(heights, key=lambda h: abs(h - slice_z_m))
    if abs(z - slice_z_m) > half_cell_m + TOLERANCE:
        raise RadiometerGridError(
            f"the radiometers facing {orientation} in {fds_dir} are at z="
            f"{_listed(list(heights))} m but the TEMPERATURE slice is at z="
            f"{slice_z_m:g} m; they must lie within half a cell "
            f"({half_cell_m:g} m) of it, so that convection and radiation come "
            "from one height."
        )
    points = select_radiometers(devices, unit, z)
    deck_path, deck = _read_deck(devices, fds_dir)
    props = radiometer_props(deck, points)
    gauge_t, emissivity = _checked_props(props, skin_temperature_c, deck_path)
    grid = RadiometerGrid.from_points(points, devices.times)
    _check_units(points)
    return RadiometerSource(
        grid=grid,
        orientation=unit,
        z_m=z,
        gauge_temperature_c=gauge_t,
        gauge_emissivity=emissivity,
        n_devices=len(points),
        deck_path=deck_path,
        deck_sha256=hashlib.sha256(deck_path.read_bytes()).hexdigest(),
        allow_horizon_hold=allow_horizon_hold,
    )


def _read_deck(devices: DeviceSet, fds_dir) -> tuple[Path, FdsDeck]:
    """The case's ``<CHID>.fds``; a missing deck is an error (the &PROP is in it)."""
    path = devices.case_dir / f"{devices.chid}.fds"
    if not path.is_file():
        raise RadiometerGridError(
            f"the FDS deck {path} is not in the case folder {fds_dir}; the "
            "radiometer source reads GAUGE_TEMPERATURE from its &PROP and "
            "needs the deck next to the output."
        )
    try:
        return path, parse_fds_deck(path)
    except FdsDeckError as exc:
        raise RadiometerGridError(f"cannot read the &PROP from {path}: {exc}") from exc


def _checked_props(
    props: dict[str, RadiometerProp], skin_temperature_c: float, deck_path: Path
) -> tuple[float, float]:
    """The shared gauge temperature and emissivity, or an error."""
    for prop in props.values():
        if abs(prop.gauge_temperature_c - skin_temperature_c) > TOLERANCE:
            raise RadiometerGridError(
                f"radiometer {prop.device_id!r} in {deck_path} has "
                f"GAUGE_TEMPERATURE={prop.gauge_temperature_c:g} C but "
                f"--heat-skin-temperature is {skin_temperature_c:g} C; the "
                "reading is the flux to a plate at the gauge temperature, so "
                "they must be equal. Set GAUGE_TEMPERATURE in the &PROP of the "
                "radiometers (FDS defaults it to TMPA)."
            )
    emissivities = sorted({p.gauge_emissivity for p in props.values()})
    if len(emissivities) != 1:
        raise RadiometerGridError(
            f"the radiometers in {deck_path} have different GAUGE_EMISSIVITY "
            f"values {emissivities}; one grid needs one."
        )
    return skin_temperature_c, emissivities[0]


def _check_units(points: Sequence[DevicePoint]) -> None:
    bad = sorted({p.unit for p in points if p.unit.replace(" ", "") != "kW/m2"})
    if bad:
        raise RadiometerGridError(f"radiometer devices report in {bad}, expected kW/m2")
