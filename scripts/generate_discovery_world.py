#!/usr/bin/env python3
"""Generate one random discoverability-test world (geometry.wkt + config.json + zip).

The world is a rectangular walkable area with a few convex obstacle holes,
2-4 exits flush against the boundary walls, and 2-4 circular checkpoint
"stages" carrying signs. The spawn area is placed as far from the exits as
possible so agents must explore to discover them. Output layout matches
cognitive_map_test.zip: a zip with geometry.wkt and config.json at its root.

Usage:
    .venv/bin/python scripts/generate_discovery_world.py --seed 42 --out worlds/

Decks run directly with ``scripts/animate_cognitive_map.py --scenario worlds/world_42``
and drive the generated-world invariant tests in ``tests/test_generated_worlds.py``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import zipfile
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

WALL_MARGIN = 2.5  # obstacle keep-out from walls, keeps corridors walkable (m)
CLEARANCE = 1.2  # minimum gap between any two placed shapes (m)
EXIT_DEPTH = 0.8  # how far an exit rectangle reaches into the room (m)
CHECKPOINT_RADIUS = 0.5

# Defaults copied verbatim from the cognitive_map_test.zip reference project.
SIMULATION_PARAMS = {
    "max_simulation_time": 600,
    "dt": 0.05,
    "model_type": "WarpDriverModel",
    "strength_neighbor_repulsion": 2.6,
    "range_neighbor_repulsion": 0.1,
    "gcfm_strength_neighbor_repulsion": 0.3,
    "gcfm_strength_geometry_repulsion": 0.2,
    "gcfm_max_neighbor_interaction_distance": 2,
    "gcfm_max_geometry_interaction_distance": 2,
    "gcfm_max_neighbor_repulsion_force": 9,
    "gcfm_max_geometry_repulsion_force": 3,
    "mass": 80,
    "tau": 0.5,
    "a_v": 1,
    "a_min": 0.2,
    "b_min": 0.2,
    "b_max": 0.4,
    "relaxation_time": 0.5,
    "agent_strength": 2000,
    "agent_range": 0.08,
    "sfm_obstacle_scale": 2000,
    "sfm_body_force": 120000,
    "sfm_friction": 240000,
    "T": 1,
    "s0": 0.5,
}


def ring(poly: Polygon) -> list[list[float]]:
    """Closed [[x, y], ...] ring (shapely exteriors repeat the first point)."""
    return [[float(x), float(y)] for x, y in poly.exterior.coords]


def make_room(rng: np.random.Generator, scale: float = 1.0) -> Polygon:
    half_w = scale * rng.uniform(12.0, 20.0)
    half_h = scale * rng.uniform(9.0, 15.0)
    return box(-half_w, -half_h, half_w, half_h)


def random_obstacle(rng: np.random.Generator, allowed: Polygon) -> Polygon | None:
    minx, miny, maxx, maxy = allowed.bounds
    for _ in range(300):
        cx = rng.uniform(minx, maxx)
        cy = rng.uniform(miny, maxy)
        if not allowed.contains(Point(cx, cy)):
            continue
        radius = rng.uniform(1.2, 3.0)
        n_pts = int(rng.integers(4, 8))
        angles = np.sort(rng.uniform(0.0, 2.0 * math.pi, n_pts))
        radii = radius * rng.uniform(0.6, 1.0, n_pts)
        pts = [
            (cx + r * math.cos(a), cy + r * math.sin(a)) for a, r in zip(angles, radii)
        ]
        poly = Polygon(pts).convex_hull
        if not isinstance(poly, Polygon) or poly.area < 1.5:
            continue
        if allowed.contains(poly):
            return poly
    return None


def place_obstacles(rng: np.random.Generator, room: Polygon, n: int) -> list[Polygon]:
    # Extra inset guarantees holes never touch the boundary, so the walkable
    # area stays connected and every exit remains discoverable.
    allowed = room.buffer(-WALL_MARGIN)
    obstacles: list[Polygon] = []
    for _ in range(n * 40):
        if len(obstacles) == n:
            break
        cand = random_obstacle(rng, allowed)
        if cand is None:
            continue
        if all(cand.distance(o) >= CLEARANCE for o in obstacles):
            obstacles.append(cand)
    return obstacles


def place_exits(rng: np.random.Generator, room: Polygon, n: int) -> list[Polygon]:
    minx, miny, maxx, maxy = room.bounds
    exits = []
    for edge in rng.choice(["N", "S", "E", "W"], size=min(n, 4), replace=False):
        width = rng.uniform(1.2, 2.5)
        if edge in ("N", "S"):
            x0 = rng.uniform(minx + 2.0, maxx - 2.0 - width)
            y0 = maxy - EXIT_DEPTH if edge == "N" else miny
            exits.append(box(x0, y0, x0 + width, y0 + EXIT_DEPTH))
        else:
            y0 = rng.uniform(miny + 2.0, maxy - 2.0 - width)
            x0 = maxx - EXIT_DEPTH if edge == "E" else minx
            exits.append(box(x0, y0, x0 + EXIT_DEPTH, y0 + width))
    return exits


def sample_clear_shape(
    rng: np.random.Generator,
    room: Polygon,
    placed: list[Polygon],
    make_shape,
    margin: float = 1.0,
) -> Polygon | None:
    minx, miny, maxx, maxy = room.bounds
    for _ in range(500):
        cx = rng.uniform(minx + margin, maxx - margin)
        cy = rng.uniform(miny + margin, maxy - margin)
        shape = make_shape(cx, cy)
        if not room.contains(shape):
            continue
        if all(shape.distance(p) >= CLEARANCE for p in placed):
            return shape
    return None


def exits_hidden_from(
    spawn: Polygon, exits: list[Polygon], obstacles: list[Polygon]
) -> bool:
    """True when every sightline from the spawn centre to every exit is blocked."""
    if not obstacles:
        return False
    blockers = unary_union(obstacles)
    origin = spawn.centroid
    for e in exits:
        targets = list(e.exterior.coords[:-1]) + [(e.centroid.x, e.centroid.y)]
        if any(not LineString([origin, t]).intersects(blockers) for t in targets):
            return False
    return True


def place_spawn(
    rng: np.random.Generator,
    room: Polygon,
    placed: list[Polygon],
    exits: list[Polygon],
    obstacles: list[Polygon],
    hide_exits: bool,
) -> Polygon:
    def make(cx: float, cy: float) -> Polygon:
        return box(cx - 1.5, cy - 1.25, cx + 1.5, cy + 1.25)

    candidates = []
    for _ in range(120):
        cand = sample_clear_shape(rng, room, placed, make, margin=2.5)
        if cand is not None:
            candidates.append(cand)
    if hide_exits:
        candidates = [c for c in candidates if exits_hidden_from(c, exits, obstacles)]
        if not candidates:
            raise RuntimeError("no spawn spot with all exits hidden; try another seed")
    if not candidates:
        raise RuntimeError("could not place a spawn area; try another seed")
    return max(candidates, key=lambda c: min(c.distance(e) for e in exits))


def sign_alpha_toward(sign_x: float, sign_y: float, focus: Point) -> float:
    """Compass bearing (deg from north, CW) from the sign toward *focus*.

    fdsvismap reads alpha as the centre of the sign's readable half-plane,
    so a sign aimed at the space its readers walk in is legible from there.
    Random orientations regularly leave a world unsolvable for discovery
    agents: every sign reachable from the spawn side can face away, and a
    blind agent then patrols its known legs forever without learning more.
    """
    return math.degrees(math.atan2(focus.x - sign_x, focus.y - sign_y)) % 360


def checkpoint_entry(
    rng: np.random.Generator, circle: Polygon, center: Point, focus: Point | None
) -> dict:
    sign_x = center.x + rng.uniform(-0.1, 0.1)
    sign_y = center.y + rng.uniform(-0.1, 0.1)
    alpha = (
        float(rng.uniform(0.0, 360.0))
        if focus is None
        else sign_alpha_toward(sign_x, sign_y, focus)
    )
    return {
        "type": "polygon",
        "coordinates": ring(circle),
        "waiting_time": 0,
        "waiting_time_distribution": "constant",
        "waiting_time_std": 1,
        "enable_throughput_throttling": False,
        "max_throughput": 1,
        "speed_factor": 1,
        "shape": "circle",
        "center": [center.x, center.y],
        "radius": CHECKPOINT_RADIUS,
        "sign": {
            "x": sign_x,
            "y": sign_y,
            "alpha": alpha,
            "c": 3,
        },
    }


def build_config(
    rng: np.random.Generator,
    seed: int,
    n_agents: int,
    exits: list[Polygon],
    spawn: Polygon,
    checkpoints: list[Polygon],
    n_obstacles: int,
    random_sign_alpha: bool = False,
) -> dict:
    exit_entries = {
        f"jps-exits_{i}": {
            "type": "polygon",
            "coordinates": ring(e),
            "enable_throughput_throttling": False,
            "max_throughput": 0,
        }
        for i, e in enumerate(exits)
    }
    distribution = {
        "type": "polygon",
        "coordinates": ring(spawn),
        "parameters": {
            "number": n_agents,
            "radius": 0.1,
            "v0": 1.3,
            "flow_start_time": 0,
            "flow_end_time": 10,
            "percentage": None,
            "distribution_mode": "by_number",
            "use_flow_spawning": False,
            "use_premovement": False,
            "premovement_distribution": "gamma",
            "premovement_param_a": None,
            "premovement_param_b": None,
            "premovement_seed": None,
            "radius_distribution": "constant",
            "v0_distribution": "constant",
        },
        "journey_weights": [],
    }
    # Aim each checkpoint sign at the spawn area: agents encounter every
    # sign travelling outward from the spawn, and a sign is read by the
    # people approaching it -- the same convention real escape-route
    # signage follows. (Aiming at the room interior instead leaves the
    # signs nearest the spawn facing away from it, and the discovery
    # chain never starts.) Exits stay hidden by geometry until approached.
    focus = None if random_sign_alpha else spawn.centroid
    checkpoint_entries = {
        f"jps-checkpoints_{i}": checkpoint_entry(rng, c, c.centroid, focus)
        for i, c in enumerate(checkpoints)
    }
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": dict(SIMULATION_PARAMS),
                "numberOfSimulations": 1,
                "baseSeed": seed,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        "exits": exit_entries,
        "distributions": {"jps-distributions_0": distribution},
        "checkpoints": checkpoint_entries,
        "zones": {},
        "journeys": [],
        "transitions": [],
        "obstacles": {f"jps-obstacles_{i}": {"height": 3} for i in range(n_obstacles)},
        "journeys_v2": [],
    }


def generate_world(seed: int, args: argparse.Namespace) -> tuple[Polygon, dict]:
    rng = np.random.default_rng(seed)
    room = make_room(rng, args.room_scale)

    n_obstacles = args.obstacles or int(rng.integers(3, 6))
    n_exits = args.exits or int(rng.integers(2, 5))
    n_stages = args.stages or int(rng.integers(2, 5))

    obstacles = place_obstacles(rng, room, n_obstacles)
    exits = place_exits(rng, room, n_exits)

    placed = obstacles + exits
    checkpoints: list[Polygon] = []
    for _ in range(n_stages):
        circle = sample_clear_shape(
            rng,
            room,
            placed,
            lambda cx, cy: Point(cx, cy).buffer(CHECKPOINT_RADIUS, quad_segs=8),
        )
        if circle is None:
            break
        checkpoints.append(circle)
        placed.append(circle)

    spawn = place_spawn(rng, room, placed, exits, obstacles, args.hide_exits)

    walkable = Polygon(room.exterior.coords, [o.exterior.coords for o in obstacles])
    if not walkable.is_valid:
        raise RuntimeError("generated geometry is invalid; try another seed")

    config = build_config(
        rng,
        seed,
        args.agents,
        exits,
        spawn,
        checkpoints,
        len(obstacles),
        random_sign_alpha=args.random_sign_alpha,
    )
    return walkable, config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--seed", type=int, default=None, help="RNG seed (random if omitted)"
    )
    parser.add_argument(
        "--out", type=Path, default=Path("worlds"), help="output directory"
    )
    parser.add_argument(
        "--agents", type=int, default=10, help="agents in the spawn area"
    )
    parser.add_argument(
        "--obstacles", type=int, default=None, help="fix obstacle count (3-5 random)"
    )
    parser.add_argument(
        "--exits", type=int, default=None, help="fix exit count (2-4 random)"
    )
    parser.add_argument(
        "--stages", type=int, default=None, help="fix stage count (2-4 random)"
    )
    parser.add_argument(
        "--room-scale",
        type=float,
        default=1.0,
        help="multiply the room half-extents (use >1 to fit many obstacles/stages)",
    )
    parser.add_argument(
        "--hide-exits",
        action="store_true",
        help="require obstacles to block every sightline from the spawn to the exits",
    )
    parser.add_argument(
        "--random-sign-alpha",
        action="store_true",
        help="orient checkpoint signs randomly instead of toward the interior "
        "(random orientations can leave a world unsolvable for discovery agents)",
    )
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else int.from_bytes(os.urandom(4), "big")
    walkable, config = generate_world(seed, args)

    world_dir = args.out / f"world_{seed}"
    world_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "geometry.wkt").write_text(walkable.wkt)
    (world_dir / "config.json").write_text(json.dumps(config, indent=2))

    zip_path = args.out / f"world_{seed}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(world_dir / "geometry.wkt", "geometry.wkt")
        zf.write(world_dir / "config.json", "config.json")

    print(f"seed        {seed}")
    print(f"obstacles   {len(walkable.interiors)}")
    print(f"exits       {len(config['exits'])}")
    print(f"stages      {len(config['checkpoints'])}")
    print(f"wrote       {zip_path}")


if __name__ == "__main__":
    main()
