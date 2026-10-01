"""Write pyFDS-Evac config.json and geometry.wkt for the Schroeder 2020 room.

The two-door per-seed configs (E1) need numpy and shapely, so run this in
the pyFDS-Evac environment, from the repository root:
``python assets/schroeder2020_room/make_configs.py <outdir>``.
"""

import json
import pathlib
import sys

OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(".")

BURNER = "(0.6 0.6, 1.2 0.6, 1.2 1.2, 0.6 1.2, 0.6 0.6)"
# Door reveals (evac only, not in FDS): 0.8 m deep jambs at each door, so
# agents must enter the 1.2 m passage before they leave. They were added
# when removal was within radius + 0.5 m of a point in the exit polygon
# (issue #349).
GEOMETRY_1D = (
    "POLYGON ((0 0, 30 0, 30 7.4, 29.2 7.4, 29.2 8.2, 30 8.2, 30 9.4, "
    "29.2 9.4, 29.2 10, 0 10, 0 0), " + BURNER + ")"
)
GEOMETRY_2D = (
    "POLYGON ((0 0, 30 0, 30 7.4, 29.2 7.4, 29.2 8.2, 30 8.2, 30 9.4, "
    "29.2 9.4, 29.2 10, 0.8 10, 0.8 9.4, 0 9.4, 0 8.2, 0.8 8.2, 0.8 7.4, "
    "0 7.4, 0 0), " + BURNER + ")"
)

EXITS = {
    "E1_east": {
        "coords": [[29.8, 8.2], [30, 8.2], [30, 9.4], [29.8, 9.4], [29.8, 8.2]],
        "sign": {"x": 29.9, "y": 8.8, "alpha": 270, "c": 3},
    },
    "E2_west": {
        "coords": [[0, 8.2], [0.2, 8.2], [0.2, 9.4], [0, 9.4], [0, 8.2]],
        "sign": {"x": 0.1, "y": 8.8, "alpha": 90, "c": 3},
    },
}

# Whole floor 0.3 m off the walls, with the south-west corner up to
# (1.4, 1.4) cut out: the burner (0.6-1.2 m) plus at least 0.2 m.
ROOM = [
    [1.4, 0.3],
    [29.7, 0.3],
    [29.7, 9.7],
    [0.3, 9.7],
    [0.3, 1.4],
    [1.4, 1.4],
    [1.4, 0.3],
]
# Two-door variant: split at x = 15, the shortest-path boundary between the
# mirrored doors (see README).
WEST = [
    [1.4, 0.3],
    [15.0, 0.3],
    [15.0, 9.7],
    [0.3, 9.7],
    [0.3, 1.4],
    [1.4, 1.4],
    [1.4, 0.3],
]
EAST = [[15.0, 0.3], [29.7, 0.3], [29.7, 9.7], [15.0, 9.7], [15.0, 0.3]]


PREMOVEMENT = {
    # The paper's case: movement starts at t = 0 (pre-proof p. 5).
    "pre0": {"use_premovement": False},
    "pre30": {
        "use_premovement": True,
        "premovement_distribution": "constant",
        "premovement_param_a": 30.0,
    },
    "pre60": {
        "use_premovement": True,
        "premovement_distribution": "constant",
        "premovement_param_a": 60.0,
    },
    # No pre-movement key at all: pyFDS-Evac applies its default, the FDS+Evac
    # PRE_MEAN of a constant 10 s, and logs a warning.
    "pre_default": {},
}


def params(number: int, pre: str = "pre0") -> dict:
    return {
        "number": number,
        "radius": 0.15,
        "v0": 1.2,
        "use_flow_spawning": False,
        "distribution_mode": "by_number",
        "percentage": None,
        **PREMOVEMENT[pre],
        "radius_distribution": "constant",
        "v0_distribution": "constant",
        "familiarity": "full",
    }


