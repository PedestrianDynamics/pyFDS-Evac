#!/usr/bin/env python3
"""ISO 20414 Table 22, run through the real FDS coupling.

Two references, and neither is sufficient alone.

**ISO 20414:2020, Table 22** (Test 19, *Occupant incapacitation by fire/smoke*)
gives the geometry and the method: a room with no fire source, 10 m x 10 m x
3 m; an occupant at the centre "held in a fixed initial position by setting a
high pre-evacuation time (> 10 000 000 s)"; hazardous conditions implemented
per the incapacitation sub-model; and the expected result that the time to
reach FED = 1 matches the time computed by hand or by an independent fire
model. It deliberately does **not** prescribe concentrations -- it says to
repeat the test for each hazardous condition the sub-model supports.

**The FDS+Evac Technical Reference, Figure 8** ("A FED test") supplies exactly
the concrete sets ISO leaves to the tester. Four calculations, as
(CO2, CO, O2) volume fractions, chosen so the terms can be told apart:

    (2,    0.1, 15) %   all three active
    (0,    0,   12) %   O2 hypoxia alone
    (0,    0.1, 21) %   CO alone -- O2 above the 19.5 % gate, no CO2 factor
    (3.43, 0.1, 21) %   CO plus the CO2 hyperventilation factor

So this asset takes ISO's room and method with the guide's concentrations.

Why this exists next to ``assets/ISO-table22``
    That asset performs the same test with the FED field *stubbed*: its model
    ignores ``time_s``, ``x`` and ``y`` and returns hardcoded numbers, so no
    slice is read, no unit converted, no position sampled. It verifies the
    accumulator and nothing about how gas reaches it. Here every step is live:

        deck -> FDS -> fdsreader -> slice selection -> unit conversion
             -> DefaultFedInputs -> accumulator -> fed_history

    ISO's Step 2 -- "hand calculations or an independent validated fire model"
    -- is ``time_to_fed_threshold_s()``, which is exact because the gas is
    prescribed by a single ``&INIT`` and so uniform in space and constant in
    time.

The occupant is held still by ISO's own method, a pre-evacuation time drawn
above 10 000 000 s, rather than by forcing ``v0`` to zero. Note the draw is
bounded *below* by 1e7: a uniform draw over [0, 2e7] would occasionally return
a few seconds and let the occupant walk away mid-test.
"""

import json
import math
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent

# ISO 20414 Table 22: "A room with no fire source (10 m x 10 m x 3 m)."
ROOM = (0.0, 0.0, 10.0, 10.0)
CEILING = 3.0
CELL = 0.5
SLICE_HEIGHT = 2.0

# "place an occupant in the centre of the room"
SPAWN = (4.4, 4.4, 5.6, 5.6)
# Structurally required by the loader; unreachable by a stationary occupant.
EXIT_BOX = (9.0, 9.0, 9.8, 9.8)

# ISO: "a high pre-evacuation time (> 10 000 000 s)". Bounded below so every
# draw satisfies it.
PREMOVEMENT_LO = 1.2e7
PREMOVEMENT_HI = 2.0e7

# FDS+Evac Technical Reference, Figure 8. Keys are the case letters used for
# the config, deck and FDS output directory names.
CASES = {
    "a": {"co2": 2.00, "co": 0.10, "o2": 15.0, "isolates": "all three terms"},
    "b": {"co2": 0.00, "co": 0.00, "o2": 12.0, "isolates": "O2 hypoxia alone"},
    "c": {"co2": 0.00, "co": 0.10, "o2": 21.0, "isolates": "CO alone"},
    "d": {"co2": 3.43, "co": 0.10, "o2": 21.0, "isolates": "CO + CO2 factor"},
}

MOLAR_MASS = {"N2": 28.013, "O2": 31.999, "CO": 28.010, "CO2": 44.009}


def inputs_for(case: str):
    """The mixture as the model should see it, for the test to compare against."""
    from pyfds_evac.core.fed import DefaultFedInputs

    spec = CASES[case]
    return DefaultFedInputs(
        co_volume_fraction_percent=spec["co"],
        co2_volume_fraction_percent=spec["co2"],
        o2_volume_fraction_percent=spec["o2"],
    )


def threshold_time_s(case: str) -> float:
    """ISO's Step 2: the hand calculation this run is verified against."""
    from pyfds_evac.core.fed import time_to_fed_threshold_s

    return time_to_fed_threshold_s(inputs_for(case), threshold=1.0)


def end_time_s(case: str) -> float:
    """15 % past the crossing, rounded up to a whole 50 s.

    The rounding is cosmetic and deliberately *not* tied to ``DT_SLCF`` (500 s):
    FDS writes a slice at ``T_END`` whatever the dump interval, and the field is
    constant anyway, so there is nothing to gain from making the two divide.
    The 15 % headroom is what matters -- the crossing has to land inside the
    run, and ``build()`` refuses to write a deck where it does not.
    """
    return math.ceil(threshold_time_s(case) * 1.15 / 50.0) * 50.0


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def mass_fractions(case: str) -> dict:
    """Convert volume fractions properly: Y_i = X_i M_i / M_mix.

    At 3.43 % CO2 or 12 % O2 the difference from assuming Y = X is far too
    large to wave away.
    """
    spec = CASES[case]
    x = {
        "CO": spec["co"] / 100.0,
        "CO2": spec["co2"] / 100.0,
        "O2": spec["o2"] / 100.0,
    }
    x_n2 = 1.0 - sum(x.values())
    m_mix = x_n2 * MOLAR_MASS["N2"] + sum(
        x[k] * MOLAR_MASS[k] for k in ("CO", "CO2", "O2")
    )
    return {k: x[k] * MOLAR_MASS[k] / m_mix for k in ("CO", "CO2", "O2")}


