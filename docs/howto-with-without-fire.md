---
title: "Evacuation with and without the fire"
linkTitle: "With and without the fire"
weight: 2
aliases:
  - /docs/using/howto-with-without-fire/
---

Egress tools such as Pathfinder are commonly run without the fire. The
required safe escape time (RSET) is taken from that run and compared with
the available safe escape time (ASET) from FDS. Engineers we consulted
regard this uncoupled comparison as conservative. But Purser (2003, p. 92)
noted that most travel-time calculations assumed no interaction between
occupants and the fire effluent. This page shows how to make the same
comparison with pyFDS-Evac, what a run coupled to the fire adds, and whether
the uncoupled run is conservative for one fire: the 2 MW PVC fire of
[A crowd in a fire](first-fds-case.md).

**You need** the FDS output of that page (step 3 there says how to make
it) in `$FDS`. Each run below takes 3 to 6 s.

## The answer in short

For this fire and this T-junction, with 100 people placed at t = 0:

- **The workflow carries over exactly.** A smoke-blind run with the fire
  (arm U) gives the same trajectories as a run without it (arm C), and it
  records the dose along those fire-free paths.
- **RSET.** The uncoupled RSET is shorter than the speed-only coupled RSET
  in every seed. It is also shorter than the fully coupled RSET in every
  seed when people wait 30 or 60 s before moving. With no wait the coupled
  RSET is later in 19 of 20 seeds, by a median of 9.9 s (sign test
  p = 4 × 10⁻⁵), although nearly everyone in the coupled run takes the far
  exit and avoids the smoke. For the 95th person out the median gap is
  0.95 s.
