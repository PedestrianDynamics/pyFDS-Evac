"""Tier A verification against two FDS+Evac guide component tests.

Source: T. Korhonen, *FDS+Evac Technical Reference and User's Guide*
(FDS 6.7.6, Evac 2.6.0), section "Component Testing", the quantitative
cases "Unimpeded walking speed vs smoke density" (figure
``Fig_SmokeSpeedTest``) and "FED calculation" (figure ``Fig_FED_Test``).
The FDS+Evac code is cited at git tag ``FDS6.7.6``: ``Source/evac.f90``
and ``Source/func.f90`` (function ``FED``).

No value is copied from the guide.  Every reference is rebuilt here from
the equations with ``math`` only, so the tests check pyFDS-Evac against an
independent computation.  No FDS run and no FDS data are needed.

Smoke vs speed (evac.f90 :8506-8537, defaults :1544-1545, :2153-2161,
:5501-5505)::

    K = 8700 m2/kg * rho_s [mg/m3] * 1e-6
    v = v0 * max(0.1, 1 + (-0.057 / 0.706) * K)

FED (func.f90 ``FED``, light work, called from evac.f90
``GET_FIRE_CONDITIONS``), t in minutes, gases as volume fractions::

    rate = 2.7641667e-5 * CO[ppm]**1.036 * HV + O2_term
    HV   = exp(0.1903 * CO2[%] + 2.0004) / 7.1   if CO2 > 0, else 1
    O2   = 1 / exp(8.13 - 0.54 * (20.9 - O2[%]))  if O2 < 20 %, else 0

pyFDS-Evac uses the CO coefficient 2.764e-5 (rel. 6.0e-5 below FDS), so
the comparison with the FDS form uses rel 1e-4; the comparison with the
same coefficient uses rel 1e-9.
"""

import math

import pytest

from pyfds_evac.core.fed import (
    DefaultFedInputs,
    accumulate_default_fed,
    default_fed_components,
    default_fed_rate_per_minute,
)
from pyfds_evac.core.smoke_speed import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    extinction_from_soot_density,
    speed_factor_from_extinction,
    speed_from_soot_density,
)

# --- Independent references (literals, not module internals) ---------------

V0 = 1.5  # m/s, guide test agent speed
K_M = 8700.0  # m2/kg, FDS default soot mass extinction (evac.f90 :5504)
ALPHA = 0.706  # m/s (evac.f90 :1544)
BETA = -0.057  # m2/s (evac.f90 :1545)
F_MIN = 0.1  # SMOKE_MIN_SPEED_FACTOR default (evac.f90 :2154)
CROSS_M = 5.0  # timed stretch, x = 5 m to 10 m

CO_COEF_FDS = 2.7641667e-5  # func.f90 FED, CO_FED_FAC for activity 2
CO_COEF_PYFDS = 2.764e-5  # pyFDS-Evac value (rounded)
T_END_S = 100.0  # guide FED test duration

# Guide densities [mg/m3].  The FDS run holds 0.997 of nominal: the decks set
# the soot mass fraction from an air density of 1.1984 kg/m3, while FDS's own
# gas density is about 1.1949 kg/m3.  The 1000 mg/m3 deck's device output
# records 9.97e-4 kg/m3, K = 8.68 1/m.  498.5 and 1495.5 are 0.997 * nominal.
NOMINAL_DENSITIES = (0.0, 500.0, 1000.0, 1500.0)
FDS_ACTUAL_DENSITIES = (498.5, 997.0, 1495.5)

# Guide FED cases: (CO2 %, CO ppm, O2 %).
FED_CASES = {
    "all": (2.0, 1000.0, 15.0),
    "o2": (0.0, 0.0, 12.0),
    "co": (0.0, 1000.0, 21.0),
    "co2": (3.43, 1000.0, 21.0),
}


def _ref_speed(rho_mg_per_m3: float) -> float:
    k = K_M * rho_mg_per_m3 * 1.0e-6
    return V0 * max(F_MIN, 1.0 + (BETA / ALPHA) * k)


def _ref_hv(co2_percent: float) -> float:
    if co2_percent <= 0.0:
        return 1.0
    return math.exp(0.1903 * co2_percent + 2.0004) / 7.1


def _ref_co_rate(co_ppm: float, coef: float) -> float:
    return coef * co_ppm**1.036


def _ref_o2_rate(o2_percent: float) -> float:
    if o2_percent >= 20.0:
        return 0.0
    return 1.0 / math.exp(8.13 - 0.54 * (20.9 - o2_percent))


