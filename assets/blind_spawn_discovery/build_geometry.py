#!/usr/bin/env python3
"""Generate the blind-spawn discovery scenario.

Every other discovery asset in this repository is one convex room whose builder
*asserts* that an exit is legible from the spawn area, so an agent always has a
default target.  This one removes that: both exits are behind walls, so a
discovery agent spawns knowing **no exit at all** and has to explore to find
one.

Hidden by geometry, not by distance or bearing
    Both exits sit 24.7 m from the spawn centroid, inside the 30 m visibility
    ceiling, and both signs are omni-directional (``alpha`` omitted, which
    fdsvismap reads as "readable from any bearing").  Distance and bearing are
    therefore ruled out as explanations, and the only remaining term in the
    legibility rule is the one nothing else in the repository tests:

        view_angle * visibility * non_concealed >= distance

    ``non_concealed`` is fdsvismap's line-of-sight mask.  ``build()`` asserts
    both halves of this -- exits inside the ceiling, exits occluded -- because
    an asset that hid them by distance instead would look identical from the
    outside and would test nothing new.

Layout (walls 0.4 m thick; doorways are the gaps in them):

    y = 30  +---------------+---------------+
            |   west room   |   east room   |
            |   [E_west]    |   [E_east]    |
    y = 22  +-----[C2]------+------[C3]-----+
            |           corridor            |
    y = 18  +------------[C1]---------------+
            |                               |
            |          spawn hall           |
    y =  0  +-------------------------------+
           x=0                            x=24

The exits are symmetric, so neither wins on distance and the split is decided
by which doorway each agent explores first -- and by nothing else.

Expected sequence for a discovery agent, and the reason each hop happens:

    hop 0   map = {spawn, C1}         no exit ranked -> explore to C1
    hop 1   map += C2, C3             expand_on_arrival reveals neighbours
    hop 2   map += the exit behind    the doorway it chose

Whether hop 1 also reveals the exits is a genuine open question about
``expand_on_arrival``, which ignores visibility entirely.  The tests are written
to record which happens rather than to assume three hops.
"""

from pathlib import Path
import json
import math

from shapely.geometry import box
from shapely.ops import unary_union

HERE = Path(__file__).parent

# fdsvismap's ceiling: in clear air no sign is legible beyond this, at any
# bearing, because view_angle cannot exceed 1.  See the pitfall section of
# assets/exit_visibility_alpha/README.md.
MAX_VIS_M = 30.0

WALL = 0.4

HALL = (0.0, 0.0, 24.0, 17.8)
CORRIDOR = (0.0, 18.2, 24.0, 21.8)
WEST_ROOM = (0.0, 22.2, 11.8, 30.0)
EAST_ROOM = (12.2, 22.2, 24.0, 30.0)

# Doorways: the gaps left in the walls.
DOOR1 = (11.0, 17.8, 13.0, 18.2)  # hall -> corridor
DOOR2 = (5.0, 21.8, 7.0, 22.2)  # corridor -> west room
DOOR3 = (17.0, 21.8, 19.0, 22.2)  # corridor -> east room

# The checkpoint stages, centred on those doorways but 2 m deep rather than
# 0.4 m. Direct steering picks a random point inside the stage polygon and walks
# the agent to it; a box only as deep as the wall gives thirty agents the same
# sliver to aim at and they jam in it. A box spanning the doorway on both sides
# gives them room to resolve. Same failure as the Station's 1.5 m checkpoints.
C1 = (11.0, 17.0, 13.0, 19.0)
C2 = (5.0, 21.0, 7.0, 23.0)
C3 = (17.0, 21.0, 19.0, 23.0)

E_WEST = (5.0, 28.5, 7.0, 29.5)
E_EAST = (17.0, 28.5, 19.0, 29.5)

SPAWN = (2.0, 2.0, 22.0, 8.0)

AGENT_RADIUS = 0.2
N_AGENTS = 30
V0 = 1.3

