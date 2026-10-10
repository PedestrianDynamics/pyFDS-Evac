"""A journey that no transition names is refused at load and at set-up (#504).

An agent on a journey is steered along that journey's transitions only.
Before #504 a deck whose ``journeys`` listed stages without any
``transitions`` (the older JuPedSim Web export) loaded, printed a normal
summary and ran to the time limit with every agent standing still.

The deck is the synthetic room of ``test_run_outcome``: 10 x 6 m, one
exit in the east wall, six agents about 6 m from it.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest
from test_run_outcome import ENOUGH_S, SEED, D, _scenario

from pyfds_evac.core.scenario import _migrate_journeys_v2, load_scenario, run_scenario
from pyfds_evac.core.simulation_init import check_journey_transitions


def _without_transitions():
    scenario = _scenario(ENOUGH_S)
    scenario.raw["transitions"] = []
    return scenario


def test_run_refuses_a_journey_without_transitions():
    # Before #504: status "incomplete", 6 of 6 agents left at 60 s.
    with pytest.raises(ValueError, match=r"Journey\(s\) 'J' list stages"):
        with contextlib.redirect_stdout(io.StringIO()):
            run_scenario(_without_transitions(), seed=SEED)


def test_load_refuses_a_journey_without_transitions(tmp_path):
    scenario = _without_transitions()
    (tmp_path / "config.json").write_text(json.dumps(scenario.raw))
    (tmp_path / "geometry.wkt").write_text(scenario.walkable_area_wkt)
    with pytest.raises(ValueError, match="never move"):
        load_scenario(str(tmp_path))


def test_only_the_journey_without_transitions_is_named():
    raw = _scenario(ENOUGH_S).raw
    raw["journeys"].append({"id": "K", "stages": [D, "E"]})
    with pytest.raises(ValueError) as excinfo:
        check_journey_transitions(raw)
    assert "'K'" in str(excinfo.value)
    assert "'J'" not in str(excinfo.value)


def test_editor_journeys_are_named_as_the_way_out():
    raw = _without_transitions().raw
    raw["journeys_v2"] = [{"id": "j1", "sequence": ["E"]}]
    with pytest.raises(ValueError, match=r"set 'journeys' to \[\] to use"):
        check_journey_transitions(raw)


def test_journeys_with_transitions_pass():
    check_journey_transitions(_scenario(ENOUGH_S).raw)


def test_a_deck_without_distributions_is_not_checked():
    # The fallback set-up places nobody from a journey, so it has no
    # journey to steer along.
    raw = _without_transitions().raw
    raw["distributions"] = {}
    check_journey_transitions(raw)


def _run_completes(scenario) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=SEED)
    try:
        assert result.agents_remaining == 0
    finally:
        result.cleanup()


def _with_second_exit(scenario):
    scenario.raw["exits"]["E2"] = {
        "type": "polygon",
        "coordinates": [[0.0, 2.0], [0.2, 2.0], [0.2, 4.0], [0.0, 4.0], [0.0, 2.0]],
    }
    return scenario


@pytest.mark.parametrize(
    "stages",
    [["E", "E2"], ["E"], [D]],
    ids=["exits-only", "one-exit", "distribution-only"],
)
def test_a_journey_without_agents_is_not_refused(stages):
    """A journey that places nobody leaves the agents to the nearest exit.

    It needs no transitions; before the restriction of #504 an exit-only
    journey of a deck with distributions was refused at load.
    """
    scenario = _with_second_exit(_without_transitions())
    scenario.raw["journeys"] = [{"id": "J", "stages": stages}]
    check_journey_transitions(scenario.raw)
    _run_completes(scenario)


def test_editor_journeys_migrate_when_journeys_is_empty(tmp_path):
    scenario = _without_transitions()
    raw = scenario.raw
    raw["journeys"] = []
    raw["journeys_v2"] = [{"id": "j1", "sequence": ["E"]}]
    raw["distributions"][D]["journey_weights"] = [{"journey_id": "j1", "weight": 100}]
    (tmp_path / "config.json").write_text(json.dumps(raw))
    (tmp_path / "geometry.wkt").write_text(scenario.walkable_area_wkt)
    loaded = load_scenario(str(tmp_path))
    assert loaded.raw["transitions"] == [{"from": D, "to": "E", "journey_id": "j1"}]
    _run_completes(loaded)


SHIPPED = sorted(
    p
    for p in pathlib.Path("assets").rglob("*.json")
    if "exits" in json.loads(p.read_text(encoding="utf-8"))
)


@pytest.mark.parametrize("config", SHIPPED, ids=str)
def test_every_shipped_deck_passes(config):
    """Including the explore, patrol and no-journey decks."""
    raw = json.loads(config.read_text(encoding="utf-8"))
    _migrate_journeys_v2(raw)
    check_journey_transitions(raw)
