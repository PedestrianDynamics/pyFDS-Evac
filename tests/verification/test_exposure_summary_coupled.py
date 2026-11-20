"""The exposure summary on a coupled corridor run (#210).

Synthetic uniform HCl (300 ppm) and HBr (100 ppm) fields: FIC = 400 / 900
(SFPE incapacitation denominators, 900 ppm each). Wiring only; the equations are
pinned in tests/test_fed.py.
"""

from __future__ import annotations

import sqlite3

import pytest
from harness import CorridorSpec, corridor_scenario, make_fed_model, uniform

from pyfds_evac.core.scenario import run_scenario

FPS = 10.0  # JuPedSim output frame rate of the run


@pytest.fixture(scope="module")
def result():
    fed = make_fed_model(
        co_volume_fraction=uniform(0.0),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        hcl=uniform(3e-4),
        hbr=uniform(1e-4),
    )
    spec = CorridorSpec(
        length_m=10.0,
        width_m=4.0,
        num_agents=3,
        v0=1.2,
        seed=3,
        max_simulation_time=60.0,
    )
    res = run_scenario(corridor_scenario(spec), seed=spec.seed, fed_model=fed)
    yield res
    res.cleanup()


def test_hcl_column_is_the_fic_numerator(result):
    for row in result.fed_history:
        assert row["hcl_ppm"] == pytest.approx(300.0)
        # HCl and HBr both enter the FIC with the 900 ppm denominator.
        assert row["fic"] == pytest.approx((row["hcl_ppm"] + row["hbr_ppm"]) / 900.0)


def test_sampled_irritant_is_a_column_and_unsampled_ones_are_not(result):
    row = result.fed_history[0]
    assert row["hbr_ppm"] == pytest.approx(100.0)
    assert "hf_ppm" not in row


def test_exit_times_agree_with_the_last_trajectory_frame(result):
    # JuPedSim numbers agents across runs in one process, so ids are not 1..3.
    assert set(result.exit_times) == {r["agent_id"] for r in result.fed_history}
    assert len(result.exit_times) == 3
    con = sqlite3.connect(result.sqlite_file)
    last = dict(con.execute("select id, max(frame) from trajectory_data group by id"))
    con.close()
    for agent_id, exit_s in result.exit_times.items():
        assert abs(exit_s - last[agent_id] / FPS) <= 1.5 / FPS


def test_summary_is_consistent_with_the_history(result):
    rows = {r["agent_id"]: r for r in result.exposure_summary()}
    for agent_id, row in rows.items():
        history = [r for r in result.fed_history if r["agent_id"] == agent_id]
        assert row["fed_max"] == max(r["fed_cumulative"] for r in history)
        assert row["fic_max"] == pytest.approx(4.0 / 9.0)
        assert row["censored"] is False
        assert row["outcome_fic_ge_0.3"] == "fail"
        assert row["t_fic_ge_0.3_s"] == 0.0
        assert row["outcome_fic_ge_1"] == "pass"
        assert row["outcome_heat_fed_ge_0.3"] == "not_evaluated"
        assert row["outcome_k_ge_0.3"] == "not_evaluated"
