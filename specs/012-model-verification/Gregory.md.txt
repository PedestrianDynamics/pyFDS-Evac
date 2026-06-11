# 012 — Behavioral verification scenarios (student tasks)

Self-contained scenario assignments for the coupled-engine verification suite.
S1 (FED lethality) and S2 (smoke-speed) are **done** and are the templates to
copy. Each task below extends `tests/verification/harness.py` with one geometry
builder and adds one `test_s*_*.py` file.

## Read first

- `tests/verification/harness.py` — the synthetic-field injection layer. A
  "field" is any object with `.sample(time_s, x, y) -> float`; build them with
  `uniform(...)`, `ramp_x(...)`, or a new closure. Models are injected into
  `run_scenario(scenario, smoke_speed_model=, fed_model=, tenability_config=,
  reroute_config=, vis_model=)`.
- `tests/verification/test_s1_corridor_fed.py`, `test_s2_corridor_speed.py` —
  the two worked examples. Copy their structure.
- `specs/012-model-verification/SPEC.md` — the principles (three arms, anti-FEMTC).

## Non-negotiable rules (inherited from S1/S2)

1. **Three arms.** Control (mechanism off) vs treatment (on); assert the
   *difference*. Add a **null-field control** (mechanism *on*, null input, e.g.
   `K=0` or `CO=0`) — it exercises the same wiring and catches drift the
   off-arm can't.
2. **Two assertion layers.** *Wiring* = exact, position-independent, from the
   per-agent history logs (`smoke_history` / `fed_history` / `route_history`).
   *Behavioral* = aggregate (counts, egress ratio, switch latency), tolerant.
3. **Never assert per-agent determinism or raw trajectories.** The coupled run
   is not bit-reproducible (JuPedSim nondeterminism — see project memory). Only
   *aggregate* invariants (sorted multisets, fractions, counts) are reproducible.
4. **Make the discriminating inequality an asserted quantity** (e.g.
   `t* < egress`, `cost_smoky > cost_clear`) so the test can't pass vacuously.
5. `ruff format` + `ruff check` clean before commit.

---

## Task A — S3: visibility gating (sign acquisition in smoke)

**Mechanism:** `core/visibility.py` + fdsvismap, injected via `vis_model`.
Agents only head to an exit once its **sign is acquired** (within `V = c/K` of
the sign, in the view cone, unobstructed).

**Geometry** (new `room_with_sign` builder): a single room, one exit, one
directional sign on the wall by the exit.

```
 y       +--------------------[sign ▲]--------+
         |                                    |
 spawn ->|  · · · agents · · ·          [Exit]|
         |                                    |
         +------------------------------------+
              <----------- L ----------->
```

**Arms / config:**
- *Clear* (`vis_model` on, `uniform(K=0)`): sign visible from spawn → agents go
  straight to the exit.
- *Smoky* (`vis_model` on, `uniform(K)` with `c/K < distance(spawn, sign)`):
  sign **not** acquired at spawn; only acquired once an agent walks within
  `R = c/K`.

**Closed form:** the acquisition boundary is the circle of radius `R = c/K`
around the sign (uniform field → clean contour, unlike a real fire field).

**Assertions:**
- *Wiring:* at spawn distance `d > R`, no agent has the sign as target; first
  acquisition happens when an agent first crosses `d = R` (±1 spacing tol).
- *Behavioral:* smoky-arm egress > clear-arm egress (acquisition delay), both
  fully evacuate (sub-lethal `K`).
- *Null control:* `K=0` smoky-arm == clear-arm (factor/visibility unchanged).

**Catches:** a gate that ignores `V=c/K` (agents teleport to the exit through
smoke), or an inverted threshold. **Note:** keep the room **non-square** and the
sign **off-centre** so a latent x/y transpose can surface — but the dedicated
transpose test is Task E.

---

## Task B — S4: T-junction rerouting (avoid the smoky arm)

**Mechanism:** `core/route_graph.py` + dynamic rerouting, via `reroute_config`.
Logged to `result.route_history` (`time_s, agent_id, old_exit, new_exit,
old_cost, new_cost, reason`) and `metrics["route_switches"]`.

**Geometry** (new `t_junction` builder): a stem splitting into a **short** arm
(→ Exit A) and a **long** arm (→ Exit B). Put smoke in the short arm so its
*cost* exceeds the long clear arm.

```
                     [Exit A]   short arm  (smoky)
                        |  ___________
 spawn -> === stem ===>|<            (junction)
                        |  ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
                     [Exit B]   long arm   (clear)
```

