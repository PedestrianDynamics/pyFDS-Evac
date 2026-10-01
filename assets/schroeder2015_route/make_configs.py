"""Write the pyFDS-Evac configs and geometry.wkt for the route-choice case.

Usage (pyFDS-Evac venv, needs shapely):
``.venv/bin/python make_configs.py <outdir>``, writes ``<outdir>/evac/``.

One config per cost model (#305: set explicitly). The four arms of the plan
(section 4) are run options on these files:

- no fire:       config_gate.json, no --fds-dir
- smoke-blind:   config_gate.json --fds-dir <run> --smoke-blind
- gate:          config_gate.json --fds-dir <run>
- additive:      config_additive.json --fds-dir <run>

Seeds 1..10 via --seed. Published inputs [P] (Schroeder et al. 2015): N =
200 in Room 1, t_pre ~ N(120, 60) s, v0 ~ N(1.0, 0.2) m/s. pyFDS-Evac has
no normal pre-movement distribution; the closest supported one is used
(see PREMOVEMENT). Everything else is [A].
"""

import json
import pathlib
import sys

from geometry import door_checkpoint, exit_polygon, spawn_area, walkable

OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(".")

# t_pre ~ N(120, 60) s [P] is not supported (gamma, lognormal, weibull,
# uniform, constant only). Weibull with the same mean and standard deviation
# (scale a = 135.49 s, shape b = 2.101) is the closest of the supported
# families to N(120, 60) truncated at 0 (KS 0.056, W1 6.1 s; gamma(4, 30):
# 0.079, 9.1 s; lognormal: 0.105, 12.6 s; uniform(16.1, 223.9): 0.076,
# 9.4 s). Non-negative, so no truncation is needed. Both parameters must be
# set, or the engine falls back to its preset.
PREMOVEMENT = {
    "use_premovement": True,
    "premovement_distribution": "weibull",
    "premovement_param_a": 135.49,
    "premovement_param_b": 2.101,
    "premovement_seed": None,
}

# Evac horizon 400 s against FDS T_END 480 s: an 80 s margin for anticipated
# arrival times with foresight_horizon_s = inf (#356). The flow ends at about
# 300 s in the source (2015 Fig. 7).
MAX_TIME = 400
V0 = 1.0


def exits() -> dict:
    out = {}
    for name, alpha in (("E", 180), ("F", 0)):
        poly = exit_polygon(name)
        out[f"exit_{name}"] = {
            "type": "polygon",
            "coordinates": poly,
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            "sign": {"x": -2.6, "y": poly[0][1] + 0.1, "alpha": alpha, "c": 3},
        }
    return out


def checkpoints() -> dict:
    out = {}
    for name in ("A", "B"):
        poly = door_checkpoint(name)
        out[f"jps-checkpoints_door{name}"] = {
            "type": "polygon",
            "coordinates": poly,
            "sign": {
                "x": 0.1,
                "y": (poly[0][1] + poly[2][1]) / 2,
                "alpha": 270,
                "c": 3,
            },
            "waiting_time": 0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 1,
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            "speed_factor": 1,
        }
    return out


def distribution() -> dict:
    return {
        "jps-distributions_0": {
            "type": "polygon",
            "coordinates": spawn_area(),
            "parameters": {
                "number": 200,
                "radius": 0.15,
                "v0": V0,
                "use_flow_spawning": False,
                "distribution_mode": "by_number",
                "percentage": None,
                **PREMOVEMENT,
                "radius_distribution": "constant",
                "v0_distribution": "gaussian",
                "v0_std": 0.2,
                "familiarity": "full",
            },
        }
    }


DIST = "jps-distributions_0"
DOORS = ["jps-checkpoints_doorA", "jps-checkpoints_doorB"]
EXITS = ["exit_E", "exit_F"]
TRANSITIONS = [{"from": DIST, "to": d, "journey_id": "journey_0"} for d in DOORS] + [
    {"from": d, "to": e, "journey_id": "journey_0"} for d in DOORS for e in EXITS
]
# The engine requires an explicit split at every checkpoint with two
# outgoing edges. The percentages only seed the journey variants; the route
# ranking at spawn and on reroute picks each agent's path.
WAYPOINT_ROUTING = {
    d: {"journey_0": {"destinations": [{"target": e, "percentage": 50} for e in EXITS]}}
    for d in DOORS
}


def config(cost_model: str) -> dict:
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": MAX_TIME,
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
                "baseSeed": 1,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "routing": {
            "cost_model": cost_model,
            # foresight_horizon_s is left at the engine default (inf): the
            # default model is what the study tests; the 80 s T_END margin
            # covers #356.
            "anticipate": True,
            "base_speed_m_per_s": V0,
            # Written out although it is the engine default: the additive arm
            # depends on it entirely (as cost_model, #305).
            "w_smoke": 1.0,
        },
        "exits": exits(),
        "distributions": distribution(),
        "checkpoints": checkpoints(),
        "zones": {},
        "journeys": [
            {
                "id": "journey_0",
                "stages": [DIST, *DOORS, *EXITS],
                "transitions": TRANSITIONS,
            }
        ],
        "transitions": TRANSITIONS,
        "waypoint_routing": WAYPOINT_ROUTING,
    }


def main() -> None:
    d = OUT / "evac"
    d.mkdir(parents=True, exist_ok=True)
    (d / "geometry.wkt").write_text(walkable().wkt + "\n")
    for cm in ("gate", "additive"):
        cfg = config(cm)
        (d / f"config_{cm}.json").write_text(json.dumps(cfg, indent=2) + "\n")
        print(d / f"config_{cm}.json")


if __name__ == "__main__":
    main()
