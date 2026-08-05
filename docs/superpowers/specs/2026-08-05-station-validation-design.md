# The Station nightclub: validation against witness statements

Date: 2026-08-05

## Why this replaces the earlier plan

The first Station plan validated against NIST NCSTAR 2 Vol. I §6.6 Table 6-2 —
evacuation times and per-exit counts from Simulex and buildingEXODUS. That is a
**model-to-model** comparison, and it tests the parts of pyFDS-Evac that are
least interesting: geometry and congestion. Neither reference model has
familiarity or sign visibility, so the two mechanisms this project exists to
model could not appear in the comparison at all.

`materials/rita.pdf` — Fahy, Proulx & Flynn, *"The Station Nightclub Fire — An
analysis of witness statements"*, Fire Safety Science 10:197–209 (2011),
doi:10.3801/IAFSS.FSS.10-197 — is an analysis of statements from 355 survivors.
It gives **empirical human data on exactly the two mechanisms**: who knew which
exits, and which exit each person actually used from where they were standing.

NCSTAR keeps a role: it supplies the dimensioned geometry, the door clear
widths, and a clear-air cross-check. But the primary target moves to observed
behaviour.

Source note: the paper's Table 2 (exits used by starting location) did not
render legibly from the scanned PDF. Every per-location number below is taken
from the prose on pp. 11–12, which restates the same breakdown. Before building,
the table should be read directly and any discrepancy resolved in its favour.

## What the paper gives us

### Aggregate exit usage (share of survivors, p. 12)

| exit | share |
|---|---|
| front (main) door | 35.8 % |
| main bar door | 20.0 % |
| stage door | 6.5 % |
| kitchen door | 5.4 % |
| **windows** | **27.9 %** (16.1 main bar, 7.3 sunroom, 4.5 unspecified) |

Exit usage was determined for 347 of 355 survivors; 127 left by the front door.
At least another 62 *attempted* the front door and failed — 34 of those went out
a window, 25 through another door. So **at least 50 % of survivors tried or
succeeded in using the front door**, out of four available doors.

### Exit choice by starting location (pp. 11–12)

The row that matters most, because it is the one a nearest-exit model gets
wrong:

| from | n | front | stage | main bar door | windows | kitchen | unspec. |
|---|---|---|---|---|---|---|---|
| **near stage / dance floor** | 75 | 16 | 7 | 4 | 40 | 1 | 7 |
| behind dance floor / soundboard | 74 | 40 | – | 15 | 14 | 1 | 4 |
| between the two bars | 29 | 15 | – | 9 | 2 | – | 3 |
| rear bar / dart room | 28 | 4 | – | 10 | 3 | 10 | 1 |
| near the stage door | 17 | 3 | 10 | 1 | 1 | 1 | 1 |
| sunroom | 16 | 4 | 2 | 1 | 6 | – | 3 |
| along the back wall | 15 | 3 | – | 4 | 7 | 1 | – |
| back hallway / restrooms | 14 | 3 | – | 3 | 3 | 3 | 2 |
| main bar area (excl. 6 at its door) | 31 | 8 | – | 18 | 2 | – | 3 |

Two findings pull in opposite directions and the model must reproduce both:

- **"The people closest to exit doors almost always used those doors."** The 17
  in the entranceway used the front door; 4 on stage used the stage door; 6 by
  the main bar door used it.
- **Except where the fire intervened.** Of the 75 by the stage, only 16 reached
  the front door and 7 the stage door — *their two closest exits*. Forty went
  out windows and 4 crossed the venue to the main bar exit.

And the front door's pull is visible from far away: 40 of the 74 behind the
dance floor used it, and 31.5 % of all front-door users started there.

### Familiarity, quantified (pp. 6–7)

Visit frequency, for 288 of the surviving patrons:

| | count | share |
|---|---|---|
| first visit | 84 | 29.2 % |
| second visit | 31 | 10.8 % |
| 3–5 visits | 62 | — |
| *subtotal ≤5 visits* | *177* | *just over 60 %* |
| regulars | ≥24 | — |

Exit awareness, for the 82 patrons where it was recorded:

- 32 aware of all or most alternate exits
- **24 not aware of the location of the alternate exits**
- 14 aware of the exit near the stage; 10 of the main bar exit; **2 of the
  kitchen exit**
- Of first-time visitors: 8 unaware of any alternate, 3 aware of the stage door
  (two of them because they were standing next to it)