**Config:**
```python
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
reroute = RerouteConfig(
    reevaluation_interval_s=10.0,
    cost_config=RouteCostConfig(w_smoke=1.0, w_fed=10.0),
)
run_scenario(scenario, smoke_speed_model=make_smoke_model(short_arm_smoke),
             reroute_config=reroute)
```
`short_arm_smoke` = a closure returning `K` inside the short-arm polygon, `0`
elsewhere (so the cost penalty is localized).

**Closed form:** path cost ≈ `Σ mean_K · segment_length` (per `RouteCostConfig`).
Pick `K`/lengths so `cost(short, smoky) > cost(long, clear)`; assert that
inequality from the cost model *before* running, so the run only has to confirm
the choice.

**Assertions:**
- *Behavioral:* with smoke, the majority pick the long arm; `route_switches > 0`
  and `route_history` shows `old_exit=A → new_exit=B`. Control (no smoke): they
  take the short arm, `route_switches == 0`.
- *Latency:* a path occluded at `t1` reroutes by `t1 + reevaluation_interval_s`
  — assert switch `time_s ≤ t1 + interval`.

**Catches:** rerouting that ignores smoke cost, or never re-evaluates (latency
unbounded).

---

## Task C — S5: cognitive map (staff vs visitor)

**Mechanism:** `core/cognitive_map.py`. `full` agents know all exits at `t=0`;
`discovery` agents only know exits they've seen.

**Geometry:** the Task-A room with **two** exits — a near one with no sign and a
far one with a sign — or two signed exits at different distances.

**Arms:** one population `full` (staff), one `discovery` (visitors), identical
spawn.

**Assertions:**
- *Wiring:* at `t=0`, `full` agents' known-exit set = all exits; `discovery`
  agents' = only exits visible from spawn (couple to S3's visibility stub).
- *Behavioral:* staff use the nearest exit immediately; visitors diverge
  predictably (only route to an exit after discovering it). Assert the two
  populations' exit-usage distributions differ.
- *Determinism:* same seed → same *aggregate* exit split (multiset, not
  per-agent).

**Catches:** discovery agents that secretly know all exits (mode ignored), or
`full` agents that don't.

**Note:** A4.1–A4.3 already unit-test the map logic with a stubbed visibility
model; S5 verifies it is *wired into the run loop*.

---

## Task D — Gradient scenario (live-position sampling)

**Why:** every uniform-field test above is **position-blind** — it cannot prove
the field is sampled at the agent's *moving* position. This task closes that gap
(advisor finding; harness docstring currently disclaims it).

**Geometry:** reuse the S1/S2 corridor. Use `ramp_x(slope, intercept)` so the
field rises toward the far (fire) end: `K(x) = slope · x`.

**Assertion (qualitative monotonic, NOT closed-form):** as an agent walks +x,
its logged `extinction_per_m` in `smoke_history` must be **non-decreasing** in
its own `x`, and `speed_factor` correspondingly non-increasing. (Exact value
isn't closed-form because it depends on the JuPedSim path — assert the trend per
agent, not a number.)

**Catches:** a sampler that reads a fixed/wrong coordinate — invisible to every
uniform test, visible here.

---

## Task E — Asymmetric room transpose test (B3.1, standalone)

**Why separate:** this is the single highest-value suspected bug (x/y axis order
masked by square geometry, SPEC §3). It does **not** need the behavioral harness
— it's a direct check of the visibility map on a manufactured asymmetric field,
cheaper to build standalone.

**Geometry:** a **non-square** room (e.g. 8 × 4 m), one sign at a known
*asymmetric* side-wall position, near-clear air.

**Assertion:** compute the set of cells that *should* see the sign (within
`max_vis`, in the view cone, unobstructed) and compare the boolean visibility
map cell-by-cell. A transpose bug fails here but passes on a square room.

**Catches:** the x/y array-orientation bug. See SPEC.md B3.1 for detail.

---

## Definition of done (per task)

- [ ] One geometry builder added to `harness.py`, reused by the test.
- [ ] Three arms incl. a null-field control.
- [ ] Wiring assertion (exact, from a history log) **and** behavioral assertion
      (aggregate, tolerant).
- [ ] The discriminating inequality asserted explicitly.
- [ ] `slow`-marked ensemble where a fraction/distribution is claimed.
- [ ] `ruff` clean; `pytest tests/verification` green.
- [ ] One sentence: *what subtly-broken implementation would this fail?*
