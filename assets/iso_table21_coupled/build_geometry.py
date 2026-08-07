#!/usr/bin/env python3
"""ISO 20414 Table 21, with the extinction coefficient read from FDS output.

ISO 20414:2020 Table 21 (Test 18, *Reduced visibility vs walking speed*)
specifies a corridor 2 m wide and 100 m long with one exit at the end, an
unimpeded walking speed of 1,25 m/s, and "a constant extinction coefficient
equal to 1,0/m ... implemented in the corridor prior to running the simulation".
The expected result is that the time to cover the corridor matches the time
calculated by hand from the model's own correlation.

``assets/ISO-table21`` implements exactly that, and it is faithful: ISO says
the coefficient is *implemented*, not that it comes from a fire model. But it
supplies K through ``ConstantExtinctionField``, so no slice is ever read.

That leaves the extinction path untested from end to end, and extinction is the
busier of the two hazard signals -- it drives the walking-speed factor *and* the
routing cost through ``w_smoke``. It is also where ``EXTINCTION`` and
``SOOT EXTINCTION COEFFICIENT`` were once confused for each other, two unrelated
FDS quantities (User Guide Sec. 22.10.29 vs 22.10.5).

This asset closes it. The corridor and the occupant are ISO's; K arrives via

    deck -> FDS -> fdsreader -> SliceFieldSampler -> speed factor -> egress time

Prescribed soot, not a fire
    A single ``&INIT`` fills the corridor with a fixed soot mass fraction. No
    combustion, no plume, no gradient, so K is constant in space and time and
    the hand calculation stays exact -- the same technique as
    ``assets/iso_table22_coupled`` and ``assets/fic_vs_fed_speed``.

A cross-check the FED asset cannot make
    FDS computes its ``SOOT EXTINCTION COEFFICIENT`` slice as
    ``MASS_EXTINCTION_COEFFICIENT * soot density``, defaulting to 8700 m^2/kg.
    ``extinction_from_soot_density()`` uses the same 8700. So asking FDS for a
    target K by prescribing the soot density that should produce it tests our
    conversion against FDS's, not merely the plumbing between them. A test that
    injected K directly could not tell the two apart.
"""

import json
import math
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent

# ISO 20414 Table 21: "A corridor 2 m wide and 100 m long. One exit (1 m wide)
# is placed at the end of the corridor."
CORRIDOR = (-50.0, -1.0, 50.0, 1.0)
CEILING = 3.0
CELL = 0.5
SLICE_HEIGHT = 2.0

EXIT_BOX = (49.0, -0.5, 49.92, 0.5)
SPAWN = (-49.5, -0.5, -48.5, 0.5)

# ISO: "unimpeded walking speed ... set to a constant value equal to 1,25 m/s".
V0 = 1.25
# ISO: "A constant extinction coefficient equal to 1,0/m".
TARGET_K = 1.0

# FDS: K = MASS_EXTINCTION_COEFFICIENT * soot_density, default 8700 m^2/kg.
# pyfds_evac.core.smoke_speed.extinction_from_soot_density uses the same value,
# which is what makes this a cross-check rather than a tautology.
MASS_EXTINCTION_COEFFICIENT = 8700.0
# Air at 20 C, 101,325 kPa. Only used to turn a target density into the mass
# fraction FDS wants; the test verifies the K that actually comes back.
AIR_DENSITY_KG_PER_M3 = 1.2041


def soot_density_kg_per_m3(target_k: float = TARGET_K) -> float:
    """The soot density that yields *target_k*, by FDS's own definition."""
    return target_k / MASS_EXTINCTION_COEFFICIENT


def soot_mass_fraction(target_k: float = TARGET_K) -> float:
    return soot_density_kg_per_m3(target_k) / AIR_DENSITY_KG_PER_M3


def expected_speed_factor(target_k: float = TARGET_K) -> float:
    from pyfds_evac.core.smoke_speed import speed_factor_from_extinction

    return speed_factor_from_extinction(target_k)


