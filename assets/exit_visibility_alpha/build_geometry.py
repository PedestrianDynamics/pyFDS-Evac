#!/usr/bin/env python3
"""Generate the exit-visibility-vs-alpha scenario.

A single-variable experiment: the only thing that differs between the two
configs is the viewing bearing of one exit sign.  Everything else -- geometry,
agents, weights, the other exit -- is identical, so any difference in exit
choice is attributable to sign orientation alone.

Layout (a straight north-south corridor, 4 m wide):

    y = 44  +--------+   E_far   (always legible, alpha = 180)
            |        |
            |        |
    y = 12  |  spawn |   200 agents, 8 m from E_near, 32 m from E_far
    y =  8  |        |
    y =  0  +--------+   E_near  (alpha is the experiment's variable)

Agents stand north of E_near, so with fdsvismap's bearing convention
(degrees clockwise from north, readable in the half-plane the sign faces):

* ``alpha = 0``   -- E_near faces north, toward the agents: legible.
  Every agent takes E_near, the geometrically obvious choice.
* ``alpha = 180`` -- E_near faces south, away from the agents: illegible.
  The route is rejected with ``next_node_not_visible`` and every agent walks
  the extra 24 m to E_far instead.

The flip is the whole point.  Distance still favours E_near in both runs, so a
model that ignored sign orientation would send agents to E_near either way.

Familiarity stays ``full`` deliberately.  Sign-visibility rejection lives in
``rank_routes`` and is independent of the cognitive map, so this isolates the
visibility channel without involving discovery.

The air is clear: the FDS deck carries no fire, so legibility is limited by
viewing angle and distance only, never by smoke.  That keeps alpha the single
independent variable.
"""

from pathlib import Path
import json

from shapely.geometry import box

HERE = Path(__file__).parent

CORRIDOR = (0.0, 0.0, 4.0, 44.0)  # x_min, y_min, x_max, y_max
SPAWN = (0.5, 8.0, 3.5, 12.0)

# Exit polygons sit inside the walkable area: JuPedSim rejects an exit stage
# that falls outside it.
E_NEAR = (0.5, 0.2, 3.5, 1.2)  # south end, 8 m from the spawn area
E_FAR = (0.5, 42.8, 3.5, 43.8)  # north end, 32 m from the spawn area

N_AGENTS = 200

# fdsvismap reads alpha as a compass bearing (degrees clockwise from north)
# and makes the sign legible in the half-plane it faces, with cosine falloff.
ALPHA_VISIBLE = 0  # E_near faces north, toward the agents
ALPHA_HIDDEN = 180  # E_near faces south, away from them
ALPHA_FAR = 180  # E_far faces south, toward the agents: always legible


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def _exit(bounds, sign_x, sign_y, alpha):
    return {
        "type": "polygon",
        "coordinates": _coords(bounds),
        "enable_throughput_throttling": False,
        "max_throughput": 0,
        "sign": {"x": sign_x, "y": sign_y, "alpha": alpha, "c": 3},
    }


def build_config(alpha_near):
    """Scenario config with E_near's sign at the given bearing.

    No journeys and no transitions: the graph auto-wires every spawn area to
    every exit and the composite cost decides, which is the mode this
    experiment is about.
    """
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
                "baseSeed": 1904,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        # Clear air, no congestion term: distance is the only cost pressure, so
        # E_near wins on cost in both runs and only legibility can change the
        # outcome.
        "routing": {
            "w_smoke": 0.0,
            "w_fed": 0.0,
            "w_queue": 0.0,
            "base_speed_m_per_s": 1.3,
            "default_exit_capacity": 1.3,
            "sampling_step_m": 2.0,
        },
        "exits": {
            "E_near": _exit(E_NEAR, 2.0, 0.7, alpha_near),
            "E_far": _exit(E_FAR, 2.0, 43.3, ALPHA_FAR),
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": {
                    "number": N_AGENTS,
                    "radius": 0.2,
                    "v0": 1.3,
                    "distribution_mode": "by_number",
                    "use_flow_spawning": False,
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    "familiarity": "full",
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
        "obstacles": {},
    }


def build_fds_deck(walkable_wkt: str) -> str:
    """A clear-air deck: the generator's fire removed, its slices kept.

    fdsvismap needs a SOOT EXTINCTION COEFFICIENT slice to answer any
    legibility query, so ``--geometry-only`` is not enough -- it drops the
    slices along with the burner.  Generate the full deck instead and strip
    only the heat source, leaving a run whose extinction field is zero
    everywhere.  Legibility is then decided by viewing angle and distance
    alone, which is what makes alpha the single independent variable.
    """
    from pyfds_evac.core.wkt_to_fds import wkt_to_fds

    fire_markers = ("SURF_ID='BURNER'", "&SURF ID='BURNER'", "&RAMP ID='qramp'")
    kept = [
        line
        for line in wkt_to_fds(walkable_wkt, chid="exit_visibility_alpha").splitlines()
        if not any(marker in line for marker in fire_markers)
    ]
    return "\n".join(kept) + "\n"


def build():
    walkable = box(*CORRIDOR)
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")

    deck = build_fds_deck(walkable.wkt)
    (HERE / "exit_visibility_alpha.fds").write_text(deck, encoding="utf-8")
    if "BURNER" in deck:
        raise SystemExit("fire was not stripped from the generated deck")
    if "SOOT EXTINCTION COEFFICIENT" not in deck:
        raise SystemExit("deck has no soot slice; fdsvismap would have no data")
    print(f"Wrote: {HERE / 'exit_visibility_alpha.fds'}  (clear air, slices kept)")

    for name, alpha in (("visible", ALPHA_VISIBLE), ("hidden", ALPHA_HIDDEN)):
        path = HERE / f"config_{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(build_config(alpha), f, indent=2)
        print(f"Wrote: {path}  (E_near alpha={alpha})")

    print(f"Wrote: {HERE / 'geometry.wkt'}")
    print(f"Corridor {walkable.bounds}, area {walkable.area:.1f} m2")
    print("E_near is 8 m from the spawn area, E_far is 32 m away")
    return walkable


if __name__ == "__main__":
    build()