def build_config(case: str) -> dict:
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": end_time_s(case),
                    "dt": 0.05,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": 420,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        "routing": {
            "w_smoke": 0.0,
            "w_fed": 0.0,
            "w_queue": 0.0,
            "base_speed_m_per_s": 1.0,
            "default_exit_capacity": 1.0,
            "sampling_step_m": 1.0,
        },
        "exits": {
            "E_unused": {
                "type": "polygon",
                "coordinates": _coords(EXIT_BOX),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": {
                    "number": 1,
                    "radius": 0.2,
                    "v0": 1.25,
                    "distribution_mode": "by_number",
                    "use_flow_spawning": False,
                    # ISO's own method of holding the occupant still.
                    "use_premovement": True,
                    "premovement_distribution": "uniform",
                    "premovement_param_a": PREMOVEMENT_LO,
                    "premovement_param_b": PREMOVEMENT_HI,
                    "premovement_seed": 420,
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


def build_deck(case: str) -> str:
    spec = CASES[case]
    y = mass_fractions(case)
    x0, y0, x1, y1 = ROOM
    i, j, k = int((x1 - x0) / CELL), int((y1 - y0) / CELL), int(CEILING / CELL)

    return f"""&HEAD CHID='iso_table22_{case}',
      TITLE='ISO 20414 Table 22 room, case {case}: CO2 {spec["co2"]}%, CO {spec["co"]}%, O2 {spec["o2"]}%' /

! ISO 20414 Table 22: "A room with no fire source (10 m x 10 m x 3 m)."
! The gas is prescribed, not burned, so it is uniform in space and constant in
! time and the hand calculation of ISO's Step 2 is exact.
&MESH IJK={i},{j},{k}, XB={x0:.2f},{x1:.2f},{y0:.2f},{y1:.2f},0.0,{CEILING:.2f} /
&TIME T_END={end_time_s(case):.0f} /
&MISC TMPA=20.0 /

! Nitrogen background so O2 is not double-counted.
&SPEC ID='NITROGEN',        BACKGROUND=.TRUE. /
&SPEC ID='OXYGEN'                             /
&SPEC ID='CARBON MONOXIDE'                    /
&SPEC ID='CARBON DIOXIDE'                     /
! Declared only so the extinction slice has a species to report on; SPEC_ID is
! mandatory once species are declared explicitly, or FDS raises ERROR 1004.
! With no combustion its mass fraction stays 0, so the room is optically clear.
&SPEC ID='SOOT'                               /

! Case {case} -- {spec["isolates"]}.
! NOTE: all species MUST be in a single &INIT. A second &INIT with no XB resets
! the whole domain, overwriting the first and leaving everything at 0.
&INIT SPEC_ID(1)='CARBON MONOXIDE',
      SPEC_ID(2)='CARBON DIOXIDE',
      SPEC_ID(3)='OXYGEN',
      MASS_FRACTION(1)={y["CO"]:.5E},
      MASS_FRACTION(2)={y["CO2"]:.5E},
      MASS_FRACTION(3)={y["O2"]:.5E} /

&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE'  /
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN'          /
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT'     /
&DUMP DT_SLCF=500.0 /

&TAIL /
"""


def build():
    if PREMOVEMENT_LO <= 1.0e7:
        raise SystemExit(
            "ISO 20414 Table 22 requires a pre-evacuation time above 10 000 000 s; "
            f"the draw starts at {PREMOVEMENT_LO:.0f} s"
        )

    (HERE / "geometry.wkt").write_text(box(*ROOM).wkt + "\n", encoding="utf-8")

    print(f"ISO 20414 Table 22 room {ROOM[2]:.0f} x {ROOM[3]:.0f} x {CEILING:.0f} m")
    header = (
        f"{'case':5s} {'CO2':>6s} {'CO':>5s} {'O2':>5s} {'FED=1':>8s} {'T_END':>7s}"
    )
    print(f"{header}   isolates")
    for case, spec in CASES.items():
        crossing = threshold_time_s(case)
        end = end_time_s(case)
        if crossing >= end:
            raise SystemExit(
                f"case {case}: FED reaches 1.0 at {crossing:.0f} s but the deck "
                f"stops at {end:.0f} s; the crossing would never be observed"
            )
        (HERE / f"iso_table22_{case}.fds").write_text(
            build_deck(case), encoding="utf-8"
        )
        with open(HERE / f"config_{case}.json", "w", encoding="utf-8") as handle:
            json.dump(build_config(case), handle, indent=2)
        print(
            f"{case:5s} {spec['co2']:6.2f} {spec['co']:5.2f} {spec['o2']:5.1f} "
            f"{crossing:7.0f}s {end:6.0f}s   {spec['isolates']}"
        )


if __name__ == "__main__":
    build()
