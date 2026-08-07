#!/usr/bin/env python3
"""Generate the FIC-vs-FED tenability scenario.

FED and FIC are the two tenability rules, and they act on different
timescales.  This scenario separates them.

* **FED** is a *cumulative* dose with a threshold.  Below the threshold it does
  nothing at all -- it is a binary gate, not a speed penalty.
* **FIC** is an *instantaneous* irritant response.  It cuts walking speed from
  the first tick, and recovers the moment the agent leaves the gas.

The prediction, stated in advance so it can be falsified: on a short egress,
**FED alone changes nothing** because the dose never reaches the threshold,
while **FIC bites immediately**.  A model carrying only FED would therefore be
non-conservative for exactly this class of fire.

Layout: a 4 x 50 m sealed corridor, one exit at the north end, agents at the
south end, so every agent walks the full length through the gas.

Gas, prescribed rather than burned
    A single ``&INIT`` fills the corridor with a fixed mixture -- no combustion,
    no transient, no spatial gradient.  Concentration is therefore not a
    variable, which is what makes the three runs comparable.  The technique and
    its pitfall (a second ``&INIT`` without ``XB`` silently resets the whole
    domain) follow ``assets/fed_incap_co_*``.

    * **CO at 2000 ppm** drives FED.  The rate is
      ``2.764e-5 * 2000^1.036 ~ 0.067 /min``, so reaching FED = 1 takes about
      15 minutes -- far longer than this egress.  FED stays near 0.05 and the
      incapacitation gate never opens.  That is the point, not a limitation.
    * **Acrolein at 10 ppm** drives FIC.  Its incapacitating concentration is
      20 ppm, so ``FIC = 10/20 = 0.5`` and the speed factor is
      ``max(0.3, 1 - 0.7 * 0.5) = 0.65``.  Chosen deliberately off the 0.3
      floor: a saturated factor would hide any error in ``fic_alpha``.

The three runs differ only in the tenability rules, set from the command line:

    neither     run.py --disable-tenability
    FED only    run.py --fic-alpha 0        (incapacitation on, no speed penalty)
    FED + FIC   run.py                      (both, the default)

Expected: the first two are indistinguishable; the third is ~1/0.65 = 1.54x
slower.
"""

import json
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent

CORRIDOR = (0.0, 0.0, 4.0, 50.0)
SPAWN = (0.5, 1.0, 3.5, 5.0)
EXIT_BOX = (0.5, 48.5, 3.5, 49.5)

AGENT_RADIUS = 0.2
N_AGENTS = 30
V0 = 1.3

# Prescribed gas. See the module docstring for why these two values.
CO_PPM = 2000.0
ACROLEIN_PPM = 10.0
ACROLEIN_FIC_PPM = 20.0  # incapacitating concentration, Purser via Korhonen Table 2
FIC_ALPHA = 0.7
FIC_MIN_FACTOR = 0.3


def expected_fic() -> float:
    return ACROLEIN_PPM / ACROLEIN_FIC_PPM


def expected_speed_factor() -> float:
    return max(FIC_MIN_FACTOR, 1.0 - FIC_ALPHA * expected_fic())


def _coords(bounds):
    return [[round(x, 3), round(y, 3)] for x, y in box(*bounds).exterior.coords]


