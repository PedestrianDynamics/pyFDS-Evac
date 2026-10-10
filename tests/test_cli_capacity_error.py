"""An over-full spawn area stops ``pyfds-evac`` with one line (#692).

The deck is the 10 x 6 m room of ``test_run_outcome``; its 3 x 4 m spawn
area holds far fewer than 500 agents of radius 0.15 m. A deck with
journeys places agents distribution by distribution; one without them
seeds each spawn area once (``_seed_shared_areas``). Both report the
distribution, the requested count and the capacity.

A count within the estimate can still fail when the sampler cannot place
everyone; that is reported in one line as well, with or without
journeys (#702, #508).
"""

from __future__ import annotations

import contextlib
import io
import re

import jupedsim as jps
import pytest
from test_run_outcome import ENOUGH_S, D, _scenario

from pyfds_evac import cli
from pyfds_evac.core import simulation_init
from pyfds_evac.core.scenario import load_scenario, run_scenario

PATTERN = (
    rf"^pyfds-evac: error: Distribution '{D}': requested 500 agents "
    r"but area can hold at most ~\d+\. "
)


def _over_full(with_journeys: bool):
    scenario = _scenario(ENOUGH_S, number=500)
    if not with_journeys:
        scenario.raw["journeys"] = []
        scenario.raw["transitions"] = []
    return scenario


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_over_full_spawn_area_is_a_one_line_error(monkeypatch, with_journeys):
    scenario = _over_full(with_journeys)
    monkeypatch.setattr(cli, "load_scenario", lambda _path: scenario)
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", "unused"])
    with contextlib.redirect_stdout(io.StringIO()), pytest.raises(SystemExit) as exit_:
        cli.main()
    message = exit_.value.code
    assert isinstance(message, str)
    assert "\n" not in message
    assert re.match(PATTERN, message), message


def test_unplaceable_agents_within_the_estimate_are_a_one_line_error(monkeypatch):
    def refuse(**_kwargs):
        raise jps.AgentNumberError("Only 9 of 10  could be placed.")

    scenario = _scenario(ENOUGH_S, number=10)
    scenario.raw["journeys"] = []
    scenario.raw["transitions"] = []
    monkeypatch.setattr(simulation_init.jps, "distribute_by_number", refuse)
    monkeypatch.setattr(cli, "load_scenario", lambda _path: scenario)
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", "unused"])
    with contextlib.redirect_stdout(io.StringIO()), pytest.raises(SystemExit) as exit_:
        cli.main()
    message = exit_.value.code
    assert isinstance(message, str)
    assert "\n" not in message
    assert re.match(
        rf"^pyfds-evac: error: Distribution '{D}': could not place the 10 "
        r"requested agents \(Only 9 of 10  could be placed\.\)\. "
        r"The capacity estimate ~\d+ is an upper bound\. ",
        message,
    ), message


def _l_corridor_with_50():
    scenario = load_scenario("assets/l_corridor")
    params = scenario.distributions[D]["parameters"]
    params.update(number=50, use_flow_spawning=False)
    return scenario


def test_unplaceable_agents_with_journeys_are_a_one_line_error(monkeypatch):
    """A deck with journeys reports the sampler's shortfall in one line (#508).

    ``assets/l_corridor`` spawns agents of radius 0.15 m in a 2.4 x 3 m
    room: the estimate admits 50, but under ``--seed 3`` the sampler
    places 49 of them.
    """
    scenario = _l_corridor_with_50()
    monkeypatch.setattr(cli, "load_scenario", lambda _path: scenario)
    monkeypatch.setattr(
        "sys.argv", ["pyfds-evac", "--scenario", "unused", "--seed", "3"]
    )
    with contextlib.redirect_stdout(io.StringIO()), pytest.raises(SystemExit) as exit_:
        cli.main()
    message = exit_.value.code
    assert isinstance(message, str)
    assert "\n" not in message
    assert re.match(
        rf"^pyfds-evac: error: Distribution '{D}': could not place the 50 "
        r"requested agents \(Only 49 of 50  could be placed\. .*\)\. "
        r"The capacity estimate ~50 is an upper bound\. ",
        message,
    ), message


def test_unplaceable_agents_with_journeys_keep_the_jupedsim_cause():
    with pytest.raises(simulation_init.SpawnCapacityError) as error:
        run_scenario(_l_corridor_with_50(), seed=3)
    assert isinstance(error.value.__cause__, jps.AgentNumberError)


def test_runtime_error_of_the_sampler_with_journeys_is_not_capacity(monkeypatch):
    def fail(**_kwargs):
        raise RuntimeError("sampler bug")

    monkeypatch.setattr(simulation_init.jps, "distribute_by_number", fail)
    with pytest.raises(RuntimeError, match="sampler bug"):
        run_scenario(_l_corridor_with_50(), seed=3)