def config(
    exit_ids: list[str], spawns: dict[str, tuple[list, int]], pre: str = "pre0"
) -> dict:
    exits = {
        e: {
            "type": "polygon",
            "coordinates": EXITS[e]["coords"],
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            "sign": EXITS[e]["sign"],
        }
        for e in exit_ids
    }
    dists = {
        d: {"type": "polygon", "coordinates": poly, "parameters": params(n, pre)}
        for d, (poly, n) in spawns.items()
    }
    transitions = [
        {"from": d, "to": e, "journey_id": "journey_0"}
        for d in spawns
        for e in exit_ids
    ]
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 600,  # = FDS T_END
                    "model_type": "CollisionFreeSpeedModel",
                    "strength_neighbor_repulsion": 2.6,
                    "range_neighbor_repulsion": 0.1,
                    "a_v": 1,
                    "a_min": 0.2,
                    "b_min": 0.2,
                    "b_max": 0.4,
                    "T": 1,
                },
                "numberOfSimulations": 1,
                "baseSeed": 42,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "routing": {
            "w_smoke": 5.0,
            "w_fed": 10.0,
            "w_queue": 0.0,
            "fed_rejection_threshold": 1.0,
            "visibility_extinction_threshold": 0.5,
            "sampling_step_m": 2.0,
            "base_speed_m_per_s": 1.3,
            "default_exit_capacity": 1.3,
        },
        "exits": exits,
        "distributions": dists,
        "checkpoints": {},
        "zones": {},
        "journeys": [
            {
                "id": "journey_0",
                "stages": list(spawns) + exit_ids,
                "transitions": transitions,
            }
        ],
        "transitions": transitions,
        "waypoint_routing": {},
    }


def write(name: str, fname: str, cfg: dict, geometry: str) -> None:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(json.dumps(cfg, indent=2) + "\n")
    (d / "geometry.wkt").write_text(geometry + "\n")
    print(d / fname)


ONE_DOOR = (["E1_east"], {"jps-distributions_0": (ROOM, 100)})
TWO_DOOR = (
    ["E1_east", "E2_west"],
    {"jps-distributions_0": (WEST, 50), "jps-distributions_1": (EAST, 50)},
)
TWO_DOOR_N200 = (
    ["E1_east", "E2_west"],
    {"jps-distributions_0": (WEST, 100), "jps-distributions_1": (EAST, 100)},
)

for name, layout, geometry in (
    ("hrr060_1door", ONE_DOOR, GEOMETRY_1D),
    ("hrr060_1door_dx010", ONE_DOOR, GEOMETRY_1D),
    ("hrr060_2door", TWO_DOOR, GEOMETRY_2D),
):
    # config.json is the paper's case (pre0); run.py picks it for a directory.
    write(name, "config.json", config(*layout, "pre0"), geometry)
    for pre in PREMOVEMENT:
        write(name, f"config_{pre}.json", config(*layout, pre), geometry)
write("hrr060_2door", "config_N200.json", config(*TWO_DOOR_N200, "pre0"), GEOMETRY_2D)

# E1 (Enrico's deck check): the fixed 50/50 split above removes the binomial
# door-load variance of a uniform placement over the whole floor. For every
# seed, draw the west count from Binomial(N, A_W / (A_W + A_E)) with that
# seed; A_W and A_E are the spawn areas clipped to the walkable area. Run
# each file with the same --seed. The files above stay as they were.
SEEDS = range(1, 11)


def split_share() -> float:
    from shapely import Polygon, wkt

    walkable = wkt.loads(GEOMETRY_2D)
    a_w = Polygon(WEST).intersection(walkable).area
    a_e = Polygon(EAST).intersection(walkable).area
    return a_w / (a_w + a_e)


def binomial_split(n: int, seed: int, share: float) -> tuple[int, int]:
    import numpy as np

    n_west = int(np.random.default_rng(seed).binomial(n, share))
    return n_west, n - n_west


SHARE = split_share()
for seed in SEEDS:
    for pre in PREMOVEMENT:
        n_w, n_e = binomial_split(100, seed, SHARE)
        layout = (
            TWO_DOOR[0],
            {"jps-distributions_0": (WEST, n_w), "jps-distributions_1": (EAST, n_e)},
        )
        cfg = config(*layout, pre)
        cfg["config"]["simulation_settings"]["baseSeed"] = seed
        write(
            "hrr060_2door/seeds", f"config_{pre}_seed{seed:02d}.json", cfg, GEOMETRY_2D
        )
    n_w, n_e = binomial_split(200, seed, SHARE)
    layout = (
        TWO_DOOR[0],
        {"jps-distributions_0": (WEST, n_w), "jps-distributions_1": (EAST, n_e)},
    )
    cfg = config(*layout, "pre0")
    cfg["config"]["simulation_settings"]["baseSeed"] = seed
    write("hrr060_2door/seeds", f"config_N200_seed{seed:02d}.json", cfg, GEOMETRY_2D)
print(f"west share A_W / (A_W + A_E) = {SHARE:.5f}")
