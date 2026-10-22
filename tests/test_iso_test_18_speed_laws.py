"""ISO 20414 Test 18 (Table 21): both smoke-speed laws over the suggested grid.

Table 21 asks the tester to verify the correlation the model uses, repeated for
"different combinations of unimpeded walking speeds and constant extinction
coefficients", with the examples 1,0 / 0,75 / 0,5 / 0,25 m/s and
10 / 7,5 / 3,0 / 0,5 1/m. pyFDS-Evac ships two laws, so both are verified.
Every expected number below is written out by hand from the published
equation and is never taken from ``speed_factor_from_extinction`` or any other
code under test (#259).

Laws, with the symbols of the sources
-------------------------------------

Frantzich and Nilsson (``speed_law="lund"``, Lund report 3126, Eq. 3,
App. D, Table D2 model 1; as FDS+Evac uses it, with the floor 0,1)::

    f(K) = min(1, max(0.1, 1 + (beta / alpha) K)),  alpha = 0.706 m/s,
                                                    beta = -0.057 m^2/s
    beta / alpha = -0.0807365 m

Fridolf et al. (``speed_law="fridolf"``, Fridolf, Ronchi, Nilsson and
Frantzich 2019, TUST 90:28-41, Eq. 7; method 3 of Fridolf et al. 2018)::

    w = min(w_free, max(0.2, w_free - 0.34 (3 - x)))      [m/s],  x = C / K

x is the visibility [m]; the speed factor is f = w / w_free. The constant of
Jin's relation is C = 3 (the FDS default for a reflecting sign, what
pyFDS-Evac uses); the paper's Eq. 1, x = A / K, was calibrated with A = 2
(reflecting) or A = 8 (emitting). The reduction is additive (0.34 m/s per
metre below 3 m) and the floor is an absolute 0.2 m/s, not 0.2 w_free.

Hand calculation, Fridolf, C = 3 (x = 3 / K: 0.3, 0.4, 1.0 and 6.0 m)
----------------------------------------------------------------------

    K = 10   : x = 0.3 m, drop 0.34 x 2.7 = 0.918 m/s
    K = 7.5  : x = 0.4 m, drop 0.34 x 2.6 = 0.884 m/s
    K = 3    : x = 1.0 m, drop 0.34 x 2.0 = 0.680 m/s
    K = 0.5  : x = 6.0 m, above 3 m, no drop

    w_free   K = 10     K = 7.5    K = 3       K = 0.5
    1.25     0.332      0.366      0.570       1.25
    1.00     0.2 floor  0.2 floor  0.320       1.00
    0.75     0.2 floor  0.2 floor  0.2 floor   0.75
    0.50     0.2 floor  0.2 floor  0.2 floor   0.50
    0.25     0.2 floor  0.2 floor  0.2 floor   0.25

(1.25 m/s is the unimpeded speed of the ISO corridor in ``assets/ISO-table21``;
it is not in the standard's list.) At K = 3 and w_free = 1.0, 1.0 - 0.68 =
0.32 lies above the floor; for w_free = 0.75, 0.5 and 0.25 the unfloored value
0.07, -0.18 and -0.43 lies below it. The floor raises the speed of a slow
walker only up to w_free, so for w_free = 0.25 the factor is 0.2 / 0.25 = 0.8.

Hand calculation, Lund
----------------------

    f(0.5)  = 1 - 0.0285 / 0.706 = 0.959632
    f(3)    = 1 - 0.171  / 0.706 = 0.757790
    f(7.5)  = 1 - 0.4275 / 0.706 = 0.394476
    f(10)   = 1 - 0.57   / 0.706 = 0.192635

The factor does not depend on the unimpeded speed. The floor is not reached in
the grid: it starts at K = 0.9 x 0.706 / 0.057 = 11.1474 1/m.

Coupled corridor
----------------

Walking a length L at w instead of w_free adds L (1/w - 1/w_free) to the egress
time. L = 98.321 m is the walked length of the ISO corridor, fitted to five
clear runs on the Test 18 page (t = L / v0 + a, a = 0.592 s start-up), so the
expected smoky time is the clear time of the same occupant plus
L (1/w - 1/w_free), with w by hand from the tables above.
"""

