# Component verification suite

Verification (*"are the equations solved correctly?"*) for the coupled
pyFDS-Evac engine, against hand-computable references. This is distinct from
behavioural **validation** of human decision-making, which is out of scope here.
See [`specs/012-model-verification/SPEC.md`](../../specs/012-model-verification/SPEC.md)
for the design and [`specs/012-model-verification/Gregory.md`](../../specs/012-model-verification/Gregory.md)
for the remaining scenario assignments.

## Two layers

| Layer | What it pins | Where |
|-------|--------------|-------|
| **Tier A** — pure-function | each model *function* against a closed form, to machine precision | `test_*_verif.py`, `fields.py` (manufactured fields F0–F4) |
| **Behavioural** — coupled run | the *coupling inside `run_scenario`*: field sampled at the agent, FED accrued each tick, incapacitation pins speed, rerouting fires | `test_s*_*.py`, `harness.py` |

The behavioural layer injects **synthetic fields** (any object with
`.sample(t, x, y) -> float`) into `run_scenario(..., smoke_speed_model=,
fed_model=, reroute_config=)`, so expected agent behaviour is closed-form with no
FDS run.

## Implemented scenarios

| ID | File | Mechanism | Key assertions |
|----|------|-----------|----------------|
| **S1** | `test_s1_corridor_fed.py` | FED lethality | incapacitation at closed-form `t* = 60·D/rate(CO)` within one FED tick; null-field control accrues 0; log-normal population endpoint *(slow)*; aggregate reproducibility *(slow)* |
| **S2** | `test_s2_corridor_speed.py` | smoke-speed | applied factor == closed-form Lund / Fridolf exactly; laws diverge; `K=0` → factor 1; egress scales `1/factor` |
| **S4** | `test_s4_tjunction_reroute.py` | dynamic rerouting | control 0 switches; smoke forces every agent `B→A` (never reverse); latency bound; reproducible count *(slow)* |

Pending (see `specs/012-model-verification/Gregory.md`): **S3** visibility gating, **S5** cognitive map,
**D** gradient (live-position sampling), **E** asymmetric-room transpose.

## Design rules (every scenario)

1. **Three arms** — control (mechanism off) vs treatment (on); assert the
   *difference*. Plus a **null-field control** (mechanism on, null input) to
   catch drift the off-arm can't.
2. **Two assertion levels** — *wiring* (exact, from per-agent history logs:
   `fed_history` / `smoke_history` / `route_history`) and *behavioural*
   (aggregate, tolerant).
3. **Aggregate-only reproducibility** — the coupled run is **not** bit-identical
   under a fixed seed (JuPedSim nondeterminism); assert sorted multisets,
   fractions and counts, never per-agent mappings or raw trajectories.
4. **Assert the discriminating inequality** (e.g. `t* < egress`) so a test can't
   pass vacuously.

## Running

```bash
# fast suite (default CI signal)
uv run pytest tests/verification -m "not slow"

# full suite incl. ensemble / reproducibility checks
uv run pytest tests/verification
```

## Engine findings surfaced by the suite

- **Trajectory nondeterminism** — same seed gives different per-agent
  trajectories; only aggregate outcomes are reproducible.
- **Rerouting bug** ([issue #21](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/21))
  — under by-number placement an agent's route-eval source node is its assigned
  exit, so rerouting is degenerate; flow spawning works. `t_junction_scenario`
  uses flow spawning as the workaround.