def _ref_fed(co2: float, co_ppm: float, o2: float, coef: float) -> float:
    rate = _ref_co_rate(co_ppm, coef) * _ref_hv(co2) + _ref_o2_rate(o2)
    return rate * T_END_S / 60.0


def _inputs(co2: float, co_ppm: float, o2: float) -> DefaultFedInputs:
    return DefaultFedInputs(
        co_volume_fraction_percent=co_ppm / 1.0e4,
        co2_volume_fraction_percent=co2,
        o2_volume_fraction_percent=o2,
    )


# --- Smoke vs speed ----------------------------------------------------------


@pytest.mark.parametrize("rho", NOMINAL_DENSITIES + FDS_ACTUAL_DENSITIES)
def test_guide_smoke_speed_matches_closed_form(rho):
    """Guide "walking speed vs smoke density": v(rho_s) equals the FDS+Evac law.

    Re-derived from evac.f90 :8522-8523 and :8537, not read off the figure.
    """
    expected = _ref_speed(rho)
    got = speed_from_soot_density(V0, rho)
    assert got == pytest.approx(expected, rel=1e-9)
    assert CROSS_M / got == pytest.approx(CROSS_M / expected, rel=1e-9)


def test_guide_smoke_speed_table_values():
    """Speeds and 5 m crossing times at the precision of the task record table."""
    table = {
        0.0: (1.500, 3.333),
        500.0: (0.9732, 5.138),
        1000.0: (0.4464, 11.201),
        1500.0: (0.150, 33.333),
        498.5: (0.9748, 5.129),
        997.0: (0.4495, 11.122),
        1495.5: (0.150, 33.333),
    }
    for rho, (v_ref, t_ref) in table.items():
        v = speed_from_soot_density(V0, rho)
        assert v == pytest.approx(v_ref, abs=5e-5), rho
        assert CROSS_M / v == pytest.approx(t_ref, abs=5e-4), rho


def test_guide_smoke_speed_figure_read_off():
    """Visual read-off of the guide figure markers (abs 0.02 m/s).

    Documentation only, not a regression target.  The 997 mg/m3 density
    comes from the deck's device output (9.97e-4 kg/m3), not from this
    read-off: the 0.003 m/s gap between 997 and 1000 mg/m3 is below the
    0.02 m/s read-off resolution.
    """
    figure = {0.0: 1.50, 498.5: 0.98, 997.0: 0.45, 1495.5: 0.15}
    for rho, v_fig in figure.items():
        assert speed_from_soot_density(V0, rho) == pytest.approx(v_fig, abs=0.02)


def test_guide_smoke_speed_floor_onset():
    """The 0.1 floor starts at K = 0.9 * alpha / |beta| = 11.15 1/m (1281 mg/m3)."""
    k_floor = (1.0 - F_MIN) * ALPHA / -BETA
    rho_floor = k_floor / (K_M * 1.0e-6)
    assert k_floor == pytest.approx(11.147, abs=1e-3)
    assert rho_floor == pytest.approx(1281.3, abs=0.1)
    assert extinction_from_soot_density(rho_floor) == pytest.approx(k_floor, rel=1e-9)
    assert speed_factor_from_extinction(k_floor) == pytest.approx(F_MIN, abs=1e-4)
    assert speed_factor_from_extinction(k_floor * (1.0 - 1e-6)) > F_MIN
    assert speed_factor_from_extinction(2.0 * k_floor) == F_MIN


@pytest.mark.parametrize("rho", NOMINAL_DENSITIES)
def test_guide_smoke_speed_default_config_is_fds_evac(rho):
    """Default SmokeSpeedConfig (lund) reproduces the FDS+Evac defaults."""
    k = K_M * rho * 1.0e-6
    model = SmokeSpeedModel(ConstantExtinctionField(k), SmokeSpeedConfig())
    assert model.speed_factor(0.0, 0.0, 0.0) == pytest.approx(
        _ref_speed(rho) / V0, rel=1e-9
    )


# --- FED -------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(FED_CASES))
def test_guide_fed_at_t_end(case):
    """Guide "FED calculation": FED(100 s) for the four gas mixtures.

    Same coefficient: rel 1e-9.  FDS func.f90 coefficient: rel 1e-4.
    """
    co2, co_ppm, o2 = FED_CASES[case]
    got = accumulate_default_fed(_inputs(co2, co_ppm, o2), duration_s=T_END_S)
    assert got == pytest.approx(_ref_fed(co2, co_ppm, o2, CO_COEF_PYFDS), rel=1e-9)
    assert got == pytest.approx(_ref_fed(co2, co_ppm, o2, CO_COEF_FDS), rel=1e-4)


