"""Targeted FED decks for the dose-refusal path of route choice (#187 A2).

The stage-2 audit found ``fed_return_margin`` (0.9, a rival's FED limit as
a fraction of the threshold) inert on every fire deck: no route is ever
refused for dose there, and the largest predicted route dose is 0.18, far
below the (0.9, 1.0] band in which the margin acted. It was removed. These
decks are what the audit swept the margin over: ``run_scenario`` runs on
the t_junction assets and a synthetic FED rate field, built so that the
rival route's dose lies in (0.9, 1.0], where the margin would have refused
it. They stay as the regression for the FED-refusal path: a rival in that
band is admitted exactly as the current exit is.

Construction (t_junction: corridor y in [10, 13], exit A at x = 0.5, exit
B at x = 29.5, checkpoint at x = 18.5, spawn area at x in [18, 22] below
the corridor). Route foresight charges a segment the mean FED rate over the
points it samples along it (every ``sampling_step_m`` = 2 m, both ends
included) for its travel time at ``base_speed_m_per_s`` (1.3 m/s here), and
the agent's own leg pro rata to what is left of it (``evaluate_segment``,
``_first_leg_dose``). The field is time-stepped and piecewise constant:

* **Arm A** (x < 17, the corridor west of the junction): rate ``arm_rate``
  from ``t_on``. The checkpoint->A segment is 18 m, read at 10 points,
  x = 18.5, 16.5, ..., 0.5; the 9 with x < 17 lie in the arm, so its mean
  rate is 0.9 * ``arm_rate`` and the predicted dose of the rival route A
  for an agent east of the arm is ``0.9 * arm_rate * (18 / 1.3) / 60`` plus
  the dose already taken (about 0, the junction is clean). With
  ``arm_rate`` 4.5 /min that is 0.935: inside (0.9, 1.0], admitted as a
  rival.
* **Strip B** (23 <= x <= 29, the corridor just before exit B): rate
  ``strip_rate`` 30 /min from ``t_on``. The checkpoint->B segment is 11 m,
  read at 7 points, x = 18.5, 20.33, ..., 29.5; the 3 at x = 24.0, 25.83
  and 27.67 lie in the strip, so its mean rate is 30 * 3/7 = 12.86 and its
  full dose is 12.86 * (11 / 1.3) / 60 = 1.81; an agent on it is charged
  the remaining share, over 1.0 while it is more than 6.1 m from the exit.
  B is the
  current exit of every agent spawned before ``t_on`` (clear air chooses
  the nearer exit), and that route is refused for dose: the agent must
  flee it.

The agent turns back to A with reason ``fed_reroute`` and takes a dose
near 0.93 (walking at v0 1.2 m/s, slower than the 1.3 m/s the prediction
assumes, so the dose taken runs a little over the one predicted, and
congestion adds to it). With the margin it was held on B instead, walking
on into the strip: audited over 10 seeds on these decks, removing it
lowered the FED p95 from 2.83 to 2.11 and the agents at FED >= 1 from
20.5 to 7.3 per run, at the cost of more ``fed_reroute`` switches.

Agents already inside the strip at ``t_on`` are not a case for the band:
the excess stretch of their rival leg samples the strip and pushes A's
predicted dose over 1.0, and they take dose at 0.5/s as they walk on.

* ``near1_hold``: the field stays as it is; with constant rates and a
  self-consistent prediction the route A dose never crosses 1.0 after the
  switch.
* ``near1_rise``: at ``t_rise`` the arm rate rises to ``arm_rate_after``
  (8 /min) and the strip clears. An agent that switched onto A and is
  still in the arm then sees its current route over 1.0 while B is clean
  again, and flees back. With ``t_rise`` 6 s after ``t_on``, agents that
  switched at the junction are 1-5 m into the arm.

Run as a script with the ``run.py`` options (``--scenario``, ``--seed``,
``--output-*``) and ``--fed-deck NAME`` it runs one deck on the staged
scenario and writes the same outputs as ``run.py``, so
``scripts/margin_audit.py`` can sweep a margin over it. The script must
be run with this checkout first on ``PYTHONPATH``, as the harness does.
"""

from __future__ import annotations

import contextlib
import io
import math
import sys
from dataclasses import dataclass

import pytest
from test_rerouting_golden import (
    ASSETS,
    REPO,
    BlobField,
    Deck,
    _check_imported_from,
    _configure_scenario,
)

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.fed import DefaultFedInputs
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

