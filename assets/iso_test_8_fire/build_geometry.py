#!/usr/bin/env python3
"""ISO 20414 Test 8 (exit route allocation) with smoke read from FDS output.

The synthetic test ``tests/test_iso_test_8_route_allocation.py`` switches a box
of extinction on at t = 5 s in the main passage and checks that an allocation
given by a journey yields to it (or, with ``"allocation": "hard"``, holds).
This asset puts the same box into an FDS deck, so the extinction reaches the
router through

    deck -> FDS -> fdsreader -> SliceFieldSampler -> route cost -> exit choice

Prescribed soot, not a fire
    A single ``&INIT`` fills the box with the soot mass fraction that gives K
    through FDS's own definition (K = 8700 m^2/kg x soot density). There is no
    combustion and no obstruction: the walls live in ``geometry.wkt`` and K is
    sampled on walkable points only.

The t = 0 limit
    An ``&INIT`` acts at t = 0, so the smoke is present at spawn. This variant
    tests allocation under smoke that is there from the start: the preference
    yields at spawn and the hard allocation holds. It does not test the 5 s
    onset, the before/inside/past groups or the 1.255 m threshold; those stay
    synthetic-only.

Two traps, both caught by the premise test
    1. FDS defaults the ambient oxygen mass fraction to 0. Outside the box
       that is a density contrast of a few percent and a gravity current within
       seconds. The OXYGEN species carries ``MASS_FRACTION_0=0.231``.
    2. Soot (W = 12.011 g/mol) is lighter than air, so the box would rise. The
       ``&INIT`` carries the temperature that cancels the buoyancy of the soot.

Frozen at t = 0
    Nothing in FDS holds the soot in the box, and it mixes out through the two
    ends that cross the passage: one cell inside them K is 11 % low at 10 s
    and 19 % low at 20 s, while the run reads up to 19.4 s. The deck therefore
    stops at 0.1 s, and the run holds the last frame
    (``--allow-fds-horizon-hold``), as the synthetic box holds its value.

The assets are standalone scripts, so the soot and temperature formulas below
are repeated in ``assets/iso_test_16_fire``.
"""

import json
from pathlib import Path

from shapely.geometry import box
from shapely.ops import unary_union

HERE = Path(__file__).parent
ASSET = "iso_test_8_fire"

# K [1/m] of each deck and the CHID suffix it is named by.
DECK_KS = (5.0, 1.0)
LABELS = {5.0: "k5", 1.0: "k1"}

# FDS: K = MASS_EXTINCTION_COEFFICIENT * soot density, 8700 m^2/kg by default.
# The conversion K / Y = 10428 1/m per unit mass fraction is the one measured
# in assets/iso_table21_coupled (0.99545 and 0.99550 /m at Y = 9.545929e-5).
K_PER_MASS_FRACTION = 1.0 / 9.5893e-5
O2_MASS_FRACTION = 0.231
N2_MASS_FRACTION = 0.769
W_O2, W_N2, W_SOOT = 31.9988, 28.0134, 12.011
# 28.8432 g/mol: the mean molar mass of the ambient O2/N2 mixture.
W_AIR = 1.0 / (O2_MASS_FRACTION / W_O2 + N2_MASS_FRACTION / W_N2)
AMBIENT_K = 293.15

# FDS mesh, 0.2 x 0.2 x 0.5 m; y = 0.3 and y = 2.3 fall on cell faces.
MESH = (95, 51, 6)
MESH_XB = (-10.0, 9.0, -4.7, 5.5, 0.0, 3.0)
# The synthetic SMOKE_BOX (-3.8, 0.3, -2.7, 2.3), widened in x into the wall
# thickness so that x is grid-aligned and the edge smear falls outside the
# 1.1 m passage.
SOOT_BOX_XB = (-4.0, -2.6, 0.3, 2.3, 0.0, 3.0)
# FDS writes the frames at 0 and 0.1 s; the run holds the last one.
T_END_S = 0.1
DT_SLCF_S = 0.1
SLICE_HEIGHT = 2.0
DEFAULT_HEIGHT = 1.6

