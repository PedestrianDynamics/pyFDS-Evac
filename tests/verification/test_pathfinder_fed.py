"""Pathfinder's two FED verification cases (#208).

Pathfinder 2025-1 verifies its FED with two cases (V&V > Special features >
FED): a moving occupant through three prescribed gas mixtures and a stationary
occupant in an FDS fire. This module reproduces both with pyFDS-Evac's own FED
rate functions, at three levels.

Facts taken from Pathfinder's page (not from this repository):

- Three INIT regions separated by thin walls hold 100 %, 75 % and 50 %
  combustion products by mass, the rest air (Table 1, mass fractions,
  combustion products / air: CO2 0.010000 / 0.000592, CO 0.001000 / 0.000000,
  N2 0.839000 / 0.763018, O2 0.150000 / 0.231164, H2O 0.000000 / 0.005226).
  The occupant starts on the left at 0.25 m/s; the distance to the exit is
  30 m. Hand calculation FED 0.07896, Pathfinder 0.07745 (1.9 %).
- The region lengths appear only in a figure. Three equal 10 m regions are
  an inference; they reproduce 0.07896. The sensitivity to the split is
  pinned below.
- The page does not state how mass fractions become volume fractions. Ideal
  gas mole fractions are used here (volume fraction = mole fraction).
- Stationary case: an FDS fire with gas devices and an FDS ``FED`` device at
  1.6459 m; FDS 0.0467, Pathfinder 0.0455 (3 %), attributed to the 0.5 s
  PLOT3D output interval. The FDS files are not published, so the stationary
  case here is this repository's own deck. No numeric tolerance is stated for
  either case.

**Tier A** (equation level): FED = sum of the rate over the three regions at
10 m / 0.25 m/s = 40 s each, expected 0.07896 within 1e-4.

**Behavioural** (through ``run_scenario``): one agent at 0.25 m/s across a
30 m corridor in a synthetic three-region gas field. Predeclared, before the
first run: the expected value is the Tier A dose, and the tolerance is one FED
update's dose at the highest-rate region, ``update_interval * R1 / 60``
(R1 = 0.0594 1/min, so 9.9e-4 for the 1 s update) plus 1e-5. The run loop adds
``rate(x at t_k) * (t_k - t_{k-1})`` at each update, a right-endpoint rule
that stops at the last update before the agent leaves. For a rate that falls
with distance this under-counts by at most one tick at each region boundary
and the part of the last interval after the last update, which sum to at
most ``dt * R1 / 60``.

**Stationary, coupled** (``external_data``): ``fds-evac-data/pathfinder_fed_
stationary`` (FDS 6.10.1, ``assets/pathfinder_fed_stationary``), one agent
held still next to the FDS ``FED`` device. Predeclared, before the first FDS
run: pyFDS-Evac cumulative FED against the FDS ``FED`` device at the same
time, relative difference <= 5 % at the last update before 120 s (119 s) and
<= 10 % at 60 and 90 s, with the FDS dose at 120 s at least 0.05 so the
comparison is not vacuous (the first deck, 100 kW, reached 0.0446 and was
replaced by this 200 kW one before any comparison). The gas it
reads back (CO and CO2 volume percent) against the FDS gas devices <= 5 % at
60, 90 and 119 s. Justification: Pathfinder's own difference is 3 %, from a
0.5 s output interval; here the slice interval is also 0.5 s and the update
is 1 s, a right-endpoint rule that overstates a rising dose by about
``p * dt / (2 t)`` for a dose growing as ``t**p``, at most 2.5 % at 120 s for
p = 3 and 5 % at 60 s; the slice is read at the nearest node and the device
in the cell around the point (0.1 m cells), and the agent sits within 0.11 m
of the device. A miss is a finding: the tolerance is not changed to pass.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from harness import (
    CorridorSpec,
    corridor_scenario,
    deterministic_tenability,
    make_fed_model,
)

from pyfds_evac.core.fed import DefaultFedInputs, default_fed_components

REPO = Path(__file__).resolve().parents[2]
ASSET = REPO / "assets" / "pathfinder_fed_stationary"
SCIEBO = next(Path.home().glob("sciebo*/fds-evac-data"), Path("absent"))
DATA = Path(os.environ.get("PATHFINDER_FED_DATA", SCIEBO / "pathfinder_fed_stationary"))

# Pathfinder Table 1, mass fractions.
COMBUSTION_PRODUCTS = {
    "CO2": 0.010000,
    "CO": 0.001000,
    "N2": 0.839000,
    "O2": 0.150000,
    "H2O": 0.000000,
}
AIR = {
    "CO2": 0.000592,
    "CO": 0.000000,
    "N2": 0.763018,
    "O2": 0.231164,
    "H2O": 0.005226,
}
# Molar masses [g/mol] from the standard atomic weights C 12.0107, O 15.9994,
# N 14.0067, H 1.00794 (not stated on Pathfinder's page).
MOLAR_MASS = {
    "CO2": 44.0095,
    "CO": 28.0101,
    "N2": 28.0134,
    "O2": 31.9988,
    "H2O": 18.01528,
}
FRACTIONS = (1.00, 0.75, 0.50)  # combustion products by mass
SPEED_M_S = 0.25
HAND_FED = 0.07896  # Pathfinder's hand calculation
PATHFINDER_FED = 0.07745
TIER_A_TOL = 1e-4

# Hand numbers of the mass-to-volume conversion, volume percent, per region.
VOLUME_PERCENT = {
    1.00: {"CO2": 0.65106, "CO": 0.10229, "O2": 13.4315},
    0.75: {"CO2": 0.49841, "CO": 0.07680, "O2": 15.2632},
    0.50: {"CO2": 0.34547, "CO": 0.05125, "O2": 17.0985},
}


def volume_percent(combustion_fraction: float) -> dict[str, float]:
    """Ideal-gas volume percent of the mixture of Table 1 at a mass share."""
    mass = {
        gas: combustion_fraction * COMBUSTION_PRODUCTS[gas]
        + (1.0 - combustion_fraction) * AIR[gas]
        for gas in MOLAR_MASS
    }
    moles = {gas: mass[gas] / MOLAR_MASS[gas] for gas in MOLAR_MASS}
    total = sum(moles.values())
    return {gas: 100.0 * moles[gas] / total for gas in MOLAR_MASS}


def inputs_of(combustion_fraction: float) -> DefaultFedInputs:
    v = volume_percent(combustion_fraction)
    return DefaultFedInputs(
        co_volume_fraction_percent=v["CO"],
        co2_volume_fraction_percent=v["CO2"],
        o2_volume_fraction_percent=v["O2"],
    )


def rate_per_min(combustion_fraction: float, **kwargs) -> float:
    return default_fed_components(
        inputs_of(combustion_fraction), **kwargs
    ).total_rate_per_min


def fed_over(lengths_m, **kwargs) -> float:
    """Dose of an occupant at 0.25 m/s through the three regions in turn."""
    return sum(
        rate_per_min(f, **kwargs) * (length / SPEED_M_S) / 60.0
        for f, length in zip(FRACTIONS, lengths_m, strict=True)
    )


# --- Tier A ---------------------------------------------------------------


def test_table_1_mass_fractions_sum_to_one():
    assert sum(COMBUSTION_PRODUCTS.values()) == pytest.approx(1.0, abs=1e-6)
    assert sum(AIR.values()) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("fraction", FRACTIONS)
def test_mass_to_volume_conversion_hand_numbers(fraction):
    got = volume_percent(fraction)
    assert sum(got.values()) == pytest.approx(100.0, abs=1e-9)
    for gas, expected in VOLUME_PERCENT[fraction].items():
        assert got[gas] == pytest.approx(expected, abs=1e-4), (fraction, gas)


def test_moving_occupant_fed_matches_pathfinder_hand_calculation():
    """Three equal 10 m regions (inferred) at 0.25 m/s: 40 s each."""
    assert fed_over((10.0, 10.0, 10.0)) == pytest.approx(HAND_FED, abs=TIER_A_TOL)
    # Pathfinder's own result is 1.9 % below its hand calculation.
    assert abs(PATHFINDER_FED / HAND_FED - 1.0) == pytest.approx(0.019, abs=1e-3)


def test_o2_term_is_active_in_all_three_regions():
    """O2 is below the 20 % gate (and Pathfinder's 19.5 %) everywhere.

    13.4, 15.3 and 17.1 % O2: the hypoxia term is on in every region, not
    inactive. It is 0.0167 of the 0.0790 dose; without it the hand value is
    missed by 0.0167, so Pathfinder's 0.07896 includes it.
    """
    for fraction in FRACTIONS:
        o2 = volume_percent(fraction)["O2"]
        assert o2 < 19.5 < 20.0
        components = default_fed_components(inputs_of(fraction))
        assert components.o2_rate_per_min > 0.0
    lengths = (10.0, 10.0, 10.0)
    assert fed_over(lengths, o2_threshold_percent=19.5) == pytest.approx(
        fed_over(lengths), abs=1e-12
    )
    without_o2 = fed_over(lengths, o2_threshold_percent=0.0)
    assert without_o2 == pytest.approx(0.06226, abs=1e-4)
    assert abs(without_o2 - HAND_FED) > 10 * TIER_A_TOL


def test_dose_terms_at_100_percent_products():
    """The 100 % region by term: CO, the CO2 factor and O2, hand numbers."""
    c = default_fed_components(inputs_of(1.00))
    assert c.co_rate_per_min == pytest.approx(0.036287, abs=1e-6)
    assert c.hv_co2 == pytest.approx(1.178452, abs=1e-6)
    assert c.o2_rate_per_min == pytest.approx(0.016622, abs=1e-6)


@pytest.mark.parametrize(
    "lengths, expected",
    [
        ((9.0, 10.0, 11.0), 0.07647),
        ((10.0, 9.0, 11.0), 0.07796),
        ((11.0, 10.0, 9.0), 0.08145),
    ],
)
def test_sensitivity_to_the_unpublished_region_lengths(lengths, expected):
    """A 1 m shift between regions moves the FED by 1.3 to 3.2 %.

    The inferred 10/10/10 split is the one that reproduces 0.07896. 9/10/11
    gives 3.2 % less, 11/10/9 3.2 % more, 10/9/11 1.3 % less; Pathfinder's own
    0.07745 (1.9 % below its hand value) lies within that range, but the
    split cannot be recovered from it.
    """
    assert sum(lengths) == 30.0
    assert fed_over(lengths) == pytest.approx(expected, abs=1e-4)


# --- Behavioural, through the run loop -----------------------------------

UPDATE_INTERVAL_S = 1.0


class ThreeRegionField:
    """Gas volume fractions in three 10 m regions from the first sampled x.

    The first x the run samples is the centre of the spawn polygon (1.2 m);
    the agent starts within 0.2 m of it. The region edges sit at 10 m and
    20 m from that origin, the exit edge 30 m on.
    """

    def __init__(self):
        self.origin: float | None = None
        self._mix = [volume_percent(f) for f in FRACTIONS]

    def _region(self, x: float) -> dict[str, float]:
        if self.origin is None:
            self.origin = x
        index = min(2, max(0, int((x - self.origin) // 10.0)))
        return self._mix[index]

    def co(self, t, x, y):
        return self._region(x)["CO"] / 100.0

    def co2(self, t, x, y):
        return self._region(x)["CO2"] / 100.0

    def o2(self, t, x, y):
        return self._region(x)["O2"] / 100.0


def test_agent_walking_through_three_regions_accumulates_the_hand_dose():
    """One agent at 0.25 m/s over 30 m: the harness dose is the hand dose.

    Predeclared tolerance (see the module docstring): one update's dose at
    the highest-rate region, dt * R1 / 60 + 1e-5.
    """
    from pyfds_evac.core.scenario import run_scenario

    field = ThreeRegionField()
    model = make_fed_model(
        co_volume_fraction=field.co,
        co2_volume_fraction=field.co2,
        o2_volume_fraction=field.o2,
        update_interval_s=UPDATE_INTERVAL_S,
    )
    spec = CorridorSpec(
        length_m=32.0,
        width_m=2.0,
        num_agents=1,
        v0=SPEED_M_S,
        seed=1,
        max_simulation_time=400.0,
    )
    scenario = corridor_scenario(spec)
    # A narrow spawn and an exit whose near edge is 30 m on from it.
    scenario.raw["distributions"]["spawn_near"]["coordinates"] = [
        [1.0, 0.5],
        [1.4, 0.5],
        [1.4, 1.5],
        [1.0, 1.5],
        [1.0, 0.5],
    ]
    scenario.raw["exits"]["exit_far"]["coordinates"] = [
        [31.2, 0.5],
        [32.0, 0.5],
        [32.0, 1.5],
        [31.2, 1.5],
        [31.2, 0.5],
    ]
    result = run_scenario(
        scenario,
        seed=spec.seed,
        fed_model=model,
        tenability_config=deterministic_tenability(),
    )
    try:
        rows = result.fed_history
        assert result.metrics["agents_evacuated"] == 1
        walked = 31.2 - field.origin
        assert walked == pytest.approx(30.0, abs=0.25)
        # The regions are 10 m from the agent's start; the exit edge is
        # 31.2 m, so the agent walks 31.2 - origin metres (<= 30.2 m).
        speeds = [
            (b["x"] - a["x"]) / (b["time_s"] - a["time_s"])
            for a, b in zip(rows, rows[1:], strict=False)
        ]
        assert max(abs(v - SPEED_M_S) for v in speeds[2:-2]) < 5e-3
        got = rows[-1]["fed_cumulative"]
        r1 = rate_per_min(1.0)
        bound = UPDATE_INTERVAL_S * r1 / 60.0 + 1e-5
        expected = fed_over((10.0, 10.0, 10.0))
        assert abs(got - expected) <= bound, (got, expected, bound)
        # One-sided: a right-endpoint rule on a falling rate under-counts.
        assert got <= expected + 1e-9
    finally:
        result.cleanup()


# --- Stationary occupant, coupled to FDS ----------------------------------

# Relative bands on the FED at the update nearest each time; "end" is the
# last update, at or before 120 s.
FED_T_TOL = {60.0: 0.10, 90.0: 0.10, "end": 0.05}
GAS_TOL = 0.05
GAS_TIMES_S = (60.0, 90.0, 119.0)
MIN_FDS_FED = 0.05


def read_devc(path: Path) -> dict[str, list[float]]:
    """FDS ``_devc.csv`` (units row, then names) as columns."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    names = rows[1]
    columns = list(zip(*rows[2:], strict=True))
    return {n: [float(v) for v in c] for n, c in zip(names, columns, strict=True)}


def devc_at(dev: dict[str, list[float]], name: str, t_s: float) -> float:
    times = dev["Time"]
    for i in range(1, len(times)):
        if times[i] >= t_s - 1e-9:
            w = (t_s - times[i - 1]) / (times[i] - times[i - 1])
            return dev[name][i - 1] + w * (dev[name][i] - dev[name][i - 1])
    raise ValueError(f"t={t_s} s is past the device record ({times[-1]} s)")


def run_stationary(fds_dir: Path):
    from pyfds_evac.core.run_config import build_run_kwargs
    from pyfds_evac.core.scenario import load_scenario, run_scenario

    scenario = load_scenario(str(ASSET / "config.json"))
    opts = SimpleNamespace(
        seed=42,
        fds_dir=str(fds_dir),
        constant_extinction=None,
        smoke_update_interval=1.0,
        smoke_slice_height=1.6,
        disable_tenability=False,
        fed_threshold=1.0,
        enable_rerouting=False,
        reroute_interval=1.0,
        vis_cache=None,
        incapacitation_mode="deterministic",
        susceptibility_sigma=0.0,
    )
    return run_scenario(scenario, **build_run_kwargs(scenario, opts))


@pytest.mark.external_data
@pytest.mark.skipif(not DATA.is_dir(), reason="FDS output not found: pathfinder_fed")
def test_stationary_occupant_against_the_fds_fed_device(fds_read_only):
    result = run_stationary(fds_read_only(DATA))
    try:
        rows = {float(r["time_s"]): r for r in result.fed_history}
        dev = read_devc(next(DATA.glob("*_devc.csv")))
        fds_end = devc_at(dev, "FED_occupant", 120.0)
        assert fds_end >= MIN_FDS_FED, fds_end
        for t_s, tol in FED_T_TOL.items():
            t_row = max(rows) if t_s == "end" else t_s
            fds = devc_at(dev, "FED_occupant", t_row)
            assert rows[t_row]["fed_cumulative"] == pytest.approx(fds, rel=tol), t_s
        for t_s in GAS_TIMES_S:
            row = rows[t_s]
            for name, col in (("CO", "co_percent"), ("CO2", "co2_percent")):
                fds = 100.0 * devc_at(dev, f"{name}_occupant", t_s)
                assert row[col] == pytest.approx(fds, rel=GAS_TOL), (t_s, name)
    finally:
        result.cleanup()