def _main(monkeypatch, scenario, *args):
    monkeypatch.setattr(cli, "load_scenario", lambda _path: scenario)
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", "unused", *args])
    with contextlib.redirect_stdout(io.StringIO()):
        return cli.main()


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_export_only_reports_an_over_full_spawn_area_as_the_run(
    monkeypatch, with_journeys
):
    """``--print-summary --export-only`` stops with the run's line (#508)."""
    with pytest.raises(SystemExit) as run:
        _main(monkeypatch, _over_full(with_journeys))
    with pytest.raises(SystemExit) as export:
        _main(
            monkeypatch,
            _over_full(with_journeys),
            "--print-summary",
            "--export-only",
        )
    assert re.match(PATTERN, export.value.code), export.value.code
    assert export.value.code == run.value.code


@pytest.mark.parametrize(
    "extra",
    [{}, {"number": 500, "use_flow_spawning": True}],
    ids=["within-estimate", "flow-spawned"],
)
def test_export_only_passes_a_spawn_area_the_run_admits(monkeypatch, extra):
    scenario = _scenario(ENOUGH_S, **extra)
    assert _main(monkeypatch, scenario, "--print-summary", "--export-only") == 0


def _two_on_one_polygon(with_journeys: bool):
    """Two distributions of 50 over one 3 x 4 m polygon that holds ~84."""
    scenario = _over_full(with_journeys)
    raw = scenario.raw
    raw["distributions"][D]["parameters"]["number"] = 50
    raw["distributions"]["other"] = raw["distributions"][D]
    return raw, scenario.walkable_polygon


def test_capacity_check_counts_a_shared_polygon_once_without_journeys():
    """Without journeys the run seeds a shared polygon once, for everybody."""
    with pytest.raises(
        simulation_init.SpawnCapacityError,
        match=rf"^Distributions '{D}', 'other': requested 100 agents ",
    ):
        simulation_init._check_spawn_capacity(*_two_on_one_polygon(False))


def test_capacity_check_counts_each_distribution_with_journeys():
    simulation_init._check_spawn_capacity(*_two_on_one_polygon(True))


def _export_and_run_messages(monkeypatch, make_scenario):
    with pytest.raises(SystemExit) as run:
        _main(monkeypatch, make_scenario())
    with pytest.raises(SystemExit) as export:
        _main(monkeypatch, make_scenario(), "--print-summary", "--export-only")
    return export.value.code, run.value.code


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_export_only_checks_the_stored_number_of_a_fill_area_spawn(
    monkeypatch, with_journeys
):
    """The run checks ``number`` whatever the ``distribution_mode`` (#508)."""

    def fill_area():
        scenario = _over_full(with_journeys)
        scenario.distributions[D]["parameters"]["distribution_mode"] = "fill_area"
        return scenario

    export, run = _export_and_run_messages(monkeypatch, fill_area)
    assert re.match(PATTERN, export), export
    assert export == run


def test_export_only_checks_the_walkable_area_of_a_deck_without_spawn_areas(
    monkeypatch,
):
    """Without distributions the run fills the walkable area (#508)."""

    def no_spawn_areas():
        scenario = _scenario(ENOUGH_S)
        scenario.raw["distributions"] = {}
        scenario.sim_params["number"] = 500
        return scenario

    export, run = _export_and_run_messages(monkeypatch, no_spawn_areas)
    assert re.match(
        r"^pyfds-evac: error: Distribution '__walkable_area__': requested 500 "
        r"agents but area can hold at most ~\d+\. ",
        export,
    ), export
    assert export == run


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_refused_agent_is_a_one_line_error_without_capacity_advice(
    monkeypatch, with_journeys
):
    """An agent JuPedSim refuses to add is not a capacity problem (#508)."""

    def refuse(_self, _params):
        raise RuntimeError("Agent references unknown journey")

    def scenario():
        scenario = _scenario(ENOUGH_S)
        if not with_journeys:
            scenario.raw["journeys"] = []
            scenario.raw["transitions"] = []
        return scenario

    monkeypatch.setattr(jps.Simulation, "add_agent", refuse)
    with pytest.raises(SystemExit) as exit_:
        _main(monkeypatch, scenario())
    assert exit_.value.code == (
        f"pyfds-evac: error: Distribution '{D}': JuPedSim could not add an agent "
        "to the simulation (Agent references unknown journey)."
    )
    with pytest.raises(simulation_init.AgentInsertionError) as error:
        run_scenario(scenario())
    assert isinstance(error.value.__cause__, RuntimeError)
