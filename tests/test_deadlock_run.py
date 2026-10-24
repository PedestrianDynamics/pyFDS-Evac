"""A jammed run stops with end_reason "deadlock" and reports its stuck agents (#760).

Uses the #359 head-on jam of assets/familiarity_test_no_journey: with 5 agents,
seed 23 jams two agents in the CP2 doorway. Before #760 that run stood until the
300 s time limit.
"""

import pytest
from test_familiarity_no_journey import _run, vis_model  # noqa: F401

pytestmark = pytest.mark.slow


def test_a_doorway_jam_ends_the_run_as_a_deadlock(tmp_path, vis_model):  # noqa: F811
    result = _run(tmp_path, vis_model, 5, 23)
    try:
        assert result.end_reason == "deadlock"
        assert result.status == "incomplete"
        assert result.evacuation_time < 300.0
        deadlock = result.metrics["deadlock"]
        assert deadlock["agents"] == 5 - result.agents_evacuated == 2
        assert result.evacuation_time == pytest.approx(deadlock["since_s"] + 100.0)
        assert sorted(map(tuple, deadlock["positions"])) == [(3.6, 1.99), (3.92, 1.44)]
    finally:
        result.cleanup()


def test_a_run_that_empties_has_no_deadlock_key(tmp_path, vis_model):  # noqa: F811
    result = _run(tmp_path, vis_model, 5, 1)
    try:
        assert result.end_reason == "all_evacuated"
        assert "deadlock" not in result.metrics
    finally:
        result.cleanup()
