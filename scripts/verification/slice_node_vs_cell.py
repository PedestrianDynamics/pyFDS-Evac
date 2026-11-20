"""Node-centred against cell-centred slice readings at 1.6 m (#231).

FDS+Evac reads the cell-centred values of the fire cell that holds each
evacuation-grid cell centre (``evac.f90`` ``GET_FIRE_CONDITIONS``); pyFDS-Evac
reads the nearest value position of a slice, which for FDS's default
node-centred ``&SLCF`` is a node value averaged from the surrounding cells.
``assets/slice_node_vs_cell/slice_node_vs_cell.fds`` writes both at the
sampling height. This script reads them with pyFDS-Evac's own samplers,
extinction field, smoke-speed model and FED rate functions and reports how
far the two readings are apart, for K, the speed factor, the gas FED rate and
the heat FED rate. It measures; it does not say which reading is right.

What is compared, per output frame and per fire cell of the plane:

- *node*: the node slice at z = 1.6 m, read by pyFDS-Evac at the cell centre
  (an exact tie between two nodes per axis, which the sampler resolves to the
  lower index) and at the four quadrant points of the cell (each nearest to a
  different corner node, as agents spread over the cell would read).
- *cell*: the cell-centred slices at z = 1.65 m (the cell whose lower face is
  1.6 m, the one FDS+Evac's ``FLOOR`` indexing gives) and at z = 1.55 m (the
  cell below), and their mean, which isolates the in-plane averaging of the
  node value from the half-cell vertical offset.

Interface zone: a cell is in the zone at a frame when the cell-centred
temperature (mean of the two layers) steps by at least ``ZONE_STEP`` of the
frame's range, across a face to an in-plane neighbour or between the two
layers, and the frame's range is at least ``ZONE_MIN_RANGE_K``; the zone is
dilated by one cell. It marks a plume edge or a layer interface crossing the
plane.

Run from the repository root::

    python scripts/verification/slice_node_vs_cell.py --data DIR

``DIR`` is the FDS output of the deck (default ``$SLICE_NODE_VS_CELL_DATA``).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from _fdsreader_open import open_fds_case

from pyfds_evac.core.fds_sampling import SliceFieldSampler, select_horizontal_slice
from pyfds_evac.core.fed import (
    FdsFedField,
    FdsHeatField,
    default_fed_rate_per_minute,
    default_heat_fed_rate_per_minute,
)
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

SAMPLING_HEIGHT_M = 1.6
ZONE_STEP = 0.10
ZONE_MIN_RANGE_K = 5.0
#: Below this a reading counts as clean air for the relative differences.
FLOORS = {"K": 1e-3, "speed_factor": 0.0, "fed_rate": 1e-5, "heat_rate": 1e-6}
UNITS = {
    "K": "1/m",
    "speed_factor": "-",
    "fed_rate": "1/min",
    "heat_rate": "1/min",
    "T": "K",
}
#: Offsets, in cell fractions, of the five points per cell: centre, quadrants.
OFFSETS = ((0.0, 0.0), (-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25))
FED_QUANTITIES = (
    "CARBON MONOXIDE VOLUME FRACTION",
    "CARBON DIOXIDE VOLUME FRACTION",
    "OXYGEN VOLUME FRACTION",
)
EXTINCTION = "SOOT EXTINCTION COEFFICIENT"
TEMPERATURE = "TEMPERATURE"


@dataclass(frozen=True)
class Fields:
    """The pyFDS-Evac readers of one family of slices (node or cell-centred)."""

    smoke: SmokeSpeedModel
    gas: FdsFedField
    heat: FdsHeatField
    #: The fdsreader TEMPERATURE slice, for the grid and the frame times.
    plane: object


def _slice(sim, quantity: str, *, cell_centred: bool, z_m: float):
    matches = [
        s
        for s in sim.slices.filter_by_quantity(quantity)
        if bool(s.cell_centered) == cell_centred
    ]
    return select_horizontal_slice(matches, z_m, quantity, "slice_node_vs_cell")


def load_fields(sim, *, cell_centred: bool, z_m: float) -> Fields:
    """The extinction, gas and temperature readers of the slices at *z_m*."""

    def pick(quantity: str):
        return _slice(sim, quantity, cell_centred=cell_centred, z_m=z_m)

    def sampler(quantity: str) -> SliceFieldSampler:
        return SliceFieldSampler(pick(quantity))

    gas = FdsFedField(*(sampler(q) for q in FED_QUANTITIES))
    smoke = SmokeSpeedModel(ExtinctionField(sampler(EXTINCTION)), SmokeSpeedConfig())
    plane = pick(TEMPERATURE)
    return Fields(smoke, gas, FdsHeatField(SliceFieldSampler(plane)), plane)


def read_fields(
    fields: Fields, times: np.ndarray, xs: np.ndarray, ys: np.ndarray
) -> dict[str, np.ndarray]:
    """K, speed factor, gas and heat FED rates and T at points, per time.

    *xs* and *ys* have one shape; the result arrays are ``(len(times), *shape)``
    with the quantities of :data:`UNITS` (T in degrees Celsius). Everything
    goes through pyFDS-Evac's own sampling and rate functions.
    """
    out = {name: np.empty((len(times), *xs.shape)) for name in (*UNITS, "T_c")}
    del out["T"]
    for ti, t in enumerate(times):
        for idx in np.ndindex(xs.shape):
            x, y = float(xs[idx]), float(ys[idx])
            k, factor = fields.smoke.sample(float(t), x, y)
            heat_in = fields.heat.sample_inputs(float(t), x, y)
            out["K"][ti][idx] = k
            out["speed_factor"][ti][idx] = factor
            out["fed_rate"][ti][idx] = default_fed_rate_per_minute(
                fields.gas.sample_inputs(float(t), x, y)
            )
            out["heat_rate"][ti][idx] = default_heat_fed_rate_per_minute(heat_in)
            out["T_c"][ti][idx] = heat_in.temperature_celsius
    return out


def difference_stats(
    node: np.ndarray, cell: np.ndarray, floor: float, mask: np.ndarray | None = None
) -> dict[str, float]:
    """Median, P95 and max of |node - cell| and of its ratio to |cell|.

    The relative figures use only samples where either reading exceeds
    *floor*, so a clean-air pair (0 against 0) does not dilute them; the
    denominator is the larger of |cell| and *floor*. *mask* restricts the
    samples (same shape as the arrays).
    """
    node = np.asarray(node, dtype=float)
    cell = np.asarray(cell, dtype=float)
    keep = np.ones(node.shape, dtype=bool) if mask is None else np.asarray(mask, bool)
    diff = np.abs(node - cell)[keep]
    active = (np.maximum(np.abs(node), np.abs(cell)) > floor)[keep]
    rel = (diff / np.maximum(np.abs(cell)[keep], max(floor, 1e-300)))[active]
    nan = float("nan")

    def three(values: np.ndarray) -> tuple[float, float, float]:
        if values.size == 0:
            return nan, nan, nan
        return (
            float(np.median(values)),
            float(np.percentile(values, 95)),
            float(values.max()),
        )

    abs_med, abs_p95, abs_max = three(diff)
    rel_med, rel_p95, rel_max = three(rel)
    return {
        "n": float(diff.size),
        "n_active": float(active.sum()),
        "abs_median": abs_med,
        "abs_p95": abs_p95,
        "abs_max": abs_max,
        "rel_median": rel_med,
        "rel_p95": rel_p95,
        "rel_max": rel_max,
    }


def interface_zone(
    t_low: np.ndarray,
    t_high: np.ndarray,
    *,
    step: float = ZONE_STEP,
    min_range_k: float = ZONE_MIN_RANGE_K,
) -> np.ndarray:
    """Cells within one cell of a sharp temperature step, per frame.

    *t_low* and *t_high* are the cell-centred temperatures of the two layers
    around the sampling plane, ``(frames, ny, nx)``. A cell is sharp when the
    largest step to an in-plane neighbour or between the layers is at least
    *step* of the frame's temperature range, and the range is at least
    *min_range_k*; the result is the sharp cells dilated by one cell
    (3 x 3).
    """
    mean = 0.5 * (t_low + t_high)
    sharp = np.abs(t_high - t_low)
    for axis in (1, 2):
        d = np.abs(np.diff(mean, axis=axis))
        pad = [(0, 0)] * 3
        lead, trail = list(pad), list(pad)
        lead[axis], trail[axis] = (0, 1), (1, 0)
        sharp = np.maximum(sharp, np.maximum(np.pad(d, lead), np.pad(d, trail)))
    span = mean.max(axis=(1, 2)) - mean.min(axis=(1, 2))
    flagged = (sharp >= step * span[:, None, None]) & (span >= min_range_k)[
        :, None, None
    ]
    padded = np.pad(flagged, ((0, 0), (1, 1), (1, 1)))
    zone = np.zeros_like(flagged)
    ny, nx = flagged.shape[1:]
    for dy in range(3):
        for dx in range(3):
            zone |= padded[:, dy : dy + ny, dx : dx + nx]
    return zone


def accumulated(rate: np.ndarray, times: np.ndarray) -> np.ndarray:
    """Dose [-] over the run from a per-frame rate [1/min] (frame held until the next)."""
    dt_s = np.diff(times, append=times[-1] + (times[-1] - times[-2]))
    return np.tensordot(dt_s / 60.0, rate, axes=(0, 0))


def cell_nodes(subslice) -> tuple[np.ndarray, np.ndarray]:
    """Mesh nodes in x and y inside one subslice's extent."""
    axes = []
    for dim in "xy":
        nodes = np.asarray(subslice.mesh.coordinates[dim], dtype=float)
        lo = getattr(subslice.extent, f"{dim}_start")
        hi = getattr(subslice.extent, f"{dim}_end")
        axes.append(nodes[(nodes >= lo - 1e-9) & (nodes <= hi + 1e-9)])
    return axes[0], axes[1]


