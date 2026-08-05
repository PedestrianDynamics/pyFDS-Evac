#!/usr/bin/env python3
"""Generate the cognitive-map acquisition-and-persistence scenario.

A discovery agent walks a straight corridor past a side exit whose sign is
legible only from a window of positions.  The scenario asks two questions that
a pure visibility query cannot tell apart:

1. **Acquisition** -- does the side exit enter the agent's cognitive map when
   its sign first becomes legible?
2. **Persistence** -- does it *stay* in the map after the agent walks on and
   the sign becomes illegible again?

The second is the one that matters.  A cognitive map differs from a visibility
query in exactly one respect: it remembers.  Delete the expansion rules and
question 1 still passes on any agent that starts within the window; only
question 2 catches it.

Layout (a 4 m wide corridor running north):

    y = 32  +--------+   E_end  (legible from the spawn area, alpha = 180)
            |        |
    y = 27.5|········|   <- upper edge of the legibility window
            |        |
    y = 20  |       [E_side]     east wall, sign faces west
            |        |
    y = 12.5|········|   <- lower edge of the window
            |        |
    y =  4  |  spawn |   agents start here, knowing only E_end
    y =  0  +--------+

Why the window exists
    fdsvismap decides legibility as ``view_angle * visibility >= distance``.
    For a sign facing west at (4, 20), an agent on the centreline x=2 has
    ``view_angle = 2 / d``, so the test becomes ``2/d * 30 >= d``, i.e.
    ``d <= sqrt(60)``.  With ``d^2 = 4 + (y-20)^2`` that is |y - 20| <= 7.48.
    Off-axis geometry kills the view angle faster than proximity helps, which
    is what produces a band rather than a half-plane.

    The window is therefore a *derived* quantity, not a tuned one.  The builder
    recomputes and asserts it, so a change to the corridor width or the sign
    position cannot silently move it.

The agent starts at y ~ 4, below the window, so E_side is unknown at t=0 while
E_end already is known -- the corridor is 32 m rather than longer precisely so
E_end sits inside the 30 m ceiling and the agent has a default target.  E_side
becomes known around y = 12.5 and must remain known at y = 30, well after it
stops being readable.

Familiarity is ``discovery``; at ``full`` the map holds everything from t=0 and
there is nothing to acquire.
"""

from pathlib import Path
import json
import math

from shapely.geometry import box

HERE = Path(__file__).parent

MAX_VIS_M = 30.0  # fdsvismap's clear-air ceiling
CORRIDOR = (0.0, 0.0, 4.0, 32.0)
SPAWN = (0.5, 2.0, 3.5, 6.0)
CENTRELINE_X = 2.0

# E_end closes the north end and is legible from the whole corridor.
E_END = (0.5, 30.8, 3.5, 31.8)
E_END_SIGN = (2.0, 31.3, 180)  # faces south, toward the agents

# E_side is an alcove in the east wall; its sign faces west into the corridor.
E_SIDE = (4.0, 19.0, 5.0, 21.0)
E_SIDE_SIGN = (4.0, 20.0, 270)  # faces west

AGENT_RADIUS = 0.2
N_AGENTS = 20


def legibility_window(sign_x, sign_y, alpha_deg, max_vis=MAX_VIS_M):
    """The y-range along the centreline where this sign is legible.

    Solves ``view_angle * max_vis >= distance`` for an observer at
    ``(CENTRELINE_X, y)``, with ``view_angle`` the clipped cosine of the angle
    between the sign's facing direction and the direction to the observer.
    """
    fx = math.sin(math.radians(alpha_deg))
    fy = math.cos(math.radians(alpha_deg))
    ys = [y / 100.0 for y in range(0, int(CORRIDOR[3] * 100))]
    legible = []
    for y in ys:
        dx, dy = CENTRELINE_X - sign_x, y - sign_y
        d = math.hypot(dx, dy)
        if d == 0:
            continue
        view_angle = max(0.0, min(1.0, (fx * dx + fy * dy) / d))
        if view_angle * max_vis >= d:
            legible.append(y)
    if not legible:
        return None
    return float(min(legible)), float(max(legible))


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def _exit(bounds, sign):
    x, y, alpha = sign
    return {
        "type": "polygon",
        "coordinates": _coords(bounds),
        "enable_throughput_throttling": False,
        "max_throughput": 0,
        "sign": {"x": x, "y": y, "alpha": alpha, "c": 3},
    }