# The four configs. Each changes exactly one thing against config_discovery.
VARIANTS = {
    "discovery": {"familiarity": "discovery", "entrance": None},
    "full": {"familiarity": "full", "entrance": None},
    "entrance": {"familiarity": "discovery", "entrance": "E_west"},
    "mixed": {"familiarity": 0.5, "entrance": None},
}


def walkable_area():
    """Rooms plus the doorways that join them; the walls are the gaps left."""
    return unary_union(
        [
            box(*HALL),
            box(*DOOR1),
            box(*CORRIDOR),
            box(*DOOR2),
            box(*DOOR3),
            box(*WEST_ROOM),
            box(*EAST_ROOM),
        ]
    )


def _centroid(bounds):
    x0, y0, x1, y1 = bounds
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def line_of_sight_clear(a, b, walkable) -> bool:
    """Whether the straight segment a->b stays inside the walkable area.

    This is the same question fdsvismap's ``non_concealed`` mask answers by ray
    casting on the FDS grid.  Reimplemented here on the polygon so the builder
    can refuse to write an asset whose premise is broken, without needing an
    FDS run first.
    """
    from shapely.geometry import LineString

    return walkable.covers(LineString([a, b]))


def _sign(bounds):
    """An omni-directional sign at the stage centroid.

    ``alpha`` is deliberately omitted: fdsvismap reads a missing bearing as
    readable from every direction, which removes orientation as an explanation
    for anything this scenario shows.
    """
    x, y = _centroid(bounds)
    return {"x": round(x, 3), "y": round(y, 3), "c": 3}


def build_config(variant: str) -> dict:
    settings = VARIANTS[variant]
    parameters = {
        "number": N_AGENTS,
        "radius": AGENT_RADIUS,
        "v0": V0,
        "distribution_mode": "by_number",
        "use_flow_spawning": False,
        "use_premovement": False,
        "radius_distribution": "constant",
        "v0_distribution": "constant",
        "familiarity": settings["familiarity"],
    }
    if settings["entrance"] is not None:
        parameters["entrance"] = settings["entrance"]

    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 300,
                    "dt": 0.05,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": 1301,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        # Hazard weights at zero: this scenario is about what agents know, not
        # about what the smoke costs. The air is clear anyway.
        "routing": {
            "w_smoke": 0.0,
            "w_fed": 0.0,
            "w_queue": 0.0,
            "base_speed_m_per_s": V0,
            "default_exit_capacity": 1.3,
            "sampling_step_m": 2.0,
        },
        "exits": {
            "E_west": {
                "type": "polygon",
                "coordinates": _coords(E_WEST),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
                "sign": _sign(E_WEST),
            },
            "E_east": {
                "type": "polygon",
                "coordinates": _coords(E_EAST),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
                "sign": _sign(E_EAST),
            },
        },
        "checkpoints": {
            "C1": {"type": "polygon", "coordinates": _coords(C1)},
            "C2": {"type": "polygon", "coordinates": _coords(C2)},
            "C3": {"type": "polygon", "coordinates": _coords(C3)},
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": parameters,
            }
        },
        "zones": {},
        # No journeys and no transitions: the graph auto-wires and cost decides,
        # which is what puts betweenness pruning on the critical path.
        "journeys": [],
        "transitions": [],
        "obstacles": {},
    }


def build_fds_deck(walkable_wkt: str) -> str:
    """Clear-air deck: the generator's fire stripped, its slices kept.

    fdsvismap needs an extinction slice to answer any legibility query, so
    ``--geometry-only`` will not do -- it drops the slices along with the
    burner.  The internal walls come through as ``&OBST`` records, which is what
    gives fdsvismap something to occlude with.
    """
    from pyfds_evac.core.wkt_to_fds import wkt_to_fds

    fire = ("SURF_ID='BURNER'", "&SURF ID='BURNER'", "&RAMP ID='qramp'")
    kept = [
        line
        for line in wkt_to_fds(walkable_wkt, chid="blind_spawn_discovery").splitlines()
        if not any(marker in line for marker in fire)
    ]
    return "\n".join(kept) + "\n"


