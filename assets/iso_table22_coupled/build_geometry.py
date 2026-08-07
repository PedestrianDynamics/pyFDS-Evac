#!/usr/bin/env python3
"""Generate the coupled stationary-FED verification scenario.

``assets/ISO-table22`` verifies that the runtime *accumulator* integrates a dose
correctly, but it hands the model three hardcoded numbers: its FED model ignores
``time_s``, ``x`` and ``y``, so no slice is read, no unit is converted and no
position is sampled.  It checks our arithmetic against our arithmetic.

This scenario closes that loop.  The same stationary occupant is exposed to the
same mixture, but the mixture reaches the model the way a real case does:

    deck -> FDS -> fdsreader -> slice selection -> unit conversion
         -> DefaultFedInputs -> accumulator -> fed_history

Every step is live.  The analytic answer is still known, because the gas is
*prescribed* rather than burned, so a closed form exists to compare against.

Why prescribed gas
    A single ``&INIT`` fills a sealed box with a fixed mixture.  No combustion,
    no transient, no spatial gradient -- concentration is not a variable, which
    is what lets ``time_to_fed_threshold_s`` predict the answer exactly.  The
    technique, and its pitfall (a second ``&INIT`` without ``XB`` silently
    resets the whole domain), follow ``assets/fic_vs_fed_speed``.

The mixture is the ``combined`` case from ``tests/test_fed.py``:

    CO   0.10 vol %   (1000 ppm)
    CO2  5.00 vol %
    O2  12.00 vol %

which gives a FED rate of 0.1316 /min and crosses FED = 1 at **456.0 s**.  All
three terms are active and none dominates: CO alone would take 1626 s, CO plus
the CO2 hyperventilation factor 628 s, and the O2 hypoxia term brings it to 456.
A unit slip in any one of the three moves the crossing time detectably.

What this catches that the stubbed test cannot
    A ppm/vol-% confusion, a slice read at the wrong height, a species missing
    from the deck (FED is silently skipped and every column reads zero -- see
    docs/fds-case-requirements.md), a sampler returning mass fraction where the
    model wants volume fraction, or a mesh whose extent does not cover the agent.
"""

import json
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent

# A small sealed box: the whole point is a uniform mixture, so the domain only
# has to be big enough to hold one agent and a slice. Small mesh, coarse dump
# interval, so the FDS output is small enough to commit and the test can run in
# CI rather than being skipped.
ROOM = (0.0, 0.0, 4.0, 4.0)
CELL = 0.5
CEILING = 3.0
SLICE_HEIGHT = 2.0

# The occupant stands in the middle and never moves; v0 = 0.
SPAWN = (1.4, 1.4, 2.6, 2.6)
# An exit is structurally required, so there is one -- in a corner, unreachable
# by an agent whose desired speed is zero. The agent must still be present at
# the end for the exposure to have been continuous, which the test asserts.
EXIT_BOX = (3.4, 3.4, 3.9, 3.9)

# The 'combined' case from tests/test_fed.py, so both tests describe the same
# occupant and their answers can be compared directly.
CO_PERCENT = 0.10
CO2_PERCENT = 5.00
O2_PERCENT = 12.00

T_END = 500.0  # FED = 1 lands at 456.0 s
DT_SLCF = 10.0


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def expected_inputs():
    """The mixture as the model should see it, for the test to compare against."""
    from pyfds_evac.core.fed import DefaultFedInputs

    return DefaultFedInputs(
        co_volume_fraction_percent=CO_PERCENT,
        co2_volume_fraction_percent=CO2_PERCENT,
        o2_volume_fraction_percent=O2_PERCENT,
    )


def expected_threshold_time_s() -> float:
    from pyfds_evac.core.fed import time_to_fed_threshold_s

    return time_to_fed_threshold_s(expected_inputs(), threshold=1.0)


def build_config():
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": T_END,
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
                    # Stationary by construction. ISO-table22 achieves the same
                    # thing with a pre-movement time of 20 000 000 s, which its
                    # own test then overrides -- two mechanisms, neither obvious.
                    "v0": 0.0,
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