from __future__ import annotations

import pytest

from pyfds_evac.core import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)
from pyfds_evac.core.smoke_speed import speed_factor_from_extinction_fridolf

pytestmark = pytest.mark.iso20414

FREE_SPEEDS = (1.0, 0.75, 0.5, 0.25)
EXTINCTIONS = (10.0, 7.5, 3.0, 0.5)

# Lund f(K) by hand (see the module docstring); the same for every free speed.
LUND_F = {10.0: 0.192635, 7.5: 0.394476, 3.0: 0.757790, 0.5: 0.959632}

# Fridolf w [m/s] by hand, C = 3, keyed by (w_free, K). Exact decimals.
FRIDOLF_W = {
    (1.00, 10.0): 0.2,
    (1.00, 7.5): 0.2,
    (1.00, 3.0): 0.32,
    (1.00, 0.5): 1.0,
    (0.75, 10.0): 0.2,
    (0.75, 7.5): 0.2,
    (0.75, 3.0): 0.2,
    (0.75, 0.5): 0.75,
    (0.50, 10.0): 0.2,
    (0.50, 7.5): 0.2,
    (0.50, 3.0): 0.2,
    (0.50, 0.5): 0.5,
    (0.25, 10.0): 0.2,
    (0.25, 7.5): 0.2,
    (0.25, 3.0): 0.2,
    (0.25, 0.5): 0.25,
    # The corridor's own unimpeded speed, where the slope is not floored.
    (1.25, 10.0): 0.332,
    (1.25, 7.5): 0.366,
    (1.25, 3.0): 0.57,
    (1.25, 0.5): 1.25,
}

# Fridolf, w_free = 1.0, for the paper's A = 2 and A = 8 as C (x = C / K):
#   C = 2: x = 0.2, 0.2667, 0.6667, 4.0 m -> 1 - 0.34 (3 - x) = 0.052,
#          0.0707, 0.20667, no drop;
#   C = 8: x = 0.8, 1.0667, 2.6667, 16 m -> 0.252, 0.342667, 0.886667, no drop.
FRIDOLF_W_OTHER_C = {
    (2.0, 10.0): 0.2,
    (2.0, 7.5): 0.2,
    (2.0, 3.0): 0.2066667,
    (2.0, 0.5): 1.0,
    (8.0, 10.0): 0.252,
    (8.0, 7.5): 0.3426667,
    (8.0, 3.0): 0.8866667,
    (8.0, 0.5): 1.0,
}


def _model(law: str, extinction: float, **config) -> SmokeSpeedModel:
    return SmokeSpeedModel(
        ConstantExtinctionField(extinction),
        SmokeSpeedConfig(fds_dir=".", speed_law=law, update_interval_s=0.1, **config),
    )


@pytest.mark.parametrize("extinction", EXTINCTIONS)
@pytest.mark.parametrize("free_speed", FREE_SPEEDS)
class TestTheGrid:
    """All 16 cells of the suggested grid, through the public model."""

    def test_lund_factor_and_speed(self, free_speed, extinction):
        factor = _model("lund", extinction).speed_factor(
            0.0, 0.0, 0.0, free_speed_m_per_s=free_speed
        )
        assert factor == pytest.approx(LUND_F[extinction], abs=1e-6)
        assert free_speed * factor == pytest.approx(
            free_speed * LUND_F[extinction], abs=1e-6
        )

    def test_fridolf_speed_and_factor(self, free_speed, extinction):
        w = FRIDOLF_W[(free_speed, extinction)]
        factor = _model("fridolf", extinction).speed_factor(
            0.0, 0.0, 0.0, free_speed_m_per_s=free_speed
        )
        assert free_speed * factor == pytest.approx(w, abs=1e-9)
        assert factor == pytest.approx(w / free_speed, abs=1e-9)


