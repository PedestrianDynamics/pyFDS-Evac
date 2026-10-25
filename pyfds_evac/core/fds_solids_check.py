"""``init --check-solids``: the walkable area against FDS's solid cells (#715).

Compares the walkable area ``init`` derived with the cells a finished FDS run
of the deck treats as solid at walking height. A plan cell (i, j) is solid in
FDS when any cell of its column that meets the floor's z band is blocked; it
disagrees when that differs from "its centre is outside the walkable area".
Only cells whose centre lies inside the exterior ring of a kept part are
compared (holes count as inside), so rooms ``init`` dropped are not compared.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon
from shapely.ops import unary_union

from pyfds_evac.core.fds_import import ImportResult
from pyfds_evac.core.fds_import_geometry import polygons_of
from pyfds_evac.core.fdsreader_adapter import open_fds_simulation

#: Mesh-matching tolerance [m]; fdsreader keeps node coordinates in float32,
#: so the relative float32 rounding is added.
_XB_TOL_M = 1e-6
_FLOAT32_REL = 1.2e-7
_BOUNDS_DIGITS = 6
_MIN_REGION_CELLS = 2

_REGION_MESSAGE = (
    "--check-solids: the walkable area and FDS's solid cells disagree in a "
    "region; see import_report.json walkable.check_solids"
)


def check_solids(sim_dir: str | Path, result: ImportResult) -> dict[str, Any]:
    """Compare the walkable area with the run in *sim_dir*; report the findings.

    Adds report items to ``result.report``, stores the summary under
    ``result.report.walkable["check_solids"]`` and returns it.
    """
    simulation, problem = _open(sim_dir)
    if simulation is None:
        return _failed(sim_dir, problem, result)
    walkable = shapely_wkt.loads(result.walkable_wkt)
    outer = _outer_rings(walkable)
    z_lo, z_hi = result.report.floor["z_band"]
    fds_meshes = list(simulation.meshes)
    compared = disagreeing = 0
    regions: list[list[float]] = []
    unmatched: list[str] = []
    for record in result.floor_meshes:
        mesh = _match(record, fds_meshes)
        if mesh is None:
            unmatched.append(record.label)
            result.report.add(
                "A",
                "warning",
                "walkable",
                "--check-solids: a floor mesh has no match in the FDS run",
                record,
            )
            continue
        cells = _compare(mesh, (z_lo, z_hi), outer, walkable)
        compared += cells.compared
        disagreeing += int(cells.disagree.sum())
        regions += _regions(cells.disagree, mesh)
    regions.sort(key=lambda r: (r[0], r[2]))
    return _summary(sim_dir, result, (compared, disagreeing), regions, unmatched)


class _Cells:
    """The compared cells of one mesh and the ones that disagree."""

    def __init__(self, compared: int, disagree: np.ndarray) -> None:
        self.compared = compared
        self.disagree = disagree


def _open(sim_dir: str | Path) -> tuple[Any, str]:
    if not any(Path(sim_dir).glob("*.smv")):
        return None, f"no .smv file in {sim_dir}"
    try:
        return open_fds_simulation(sim_dir), ""
    except Exception as exc:  # fdsreader raises whatever its parsers raise
        return None, str(exc)


def _failed(sim_dir, problem: str, result: ImportResult) -> dict[str, Any]:
    result.report.add(
        "D", "error", "walkable", f"--check-solids: no readable FDS run in {sim_dir}"
    )
    summary = {"sim_dir": str(sim_dir), "error": problem}
    result.report.walkable["check_solids"] = summary
    return summary


def _outer_rings(walkable) -> Polygon:
    """The kept parts with their holes filled."""
    return unary_union([Polygon(p.exterior) for p in polygons_of(walkable)])


def _match(record, fds_meshes):
    """The FDS mesh whose extremes equal the record's XB, or None."""
    xb = record.xb()
    for mesh in fds_meshes:
        if _same_box(_extremes(mesh), xb):
            return mesh
    return None


def _extremes(mesh) -> tuple[float, ...]:
    coordinates = mesh.coordinates
    out: list[float] = []
    for axis in ("x", "y", "z"):
        nodes = coordinates[axis]
        out += [float(nodes[0]), float(nodes[-1])]
    return tuple(out)


def _same_box(a, b) -> bool:
    return all(abs(u - v) <= _XB_TOL_M + _FLOAT32_REL * abs(v) for u, v in zip(a, b))


def _compare(mesh, band, outer, walkable) -> _Cells:
    x = np.asarray(mesh.coordinates["x"], dtype=float)
    y = np.asarray(mesh.coordinates["y"], dtype=float)
    z = np.asarray(mesh.coordinates["z"], dtype=float)
    mask = mesh.get_obstruction_mask([0.0], cell_centered=True)[0]
    in_band = (z[1:] > band[0]) & (z[:-1] < band[1])
    solid = (~mask[:, :, in_band]).any(axis=2)
    cx, cy = (x[1:] + x[:-1]) / 2, (y[1:] + y[:-1]) / 2
    px, py = np.meshgrid(cx, cy, indexing="ij")
    inside = shapely.contains_xy(outer, px, py)
    free = shapely.contains_xy(walkable, px, py)
    return _Cells(int(inside.sum()), inside & (free == solid))


def _regions(disagree: np.ndarray, mesh) -> list[list[float]]:
    """Bounds of every 4-connected group of at least two disagreeing cells."""
    x = np.asarray(mesh.coordinates["x"], dtype=float)
    y = np.asarray(mesh.coordinates["y"], dtype=float)
    seen = np.zeros(disagree.shape, dtype=bool)
    found = []
    for start in zip(*np.nonzero(disagree)):
        if seen[start]:
            continue
        cells = _flood(disagree, seen, (int(start[0]), int(start[1])))
        if len(cells) < _MIN_REGION_CELLS:
            continue
        found.append(_bounds(cells, x, y))
    return found


def _flood(disagree, seen, start) -> list[tuple[int, int]]:
    cells, stack = [], [start]
    seen[start] = True
    while stack:
        i, j = stack.pop()
        cells.append((i, j))
        for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if _open_cell(disagree, seen, n):
                seen[n] = True
                stack.append(n)
    return cells


def _open_cell(disagree, seen, cell) -> bool:
    i, j = cell
    if not (0 <= i < disagree.shape[0] and 0 <= j < disagree.shape[1]):
        return False
    return bool(disagree[cell]) and not seen[cell]


def _bounds(cells, x, y) -> list[float]:
    ii = [c[0] for c in cells]
    jj = [c[1] for c in cells]
    bounds = (x[min(ii)], x[max(ii) + 1], y[min(jj)], y[max(jj) + 1])
    return [round(float(v), _BOUNDS_DIGITS) for v in bounds]


def _summary(sim_dir, result, counts, regions, unmatched) -> dict[str, Any]:
    compared, disagreeing = counts
    summary = {
        "sim_dir": str(sim_dir),
        "cells_compared": compared,
        "cells_disagreeing": disagreeing,
        "regions": regions,
        "meshes_unmatched": unmatched,
    }
    for n, _ in enumerate(regions):
        result.report.add(
            "A", "warning", "walkable", _REGION_MESSAGE, id=f"check_solids_{n}"
        )
    result.report.add(
        "S",
        "info",
        "walkable",
        f"--check-solids: {disagreeing} of {compared} cells disagree",
        id="check_solids",
    )
    result.report.walkable["check_solids"] = summary
    return summary