- **Dose.** Whether the uncoupled run over- or under-states the dose
  depends on the metric (see [the dose table](#dose)).
- **Exit usage** differs: without the fire everyone takes the near exit B.
  With smoke-aware routing (arm R), 94 % take the far exit A when people
  move at once; with 30 s of pre-movement 3 % do, and with 60 s 2 %: from
  about 23 s after ignition every route is refused, and the router takes
  the one with the lowest optical depth, the shorter route to exit B, although it
  passes the densest smoke by the burner
  ([#696](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/696)).
- **The pass/fail verdict** at a fixed point is the same in U, S, R and R-na for
  visibility (fails) and, at 0 and 30 s, for FED 0.3 (passes). At 60 s one
  of ten R seeds misses FED 0.3 at the junction and the branch mouth, as
  do two of ten S seeds and one of ten R-na seeds. For
  HCl with no wait, at ISO FEC 1 (an incapacitation-level value, above the
  design value 0.3), U passes at the junction and the branch mouth in every
  seed, R in 2 and 10 of 20, R-na in 0 and 4, and S in none. Summed over
  seeds and points, U passes 40 times, R 12, R-na 4 and S 0.

This fire has no margin to lose: at every point the visibility limit is
reached before the last person gets out, in every arm and seed. So the
study shows what the uncoupled run misses once the margin is gone. It cannot tell whether a design that passes
without the fire also passes with it. It is one fire in one geometry, run
with research software, and it gives no design verdict.

## 1. The classic comparison: run without the fire

The scenario is `assets/t_junction/config_initial_pre0.json`: 100 agents
spread over the dead-end branch of the T, all familiar with both exits, no
pre-movement, and a time limit of 270 s. The two variants
`config_initial_pre30.json` and `config_initial_pre60.json` differ only in a
constant pre-movement of 30 or 60 s.

**Arm C, no fire.** Leave out `--fds-dir`:

```bash
mkdir -p ww
SC=assets/t_junction/config_initial_pre0.json
uv run python run.py --scenario $SC --seed 4 \
    --output-sqlite ww/c.sqlite --output-exit-history ww/c_exits.csv
```

The output ends with:

```text
Simulation finished in 50.48 s (100/100 evacuated).
```

This is the run an egress-only tool gives you. Take RSET from it and compare
it with the location ASET from FDS, as in
[A crowd in a fire › At fixed points](first-fds-case.md#at-fixed-points-location-aset).

**Arm U, smoke-blind.** The same run, with the fire sampled but not acting.
`--smoke-blind` keeps every agent at its free speed and on its fire-free
route, and still writes what each agent breathed and saw
([#341](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/341)):

```bash
uv run python run.py --scenario $SC --seed 4 --fds-dir "$FDS" --smoke-blind \
    --output-sqlite ww/u.sqlite --output-exit-history ww/u_exits.csv \
    --output-fed-history ww/u_fed.csv --output-smoke-history ww/u_smoke.csv
```

```text
Smoke-blind: rerouting is off.
Smoke-blind: FED is recorded, incapacitation and FIC slowdown off.
…
Simulation finished in 50.48 s (100/100 evacuated).
```

fdsreader also logs `Module vents: could not convert string to float` for
this deck. It does not affect the result.

A scenario with an exit that closes (`closed_after_s`, for example a front
door that jams) also runs smoke-blind
([#395](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/395)). An
agent whose exit closes chooses again, once for each closure, in clear air, as it chose its
first exit; nobody else re-decides. Arm C re-decides through the reroute
pass, so with a closure U walks exactly as the no-fire run with
`--no-enable-rerouting`, not necessarily as C.

{{< checkpoint title="U walks exactly as C" >}}
Pair the agents of both runs by origin and spawn order and compare their
positions frame by frame:

```python
import sqlite3

import pandas as pd


def track(run):
    """Positions per frame, keyed by origin and spawn order, not by id."""
    with sqlite3.connect(f"ww/{run}.sqlite") as con:
        tr = pd.read_sql("SELECT frame, id, pos_x, pos_y FROM trajectory_data", con)
    keys = pd.read_csv(f"ww/{run}_exits.csv").set_index("agent_id")
    return tr.join(keys[["origin", "spawn_index"]], on="id").drop(columns="id")


c, u = track("c"), track("u")
both = c.merge(u, on=["frame", "origin", "spawn_index"])
gap = ((both.pos_x_x - both.pos_x_y) ** 2 + (both.pos_y_x - both.pos_y_y) ** 2) ** 0.5
print(f"rows C {len(c)}, U {len(u)}, paired {len(both)}")
print(f"max position difference C-U: {gap.max():.3f} m")
```

```text
rows C 31276, U 31276, paired 31276
max position difference C-U: 0.000 m
```

Every row pairs and no agent is anywhere else. If the difference is not
zero, check that both runs use the same scenario file and seed.
{{< /checkpoint >}}

**Read RSET from the trajectory**, not from the `Simulation finished` line.
The [ensemble how-to](howto-rset-ensemble.md) explains why and how. For one
seed:

```python
import sqlite3

import numpy as np
import pandas as pd

for run in ("c", "u"):
    with sqlite3.connect(f"ww/{run}.sqlite") as con:
        fps = float(con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0])
        last = pd.read_sql("SELECT MAX(frame) AS f FROM trajectory_data GROUP BY id", con).f / fps
    exits = pd.read_csv(f"ww/{run}_exits.csv").exit_id.value_counts().to_dict()
    print(f"{run.upper()}: RSET_last {last.max():.1f} s, "
          f"p95 {np.sort(last)[94]:.1f} s, exits {exits}")
```

```text
C: RSET_last 50.4 s, p95 48.0 s, exits {'exit_B_right': 100}
U: RSET_last 50.4 s, p95 48.0 s, exits {'exit_B_right': 100}
```

`RSET_last` is the last agent out; `p95` the 95th of 100. The clock starts
at ignition. The run models no detection and no alarm, so RSET here is
pre-movement plus travel: with no pre-movement, the agents move at ignition,
which no standard timeline assumes. Add *t*<sub>det</sub> and
*t*<sub>warn</sub> yourself (ISO/TR 16738:2009, Eq. 2, as on
[ASET and RSET](/fundamentals/aset-rset.md)).

If the run stopped at the time limit with people still inside, `RSET_last`
prints the 270 s cap and `exits` counts the exit assigned to each agent,
out or not. That is not an RSET; see [Sensitivity arms](#sensitivity-arms).

**Read the dose along the fire-free paths** from U's histories:

```python
import pandas as pd

fed = pd.read_csv("ww/u_fed.csv")
smoke = pd.read_csv("ww/u_smoke.csv")
hist = fed.merge(smoke[["time_s", "agent_id", "extinction_per_m"]],
                 on=["time_s", "agent_id"])
hist["hcl_ppm"] = 900 * hist.fic  # HCl is the only irritant in this deck
per_agent = hist.groupby("agent_id").agg(
    max_fed=("fed_cumulative", "max"),
    max_fic=("fic", "max"),
    s_hcl300=("hcl_ppm", lambda v: int((v >= 300).sum())),
    s_k03=("extinction_per_m", lambda v: int((v >= 0.3).sum())),
)
print(per_agent.describe().loc[["50%", "max"]].round(2).to_string())
print(f"agents at HCl >= 300 ppm for at least 1 s: {(per_agent.s_hcl300 > 0).sum()}")
```

```text
     max_fed  max_fic  s_hcl300  s_k03
50%     0.00     1.77       7.0   10.0
max     0.01    19.05      14.0   19.0
agents at HCl >= 300 ppm for at least 1 s: 92
```

The histories are written once per second, so `s_hcl300` and `s_k03` are
seconds at HCl ≥ 300 ppm and at *K* ≥ 0.3 1/m. HCl = 900 × `fic` holds
only because HCl is the only irritant of this deck
([A crowd in a fire › How the numbers are computed](first-fds-case.md#aset-rset)).
The classic comparison uses no such dose: it compares location ASET with
RSET only. The per-agent dose is extra post-processing, as on
[A crowd in a fire › Each agent against its own limits](first-fds-case.md#each-agent-against-its-own-limits).

**The location ASET** comes from the FDS output alone, so it is the same for
every arm. The study uses four points of the
[location ASET table](first-fds-case.md#at-fixed-points-location-aset),
times from ignition:

| Point | *K* ≥ 0.3 1/m | HCl ≥ 300 ppm | HCl ≥ 1000 ppm | FED ≥ 0.3 |
|---|---|---|---|---|
| Exit B | 17 s | 22 s | 33 s | not by 300 s |
| Junction | 23 s | 26 s | 57 s | 261 s |
| Branch mouth | 42 s | 48 s | 62 s | 262 s |
| Exit A | 46 s | 46 s | 48 s | not by 300 s |

The *K* limit is the Engineers Australia visibility of 10 m with *C* = 3
(EA 2014, Fig. 8, *Tenability Criteria – Short Exposure*, p. 15). The HCl
limits are ISO FEC 0.3 and 1. Every agent starts in the branch, so every
agent passes the branch mouth and the junction.

## 2. What coupling adds

Two further arms let the fire act, one effect at a time.

**Arm S, speed only.** Smoke slows the agents, but each keeps the exit it
took in U. `--replay-exits` reads U's exit history and pairs agents by
origin and spawn order ([#352](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/352)):

```bash
uv run python run.py --scenario $SC --seed 4 --fds-dir "$FDS" \
    --no-enable-rerouting --disable-tenability --replay-exits ww/u_exits.csv \
    --output-sqlite ww/s.sqlite --output-exit-history ww/s_exits.csv
```

```text
Replaying the exits of 100 agents from ww/u_exits.csv.
…
Simulation finished in 74.84 s (100/100 evacuated).
```

**Arm R, speed and routing.** The default coupled run. Smoke slows the
agents and enters their route cost:

```bash
uv run python run.py --scenario $SC --seed 4 --fds-dir "$FDS" \
    --disable-tenability \
    --output-sqlite ww/r.sqlite --output-exit-history ww/r_exits.csv
```

```text
Simulation finished in 61.93 s (100/100 evacuated).
```

With `--debug`, C and R also print `Reroute debug` lines; they do not affect
the result.

`--disable-tenability` in S and R records FED and FIC but lets nobody be
incapacitated, so that everyone leaves and RSET stays defined. It also
turns off `--enable-fic-speed` ([Usage](usage.md#tenability-fic-slowdown-and-incapacitation)).
The study adds incapacitation and the HCl slowdown as separate arms
([below](#sensitivity-arms)).

Run the RSET snippet above with `("c", "u", "s", "r")`:

```text
C: RSET_last 50.4 s, p95 48.0 s, exits {'exit_B_right': 100}
U: RSET_last 50.4 s, p95 48.0 s, exits {'exit_B_right': 100}
S: RSET_last 74.8 s, p95 66.2 s, exits {'exit_B_right': 100}
R: RSET_last 61.9 s, p95 52.7 s, exits {'exit_A_left': 93, 'exit_B_right': 7}
```

In this seed smoke slows S by 24.4 s (74.8 against 50.4 s). R is 11.5 s
slower than U; across seeds R is later than U in 19 of 20 ([below](#rset)).
Against S, which keeps exit B, R is faster because 93 of its 100 agents
went to the far exit A and avoided B's smoke. One seed says little: the
study below runs 20 seeds with no pre-movement and 10 each with 30 and
60 s.

**Reading the arms.** U → S isolates the effect of smoke on speed. S → R
isolates routing. R against R-na, the same run with the route cost's look
ahead in time off, isolates that look ahead.

### Evacuation over time

![Three panels, one per pre-movement of 0, 30 and 60 s, each showing agents out of 100 against time since ignition from 0 to 250 s for arms U (blue dashed), S (orange dash-dot) and R (red solid), with shaded min-max bands. Dotted vertical lines at 17, 23 and 46 s mark the location ASET for K at exit B, the junction and exit A. With no pre-movement U and R overlap until about 50 s; U ends near 53 s, R near 62 s and S near 91 s. At 30 s, U ends first near 83 s, R near 150 s and S near 154 s. At 60 s, U ends near 113 s while S and R end near 229 and 235 s and overlap for most of the run](/images/fire-blind/evacuated.png)

*Agents out (of 100) against time since ignition [s], median over seeds
(line) and min–max (band); n = 20 seeds with no pre-movement, 10 at 30 and
60 s. Dotted: location ASET for K ≥ 0.3 1/m at exit B, the junction and
exit A. Exit times from the trajectory at 0.1 s. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

The last agent out, median [min, max] over seeds, seconds from ignition:

| Arm | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| U (= C) | 53.3 [50.1, 56.9] | 83.3 [80.4, 85.8] | 113.3 [110.4, 115.8] |
| S | 90.9 [74.8, 107.2] | 154.4 [135.7, 178.3] | 228.6 [209.0, >270] |
| R | 62.5 [53.5, 66.5] | 150.1 [135.2, 198.3] | 235.3 [228.1, 265.8] |
| R-na | 63.7 [60.7, 72.4] | 127.7 [117.4, 146.3] | 222.8 [207.9, >270] |

">270": at least one agent was still inside at the 270 s limit, in 2 of 10
seeds for S and 1 of 10 for R-na at 60 s; such a run has no RSET
([Sensitivity arms](#sensitivity-arms)).

### Exit usage

![Three bar panels, one per pre-movement, showing the percentage of agents leaving by exit A for arms C, U, S, R, R-na, R-det, R-prob and R+FIC, with one dot per seed. C, U and S are at 0 percent in every panel. With no pre-movement R, R-det and R-prob are near 94 percent, R+FIC near 81 percent and R-na near 97 percent. At 30 s R-na is near 40 percent and R, R-det, R-prob and R+FIC are at 3 percent or below. At 60 s every arm is below 3 percent. A note in the first panel says C, U and S send every agent to exit B, 10 m from the junction](/images/fire-blind/exit_usage.png)

*Agents leaving by exit A [%], bar: median over seeds, dots: one seed each.
Exit A is 20 m from the junction, exit B 10 m. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

C, U and S send everyone to exit B, the nearer one. R sends 94 % [86, 99]
to exit A with no pre-movement, 3 % [1, 4] at 30 s and 2 % [1, 5] at
60 s. The initial exit is chosen in `_assign_initial_exit` (`scenario.py`),
and R's route cost prices the smoke each route meets on the way. With
foresight on (the default `"anticipate": true` of `RouteCostConfig`,
`route_graph.py`), the cost reads the smoke at the time the agent would
arrive at each point (`_arrival_time`), from the whole FDS record
([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)). No
occupant could perceive that. With the look ahead off (R-na), the cost
still reads the current smoke along the whole route, including parts no
occupant could see: 97 % [95, 98] go to exit A with no pre-movement,
40 % [38, 44] at 30 s and 1 % [0, 2] at 60 s. At 30 s R takes B far more
often than R-na; the two differ only in the look ahead.

{{< callout type="warning" >}}
**When every route is refused, the router takes the route with the lowest
optical depth τ.** With 30 or 60 s of pre-movement the first exit changes
under this fallback rule come at 23 s after ignition in seed 7 at 30 and
60 s, while the agents still wait. In seed 7 at 60 s, 101 agents switch from exit
A to exit B and 2 from B to A, the first at 23 s. Between two refused
routes the lower τ decides
([#458](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/458)).
Here that is the shorter route to exit B (17.7 m against 24.7 m), although
it passes the densest smoke near the burner. At 30 and 60 s,
97 % and 98 % of R's agents go past the burner to B; with no pre-movement
94 % go to exit A.

A code-level alternative, `fallback_rule="hold"`, keeps the exit an agent
has once every route is refused, whatever the smoke on it, until the
current route crosses the FED limit and a rival does not
([Route rejection](routing.md#route-rejection);
[#750](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/750)). On the seeds of this
page, R under `"hold"` sends 100 % [100, 100] to exit A at every
pre-movement, against 94 % [86, 99], 3 % [1, 4] and 2 % [1, 5] under
the default `"tau"`. The median largest max FED is 0.009, 0.139 and 0.268
under `"hold"`, against 0.037, 0.170 and 0.271; the median number of
fallback exit changes per run is 0 under `"hold"`, against 6, 101 and
103.5 (at most 14, 104 and 107).

Paired over seeds (exact sign-flip test of the mean difference, `"tau"`
minus `"hold"`), `"tau"` costs dose at 0 and 30 s and gets the 95th person
out earlier at every pre-movement. With no pre-movement the largest max FED is higher in all 20 seeds
(median +0.027) and the 95th person leaves 1.4 s earlier in 17 of 20; the
last person leaves later in 13 of 19 seeds (p = 0.17). At
30 s the mean largest max FED is +0.033 (p = 0.002) and the 95th
person leaves 15.4 s earlier (p = 0.039, weak evidence). At 60 s there is no
dose penalty (+0.013, p = 0.27) and the 95th person leaves 58.0 s earlier
(p = 0.002); under `"hold"`, 6 agents of the 10 runs are still inside at
270 s. `"hold"` is experimental: no scenario key or
flag sets it, and it is neither recommended nor validated. The ranking depends on the fire: on the earlier output of the same deck
(`fire_2MW_PVC`), `"hold"` gave the lower dose at 60 s (median largest max
FED 0.100 against 0.178 under `"tau"`); on `fire_2MW_PVC_796` the gap is
gone. Whether the
rule should send everyone to the exit by the fire is open
([#696](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/696)).
{{< /callout >}}

### U and R, animated

![Animation of arms U (top) and R (bottom) in the T-junction at 8 times real time, pre-movement 30 s. In both, 100 blue dots wait in the dead-end branch while grey smoke spreads from the burner near exit B along the corridor. After 30 s the U dots walk right to exit B, through the smoke and past the burner, staying small and blue; all 100 leave by B, the last at about 83 s. In R, one dot turns left to the far exit A and 99 go right to B past the burner; they grow and turn pale and red as the smoke slows them, and the last leaves at about 151 s.](/images/fire-blind/agents_smoke_u_vs_r.gif)

*Arms U (top) and R (bottom), pre-movement 30 s, seed 7 (R's last agent
leaves at 150.8 s, the seed closest to the median of 150.1 s), 8 times real
time. Background: K from the FDS output, log scale. Dots are coloured and
sized by their speed factor, as in
[The run, animated](first-fds-case.md#the-run-animated). Regenerated by
`scripts/docs/study_animations.py`.*

Both crowds wait 30 s while the smoke spreads from the burner near exit B.
U then walks at free speed through that smoke to exit B, all 100 agents, and
the last is out at 83.0 s. In R, one agent turns to the far exit A and 99 go
to B; the smoke slows them, and the last is out at 150.8 s. The animation
shows 30 s of pre-movement because the smoke has spread by then, so it
shows the speed effect: both arms send almost everyone to B. With no wait,
the two arms differ mainly in the exit.

### Pre-movement does not simply add

![RSET_last against a constant pre-movement of 0, 30 and 60 s for arms U, S and R, medians with markers and one faint line per seed. A dashed line of slope 1 through U at 0 s lies on top of U. S and R rise more steeply: at 0 s S is near 88 s and R near 63 s; at 30 s S near 154 s and R near 150 s; at 60 s U is near 113 s and S and R near 229 and 235 s](/images/fire-blind/additivity.png)

*RSET_last [s from ignition] against constant pre-movement [s], seeds
shared by all three pre-movements (n = 10). Thick: median; faint: one seed.
Dashed: slope 1 through U at 0 s. S and R are drawn slightly left and right
of the tick to keep the markers apart. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

For the same seed, RSET(pre) − pre − RSET(0) is exactly 0.00 s for U and C
in every seed. That follows from how the run is built: the pre-movement is
constant, everyone starts together, and nothing reacts to the fire. S adds
41.3 s more than the pre-movement at 30 s and 69.2 s more at 60 s (8
seeds; the 2 censored ones are left out); R adds 55.6 s and 112.4 s
(medians over seeds). Every seed adds at least 20.8 s in S and 41.6 s in R
at 30 s. The fire grows while people wait, so a later
start meets thicker smoke. An uncoupled run cannot show that: waiting
longer only shifts its curve. The same test on a passenger rail car, FDS
data imported into railEXODUS and Pathfinder with delays of 0, 60, 180 and
300 s, found the movement time (total minus delay) rising with the delay in
railEXODUS, with occupants incapacitated at 300 s, but almost constant in
Pathfinder, for reasons the report leaves open (Ingram et al. 2022, pp. 1
and 42–43).

To let the fire develop before the alarm, where Pathfinder offsets the
FDS results in time, set `premovement_offset_s` on each distribution
([scenario reference](scenario-json.md#spawn-areas-distributionsidparameters)). The FDS clock is
not shifted: agents are in the building from ignition, and while they
wait the smoke update skips them, so they accrue no dose
([#145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)).

## 3. Is the uncoupled run conservative here?

**What "conservative" means.** The decision rests on whether ASET exceeds
RSET by an adequate margin (ISO/TR 16738:2009, Eq. 1 and §5.6, as quoted
on [ASET and RSET](/fundamentals/aset-rset.md)). U is conservative relative
to another arm X if its error makes the margin look smaller than X does.
The reference is a model, R or S, not reality. R's route cost looks ahead
in time, so R-na, without that look ahead, is a second model reference. It
is not a perceptual one: it still reads the smoke along the whole route.

| Metric | U is conservative relative to X if |
|---|---|
| RSET (last, p95) | RSET<sub>U</sub> ≥ RSET<sub>X</sub>, tested against S and R separately |
| Location margin, same point and criterion | ASET − RSET<sub>U</sub> ≤ ASET − RSET<sub>X</sub>; this follows the RSET row, since the location ASET is shared |
| Per-agent margin (first crossing − own exit) | smaller for U than for X, on the same agent |
| People inside at the location ASET | at least as many in U as in X |
| Dose (peak FIC, time above an HCl level, max FED) | at least as large in U as in X |
| Exit usage | neither: it is a scenario assumption, so the page reports how it differs |

Counts below are seeds (or agents) in which U is above, equal to, or below
X. With 10 seeds, 10 of one sign gives a two-sided sign-test p of 0.002;
with 20, 20 of one sign gives 2 × 10⁻⁶. The page runs many such tests, so
treat p near 0.05 as no evidence.

### RSET

![Three strip-plot panels, one per pre-movement, showing per-seed differences S minus U, R minus U and R-na minus U in seconds, with a zero line and a black median bar. With no pre-movement S minus U is above 0 in 20 of 20 seeds, between about 24 and 52 s, R minus U in 19 of 20 with values from about minus 2 to plus 14 s, R-na minus U in 20 of 20 between about 5 and 19 s. At 30 and 60 s all differences are above 0 in 10 of 10 seeds, between about 34 and 152 s](/images/fire-blind/rset_paired.png)

*RSET_last difference per seed [s], same seed in both arms. Above 0: U gets
out earlier. Black bar: median. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

| Pair | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| S − U | +37.1 s [+24.4, +52.0]; S > U in 20/20 | +71.5 s; 10/10 | +109.2 s; 10/10 |
| R − U | +9.9 s [−2.3, +13.8]; R > U in 19/20 (p = 4 × 10⁻⁵) | +66.9 s; 10/10 | +122.4 s; 10/10 |
| R − S | −28.3 s; R < S in 20/20 | +1.9 s; R > S in 6/10, R < S in 4/10 (p = 0.75) | +13.6 s; R > S in 8/10, R < S in 2/10 (p = 0.11) |
| R-na − R | +3.5 s [−4.3, +15.5]; R-na > R in 14/20, R-na < R in 5/20 (p = 0.064) | −20.7 s; R-na < R in 10/10 (p = 0.002) | −19.1 s; R-na > R in 3/10, R-na < R in 7/10 (p = 0.34) |

Medians of the seeds where both runs finished. At 60 s, S is censored in
2 seeds and R-na in 1; a censored run counts as later than any finished
one in the counts.

- **Against S, U is not conservative** at any pre-movement: smoke slows
  people, and U leaves that out.
- **Against R, U is not conservative at any pre-movement.** R is later
  than U on the last agent out in 19 of 20 seeds with no wait (p = 4 × 10⁻⁵)
  and in every seed at 30 and 60 s. With no wait the gap sits in the tail:
  on p95 R is later in 14 of 20 seeds, by a median of 0.95 s, and on the
  last agent by 9.9 s. In 18 of 20 seeds the last agent out is one of the
  few R agents who end at exit B (median 5.5 per seed, 1 to 14); the rest
  go to exit A and meet little smoke.
- **The gap grows with pre-movement**, for R − U from 9.9 s to 122.4 s
  and for S − U from 37.1 s to 109.2 s (medians), because the fire grows
  while people wait. The largest single R − U, 152.0 s, is at 60 s.
- **R against S:** R is faster in 20 of 20 seeds with no pre-movement,
  by 28.3 s in median, by avoiding exit B's smoke. At 30 s R and S are not
  resolved (R later in 6 of 10 seeds, p = 0.75). At 60 s R and S take
  nearly the same exit and are not resolved either: R later in 8, earlier
  in 2 of 10 (p = 0.11).

### ASET − RSET at fixed points

![A three-by-three grid of panels: rows are the criteria K 0.3 per metre, HCl 300 ppm and HCl 1000 ppm, columns the pre-movements 0, 30 and 60 s. Each panel shows location ASET minus RSET_last for exit A, branch mouth, junction and exit B, one marker per arm U, S, R and R-na with a min-max line, and a vertical line at 0. Almost every marker lies left of 0. With no pre-movement, in the HCl 1000 ppm row only U lies right of 0, at the junction and the branch mouth; the ranges of R and R-na reach 0 there and S lies left; an annotation reads junction, seeds that pass of 20: U 20, S 0, R 2, R-na 0](/images/fire-blind/margins.png)

*Location ASET − RSET_last [s] at four fixed points, the same points for
every arm; marker: median over seeds, line: min–max. Right of 0: the last
agent is out before the limit is met there. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

Seeds in which the margin is positive (pass), at exit B / junction / branch
mouth / exit A. Bold: the most passes at that point where the arms differ.

| Criterion | pre-movement | U | S | R | R-na |
|---|---|---|---|---|---|
| *K* ≥ 0.3 1/m | 0, 30, 60 s | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| HCl ≥ 300 ppm | 0, 30, 60 s | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| HCl ≥ 1000 ppm | 0 s | 0/**20**/**20**/0 of 20 | 0/0/0/0 | 0/2/10/0 | 0/0/4/0 |
| HCl ≥ 1000 ppm | 30, 60 s | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| FED ≥ 0.3 | 0, 30 s | all pass | all pass | all pass | all pass |
| FED ≥ 0.3 | 60 s | all pass | 8+2?/8/8/8+2? of 10 | 10/9/9/10 | 9+1?/9/9/9+1? |

*k*?: *k* seeds undetermined. The run ends at the 270 s limit with people
inside, so RSET is censored: the margin is negative where the location
ASET is before 270 s (junction, branch mouth) and unknown where FED 0.3 is
not reached by 300 s (exit B, exit A).

- **Visibility and HCl 300 ppm fail in every arm, seed and pre-movement.**
  FED 0.3 passes in every seed of U, S, R and R-na at 0 and 30 s. At 60 s
  U passes at all four points, but at the junction and the branch mouth R
  fails in 1 seed (seed 13: its last agent leaves at 265.8 s, after
  261 and 262 s), S in 2 seeds and R-na in 1, the last two because people
  are still inside at 270 s. R+FIC fails there in 5 of 10 seeds at 30 s and
  3 of 10 at 60 s for the same reason
  ([Sensitivity arms](#sensitivity-arms)).
- **HCl 1000 ppm with no pre-movement.** U's median margin at the junction
  is about +4 s (57 − 53.3), so U passes there in every seed. R passes at
  the junction in 2 of 20 seeds and at the branch mouth in 10, R-na in 0 and
  4, S in none. Summed over the four points, U passes 40 times, R 12, R-na 4
  and S 0. At every point and criterion U passes at least as often as each
  coupled arm. These counts hold only to a few seeds: on the earlier
  `fire_2MW_PVC` output, changing nothing but the per-agent random draws
  ([#361](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/361)) moved them by up to 3 of 20 seeds at a point.
- The differences sit at HCl 1000 ppm (ISO FEC 1, an incapacitation-level
  value) with no pre-movement and at FED 0.3 at 60 s, and the HCl in this
  deck is probably overestimated (see [Limits](#limits)).

**People inside when the junction reaches the visibility limit** (23 s):
with no pre-movement a median of 74 in U, 75 in S, 81 in R and 93 in
R-na; U has fewer than R in 20 of 20 seeds (median 6.5 fewer). At 30 and 60 s all
100 are inside in every arm. So U is not conservative on this count.

### Dose {#dose}

![A three-by-three grid of cumulative distributions, rows for pre-movement 0, 30 and 60 s, columns for max FIC per agent, seconds at HCl 300 ppm or more, and seconds at K 0.3 per metre or more, for arms U, S and R. In the FIC column with no pre-movement the R curve lies far left of U, with about 95 percent of R agents below FIC 2, and S lies right of U; at 30 and 60 s R lies on top of S, right of U. In the two time columns S lies right of U in every row; R lies left of U with no pre-movement, with about 80 percent of its agents at 0 s and a short tail to the right, and on top of S at 30 and 60 s](/images/fire-blind/exposure.png)

*Share of agents with a value ≤ x, pooled over seeds (2,000 agents with no
pre-movement, 1,000 at 30 and 60 s). Curve further right: more dose. Values
until each agent's exit, at z = 2.0 m (the deck's only slice height; the
1.6 m default resolves to it, see
[A crowd in a fire › The fire](first-fds-case.md#3-the-fire)), 1 s
resolution. Seconds at *K* ≥ 0.3
1/m are secondary: obscuration alone is not treated as incapacitating for
people who are not performing tasks (ISO 13571:2012, §4.5, note).
Regenerated by `scripts/docs/fire_blind_vs_coupled.py`.*

Per seed, U against R. R-na differs from R at 30 s (40 % against 3 % at
exit A) and gives nearly the same exits at 0 s (97 % against 94 %) and at
60 s (1 % against 2 %).

| Dose metric | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| Median of the agents' peak FIC | U higher in 20/20 | U lower in 10/10 | U lower in 10/10 |
| Agent-seconds at HCl ≥ 300 ppm | U higher in 20/20 | U lower in 10/10 | U lower in 10/10 |
| Agent-seconds at HCl ≥ 1000 ppm | U higher in 14/20, lower in 6/20 | U lower in 10/10 | U lower in 10/10 |
| Max FED | U lower in 19/20, higher in 1/20 | U lower in 10/10 | U lower in 10/10 |
| Agents past *K* 0.3 or HCl 300 ppm before getting out | U more in 20/20 | 100 in every arm | 100 in every arm |

- **Against R, "conservative" depends on the metric and the
  pre-movement.** With no pre-movement U over-states the peak FIC and the
  time above 300 ppm in 20 of 20 seeds and the time above 1000 ppm in 14,
  but under-states the max FED in 19: U walks into exit B's HCl, which
  almost every R agent avoids. In 19 of 20 seeds the agent with the
  highest FED in R is one of the few that end at exit B; the median R
  agent has a FED near zero. At 30 and 60 s U under-states every dose metric except the crossing count in every seed: almost every
  R agent walks to B later, in thicker smoke.
- **Against S, U under-states the run totals** in every seed, at every
  pre-movement: agent-seconds at HCl ≥ 300 and ≥ 1000 ppm and at *K* ≥ 0.3
  1/m, and max FED. On single agents it does not always: U's peak FIC is
  higher than S's for 534 of 2,000 agents with no pre-movement, 165 of 1,000 at
  30 s and 176 of 1,000 at 60 s.
- The largest max FED of any agent is 0.07 in U, 0.38 in R and 0.42 in S,
  each at 60 s. In U no agent reaches FED 0.3. At 60 s one R agent reaches
  it (seed 13, out at 265.8 s), 4 S agents in 3 seeds and 2 R-na agents in
  2 seeds; at 30 s none does. No agent of U, S, R or R-na reaches FED 1. A FED
  below 0.3 or 1 is not a statement of tenability: FED 0.3 is a threshold for susceptible people, and FED < 1
  does not mean safe
  ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).

**Per-agent margin**, first crossing of *K* 0.3 1/m minus the agent's own
exit, compared on the same agent (seed, origin, spawn order):

| | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| Agents crossing in both U and R | 631 of 2,000 | 1,000 of 1,000 | 1,000 of 1,000 |
| Median R − U among them | −4.5 s (R smaller in 488) | −35.1 s (993) | −65.9 s (1,000) |
| Median S − U, crossing in both | −4.0 s (S smaller in 1,707 of 1,913) | −36.7 s (996) | −65.8 s (998 of 998) |

With no pre-movement, 1,284 agents cross the limit in U but not in R, and
none the other way round. Counting an agent that never crosses as having an
infinite margin, R has the larger margin for 1,420 agents and U for 488
(92 tie). So with no pre-movement the direction depends on how agents who
never cross are counted; at 30 and 60 s U's margin is larger (not
conservative) for 993 and 1,000 of 1,000 agents.

### Is exit usage conservative?

Exit usage is not conservative or otherwise. Choosing exits is part of the
scenario: each design fire scenario is analysed with design occupant
scenarios, and the occupants' initial route choice is one of the
variables of such a scenario (Nilsson and Fahy 2016, pp. 2047, 2061).
Here the difference is large: exit B for everyone without the fire, exit
A for 94 % with it when people move at once, for 3 % after 30 s of
waiting and for 2 % after 60 s. It also drives the
dose differences above.

### Sensitivity arms {#sensitivity-arms}

{{< details title="Incapacitation, per-agent thresholds, HCl slowdown and route look ahead" closed="true" >}}

| Arm | Flags on top of R | Result |
|---|---|---|
| R-na | `"anticipate": false` in the scenario's `routing` block (see below) | With no pre-movement 3.5 s later than R in median (R-na > R in 14 of 20, p = 0.064), with 97 % [95, 98] at exit A against 94 % in R. At 30 s: 40 % at A against 3 %, last out 20.7 s earlier in median (10 of 10, p = 0.002). At 60 s: 1 % at A against 2 %, last out 19.1 s earlier in median (7 of 10, p = 0.34); 1 of 10 runs is censored. |
| R-det | tenability on (FED 1 incapacitates) | Identical to R: nobody reaches FED 1. |
| R-prob | R-det with `--incapacitation-mode probabilistic` | Identical to R with no pre-movement: nobody is incapacitated. At 30 s, 7 agents are incapacitated in 5 of 10 seeds and 7 are inside when the run ends; RSET is censored in those 5 seeds. At 60 s, 27 agents are incapacitated in 10 of 10 seeds and 30 are inside at 270 s; RSET is censored in all 10 seeds. The median last exit among the rest is 150.1 s at 30 s and 235.3 s at 60 s, as in R. Their dose counts only until incapacitation. |
| R+FIC | R-det with `--enable-fic-speed` | No pre-movement: RSET 168.3 s [164.7, 174.1], 81 % [74, 87] to exit A, with 26 [20, 33] agents per seed reaching FIC 1, where the irritant fraction is 0 and the speed is at its 0.1 floor ([FED and FIC](/models/fed.md), Eq. 70.11/70.12). At 30 s: all 100 agents reach FIC 1; censored in 5 of 10 seeds, 8 of 1,000 agents inside at 270 s. At 60 s: all 100 reach FIC 1; censored in 3 of 10 seeds, 3 of 1,000 inside, and 4.5 [3, 8] agents per seed reach FED 0.3. Max FED reaches 0.40 at 30 s and 0.44 at 60 s. |

To build R-na, add the key to a copy of the scenario and save the copy
next to a copy of `geometry.wkt`, which the scenario needs beside it:

```bash
mkdir -p ww/na
cp assets/t_junction/geometry.wkt ww/na/
uv run python - <<'EOF'
import json
from pathlib import Path

config = json.loads(Path("assets/t_junction/config_initial_pre0.json").read_text())
config["routing"]["anticipate"] = False
Path("ww/na/config_initial_pre0.json").write_text(json.dumps(config, indent=2))
EOF
uv run python run.py --scenario ww/na/config_initial_pre0.json --seed 4 \
    --fds-dir "$FDS" --disable-tenability \
    --output-sqlite ww/rna.sqlite --output-exit-history ww/rna_exits.csv
```

```text
Simulation finished in 67.59 s (100/100 evacuated).
```

98 leave by exit A and 2 by exit B; in R, 93 take exit A and 7 exit B. The
study script builds the same files (`write_noanticipate`).

A censored RSET is only known to exceed 270 s. It is never compared by size
with U's. An agent incapacitated or still inside at 270 s never counts as
out, so a coupled RSET cannot look shorter because people dropped out of
the count. Runs that end with agents inside, at 270 s or with only
incapacitated agents left, are incomplete, and `run.py` exits with status 2
for them ([Exit status](usage.md#exit-status)); in this study that
is R-prob at 30 and 60 s, R+FIC at 30 and 60 s, S in 2 seeds and R-na in 1
at 60 s. R+FIC is an upper bound: it is censored in 5 of 10 seeds at 30 s
and 3 of 10 at 60 s, its dose stops at the cap, and it rests on HCl that
is probably overestimated.

{{< /details >}}

## 4. Run the whole study

```bash
uv run python scripts/docs/fire_blind_vs_coupled.py --data "$FDS" --runs RUNS
```

`RUNS` must lie outside the repository. The script runs arms C, U, S, R,
R-na, R-det, R-prob and R+FIC for seeds 4–23 with no pre-movement and 4–13
at 30 and 60 s, one `run.py` process per arm and seed
([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)). It
skips runs that already exist, prints every number on this page, writes
`summary_runs.csv` and `summary_agents.csv` into `RUNS`, and redraws the
figures in `site/static/images/fire-blind/`. At `efee66e3` the 320 runs
took 449 s (about 7.5 min) of wall time on 8 workers, the default of
`--workers`, on an Apple M3 Pro; the analysis alone takes about 22 s. Seeds 1–3 were used for
a pilot and are left out.

The animation above is drawn from the same `RUNS` folder:

```bash
uv run python scripts/docs/study_animations.py fire-blind --data "$FDS" --runs RUNS
```

**Provenance.** The numbers and figures on this page come from runs of
the code of commit `efee66e3` on main (`pyfds_evac/` and `run.py` of the
worktree are identical to it), on the FDS 6.10.1 output
`t_junction/fire_2MW_PVC_796` of the deck `assets/t_junction/t_junction.fds`
(Python 3.12.16), made with the two commands above. Each run's manifest
records `agent_seeding: spawn-key-blake2b-v2`. The seed-4
walkthrough above gives trajectories identical to those study runs. When the code changes, re-run the
study into a new `RUNS` folder and compare the printed report with this
page.

## Limits

- **One fire with no margin.** Here, at every point, the visibility limit
  is met before the last person gets out, in every arm. Schröder et al.
  (2020, §4) state that the effects of smoke, heat and toxic gases on route
  choice and walking speed "should play a subordinate role as long as the
  safety margin is sufficiently greater than the limiting state". In our
  view, the regime near the limit is where practice decides, and this study
  does not test it.
- **The size of the S − U and R − U gaps is not measured behaviour.** The
  smoke-speed law is fitted to Frantzich and Nilsson's data, *K* ≈ 1.9–7.4
  1/m (read from their Fig. 14; see
  [walking speed in smoke](/fundamentals/walking-speed.md)), and has a floor
  of 0.1 from *K* = 11.1 1/m. Share of moving agent-seconds below / within /
  above that range, and at the floor:

  | Arm | pre-movement 0 s | 30 s | 60 s |
  |---|---|---|---|
  | S | 72.1 / 12.3 / 15.6 %, floor 9.3 % | 23.2 / 23.3 / 53.5 %, floor 36.0 % | 0.1 / 10.6 / 89.3 %, floor 68.5 % |
  | R | 91.7 / 6.6 / 1.7 %, floor 1.1 % | 23.2 / 24.0 / 52.8 %, floor 35.5 % | 0.1 / 10.6 / 89.3 %, floor 68.4 % |

  Below 1.9 1/m the law is outside the data too. There it slows people by
  2.4 % at *K* = 0.3 1/m, the visibility limit, rising to about 15 % at
  1.9 1/m.

  ![Left: the speed factor against the extinction coefficient K from 0 to 25 per metre, solid over the Frantzich and Nilsson data range 1.9 to 7.4, dashed outside it, falling from 1 at K 0 to the floor 0.1 at K 11.1 and flat after. Right: histograms of K at moving agents in arms S and R; the largest bin is below 0.5 per metre, with a tail beyond 11; an annotation gives S 55 percent above 7.4 and 40 percent at the floor, R 54 and 40 percent](/images/fire-blind/speed_extrapolation.png)

  *Left: speed factor v/v₀ [-] against K [1/m] of the default law;
  shaded: the data range. Right: K at the moving agent [1/m], share of
  agent-seconds [%], pooled over all three pre-movements; the last bin
  holds K ≥ 24.5. "At the floor" counts K ≥ 11.1 1/m. Regenerated by
  `scripts/docs/fire_blind_vs_coupled.py`.*
- **Route foresight.** R's route cost reads the smoke ahead from the whole
  FDS record ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
  R's avoidance of exit B is therefore not a claim that people would see it
  coming. R-na removes only the look ahead in time: it still reads the
  current smoke along the whole route, including parts no occupant could
  see. With no pre-movement it sends 97 % [95, 98] to exit A against
  94 % in R, at 30 s 40 % against 3 %, and at 60 s 1 % against 2 %.
  At 30 s foresight therefore moves agents toward exit B, the exit by the
  fire, when it sees smoke coming on the longer route.
- **All routes refused.** Then the router takes the
  route with the lowest optical depth τ
  ([#458](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/458)), here the shorter route to
  exit B past the burner. At 30 s the code-level `fallback_rule="hold"`,
  which keeps everyone on the route to A, gives a lower largest max FED
  (median 0.139 against 0.170; the default rule's paired mean is +0.033,
  p = 0.002) and a later 95th person out (by 15.4 s, p = 0.039). At 60 s
  the doses do not differ (median 0.268 against 0.271; p = 0.27) and the
  default rule is faster by 58.0 s. Whether this rule is right is
  open ([#696](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/696)).
- **HCl is probably overestimated.** The deck has no HCl loss to walls
  ([A crowd in a fire › What this does not show](first-fds-case.md#what-this-does-not-show)).
  That makes the HCl crossings early and inflates R+FIC.
- **The HCl slowdown is opt-in**, off in S and R, and incapacitation uses
  the FDS+Evac FED ([FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source)
  has no irritant slowdown), not HCl.
- **Constant pre-movement.** Everyone waits the same 0, 30 or 60 s. The three
  values were fixed from the fire before any run: 0 s moves before the
  junction reaches the visibility limit (23 s), 30 s falls between the first
  and last of the six points of
  [A crowd in a fire](first-fds-case.md#at-fixed-points-location-aset)
  (17–46 s), 60 s after all of them. Babrauskas et al. (2010,
  pp. 346–347, 351) criticise pre-movement times of 0–80 s used for homes
  as unrealistic. Citing an NRCC study, they report that healthy occupants
  of a single-family house at night can need up to 11 min from alarm to
  exit (p. 346). That figure includes travel and is counted from the alarm,
  not the fire. Those are residential values and do not transfer to this
  geometry.
- **Everyone knows both exits** (`familiarity: "full"`). Agents who discover
  exits could fail to find one, and the familiarity draw depends on the
  JuPedSim id ([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)).
  For sign loss in this fire, see
  [A crowd in a fire](first-fds-case.md#at-fixed-points-location-aset).
- **The time limit is 270 s**, 30 s before the end of the FDS output. At
  60 s it binds: S in 2 of 10 seeds, R-na in 1, R-prob in 10 and R+FIC in 3
  end with people inside. Route
  foresight samples ahead of the current time and can read past the end
  ([#356](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/356)); the
  longest route, 30 m from the branch to exit A, takes 23 s at the 1.3 m/s
  the cost assumes. Configured waypoints are not included in that bound.
- **Per agent goes beyond ISO 13571,** which treats populations, not
  individuals (§5.2). The FED is the FDS+Evac FED, not the ISO asphyxiant
  FED.
- **The ASET side is not built in.** The location ASET and the crossings
  are computed by the script, not by the engine
  ([#210](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/210)).

{{< details title="Sources" closed="true" >}}

- Babrauskas, V., Fleming, J. M., & Russell, B. D. (2010). RSET/ASET, a
  flawed concept for fire safety assessment. *Fire and Materials*, 34(7),
  341–355, pp. 346–347, 351.
  [doi:10.1002/fam.1025](https://doi.org/10.1002/fam.1025)
- Engineers Australia Society of Fire Safety (2014). *Practice note for
  tenability criteria in building fires*, version 2.0, §5.2 and Fig. 8,
  *Tenability Criteria – Short Exposure*, p. 15. Full reference on
  [ASET and RSET](/fundamentals/aset-rset.md).
- Frantzich, H., & Nilsson, D. (2003). *Utrymning genom tät rök: beteende
  och förflyttning*, Fig. 14. Full reference on
  [walking speed in smoke](/fundamentals/walking-speed.md).
- Ingram, B., Datta, M., Lattimer, B. Y., & Kapahi, A. (2022). *Evaluation
  of egress models for passenger rail cars for emergency and non-emergency
  scenarios*. Report DOT/FRA/ORD-22/11, Federal Railroad Administration,
  Washington, DC, pp. 1, 19, 42–43.
  [rosap.ntl.bts.gov/view/dot/60734](https://rosap.ntl.bts.gov/view/dot/60734)
- ISO 13571:2012, §4.5 (note) and §5.2; ISO/TR 16738:2009, Eq. 1, Eq. 2
  and §5.6: paraphrased; see [ASET and RSET](/fundamentals/aset-rset.md).
- Nilsson, D., & Fahy, R. (2016). Selecting scenarios for deterministic fire
  safety engineering analysis: life safety for occupants. *SFPE Handbook of
  Fire Protection Engineering*, 5th ed., Ch. 57, pp. 2047, 2061.
  [doi:10.1007/978-1-4939-2565-0_57](https://doi.org/10.1007/978-1-4939-2565-0_57)
- Purser, D. A. (2003). ASET and RSET: addressing some issues in relation
  to occupant behaviour and tenability. *Fire Safety Science*, 7, 91–102,
  p. 92. [doi:10.3801/IAFSS.FSS.7-91](https://doi.org/10.3801/IAFSS.FSS.7-91)
- Schröder, B., Arnold, L., & Seyfried, A. (2020). A map representation of
  the ASET-RSET concept. *Fire Safety Journal*, 115, 103154, §4.
  [doi:10.1016/j.firesaf.2020.103154](https://doi.org/10.1016/j.firesaf.2020.103154)
- Code: `_assign_initial_exit` in `pyfds_evac/core/scenario.py`;
  `RouteCostConfig` and `_arrival_time` in `pyfds_evac/core/route_graph.py`.

{{< /details >}}

## What next

- [Usage › Smoke-blind runs and exit replay](usage.md#smoke-blind-runs-and-exit-replay):
  every flag of the three arms.
- [How do I get the egress time from an ensemble?](howto-rset-ensemble.md)
  for RSET over many seeds.
- [ASET and RSET](/fundamentals/aset-rset.md) for the concepts.
- [ASET-RSET maps after Schröder et al. (2020)](study-schroeder2020.md): arm U only, as ASET − RSET
  maps.
