"""NIST TN 1822 Verif.2.5: reduced visibility versus walking speed.

Ronchi et al. (2013), Verif.2.5: a corridor 2 m wide and 100 m long with a 1 m
exit at the end, one occupant with an unimpeded speed of 1.25 m/s, and a
constant extinction coefficient of 1.0 1/m. Expected result: the time to cover
the corridor equals the time calculated by hand from the correlation the model
uses. The geometry and the numbers are those of ISO 20414 Test 18 (Table 21),
so ``assets/ISO-table21`` is the NIST corridor. The 1.0 1/m cell is not in
ISO's suggested grid (10, 7.5, 3, 0.5 1/m); this module runs it for both laws
pyFDS-Evac ships.

The occupant walks from x = -49.5 m to the exit at x = 49 m. NIST's report
does not say where the time is measured. The time is taken between the first
frames at x = -30 m and x = +30 m, a 60 m stretch far from the start-up and
the exit, so the expected time follows from the speed alone and needs no
fitted corridor length (the ISO 18 coupled test fits one).

Hand calculation, v0 = 1.25 m/s, K = 1.0 1/m
--------------------------------------------

Frantzich and Nilsson (``speed_law="lund"``)::

    f(K) = 1 + (beta / alpha) K = 1 - 0.057 / 0.706 = 0.919263
    w = 1.25 x 0.919263 = 1.149079 m/s       t(60 m) = 60 / 1.149079 = 52.215 s

Fridolf et al. (``speed_law="fridolf"``, A = 2)::

    x = A / K = 2 m, below the 3 m knee, above the floor:
    w = 1.25 - 0.34 (3 - 2) = 0.91 m/s       t(60 m) = 60 / 0.91 = 65.934 s

Clear air: t(60 m) = 60 / 1.25 = 48.0 s.

Tolerance: the trajectory has 10 frames/s and each crossing time is a whole
frame, so the difference is good to 0.1 s; 0.15 s leaves half a frame more.
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

pytestmark = pytest.mark.nist_tn1822

FREE_SPEED_M_S = 1.25
EXTINCTION_PER_M = 1.0
X_IN_M = -30.0
X_OUT_M = 30.0
SEGMENT_M = X_OUT_M - X_IN_M
TOLERANCE_S = 0.15

# Hand values, see the module docstring.
HAND_SPEED_M_S = {"lund": 1.149079, "fridolf": 0.91}


def _segment_time_s(law: str | None) -> tuple[float, list]:
    scenario = load_scenario("assets/ISO-table21")
    scenario.set_max_time(300.0)
    kwargs = {}
    if law is not None:
        kwargs["smoke_speed_model"] = SmokeSpeedModel(
            ConstantExtinctionField(EXTINCTION_PER_M),
            SmokeSpeedConfig(fds_dir=".", speed_law=law, update_interval_s=0.1),
        )
    result = run_scenario(scenario, seed=420, **kwargs)
    try:
        assert result.success and result.agents_remaining == 0
        frames = result.trajectory_dataframe().sort_values("frame")

        def crossing(x: float) -> float:
            return frames.loc[frames.x >= x, "frame"].iloc[0] / result.frame_rate

        return crossing(X_OUT_M) - crossing(X_IN_M), list(result.smoke_history or [])
    finally:
        result.cleanup()


def test_clear_air_time_is_the_distance_over_the_unimpeded_speed():
    elapsed, history = _segment_time_s(None)
    assert elapsed == pytest.approx(SEGMENT_M / FREE_SPEED_M_S, abs=TOLERANCE_S)
    assert not history


@pytest.mark.parametrize("law", ["lund", "fridolf"])
def test_smoke_time_is_the_distance_over_the_hand_calculated_speed(law):
    elapsed, history = _segment_time_s(law)
    assert elapsed == pytest.approx(SEGMENT_M / HAND_SPEED_M_S[law], abs=TOLERANCE_S)
    assert history
    for row in history:
        assert row["extinction_per_m"] == pytest.approx(EXTINCTION_PER_M, abs=1e-9)
        assert row["base_speed"] == pytest.approx(FREE_SPEED_M_S, abs=1e-9)
        assert row["desired_speed"] == pytest.approx(HAND_SPEED_M_S[law], abs=1e-6)