**All patrons entered through the front door** — tickets collected, hands
stamped. And of the 56 who arrived after 22:30, **none reported awareness of any
alternative exit**.

### Signs (p. 7)

- 25 survivors explicitly did not notice any exit sign
- the stage-door sign was **unlit**: six noticed it unlit, one said there was no
  sign there at all
- lit signs were noticed in the main bar (2) and near the rear bar (3)

### Timing and victims

Untenable on the dance floor in **under 90 s**, and in the dart room and sunroom
ten seconds later. Of the 96 who died at the scene, **31 were in the entranceway
pile-up** and 18 in the sunroom along the wall adjoining it.

## Scenario definition

**Geometry** from NCSTAR Fig. 1-5 as before: 412 m² footprint, four doors, clear
widths from Table 7-6 (all side doors 914 mm; the front entrance limited by its
914 mm interior door). Internal walls belong in the WKT so `wkt_to_fds` carries
them into the FDS deck and hence into fdsvismap's occlusions.

**Initial positions** from Fahy Fig. 4 rather than NCSTAR's uniform densities —
the named areas with the counts in the table above. This is observed data
replacing an assumption.

**Familiarity** drawn to match the visit-frequency distribution, using the
scalar parameterisation (probability an exit is in the agent's map at t=0)
rather than the `full`/`discovery` binary:

- ~29 % first-time → knows only the front door
- ~11 % second visit → front door, plus a small chance of one alternate
- ~40 % occasional (3–5 visits) → front door plus roughly one alternate
- ~20 % regulars → most or all exits

**Every agent starts knowing the front door**, because every patron walked in
through it. That single rule is the mechanism behind the crush, and it is
empirically grounded rather than tuned.

**Signs**: stage door `c = 3` (unlit), main bar and rear bar `c = 8` (lit),
front door `c = 8`.

## Validation targets

Primary, in order of how much they discriminate between models:

1. **Origin→exit matrix**, compared row by row against the table above. A
   nearest-exit model reproduces the entranceway and stage rows and fails the
   dance-floor row.
2. **Front-door share** ≥ 50 % of agents attempting it.
3. **Aggregate per-exit split**, renormalised over door users (see below).

Secondary, as a sanity band rather than a target: NCSTAR Table 6-2's clear-air
times, 188 s (Simulex) and 202 s (buildingEXODUS), run with all hazard weights
at zero and full familiarity.

## Four things that bound what this can prove

**Windows are 27.9 % of egress and we do not model them.** This is the largest
threat to an honest comparison. Two options, and the choice must be stated in
the results rather than buried: renormalise over door users only (front 52.9 %,
main bar 29.5 %, stage 9.6 %, kitchen 8.0 %), or add windows as exits and
compare directly. Silently ignoring them would inflate apparent agreement,
because the 40 window users by the stage would be redistributed onto doors the
model does have.

**Survivor bias.** The matrix covers 355 survivors, not the ~455 present. The 96
who died are absent, and they were concentrated exactly where the model is most
stressed — 31 in the entranceway pile-up. Every row is conditioned on survival,
so the model should not be expected to reproduce it as an unconditional
distribution.

**A bouncer blocked the stage door.** Thirteen survivors mention it; some
diverted to the main door. We model no such intervention, so the stage-door row
carries an unmodelled suppression.

**The data is retrospective and self-reported.** The authors state it plainly:
statements were collected by police for a different purpose, with no consistent
question set, and the locations "cannot validly be used to calculate crowd
density." Treat counts as approximate and do not fit parameters to them.

## Model work this implies

- **Scalar familiarity** replacing the `full`/`discovery` binary, as the
  probability that each exit is in an agent's initial map.
- **Seed the map with the spawn area's entrance**, so an agent knows the door it
  came through. Empirically grounded here.
- The **auto-wiring/discovery degeneracy** must be resolved first: in an
  auto-wired graph, arrival at any crossing reveals every crossing and exit at
  once, which would erase the familiarity gradient this scenario depends on.

## Out of scope

- Windows as an egress route, unless the renormalisation proves inadequate.
- Group behaviour, though the paper documents it (124 of 275 who came with
  others were already with their party; 16 did not try to find them).
- Re-entry, altruistic behaviour, and injury outcomes.
- Fitting any parameter to the witness data. It is a validation target, not a
  calibration set — the distinction matters more here than usual, because the
  data is rich enough to fit and too uncertain to fit to.
