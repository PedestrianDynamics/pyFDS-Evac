"""L2 reference for the total-flux heat dose: walking past a flame.

Spec 016 (Verification, L2) and #219: an agent walks at 1 m/s in a straight
line past a small flame at 1000 C, closest approach 0.5 m, dose updated every
1 s. The heat model has no flame term: a flame's flux enters only through the
INTEGRATED INTENSITY source (#221). These tests call no pyFDS-Evac code. They
fix the expected values a flame term must
reproduce, computed two independent ways (a time-step sum and a closed-form
integral), and show how much a 1 s update changes the result.

Sourced (SFPE Handbook 5th ed., Ch. 63, pp. 2382-2384):

- dose per Eq. 63.43, t = D / q**1.33 min, summed per Eq. 63.48;
- the fatal endpoint (third-degree burns) for heat FED = 1, the
  maintainer's choice (spec 016); D = 16.7 (kW/m2)^4/3 min as printed on
  p. 2382 (r range) and p. 2384 (D values for Eq. 63.49). Purser's
  spreadsheet uses 16.667; the code follows the Handbook;
- sigma = 5.67e-8 W m^-2 K^-4, as printed with Eq. 63.49.

Assumptions (not sourced; each is a named argument below):

- the flame is a black-body sphere (emissivity 1) of radius 0.1 m;
- the exposed skin faces the flame centre, so the view factor of the sphere
  is (R / r)**2 at distance r >= R;
- skin surface at 35 C, the draft's value (spec 016, open question 2);
- the air at the head is at skin temperature, so there is no convective term;
- the reference values below take no 2.5 kW/m2 threshold; the code
  follows ISO 13571:2012 §8.2, §8.4 (maintainer decision) and counts the
  radiant flux as zero below 2.5 kW/m2, whose values are in
  ``test_iso_threshold_one_second_updates``.

Eq. 63.48 holds only while exposure is steady or rising; past the closest
approach it falls, so this is a reference for the summing, not a claim that
the Handbook validates the dose of a passing agent.

Reference values (FED, D = 16.7, path -10 m to +10 m):

- continuum, closed form: 0.011982;
- 1 s updates, one of them at the closest approach: 0.014052 (+17 %);
- 1 s updates, closest approach half-way between two: 0.010038 (-16 %).
"""

import math

import pytest

SIGMA = 5.67e-8  # W m^-2 K^-4
EXPONENT = 1.33  # Eq. 63.43
D_FATAL = 16.7  # (kW/m2)^4/3 min, SFPE Ch. 63 pp. 2382 and 2384

SPEED_M_S = 1.0
FLAME_TEMPERATURE_C = 1000.0
CLOSEST_APPROACH_M = 0.5
UPDATE_INTERVAL_S = 1.0
HALF_PATH_M = 10.0

# Assumptions, see the module docstring.
FLAME_RADIUS_M = 0.1
SKIN_TEMPERATURE_C = 35.0


def _surface_flux_kw_m2(
    flame_temperature_c: float = FLAME_TEMPERATURE_C,
    skin_temperature_c: float = SKIN_TEMPERATURE_C,
) -> float:
    """Return the net black-body flux at the flame surface, kW/m2."""
    t_f = flame_temperature_c + 273.15
    t_s = skin_temperature_c + 273.15
    return SIGMA * (t_f**4 - t_s**4) / 1000.0


def _flux_at_kw_m2(x_m: float, flame_radius_m: float = FLAME_RADIUS_M) -> float:
    """Return the flux on skin facing the flame, at path position x."""
    r_squared = CLOSEST_APPROACH_M**2 + x_m**2
    return _surface_flux_kw_m2() * flame_radius_m**2 / r_squared


def _step_sum_fed(step_s: float, phase: float) -> float:
    """Sum Eq. 63.48 over updates at t = (k + phase) * step_s, |x| <= L.

    t = 0 is the closest approach; ``phase`` in [0, 1) shifts the updates.
    """
    n = int(HALF_PATH_M / (SPEED_M_S * step_s)) + 1
    total = 0.0
    for k in range(-n, n + 1):
        x = (k + phase) * step_s * SPEED_M_S
        if abs(x) > HALF_PATH_M:
            continue
        rate_per_min = _flux_at_kw_m2(x) ** EXPONENT / D_FATAL
        total += rate_per_min * step_s / 60.0
    return total


