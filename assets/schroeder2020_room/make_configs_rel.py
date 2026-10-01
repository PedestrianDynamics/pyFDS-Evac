"""Write pyFDS-Evac configs and geometry.wkt for the rel_* variants.

Geometry, exits and agents follow the authors' release,
doi:10.5281/zenodo.3875550 (1_RSET/*/corridor_geo.xml, corridor_ini.xml),
where CFSM in pyFDS-Evac allows it. Needs numpy and shapely, so run it
in the pyFDS-Evac environment, from the repository root:
``python assets/schroeder2020_room/make_configs_rel.py <outdir>``.

The exit cap (1.00 p/s, measured from the release trajectories) is not set
here: the study script applies it per run, as for the hrr060_* configs.
"""

import json
import pathlib
import sys

import numpy as np
from shapely import Polygon, wkt
from shapely.geometry.polygon import orient

OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(".")

# Burner 1 x 1 m at x, y = 1-2 m [R]. The release's JuPedSim geometry has
# no hole here; we keep agents off the fire.
BURNER = "(1 1, 2 1, 2 2, 1 2, 1 1)"
# Door D1 at x = 30, y = 8-9 m [R]. Door reveals (evac only, not in FDS):
# 0.8 m deep jambs, so agents must enter the 1.0 m passage before they
# leave. They were added when removal was within radius + 0.5 m of a
# point in the exit polygon (issue #349) and kept by decision.
GEOMETRY_1D = (
    "POLYGON ((0 0, 30 0, 30 7.2, 29.2 7.2, 29.2 8, 30 8, 30 9, "
    "29.2 9, 29.2 10, 0 10, 0 0), " + BURNER + ")"
)
# D2 at x = 0, y = 8-9 m: D1 mirrored about x = 15 [A], jambs mirrored.
GEOMETRY_2D = (
    "POLYGON ((0 0, 30 0, 30 7.2, 29.2 7.2, 29.2 8, 30 8, 30 9, "
    "29.2 9, 29.2 10, 0.8 10, 0.8 9, 0 9, 0 8, 0.8 8, 0.8 7.2, "
    "0 7.2, 0 0), " + BURNER + ")"
)

EXITS = {
    "E1_east": {
        "coords": [[29.8, 8], [30, 8], [30, 9], [29.8, 9], [29.8, 8]],
        "sign": {"x": 29.9, "y": 8.5, "alpha": 270, "c": 3},
    },
    "E2_west": {
        "coords": [[0, 8], [0.2, 8], [0.2, 9], [0, 9], [0, 8]],
        "sign": {"x": 0.1, "y": 8.5, "alpha": 90, "c": 3},
    },
}

# Spawn over [0.3, 29.7] x [0.3, 9.7] (the release lattice spans
# x 0.3-29.7, y 0.37-9.62), with the south-west corner up to (2.2, 2.2)
# cut out: the burner (1-2 m) plus 0.2 m. Each area is clipped to the
# walkable area, which removes the jamb notches.
ROOM = [[2.2, 0.3], [29.7, 0.3], [29.7, 9.7], [0.3, 9.7], [0.3, 2.2], [2.2, 2.2]]
# Two-door variant: split at x = 15, the shortest-path boundary between the
# mirrored doors.
WEST = [[2.2, 0.3], [15.0, 0.3], [15.0, 9.7], [0.3, 9.7], [0.3, 2.2], [2.2, 2.2]]
EAST = [[15.0, 0.3], [29.7, 0.3], [29.7, 9.7], [15.0, 9.7]]


def clipped(poly: list, geometry: str) -> list:
    """Spawn polygon clipped to the walkable area, as a closed coordinate list."""
    part = orient(Polygon(poly).intersection(wkt.loads(geometry)))
    assert part.geom_type == "Polygon" and not part.interiors, part.wkt
    assert part.within(wkt.loads(geometry))
    return [[round(x, 6), round(y, 6)] for x, y in part.exterior.coords]


ROOM_1D = clipped(ROOM, GEOMETRY_1D)
WEST_2D = clipped(WEST, GEOMETRY_2D)
EAST_2D = clipped(EAST, GEOMETRY_2D)


PREMOVEMENT = {
    # The paper's and the release's case: movement starts at t = 0.
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
        # v0 = N(1.3, 0.1) m/s as in the release's corridor_ini.xml [R]; the
        # paper text gives 1.2 m/s.
        "v0": 1.3,
        "use_flow_spawning": False,
        "distribution_mode": "by_number",
        "percentage": None,
        **PREMOVEMENT[pre],
        "radius_distribution": "constant",
        "v0_distribution": "gaussian",
        "v0_std": 0.1,
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


ONE_DOOR = (["E1_east"], {"jps-distributions_0": (ROOM_1D, 100)})
TWO_DOOR = ["E1_east", "E2_west"]

for name in ("rel_1door", "rel_1door_dx010"):
    # config.json is the release's case (pre0); run.py picks it for a directory.
    write(name, "config.json", config(*ONE_DOOR, "pre0"), GEOMETRY_1D)
    for pre in PREMOVEMENT:
        write(name, f"config_{pre}.json", config(*ONE_DOOR, pre), GEOMETRY_1D)

# Two doors: for every seed, draw the west count from Binomial(N, A_W / (A_W
# + A_E)) with that seed, A_W and A_E being the clipped spawn areas. Run each
# file with the same --seed.
SEEDS = range(1, 11)
SHARE = Polygon(WEST_2D).area / (Polygon(WEST_2D).area + Polygon(EAST_2D).area)


def binomial_split(n: int, seed: int) -> tuple[int, int]:
    n_west = int(np.random.default_rng(seed).binomial(n, SHARE))
    return n_west, n - n_west


def two_door(n: int, seed: int, pre: str) -> dict:
    n_w, n_e = binomial_split(n, seed)
    spawns = {
        "jps-distributions_0": (WEST_2D, n_w),
        "jps-distributions_1": (EAST_2D, n_e),
    }
    cfg = config(TWO_DOOR, spawns, pre)
    cfg["config"]["simulation_settings"]["baseSeed"] = seed
    return cfg


for seed in SEEDS:
    for pre in PREMOVEMENT:
        write(
            "rel_2door/seeds",
            f"config_{pre}_seed{seed:02d}.json",
            two_door(100, seed, pre),
            GEOMETRY_2D,
        )
    write(
        "rel_2door/seeds",
        f"config_N200_seed{seed:02d}.json",
        two_door(200, seed, "pre0"),
        GEOMETRY_2D,
    )
print(f"west share A_W / (A_W + A_E) = {SHARE:.5f}")
