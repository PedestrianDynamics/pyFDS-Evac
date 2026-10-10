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
import json
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
def test_export_only_ignores_the_number_of_a_percentage_spawn(
    monkeypatch, with_journeys
):
    """A percentage mode fills its share of the area, whatever ``number`` (#436)."""

    def fill_area():
        scenario = _over_full(with_journeys)
        params = scenario.distributions[D]["parameters"]
        params.update(distribution_mode="fill_area", percentage=50)
        return scenario

    assert _main(monkeypatch, fill_area(), "--print-summary", "--export-only") == 0


def test_export_only_sums_percentage_spawns_sharing_a_polygon(monkeypatch):
    """Two 60 % areas on one polygon over-fill it, as the run finds (#436).

    The 3 x 4 m area holds ~84 agents of radius 0.15 m; 60 % is 50 each.
    """

    def two_at_60():
        scenario = _scenario(ENOUGH_S)
        scenario.raw["journeys"] = []
        scenario.raw["transitions"] = []
        params = scenario.distributions[D]["parameters"]
        params.update(distribution_mode="by_percentage", percentage=60)
        scenario.raw["distributions"]["other"] = json.loads(
            json.dumps(scenario.distributions[D])
        )
        return scenario

    export, run = _export_and_run_messages(monkeypatch, two_at_60)
    assert re.match(
        rf"^pyfds-evac: error: Distributions '{D}', 'other': requested 100 "
        r"agents but area can hold at most ~84\. ",
        export,
    ), export
    assert export == run


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_export_only_checks_the_initial_agents_of_a_flow_schedule(
    monkeypatch, with_journeys
):
    """Both check ``initial_number`` beside a schedule, not ``number`` (#390)."""

    def scheduled():
        scenario = _over_full(with_journeys)
        scenario.set_flow_schedule(
            D,
            [{"flow_start_time": 0, "flow_end_time": 600, "number": 5}],
            keep_initial_agents=True,
        )
        return scenario

    assert scheduled().distributions[D]["parameters"]["number"] == 5
    export, run = _export_and_run_messages(monkeypatch, scheduled)
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


def test_export_only_skips_a_spawn_polygon_the_run_skips(monkeypatch):
    """A self-intersecting spawn polygon is warned about and skipped (#508).

    With journeys the run skips a distribution it cannot process; the
    export check skips it too instead of failing on the invalid polygon.
    """
    scenario = _scenario(ENOUGH_S)
    bow = [[1.1, 1.1], [3.9, 4.9], [3.9, 1.1], [1.1, 4.9], [1.1, 1.1]]
    scenario.raw["distributions"]["bow"] = {
        **scenario.raw["distributions"][D],
        "coordinates": bow,
    }
    assert _main(monkeypatch, scenario, "--print-summary", "--export-only") == 0


def test_export_only_counts_a_fill_mode_as_an_upper_bound(monkeypatch):
    """An ``until_full`` area beside an exact count on one polygon passes (#436).

    Without journeys, the exact 80 of ~84 are checked; the fill mode
    takes what is left, up to its own count.
    """

    def shared():
        scenario = _scenario(ENOUGH_S, number=80)
        scenario.raw["journeys"] = []
        scenario.raw["transitions"] = []
        other = json.loads(json.dumps(scenario.distributions[D]))
        other["parameters"]["distribution_mode"] = "until_full"
        scenario.raw["distributions"]["other"] = other
        return scenario

    assert _main(monkeypatch, shared(), "--print-summary", "--export-only") == 0


def test_run_reports_what_a_fill_mode_placed():
    """The result and its summary line give placed of the upper bound (#436)."""
    from pyfds_evac.core.run_outputs import summary_line

    scenario = _scenario(ENOUGH_S, distribution_mode="fill_area", percentage=20)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario)
    assert result.fill_placement == {D: {"placed": 16, "upper_bound": 16}}
    assert summary_line(result).endswith(f" '{D}' placed 16 of at most 16.")


def test_export_only_skips_malformed_spawn_coordinates_the_run_skips(monkeypatch):
    """Coordinates that are not numbers are skipped as by the run (#118)."""
    scenario = _scenario(ENOUGH_S)
    scenario.raw["distributions"]["bad"] = {
        **scenario.raw["distributions"][D],
        "coordinates": [[None, 0], [1, 0], [0, 1]],
    }
    assert _main(monkeypatch, scenario, "--print-summary", "--export-only") == 0


def _scheduled(with_journeys, window):
    scenario = _scenario(ENOUGH_S)
    if not with_journeys:
        scenario.raw["journeys"] = []
        scenario.raw["transitions"] = []
    scenario.distributions[D]["parameters"]["flow_schedule"] = [window]
    return scenario


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
@pytest.mark.parametrize(
    ("window", "message"),
    [
        (
            {"flow_start_time": 0, "flow_end_time": 0.02, "number": 3},
            r"window \[0, 0\.02\] s is too short for 3 agents",
        ),
        (
            {"flow_start_time": 0, "flow_end_time": 10, "number": 900},
            r"flow rate of 90\.0 agents/s exceeds area capacity",
        ),
    ],
    ids=["too-short", "too-fast"],
)
def test_export_only_checks_the_flow_windows_as_the_run(
    monkeypatch, with_journeys, window, message
):
    """--export-only refuses the windows the run refuses, in one line (#390)."""
    export, run = _export_and_run_messages(
        monkeypatch, lambda: _scheduled(with_journeys, window)
    )
    assert re.match(rf"^pyfds-evac: error: Distribution '{D}': .*{message}", export)
    assert export == run


@pytest.mark.parametrize("args", [(), ("--export-only",), ("--print-summary",)])
def test_an_unreadable_flow_schedule_is_a_one_line_error(monkeypatch, args):
    """A spawn area's schedule error ends the CLI in one line (#390)."""
    scenario = _scheduled(
        True, {"flow_start_time": -1, "flow_end_time": 5, "number": 2}
    )
    with pytest.raises(SystemExit) as exit_:
        _main(monkeypatch, scenario, *args)
    message = exit_.value.code
    assert isinstance(message, str) and "\n" not in message
    assert message.startswith(
        f"pyfds-evac: error: Distribution '{D}': flow_schedule: Invalid flow window"
    ), message