def point_grid(
    x_nodes: np.ndarray, y_nodes: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """``(ny, nx, 5)`` x and y of the centre and quadrant points of every cell."""
    cx, cy = 0.5 * (x_nodes[:-1] + x_nodes[1:]), 0.5 * (y_nodes[:-1] + y_nodes[1:])
    wx, wy = np.diff(x_nodes), np.diff(y_nodes)
    xs = np.stack(
        [cx[None, :] + ox * wx[None, :] + 0 * cy[:, None] for ox, _ in OFFSETS], -1
    )
    ys = np.stack(
        [cy[:, None] + oy * wy[:, None] + 0 * cx[None, :] for _, oy in OFFSETS], -1
    )
    return xs, ys


def analyse(sim) -> dict:
    """Read both families of slices of *sim* and return the paired readings."""
    node = load_fields(sim, cell_centred=False, z_m=SAMPLING_HEIGHT_M)
    lower = load_fields(sim, cell_centred=True, z_m=SAMPLING_HEIGHT_M - 0.05)
    upper = load_fields(sim, cell_centred=True, z_m=SAMPLING_HEIGHT_M + 0.05)
    if len(node.plane.subslices) != 1:
        raise ValueError("the deck has one mesh; got a slice of several subslices")
    xs, ys = point_grid(*cell_nodes(node.plane.subslices[0]))
    times = np.asarray(node.plane.times, dtype=float)
    return {
        "times": times,
        "cx": xs[0, :, 0],
        "cy": ys[:, 0, 0],
        "node": read_fields(node, times, xs, ys),
        "lower": read_fields(lower, times, xs[..., 0], ys[..., 0]),
        "upper": read_fields(upper, times, xs[..., 0], ys[..., 0]),
    }


def _reference(result: dict, which: str) -> dict[str, np.ndarray]:
    """The cell reading, broadcast over the five points of each cell."""
    shape = result["node"]["K"].shape
    if which == "mean":
        a, b = result["lower"], result["upper"]
        cells = {k: 0.5 * (a[k] + b[k]) for k in a}
    else:
        cells = result[which]
    return {k: np.broadcast_to(v[..., None], shape) for k, v in cells.items()}


def report(result: dict, out=sys.stdout) -> None:
    """Print the difference tables and the accumulated doses."""
    zone = interface_zone(result["lower"]["T_c"], result["upper"]["T_c"])
    zone5 = np.broadcast_to(zone[..., None], result["node"]["K"].shape)
    centre = np.zeros(zone5.shape, bool)
    centre[..., 0] = True
    print(
        f"frames {len(result['times'])}, cells {zone.shape[1] * zone.shape[2]}, "
        f"zone share {zone.mean():.3f} of cell-frames",
        file=out,
    )
    for which in ("upper", "lower", "mean"):
        ref = _reference(result, which)
        for label, region in (("all", None), ("interface zone", zone5)):
            for sub, extra in (("quadrant points", ~centre), ("cell centre", centre)):
                keep = extra if region is None else extra & region
                print(f"\n== cell reference: {which}; {label}; {sub}", file=out)
                for name, floor in FLOORS.items():
                    s = difference_stats(result["node"][name], ref[name], floor, keep)
                    print(_row(name, s), file=out)
                s = difference_stats(result["node"]["T_c"], ref["T_c"], 0.0, keep)
                print(_row("T", s), file=out)
    print("\n== accumulated dose of stationary points in the interface zone", file=out)
    _report_doses(result, zone, out)


def _row(name: str, s: dict[str, float]) -> str:
    return (
        f"{name:>12} [{UNITS[name]}]  n={int(s['n'])}  abs med {s['abs_median']:.3g} "
        f"p95 {s['abs_p95']:.3g} max {s['abs_max']:.3g} | rel med {s['rel_median']:.3g} "
        f"p95 {s['rel_p95']:.3g} max {s['rel_max']:.3g}"
    )


def _report_doses(result: dict, zone: np.ndarray, out) -> None:
    times = result["times"]
    count = zone.sum(axis=0)
    chosen: list[tuple[int, int]] = []
    cx, cy = result["cx"], result["cy"]
    for flat in np.argsort(-count, axis=None, kind="stable"):
        j, i = np.unravel_index(flat, count.shape)
        if count[j, i] == 0 or len(chosen) == 5:
            break
        if all(np.hypot(cx[i] - cx[a], cy[j] - cy[b]) >= 1.0 for b, a in chosen):
            chosen.append((int(j), int(i)))
    for name in ("fed_rate", "heat_rate"):
        print(f"-- {name}: dose over the run", file=out)
        for j, i in chosen:
            node = accumulated(result["node"][name][:, j, i, :], times)
            cells = {
                w: float(accumulated(result[w][name][:, j, i], times))
                for w in ("lower", "upper")
            }
            print(
                f"({cx[i]:.1f}, {cy[j]:.1f}) zone frames {int(count[j, i])}: "
                f"node centre {node[0]:.4g}, node quadrant mean {node[1:].mean():.4g} "
                f"[{node[1:].min():.4g}..{node[1:].max():.4g}], "
                f"cell 1.65 {cells['upper']:.4g}, cell 1.55 {cells['lower']:.4g}",
                file=out,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=os.environ.get("SLICE_NODE_VS_CELL_DATA"),
        help="FDS output of slice_node_vs_cell.fds",
    )
    args = parser.parse_args(argv)
    if args.data is None:
        parser.error("give --data or set SLICE_NODE_VS_CELL_DATA")
    report(analyse(open_fds_case(Path(args.data))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