def _prefactor_per_min() -> float:
    """Return (q0 R^2)^a / D, the rate is this times (d^2 + x^2)^-a."""
    return (_surface_flux_kw_m2() * FLAME_RADIUS_M**2) ** EXPONENT / D_FATAL


def _continuum_fed_infinite_path() -> float:
    """Closed form of the integral over an infinite straight path.

    int (d^2 + x^2)^-a dx = d^(1 - 2a) sqrt(pi) Gamma(a - 1/2) / Gamma(a),
    and dt = dx / v, so FED = prefactor / (60 v) times that.
    """
    a = EXPONENT
    d = CLOSEST_APPROACH_M
    integral = d ** (1 - 2 * a) * math.sqrt(math.pi) * math.gamma(a - 0.5)
    integral /= math.gamma(a)
    return _prefactor_per_min() / (60.0 * SPEED_M_S) * integral


def _tail_bound() -> float:
    """Upper bound of the dose beyond |x| = L: 2 int_L^inf x^-2a dx."""
    a = EXPONENT
    tail_integral = 2.0 * HALF_PATH_M ** (1 - 2 * a) / (2 * a - 1)
    return _prefactor_per_min() / (60.0 * SPEED_M_S) * tail_integral


def test_peak_flux_at_closest_approach():
    """sigma (1273.15^4 - 308.15^4) / 1000 * (0.1 / 0.5)^2 = 5.94 kW/m2."""
    assert _flux_at_kw_m2(0.0) == pytest.approx(5.938, abs=0.001)


def test_fine_step_sum_matches_closed_form():
    """A 0.01 s sum over +-10 m equals the closed form less the tails.

    The two are independent computations of the same integral; the only gap
    is the path beyond +-10 m, bounded by ``_tail_bound``.
    """
    fine = _step_sum_fed(step_s=0.01, phase=0.0)
    continuum = _continuum_fed_infinite_path()
    assert continuum == pytest.approx(0.011982, abs=1e-6)
    assert continuum - _tail_bound() <= fine <= continuum


def test_one_second_updates_bracket_the_continuum():
    """With 1 s updates the result depends on where the updates fall.

    An update at the closest approach over-counts the peak, updates either
    side of it under-count; the continuum lies between. The spread (+17 %,
    -16 %) is the sampling error a 1 s update interval gives for this pass.
    """
    at_peak = _step_sum_fed(step_s=UPDATE_INTERVAL_S, phase=0.0)
    straddling = _step_sum_fed(step_s=UPDATE_INTERVAL_S, phase=0.5)
    continuum = _continuum_fed_infinite_path()
    assert at_peak == pytest.approx(0.014052, abs=1e-6)
    assert straddling == pytest.approx(0.010038, abs=1e-6)
    assert straddling < continuum - _tail_bound() < continuum < at_peak


def test_single_pass_is_far_below_the_fatal_dose():
    """One pass at 0.5 m gives about 1 % of the fatal dose."""
    assert _step_sum_fed(step_s=UPDATE_INTERVAL_S, phase=0.0) < 0.02


def test_iso_threshold_one_second_updates():
    """ISO 13571:2012 §8.2, §8.4: radiant flux below 2.5 kW/m2 counts zero.

    q(x) = q0 R^2 / (d^2 + x^2) >= 2.5 only for |x| <= 0.586 m. With 1 s
    updates at x = 0 only the peak (5.938 kW/m2) counts; with updates at
    x = +-0.5 m both count (1.4845 / 0.5 = 2.969 kW/m2), the rest not.
    """
    q0_r2 = _surface_flux_kw_m2() * FLAME_RADIUS_M**2
    x_limit = math.sqrt(q0_r2 / 2.5 - CLOSEST_APPROACH_M**2)
    assert x_limit == pytest.approx(0.586, abs=0.001)
    at_peak = 5.938**EXPONENT / D_FATAL / 60.0
    straddling = 2 * 2.969**EXPONENT / D_FATAL / 60.0
    assert at_peak == pytest.approx(0.01067, abs=2e-5)
    assert straddling == pytest.approx(0.00848, abs=2e-5)