# Scenario: the same constants as tests/test_iso_test_8_route_allocation.py.
SEED = 42
RADIUS_M = 0.15
SPEED_MPS = 1.3
MAX_TIME_S = 120.0
DOOR_WIDTH_M = 0.8
WALL_M = 0.1
SPAWN_MARGIN_M = 0.3
CORRIDOR = (-9.9, -0.6, 9.0, 0.3)
MAIN = "main"
SECONDARY = "secondary"
# Room number -> (x_min, x_max, north side?) of the room interior.
ROOMS = {
    1: (-9.8, -6.9, True),
    2: (-6.8, -4.0, True),
    3: (-2.6, -0.7, True),
    4: (-0.5, 2.3, True),
    5: (2.5, 5.3, True),
    6: (5.4, 8.3, True),
    7: (-9.8, -6.9, False),
    8: (-6.8, -3.9, False),
    9: (-3.8, -0.7, False),
    10: (-0.5, 2.3, False),
    11: (2.4, 5.3, False),
    12: (5.4, 8.3, False),
}
OCCUPANTS = {room: 2 for room in ROOMS} | {3: 1}
MAIN_ROOMS = (1, 2, 3, 4, 7, 8, 9, 10)
ALLOCATION = {room: MAIN if room in MAIN_ROOMS else SECONDARY for room in ROOMS}
ROOM_DEPTH_NORTH = (0.4, 4.2)
ROOM_DEPTH_SOUTH = (-4.5, -0.7)
MAIN_PASSAGE = (-3.8, -2.7)
EXITS = {
    MAIN: box(-3.7, 5.0, -2.8, 5.4),
    SECONDARY: box(8.7, -0.3, 8.9, 0.1),
}
SAMPLING_STEP_M = 0.25


def soot_mass_fraction(k: float) -> float:
    """The soot mass fraction that gives *k* [1/m] by FDS's definition."""
    return k / K_PER_MASS_FRACTION


def box_temperature_c(k: float) -> float:
    """The box temperature [C] at which the soot does not change the density."""
    y = soot_mass_fraction(k)
    inverse_w = O2_MASS_FRACTION / W_O2 + (N2_MASS_FRACTION - y) / W_N2 + y / W_SOOT
    return AMBIENT_K * (1.0 / inverse_w) / W_AIR - 273.15


def deck_chid(k: float) -> str:
    return f"{ASSET}_{LABELS[k]}"


def deck_text(k: float) -> str:
    i, j, n = MESH
    mesh = ",".join(f"{v:.1f}" for v in MESH_XB)
    soot = ",".join(f"{v:.1f}" for v in SOOT_BOX_XB)
    return f"""&HEAD CHID='{deck_chid(k)}',
      TITLE='ISO 20414 Test 8 fire variant, prescribed soot box K = {k:g} 1/m' /

! ISO 20414 Test 8 (exit route allocation), smoke in the main passage.
! No combustion and no obstruction: the soot is prescribed in a box that is
! there from t = 0, and the walls live in geometry.wkt. The run holds the
! 0.1 s frame (--allow-fds-horizon-hold): the box mixes out at its ends later.
&MESH IJK={i},{j},{n}, XB={mesh} /
&TIME T_END={T_END_S} /
&MISC TMPA=20.0 /

&SPEC ID='NITROGEN', BACKGROUND=.TRUE. /
&SPEC ID='OXYGEN', MASS_FRACTION_0={O2_MASS_FRACTION} /      ! ambient O2 outside the box
&SPEC ID='SOOT' /

! Target K = {k:g} 1/m: soot mass fraction K x 9.5893E-05 (8700 m^2/kg).
! The box temperature cancels the buoyancy of the soot (W = 12.011 g/mol),
! so the gas stays still. All species MUST be in this single &INIT.
&INIT XB={soot}, TEMPERATURE={box_temperature_c(k):.4f},
      SPEC_ID(1)='SOOT', SPEC_ID(2)='OXYGEN',
      MASS_FRACTION(1)={soot_mass_fraction(k):.5E},
      MASS_FRACTION(2)={O2_MASS_FRACTION} /

! SPEC_ID is mandatory on the extinction slice once species are declared.
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT' /
! The default sampling height of pyFDS-Evac; FDS snaps it to the 1.5 m face.
&SLCF PBZ={DEFAULT_HEIGHT}, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT' /
&DUMP DT_SLCF={DT_SLCF_S} /

&TAIL /
"""


