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

**You need** the `fire_2MW_PVC` FDS output of that page (step 3 there says
where to get it) in `$FDS`. Each run below takes 4 to 6 s.

## The answer in short

For this fire and this T-junction, with 100 people placed at t = 0:

- **The workflow carries over exactly.** A smoke-blind run with the fire
  (arm U) gives the same trajectories as a run without it (arm C), and it
  records the dose along those fire-free paths.
- **RSET.** The uncoupled RSET is shorter than the speed-only coupled RSET
  in every seed. It is shorter than the fully coupled RSET in every seed
  when people wait 30 or 60 s before moving, and in 17 of 20 seeds with no
  wait, where the median gap is 3.7 s.
- **Dose.** Whether the uncoupled run over- or under-states the dose
  depends on the metric (see [the dose table](#dose)).
- **Exit usage** differs: without the fire everyone takes the near exit B;
  with smoke-aware routing (arm R) most agents take exit A.
- **The pass/fail verdict** at a fixed point is the same in every arm for
  visibility (fails), and in U, S, R and R-na for FED 0.3 (passes). For HCl
  with no wait, the verdict at ISO FEC 1 (not the design value 0.3) is
  knife-edge: a single uncoupled run can give either verdict. Summed over
  seeds and points, U passes 35 times, R 26, R-na 20 and S 5.

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
Simulation finished in 55.11 s (100/100 evacuated).
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
Simulation finished in 55.11 s (100/100 evacuated).
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
rows C 33665, U 33665, paired 33665
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
C: RSET_last 55.1 s, p95 52.4 s, exits {'exit_B_right': 100}
U: RSET_last 55.1 s, p95 52.4 s, exits {'exit_B_right': 100}
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
50%     0.00     1.25       4.0   11.5
max     0.02    17.86      13.0   26.0
agents at HCl >= 300 ppm for at least 1 s: 82
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
Simulation finished in 67.95 s (100/100 evacuated).
```

**Arm R, speed and routing.** The default coupled run. Smoke slows the
agents and enters their route cost:

```bash
uv run python run.py --scenario $SC --seed 4 --fds-dir "$FDS" \
    --disable-tenability \
    --output-sqlite ww/r.sqlite --output-exit-history ww/r_exits.csv
```

```text
Simulation finished in 62.94 s (100/100 evacuated).
```

C and R print `Reroute debug` lines; they do not affect the result.

`--disable-tenability` in S and R records FED and FIC but lets nobody be
incapacitated, so that everyone leaves and RSET stays defined. It also
turns off `--enable-fic-speed` ([Usage](usage.md#tenability-fic-slowdown-and-incapacitation)).
The study adds incapacitation and the HCl slowdown as separate arms
([below](#sensitivity-arms)).

Run the RSET snippet above with `("c", "u", "s", "r")`:

```text
C: RSET_last 55.1 s, p95 52.4 s, exits {'exit_B_right': 100}
U: RSET_last 55.1 s, p95 52.4 s, exits {'exit_B_right': 100}
S: RSET_last 67.9 s, p95 62.8 s, exits {'exit_B_right': 100}
R: RSET_last 62.9 s, p95 61.0 s, exits {'exit_A_left': 100}
```

In this seed smoke slows S by 12.8 s (67.9 against 55.1 s). R is 7.8 s
slower than U; across seeds R is later than U in 17 of 20 ([below](#rset)). Against S, which keeps exit B,
R is faster because every agent went to the far exit A and avoided B's
smoke. One seed says little: the study below runs 20 seeds with no
pre-movement and 10 each with 30 and 60 s.

**Reading the arms.** U → S isolates the effect of smoke on speed. S → R
isolates routing. R against R-na, the same run with the route cost's look
ahead in time off, isolates that look ahead.

### Evacuation over time

![Three panels, one per pre-movement of 0, 30 and 60 s, each showing agents out of 100 against time since ignition from 0 to 250 s for arms U (blue dashed), S (orange dash-dot) and R (red solid), with shaded min-max bands. Dotted vertical lines at 18, 24 and 45 s mark the location ASET for K at exit B, the junction and exit A. With no pre-movement the three curves overlap and end near 57 to 70 s. At 30 s, U ends first near 85 s, R near 117 s and S near 129 s. At 60 s, U ends near 115 s while S and R end near 187 to 193 s](/images/fire-blind/evacuated.png)

*Agents out (of 100) against time since ignition [s], median over seeds
(line) and min–max (band); n = 20 seeds with no pre-movement, 10 at 30 and
60 s. Dotted: location ASET for K ≥ 0.3 1/m at exit B, the junction and
exit A. Exit times from the trajectory at 0.1 s. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

The last agent out, median [min, max] over seeds, seconds from ignition:

| Arm | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| U (= C) | 56.5 [52.2, 61.1] | 84.8 [82.2, 91.1] | 114.8 [112.2, 121.1] |
| S | 70.0 [65.0, 98.5] | 129.4 [117.3, 151.0] | 187.0 [165.9, 227.1] |
| R | 60.5 [56.2, 64.6] | 116.6 [102.1, 130.2] | 192.8 [169.6, 216.4] |
| R-na | 62.0 [59.4, 66.6] | 116.6 [102.1, 130.2] | 192.8 [169.6, 216.4] |

### Exit usage

![Three bar panels, one per pre-movement, showing the percentage of agents leaving by exit A for arms C, U, S, R, R-na, R-det, R-prob and R+FIC, with one dot per seed. C, U and S are at 0 percent in every panel. R, R-det, R-prob and R+FIC are near 100 percent with no pre-movement and R-na near 94 percent; at 30 and 60 s all R arms lie between 78 and 93 percent](/images/fire-blind/exit_usage.png)

*Agents leaving by exit A [%], bar: median over seeds, dots: one seed each.
Exit A is 20 m from the junction, exit B 10 m. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

C, U and S send everyone to exit B, the nearer one. R sends 100 % [98, 100]
to exit A with no pre-movement, 88 % [85, 92] at 30 s and 86 % [80, 89] at
60 s. The initial exit is chosen in `_assign_initial_exit` (`scenario.py`),
and R's route cost prices the smoke each route meets on the way. With
foresight on (the default `"anticipate": true` of `RouteCostConfig`,
`route_graph.py`), the cost reads the smoke at the time the agent would
arrive at each point (`_arrival_time`), from the whole FDS record
([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)). No
occupant could perceive that. With the look ahead off (R-na), the cost
still reads the current smoke along the whole route, including parts no
occupant could see. Most agents still end at exit A: 94 % [91, 97] with
no pre-movement, and the same share as R at 30 and 60 s.

### U and R, animated

![Animation of arms U (top) and R (bottom) in the T-junction at 8 times real time, pre-movement 30 s. In both, 100 blue dots wait in the dead-end branch while grey smoke spreads from the burner near exit B along the corridor. After 30 s the U dots walk right to exit B, through the smoke and past the burner, staying small and blue; the last leaves at about 83 s. Most R dots turn left to the far exit A; they grow and turn pale and red as the smoke slows them, 11 go right to B, and the last leaves at about 119 s.](/images/fire-blind/agents_smoke_u_vs_r.gif)

*Arms U (top) and R (bottom), pre-movement 30 s, seed 11 (R's last agent
leaves at 118.7 s, the seed closest to the median of 116.6 s), 8 times real
time. Background: K from the FDS output, log scale. Dots are coloured and
sized by their speed factor, as in
[The run, animated](first-fds-case.md#the-run-animated). Regenerated by
`scripts/docs/study_animations.py`.*

Both crowds wait 30 s while the smoke spreads from the burner near exit B.
U then walks at free speed through that smoke to exit B, all 100 agents, and
the last is out at 82.7 s. In R, 89 agents turn to the far exit A, the smoke
slows them, and the last is out at 118.7 s. The animation shows 30 s of
pre-movement because it shows both effects, the exit and the speed. With no
wait, the two arms differ mainly in the exit.

### Pre-movement does not simply add

![RSET_last against a constant pre-movement of 0, 30 and 60 s for arms U, S and R, medians with markers and one faint line per seed. A dashed line of slope 1 through U at 0 s lies on top of U. S and R rise more steeply: at 60 s U is near 115 s, S near 187 s and R near 193 s](/images/fire-blind/additivity.png)

*RSET_last [s from ignition] against constant pre-movement [s], seeds
shared by all three pre-movements (n = 10). Thick: median; faint: one seed.
Dashed: slope 1 through U at 0 s. S and R are drawn slightly left and right
of the tick to keep the markers apart. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

For the same seed, RSET(pre) − pre − RSET(0) is exactly 0.00 s for U and C
in every seed. That follows from how the run is built: the pre-movement is
constant, everyone starts together, and nothing reacts to the fire. S adds
22.4 s more than the pre-movement at 30 s and 46.5 s more at 60 s; R
adds 26.4 s and 72.8 s (medians over seeds). That is not so in every
seed: one S seed adds only 0.1 s at 30 s, because its run with no wait was
slow (98.5 s). The fire grows while people wait, so a later
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

![Three strip-plot panels, one per pre-movement, showing per-seed differences S minus U, R minus U and R-na minus U in seconds, with a zero line and a black median bar. With no pre-movement S minus U is above 0 in 20 of 20 seeds, R minus U in 17 of 20 with values from minus 3 to plus 10, R-na minus U in 19 of 20. At 30 and 60 s all differences are above 0 in 10 of 10 seeds, between 19 and 110 s](/images/fire-blind/rset_paired.png)

*RSET_last difference per seed [s], same seed in both arms. Above 0: U gets
out earlier. Black bar: median. Regenerated by
`scripts/docs/fire_blind_vs_coupled.py`.*

| Pair | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| S − U | +14.4 s; S > U in 20/20 | +43.4 s; 10/10 | +71.1 s; 10/10 |
| R − U | +3.7 s [−3.1, +10.2]; R > U in 17/20 (p = 0.003) | +33.3 s; 10/10 | +76.4 s; 10/10 |
| R − S | R < S in 20/20 | R < S in 10/10 | R < S in 4/10 (p = 0.75) |
| R-na − R | +2.9 s [−2.5, +5.8]; R-na > R in 16/20 (p = 0.01) | identical | identical |

- **Against S, U is not conservative** at any pre-movement: smoke slows
  people, and U leaves that out.
- **Against R, U is not conservative at 30 and 60 s, and mostly not with
  no pre-movement.** With no pre-movement R is later than U in 17 of 20
  seeds, on the last agent out and on p95. The median gap, 3.7 s, is
  smaller than the seed-to-seed spread of U itself (52.2–61.1 s).
- **The gap grows with pre-movement**, for R − U from a few seconds to
  about 76 s and for S − U from 14 s to 71 s (medians), because the fire
  grows while people wait. The largest single R − U, 104 s at 60 s, comes
  from one R seed that ends at 216.4 s.
- **R against S:** R is faster in 20 of 20 seeds with no pre-movement, by
  avoiding exit B's smoke, and in 10 of 10 at 30 s (p = 0.002). At 60 s it
  is not resolved: R is later in 6 of 10, paired median +5.1 s.

### ASET − RSET at fixed points

![A three-by-three grid of panels: rows are the criteria K 0.3 per metre, HCl 300 ppm and HCl 1000 ppm, columns the pre-movements 0, 30 and 60 s. Each panel shows location ASET minus RSET_last for exit A, branch mouth, junction and exit B, one marker per arm U, S, R and R-na with a min-max line, and a vertical line at 0. Almost every marker lies left of 0. With no pre-movement, in the HCl 1000 ppm row U reaches right of 0 at the junction and the branch mouth, R and R-na at the branch mouth, R's range crosses 0 at the junction, and S's range crosses 0 at the branch mouth; an annotation reads junction, seeds that pass of 20: U 15, S 0, R 6, R-na 0](/images/fire-blind/margins.png)

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
| HCl ≥ 1000 ppm | 0 s | 0/**15**/**20**/0 of 20 | 0/0/5/0 | 0/6/**20**/0 | 0/0/**20**/0 |
| HCl ≥ 1000 ppm | 30, 60 s | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |
| FED ≥ 0.3 | 0, 30, 60 s | all pass | all pass | all pass | all pass |

- **Visibility fails in every arm, seed and pre-movement;** FED 0.3 passes
  in every seed of U, S, R and R-na. For these criteria the arm changes the
  size of the margin, not the verdict. R+FIC at 30 and 60 s is undetermined
  for FED 0.3: its RSET is censored ([Sensitivity arms](#sensitivity-arms)).
- **HCl with no pre-movement is knife-edge.** U's median margin at the
  junction under HCl 1000 ppm is about +2.5 s (59 − 56.5), inside the seed
  spread. So a single uncoupled run can give either verdict. The coupled
  arms pass less often at this level (35 point-passes in U, 26 in R, 20 in
  R-na, 5 in S), and R keeps most of U's. At every point and criterion U
  passes at least as often as each coupled arm. These counts hold only to
  a few seeds: changing nothing but the per-agent random draws
  ([#361](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/361)) moved them by up to 3 of 20 seeds at a point.
- These flips sit mostly at HCl 1000 ppm (ISO FEC 1, an incapacitation-level
  value), not at the design value FEC 0.3, and the HCl in this deck is
  probably overestimated (see [Limits](#limits)).

**People inside when the junction reaches the visibility limit** (24 s):
with no pre-movement a median of 73 in U, 73 in S, 83 in R and 88 in
R-na; U has fewer than R in 20 of 20 seeds (median 10 fewer). At 30 and 60 s all
100 are inside in every arm. So U is not conservative on this count.

### Dose {#dose}

![A three-by-three grid of cumulative distributions, rows for pre-movement 0, 30 and 60 s, columns for max FIC per agent, seconds at HCl 300 ppm or more, and seconds at K 0.3 per metre or more, for arms U, S and R. In the FIC column the R curve lies far left of U, and S right of U. In the two time columns S lies right of U in every row; R lies near U with no pre-movement, right of U at 30 s, and on top of S at 60 s](/images/fire-blind/exposure.png)

*Share of agents with a value ≤ x, pooled over seeds (2,000 agents with no
pre-movement, 1,000 at 30 and 60 s). Curve further right: more dose. Values
until each agent's exit, at z = 2.0 m (the deck's only slice height; the
1.6 m default resolves to it, see
[A crowd in a fire › The fire](first-fds-case.md#3-the-fire)), 1 s
resolution. Seconds at *K* ≥ 0.3
1/m are secondary: obscuration alone is not treated as incapacitating for
people who are not performing tasks (ISO 13571:2012, §4.5, note).
Regenerated by `scripts/docs/fire_blind_vs_coupled.py`.*

Per seed, U against R. R-na is identical to R at 30 and 60 s; with no
pre-movement it differs (for example, U has fewer seconds at HCl ≥ 300 ppm
than R-na in 16 of 20 seeds).

| Dose metric | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| Median of the agents' peak FIC | U higher in 20/20 | U higher in 10/10 | U higher in 10/10 |
| Agent-seconds at HCl ≥ 300 ppm | mixed: U higher in 11/20 | U lower in 10/10 | U lower in 10/10 |
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
  higher than S's for 633 of 2,000 agents with no pre-movement, 240 of 1,000 at
  30 s and 243 of 1,000 at 60 s.
- The largest max FED of any agent is 0.06 in U, 0.17 in R and 0.31 in S,
  each at 60 s. FED 0.3 still passes at the four fixed points in every arm
  (table above), but in S one agent exceeds it on the way out. A FED
  below 0.3 or 1 is not a statement of tenability: FED 0.3 is a threshold for susceptible people, and FED < 1
  does not mean safe
  ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).

**Per-agent margin**, first crossing of *K* 0.3 1/m minus the agent's own
exit, compared on the same agent (seed, origin, spawn order):

| | pre-movement 0 s | 30 s | 60 s |
|---|---|---|---|
| Agents crossing in both U and R | 945 of 2,000 | 1,000 of 1,000 | 1,000 of 1,000 |
| Median R − U among them | −6.0 s (R smaller in 743) | −10.8 s (902) | −34.2 s (993) |
| Median S − U, crossing in both | −1.4 s (S smaller in 1,485 of 1,877) | −15.8 s (979) | −35.0 s (998) |

With no pre-movement, 938 agents cross the limit in U but not in R, and
none the other way round. Counting an agent that never crosses as having an
infinite margin, R has the larger margin for 1,136 agents and U for 743. So
with no pre-movement the direction depends on how agents who never cross
are counted; at 30 and 60 s U's margin is larger (not conservative) for
902 and 993 of 1,000 agents.

### Is exit usage conservative?

Exit usage is not conservative or otherwise. Choosing exits is part of the
scenario: each design fire scenario is analysed with design occupant
scenarios, and the occupants' initial route choice is one of the
variables of such a scenario (Nilsson and Fahy 2016, pp. 2047, 2061).
Here the difference is large: exit B for everyone without the fire, exit A for 86–100 % with it. It also drives the
dose differences above.

### Sensitivity arms {#sensitivity-arms}

{{< details title="Incapacitation, per-agent thresholds, HCl slowdown and route look ahead" closed="true" >}}

| Arm | Flags on top of R | Result |
|---|---|---|
| R-na | `"anticipate": false` in the scenario's `routing` block (see below) | Later than R with no pre-movement (+2.9 s, 16 of 20 seeds), with 94 % [91, 97] at exit A against 100 % in R. Identical to R at 30 and 60 s: same exits and same histories. |
| R-det | tenability on (FED 1 incapacitates) | Identical to R: nobody reaches FED 1. |
| R-prob | R-det with `--incapacitation-mode probabilistic` | At 60 s, 4 agents are incapacitated, one in each of 4 of 10 seeds, and 5 agents are inside at 270 s. RSET is censored (> 270 s) in those 4 seeds. The median last exit among the rest is 192.9 s, against 192.8 s in R. Their dose counts only until incapacitation. |
| R+FIC | R-det with `--enable-fic-speed` | No pre-movement: RSET 119.9 s [100.5, 161.7], with 32 [22, 39] agents at the 0.3 speed floor. At 30 s: censored in 10 of 10 seeds, 117 of 1,000 agents inside at 270 s. At 60 s: censored in 10 of 10, 773 of 1,000 inside. Max FED reaches 0.45 and 0.44. |

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
Simulation finished in 63.82 s (100/100 evacuated).
```

95 leave by exit A and 5 by exit B; in R all 100 take exit A. The study script builds the same files
(`write_noanticipate`).

A censored RSET is only known to exceed 270 s. It is never compared by size
with U's. An agent incapacitated or still inside at 270 s never counts as
out, so a coupled RSET cannot look shorter because people dropped out of
the count. The R-prob and R+FIC runs that reach 270 s with agents inside
are incomplete, and `run.py` exits with status 2 for them
([Exit status](usage.md#exit-status)). R+FIC is an upper bound: it is mostly censored, its dose stops at
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
figures in `site/static/images/fire-blind/`. The 320 runs took 463 s
(about 8 min) of wall time on 8 workers, the default of `--workers`, on an
Apple M3 Pro; the analysis alone takes about 20 s. Seeds 1–3 were used for
a pilot and are left out. The maintainers keep the runs in their data
store, `fds-evac-data/t_junction/fire_blind_runs_f5c61f21/`.

The animation above is drawn from the same `RUNS` folder:

```bash
uv run python scripts/docs/study_animations.py fire-blind --data "$FDS" --runs RUNS
```

**Provenance.** The numbers and figures on this page come from runs of
commit `f5c61f21` on main, from a clean checkout. Each run's manifest
records that commit, `git_dirty: false` and
`agent_seeding: spawn-key-blake2b-v2`. The seed-4 walkthrough above gives
the same numbers as those study runs. When the code changes, re-run the
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
  | S | 80 / 13 / 6 %, floor 3 % | 37 / 37 / 26 %, floor 14 % | 1 / 40 / 59 %, floor 24 % |
  | R | 89 / 11 / 0 %, floor 0 % | 40 / 55 / 5 %, floor 2 % | 1 / 48 / 52 %, floor 7 % |

  Below 1.9 1/m the law is outside the data too. There it slows people by
  2.4 % at *K* = 0.3 1/m, the visibility limit, rising to about 15 % at
  1.9 1/m.

  ![Left: the speed factor against the extinction coefficient K from 0 to 25 per metre, solid over the Frantzich and Nilsson data range 1.9 to 7.4, dashed outside it, falling from 1 at K 0 to the floor 0.1 at K 11.1 and flat after. Right: histograms of K at moving agents in arms S and R; the largest bin is below 0.5 per metre, with a tail beyond 11; an annotation gives S 30 percent above 7.4 and 13 percent at the floor, R 20 and 3 percent](/images/fire-blind/speed_extrapolation.png)

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
  see. With no pre-movement it sends 94 % [91, 97] of the agents to exit A,
  against 100 % in R; at 30 and 60 s it gives the same exits as R.
- **HCl is probably overestimated.** The deck has no HCl loss to walls
  ([A crowd in a fire › What this does not show](first-fds-case.md#what-this-does-not-show)).
  That makes the HCl crossings early and inflates R+FIC.
- **The HCl slowdown is opt-in**, off in S and R, and incapacitation uses
  the FDS+Evac FED ([FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source)
  has no irritant slowdown), not HCl.
- **Constant pre-movement.** Everyone waits the same 0, 30 or 60 s. The three
  values were fixed from the fire before any run: 0 s moves before the
  junction reaches the visibility limit (24 s), 30 s falls between the first
  and last of the six points of
  [A crowd in a fire](first-fds-case.md#at-fixed-points-location-aset)
  (18–46 s), 60 s after all of them. Babrauskas et al. (2010,
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