def build_config():
    """No journeys or transitions: the graph auto-wires and cost decides."""
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
                "baseSeed": 5150,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        # Clear air and no congestion term: distance is the only cost pressure,
        # so once E_side is known it is unambiguously the cheaper exit and any
        # change in behaviour is attributable to knowledge, not to weighting.
        "routing": {
            "w_smoke": 0.0,
            "w_fed": 0.0,
            "w_queue": 0.0,
            "base_speed_m_per_s": 1.3,
            "default_exit_capacity": 1.3,
            "sampling_step_m": 2.0,
        },
        "exits": {
            "E_end": _exit(E_END, E_END_SIGN),
            "E_side": _exit(E_SIDE, E_SIDE_SIGN),
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": {
                    "number": N_AGENTS,
                    "radius": AGENT_RADIUS,
                    "v0": 1.3,
                    "distribution_mode": "by_number",
                    "use_flow_spawning": False,
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    "familiarity": "discovery",
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
    """Clear-air deck: the generator's fire stripped, its slices kept.

    fdsvismap needs an extinction slice to answer any legibility query, so
    ``--geometry-only`` will not do -- it drops the slices along with the
    burner.  Clear air keeps position the only thing that varies.
    """
    from pyfds_evac.core.wkt_to_fds import wkt_to_fds

    fire = ("SURF_ID='BURNER'", "&SURF ID='BURNER'", "&RAMP ID='qramp'")
    kept = [
        line
        for line in wkt_to_fds(walkable_wkt, chid="cognitive_map_memory").splitlines()
        if not any(marker in line for marker in fire)
    ]
    return "\n".join(kept) + "\n"


def build():
    walkable = box(*CORRIDOR).union(box(*E_SIDE))
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")

    deck = build_fds_deck(walkable.wkt)
    if "BURNER" in deck:
        raise SystemExit("fire was not stripped from the generated deck")
    if "QUANTITY='EXTINCTION COEFFICIENT'" not in deck:
        raise SystemExit("deck has no extinction slice; fdsvismap would have no data")
    (HERE / "cognitive_map_memory.fds").write_text(deck, encoding="utf-8")

    with open(HERE / "config.json", "w", encoding="utf-8") as f:
        json.dump(build_config(), f, indent=2)

    spawn_area = box(*SPAWN).area
    capacity = spawn_area / (2 * AGENT_RADIUS) ** 2
    if N_AGENTS > 0.9 * capacity:
        raise SystemExit(
            f"{N_AGENTS} agents exceeds the ~{capacity:.0f} the spawn area holds"
        )

    window = legibility_window(*E_SIDE_SIGN)
    if window is None:
        raise SystemExit("E_side is legible nowhere; the scenario has no acquisition")
    lo, hi = window
    spawn_top = SPAWN[3]
    if lo <= spawn_top:
        raise SystemExit(
            f"E_side is already legible at the spawn area (window starts {lo:.1f} m, "
            f"spawn reaches {spawn_top:.1f} m): there would be nothing to acquire"
        )
    if hi >= CORRIDOR[3] - 2.0:
        raise SystemExit(
            f"the window ({hi:.1f} m) reaches the far end, so the sign never "
            "becomes illegible again and persistence is never exercised"
        )

    end_window = legibility_window(*E_END_SIGN)
    if end_window is None:
        raise SystemExit("E_end is legible nowhere; agents would know no exit at all")
    if end_window[0] > SPAWN[1]:
        raise SystemExit(
            f"E_end is illegible at the spawn area (legible only from "
            f"y={end_window[0]:.1f}, spawn starts at y={SPAWN[1]:.1f}). Agents would "
            "start knowing no exit at all and fall back to frontier exploration, "
            "which is a different scenario. Usually means the corridor outgrew the "
            f"{MAX_VIS_M:.0f} m visibility ceiling."
        )
    print(f"Wrote: {HERE / 'geometry.wkt'} and config.json and the deck")
    print(f"  E_side legible on the centreline for y in [{lo:.1f}, {hi:.1f}]")
    print(f"  spawn reaches y={spawn_top:.1f} (below the window: nothing known yet)")
    print(f"  E_end legible for y in [{end_window[0]:.1f}, {end_window[1]:.1f}]")
    print(f"  {N_AGENTS} agents in {spawn_area:.1f} m2 (capacity ~{capacity:.0f})")
    return walkable


if __name__ == "__main__":
    build()
