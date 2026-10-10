"""An over-full spawn area stops ``pyfds-evac`` with one line (#692).

The deck is the 10 x 6 m room of ``test_run_outcome``; its 3 x 4 m spawn
area holds far fewer than 500 agents of radius 0.15 m. A deck with
journeys places agents distribution by distribution; one without them
seeds each spawn area once (``_seed_shared_areas``). Both report the
distribution, the requested count and the capacity.

A count within the estimate can still fail when the sampler cannot place
everyone; that is reported in one line as well (#702).
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
