"""Setup warning for an exit an agent centre cannot reach (#975).

A model with a wall clearance holds an agent's centre at least ``r + c`` from
a wall segment, where *r* is the radius and *c* the clearance. An agent
heading straight at the wall stops there. The run counts an exit as reached
when the centre is within ``EXIT_REACH_TOLERANCE_M`` of its polygon, so an
exit that lies flush with a wall and is shallower than ``r + c`` minus that
tolerance is not reached head-on.

The check is a necessary condition for the single agent heading straight at
the wall, not a guarantee: crowds can strand agents when it is silent, and an
agent arriving at an angle can slide in when it fires. It is a warning.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shapely.geometry import Polygon

from .agent_params import max_agent_radius, parameters_as_dict
from .direct_steering_runtime import EXIT_REACH_TOLERANCE_M
from .simulation_init import AVM_WALL_BUFFER_M

# JuPedSim 1.4.2 ``range_geometry_repulsion`` default of CollisionFreeSpeedModel
# and CollisionFreeSpeedModelV2: measured stop gap r + 0.02 m (#975).
RANGE_GEOMETRY_REPULSION_M = 0.02

_CLEARANCE_MODELS = ("CollisionFreeSpeedModel", "CollisionFreeSpeedModelV2")
_AVM = "AnticipationVelocityModel"


def wall_clearance(model_type: str) -> float:
    """The clearance *c* [m] the model keeps beyond the radius; 0 if unmeasured."""
    if model_type == _AVM:
        return AVM_WALL_BUFFER_M
    if model_type in _CLEARANCE_MODELS:
        return RANGE_GEOMETRY_REPULSION_M
    return 0.0


def _largest_radius(distributions: Mapping[str, Any]) -> float | None:
    """The largest spawn radius over the distributions, None without any."""
    radii = []
    for dist in distributions.values():
        params = parameters_as_dict(dist.get("parameters") if dist else None)
        if params is not None:
            radii.append(max_agent_radius(params))
    return max(radii) if radii else None


def _exit_polygon(data: Any) -> Polygon | None:
    coordinates = data.get("coordinates") if isinstance(data, Mapping) else None
    try:
        polygon = Polygon(coordinates)
    except (TypeError, ValueError):
        return None
    return None if polygon.is_empty or not polygon.is_valid else polygon


def exit_reach_warning(
    model_type: str,
    walkable: Any,
    raw: Mapping[str, Any],
    clearance: float | None = None,
) -> str | None:
    """The warning for exits the agent centres cannot reach, or None.

    An exit is flagged when the region the centres can occupy, the walkable
    area eroded by ``r_max + c``, is farther from it than
    ``EXIT_REACH_TOLERANCE_M``. *r_max* is the largest spawn radius. *clearance*
    replaces the model's wall clearance (a deck that sets another one).
    """
    radius = _largest_radius(raw.get("distributions") or {})
    if radius is None or walkable is None:
        return None
    if clearance is None:
        clearance = wall_clearance(model_type)
    reach = walkable.buffer(-(radius + clearance))
    if reach.is_empty:
        return None
    flagged = []
    for name, data in (raw.get("exits") or {}).items():
        polygon = _exit_polygon(data)
        if polygon is not None and reach.distance(polygon) > EXIT_REACH_TOLERANCE_M:
            flagged.append(f"{name} ({reach.distance(polygon):.3f} m)")
    if not flagged:
        return None
    return (
        f"{model_type}: agent centres stay {radius + clearance:g} m "
        f"(radius {radius:g} + clearance {clearance:g}) from walls and may not "
        f"come within {EXIT_REACH_TOLERANCE_M:g} m of exit "
        f"{', '.join(flagged)}; agents heading straight at it can stop short "
        "(#975). Deepen the exit, reduce the radius or the wall clearance."
    )