ARM_X_MAX = 17.0
STRIP_X = (23.0, 29.0)
CORRIDOR_Y_MIN = 10.0
# Checkpoint->exit A segment length, the share of its sample points in the
# arm (9 of 10), the checkpoint->exit B segment length, the share of its
# sample points in the strip (3 of 7), and the routing block's base speed.
ARM_SEGMENT_M = 18.0
ARM_SAMPLE_SHARE = 9 / 10
STRIP_SEGMENT_M = 11.0
STRIP_SAMPLE_SHARE = 3 / 7
BASE_SPEED = 1.3
_CLEAN_AIR = DefaultFedInputs()


@dataclass(frozen=True)
class CorridorFed:
    """The piecewise constant FED rate field [1/min] described above.

    Serves route foresight (``sample_rate``) and the agents' dose
    (``advance``) from the same function, so prediction and exposure agree.
    """

    arm_rate: float
    strip_rate: float
    t_on: float
    t_rise: float = math.inf
    arm_rate_after: float = 0.0

    def rate(self, time_s: float, x: float, y: float) -> float:
        if time_s < self.t_on or y < CORRIDOR_Y_MIN:
            return 0.0
        risen = time_s >= self.t_rise
        if x < ARM_X_MAX:
            return self.arm_rate_after if risen else self.arm_rate
        if STRIP_X[0] <= x <= STRIP_X[1]:
            return 0.0 if risen else self.strip_rate
        return 0.0

    def sample_rate(self, time_s: float, x: float, y: float):
        return _CLEAN_AIR, self.rate(time_s, x, y)

    def advance(self, time_s, x, y, *, dt_s, current_fed):
        rate = self.rate(time_s, x, y)
        return _CLEAN_AIR, rate, float(current_fed) + rate * max(0.0, dt_s) / 60.0

    @property
    def rival_dose(self) -> float:
        """The predicted dose of route A from the junction, before t_rise."""
        mean_rate = self.arm_rate * ARM_SAMPLE_SHARE
        return mean_rate * (ARM_SEGMENT_M / BASE_SPEED) / 60.0

    @property
    def strip_dose(self) -> float:
        """The full predicted dose of the checkpoint->B segment."""
        mean_rate = self.strip_rate * STRIP_SAMPLE_SHARE
        return mean_rate * (STRIP_SEGMENT_M / BASE_SPEED) / 60.0


@dataclass(frozen=True)
class FedDeck(Deck):
    """A golden-style deck with a FED rate field instead of smoke."""

    fed: CorridorFed | None = None

    def describe(self) -> dict:
        return {**super().describe(), "fed": vars(self.fed) if self.fed else None}


_HOLD = CorridorFed(arm_rate=4.5, strip_rate=30.0, t_on=15.0)
_RISE = CorridorFed(
    arm_rate=4.5, strip_rate=30.0, t_on=15.0, t_rise=21.0, arm_rate_after=8.0
)
_TJ = "t_junction/config_full.json"


def _deck(fed: CorridorFed, cost_model: str) -> FedDeck:
    # Spawning ends before t_on so that every agent chose B in clear air;
    # the first ones spawned reach B at about t_on.
    return FedDeck(_TJ, cost_model, (), agents=30, flow_end_s=10.0, fed=fed)


FED_DECKS: dict[str, FedDeck] = {
    "near1_hold_gate": _deck(_HOLD, "gate"),
    "near1_hold_additive": _deck(_HOLD, "additive"),
    "near1_rise_gate": _deck(_RISE, "gate"),
    "near1_rise_additive": _deck(_RISE, "additive"),
}


def run_fed_deck(
    deck: FedDeck,
    scenario,
    *,
    seed: int,
    collect_costs: bool = False,
):
    """Run *deck* on *scenario*; the caller owns the result's cleanup."""
    scenario = _configure_scenario(scenario, deck)
    routing = {**scenario.raw.get("routing", {}), "cost_model": deck.cost_model}
    if deck.anticipate is not None:
        routing["anticipate"] = deck.anticipate
    cost_config = RouteCostConfig.from_routing_params(routing)
    smoke = SmokeSpeedModel(
        BlobField(()), SmokeSpeedConfig(fds_dir=".", update_interval_s=1.0)
    )
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(
            scenario,
            seed=seed,
            smoke_speed_model=smoke,
            fed_model=deck.fed,
            reroute_config=RerouteConfig(
                reevaluation_interval_s=1.0, cost_config=cost_config
            ),
            collect_route_cost_history=collect_costs,
        )


# ── Tests ─────────────────────────────────────────────────────────────


def _switches(result, reason: str) -> list[dict]:
    return [r for r in result.route_history or [] if r["reason"] == reason]