def _check_premises(walkable):
    """Refuse to write an asset whose premise has silently broken."""
    spawn = _centroid(SPAWN)

    for name, bounds in (("E_west", E_WEST), ("E_east", E_EAST)):
        target = _centroid(bounds)
        distance = math.hypot(target[0] - spawn[0], target[1] - spawn[1])
        if distance >= MAX_VIS_M:
            raise SystemExit(
                f"{name} is {distance:.1f} m from the spawn centroid, at or beyond "
                f"the {MAX_VIS_M:.0f} m visibility ceiling. It would be illegible "
                "for the trivial reason of being too far away, and the occlusion "
                "this scenario exists to test would carry none of the result."
            )
        if line_of_sight_clear(spawn, target, walkable):
            raise SystemExit(
                f"{name} is in direct line of sight from the spawn area, so a "
                "discovery agent would know an exit at t=0 and never explore."
            )

    if not line_of_sight_clear(spawn, _centroid(C1), walkable):
        raise SystemExit(
            "C1 is occluded from the spawn area too, so the agent's map would be "
            "{spawn} alone, there would be no frontier to head for, and agents "
            "would stand still rather than explore."
        )

    for name, bounds in (("C2", C2), ("C3", C3)):
        if line_of_sight_clear(spawn, _centroid(bounds), walkable):
            raise SystemExit(
                f"{name} is visible from the spawn area, collapsing the three-hop "
                "discovery this scenario is built to exercise."
            )

    west = math.dist(spawn, _centroid(E_WEST))
    east = math.dist(spawn, _centroid(E_EAST))
    if abs(west - east) > 1e-6:
        raise SystemExit(
            f"the exits are not symmetric ({west:.2f} m vs {east:.2f} m), so the "
            "split between them could be explained by distance."
        )

    capacity = box(*SPAWN).area / (2 * AGENT_RADIUS) ** 2
    if N_AGENTS > 0.9 * capacity:
        raise SystemExit(
            f"{N_AGENTS} agents exceeds the ~{capacity:.0f} the spawn area holds"
        )

    for name, bounds in (("C1", C1), ("C2", C2), ("C3", C3)):
        if not walkable.covers(box(*bounds)):
            raise SystemExit(
                f"{name} is not wholly inside the walkable area, so direct "
                "steering could pick a target point inside a wall"
            )
        depth = bounds[3] - bounds[1]
        if depth < 1.5:
            raise SystemExit(
                f"{name} is only {depth:.1f} m deep; agents jam aiming for the "
                "same sliver. Give the checkpoint room on both sides of the door."
            )


def build():
    walkable = walkable_area()
    _check_premises(walkable)

    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")

    deck = build_fds_deck(walkable.wkt)
    if "BURNER" in deck:
        raise SystemExit("fire was not stripped from the generated deck")
    if "QUANTITY='EXTINCTION COEFFICIENT'" not in deck:
        raise SystemExit("deck has no extinction slice; fdsvismap would have no data")
    (HERE / "blind_spawn_discovery.fds").write_text(deck, encoding="utf-8")

    for variant in VARIANTS:
        path = HERE / f"config_{variant}.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(build_config(variant), handle, indent=2)

    spawn = _centroid(SPAWN)
    print("Wrote geometry.wkt, blind_spawn_discovery.fds and 4 configs")
    print(f"  spawn centroid {spawn}, {N_AGENTS} agents")
    for name, bounds in (("C1", C1), ("C2", C2), ("C3", C3), ("E_west", E_WEST)):
        target = _centroid(bounds)
        seen = line_of_sight_clear(spawn, target, walkable)
        print(
            f"  {name:7s} at {target}  d={math.dist(spawn, target):5.1f} m  "
            f"line of sight from spawn: {'clear' if seen else 'blocked'}"
        )
    return walkable


if __name__ == "__main__":
    build()