def test_guide_fed_table_values():
    """FED(100 s) at the precision of the task record table (FDS form)."""
    table = {"all": 0.101870, "o2": 0.060014, "co": 0.059076, "co2": 0.118139}
    for case, fed_ref in table.items():
        co2, co_ppm, o2 = FED_CASES[case]
        got = accumulate_default_fed(_inputs(co2, co_ppm, o2), duration_s=T_END_S)
        assert got == pytest.approx(fed_ref, rel=1e-4), case


def test_guide_fed_o2_case_has_no_co_term():
    """O2 case (0, 0, 12): only hypoxia contributes."""
    comp = default_fed_components(_inputs(*FED_CASES["o2"]))
    assert comp.co_rate_per_min == 0.0
    assert comp.hv_co2 == 1.0
    assert comp.o2_rate_per_min == pytest.approx(_ref_o2_rate(12.0), rel=1e-9)


def test_guide_fed_co_case_has_no_hv_and_no_o2_term():
    """CO case (0, 1000, 21): HV = 1 with no CO2, and O2 above the gate."""
    comp = default_fed_components(_inputs(*FED_CASES["co"]))
    assert comp.hv_co2 == 1.0
    assert comp.o2_rate_per_min == 0.0
    assert comp.co_rate_per_min == pytest.approx(
        _ref_co_rate(1000.0, CO_COEF_PYFDS), rel=1e-9
    )


def test_guide_fed_co2_over_co_is_hv():
    """CO2 case / CO case = HV(3.43 %) = 1.9998: CO2 acts only through HV."""
    fed = {
        c: accumulate_default_fed(_inputs(*FED_CASES[c]), duration_s=T_END_S)
        for c in ("co", "co2")
    }
    ratio = fed["co2"] / fed["co"]
    assert ratio == pytest.approx(_ref_hv(3.43), rel=1e-9)
    assert ratio == pytest.approx(1.9998, rel=1e-4)


def test_guide_fed_all_is_co_times_hv_plus_o2():
    """All case (2, 1000, 15): HV multiplies the CO term only, not the O2 term."""
    comp = default_fed_components(_inputs(*FED_CASES["all"]))
    assert comp.hv_co2 == pytest.approx(_ref_hv(2.0), rel=1e-9)
    assert comp.hv_co2 == pytest.approx(1.5233, abs=1e-4)
    expected = _ref_co_rate(1000.0, CO_COEF_PYFDS) * _ref_hv(2.0) + _ref_o2_rate(15.0)
    assert comp.total_rate_per_min == pytest.approx(expected, rel=1e-9)
    assert default_fed_rate_per_minute(_inputs(*FED_CASES["all"])) == pytest.approx(
        expected, rel=1e-9
    )


def test_guide_fed_hv_steps_at_small_co2():
    """HV is 1 at zero CO2 and exp(2.0004)/7.1 = 1.041 for any CO2 > 0.

    func.f90 ``FED`` applies HV only when CO2 > 0.  With ~0.04 % ambient
    CO2 the guide's CO case gives FED(100 s) = 0.0620 rather than 0.0591,
    which is what the guide figure shows.
    """
    assert default_fed_components(_inputs(0.0, 1000.0, 21.0)).hv_co2 == 1.0
    tiny = default_fed_components(_inputs(1e-9, 1000.0, 21.0)).hv_co2
    assert tiny == pytest.approx(math.exp(2.0004) / 7.1, rel=1e-6)
    assert tiny == pytest.approx(1.0411, abs=1e-4)

    got = accumulate_default_fed(_inputs(0.04, 1000.0, 21.0), duration_s=T_END_S)
    assert got == pytest.approx(_ref_fed(0.04, 1000.0, 21.0, CO_COEF_PYFDS), rel=1e-9)
    assert got == pytest.approx(0.0620, rel=1e-3)


def test_guide_fed_o2_gate_at_20_percent():
    """func.f90 ``FED``: the O2 term applies only for X_O2 < 0.20."""
    assert default_fed_components(_inputs(0.0, 0.0, 20.0)).o2_rate_per_min == 0.0
    below = default_fed_components(_inputs(0.0, 0.0, 19.9)).o2_rate_per_min
    assert below > 0.0
    assert below == pytest.approx(_ref_o2_rate(19.9), rel=1e-9)
