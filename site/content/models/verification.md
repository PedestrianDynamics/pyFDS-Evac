---
title: "Verification suite"
weight: 5
math: true
---

A two-layer verification suite checks each sub-model against a hand-computable
reference:

- **Tier A** pins each model *function* (FED, smoke-speed, cognitive map,
  pre-movement) to a closed form, to machine precision.
- **Behavioural** scenarios drive the coupling inside `run_scenario` with
  injected synthetic fields (no FDS run): a corridor for FED lethality (S1) and
  smoke-speed slowdown (S2), and a T-junction for dynamic rerouting (S4). Each
  uses a control / treatment / null-field design and asserts both exact wiring
  (from the per-agent history logs) and aggregate behaviour.

```bash
uv run pytest tests/verification -m "not slow"   # fast suite
uv run pytest tests/verification                  # incl. ensemble checks
```

See [tests/verification/README.md](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/README.md) for the full
catalogue and [specs/012-model-verification/SPEC.md](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/specs/012-model-verification/SPEC.md)
for the design. The suite already surfaced two engine findings: trajectory-level
nondeterminism (only aggregate outcomes reproduce under a fixed seed) and a
rerouting bug under by-number placement
([issue #21](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/21)).
