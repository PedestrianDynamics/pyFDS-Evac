# Incapacitation is an absorbing state

Design for pyFDS-Evac, 2026-10-17. Issues #145, #593, #141. Replaces the
"fix the premovement write-back" reading of #145 with a single rule.

## Intent

The maintainer's rule: incapacitated means dead. A dead agent does not move,
is not removed, and causes no further model side effects. It stays where it
collapsed until the run ends, and the run's results say so.

Why now: the G3 removal study (profiling package, branch `g3-removal`,
invalid first `nss` arm, 2026-10-17) incapacitated every agent and they still
walked out when their premovement time ended. The same defect was reproduced
twice before (#145, #258). The exit-removal path (#593) and the
evacuation-time metric (#141) are the same rule seen from two other sides.

## Goal

After an agent enters `incapacitated_agents` in `run_scenario`
(`pyfds_evac/core/scenario.py`, the gas/heat threshold test, today around
line 3107), nothing in pyFDS-Evac writes to that agent again, and the run's
metrics never count it as evacuated.

## Scope: state on disk (2026-10-17, `main` at ed806ff7)

Sites in `pyfds_evac/core/scenario.py` that act on agents after
incapacitation. Line numbers are from `main` today and will drift.

| Site | Today | Required |
|---|---|---|
| Premovement activation, ~2908–2927 | Writes `desired_speed` and `speed_state["original_speed"]` for any agent whose premovement time has passed. No incapacitation check. **This is #145.** | Skip agents in `incapacitated_agents`. Their premovement entry stays `activated = False`; nothing is written. |
| Frantzich smoke speed update, ~2938 | Already skips incapacitated agents. | Unchanged. Keep the test. |
| Exposure loop (gas FED, heat FED, FIC), ~3010–3220 | Keeps sampling and advancing dose for an agent after it is incapacitated (`incapacitated_now` only gates the threshold test and the FIC factor). The exposure history keeps growing. | Stop sampling at incapacitation: the loop `continue`s for agents already in `incapacitated_agents` before any sampler call. The exposure record for that agent ends with the row that recorded `incapacitated = True`. |
| `update_checkpoint_speed` calls, ~3368, 3415, 3435, 3525 and `apply_fic_factor`-style restorations in `direct_steering_runtime.py` | Rely on the baseline pin (`original_speed = 0.0`, factors 1.0) written at incapacitation so the restore computes 0. Correct only as long as nothing resets the pin (which #145 does). | Keep the pin, and additionally skip these calls for incapacitated agents so no write happens at all. The pin stays as defence in depth. |
| Direct-steering stage loop, ~3401–3560 (target assignment, looking, `reached_stage`, exit removal with `mark_agent_for_removal` at ~3497, waiting, `_arrive`) | Processes incapacitated agents like any other. An agent that collapses within reach of an exit is removed and counted as evacuated. **This is #593.** | `continue` for incapacitated agents at the top of the per-agent loop body, after `current_position` is recorded. No target change, no look, no arrival, no removal. |
| Reroute passes: the per-agent loops at ~3261 (route-cost pass, `for agent in simulation.agents()`) and ~3349 (closed-exit pass); the helpers `_reevaluate` (~2239) and `_redirect_from_closed_exit` (~2395) are called from there | Evaluate routes for every agent in `agent_wait_info`. | Skip incapacitated agents before any route evaluation or `evaluate_and_reroute` call. No route history rows after incapacitation. |
| Flow spawning | Unaffected (acts on agents not yet in the simulation). | Unchanged. |
| Loop termination, ~2487–2530 and metrics, ~3604–3660 | Loop ends only when `agent_count() == 0`; `evacuation_time` is the time limit whenever an agent is incapacitated; `agents_evacuated = total − remaining` counts a removed dead agent as evacuated. **This is #141 and the counting half of #593.** | See Decisions 6–8. |
| `frame_recorder.after_step` / `finish` | Already receive the incapacitated set. | Unchanged. |

JuPedSim exit stages: agents headed for a non-throttled exit ride a JuPedSim
journey `[exit_stage]` (`simulation_init.py:2518` `add_exit_stage`,
`exit_to_journey` at ~3113; flow agents at `scenario.py:~2674`, nearest-exit
initial agents at `simulation_init.py:~3556`). JuPedSim removes those agents
itself when they enter the exit polygon (`plan_view.py:246-252`,
`removed_agents()`); `mark_agent_for_removal` is only the direct-steering
path (throttled exits, direct-steering decks). A dead agent with desired
speed 0 can still be displaced by the operational model into an exit
polygon. That displacement is JuPedSim's behaviour and stays; the removal is
prevented by Decision 3b.

## Decisions

1. **One predicate, applied at every site.** Each site listed above tests
   `agent_id in incapacitated_agents` and skips. No new state, no flag on
   the agent. The set is the single source of truth, as today.
2. **No motion.** No call to `set_agent_desired_speed` or any
   `direct_steering_runtime` speed function with an incapacitated agent after
   the zero write at incapacitation. The baseline pin written at
   incapacitation stays.
3. **No removal.** `mark_agent_for_removal` is never called for an
   incapacitated agent. `frame_recorder.leaves` is never called for one.
3b. **No removal by JuPedSim either.** At incapacitation, an agent on a
   JuPedSim exit-stage journey is switched (`switch_agent_journey`) to the
   global direct-steering journey, which JuPedSim never removes at. That
   journey is therefore created in every run (today `simulation_init.py:1766`
   creates it only with direct steering) and its id is passed to
   `run_scenario`. Maintainer, 2026-10-17: in the station example agents died
   just short of the exit and blocked the way for others; removing them
   would be wrong. `simulation.removed_agents()` is still read each step for
   `last_exit_time` (Decision 8) and, as a check, any incapacitated id found
   there raises the invariant error of Decision 6.
4. **No model side effects.** No reroute evaluation, no exit choice, no
   target assignment, no look, no stage arrival, no wait sampling, no
   premovement activation for an incapacitated agent.
5. **Sampling stops; the record freezes.** No extinction, FED, heat or FIC
   sample is taken for an incapacitated agent after the step in which it was
   incapacitated. The exposure history and the smoke history for that agent
   end at that step. (Maintainer, 2026-10-17.)
6. **Counting.** `agents_evacuated` counts agents that left through an
   exit: `total_agents − remaining`, where `remaining` includes the
   incapacitated agents because they are never removed. Add the invariant
   `agents_incapacitated <= agents_remaining`, asserted at the end of the run
   (a violation is a bug, raised as an error, not logged).
7. **Completion.** A run with incapacitated agents is `incomplete`; the
   existing rule `completed = remaining == 0 and not_spawned == 0` already
   gives that once dead agents are never removed. `end_reason` gains a value
   `all_mobile_left` for the case in Decision 8.
8. **Loop termination (#141).** The main loop also ends when every mobile
   agent has left: `agent_count() == len(incapacitated_agents)` and all
   agents are spawned. `evacuation_time` is then the time of that step, not
   the time limit. `metrics` gains `last_exit_time` (time of the last
   `mark_agent_for_removal`, or `None` if nobody left). `evacuation_time`
   keeps its name and meaning (time the loop ended).
   `last_exit_time` is updated from both `mark_agent_for_removal` and
   `simulation.removed_agents()`. Maintainer, 2026-10-17: stop early; there
   is no point simulating when everyone left alive has left. Consequences
   accepted: every other agent's history ends at that step;
   `tests/test_fds_horizon.py:~470` (asserts `evacuation_time == 300.0` on
   a run with incapacitation) is rewritten to exercise the horizon another
   way or to assert the new value; the front ends (`config/frontend.py`
   `run_outcome`, `config/events.py`, `config/script.py`, TUI snapshots)
   learn the new `end_reason` with the wording "Incomplete: all mobile
   agents left, N incapacitated inside".
9. **Tests, one per guard**, each failing on `main` today:
   - premovement: agent incapacitated at t < premovement time stays at speed
     0 and at its position after the premovement time (#145);
   - exit reach: agent incapacitated inside the exit reach is not removed,
     `agents_evacuated` excludes it, `agents_incapacitated <=
     agents_remaining` (#593);
   - exposure: no exposure rows for the agent after the incapacitation row;
   - reroute: no route-history rows for the agent after incapacitation;
   - checkpoint/steering zone: an incapacitated agent inside a speed zone
     stays at 0;
   - termination: corridor with a lethal field for part of the agents,
     `evacuation_time < max_simulation_time`, `last_exit_time` set, counts
     correct (#141).
   Golden and equivalence tests (`tests/test_rerouting_golden.py`,
   `tests/test_routing_refactor_equivalence.py`) must stay bit-identical:
   their decks incapacitate nobody, so skipping dead agents changes nothing
   there. Verify by running them.
10. **Docs.** `docs/limitations.md:~122-134`, `docs/howto-rset-ensemble.md:~39-45`,
    `docs/outputs.md:~69,225,233-236` and `docs/concepts.md` describe the current behaviour
    and get a short paragraph: incapacitated agents stay, are never counted as
    evacuated, their exposure record ends at incapacitation, and the loop
    ends when every mobile agent has left. CHANGELOG entry under Unreleased.
11. **DESIGN_PRINCIPLES.md §9** is answered briefly in the PR (minor
    change rule, item 6): what is fixed (the absorbing rule), validity
    (any tenability model that writes `incapacitated_agents`), verification
    (the tests above), what could go wrong (a new write site added later
    without the guard; mitigated by the end-of-run invariant and by routing
    every speed write through `direct_steering_runtime`).

## Non-goals

- No change to how or when incapacitation is decided (thresholds, FED
  models, heat model).
- No change to JuPedSim's operational model; a dead agent may still be
  displaced by neighbours.
- No new per-agent state object; no refactor of `run_scenario`.
- No change to the profiling package.
- No change to #243 (rerouting cost); that plan waits for its own finish
  line.

## Anti-goals

- A dead agent that walks, is removed, or is counted as evacuated after this
  change, under any setting (premovement, smoke speed, FIC, steering zones,
  checkpoints, rerouting, flow spawning).
- A golden trajectory that changes on a deck without incapacitation.

## Constraints

- Smallest correct change; guards at the existing sites, following the
  pattern already used by the Frantzich block (`if agent_id in
  incapacitated_agents: continue`).
- Backend team workflow: backend-model writes the contract (§9 answers),
  backend-engineer implements with tests, backend-qa verifies that each test
  fails before and passes after.
- Tests run with `.venv/bin/python -m pytest`, not `uv run pytest`.
- `ruff` and `mypy` clean; the pre-commit hook runs.

## Left to the builder

- Exact placement of each guard and whether one helper predicate is worth
  it (probably not; the set test is one line).
- Fixture decks for the tests (reuse the corridor and CO fixtures that
  `tests/test_iso_table21_coupled.py` and `tests/test_smoke_blind.py` use
  if they fit).
- Whether `last_exit_time` is also written to the run manifest.

## Open questions for the maintainer

None. Both questions from the builder check were answered on 2026-10-17
(Decisions 3b and 8).

## Risks / review focus

1. A guard placed after a write instead of before it.
2. The exposure guard placed so that the incapacitating step itself is not
   recorded (the row with `incapacitated = True` must still be written).
3. The reroute guard changing the route-history row order for other agents
   (it must not; dead agents are only skipped).
4. Early termination (Decision 8) interacting with flow spawning: all
   sources must be exhausted before the mobile-agents test applies.
5. The end-of-run invariant raising on an existing deck that removes agents
   by some path not listed here. That would be a finding, not a reason to
   soften the invariant.
