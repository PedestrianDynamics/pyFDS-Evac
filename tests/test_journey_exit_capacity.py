"""A journey deck prices each exit with its own ``capacity_agents_per_s`` (#394).

Route pricing charges an exit's queue as the agents counted there divided
by its capacity in agents per second, the deck's ``capacity_agents_per_s``
or else ``routing.default_exit_capacity`` (1.3). Before #394 the set-up
with journeys left the key out of the exit's stage data, so every exit of
a journey deck was priced at 1.3 agents/s; the set-up without journeys
carried it.

The deck is the synthetic room of ``test_run_outcome``, its exit given a
capacity of 0.5 agents/s, run with rerouting, a queue weight and the
route-cost history.
"""

from __future__ import annotations

import contextlib
import io

import pytest
from test_run_outcome import ENOUGH_S, SEED, _scenario

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import run_scenario

CAPACITY = 0.5


def _priced_rows(with_journeys: bool) -> list[dict]:
    scenario = _scenario(ENOUGH_S)
    scenario.raw["exits"]["E"]["capacity_agents_per_s"] = CAPACITY
    if not with_journeys:
        scenario.raw["journeys"] = []
        scenario.raw["transitions"] = []
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(
            scenario,
            seed=SEED,
            reroute_config=RerouteConfig(
                reevaluation_interval_s=1.0, cost_config=RouteCostConfig(w_queue=1.0)
            ),
            collect_route_cost_history=True,
        )
    try:
        assert result.agents_remaining == 0
        return list(result.route_cost_history or [])
    finally:
        result.cleanup()


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_exit_is_priced_with_its_capacity(with_journeys):
    rows = _priced_rows(with_journeys)
    assert rows, "no route was priced"
    # Before #394, with journeys: exit_capacity 1.3 on every row.
    assert {row["exit_capacity"] for row in rows} == {CAPACITY}
    for row in rows:
        assert row["queue_time_s"] == pytest.approx(row["exit_count"] / CAPACITY)
    assert any(row["queue_time_s"] > 0 for row in rows)
