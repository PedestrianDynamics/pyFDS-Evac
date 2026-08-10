# Cognitive-map test strategy — trustworthy results for the talk

**Goal.** Full confidence that the cognitive-map/discovery pipeline works as
specified, ahead of a talk in September 2026. "Full confidence" means: every
rule of the model is pinned by a test that fails when the rule breaks, the
integration between rules is exercised on uncurated geometry, and the known
remaining risks are listed rather than implied.

## What exists already (do not duplicate)

| Area | Where |
| --- | --- |
| Perception acquisition vs persistence (memory) | `tests/test_cognitive_map_memory.py` |
| Blind spawn, frontier hops, position-aware frontier ties | `tests/test_blind_spawn_discovery.py` |
| Vis-gated arrival, reverse-edge learning, no invented exit reverses | `tests/test_blind_spawn_discovery.py` (PR #96) |
| Visited-based frontier, explore/wander commitment, patrol-home | `tests/test_route_graph.py` (PR #96) |
| Initial exit choice from the map, not geometry | `tests/test_initial_exit_from_cognitive_map.py` |
| History replay equals engine state | `tests/test_cognitive_map_history.py` |
| Familiarity tiers and scalar draw plumbing | `tests/test_familiarity_routing.py`, `tests/test_scalar_familiarity.py` |
| Verification-grade map checks | `tests/verification/test_cognitive_map_verif.py` |
| Invariants on generated worlds (this PR) | `tests/test_generated_worlds.py` |

## Risk map (ordered by cost of being wrong on stage)

1. **Through-wall knowledge** — an agent uses an exit it could never have
   seen. Would invalidate the headline claim of the talk. *Covered*: unit
   tests + the generated-world evidence invariant (every learned node was
   sign-visible from the agent's position or physically adjacent).
2. **Silent stall / infinite loop** — an agent freezes or shuttles although
   it has somewhere informative to go. *Covered* for the failure modes found
   in PR #96; *gap*: no test asserts "an agent with a reachable unvisited
   frontier never stands idle for more than one reevaluation interval".
3. **Wander patrol walking through an exit** — `_undirected_known_path`
   builds paths over symmetric known edges; a known exit could appear as an
   intermediate hop, and stepping into an exit stage evacuates the agent.
   Reachable only when an exit is known but every route to it was rejected
   (e.g. smoke), so rare — but it would silently *shorten* egress. *Gap*.
4. **Familiarity semantics** — `full` must equal classical shortest-path
   behaviour; scalar `p` must yield ≈ p fraction of agents knowing each exit.
   *Partly covered* (tier plumbing); *gap*: no equivalence test full-vs-
   no-cognitive-map, no statistical test of the scalar draw.
5. **Multi-agent isolation** — one agent's learning must never leak into
   another's map. *Gap*: all current behavioural tests are single-agent.
6. **Flow-spawned agents** — two map-initialisation sites claim to produce
   identical maps for the same agent (`_assign_initial_exit` vs reroute
   pass). *Gap*: asserted in a comment, not a test.
7. **Smoke-coupled discovery** — under a time-varying extinction field,
   acquisition must stop where visibility ends and resume when it clears.
   *Partly covered* in clear air; *gap*: no FDS-coupled discovery test.
8. **Sign-position offsets** — audits flag "sign visible, centroid not";
   benign today, but nothing pins that node visibility means *sign*
   visibility. Low risk; document rather than test.

## Layered plan

- **Unit** (fast, per-rule): close gaps 3 and 6 with direct tests on
  `wander_target` (exit never an intermediate hop — likely needs a fix, not
  just a test) and on the two init sites (identical map for identical seed).
- **Integration** (engine runs on small decks): close gaps 2, 4, 5 —
  no-idle-with-reachable-frontier watchdog; `full` agent's route equals the
  no-cognitive-map route on the same deck; a 2-group run (staff + visitors)
  asserting per-agent map sizes never cross-contaminate.
- **Statistical** (seeded, aggregate): scalar familiarity draw — over ~200
  seeded map initialisations, exit-known fraction within a binomial
  tolerance of p (mutation-tested: breaking the draw must fail it).
- **End-to-end** (generated worlds, this PR): invariants on uncurated
  geometry; extend later with a smoke-coupled seed once gap 7 is addressed.

## Test cases to add (priority order)

1. `wander_target` never returns a path with an exit as an intermediate node
   (and engine fix if it can).
2. Watchdog: agent with reachable unvisited frontier receives a switch
   within one reevaluation interval (regression net over PR #96's class of
   bugs).
3. Full-familiarity equivalence: same deck, `familiarity=full` vs
   `reroute_config` without cognitive maps — same exit chosen, comparable
   egress (aggregate, not bit-exact; coupled runs are not reproducible).
4. Two-group isolation: visitors' maps grow, staff maps stay complete, no
   agent's known set ever contains a node only another agent could have
   perceived at that time.
5. Init-site parity: `init_cognitive_map` called from both sites with the
   same seed yields identical maps.
6. Scalar familiarity statistics (binomial band, fixed seeds).
7. Smoke-coupled discovery on one FDS-backed deck (acquisition stops in
   smoke, resumes in clear air) — needs an FDS fixture; schedule last.

## Non-test controls

- The per-run audit (`audit_worlds.py` pattern) stays the pre-talk gate for
  any world shown publicly: learning-evidence check + egress table.
- Videos remain the human check: sign arrows + amber wander phases make
  violations visible even where no assertion looks.

## Out of scope

Multi-storey knowledge, agent-to-agent knowledge exchange, forgetting.
