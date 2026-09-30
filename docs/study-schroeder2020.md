---
title: "ASET-RSET maps: the Schröder room"
linkTitle: "The Schröder room"
weight: 1
---

Schröder, Arnold and Seyfried (2020) turned the ASET-RSET comparison from
one number at one point into maps: a time for every 0.6 m cell of a room.
This page runs the same experiment again, with our own FDS fire and
pyFDS-Evac crowds, and shows three things:

- **ASET per fire quantity.** When each cell first exceeds a limit for smoke,
  temperature, CO, CO₂, radiation and dose, and which of them matter for
  this fire.
- **RSET per cell.** When the last person leaves each cell (Schröder's §2.3).
  This is the "ASET with regard to evacuation time" of the paper.
- **DIFF = ASET − RSET.** Where in the room the smoke arrives before the
  last person has left, and how the door-flow model, pre-movement and a
  second door move that.

{{< callout type="info" >}}
This is the same experiment with our own FDS and our own evacuation model.
None of the authors' data is used, and it is **not** a reproduction of their
figures. pyFDS-Evac does not build these maps itself; the script
`scripts/docs/schroeder_room_maps.py` does. A built-in version is planned in
[#210](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/210). This is
research software and one room: nothing here is a design or safety verdict.
{{< /callout >}}

## The result in brief

One door, the exit flow capped at 0.96 persons/s, everyone moving at t = 0,
smoke criterion K ≥ 0.23 1/m at 2.0 m, maximum over n = 10 seeds:

| | 0.2 m FDS grid | 0.1 m FDS grid | Paper, Fig. 5 (read off) |
|---|---|---|---|
| min DIFF | −30 s | −25 s | about −29 s |
| Area with DIFF < 0 | 6.4 m² | 5.2 m² | about 20 m² |
| C (bin-free) | −108 m²s | −83 m²s | – |

- **Smoke sets ASET here.** Every cell reaches K ≥ 0.23 1/m at 2.0 m, the
  last one at 88 s. The EA limits and the FED limits are not reached in any
  cell by 600 s. The vfdb CO and CO₂ values are reached only in plume cells
  on the 0.1 m grid, which is grid-dependent.
- **Only the queue fails.** The negative cells are the corner in front of
  the door, where people wait at the capped exit.
- **The door-flow model decides the sign.** Without the cap, the room
  empties in about 35 s and no cell has DIFF < 0.
- **The min DIFF is one cell.** It is the last cell before the door. The
  agreement with the paper's −29 s tests only when smoke reaches the door.
  Our negative area is about three times smaller than the paper's, and we
  have not found why ([below](#against-the-paper)).

## The room

![Four RSET maps of the 30 by 10 m room, shaded from white (0 s) to dark blue (about 125 s), with the burner as a red square in the south-west corner and the exits as green bars. (a) One door, capped: dark blue in the north-east corner in front of the door, latest 105 s. (b) One door, uncapped: pale everywhere, latest 35 s. (c) Two doors, capped: blue at both doors, latest 65 s. (d) Two doors, N = 200, capped: dark blue at both doors, latest 124 s.](/images/studies/schroeder2020/rset_maps.png)

*RSET maps of four versions (next section). The plan is the same in every
figure: 30 m × 10 m, burner red in the south-west corner, exit green on
the east wall, grey cells never visited by any agent.*

A 30 × 10 × 3 m room with one door, a fire in the opposite corner and 100
people who all start moving at once (paper §2.1). The paper leaves out the
fire ("we deliberately leave out details"), so we chose one:

- a constant 60 kW burner, 0.6 m × 0.6 m, burning flexible polyurethane
  foam, which yields soot and CO;
- FDS 6.10.1, 0.2 m cells (0.1 m as a grid check), 600 s;
- evacuation with the collision-free speed model, radius 0.15 m, free speed
  1.2 m/s, 10 seeds per version.

The full list of inputs, each marked as stated in the paper, read off a
figure, or assumed, is under [Setup and deviations](#setup-and-deviations).

## ASET: which fire quantity matters

ASET of a cell is the first time a criterion holds anywhere in that cell
at 2.0 m, counted from ignition. We screened every criterion of three
published sets, plus the pyFDS-Evac doses, and counted the cells that
exceed each one by 600 s.

![Dot plot of the number of map cells exceeded by 600 s for each criterion, grouped into four source sets, for three FDS runs. The smoke criteria K ≥ 0.23, 0.3 and 0.46 per metre reach all 848 cells in every run. Temperature at 45 or 50 °C reaches 6 to 15 cells. CO at 100 ppm reaches 2 cells and CO₂ at 1 % 3 cells, only on the 0.1 m grid. The total-flux heat doses reach 3 cells. Every other criterion reaches none, drawn as open markers at zero.](/images/studies/schroeder2020/criteria_screen.png)

*Map cells (0.6 m) exceeded by 600 s at z = 2.0 m, any FDS node of the
cell. Open markers: no cell. One marker shape per FDS run.*

| Source set | Criterion | 0.2 m, 1 door | 0.1 m, 1 door | 0.2 m, 2 doors |
|---|---|---|---|---|
| vfdb Table 8.3, < 30 min | K ≥ 0.23 1/m (the paper's criterion) | all 848, from 3 s | all 848, from 3 s | all 847, from 3 s |
| | T ≥ 45 °C | 15, within 2.7 m of the burner | 14, within 2.7 m | 14, within 2.7 m |
| | CO ≥ 100 ppm | 0 | 2, within 0.3 m | 0 |
| | CO₂ ≥ 1 % | 0 | 3, within 0.4 m | 0 |
| | radiant flux ≥ 1.7 kW/m² | 0 | 0 | 0 |
| vfdb Table 8.3, < 5 min | K ≥ 0.46 1/m (D_L 0.2, note 4) | all 848 | all 848 | all 847 |
| | T ≥ 50 °C | 7, within 0.9 m | 11, within 1.5 m | 6, within 0.9 m |
| | CO ≥ 500 ppm, CO₂ ≥ 3 %, radiant flux ≥ 2.5 kW/m² | 0 | 0 | 0 |
| EA Fig. 8, 2.0 m, up to 10 min | K ≥ 0.3 1/m (10 m visibility with C = 3) | all 848, from 3 s | all 848 | all 847 |
| | T ≥ 100 °C, radiant flux ≥ 2.5 kW/m², CO ≥ 2,700 ppm | 0 | 0 | 0 |
| Doses from ignition | gas FED ≥ 0.3 | 0 | 0 | 0 |
| | heat FED ≥ 0.3, convective | 0 | 0 | 0 |
| vfdb and EA | HCN | not applicable: not tracked | | |
| – | irritants | not applicable: the fuel has no tracked irritant | | |

"0" means not reached by 600 s at 2.0 m for this fire. That is a result for
this fire, not a pass, and it says nothing about a room that is safe.

The largest values anywhere on the 2.0 m slice, 0–600 s (0.2 m / 0.1 m
grid, one door): K 7.8 / 12.8 1/m, T 70 / 115 °C, CO 69 / 124 ppm, CO₂ 0.82 /
1.45 %, O₂ never below 19.5 / 18.5 %, gas FED 0.019 / 0.029, convective heat
FED 0.054 / 0.139.

{{< details title="What the criteria are, and what they are not" closed="true" >}}

- **The criteria are not incapacitation limits for a person.** K ≥ 0.23 1/m
  and 45 °C are guideline acceptance values of vfdb TB 04-01 (2020),
  Table 8.3, for a stay of up to 30 minutes. The paper uses both (§2.2.4).
  K = 0.23 1/m is D_L = 0.1 1/m converted with vfdb Eq. 8.1 (K = D_L · ln 10).
  ISO 13571:2012 §4.6 f treats the early effects of obscuration as
  behavioural and leaves them out of its incapacitation model.
- **Each set is shown whole.** Taking CO from one source and temperature from
  another would mix two sets of assumptions. Which set to adopt for the
  maps is still open.
- **The time column matters.** The evacuations here last under 5 minutes.
  For that column vfdb gives 50 °C, not 45 °C, and allows D_L = 0.2 1/m
  where the area is clearly laid out or people know it (note 4).
- **Temperature is not a criterion on its own.** vfdb Table 8.3, note 2:
  gas temperature is not to be assessed in isolation from smoke density.
  T ≥ 45 °C is never the first criterion in a cell here; it ties with smoke
  in 4 cells at the burner.
- **EA gives no visibility constant.** K ≥ 0.3 1/m for 10 m visibility uses
  C = 3, our assumption. EA §5.2 also allows 5 m (K ≥ 0.6 with C = 3) in
  enclosures of about 10 m, and reduced visibility where occupants may be
  queuing next to exits, which is where DIFF is negative here.
- **Radiant flux** is estimated as 0.25 · (U − 4σT_amb⁴) from the FDS
  `INTEGRATED INTENSITY` U, with T_amb = 20 °C (assumed): a small body in an
  isotropic field receives about U/4.
- **Gas FED ≥ 0.3** is the dose of someone standing still from ignition,
  with the pyFDS-Evac form of the FDS+Evac FED
  ([Fractional effective dose](/models/fed.md)). ISO 13571:2012 §5.4 and
  A.5.2 give 0.3 as the level that protects most of a susceptible
  population. No HCN is set, so its term is zero.
- **Heat FED ≥ 0.3** uses the clothed convective form of ISO 13571:2012
  §8.3.1, Eq. (9) ([Heat](/models/heat.md)). ISO sets no threshold for heat
  (§8.5); the 0.3 is a pyFDS-Evac choice, by analogy with A.5.2.
- **Total-flux heat, as a sensitivity.** The total-flux dose (SFPE Handbook
  Ch. 63, Eq. 63.43) with the radiant part f · (U − 4σT_skin⁴): at f = 0.25
  the radiant part never reaches the 2.5 kW/m² from which ISO counts it,
  and the tolerance dose reaches 0.3 in 3 cells next to the burner, from
  455 s (0.2 m) or 255 s (0.1 m). At f = 1, the upper bound the engine
  accepts, it passes 0.3 only in the same 3 cells and is not grid-stable
  (maximum 13.5 on the 0.2 m grid against 0.97 on the 0.1 m grid).

{{< /details >}}

### The ASET maps

![Four plan views of the one-door room at 2.0 m, shaded from dark (0 to 10 s) to light (150 to 600 s), beige for not by 600 s. (a) K ≥ 0.23 per metre: the burner corner exceeds first, within 10 s, the west half by about 40 s, the door region last at 75 to 88 s. (b) K ≥ 0.3 per metre: almost the same. (c) T ≥ 45 °C: only 15 cells at the burner; everything else beige, with a note that gas temperature is not to be assessed without smoke density. (d) Which criterion is first: smoke in every cell, a tie with temperature in 4 cells at the burner.](/images/studies/schroeder2020/aset_criteria_1door.png)

*One door, 0.2 m FDS grid. Dotted beige: not by 600 s, censored and not
filled with a value.*

Smoke fills the room from the burner corner eastward. The burner corner
exceeds first, within 10 s; the door region is among the last parts to
reach the limit, at 75–88 s.

{{< details title="Two doors, and the 0.1 m grid" closed="true" >}}

![The same four panels for the two-door room: the smoke map looks alike, with the latest cell at 189 s; temperature again only at the burner.](/images/studies/schroeder2020/aset_criteria_2door.png)

*Two doors, 0.2 m FDS grid. This is a separate FDS run: the second door
changes the ventilation. The cells at the west door D2 exceed K ≥ 0.23 1/m
at 21–32 s, the cells at the east door D1 at 73–76 s.*

![Three plan views: the K ≥ 0.23 ASET map on the 0.2 m and on the 0.1 m FDS grid, and their difference. The two agree within 16 s in the door region; the largest differences are in a late pocket near the fire.](/images/studies/schroeder2020/aset_grid_pair.png)

*The same ASET map on two FDS grids. Mean |Δ| 9 s; 6 % of cells differ by
more than 30 s. In the door region (x ≥ 24 m, y ≥ 6 m) |Δ| is at most 16 s
(95th percentile 7 s). The 0.1 m grid has a late pocket near the fire
(latest cell 203 s against 88 s) beside the plume, around x ≈ 1.5–5 m and
y ≈ 1–6 m; it is not grid-converged.*

{{< /details >}}

## RSET: when the last person leaves each cell

RSET of a cell is the last time any agent is in it (paper §2.3, Eqs. 4–5),
counted from ignition. The agents here do not see smoke: they walk at free
speed and keep their first exit ("arm U"), so their RSET does not depend on
the fire.

### The door flow

The collision-free speed model passes about 3 persons/s through the 1.2 m
door and empties the room in about 35 s. The paper's Fig. 3 implies about
0.96 persons/s and about 104 s. We therefore run two versions on the same
FDS output:

- **capped:** the exit removes at most one agent every 1/0.96 s
  (`enable_throughput_throttling`, `max_throughput: 0.96`; see
  [Scenario JSON](scenario-json.md));
- **uncapped:** the model's own flow, reported as a model difference.

![Two panels of agents in the room against time. Left, one door: the capped runs fall along a straight line through the paper's Fig. 3 points (97, 61, 23 and 0 at 0, 40, 80 and 120 s) and reach zero at about 105 s; the uncapped runs reach zero at about 34 s. Right, two doors: capped N = 100 reaches zero at 54 to 65 s, uncapped at about 21 s, capped N = 200 at 105 to 125 s.](/images/studies/schroeder2020/agents_remaining.png)

*n = 10 seeds per version: line median, band minimum to maximum. Black
squares: the paper's Fig. 3, read off. Dashed: the paper's extrapolation,
not data.*

The capped runs leave 62.2 ± 0.6 agents at 40 s and 24.1 ± 0.6 at 80 s;
the last agent leaves at 104–106 s. The paper's Fig. 3 shows 61 and 23.

{{< callout type="warning" >}}
This match is a calibration, not a validation. The 0.96 persons/s is read
off the same Fig. 3 (100 − 0.96 · 40 ≈ 61.6), so the check shows only that
the cap works as coded. The cap limits the removal rate at the exit; it is
not door-flow physics, and it has no test yet
([#355](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/355)).
{{< /callout >}}

### The RSET maps

The figure at the top of the page shows RSET for four versions. With the
cap, RSET is highest in the corner in front of the door, where the queue
forms (105 s). Without it, no cell is occupied after 35 s. With two doors,
N = 100 capped, the room is empty by 65 s; with N = 200, by 124 s.

| Version (maximum over n = 10) | Latest cell, one door | Latest cell, two doors |
|---|---|---|
| Capped, pre-movement 0 | 105 s | 65 s |
| Capped, pre-movement 10 s (the default) | 115 s | 75 s |
| Capped, pre-movement 30 s | 135 s | 95 s |
| Capped, pre-movement 60 s | 165 s | 125 s |
| Uncapped, pre-movement 0 | 35 s | 22 s |
| Capped, N = 200, pre-movement 0 | – | 124 s |

Pre-movement is a constant delay for everyone. "The default" is the
pyFDS-Evac default when a scenario sets no pre-movement key: a constant
10 s, the FDS+Evac `PRE_MEAN` (not the gamma preset).

## DIFF: where smoke arrives before the last person leaves

DIFF = ASET − RSET per cell (paper Eq. 7). A cell fails when DIFF < 0;
DIFF = 0 counts as a pass. DIFF is a time window between the first
exceedance in a cell and the last presence of *any* agent there. It is not
the exposure or dose of an individual; the paper says so itself (p. 6).
For per-agent exposure, see
[A crowd in a real fire](first-fds-case.md#aset-rset).

![Six DIFF maps of the one-door room, red and hatched where DIFF is negative, blue where it is positive, grey where no agent went. (a) capped, pre-movement 0, 0.2 m grid: a small red block in the north-east corner in front of the door; min DIFF −30 s, 6.4 m². (b) the same on the 0.1 m grid: −25 s, 5.2 m². (c) pre-movement 10 s: −40 s, 14.0 m². (d) pre-movement 30 s: red spreads along the north wall and the west end, −60 s, 70.5 m². (e) pre-movement 60 s: most of the room red, −90 s, 212.7 m². (f) uncapped: all blue, min DIFF +3 s.](/images/studies/schroeder2020/diff_1door.png)

*One door. ASET: K ≥ 0.23 1/m, any node of the cell, z = 2.0 m, about 1 s
steps. RSET: maximum over n = 10 seeds. No visited cell is censored.*

| One door, maximum over n = 10 | min DIFF | Area DIFF < 0 | C | Failing cells |
|---|---|---|---|---|
| Capped, pre-movement 0 | −30 s (−25 s) | 6.4 m² (5.2) | −108 m²s (−83) | 21 (17) |
| Capped, pre-movement 10 s | −40 s (−35 s) | 14.0 m² (9.8) | −204 m²s (−157) | 42 (30) |
| Capped, pre-movement 30 s | −60 s (−55 s) | 70.5 m² (58.8) | −920 m²s (−654) | 200 (167) |
| Capped, pre-movement 60 s | −90 s (−85 s) | 212.7 m² (184.3) | −5,605 m²s (−4,730) | 596 (517) |
| Uncapped, pre-movement 0 | +3 s (+3 s) | 0 | 0 | 0 |

*0.2 m FDS grid; in brackets the 0.1 m grid. Of the 848 cells, 757 are
visited in the capped versions; the 91 others are shown as "not visited"
and are outside the five DIFF states.*

- **Pre-movement shifts min DIFF one for one.** It delays everyone by the
  same constant, so −30, −40, −60, −90 s carry no new information. Only the
  area and C change shape across the pre-movement versions.
- **C** is Σ DIFF · A over the failing cells, in m²s (paper Eq. 8, without
  the paper's 20 s bins). The paper's authors "do not yet have a direct
  physical interpretation" of it (p. 7). Use it to rank versions, not as a
  quantity.
- **The door jambs.** The walkable area has 0.8 m deep jambs either side of
  the door ([Setup and deviations](#setup-and-deviations)). They take about
  1.1 m² (about 3 cells) out of the corner where RSET is highest, so every
  area here is up to about 1.1 m² smaller than without them.

![Two dot plots, one row per version. Left, min DIFF: the capped versions from −30 to −101 s, the uncapped at +2 and +3 s, with the paper's −29 s as a star next to −30. Right, the area with DIFF below zero: 6.4 to 212.7 m² for one door and 5.8 to 204.9 m² for two doors, the paper's 20 m² as a star to the right of 6.4. Open diamonds show the 0.1 m grid next to each one-door point.](/images/studies/schroeder2020/diff_measures.png)

*Maximum over n = 10 seeds. Filled: 0.2 m FDS grid; open diamonds: 0.1 m
grid; grey bar: the grid band. Two doors: no 0.1 m run, so no grid band.*

### Two doors

![Six DIFF maps of the two-door room. With the cap, red cells appear at both doors, first and most at the west door D2; with pre-movement 60 s most of the room is red. Uncapped: all blue. N = 200, capped: red blocks at both doors, deepest at the west door.](/images/studies/schroeder2020/diff_2door.png)

*Two doors, 0.2 m FDS grid only: there is no 0.1 m two-door run, so no grid
band, and the one-door band does not carry over.*

| Two doors, maximum over n = 10 | min DIFF | Area DIFF < 0 | C |
|---|---|---|---|
| Capped, pre-movement 0 | −39 s | 5.8 m² | −129 m²s |
| Capped, pre-movement 10 s | −49 s | 14.2 m² | −221 m²s |
| Capped, pre-movement 30 s | −69 s | 55.0 m² | −837 m²s |
| Capped, pre-movement 60 s | −99 s | 204.9 m² | −4,567 m²s |
| Uncapped, pre-movement 0 | +2 s | 0 | 0 |
| Capped, N = 200, pre-movement 0 | −101 s | 22.2 m² | −898 m²s |

- **The second door is our assumption.** The paper names no position for it.
  We mirrored D1 onto the west wall, about 7 m from the burner. Smoke
  reaches the cells at D2 at 21–32 s, against 73–76 s at D1, so D2 sets
  every two-door min DIFF.
- **N = 100 with two doors is not the paper's thought experiment.** In §3.1
  the paper doubles the occupants *and* adds a second exit, and states that
  the margin "remains more or less unchanged". Only the N = 200 version
  tests that. Here it gives −101 s against −30 s for one door with N = 100,
  and the last agent leaves at 105–125 s against 104–106 s. This difference
  comes from our D2 position, so it neither confirms nor refutes the paper.
- **Seeds split the crowd.** Each seed draws the west/east split from a
  binomial distribution. Seed 10 of N = 200 put 119 agents west, and it sets
  the maximum; the per-seed mean of min DIFF is −86.4 s.

## How far to trust the numbers

Four sources of spread, on min DIFF for one door, capped, pre-movement 0:

| Source | Size | How measured |
|---|---|---|
| Seeds | ±0.3 s | 95 % bootstrap CI of the per-seed min DIFF, −29.8 [−30.0, −29.5] s |
| A tiny change of the fire | about 1 s | same grid, HRRPUA 166.87 against 166.7 kW/m²: −29.4 against −30.4 s |
| FDS grid | about 5 s | 0.2 m against 0.1 m: −30.4 against −25.4 s |
| Door-flow model | about 33 s | capped against uncapped: −30.4 against +2.5 s |

The seed spread is small because the cap, not the crowd, sets the exit
times. The area and C are less robust than min DIFF: 6.4 against 5.2 m²
between the grids.

### Against the paper

- **The min DIFF agreement is structural.** The worst cell is the last cell
  before the door, at (29.7, 8.7) m. Its RSET is about N/0.96 ≈ 105 s,
  set by the cap; its ASET is 75 s (80 s on the 0.1 m grid). So −30 s tests
  when smoke reaches the door, not the whole map. That cell lies inside the
  reach at which the engine removes agents at the exit
  ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349)).
- **The area is about three times smaller.** Ours fails in a compact block
  of 21 cells, x ≥ 27 m and y ≥ 6.6 m; the paper's Fig. 7 has about 55
  failing elements. The jambs explain about 1.1 m² of the gap. One
  hypothesis is a denser queue in the authors' model; we have not tested it,
  so the gap is unexplained.
- **The 60 kW fire is our assumption.** The paper does not state the
  demonstration HRR. Its Fig. 7 histogram (about 20 m² failing, C about
  −300 m²s, read off) matches the 60 kW, N = 100 point of its Figs. 5 and 8,
  which supports the choice but does not prove it.

{{< details title="Sensitivity to the map rules (one door, capped, pre-movement 0)" closed="true" >}}

| Variant | min DIFF | Area DIFF < 0 | C |
|---|---|---|---|
| Headline: K ≥ 0.23, ∃ rule, about 1 s | −30 s | 6.4 m² | −108 m²s |
| K ≥ 0.23 or T ≥ 45 °C | −30 s | 6.4 m² | −108 m²s |
| K ≥ 0.3 1/m | −30 s | 6.1 m² | −104 m²s |
| Nearest FDS node per cell | −30 s | 5.8 m² | −99 m²s |
| ∀ rule (Eq. 2 as printed) | −29 s | 5.5 m² | −95 m²s |
| ∀ rule, 0.1 m FDS grid | −23 s | 3.8 m² | −63 m²s |
| 10 s steps | −25 s | 5.1 m² | −76 m²s |
| The paper's demonstration settings: K ≥ 0.23 or T ≥ 45, nearest node, 10 s, 120 s fill | −25 s | 4.5 m² | −71 m²s |

- **∃ against ∀.** The paper's text (§2.2.3) counts a cell as exceeded when
  the criterion holds at any data point in it; Eq. 2 as printed reads "for
  all". We follow the text (∃); the ∀ row shows the difference.
- **The 120 s fill.** The paper gives cells that never exceed within 120 s
  the value 120 s (p. 4). We keep them open ("not by 600 s"). On the 0.2 m
  grid every cell exceeds by 88 s, so nothing changes. On the 0.1 m grid
  23 cells exceed only after 120 s, but none of them is occupied after
  120 s in any version, so no DIFF measure changes.

{{< /details >}}

{{< details title="Pooling: maximum, 95th percentile and per seed" closed="true" >}}

The paper pools the seeds by the maximum RSET per cell (p. 5), and so do
the tables above. Two other views, one door, 0.2 m grid:

| Capped, pre-movement 0 | min DIFF | Area DIFF < 0 | C |
|---|---|---|---|
| Maximum over n = 10 | −30 s | 6.4 m² | −108 m²s |
| 95th percentile over n = 10 | −30 s | 5.8 m² | −106 m²s |
| Per seed, mean [95 % bootstrap CI] | −29.8 [−30.0, −29.5] s | 5.6 [5.4, 5.8] m² | −94.5 [−95.5, −93.4] m²s |

With 10 seeds the 95th percentile interpolates between the 9th and 10th
values, so it lies close to the maximum. For two doors the views differ
more (capped, pre-movement 0): maximum −39 s, 95th percentile −37 s,
per-seed mean −29.1 [−32.8, −24.9] s, because the binomial split changes
how many agents use D2.

{{< /details >}}

## How the maps are computed

1. **ASET.** FDS writes slices at z = 2.0 m every second. For each
   criterion, each FDS node gets the first time it holds. A 0.6 m map cell
   takes the earliest of its nodes (the ∃ rule, the block maximum). The
   clock starts at ignition; a cell that never exceeds by the FDS end,
   600 s, stays open ("not by 600 s").
2. **RSET.** PedPy `compute_rset_map` with `RsetMethod.MAX`: the last frame
   at which any agent is in the cell, at 10 frames/s, frame 0 at ignition.
   ASET and RSET share PedPy's cell edges (asserted). The room is 10 m deep,
   so the top row is 0.4 m, and every area uses the true cell area.
3. **Pooling.** The maximum per cell over n = 10 seeds.
4. **DIFF** on every visited cell, in five states: pass, fail, ≥ bound
   (ASET not reached), ≤ bound and undetermined (RSET open; empty here,
   because every run empties the room).

**RSET here is not the RSET of ISO/TR 16738.** Its Eq. 2 adds detection,
alarm, pre-movement and travel times. RSET of a cell here is travel time
plus the modelled pre-movement, counted from ignition, with no detection or
alarm time, and it is the last time anyone is in that cell.

**The agents ignore the fire.** All runs use arm U:
`--smoke-blind --disable-tenability --smoke-slice-height 2.0` (see
[Usage](usage.md)). The trajectories are identical on the 0.2 m and the
0.1 m FDS output for all 50 one-door runs (asserted), so one RSET set per
door layout serves both grids. Smoke feedback on speed and route choice is
not part of this study.

**Reproduce.** The FDS decks and output are not in the repository. With
them in `DATA` and an empty folder `RUNS` outside the repository:

```bash
uv run --with "pedpy>=1.5.1" python scripts/docs/schroeder_room_maps.py \
    --data DATA --runs RUNS
```

It runs the 160 evacuations (existing ones are reused),
prints every number on this page as Markdown tables, and writes the
figures to `site/static/images/studies/schroeder2020/`. It needs PedPy ≥
1.5.1 for `compute_rset_map`.

## Setup and deviations

{{< details title="Every input, with its source" closed="true" >}}

Tags: **[P]** stated in the paper, **[F]** read off a paper figure, **[A]**
assumed because the paper is silent.

| Item | Value | Tag |
|---|---|---|
| Room | 30 × 10 × 3 m, one door, no other openings | [P] §2.1 |
| Door D1 | east wall, y = 8.2–9.4 m (1.2 m; 1.28 ± 0.05 m measured on Fig. 2), 2.0 m high, open | position and width [F]; height [A] |
| Door D2 (two doors) | west wall, y = 8.2–9.4 m, D1 mirrored | [A] |
| Fire | south-west corner, 0.6 × 0.6 m burner at x, y = 0.6–1.2 m | corner [P] §2.1; size and position [A] |
| HRR | 60 kW constant (HRRPUA 166.7 kW/m²) | [A] |
| Fuel | flexible PU foam GM21: soot yield 0.131, CO yield 0.010, ΔH_ch 17.8 MJ/kg, χr 0.52 from the same row | [A] SFPE Handbook 5th ed., App. 3, Tables A.38 and A.39 |
| Smoke | K_m = 8,700 m²/kg, the FDS default | [A] |
| Irritants, HCN | none tracked | [A] |
| FDS | 6.10.1, 0.2 m cells (0.1 m grid check), 600 s, slices every 1 s | 0.2 m [P]; rest [A] |
| Occupants | 100 (200 for N200), all placed at t = 0, uniform over the floor | N [P] §2.1 |
| Pre-movement | 0 [P]; 10 s (default), 30 s, 60 s constant | [P] / [A] |
| Model | collision-free speed model, r = 0.15 m, v0 = 1.2 m/s | [A]; 1.2 m/s is the paper's v_max |
| Exit cap | 0.96 persons/s per exit | [F] Fig. 3 |
| Two-door split | per seed, binomial by floor area west and east of x = 15 m | [A] |
| Seeds | 1–10 | n = 10 [P] p. 5 |

**Deviations from the paper**

- **Our own FDS and model.** None of the authors' data is used.
- **Censoring instead of the 120 s fill**, the ∃ rule, and 1 s steps
  instead of 10 s. The sensitivity table above shows each change.
- **Door jambs, 0.8 m deep, in the walkable area only.** The engine removes
  an agent within its radius + 0.5 m of a random point in the exit polygon,
  which makes a door drawn flush with the wall act about 1.3 m wider
  ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349)).
  The jambs force every agent into the 1.2 m passage. They cost about
  1.1 m² (about 3 cells) at the north-east corner. FDS has no jambs.
- **One-door and two-door rooms are separate FDS runs**, so the ventilation
  differs as well as the egress.
- **FDS device trees sit on mesh interfaces.** They are not used for the
  maps.

**Grid.** The characteristic fire diameter at 60 kW is D* ≈ 0.31 m, so
D*/δx = 1.56 at 0.2 m and 3.1 at 0.1 m, and H/D* = 9.6. The FDS User's
Guide (§6.3.6) warns against taking any tabulated D*/δx as an acceptable
minimum. The 2.0 m slice sits in a weak, smeared layer interface, about
1–5 K above ambient, so first crossings there are ill-conditioned. Neither
grid is shown to be converged: min DIFF and the door-region ASET agree
within 5 s and 16 s; the area and C do not, so both grids are given.

{{< /details >}}

## Limits and open issues

- **Not modelled here:** smoke slowing agents or changing their route, and
  signs losing visibility. Both are open questions for the built-in maps
  ([#210](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/210)).
  Sign visibility is a wayfinding map and never enters DIFF
  ([#140](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/140)).
- **Engine issues that touch this study:** exit removal ignores the door
  width ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349));
  the initial exit uses the spawn area, not the agent, which is why the two
  doors need two spawn areas
  ([#350](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/350));
  flow spawning breaks common random numbers across arms
  ([#353](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/353));
  exit throttling has no test
  ([#355](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/355)).
  The smoke-blind arm and exit replay
  ([#341](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/341)) and
  the guard against sampling past the FDS end time
  ([#340](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/340)) are
  in place.
- **Fire assumptions:** the HRR, the fuel and χr = 0.52, which comes from
  small-scale data, are ours.
- **One room, one fire.** The paper's other combinations of HRR and N were
  not run.

## Sources

{{< details title="Sources" closed="true" >}}

- Schröder, B., Arnold, L., & Seyfried, A. (2020). A map representation of
  the ASET-RSET concept. *Fire Safety Journal*, 115, 103154.
  [doi:10.1016/j.firesaf.2020.103154](https://doi.org/10.1016/j.firesaf.2020.103154).
  Version-of-record pages: Eqs. 1–3, 0.23 1/m, 2 m and 0.6 m p. 3; the
  120 s fill and Eq. 4 p. 4; Eq. 5 and pooling p. 5; Eq. 7 and the note on
  individual exposure p. 6; the two-exit thought experiment (§3.1), Fig. 5
  and Eq. 8 p. 7; Figs. 6–8 p. 8.
- vfdb (2020). *Leitfaden Ingenieurmethoden des Brandschutzes*, TB 04-01,
  §8.2, Eq. 8.1 and Table 8.3 with notes 2 and 4 (p. 325).
- Engineers Australia Society of Fire Safety (2014). *Practice note for
  tenability criteria in building fires*, version 2.0, §5.2 and Fig. 8
  (p. 15). Full reference on [ASET and RSET](/fundamentals/aset-rset.md).
- ISO 13571:2012, §4.6 f, §5.4, §8.3.1 Eq. (9), §8.4, §8.5 and A.5.2;
  ISO/TR 16738:2009, §5.7 Eq. (2). Paraphrased; see
  [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md).
- Purser, D. A., & McAllister, J. L. (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. *SFPE Handbook of Fire
  Protection Engineering*, 5th ed., Ch. 63, Eq. 63.43.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- *SFPE Handbook of Fire Protection Engineering*, 5th ed., App. 3, Tables
  A.38 and A.39 (fuel yields).
- McGrattan, K. et al. *Fire Dynamics Simulator User's Guide*, sixth
  edition, NIST SP 1019, §6.3.6.
- The original [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source),
  for `PRE_MEAN`.
- Code: `pyfds_evac/core/fed.py` (gas and heat FED rates),
  `pyfds_evac/core/scenario.py` (exit removal and throttling),
  `pyfds_evac/core/run_config.py` (`--smoke-blind`),
  `pyfds_evac/core/simulation_init.py` (`_apply_default_premovement`).

{{< /details >}}

## What next

- [ASET, RSET and the egress timeline](/fundamentals/aset-rset.md): the
  classic single-point comparison this page maps.
- [A crowd in a real fire](first-fds-case.md): per-agent exposure and a
  location ASET map on a real FDS fire.
- [RSET from an ensemble of seeds](howto-rset-ensemble.md).
- [Visibility through smoke](/fundamentals/visibility.md),
  [Fractional effective dose](/models/fed.md), [Heat](/models/heat.md).

pyFDS-Evac is research software, provided without warranty.
