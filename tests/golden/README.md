# Golden and snapshot inventory

Every stored expected output in `tests/`, tagged by what it can prove (see
[testing guidelines §5](../../docs/TESTING_GUIDELINES.md#5-goldens-and-snapshots)).
A pull request that changes any artifact below has a `Golden re-record:`
section with the evidence the guidelines ask for.

None of these artifacts is checked against a source outside the code, so
none is tagged `independent-truth`. Each was recorded from the code itself
and shows that output changed, not that it is right. Truth-backed checks
that some consumer files also make are listed under "Assertions besides the
snapshot".

## Artifacts

| Artifact | Tag | Consumer | Recorded from | Regenerate |
|---|---|---|---|---|
| `tests/golden/cli_options.json` | `regression-only` | `tests/test_cli_help.py` | The option table of 0.2.1 (`cli._build_parser()`), plus the flags added since | No regeneration switch; edit it by hand for a deliberate flag change |
| `tests/golden/rank_routes/*.json` (36) | `regression-only` | `tests/test_rerouting_golden.py` | `rank_routes` on hand-built graphs, one case per ordering, rejection and fallback branch | `PYFDS_EVAC_REGEN_GOLDEN=1` |
| `tests/golden/evaluate_and_reroute/*.json` (34) | `regression-only` | `tests/test_rerouting_golden.py` | `evaluate_and_reroute`, one case per decision branch | `PYFDS_EVAC_REGEN_GOLDEN=1` |
| `tests/golden/scenarios/<platform>/*.json` (15 per platform) | `regression-only` | `tests/test_rerouting_golden.py` | `run_scenario` on small decks with a synthetic extinction field; stored per platform because JuPedSim builds differ in the last bits | `PYFDS_EVAC_REGEN_GOLDEN=1`; the `linux-x86_64` set in the Docker command of the test module |
| `tests/golden/routing_decisions/*.json` (10) | `regression-only` | `tests/test_routing_decisions.py` | The decision cases, variants, threshold-equality cases, anchor and must-flee table and shared-cache passes, with every sample and cache write | `PYFDS_EVAC_REGEN_GOLDEN=1` |
| `tests/verification/golden/heat_default/fed_history.csv`, `manifest.json` | `regression-only` | `tests/verification/test_heat_endpoint_coupled.py` | A default-mode heat run at commit 76c9a76 (SFPE Eq. 63.44), reseeded since; see its [README](../verification/golden/heat_default/README.md) | `make_baseline.py`, `reseed_baseline.py` there |
| `tests/__snapshots__/test_tui/*.raw` (8) | `presentation-snapshot` | `tests/test_tui.py` (`snap_compare`) | Rendered TUI screens per theme | `uv run pytest tests/test_tui.py --snapshot-update` |

`heat_default` uses the SFPE temperature history as the run's input, not as
the expected output: the stored FED values come from the code at 76c9a76.

## Assertions besides the snapshot

Consumer files also hold explicit tests next to the snapshot comparison
(for example each decision branch in `test_routing_decisions.py`). Those
tests are not part of the artifacts above and are classified where they
are written. Converting cheap, derivable snapshot values into such
hand-computed assertions is tracked in #810.

## Files that reuse a golden deck or helper

These files import builders or decks from `test_rerouting_golden` (or
mention a golden in a docstring) and assert their own expectations. They
do not read any artifact above and are not consumers of golden data.

`test_direct_steering_fallbacks.py`, `test_fallback_hold.py`,
`test_fallback_tau_hold.py`, `test_fed_margin_deck.py`,
`test_foresight_arrival_time.py`,
`test_must_flee_lethal_route.py`, `test_route_assessment.py`,
`test_spawn_key_seeding.py`, `test_switch_reasons.py`, `test_walk_dose.py`,
`verification/test_heat_total_flux_coupled.py`.

Tests of the golden tooling, not consumers: `test_golden_rerouting_script.py`
(`scripts/golden_rerouting.py`, the base-versus-head harness) and
`test_routing_differential_script.py` (`scripts/routing_differential.py`, on
synthetic dumps).

In `test_webapp.py`, `test_flow_source_due.py` and
`test_flow_spawn_spacing.py`, "snapshot" means a saved run configuration or
a loop state, not a stored expected output.