def build_config():
    return {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 400,
                    "dt": 0.05,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": 1301,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        # One exit, so routing cannot vary between runs and the only thing that
        # differs is walking speed.
        "routing": {
            "w_smoke": 0.0,
            "w_fed": 0.0,
            "w_queue": 0.0,
            "base_speed_m_per_s": V0,
            "default_exit_capacity": 1.3,
            "sampling_step_m": 2.0,
        },
        "exits": {
            "E_out": {
                "type": "polygon",
                "coordinates": _coords(EXIT_BOX),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
                "sign": {"x": 2.0, "y": 49.0, "alpha": 180, "c": 3},
            }
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": {
                    "number": N_AGENTS,
                    "radius": AGENT_RADIUS,
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
    """A sealed corridor with a prescribed, homogeneous irritant + CO mixture.

    Mass fractions are converted from the target volume fractions properly
    (``Y_i = X_i * M_i / M_mix``) rather than assumed equal to them; the molar
    masses differ enough from the nitrogen background to matter.
    """
    x0, y0, x1, y1 = CORRIDOR
    m = {  # molar masses, g/mol
        "N2": 28.013,
        "O2": 31.999,
        "CO": 28.010,
        "CO2": 44.009,
        "C3H4O": 56.064,  # acrolein
    }
    x_co = CO_PPM * 1e-6
    x_acr = ACROLEIN_PPM * 1e-6
    x_o2 = 0.209
    x_co2 = 500e-6
    x_n2 = 1.0 - x_co - x_acr - x_o2 - x_co2
    m_mix = (
        x_n2 * m["N2"]
        + x_o2 * m["O2"]
        + x_co * m["CO"]
        + x_co2 * m["CO2"]
        + x_acr * m["C3H4O"]
    )
    y_co = x_co * m["CO"] / m_mix
    y_co2 = x_co2 * m["CO2"] / m_mix
    y_o2 = x_o2 * m["O2"] / m_mix
    y_acr = x_acr * m["C3H4O"] / m_mix

    return f"""&HEAD CHID='fic_vs_fed_speed',
      TITLE='{x1 - x0:.0f}x{y1 - y0:.0f} m sealed corridor, homogeneous acrolein + CO' /

! Sealed corridor. No combustion: the gas is prescribed, so concentration is
! constant in space and time and the only variable across runs is which
! tenability rules are enabled.
&MESH IJK=16,200,12, XB={x0 - 0.25:.2f},{x1 + 0.25:.2f},{y0 - 0.25:.2f},{y1 + 0.25:.2f},0.0,3.0 /
&TIME T_END=400 /
&MISC TMPA=20.0 /

! Nitrogen background so O2 is not double-counted.
&SPEC ID='NITROGEN',        BACKGROUND=.TRUE. /
&SPEC ID='OXYGEN'                             /
&SPEC ID='CARBON MONOXIDE'                    /
&SPEC ID='CARBON DIOXIDE'                     /
&SPEC ID='ACROLEIN'                           /
! Declared only so the extinction slice below has a species to report on.
! With no combustion its mass fraction stays 0, so the air is optically clear
! and the scenario keeps gas concentration as its single variable.
&SPEC ID='SOOT'                               /

! Target volume fractions: CO = {CO_PPM:.0f} ppm (drives FED),
! acrolein = {ACROLEIN_PPM:.0f} ppm (drives FIC), O2 = 20.9 %, CO2 = 500 ppm.
!
! NOTE: all species MUST be in a single &INIT. A second &INIT with no XB
! resets the whole domain, overwriting the first and leaving everything at 0.
&INIT SPEC_ID(1)='CARBON MONOXIDE',
      SPEC_ID(2)='CARBON DIOXIDE',
      SPEC_ID(3)='OXYGEN',
      SPEC_ID(4)='ACROLEIN',
      MASS_FRACTION(1)={y_co:.5E},
      MASS_FRACTION(2)={y_co2:.5E},
      MASS_FRACTION(3)={y_o2:.5E},
      MASS_FRACTION(4)={y_acr:.5E} /

! Walls: the corridor is a sealed box.
&OBST XB={x0 - 0.25:.2f},{x1 + 0.25:.2f},{y0 - 0.25:.2f},{y0:.2f},0.0,3.0 /
&OBST XB={x0 - 0.25:.2f},{x1 + 0.25:.2f},{y1:.2f},{y1 + 0.25:.2f},0.0,3.0 /
&OBST XB={x0 - 0.25:.2f},{x0:.2f},{y0:.2f},{y1:.2f},0.0,3.0 /
&OBST XB={x1:.2f},{x1 + 0.25:.2f},{y0:.2f},{y1:.2f},0.0,3.0 /

! Slices pyFDS-Evac reads at breathing height.
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE'  /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN'          /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='ACROLEIN'        /
! SPEC_ID is required once species are declared explicitly: FDS will not
! assume soot (ERROR 1004). Decks generated by wkt_to_fds use simple chemistry,
! where soot is implicit and the bare quantity is accepted -- which is why this
! hand-written deck is the only one that hit this.
&SLCF PBZ=2.0, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT'     /
&DUMP DT_SLCF=5.0 /

&TAIL /
"""


def build():
    walkable = box(*CORRIDOR)
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")
    (HERE / "fic_vs_fed_speed.fds").write_text(build_deck(), encoding="utf-8")
    with open(HERE / "config.json", "w", encoding="utf-8") as f:
        json.dump(build_config(), f, indent=2)

    spawn_area = box(*SPAWN).area
    capacity = spawn_area / (2 * AGENT_RADIUS) ** 2
    if N_AGENTS > 0.9 * capacity:
        raise SystemExit(f"{N_AGENTS} agents exceeds the ~{capacity:.0f} that fit")

    factor = expected_speed_factor()
    if factor <= FIC_MIN_FACTOR + 1e-9:
        raise SystemExit(
            f"the FIC speed factor is pinned at its {FIC_MIN_FACTOR} floor, which "
            "would hide any error in fic_alpha; lower the acrolein concentration"
        )
    if factor >= 0.95:
        raise SystemExit(
            f"the FIC speed factor is {factor:.2f}, too close to 1 to measure "
            "against run-to-run variation; raise the acrolein concentration"
        )

    walk_m = EXIT_BOX[1] - SPAWN[3]
    print("Wrote geometry.wkt, config.json and fic_vs_fed_speed.fds")
    print(f"  {N_AGENTS} agents walk ~{walk_m:.0f} m at v0={V0} m/s")
    print(f"  FIC = {expected_fic():.2f} -> speed factor {factor:.2f}")
    print(
        f"  expected egress ~{walk_m / V0:.0f} s clear, ~{walk_m / (V0 * factor):.0f} s with FIC"
    )
    return walkable


if __name__ == "__main__":
    build()
