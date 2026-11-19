"""AnticipationVelocityModel at a flush exit (#975) and the exit-reachability warning.

The room of ``test_run_outcome`` is 10 x 6 m with six agents of radius 0.15 m
and v0 1.3 m/s. Its exit is flush with the east wall and 0.2 m deep.

An agent whose target lies behind a wall stops at r + b (b the wall buffer),
and the run counts an exit as reached within ``EXIT_REACH_TOLERANCE_M`` (0.03 m)
of its polygon. With JuPedSim's b = 0.1 m the stop gap is 0.25 m, beyond the
0.23 m the exit allows; b = 0.0 is a pyFDS-Evac choice. The expected
evacuation times are seeded results of the b16 measurement.
"""

from __future__ import annotations

import contextlib
import io
import logging
from types import SimpleNamespace

import pytest
import test_run_outcome as room
from shapely.geometry import box

from pyfds_evac.config.effective import effective_configuration
from pyfds_evac.core.exit_reach import exit_reach_warning
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import create_agent_parameters

AVM = "AnticipationVelocityModel"
CFSM = "CollisionFreeSpeedModel"


@pytest.fixture(autouse=True)
def _flush_exit(monkeypatch):
    monkeypatch.setattr(room, "EXIT", box(9.8, 2.0, 10.0, 4.0))


def _room(model, **dist_extra):
    scenario = room._scenario(room.ENOUGH_S, **dist_extra)
    scenario.set_model_type(model)
    return scenario


def _run(scenario, seed):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(scenario, seed=seed)


def test_avm_wall_buffer_default_is_pinned():
    agent = create_agent_parameters(AVM, (0.0, 0.0), {})
    assert agent.wall_buffer_distance == 0.0


@pytest.mark.parametrize("seed, time_s", [(3, 6.69), (5, 7.62)])
def test_avm_leaves_a_flush_exit(seed, time_s):
    result = _run(_room(AVM), seed)
    try:
        assert result.agents_evacuated == room.NUM_AGENTS
        assert result.end_reason == "all_evacuated"
        assert round(result.evacuation_time, 2) == pytest.approx(time_s, abs=0.01)
    finally:
        result.cleanup()


def _warning(model, radius=0.15, clearance=None):
    scenario = _room(model, radius=radius)
    return exit_reach_warning(
        model, scenario.walkable_polygon, scenario.raw, clearance=clearance
    )


@pytest.mark.parametrize(
    "model, radius, clearance",
    [
        (AVM, 0.15, 0.1),  # JuPedSim's buffer: the defect of #975
        (AVM, 0.15, 0.08),  # on the threshold: 0.030 m
        (CFSM, 0.22, None),
        ("CollisionFreeSpeedModelV2", 0.22, None),
    ],
)
def test_warning_fires(model, radius, clearance):
    message = _warning(model, radius, clearance)
    assert message is not None
    assert "E (" in message and "#975" in message


@pytest.mark.parametrize(
    "model, radius, clearance",
    [
        (AVM, 0.15, None),
        (AVM, 0.15, 0.0),
        (CFSM, 0.15, None),
        (CFSM, 0.2, None),
    ],
)
def test_warning_is_silent(model, radius, clearance):
    assert _warning(model, radius, clearance) is None


def test_run_logs_the_warning(caplog):
    scenario = _room(CFSM, radius=0.22)
    scenario.set_max_time(1)
    with caplog.at_level(logging.WARNING):
        _run(scenario, 3).cleanup()
    assert any("#975" in record.getMessage() for record in caplog.records)


def test_effective_configuration_lists_the_warning():
    opts = SimpleNamespace(scenario="deck.json")
    fires = effective_configuration(opts, _room(CFSM, radius=0.22), inspect_fds=False)
    assert any("#975" in message for message in fires.warnings)
    quiet = effective_configuration(opts, _room(AVM), inspect_fds=False)
    assert not any("#975" in message for message in quiet.warnings)
