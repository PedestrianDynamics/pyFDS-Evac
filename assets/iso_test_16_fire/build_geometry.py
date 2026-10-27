#!/usr/bin/env python3
"""ISO 20414 Test 16 (affiliation to familiar exits) with smoke from FDS output.

The synthetic test ``tests/test_iso_test_16_familiar_exit.py`` fills the east
side of a 10 m x 15 m room, with the door strip of exit 2, with a static
extinction coefficient K and measures how often three occupants leave by exit 2:

    A  discovery + ``entrance: "exit_2"`` (the ISO 16 sub-model),
    B  full familiarity and a journey to exit 2 with ``allocation: "preference"``,
    C  full familiarity, no journey.

This asset puts the same box into five FDS decks, one per K, so the extinction
reaches the router through

    deck -> FDS -> fdsreader -> SliceFieldSampler -> route cost -> exit choice

Prescribed soot, not a fire
    A single ``&INIT`` fills the box with the soot mass fraction that gives K
    through FDS's own definition (K = 8700 m^2/kg x soot density). There is no
    combustion and no obstruction: the walls live in ``geometry.wkt``.

The t = 0 limit
    An ``&INIT`` acts at t = 0. The synthetic box is also on from t = 0, so
    this variant has no limit of its own.

Two traps, both caught by the premise test
    1. FDS defaults the ambient oxygen mass fraction to 0, which gives a density
       contrast outside the box and a gravity current within seconds. The
       OXYGEN species carries ``MASS_FRACTION_0=0.231``.
    2. Soot (W = 12.011 g/mol) is lighter than air, so the box would rise. The
       ``&INIT`` carries the temperature that cancels the buoyancy of the soot.

The assets are standalone scripts, so the soot and temperature formulas below
are repeated in ``assets/iso_test_8_fire``.
"""

import json
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent
ASSET = "iso_test_16_fire"

# K [1/m] of each deck and the CHID suffix it is named by: the three levels of
# the synthetic test plus the two that bracket the tau deadband (K = 0.13 /m).
DECK_KS = (0.05, 0.10, 0.20, 0.5, 3.0)
LABELS = {0.05: "k0p05", 0.10: "k0p10", 0.20: "k0p20", 0.5: "k0p5", 3.0: "k3"}

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

# FDS mesh, 0.25 x 0.25 x 0.5 m; x = 6.0 is a cell face.
MESH = (48, 60, 6)
MESH_XB = (-1.0, 11.0, 0.0, 15.0, 0.0, 3.0)
# The synthetic _BoxSmoke(SMOKE_X_MIN_M = 6.0), including the exit-2 strip.
SOOT_BOX_XB = (6.0, 11.0, 0.0, 15.0, 0.0, 3.0)
T_END_S = 70
DT_SLCF_S = 5
SLICE_HEIGHT = 2.0
DEFAULT_HEIGHT = 1.6

# Scenario: the same constants as tests/test_iso_test_16_familiar_exit.py.
ROOM_WIDTH_M = 10.0
ROOM_LENGTH_M = 15.0
EXIT_WIDTH_M = 1.0
EXIT_DEPTH_M = 1.0
SPEED_MPS = 1.0
MAX_TIME_S = 40.0
SEED = 1
PIN_HALF_M = 0.25
PIN_CENTRE = (ROOM_WIDTH_M / 2.0, ROOM_LENGTH_M / 2.0)
SAMPLING_STEP_M = 0.25
# Occupant A: the ISO 16 sub-model.
OCCUPANT_A = {"familiarity": "discovery", "entrance": "exit_2"}


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
      TITLE='ISO 20414 Test 16 fire variant, prescribed soot box K = {k:g} 1/m' /

! ISO 20414 Test 16 (affiliation to familiar exits), smoke in the east of the
! room and in the strip of exit 2. No combustion and no obstruction: the soot
! is prescribed in a box that is there from t = 0, and the walls live in
! geometry.wkt.
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


def _doors() -> dict:
    lo = ROOM_LENGTH_M / 2.0 - EXIT_WIDTH_M / 2.0
    hi = ROOM_LENGTH_M / 2.0 + EXIT_WIDTH_M / 2.0
    return {
        "exit_1": box(-EXIT_DEPTH_M, lo, 0.0, hi),
        "exit_2": box(ROOM_WIDTH_M, lo, ROOM_WIDTH_M + EXIT_DEPTH_M, hi),
    }


def walkable_area():
    area = box(0.0, 0.0, ROOM_WIDTH_M, ROOM_LENGTH_M)
    for door in _doors().values():
        area = area.union(door)
    return area


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def build_config() -> dict:
    """Occupant A at seed 1, pinned to a 0.5 m square at the room centre."""
    x, y = PIN_CENTRE
    pin = box(x - PIN_HALF_M, y - PIN_HALF_M, x + PIN_HALF_M, y + PIN_HALF_M)
    sim_params = {
        "max_simulation_time": MAX_TIME_S,
        "model_type": "CollisionFreeSpeedModel",
    }
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
        "routing": {"sampling_step_m": SAMPLING_STEP_M},
        "exits": {
            name: {
                "type": "polygon",
                "coordinates": _coords(poly),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
            for name, poly in _doors().items()
        },
        "distributions": {
            "occupant": {
                "type": "polygon",
                "coordinates": _coords(pin),
                "parameters": {
                    "number": 1,
                    "radius": 0.2,
                    "v0": SPEED_MPS,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    **OCCUPANT_A,
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
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