class TestTheClampEdges:
    """Where each law's floor takes over."""

    @pytest.mark.parametrize(
        ("extinction", "factor"),
        [
            (11.0, 0.111898),  # just below the onset: 1 - 0.627 / 0.706
            (11.147368, 0.1),  # the onset, K = 0.9 x 0.706 / 0.057
            (12.0, 0.1),  # past it: floor
            (100.0, 0.1),
        ],
    )
    def test_lund_floor(self, extinction, factor):
        got = _model("lund", extinction).speed_factor(0.0, 0.0, 0.0)
        assert got == pytest.approx(factor, abs=1e-6)

    def test_lund_floor_is_not_reached_by_the_grid(self):
        assert min(LUND_F.values()) > 0.1

    @pytest.mark.parametrize(
        ("extinction", "w"),
        [
            (4.5, 0.2066667),  # x = 0.6667 m: 1 - 0.34 x 2.3333, above the floor
            (4.8, 0.2),  # x = 0.625 m: 1 - 0.34 x 2.375 = 0.1925, floored
            (1e6, 0.2),  # x -> 0: 1 - 1.02 = -0.02, floored
        ],
    )
    def test_fridolf_floor_at_one_metre_per_second(self, extinction, w):
        factor = _model("fridolf", extinction).speed_factor(
            0.0, 0.0, 0.0, free_speed_m_per_s=1.0
        )
        assert factor == pytest.approx(w, abs=1e-6)

    def test_fridolf_floor_is_absolute_not_a_fraction_of_the_free_speed(self):
        """0.2 m/s for w_free = 1.0 (factor 0.2) and for 0.5 (factor 0.4)."""
        model = _model("fridolf", 10.0)
        assert model.speed_factor(0.0, 0.0, 0.0, free_speed_m_per_s=1.0) == (
            pytest.approx(0.2, abs=1e-12)
        )
        assert model.speed_factor(0.0, 0.0, 0.0, free_speed_m_per_s=0.5) == (
            pytest.approx(0.4, abs=1e-12)
        )

    def test_fridolf_knee_at_three_metres(self):
        """x = 3 m, i.e. K = C / 3 = 1 1/m for C = 3: no slowing at the knee."""
        assert _model("fridolf", 1.0).speed_factor(
            0.0, 0.0, 0.0, free_speed_m_per_s=1.25
        ) == pytest.approx(1.0, abs=1e-12)

    def test_fridolf_just_inside_the_knee_slows_by_the_slope(self):
        """K = 1.5 -> x = 2 m: w = 1.25 - 0.34 x 1 = 0.91, f = 0.728."""
        factor = _model("fridolf", 1.5).speed_factor(
            0.0, 0.0, 0.0, free_speed_m_per_s=1.25
        )
        assert factor == pytest.approx(0.728, abs=1e-12)


class TestTheVisibilityConstant:
    """C = 3 by default; the paper's A = 2 and A = 8 as an alternative."""

    def test_the_default_constant_is_three(self):
        assert SmokeSpeedConfig().visibility_factor_c == 3.0

    @pytest.mark.parametrize(("c", "extinction"), sorted(FRIDOLF_W_OTHER_C))
    def test_other_constants(self, c, extinction):
        factor = speed_factor_from_extinction_fridolf(
            extinction, visibility_factor_c=c, free_speed_m_per_s=1.0
        )
        assert factor == pytest.approx(FRIDOLF_W_OTHER_C[(c, extinction)], abs=1e-6)

    def test_the_configured_constant_reaches_the_model(self):
        model = _model("fridolf", 3.0, visibility_factor_c=8.0)
        factor = model.speed_factor(0.0, 0.0, 0.0, free_speed_m_per_s=1.0)
        assert factor == pytest.approx(0.8866667, abs=1e-6)


# ---------------------------------------------------------------------------
# Coupled corridor: ISO 20414 Table 21, 2 m x 100 m, 1 m exit, one occupant.
# ---------------------------------------------------------------------------

