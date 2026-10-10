"""A spawn area's ``flow_schedule`` in a whole run (#390).

The deck is the 10 x 6 m room of ``test_run_outcome``: one exit in the
east wall, a 3 x 4 m spawn area in the west half. Each window adds its
``number`` agents at evenly spaced times within it, at most one per
0.01 s step; ``initial_number`` agents start at t = 0.
"""

from __future__ import annotations

import contextlib
import io
import json
import random
from types import SimpleNamespace

import jupedsim as jps
import pytest
from shapely.geometry import box
from test_run_outcome import ENOUGH_S, SEED, D, _scenario

from pyfds_evac.core.agent_seed import (
    PURPOSE_FLOW_POSITIONS,
    PURPOSE_FLOW_SHUFFLE,
    PURPOSE_POSITIONS,
    distribution_seed,
)
from pyfds_evac.core.run_outputs import summary_line
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json

SPAWN = box(1.0, 1.0, 4.0, 5.0)


def _scheduled(windows, *, max_time_s=ENOUGH_S, initial=0):
    scenario = _scenario(max_time_s, number=initial)
    scenario.set_flow_schedule(D, windows, keep_initial_agents=initial > 0)
    return scenario


def _run(scenario):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(scenario, seed=SEED)


def _window(start, end, number):
    return {"flow_start_time": start, "flow_end_time": end, "number": number}


def test_overlapping_windows_add_all_their_agents():
    result = _run(_scheduled([_window(0, 4, 5), _window(2, 6, 5)]))
    assert (result.total_agents, result.agents_not_spawned) == (10, 0)
    assert result.success


def test_a_short_window_keeps_its_length():
    """[0, 0.05] s for 3 agents, within the window as written.

    The run once stretched every window to at least 0.1 s, which spaced
    the agents 0.033 s apart; at 0.06 s the third had not entered. Now
    they enter 0.0167 s apart, all by 0.04 s. 3 agents in 0.05 s is 60
    agents/s, within the flow-rate check of this area (84).
    """
    result = _run(_scheduled([_window(0, 0.05, 3)], max_time_s=0.06))
    assert (result.total_agents, result.agents_not_spawned) == (3, 0)


def test_a_window_too_short_for_its_agents_stops_the_run():
    with pytest.raises(ValueError, match=r"too short for 3 agents.*at least 0\.03 s"):
        _run(_scheduled([_window(0, 0.02, 3)]))


def test_a_window_past_the_time_limit_leaves_agents_unspawned():
    """A window cut off by ``max_simulation_time`` is reported, not dropped."""
    result = _run(_scheduled([_window(2, 12, 10)], max_time_s=4.0))
    assert result.status == "incomplete"
    assert 0 < result.agents_not_spawned < 10
    assert summary_line(result).endswith(f"{result.agents_not_spawned} not spawned).")


def test_initial_and_scheduled_agents_draw_their_own_positions(tmp_path):
    """The windows' candidate positions have their own seed streams.

    The pool is ``distribute_until_filled`` seeded with ``flow_positions``
    and shuffled with ``flow_shuffle``, not the ``positions`` stream that
    places the initial agents; the whole run adds both.
    """
    scenario = _scheduled([_window(1, 5, 6)], initial=4)
    result = _run(scenario)
    assert (result.total_agents, result.agents_not_spawned) == (10, 0)
    assert result.success

    pool = jps.distribute_until_filled(
        polygon=SPAWN,
        distance_to_agents=0.3,
        distance_to_polygon=0.15,
        seed=distribution_seed(SEED, D, PURPOSE_FLOW_POSITIONS),
    )
    random.Random(distribution_seed(SEED, D, PURPOSE_FLOW_SHUFFLE)).shuffle(pool)
    initial = jps.distribute_by_number(
        polygon=SPAWN,
        number_of_agents=4,
        distance_to_agents=0.3,
        distance_to_polygon=0.15,
        seed=distribution_seed(SEED, D, PURPOSE_POSITIONS),
    )
    assert pool[:4] != initial

    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=scenario.walkable_polygon
    )
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(scenario.raw), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        _, positions, _, info = initialize_simulation_from_json(
            str(path),
            simulation,
            SimpleNamespace(polygon=scenario.walkable_polygon),
            seed=SEED,
            global_parameters=SimpleNamespace(**scenario.sim_params),
        )
    assert info["starting_pos_per_source"] == [pool]
    assert sorted(positions) == sorted(initial)