def _rival_refusals_in_band(result) -> list[dict]:
    """Rival rows refused for dose with the dose inside (0.9, 1.0]."""
    return [
        r
        for r in result.route_cost_history or []
        if r["current_exit"]
        and r["exit_id"] != r["current_exit"]
        and r["rejected"]
        and str(r["rejection_reason"]).startswith("FED")
        and 0.9 < float(r["fed_max_route"]) <= 1.0
    ]


def _rival_rows_in_band(result) -> list[dict]:
    """Rival rows evaluated with the dose inside (0.9, 1.0]."""
    return [
        r
        for r in result.route_cost_history or []
        if r["current_exit"]
        and r["exit_id"] != r["current_exit"]
        and 0.9 < float(r["fed_max_route"]) <= 1.0
    ]


def _left_b(result) -> list[dict]:
    """The switches that fled exit B for dose."""
    return [
        r for r in _switches(result, "fed_reroute") if r["old_exit"] == "exit_B_right"
    ]


def _flee_backs(result) -> set[int]:
    """Agents that switched onto a route for dose and then fled it for dose."""
    seen: dict[int, str] = {}
    fled_back = set()
    for row in _switches(result, "fed_reroute"):
        agent = row["agent_id"]
        if seen.get(agent) == row["old_exit"]:
            fled_back.add(agent)
        seen[agent] = row["new_exit"]
    return fled_back


@pytest.mark.parametrize("name", sorted(FED_DECKS))
def test_rival_dose_is_in_the_former_margin_band(name):
    """The construction: the rival route's predicted dose sits in (0.9, 1.0]."""
    fed = FED_DECKS[name].fed
    assert fed is not None
    assert 0.9 < fed.rival_dose <= 1.0
    assert fed.strip_dose > 1.0


def _run(name: str, seed: int):
    deck = FED_DECKS[name]
    scenario = load_scenario(str(ASSETS / deck.config))
    return run_fed_deck(deck, scenario, seed=seed, collect_costs=True)


@pytest.mark.parametrize("name", ["near1_hold_gate", "near1_rise_gate"])
def test_rival_in_the_band_is_admitted(name):
    """A rival with dose in (0.9, 1.0] is not refused; agents flee B for A.

    The refused exit B is fled with reason ``fed_reroute`` (#187 A2: the
    0.9 margin used to refuse A and hold the agents on B).
    """
    result = _run(name, seed=11)
    try:
        assert result.success
        assert _rival_rows_in_band(result)
        assert not _rival_refusals_in_band(result)
        assert len(_left_b(result)) >= 5
    finally:
        result.cleanup()


def test_rise_deck_makes_agents_flee_back():
    """On the rise deck agents that took route A for dose turn back for dose."""
    result = _run("near1_rise_gate", seed=11)
    try:
        assert _flee_backs(result)
    finally:
        result.cleanup()


def test_the_removed_margin_key_stops_a_deck_run():
    """A scenario that still sets fed_return_margin is refused (#187 A2)."""
    deck = FED_DECKS["near1_hold_gate"]
    scenario = load_scenario(str(ASSETS / deck.config))
    scenario.raw.setdefault("routing", {})["fed_return_margin"] = 0.9
    with pytest.raises(ValueError, match=r"fed_return_margin was removed in #187"):
        run_fed_deck(deck, scenario, seed=11)


def test_harness_writes_the_requested_cost_history(tmp_path):
    """--output-route-cost-history reaches the deck run and writes the CSV."""
    out = tmp_path / "costs.csv"
    code = main(
        [
            "--scenario",
            str(ASSETS / FED_DECKS["near1_hold_gate"].config),
            "--seed",
            "11",
            "--fed-deck",
            "near1_hold_gate",
            "--output-route-cost-history",
            str(out),
        ]
    )
    assert code == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) > 1


# ── Harness entry point ───────────────────────────────────────────────


def main(argv: list[str]) -> int:
    """Run one deck on a staged scenario with run.py's options and outputs."""
    from pyfds_evac.cli import _build_parser
    from pyfds_evac.core.run_outputs import apply_outputs, summary_line

    _check_imported_from(REPO)
    parser = _build_parser()
    parser.add_argument("--fed-deck", required=True, choices=sorted(FED_DECKS))
    args = parser.parse_args(argv)
    scenario = load_scenario(args.scenario)
    result = run_fed_deck(
        FED_DECKS[args.fed_deck],
        scenario,
        seed=args.seed,
        collect_costs=bool(args.output_route_cost_history),
    )
    try:
        print(summary_line(result))
        apply_outputs(result, scenario, args, log=print)
    finally:
        result.cleanup()
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
