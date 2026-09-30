---
title: "Evacuation with and without the fire"
linkTitle: "How-to: with and without the fire"
weight: 15
---

Egress tools such as Pathfinder are commonly run without the fire. The
required safe escape time (RSET) is taken from that run and compared with
the available safe escape time (ASET) from FDS. Practitioners regard this
uncoupled comparison as conservative. This page shows how to make the same
comparison with pyFDS-Evac, what a run coupled to the fire adds, and whether
the uncoupled run is conservative for one fire: the 2 MW PVC fire of
[A crowd in a real fire](first-fds-case.md).

**You need** the `fire_2MW_PVC` FDS output of that page (step 3 there says
where to get it) in `$FDS`. Each run below takes about 4 s.

## The answer in short

For this fire and this T-junction, with 100 people placed at t = 0:

- **The workflow carries over exactly.** A smoke-blind run with the fire
  (arm U) gives the same trajectories as a run without it (arm C), and it
  records the dose along those fire-free paths.
- **RSET.** The uncoupled RSET is shorter than the speed-only coupled RSET
  in every seed. It is shorter than the fully coupled RSET in every seed
  when people wait 30 or 60 s before moving. With no wait, the direction
  against the fully coupled run is not resolved.
- **Dose.** Whether the uncoupled run over- or under-states the dose
  depends on the metric (see [the dose table](#dose)).
- **Exit usage** differs: without the fire everyone takes the near exit B;
  with smoke-aware routing (arm R) most agents take exit A.
- **The pass/fail verdict** at a fixed point is the same in every arm for
  visibility (fails), and in U, S, R and R-na for FED 0.3 (passes). For HCl
  with no wait, the verdict at ISO FEC 1 (not the design value 0.3) is
  knife-edge: a single uncoupled run can give either verdict. Summed over
  seeds and points, U passes 36 times, R 30, R-na 17 and S 4.

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
Simulation finished in 57.65 s (100/100 evacuated).
```

This is the run an egress-only tool gives you. Take RSET from it and compare
it with the location ASET from FDS, as in
[A crowd in a real fire › At fixed points](first-fds-case.md#at-fixed-points-location-aset).

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
Simulation finished in 57.65 s (100/100 evacuated).
```

fdsreader also logs `Module vents: could not convert string to float` for
this deck. It does not affect the result.

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
rows C 35585, U 35585, paired 35585
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
C: RSET_last 57.6 s, p95 55.5 s, exits {'exit_B_right': 100}
U: RSET_last 57.6 s, p95 55.5 s, exits {'exit_B_right': 100}
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
50%     0.00     1.62       5.0   11.0
max     0.01    16.30      26.0   37.0
agents at HCl >= 300 ppm for at least 1 s: 83
```

The histories are written once per second, so `s_hcl300` and `s_k03` are
seconds at HCl ≥ 300 ppm and at *K* ≥ 0.3 1/m. HCl = 900 × `fic` holds
only because HCl is the only irritant of this deck
([A crowd in a real fire › How the numbers are computed](first-fds-case.md#aset-rset)).
The classic comparison uses no such dose: it compares location ASET with
RSET only. The per-agent dose is extra post-processing, as on
[A crowd in a real fire › Each agent against its own limits](first-fds-case.md#each-agent-against-its-own-limits).

**The location ASET** comes from the FDS output alone, so it is the same for
every arm. The study uses four points of the
[location ASET table](first-fds-case.md#at-fixed-points-location-aset),
times from ignition:

| Point | *K* ≥ 0.3 1/m | HCl ≥ 300 ppm | HCl ≥ 1000 ppm | FED ≥ 0.3 |
|---|---|---|---|---|
| Exit B | 18 s | 28 s | 40 s | not by 300 s |
| Junction | 24 s | 45 s | 59 s | 274 s |
| Branch mouth | 46 s | 51 s | 68 s | 275 s |
| Exit A | 45 s | 47 s | 50 s | not by 300 s |

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
Simulation finished in 67.57 s (100/100 evacuated).
```

**Arm R, speed and routing.** The default coupled run. Smoke slows the
agents and enters their route cost:

```bash
uv run python run.py --scenario $SC --seed 4 --fds-dir "$FDS" \
    --disable-tenability \
    --output-sqlite ww/r.sqlite --output-exit-history ww/r_exits.csv
```

```text
Simulation finished in 56.41 s (100/100 evacuated).
```

C and R print `Reroute debug` lines; they do not affect the result.

`--disable-tenability` in S and R records FED and FIC but lets nobody be
incapacitated, so that everyone leaves and RSET stays defined. It also
turns off `--enable-fic-speed` ([Usage](usage.md#tenability-fic-slowdown-and-incapacitation)).
The study adds incapacitation and the HCl slowdown as separate arms
([below](#sensitivity-arms)).

Run the RSET snippet above with `("c", "u", "s", "r")`:

```text
C: RSET_last 57.6 s, p95 55.5 s, exits {'exit_B_right': 100}
U: RSET_last 57.6 s, p95 55.5 s, exits {'exit_B_right': 100}
S: RSET_last 67.5 s, p95 63.9 s, exits {'exit_B_right': 100}
R: RSET_last 56.4 s, p95 54.5 s, exits {'exit_A_left': 100}
```

In this seed smoke slows S by 10 s. R is 1.2 s faster than U; across seeds
that sign is not resolved ([below](#rset)). Against S, which keeps exit B,
R is faster because every agent went to the far exit A and avoided B's
smoke. One seed says little: the study below runs 20 seeds with no
pre-movement and 10 each with 30 and 60 s.

**Reading the arms.** U → S isolates the effect of smoke on speed. S → R
isolates routing. R against R-na, the same run with the route cost's look
ahead in time off, isolates that look ahead.

### Evacuation over time

![Three panels, one per pre-movement of 0, 30 and 60 s, each showing agents out of 100 against time since ignition from 0 to 250 s for arms U (blue dashed), S (orange dash-dot) and R (red solid), with shaded min-max bands. Dotted vertical lines at 18, 24 and 45 s mark the location ASET for K at exit B, the junction and exit A. With no pre-movement the three curves overlap and end near 57 to 72 s. At 30 s, U ends first near 86 s, R near 114 s and S near 129 s. At 60 s, U ends near 116 s while S and R end near 200 s](/images/fire-blind/evacuated.png)

*Agents out (of 100) against time since ignition [s], median over seeds
(line) and min–max (band); n = 20 seeds with no pre-movement, 10 at 30 and
60 s. Dotted: location ASET for K ≥ 0.3 1/m at exit B, the junction and
exit A. Exit times from the trajectory at 0.1 s. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

The last agent out, median [min, max] over seeds, seconds from ignition:

| Arm | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| U (= C) | 56.9 [48.8, 74.8] | 86.3 [78.8, 104.8] | 116.3 [108.8, 134.8] |
| S | 71.5 [66.0, 113.3] | 129.1 [123.0, 188.5] | 203.1 [180.1, 234.3] |
| R | 59.0 [54.7, 66.7] | 113.7 [95.6, 143.4] | 196.6 [174.6, 214.7] |
| R-na | 63.5 [57.3, 83.8] | 113.7 [95.6, 143.4] | 196.6 [174.6, 214.7] |

### Exit usage

![Three bar panels, one per pre-movement, showing the percentage of agents leaving by exit A for arms C, U, S, R, R-na, R-det, R-prob and R+FIC, with one dot per seed. C, U and S are at 0 percent in every panel. The R arms are near 100 percent with no pre-movement and between 75 and 94 percent at 30 and 60 s](/images/fire-blind/exit_usage.png)

*Agents leaving by exit A [%], bar: median over seeds, dots: one seed each.
Exit A is 20 m from the junction, exit B 10 m. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

C, U and S send everyone to exit B, the nearer one. R sends 100 % [99, 100]
to exit A with no pre-movement, 88 % [81, 94] at 30 s and 84 % [78, 89] at
60 s. The initial exit is chosen in `_assign_initial_exit` (`scenario.py`),
and R's route cost prices the smoke each route meets on the way. With
foresight on (the default `"anticipate": true` of `RouteCostConfig`,
`route_graph.py`), the cost reads the smoke at the time the agent would
arrive at each point (`_arrival_time`), from the whole FDS record
([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)). No
occupant could perceive that. With the look ahead off (R-na), the cost
still reads the current smoke along the whole route, including parts no
occupant could see, and agents still end at exit A in the same
proportions.

### Pre-movement does not simply add

![RSET_last against a constant pre-movement of 0, 30 and 60 s for arms U, S and R, medians with markers and one faint line per seed. A dashed line of slope 1 through U at 0 s lies on top of U. S and R rise more steeply: at 60 s U is near 116 s, R near 197 s and S near 203 s](/images/fire-blind/additivity.png)

*RSET_last [s from ignition] against constant pre-movement [s], seeds
shared by all three pre-movements (n = 10). Thick: median; faint: one seed.
Dashed: slope 1 through U at 0 s. S and R are drawn slightly left and right
of the tick to keep the markers apart. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

For the same seed, RSET(pre) − pre − RSET(0) is exactly 0.00 s for U and C
in every seed. That follows from how the run is built: the pre-movement is
constant, everyone starts together, and nothing reacts to the fire. S adds
29.9 s more than the pre-movement at 30 s and 61.8 s more at 60 s; R adds
24.7 s and 75.4 s (medians). The fire grows while people wait, so a later
start meets thicker smoke. An uncoupled run cannot show that: waiting
longer only shifts its curve.

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

![Three strip-plot panels, one per pre-movement, showing per-seed differences S minus U, R minus U and R-na minus U in seconds, with a zero line and a black median bar. With no pre-movement S minus U is above 0 in 20 of 20 seeds, R minus U in 14 of 20 with values from minus 16 to plus 18, R-na minus U in 19 of 20. At 30 and 60 s all differences are above 0 in 10 of 10 seeds, between 8 and 106 s](/images/fire-blind/rset_paired.png)

*RSET_last difference per seed [s], same seed in both arms. Above 0: U gets
out earlier. Black bar: median. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

| Pair | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| S − U | +17.6 s; S > U in 20/20 | +45.9 s; 10/10 | +85.4 s; 10/10 |
| R − U | +2.4 s [−15.9, +17.9]; R > U in 14/20 (p = 0.12) | +28.0 s; 10/10 | +81.0 s; 10/10 |
| R − S | R < S in 20/20 | R < S in 9/10 | R < S in 6/10 (p = 0.75) |
| R-na − R | +4.8 s; R-na > R in 19/20 | identical | identical |

- **Against S, U is not conservative** at any pre-movement: smoke slows
  people, and U leaves that out.
- **Against R, U is not conservative at 30 and 60 s.** With no pre-movement
  the direction is not resolved: R is later than U in 14 of 20 seeds on the
  last agent out, and in 15 of 20 on p95. The median gap, 2.4 s, is below
  the seed-to-seed spread of U itself.
- **The gap grows with pre-movement**, for R − U from a few seconds to
  about 80 s and for S − U from 18 s to 85 s, because the fire grows while
  people wait.
- **R against S:** R is faster in 20 of 20 seeds with no pre-movement, by
  avoiding exit B's smoke; in 9 of 10 at 30 s (p = 0.02, weak by the rule
  above); and in 6 of 10 at 60 s (not resolved).

### ASET − RSET at fixed points

![A three-by-three grid of panels: rows are the criteria K 0.3 per metre, HCl 300 ppm and HCl 1000 ppm, columns the pre-movements 0, 30 and 60 s. Each panel shows location ASET minus RSET_last for exit A, branch mouth, junction and exit B, one marker per arm U, S, R and R-na with a min-max line, and a vertical line at 0. Almost every marker lies left of 0. With no pre-movement, in the HCl 1000 ppm row U, R and R-na reach right of 0 at the junction and branch mouth, and U's range also crosses 0 at exit A; in the HCl 300 ppm row U's range crosses 0 at the branch mouth; an annotation reads branch mouth, seeds that pass of 20: U 19, S 4, R 20, R-na 14](/images/fire-blind/margins.png)

*Location ASET − RSET_last [s] at four fixed points, the same points for
every arm; marker: median over seeds, line: min–max. Right of 0: the last
agent is out before the limit is met there. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

Seeds in which the margin is positive (pass), at exit B / junction / branch
mouth / exit A:

| Criterion | pre-movement | U | S | R | R-na |
|---|---|---|---|---|---|
| *K* ≥ 0.3 1/m | 0, 30, 60 s | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| HCl ≥ 300 ppm | 0 s | 0/0/**2**/0 of 20 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| HCl ≥ 1000 ppm | 0 s | 0/**15**/**19**/**2** of 20 | 0/0/4/0 | 0/10/**20**/0 | 0/3/14/0 |
| HCl, either level | 30, 60 s | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| FED ≥ 0.3 | 0, 30, 60 s | all pass | all pass | all pass | all pass |

- **Visibility fails in every arm, seed and pre-movement;** FED 0.3 passes
  in every seed of U, S, R and R-na. For these criteria the arm changes the
  size of the margin, not the verdict. R+FIC at 30 and 60 s is undetermined
  for FED 0.3: its RSET is censored ([Sensitivity arms](#sensitivity-arms)).
- **HCl with no pre-movement is knife-edge.** U's median margin at the
  junction under HCl 1000 ppm is about +2 s (59 − 56.9), inside the seed
  spread. So a single uncoupled run can give either verdict. The coupled
  arms pass less often at this level (36 point-passes in U, 30 in R, 17 in
  R-na, 4 in S), and R keeps most of U's. U is the more cautious arm in
  one cell only: at the branch mouth under HCl 1000 ppm, R passes in 20 of
  20 seeds and U in 19.
- These flips sit mostly at HCl 1000 ppm (ISO FEC 1, an incapacitation-level
  value), not at the design value FEC 0.3, and the HCl in this deck is
  probably overestimated (see [Limits](#limits)).

**People inside when the junction reaches the visibility limit** (24 s):
with no pre-movement a median of 72 in U, 74 in S, 83 in R and 92 in R-na;
U has fewer than R in 20 of 20 seeds (median 11 fewer). At 30 and 60 s all
100 are inside in every arm. So U is not conservative on this count.

### Dose {#dose}

![A three-by-three grid of cumulative distributions, rows for pre-movement 0, 30 and 60 s, columns for max FIC per agent, seconds at HCl 300 ppm or more, and seconds at K 0.3 per metre or more, for arms U, S and R. In the FIC column the R curve lies far left of U, and S right of U. In the two time columns S lies right of U in every row; R lies near U with no pre-movement and far right of U at 30 and 60 s](/images/fire-blind/exposure.png)

*Share of agents with a value ≤ x, pooled over seeds (2,000 agents with no
pre-movement, 1,000 at 30 and 60 s). Curve further right: more dose. Values
until each agent's exit, at z = 2.0 m (the deck's only slice height; the
1.6 m default resolves to it, see
[A crowd in a real fire › The fire](first-fds-case.md#3-the-fire)), 1 s
resolution. Seconds at *K* ≥ 0.3
1/m are secondary: obscuration alone is not treated as incapacitating for
people who are not performing tasks (ISO 13571:2012, §4.5, note).
Regenerated by `scripts/docs/fire_blind_vs_coupled.py`.*

Per seed, U against R. R-na is identical to R at 30 and 60 s; with no
pre-movement it differs (for example, U has fewer seconds at HCl ≥ 300 ppm
than R-na in 15 of 20 seeds).

| Dose metric | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| Median of the agents' peak FIC | U higher in 20/20 | U higher in 10/10 | U higher in 10/10 |
| Agent-seconds at HCl ≥ 300 ppm | mixed: U higher in 12/20 | U lower in 10/10 | U lower in 10/10 |
| Agent-seconds at HCl ≥ 1000 ppm | U higher in 20/20 | U lower in 10/10 | U lower in 10/10 |
| Max FED | U higher in 18/20 | U lower in 10/10 | U lower in 10/10 |
| Agents past *K* 0.3 or HCl 300 ppm before getting out | U more in 20/20 | 100 in every arm | 100 in every arm |

- **Against R, "conservative" depends on the metric.** U over-states the
  peak FIC in every seed: U walks into exit B's HCl, which R avoids. At 30
  and 60 s U under-states the time above both HCl levels and the max FED in
  every seed, because R walks longer in thicker smoke.
- **Against S, U under-states the run totals** in every seed, at every
  pre-movement: agent-seconds at HCl ≥ 300 and ≥ 1000 ppm and at *K* ≥ 0.3
  1/m, and max FED. On single agents it does not always: U's peak FIC is
  higher than S's for 605 of 2,000 agents with no pre-movement, 257 of 1,000 at
  30 s and 239 of 1,000 at 60 s.
- The largest max FED is 0.25 in U, S and R. That is not a statement of
  tenability: FED 0.3 is a threshold for susceptible people, and FED < 1
  does not mean safe
  ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).

**Per-agent margin**, first crossing of *K* 0.3 1/m minus the agent's own
exit, compared on the same agent (seed, origin, spawn order):

| | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| Agents crossing in both U and R | 900 of 2,000 | 1,000 of 1,000 | 1,000 of 1,000 |
| Median R − U among them | −5.6 s (R smaller in 668) | −10.8 s (879) | −30.4 s (987) |
| Median S − U, crossing in both | −1.6 s (S smaller in 1,518 of 1,876) | −16.2 s (953) | −37.8 s (991) |

With no pre-movement, 983 agents cross the limit in U but not in R, and 4
the other way round. Counting an agent that never crosses as having an
infinite margin, R has the larger margin for 1,215 agents and U for 672. So
with no pre-movement the direction depends on how agents who never cross
are counted; at 30 and 60 s U's margin is larger (not conservative) for
879 and 987 of 1,000 agents.

### Is exit usage conservative?

Exit usage is not conservative or otherwise. Choosing exits is part of the
scenario: each design fire scenario is analysed with design occupant
scenarios, and the occupants' initial route choice is one of the
variables of such a scenario (Nilsson and Fahy 2016, pp. 2047, 2061).
Here the difference is large: exit B for everyone without the fire, exit A for 84–100 % with it. It also drives the
dose differences above.

### Sensitivity arms {#sensitivity-arms}

{{< details title="Incapacitation, per-agent thresholds, HCl slowdown and route look ahead" closed="true" >}}

| Arm | Flags on top of R | Result |
|---|---|---|
| R-na | `"anticipate": false` in the scenario's `routing` block (see below) | Later than R with no pre-movement (+4.8 s, 19 of 20 seeds). Identical to R at 30 and 60 s: same exits and same histories. |
| R-det | tenability on (FED 1 incapacitates) | Identical to R: nobody reaches FED 1. |
| R-prob | R-det with `--incapacitation-mode probabilistic` | At 60 s, 5 agents are incapacitated, one in each of 5 of 10 seeds. RSET is censored (> 270 s) in those seeds. The last exit among the rest is 196.6 s, as in R. Their dose counts only until incapacitation. |
| R+FIC | R-det with `--enable-fic-speed` | No pre-movement: RSET 112.5 s [97.3, 148.2], with 30 [19, 44] agents at the 0.3 speed floor. At 30 s: censored in 10 of 10 seeds, 84 of 1,000 agents inside at 270 s. At 60 s: censored in 10 of 10, 763 of 1,000 inside. Max FED reaches 0.44 and 0.45. |

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
Simulation finished in 63.06 s (100/100 evacuated).
```

All 100 leave by exit A, as in R. The study script builds the same files
(`write_noanticipate`).

A censored RSET is only known to exceed 270 s. It is never compared by size
with U's. An agent incapacitated or still inside at 270 s never counts as
out, so a coupled RSET cannot look shorter because people dropped out of
the count. R+FIC is an upper bound: it is mostly censored, its dose stops at
the cap, and it rests on HCl that is probably overestimated.

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
figures in `site/static/images/fire-blind/`. The 320 runs took 43 min of
single-process time (11 min on 4 workers); the analysis alone takes about
30 s. Seeds 1–3 were used for a pilot and are left out. The maintainers
keep the runs in their data store, `fds-evac-data/t_junction/fire_blind_runs/`.

## Limits

- **One fire with no margin.** Here, at every point, the visibility limit
  is met before the last person gets out, in every arm. Schröder et al.
  (2020, §4) expect the fire's effect on route choice and speed to play a secondary role only
  while the safety margin is well above the limit. That is the regime in
  which practice decides, and this study does not test it.
- **The size of the S − U and R − U gaps is not measured behaviour.** The
  smoke-speed law is fitted to Frantzich and Nilsson's data, *K* ≈ 1.9–7.4
  1/m (read from their Fig. 14; see
  [walking speed in smoke](/fundamentals/walking-speed.md)), and has a floor
  of 0.1 from *K* = 11.1 1/m. Share of moving agent-seconds below / within /
  above that range, and at the floor:

  | Arm | pre-movement 0 s | 30 s | 60 s |
  |---|---|---|---|
  | S | 80 / 14 / 6 %, floor 3 % | 37 / 37 / 26 %, floor 14 % | 1 / 40 / 60 %, floor 25 % |
  | R | 90 / 10 / 0 %, floor 0 % | 39 / 55 / 6 %, floor 2 % | 1 / 51 / 48 %, floor 6 % |

  Below 1.9 1/m the law is outside the data too. There it slows people by
  2.4 % at *K* = 0.3 1/m, the visibility limit, rising to about 15 % at
  1.9 1/m.

  ![Left: the speed factor against the extinction coefficient K from 0 to 25 per metre, solid over the Frantzich and Nilsson data range 1.9 to 7.4, dashed outside it, falling from 1 at K 0 to the floor 0.1 at K 11.1 and flat after. Right: histograms of K at moving agents in arms S and R; the largest bin is below 0.5 per metre, with a tail beyond 11; an annotation gives S 31 percent above 7.4 and 13 percent at the floor, R 19 and 3 percent](/images/fire-blind/speed_extrapolation.png)

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
  see, and it gives the same exits.
- **HCl is probably overestimated.** The deck has no HCl loss to walls
  ([A crowd in a real fire › What this does not show](first-fds-case.md#what-this-does-not-show)).
  That makes the HCl crossings early and inflates R+FIC.
- **The HCl slowdown is opt-in**, off in S and R, and incapacitation uses
  the FDS+Evac FED ([FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source)
  has no irritant slowdown), not HCl.
- **Constant pre-movement.** Everyone waits the same 0, 30 or 60 s. The three
  values were fixed from the fire before any run: 0 s moves before the
  junction reaches the visibility limit (24 s), 30 s falls between the first
  and last of the six points of
  [A crowd in a real fire](first-fds-case.md#at-fixed-points-location-aset)
  (18–46 s), 60 s after all of them.
- **Everyone knows both exits** (`familiarity: "full"`). Agents who discover
  exits could fail to find one, and the familiarity draw depends on the
  JuPedSim id ([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)).
  For sign loss in this fire, see
  [A crowd in a real fire](first-fds-case.md#at-fixed-points-location-aset).
- **The time limit is 270 s**, 30 s before the end of the FDS output. Route
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

- Engineers Australia Society of Fire Safety (2014). *Practice note for
  tenability criteria in building fires*, version 2.0, §5.2 and Fig. 8,
  *Tenability Criteria – Short Exposure*, p. 15. Full reference on
  [ASET and RSET](/fundamentals/aset-rset.md).
- Frantzich, H., & Nilsson, D. (2003). *Utrymning genom tät rök: beteende
  och förflyttning*, Fig. 14. Full reference on
  [walking speed in smoke](/fundamentals/walking-speed.md).
- ISO 13571:2012, §4.5 (note) and §5.2; ISO/TR 16738:2009, Eq. 1, Eq. 2
  and §5.6: paraphrased; see [ASET and RSET](/fundamentals/aset-rset.md).
- Nilsson, D., & Fahy, R. (2016). Selecting scenarios for deterministic fire
  safety engineering analysis: life safety for occupants. *SFPE Handbook of
  Fire Protection Engineering*, 5th ed., Ch. 57, pp. 2047, 2061.
  [doi:10.1007/978-1-4939-2565-0_57](https://doi.org/10.1007/978-1-4939-2565-0_57)
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
- [The Schröder room](study-schroeder2020.md): arm U only, as ASET − RSET
  maps.
