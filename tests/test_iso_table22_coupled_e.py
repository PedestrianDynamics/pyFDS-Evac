"""ISO 20414 Table 22, case e: HCN, NO2 and the CO2 factor on every term (#257).

Cases a-d (``test_iso_table22_coupled.py``) cover CO, CO2 and O2. Case e puts
200 ppm HCN and 50 ppm NO2 in a room with 2 % CO2, 21 % O2 and no CO, so the
dose is the sum of

    r_CN  = (exp(C_CN / 43) - 1) / 220,   C_CN = C_HCN - (C_NO + C_NO2)
    r_NOx = (C_NO + C_NO2) / 1500
    r_irr = C_NO2 / 1900                  (FDS counts NO2 here as well)
    HV    = exp(0.1903 C_CO2 + 2.0004) / 7.1

    r = (r_CN + r_NOx + r_irr) HV                      [1/min]

all in the form of FDS 6.10.1 ``FED`` (Source/func.f90). The expected values
below are written out with literal constants and import nothing from
pyfds_evac: ISO's Step 2 is a hand calculation, and the expected value of a
test must not come from the code it checks.

The FDS ``FED`` device at the occupant (FDS 6.10.1, ``iso_table22_e.fds``) is
read from ``reference/iso_table22_e_fed_device.csv``: the rows of its
``_devc.csv`` between 190 s and 197 s, which bracket the crossing. The full
file (17 kB) is in the project data folder.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario, run_scenario

pytestmark = [
    pytest.mark.iso20414,
    pytest.mark.xdist_group("test_iso_table22_coupled_e"),
]

ASSET = Path("assets/iso_table22_coupled")

# Prescribed by the deck.
HCN_PPM = 200.0
NO2_PPM = 50.0
CO2_PERCENT = 2.0
O2_PERCENT = 21.0

DEVC_EXTRACT = ASSET / "reference" / "iso_table22_e_fed_device.csv"


def hand_rates() -> dict[str, float]:
    """Per-term FED rates in 1/min, FDS form, from the prescribed gas."""
    c_cn = HCN_PPM - NO2_PPM
    r_cn = (math.exp(c_cn / 43.0) - 1.0) / 220.0
    r_nox = NO2_PPM / 1500.0
    r_irr = NO2_PPM / 1900.0
    hv = math.exp(0.1903 * CO2_PERCENT + 2.0004) / 7.1
    return {
        "cn": r_cn,
        "nox": r_nox,
        "irr": r_irr,
        "hv": hv,
        "total": (r_cn + r_nox + r_irr) * hv,
    }


def hand_crossing_s() -> float:
    return 60.0 / hand_rates()["total"]


def fds_device_crossing_s() -> float:
    """Time at which FDS's FED device reaches 1, linear between rows.

    The first line of the file holds the units, the second the names.
    """
    with open(DEVC_EXTRACT, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    names = [name.strip() for name in rows[1]]
    column = names.index("FED_occupant")
    times = [float(row[0]) for row in rows[2:]]
    fed = [float(row[column]) for row in rows[2:]]
    assert fed[0] < 1.0 <= fed[-1], "the extract must bracket the crossing"
    return float(np.interp(1.0, fed, times))


@pytest.fixture(scope="module")
def case_e():
    scenario = load_scenario(str(ASSET / "config_e.json"))
    opts = SimpleNamespace(
        seed=420,
        fds_dir=str(ASSET / "fds" / "e"),
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
    result = run_scenario(scenario, **build_run_kwargs(scenario, opts))
    try:
        yield result
    finally:
        result.cleanup()


def test_the_hand_values_are_the_ones_in_the_documentation():
    rates = hand_rates()
    assert rates["cn"] == pytest.approx(0.144239, abs=5e-7)
    assert rates["nox"] == pytest.approx(0.033333, abs=5e-7)
    assert rates["irr"] == pytest.approx(0.026316, abs=5e-7)
    assert rates["hv"] == pytest.approx(1.523340, abs=5e-7)
    assert rates["total"] == pytest.approx(0.310591, abs=5e-7)
    assert hand_crossing_s() == pytest.approx(193.180, abs=5e-4)


def test_fds_own_fed_device_agrees_with_the_hand_calculation():
    """FDS integrates the gas it holds, which is not exactly the prescribed one.

    The slices show 199.9997 ppm HCN, 50.0011 ppm NO2 and 1.999994 % CO2 where
    the deck's mass fractions give 200.0002, 50.00002 and 1.999997; the offset
    comes from FDS's internal conversion (cause not established). It moves the
    rate by 1.8e-5 relative and the crossing by 0.0035 s.
    """
    assert abs(fds_device_crossing_s() - hand_crossing_s()) <= 0.01


def test_the_gas_arrives_at_the_occupant_unaltered(case_e):
    row = case_e.fed_history[0]
    assert float(row["hcn_ppm"]) == pytest.approx(HCN_PPM, rel=1e-4)
    assert float(row["no2_ppm"]) == pytest.approx(NO2_PPM, rel=1e-4)
    assert float(row["co2_percent"]) == pytest.approx(CO2_PERCENT, abs=2e-3)
    assert float(row["o2_percent"]) == pytest.approx(O2_PERCENT, abs=2e-2)
    # Species the deck does not contain must read exactly zero.
    assert float(row["co_percent"]) == 0.0
    assert float(row["no_ppm"]) == 0.0


def test_each_term_matches_the_hand_calculation(case_e):
    row = case_e.fed_history[0]
    hand = hand_rates()
    assert float(row["cn_rate_per_min"]) == pytest.approx(hand["cn"], rel=1e-4)
    assert float(row["nox_rate_per_min"]) == pytest.approx(hand["nox"], rel=1e-4)
    assert float(row["fld_rate_per_min"]) == pytest.approx(hand["irr"], rel=1e-4)
    assert float(row["hv_co2"]) == pytest.approx(hand["hv"], rel=1e-4)
    assert float(row["co_rate_per_min"]) == 0.0
    assert float(row["o2_rate_per_min"]) == 0.0
    assert float(row["fed_rate_per_min"]) == pytest.approx(hand["total"], rel=1e-4)


def test_the_crossing_is_the_first_update_at_or_after_the_hand_time(case_e):
    """t* <= t < t* + interval, with the history spaced at the FED interval."""
    history = case_e.fed_history
    times = [float(row["time_s"]) for row in history]
    interval = max(round(b - a, 6) for a, b in zip(times, times[1:]))
    crossing = next(
        float(row["time_s"]) for row in history if float(row["fed_cumulative"]) >= 1.0
    )
    t_star = hand_crossing_s()
    assert t_star <= crossing < t_star + interval, (
        f"crossed at {crossing} s, hand calculation {t_star:.3f} s, "
        f"interval {interval} s"
    )


def test_the_occupant_stays_put_and_is_incapacitated(case_e):
    history = case_e.fed_history
    assert (
        len({(round(float(r["x"]), 3), round(float(r["y"]), 3)) for r in history}) == 1
    )
    assert case_e.metrics["agents_remaining"] == 1
    assert case_e.metrics["all_evacuated"] is False
    assert case_e.metrics["fed_max"] >= 1.0


def test_gas_incapacitation_starts_at_the_crossing(case_e):
    """Premovement already holds the occupant, so only this checks the stop."""
    history = case_e.fed_history
    crossed = next(
        i for i, r in enumerate(history) if float(r["fed_cumulative"]) >= 1.0
    )
    stopped = next((i for i, r in enumerate(history) if r["incapacitated"]), None)
    assert stopped == crossed, "incapacitation must start in the crossing row"
    t_star = hand_crossing_s()
    t_stop = float(history[stopped]["time_s"])
    assert t_star <= t_stop < t_star + 1.0
    assert history[stopped]["incapacitation_cause"] == "gas"
    assert all(not r["incapacitated"] for r in history[:stopped])
    for row in history[stopped:]:
        assert row["incapacitated"]
        assert float(row["desired_speed"]) == 0.0
        assert float(row["base_speed"]) == 0.0
    assert float(history[0]["base_speed"]) > 0.0