def build_deck() -> str:
    """A sealed box holding a prescribed, homogeneous CO / CO2 / O2 mixture.

    Mass fractions are converted properly (``Y_i = X_i M_i / M_mix``) rather
    than assumed equal to the volume fractions; at 5 % CO2 and 12 % O2 the
    difference is far too large to wave away.
    """
    x0, y0, x1, y1 = ROOM
    m = {"N2": 28.013, "O2": 31.999, "CO": 28.010, "CO2": 44.009}
    x_co = CO_PERCENT / 100.0
    x_co2 = CO2_PERCENT / 100.0
    x_o2 = O2_PERCENT / 100.0
    x_n2 = 1.0 - x_co - x_co2 - x_o2
    m_mix = x_n2 * m["N2"] + x_o2 * m["O2"] + x_co * m["CO"] + x_co2 * m["CO2"]
    y_co = x_co * m["CO"] / m_mix
    y_co2 = x_co2 * m["CO2"] / m_mix
    y_o2 = x_o2 * m["O2"] / m_mix

    i = int((x1 - x0) / CELL)
    j = int((y1 - y0) / CELL)
    k = int(CEILING / CELL)

    return f"""&HEAD CHID='iso_table22_coupled',
      TITLE='Sealed {x1 - x0:.0f}x{y1 - y0:.0f} m box, prescribed CO/CO2/O2 for stationary FED' /

! No combustion: the mixture is prescribed, so it is uniform in space and
! constant in time and the analytic FED crossing is exact.
&MESH IJK={i},{j},{k}, XB={x0:.2f},{x1:.2f},{y0:.2f},{y1:.2f},0.0,{CEILING:.2f} /
&TIME T_END={T_END:.0f} /
&MISC TMPA=20.0 /

! Nitrogen background so O2 is not double-counted.
&SPEC ID='NITROGEN',        BACKGROUND=.TRUE. /
&SPEC ID='OXYGEN'                             /
&SPEC ID='CARBON MONOXIDE'                    /
&SPEC ID='CARBON DIOXIDE'                     /
! Declared only so the extinction slice has a species to report on; with no
! combustion its mass fraction stays 0, so the box is optically clear.
&SPEC ID='SOOT'                               /

! Target volume fractions: CO = {CO_PERCENT} %, CO2 = {CO2_PERCENT} %, O2 = {O2_PERCENT} %.
!
! NOTE: all species MUST be in a single &INIT. A second &INIT with no XB resets
! the whole domain, overwriting the first and leaving everything at 0.
&INIT SPEC_ID(1)='CARBON MONOXIDE',
      SPEC_ID(2)='CARBON DIOXIDE',
      SPEC_ID(3)='OXYGEN',
      MASS_FRACTION(1)={y_co:.5E},
      MASS_FRACTION(2)={y_co2:.5E},
      MASS_FRACTION(3)={y_o2:.5E} /

! Slices pyFDS-Evac reads at breathing height. SPEC_ID is required on the
! extinction slice once species are declared explicitly (FDS ERROR 1004).
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE'  /
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN'          /
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT'     /
&DUMP DT_SLCF={DT_SLCF:.1f} /

&TAIL /
"""


def build():
    walkable = box(*ROOM)
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")
    (HERE / "iso_table22_coupled.fds").write_text(build_deck(), encoding="utf-8")
    with open(HERE / "config.json", "w", encoding="utf-8") as handle:
        json.dump(build_config(), handle, indent=2)

    crossing = expected_threshold_time_s()
    if crossing >= T_END:
        raise SystemExit(
            f"FED reaches 1.0 only at {crossing:.0f} s but the deck stops at "
            f"{T_END:.0f} s; the crossing would never be observed."
        )
    if crossing <= 3 * DT_SLCF:
        raise SystemExit(
            f"FED crosses at {crossing:.0f} s, within a few slice dumps "
            f"({DT_SLCF:.0f} s apart); the comparison would be dominated by "
            "the dump interval rather than by the accumulator."
        )

    print("Wrote geometry.wkt, config.json and iso_table22_coupled.fds")
    print(f"  CO {CO_PERCENT} %, CO2 {CO2_PERCENT} %, O2 {O2_PERCENT} %")
    print(f"  analytic FED=1 at {crossing:.1f} s, deck runs to {T_END:.0f} s")
    return walkable


if __name__ == "__main__":
    build()