def _room_box(room: int):
    x0, x1, north = ROOMS[room]
    y0, y1 = ROOM_DEPTH_NORTH if north else ROOM_DEPTH_SOUTH
    return box(x0, y0, x1, y1)


def _door_box(room: int):
    x0, x1, north = ROOMS[room]
    xc = (x0 + x1) / 2.0
    lo, hi = xc - DOOR_WIDTH_M / 2.0, xc + DOOR_WIDTH_M / 2.0
    if north:
        return box(lo, CORRIDOR[3] - WALL_M, hi, ROOM_DEPTH_NORTH[0] + WALL_M)
    return box(lo, ROOM_DEPTH_SOUTH[1] - WALL_M, hi, CORRIDOR[1] + WALL_M)


def walkable_area():
    x0, y0, x1, y1 = CORRIDOR
    parts = [box(x0, y0, x1, y1)]
    parts += [_room_box(room) for room in ROOMS]
    parts += [_door_box(room) for room in ROOMS]
    parts.append(box(MAIN_PASSAGE[0], y1 - WALL_M, MAIN_PASSAGE[1], 5.5))
    return unary_union(parts)


def _spawn_area(room: int):
    x0, y0, x1, y1 = _room_box(room).bounds
    m = SPAWN_MARGIN_M
    return box(x0 + m, y0 + m, x1 - m, y1 - m)


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def build_config() -> dict:
    """The preference variant: each journey names an exit but may yield."""
    sim_params = {
        "max_simulation_time": MAX_TIME_S,
        "model_type": "CollisionFreeSpeedModel",
    }
    pairs = []
    for room in ROOMS:
        name, exit_id = f"room_{room}", ALLOCATION[room]
        transition = {"from": name, "to": exit_id, "journey_id": f"journey_{room}"}
        journey = {
            "id": f"journey_{room}",
            "stages": [name, exit_id],
            "transitions": [transition],
        }
        pairs.append((journey, transition))
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": sim_params,
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "routing": {"sampling_step_m": SAMPLING_STEP_M, "anticipate": False},
        "exits": {
            name: {
                "type": "polygon",
                "coordinates": _coords(poly),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
            for name, poly in EXITS.items()
        },
        "distributions": {
            f"room_{room}": {
                "type": "polygon",
                "coordinates": _coords(_spawn_area(room)),
                "parameters": {
                    "number": OCCUPANTS[room],
                    "radius": RADIUS_M,
                    "v0": SPEED_MPS,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                },
            }
            for room in ROOMS
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [journey for journey, _ in pairs],
        "transitions": [transition for _, transition in pairs],
    }


def main() -> None:
    (HERE / "geometry.wkt").write_text(walkable_area().wkt + "\n", encoding="utf-8")
    with open(HERE / "config.json", "w", encoding="utf-8") as handle:
        json.dump(build_config(), handle, indent=2)
        handle.write("\n")
    for k in DECK_KS:
        (HERE / f"{deck_chid(k)}.fds").write_text(deck_text(k), encoding="utf-8")
        print(
            f"{deck_chid(k)}: K = {k:g} 1/m, mass fraction "
            f"{soot_mass_fraction(k):.5E}, box {box_temperature_c(k):.4f} C"
        )


if __name__ == "__main__":
    main()