def end_time_s() -> float:
    """Generous: the walk at the reduced speed, plus half again."""
    length = CORRIDOR[2] - CORRIDOR[0]
    return math.ceil(length / (V0 * expected_speed_factor()) * 1.5 / 50.0) * 50.0


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def build_config() -> dict:
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": end_time_s(),
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
            "base_speed_m_per_s": V0,
            "default_exit_capacity": 1.0,
            "sampling_step_m": 2.0,
        },
        "exits": {
            "E_end": {
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
                    "v0": V0,
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
    x0, y0, x1, y1 = CORRIDOR
    i = int((x1 - x0) / CELL)
    j = int((y1 - y0) / CELL)
    k = int(CEILING / CELL)
    y_soot = soot_mass_fraction()

    return f"""&HEAD CHID='iso_table21_coupled',
      TITLE='ISO 20414 Table 21 corridor, prescribed soot for K = {TARGET_K} 1/m' /

! ISO 20414 Table 21: "A corridor 2 m wide and 100 m long."
! No combustion: the soot is prescribed, so K is constant in space and time and
! the hand calculation of the expected egress time stays exact.
&MESH IJK={i},{j},{k}, XB={x0:.2f},{x1:.2f},{y0:.2f},{y1:.2f},0.0,{CEILING:.2f} /
&TIME T_END={end_time_s():.0f} /
&MISC TMPA=20.0 /

&SPEC ID='NITROGEN', BACKGROUND=.TRUE. /
&SPEC ID='OXYGEN'                      /
&SPEC ID='SOOT'                        /

! Target K = {TARGET_K} 1/m. FDS computes the extinction coefficient as
! MASS_EXTINCTION_COEFFICIENT * soot density, defaulting to {MASS_EXTINCTION_COEFFICIENT:.0f} m^2/kg, so
! a soot density of {soot_density_kg_per_m3() * 1e6:.1f} mg/m^3 is what produces it.
!
! NOTE: all species MUST be in a single &INIT. A second &INIT with no XB resets
! the whole domain, overwriting the first and leaving everything at 0.
&INIT SPEC_ID(1)='SOOT',
      SPEC_ID(2)='OXYGEN',
      MASS_FRACTION(1)={y_soot:.6E},
      MASS_FRACTION(2)=2.31000E-01 /

! SPEC_ID is mandatory on the extinction slice once species are declared
! explicitly, or FDS raises ERROR 1004.
&SLCF PBZ={SLICE_HEIGHT}, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT' /
&DUMP DT_SLCF=100.0 /

&TAIL /
"""


def build():
    walkable = box(*CORRIDOR)
    if abs((CORRIDOR[2] - CORRIDOR[0]) - 100.0) > 1e-9:
        raise SystemExit("ISO 20414 Table 21 specifies a 100 m corridor")
    if abs((CORRIDOR[3] - CORRIDOR[1]) - 2.0) > 1e-9:
        raise SystemExit("ISO 20414 Table 21 specifies a 2 m wide corridor")
    if abs((EXIT_BOX[3] - EXIT_BOX[1]) - 1.0) > 1e-9:
        raise SystemExit("ISO 20414 Table 21 specifies a 1 m wide exit")

    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")
    (HERE / "iso_table21_coupled.fds").write_text(build_deck(), encoding="utf-8")
    with open(HERE / "config.json", "w", encoding="utf-8") as handle:
        json.dump(build_config(), handle, indent=2)

    factor = expected_speed_factor()
    length = CORRIDOR[2] - CORRIDOR[0]
    print(f"ISO 20414 Table 21 corridor {length:.0f} x 2 m, v0 = {V0} m/s")
    print(f"  target K              {TARGET_K} 1/m")
    print(
        f"  prescribed soot       {soot_density_kg_per_m3() * 1e6:.1f} mg/m3 "
        f"(mass fraction {soot_mass_fraction():.3E})"
    )
    print(f"  expected speed factor {factor:.4f}")
    print(f"  clear walk            {length / V0:.1f} s")
    print(
        f"  smoky walk            {length / (V0 * factor):.1f} s  "
        f"(ratio {1 / factor:.4f})"
    )
    print(f"  deck runs to          {end_time_s():.0f} s")
    return walkable


if __name__ == "__main__":
    build()
