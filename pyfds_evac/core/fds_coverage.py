"""Setup check of the scenario geometry against the FDS slice coverage.

Outside the FDS slices pyFDS-Evac reads ambient air and clear sight, as
FDS+Evac does. That is a modelling assumption, so it is checked once at setup
and reported: which part of the walkable area, which exits, checkpoints and
spawn areas, which signs and which route edges lie outside. With
``--require-fds-coverage`` anything outside is an error.

A point is covered when every sampled FDS quantity covers it. A quantity
covers the union of its subslice rectangles, closed on every side, the same
rule ``SliceFieldSampler`` samples by. A hole between subslices therefore
counts as outside.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .fds_sampling import FdsDomainError, SliceFieldSampler
from .visibility import _sign_positions, extract_sign_descriptors

_logger = logging.getLogger(__name__)

# Areas and lengths below this are floating-point noise of the polygon
# arithmetic, not geometry outside the domain.
_AREA_EPS_M2 = 1e-9
_LENGTH_EPS_M = 1e-9

# Scenario sections whose polygons are reported by name.
_AREA_SECTIONS = ("exits", "checkpoints", "distributions")


@dataclass
class FdsCoverageReport:
    """What lies outside the FDS slice coverage, in m² and m."""

    quantities: list[str]
    walkable_area_m2: float = 0.0
    walkable_outside_m2: float = 0.0
    areas_outside_m2: dict[str, float] = field(default_factory=dict)
    signs_outside: list[str] = field(default_factory=list)
    signs_off_vismap_grid: dict[str, float] = field(default_factory=dict)
    edges_outside_m: dict[str, float] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True when nothing lies outside the coverage."""
        return not (
            self.walkable_outside_m2 > _AREA_EPS_M2
            or self.areas_outside_m2
            or self.signs_outside
            or self.signs_off_vismap_grid
            or self.edges_outside_m
        )

    def summary(self) -> str:
        """Return a one-paragraph description for the log and the error."""
        if self.is_empty:
            return (
                "FDS coverage: the walkable area, exits, checkpoints, spawn "
                "areas, signs and route edges all lie inside the FDS slices "
                f"({', '.join(self.quantities)})."
            )
        share = (
            100.0 * self.walkable_outside_m2 / self.walkable_area_m2
            if self.walkable_area_m2 > 0
            else 0.0
        )
        parts = [
            f"walkable area {self.walkable_outside_m2:.2f} m² ({share:.1f} %)",
        ]
        parts += [f"{n} {a:.2f} m²" for n, a in self.areas_outside_m2.items()]
        parts += [f"sign {n}" for n in self.signs_outside]
        parts += [
            f"sign {n} {d:.2f} m off the vismap grid"
            for n, d in self.signs_off_vismap_grid.items()
        ]
        parts += [f"edge {n} {m:.2f} m" for n, m in self.edges_outside_m.items()]
        return (
            "FDS coverage: outside the FDS slices "
            f"({', '.join(self.quantities)}), agents read ambient air and "
            "clear sight: " + "; ".join(parts) + "."
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the report as JSON-ready data for the run manifest."""
        return {
            "quantities": list(self.quantities),
            "walkable_area_m2": self.walkable_area_m2,
            "walkable_outside_m2": self.walkable_outside_m2,
            "areas_outside_m2": dict(self.areas_outside_m2),
            "signs_outside": list(self.signs_outside),
            "signs_off_vismap_grid_m": dict(self.signs_off_vismap_grid),
            "edges_outside_m": dict(self.edges_outside_m),
        }


def domain_fields(*models: Any) -> list[Any]:
    """Return the FDS-backed fields of smoke, FED and heat models.

    A field counts when it reads at least one FDS slice; a constant
    extinction, a model that is None, or a field over stand-in samplers that
    carry no slice extents (synthetic test fields) contributes none.
    """
    fields = []
    for model in models:
        for name in ("field", "layer_field"):
            fds_field = getattr(model, name, None)
            reader = getattr(fds_field, "samplers", None)
            samplers = reader() if reader is not None else []
            if samplers and all(hasattr(s, "extents") for s in samplers):
                fields.append(fds_field)
    return fields


def model_samplers(*models: Any) -> list[SliceFieldSampler]:
    """Return the FDS slice samplers behind smoke, FED and heat models."""
    return [s for f in domain_fields(*models) for s in f.samplers()]


def in_fds_domain(fields: list[Any], x: float, y: float) -> bool:
    """Return whether every field in *fields* covers the x/y point."""
    return all(f.covers(x, y) for f in fields)


def coverage_polygon(samplers: list[SliceFieldSampler]):
    """Return the area every sampler covers, or None without samplers."""
    covered = None
    for sampler in samplers:
        boxes = [box(x0, y0, x1, y1) for x0, x1, y0, y1 in sampler.extents()]
        area = unary_union(boxes)
        covered = area if covered is None else covered.intersection(area)
    return covered


def _outside_areas(raw: dict, domain) -> dict[str, float]:
    """Return {section/id: m²} of every named polygon reaching outside."""
    outside: dict[str, float] = {}
    for section in _AREA_SECTIONS:
        for name, data in (raw.get(section) or {}).items():
            coords = data.get("coordinates") if isinstance(data, dict) else None
            if not coords or len(coords) < 3:
                continue
            area = Polygon(coords).difference(domain).area
            if area > _AREA_EPS_M2:
                outside[f"{section[:-1]} {name}"] = float(area)
    return outside


def _outside_edges(stage_graph, domain) -> dict[str, float]:
    """Return {"source -> target": m} of every route edge leaving the domain."""
    outside: dict[str, float] = {}
    if stage_graph is None:
        return outside
    for edges in stage_graph.edges.values():
        for edge in edges:
            if len(edge.waypoints) < 2:
                continue
            length = LineString(edge.waypoints).difference(domain).length
            if length > _LENGTH_EPS_M:
                outside[f"{edge.source} -> {edge.target}"] = float(length)
    return outside


def check_fds_coverage(
    *,
    walkable,
    raw: dict,
    samplers: list[SliceFieldSampler],
    stage_graph=None,
    vis_model=None,
) -> FdsCoverageReport | None:
    """Compare the scenario geometry with the FDS slice coverage.

    Returns None when no FDS slice is sampled. Signs are the exit,
    checkpoint and waypoint signs of the scenario, authored or synthesised,
    as the sign-visibility model reads them; with that model they are also
    checked against its grid.
    """
    domain = coverage_polygon(samplers)
    if domain is None:
        return None
    report = FdsCoverageReport(
        quantities=sorted({s.quantity for s in samplers}),
        walkable_area_m2=float(walkable.area),
        walkable_outside_m2=float(walkable.difference(domain).area),
        areas_outside_m2=_outside_areas(raw, domain),
        edges_outside_m=_outside_edges(stage_graph, domain),
    )
    signs = getattr(vis_model, "_sign_xy", None)
    if signs is None:
        signs = _sign_positions(extract_sign_descriptors(raw))
    report.signs_outside = [
        name for name, xy in signs.items() if not domain.covers(Point(xy))
    ]
    if vis_model is not None:
        report.signs_off_vismap_grid = vis_model.signs_outside_grid()
    return report


def apply_coverage_policy(
    report: FdsCoverageReport | None, *, require_fds_coverage: bool
) -> None:
    """Log the report; raise ``FdsDomainError`` in strict mode if not empty."""
    if report is None:
        return
    if report.is_empty:
        _logger.info(report.summary())
        return
    if require_fds_coverage:
        raise FdsDomainError(
            report.summary() + " Extend the FDS meshes or slices over these "
            "objects, or run without --require-fds-coverage."
        )
    _logger.warning(report.summary())


def count_outside(rows: list[dict[str, Any]], interval_s: float) -> dict[str, Any]:
    """Count history rows flagged outside the FDS domain.

    Returns the number of rows, the agents they belong to, and agent-seconds,
    each row standing for one sampling interval.
    """
    outside = [r for r in rows if r.get("in_fds_domain") is False]
    return {
        "rows": len(outside),
        "agents": len({int(r["agent_id"]) for r in outside}),
        "agent_seconds": len(outside) * float(interval_s),
    }