# Walked length of the corridor [m], from the clear-run fit on the Test 18 page.
WALKED_LENGTH_M = 98.321
TIME_STEP_S = 0.01
# The tolerance: the clear time and the smoky time are each a whole number of
# steps (2 steps), the page's largest fit residual (0.016 s), and an assumed
# error of 0.01 m in L, which enters as L_error x |1/w - 1/w_free|.
LENGTH_ERROR_M = 0.01
FIT_RESIDUAL_S = 0.016

# (law, w_free, K) cells run in the corridor. The Fridolf cells cover both the
# slope (w_free = 1.25, 1.0 at K = 3), the floor with a large margin
# (1.0 at K = 7.5, 0.5 at K = 3), the floor against w_free (0.25 at K = 7.5,
# f = 0.8) and the no-effect cell (0.75 at K = 0.5). The Lund cells are
# hand-calculated counterparts: the Test 18 page covers the K sweep at 1.25 m/s
# and the v0 sweep at K = 1.
COUPLED_CELLS = (
    ("fridolf", 1.25, 3.0),
    ("fridolf", 1.25, 7.5),
    ("fridolf", 1.25, 10.0),
    ("fridolf", 1.0, 3.0),
    ("fridolf", 1.0, 7.5),
    ("fridolf", 0.5, 3.0),
    ("fridolf", 0.25, 7.5),
    ("fridolf", 0.75, 0.5),
    ("lund", 1.0, 7.5),
    ("lund", 0.5, 3.0),
)


def _hand_speed(law: str, free_speed: float, extinction: float) -> float:
    if law == "lund":
        return LUND_F[extinction] * free_speed
    return FRIDOLF_W[(free_speed, extinction)]


def _scenario(free_speed: float, max_time: float):
    scenario = load_scenario("assets/ISO-table21")
    for distribution in scenario.raw["distributions"].values():
        distribution["parameters"]["v0"] = free_speed
    scenario.set_max_time(max_time)
    return scenario


@pytest.fixture(scope="module")
def clear_times():
    """Clear-air egress time of the occupant per unimpeded speed, run once."""
    times: dict[float, float] = {}

    def get(free_speed: float) -> float:
        if free_speed not in times:
            outcome = run_scenario(
                _scenario(free_speed, 450.0 * 1.25 / free_speed), seed=420
            )
            try:
                assert outcome.success and outcome.agents_remaining == 0
                times[free_speed] = outcome.evacuation_time
            finally:
                outcome.cleanup()
        return times[free_speed]

    return get


@pytest.mark.parametrize(
    ("law", "free_speed", "extinction"),
    COUPLED_CELLS,
    ids=[f"{law}-v{v}-K{k}" for law, v, k in COUPLED_CELLS],
)
def test_the_corridor_time_matches_the_hand_calculation(
    clear_times, law, free_speed, extinction
):
    w = _hand_speed(law, free_speed, extinction)
    expected = clear_times(free_speed) + WALKED_LENGTH_M * (1.0 / w - 1.0 / free_speed)
    outcome = run_scenario(
        _scenario(free_speed, 1.3 * expected + 60.0),
        seed=420,
        smoke_speed_model=_model(law, extinction),
    )
    try:
        assert outcome.success and outcome.agents_remaining == 0
        assert outcome.smoke_history
        for row in outcome.smoke_history:
            assert row["extinction_per_m"] == pytest.approx(extinction, abs=1e-9)
            assert row["base_speed"] == pytest.approx(free_speed, abs=1e-9)
            assert row["desired_speed"] == pytest.approx(w, abs=1e-6)
            assert row["speed_factor"] == pytest.approx(w / free_speed, abs=1e-6)
        tolerance = (
            2 * TIME_STEP_S
            + FIT_RESIDUAL_S
            + LENGTH_ERROR_M * abs(1.0 / w - 1.0 / free_speed)
        )
        assert outcome.evacuation_time == pytest.approx(expected, abs=tolerance)
    finally:
        outcome.cleanup()
