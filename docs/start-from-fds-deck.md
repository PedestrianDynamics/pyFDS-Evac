---
title: "Start from your own FDS case"
linkTitle: "From your FDS deck"
weight: 4
---

`pyfds-evac init` reads an FDS deck and writes a scenario folder that
`pyfds-evac` runs. It works on a plain FDS deck and on an FDS+Evac deck. It
also writes a report of everything it guessed, approximated or dropped.

On this page you check a deck before FDS runs, import a plain deck, add an
exit the deck lacks, and import an FDS+Evac deck. Each step shows the command
and its output.

{{< example-files-link "start-from-fds-deck" >}}

## Before you start

{{< example-files "start-from-fds-deck" >}}

Install the packages of the zip's `requirements.txt`, which include
pyFDS-Evac at the commit the zip was built from
(`pip install -r requirements.txt`, see [Install](install.md)), and run
every command from the unpacked zip. Steps 1 to 5 need no FDS; step 6
runs it.

The workflow, for any deck:

- check the deck: `pyfds-evac init DECK.fds --check`;
- import it: `pyfds-evac init DECK.fds`;
- read the summary and the exit status, supply what the deck lacks
  (`--agents`, `--exit`, `--walkable`), and import again;
- run the scenario in clear air;
- run FDS, then run the scenario on its output;
- refine the scenario in JuPedSim Web or the terminal UI.

## 1. Check the deck before you run FDS

An FDS run can take hours. The run of pyFDS-Evac then reads a few slices of
its output. Check that the deck asks for them first:

```bash
pyfds-evac init assets/t_junction/t_junction.fds --check
```

```text
FDS output check at z = 1.6 m (deck z; FDS moves a slice to the grid, up to half a cell):
  ✓ Extinction  z 2 m (requested 1.6 m, line 73); smoke speed and sign legibility read it
  ✓ CO          z 2 m (requested 1.6 m, line 76)
  ✓ CO2         z 2 m (requested 1.6 m, line 77)
  ✓ O2          z 2 m (requested 1.6 m, line 78)
  · Other gases HYDROGEN CHLORIDE z 2 m (FED adds the ones present)
  · Temperature none; needed for --enable-heat-fed or --heat-regime layer
  · Intensity   none; needed for --heat-radiant-source integrated-intensity
  ✓ T_END       300 s; init writes max_simulation_time 300 s
  · DT_SLCF     1 s (&DUMP DT_SLCF)
✓ The deck has what a pyFDS-Evac run reads.
```

The check reads the deck only and writes nothing. It looks for what the run
reads by default: the extinction coefficient (smoke slows the agents and
hides signs), CO, CO2 and O2 (the toxic dose, FED), and `&TIME T_END`.

- **✓** the deck has it. **✗** it is missing, with the `&SLCF` line to add.
- **·** information, such as the heat slices, which only opt-in flags read.
- **!** a warning that does not fail the check.

The deck asks for its slices at z = 2.0 m. The run samples smoke at 1.6 m,
the FDS+Evac head height, and takes the nearest horizontal slice, here 2.0 m.

{{< checkpoint title="Deck ready" >}}
The last line reads `✓ The deck has what a pyFDS-Evac run reads.` and
`echo $?` prints `0`. A deck with a ✗ line gives `3`, as in
[step 5](#5-an-fdsevac-deck); a deck that cannot be read gives `1`.
{{< /checkpoint >}}

The full list of items is in
[Usage › init --check](usage.md#check-a-deck-before-running-fds--pyfds-evac-init---check).

## 2. Import a plain FDS deck

`t_junction.fds` is the fire of [A crowd in a fire](first-fds-case.md): a
T-shaped corridor on four meshes of 30 m × 13 m, two `&OBST` blocks, a burner
and two `SURF_ID='OPEN'` vents at the corridor ends.

```bash
pyfds-evac init assets/t_junction/t_junction.fds
```

```text
assets/t_junction/t_junction.fds → assets/t_junction/t_junction_scenario/   (FDS deck)

  Walkable  150.0 m², 1 area                   Exits    2 of 2 (vent_2, vent_3)
  Spawn     1 area (100 placeholder agents)    Floor    z = 0 m

FDS output check at z = 1.6 m (deck z; FDS moves a slice to the grid, up to half a cell):
  ✓ Extinction  z 2 m (requested 1.6 m, line 73); smoke speed and sign legibility read it
  ✓ CO          z 2 m (requested 1.6 m, line 76)
  ✓ CO2         z 2 m (requested 1.6 m, line 77)
  ✓ O2          z 2 m (requested 1.6 m, line 78)
  ✓ T_END       300 s; init writes max_simulation_time 300 s

! 2 approximations (details: import_report.json)
  placeholder: 100 agents                                                    1 record
  fire surface over 2.000 m2 of the walkable area: agents may spawn on it    1 vent

Next:
  1. Run FDS:
       cd assets/t_junction && mpiexec -n 4 fds t_junction.fds
  2. pyfds-evac --scenario assets/t_junction/t_junction_scenario --fds-dir assets/t_junction
     (clear air: drop --fds-dir)
  3. Refine in JuPedSim Web (https://app.jupedsim.org) or pyfds-evac-tui
```

`init` wrote three files into the folder `t_junction_scenario` next to the
deck:

| File | What it holds |
|---|---|
| `config.json` | the JuPedSim scenario: exits, spawn area, agents, settings |
| `geometry.wkt` | the walkable area |
| `import_report.json` | every deck record that was mapped, approximated or dropped, with its line number |

What it derived:

- **Walkable area, 150.0 m².** The four mesh footprints (390 m²) minus the
  two `&OBST` blocks (170 m² and 70 m²). This is the polygon of
  `assets/t_junction/geometry.wkt`, drawn by hand for A crowd in a fire.
- **Two exits**, `vent_2` and `vent_3`, one per `OPEN` vent. Each is a strip
  0.5 m deep on the room side of the vent, with an exit sign.
- **One spawn area** of 147.0 m²: the walkable area minus the two exit strips.
- **100 agents**, a placeholder. The deck has no occupant count.
- **The burner** lies inside the walkable area. `init` reports it and does
  not cut it out: agents may spawn on it.

The FDS output check of step 1 runs again inside `init`. Its result never
changes the exit status of a plain `init`: the scenario can run in clear air
without FDS output.

{{< checkpoint title="Scenario written" >}}
`echo $?` prints `0`: the scenario is written and can run. Open
`geometry.wkt` in JuPedSim Web or any WKT viewer and compare it with the
plan. Every `&OBST` between 0.1 and 1.8 m above the floor blocks walking.
{{< /checkpoint >}}

Only the walkable area matches the scenario of A crowd in a fire. The
imported scenario has no journey and no junction checkpoint, it places 100
agents at once instead of letting them enter over time, every agent knows
both exits, and every agent waits a constant 10 s before moving.

## 3. Set the number of agents and run in clear air

Replace the placeholder with `--agents` and import again. `init` overwrites
a folder it wrote before, without asking.

```bash
pyfds-evac init assets/t_junction/t_junction.fds --agents 40
pyfds-evac --scenario assets/t_junction/t_junction_scenario --seed 1
```

The summary now reads `Spawn     1 area (40 agents)`. The run prints a
warning that the scenario sets no pre-movement, so every agent waits the
FDS+Evac default of 10 s, and ends with:

```text
Simulation finished in 34.70 s (40/40 evacuated).
```

{{< checkpoint title="Clear-air run completed" >}}
All 40 agents leave, and `echo $?` prints `0`.
{{< /checkpoint >}}

**Try it:** import with `--agents 400` and run again. The 400 agents queue
at the two exits, and the run ends with
`Simulation finished in 121.45 s (400/400 evacuated).` With `--agents 600`
the import stops with exit status 3:

```text
  - spawn area spawn_1 (147.000 m2) holds about 584 agents of radius 0.2 m, but 600 are requested: pass --agents N with a smaller N, or enlarge the walkable area
```

The capacity is the run's own estimate of how many agents it can place in
the area. The folder is still written, and the run refuses it. Import again
with `--agents 40` before you go on.

{{< details title="The run stopped with exit status 2" closed="true" >}}
Status 2 means the run reached `max_simulation_time` with agents still
inside ([Exit status](usage.md#exit-status)). It is not a setup error.
`init` copies the deck's `&TIME T_END` into `max_simulation_time`, or 300 s
without one, so a short `T_END` can cut the run off. Raise
`simulationParams.max_simulation_time` in `config.json`.
{{< /details >}}

## 4. A deck with no exit

`ISO-table21.fds` is the corridor of the [Quickstart](quickstart.md), 100 m
× 2 m, closed by four `&OBST` walls. It has no `OPEN` vent.

```bash
pyfds-evac init assets/ISO-table21/ISO-table21.fds
```

```text
assets/ISO-table21/ISO-table21.fds → assets/ISO-table21/ISO-table21_scenario/   (FDS deck)

  Walkable  200.0 m², 1 area      Exits    0 of 0
  Spawn     0 areas (0 agents)    Floor    z = 0 m

FDS output check at z = 1.6 m (deck z; FDS moves a slice to the grid, up to half a cell):
  ✓ Extinction  z 2 m (requested 1.6 m, line 20); smoke speed and sign legibility read it
  ✓ CO          z 2 m (requested 1.6 m, line 21)
  ✓ CO2         z 2 m (requested 1.6 m, line 22)
  ✓ O2          z 2 m (requested 1.6 m, line 23)
  ✓ T_END       120 s; init writes max_simulation_time 120 s
  ! DT_SLCF     2 s (&DUMP DT_SLCF), coarser than the run's smoke update interval of 1 s; fix: set &DUMP DT_SLCF=1 /

! 2 approximations (details: import_report.json)
  walkable component 0 (200.000 m2) has no exit: no agents placed there      1 record
  fire surface over 0.250 m2 of the walkable area: agents may spawn on it    1 vent

✗ Not runnable, so no run command:
  - no exit found: add exits in JuPedSim Web or with --exit x0,y0,x1,y1[,ior]
  - no agents to place
  Fix these (or pass --walkable, --exit, --agents), then run pyfds-evac init again.
```

The exit status is 3: the folder is written, but the scenario cannot run.
Without an exit there is no spawn area, so there are no agents either.

The `!` line is a warning. FDS writes a slice frame every 2 s; the run
updates the smoke every 1 s and takes the nearest frame, so the smoke the
agents see changes only every 2 s. `&DUMP DT_SLCF=1 /` in the deck removes
the warning.

Add the exit as a line, `--exit x0,y0,x1,y1`. The corridor ends at x = 50 m,
between y = −1 and 1 m:

```bash
pyfds-evac init assets/ISO-table21/ISO-table21.fds --exit 50,-1,50,1 --agents 20
pyfds-evac --scenario assets/ISO-table21/ISO-table21_scenario --seed 1
```

The import exits with 0, and the run ends with:

```text
Simulation finished in 89.12 s (20/20 evacuated).
```

An exit added with `--exit` gets no exit sign. The line must be parallel to
x or y and lie on a wall or a mesh edge next to walkable space. Add a fifth
number, the `IOR` of FDS `&EXIT`, when the room side is ambiguous.

{{< details title="The exit line is in the wrong place" closed="true" >}}
A line with no walkable space next to it stops the import with status 1,
and nothing is written:

```bash
pyfds-evac init assets/ISO-table21/ISO-table21.fds --exit 60,-1,60,1
```

```text
pyfds-evac init: error: --exit (60.0, -1.0, 60.0, 1.0): no walkable strip next to the line
```

x = 60 m lies outside the corridor. Read the extent of the meshes from
`&MESH XB` in the deck.
{{< /details >}}

## 5. An FDS+Evac deck

`evac_example1aA.fds` is an example of the FDS+Evac guide: one room, two
exits, four groups of 25 agents. The deck is GPL-3.0 and not in the zip.
Download it from
[tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide/blob/10eb1a4448ae771ad2187a238a8330c819550008/InputFiles/Examples/evac_example1aA.fds)
(commit `10eb1a44`) into the unpacked folder:

```bash
curl -LO https://raw.githubusercontent.com/tkorhon1/FDS-Evac-Guide/10eb1a4448ae771ad2187a238a8330c819550008/InputFiles/Examples/evac_example1aA.fds
```

A [source checkout](install.md#install-from-the-repository) has the same
file in the folder
[assets/fds_evac_guide/Examples](https://github.com/PedestrianDynamics/pyFDS-Evac/tree/main/assets/fds_evac_guide/Examples).

**Check it.**

```bash
pyfds-evac init evac_example1aA.fds --check
```

```text
FDS output check at z = 1.6 m (deck z; FDS moves a slice to the grid, up to half a cell):
  ✗ Extinction  none (requested z 1.6 m); the run has no smoke slowdown and no smoke on signs; fix: add &SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /
  ✗ CO          none (requested z 1.6 m); fix: add &SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
  ✗ CO2         none (requested z 1.6 m); fix: add &SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /
  ✗ O2          none (requested z 1.6 m); fix: add &SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /
  · Other gases none (FED adds the ones present)
  · Temperature vertical only; needed for --enable-heat-fed or --heat-regime layer
  · Intensity   none; needed for --heat-radiant-source integrated-intensity
  ✓ T_END       200 s; init writes max_simulation_time 200 s
  · DT_SLCF     1 s (&DUMP DT_SLCF)
  FED needs CO, CO2 and O2 slices together; without all three the run has no toxic FED
✗ 4 items missing: the deck is not ready for a pyFDS-Evac run; fix it before running FDS.
```

The exit status is 3. The deck has no horizontal slice: a run on its output
would have no smoke and no FED. Each ✗ line gives the `&SLCF` line to add.

**Import it.**

```bash
pyfds-evac init evac_example1aA.fds
```

```text
evac_example1aA.fds → evac_example1aA_scenario/   (FDS+Evac deck)

  Walkable  120.4 m², 1 area    Exits    2 of 2 (LeftExit, RightExit)
  Groups    4 (100 agents)      Floor    z = 0 m

FDS output check at z = 1.6 m (deck z; FDS moves a slice to the grid, up to half a cell):
  ✗ Extinction  none (requested z 1.6 m); the run has no smoke slowdown and no smoke on signs; fix: add &SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /
  …
  The scenario is still written; the ✗ lines say what the run will lack. Details: pyfds-evac init DECK --check

! 9 approximations (details: import_report.json)
  XYZ -> omni-directional sign, c = 3 (FDS+Evac has no viewing-angle factor)                  2 exits
  COUNT_ONLY counter: not an exit (FDS+Evac makes no opening for it)                          1 exit
  …
  delay: detection + reaction = 10 s + gamma(k=6, theta=1.66667), mean 20 s                   4 groups
  e.g. subtracted from &EVAC 'HumanLeftDoorKnown'                                             1 hole
  no known doors -> familiarity 'discovery'                                                   1 group

Next:
  1. Run FDS on a fire-only copy of the deck: remove the evacuation namelists and meshes
       (&EVAC, &PERS, &EXIT, &DOOR, &ENTR, &EVHO, &CORR, &STRS, &EVSS, &EDEV and every &MESH with EVACUATION=.TRUE.), then
       fds <fire-only copy>.fds
  2. pyfds-evac --scenario evac_example1aA_scenario --fds-dir <folder of the fire-only run>
     (clear air: drop --fds-dir)
  3. Refine in JuPedSim Web (https://app.jupedsim.org) or pyfds-evac-tui
```

The exit status is 0, although the slice check failed: the slices never
change the exit status of a plain `init`, only that of `init --check`.

An FDS+Evac deck carries its own exits and agents:

- **Floor and walkable area.** The floor is the evacuation mesh
  `MainEvacGrid`. The walkable area, 120.4 m², is its footprint minus seven
  `&OBST` walls, with two `&HOLE` doorways cut back into them. Without the
  `&HOLE` cuts, RightExit would lie behind a wall.
- **Exits.** `&EXIT` LeftExit and RightExit, each with a sign. RightCounter
  is a `COUNT_ONLY` counter and is not an exit.
- **Agents.** Four `&EVAC` groups, 100 agents. The `&EVHO` area is cut out,
  which splits each group into two pieces. The `&PERS` pre-movement becomes
  10 s plus a gamma-distributed reaction, mean 20 s. The group that knows no
  door gets familiarity `discovery`.

`--agents` has no effect here: the `&EVAC` records set the numbers. Change
them in a copy of the deck or in `config.json`. The mapping of each
namelist is on [Coming from FDS+Evac](coming-from-fds-evac.md).

**Run it in clear air.**

```bash
pyfds-evac --scenario evac_example1aA_scenario --seed 1
```

The run warns that a 0.2 m wall is not wider than the 0.25 m visibility
cell, and ends with:

```text
Simulation finished in 51.85 s (100/100 evacuated).
```

**Before you couple it to a fire**, three things the importer does not do:

1. Make the fire-only copy by hand: remove the namelists listed under
   `Next:` and every `&MESH` with `EVACUATION=.TRUE.`. pyFDS-Evac does not
   read FDS+Evac output.
2. Add the slices of the ✗ lines
   ([What your FDS case must provide](fds-case-requirements.md)).
3. Check `recommendations.coverage` in `import_report.json`. Here 17.04 m²
   of the walkable area and RightExit lie outside the fire mesh, where the
   run has no smoke data.

## 6. Run FDS and couple

`init` prints the FDS command under `Next:`, with `mpiexec -n N` for a deck
of N meshes. For `t_junction.fds`:

```bash
cd assets/t_junction && mpiexec -n 4 fds t_junction.fds && cd ../..
pyfds-evac --scenario assets/t_junction/t_junction_scenario --fds-dir assets/t_junction --seed 1
```

FDS takes about 20 minutes on four processes; A crowd in a fire,
[step 3](first-fds-case.md#3-the-fire), shows what the output contains. With
the 40 agents of step 3 the run ends with:

```text
Simulation finished in 43.47 s (40/40 evacuated).
```

The smoke slows the agents: the same scenario took 34.70 s in clear air.
The run samples the slices at 2.0 m, the nearest to the 1.6 m smoke slice
height that `init` wrote. After the FDS run, `init` finds `t_junction.smv`
next to the deck and adds `--fds-dir` to the run command it prints. [What your FDS case must provide](fds-case-requirements.md)
lists what else can go wrong between the deck and the run.

## 7. Refine the scenario

`init` gives a starting point. Add journeys, checkpoints, signs, groups
with their own speeds, and flow spawning in
[JuPedSim Web](howto-create-scenario.md#draw-it-in-jupedsim-web) or the
[terminal UI](terminal-ui.md). Neither has an entry to start from a deck
yet.

## How the import works

The rules in short; [Usage › pyfds-evac init](usage.md#scenario-from-an-fds-deck--pyfds-evac-init)
has every flag, constant, message and report field.

{{< details title="Deck type and floor" closed="true" >}}
A deck is an FDS+Evac deck when it has a `&MESH` with `EVACUATION=.TRUE.`
or any of `&EVAC`, `&EXIT`, `&PERS`, `&DOOR`, `&ENTR`, `&CORR`, `&EVHO`,
`&EVSS`, `&STRS`, `&EDEV`; otherwise it is a plain deck.

- **FDS+Evac deck.** The floor is a group of main evacuation meshes at one
  height, the lowest by default; `--floor MESH_ID` picks another. Its level
  is the mesh mid-height minus `EVAC_Z_OFFSET` (default 1.0 m). Obstructions
  count within the evacuation mesh's own z range.
- **Plain deck.** The floor is the lowest mesh z (or `--floor-z`).
  Obstructions count between 0.1 and 1.8 m above it (or `--z-band LO HI`).
  Only meshes that reach into this band form the floor; an upper storey is
  left out with a warning.
{{< /details >}}

{{< details title="Walkable area" closed="true" >}}
The union of the floor's mesh footprints, minus the `&OBST` records in the
band, less their `&HOLE` cuts. The edge of the meshes is a wall. `MULT_ID`
is expanded; `&GEOM` is not represented; a deck with `&CATF` is refused.

When the result falls apart into pieces, `init` keeps the pieces that hold a
spawn area; without spawn areas, those that hold an exit; an `--exit` always
keeps its piece. `import_report.json` lists the dropped pieces with area and
reason. `--walkable FILE.wkt` replaces all of this.

On an FDS+Evac deck the outer boundary of an evacuation mesh is solid, and
agents leave only through its `&EXIT`s and `&DOOR`s, as in FDS+Evac
(Korhonen, *FDS+Evac Technical Reference and User's Guide*, Evac
2.6.0-draft, 2021, ch. 8, p. 73). On a plain deck, a mesh that reaches
outdoors through an `OPEN` vent makes that outdoor space walkable.
{{< /details >}}

{{< details title="Exits" closed="true" >}}
- **Plain deck:** every `SURF_ID='OPEN'` vent on the outside of the meshes
  that is vertical and meets the walking band. A vent wider than 5 m, or
  covering 80 % or more of a face, is flagged as a possible open boundary.
- **FDS+Evac deck:** the `&EXIT` and `&DOOR` lines of the floor. A `&DOOR`
  that leads off the floor, to a `&CORR` or `&STRS`, becomes an exit.
  `COUNT_ONLY` exits are counters and are not imported.

Every exit is a strip 0.5 m deep (`--exit-depth`) on the room side of its
line. An exit is never moved to reach the walkable area. One whose strip is
empty, or narrower than 0.1 m, is dropped at error level, and `init` exits
with 3 although the scenario can run.
{{< /details >}}

{{< details title="Agents and settings" closed="true" >}}
- **Plain deck:** each walkable piece with an exit, minus the exit strips,
  is a spawn area. `--agents N` shares N agents between them by area;
  without it, 100 placeholder agents.
- **FDS+Evac deck:** `&EVAC` gives the spawn areas and numbers, `&PERS` the
  speed and pre-movement, `&ENTR` flow spawning. A point or line `&EVAC` is
  grown to a 0.6 m band.
- **Capacity.** A spawn area that asks for more agents than the run can
  place makes the scenario not runnable. The estimate is the run's own
  packing rule, not an occupant density limit.
- **Settings.** `max_simulation_time` is `&TIME T_END`, or 300 s.
  `smoke_slice_height` is the floor plus `HUMAN_SMOKE_HEIGHT` (1.6 m by
  default, FDS+Evac guide §8.7). Keys the deck does not set fall to the
  scenario defaults, listed per group in `import_report.json`.
{{< /details >}}

## Limits

- **One floor per import.** `&CORR`, `&STRS` and `&EVSS` have no
  counterpart, and a `&DOOR` to another floor becomes an exit, so
  "evacuated" on an imported upper floor means "reached the stair door".
  Multi-floor FDS+Evac decks whose lowest floor has no `&EVAC` end with
  "no agents to place"; when agents enter only through stairs, no floor
  has any ([Limitations](limitations.md)).
- **Stairs.** Every `&OBST` in the band blocks, stair treads included;
  there is no speed reduction on inclines.
- **Exits narrower than 0.1 m** are dropped. Exits used only as flow-field
  targets, as in the guide's `CorridorFlowExample`, are not modelled.
- **Exits stay where the deck puts them.** FDS+Evac rounds an exit to its
  evacuation grid; `import_report.json` gives that position
  (`fds_evac_segment`) without applying it.
- **The deck is read by pyFDS-Evac's own parser.** `&GEOM` is not
  represented, `&CATF` is refused, and obstructions with `DEVC_ID` or
  `CTRL_ID` are taken as written, without their time dependence.
- **The check reads the deck.** FDS moves a slice to the nearest grid plane,
  up to half a cell from the deck's z; the check cannot see that.
- **FDS+Evac output is not read.** Run FDS on a fire-only copy, written by
  hand.
- **Touching evacuation meshes are joined.** FDS+Evac keeps their shared
  edge a wall; a warning names them.
- **Fire surfaces** in the walkable area are reported, not cut out. On a
  plain deck, rerun `init` with `--walkable FILE.wkt`, a walkable area
  without the surface, or cut a notch around it from the edge of the spawn
  polygon in `config.json`. Do not add `&EVHO`: it turns the deck into an
  FDS+Evac deck.
- **Exit status 0 means runnable, not checked.** Compare `geometry.wkt` with
  the plan and read `import_report.json` before you use the results.

## What next

{{< cards >}}
  {{< card link="../first-fds-case/" title="A crowd in a fire" subtitle="The T-junction with journeys, signs and flow spawning, coupled to its FDS fire." >}}
  {{< card link="../coming-from-fds-evac/" title="Coming from FDS+Evac" subtitle="Where each FDS+Evac input goes, and what has no equivalent." >}}
  {{< card link="../../using/fds-case-requirements/" title="What your FDS case must provide" subtitle="The slices, their height, and the failures to watch for." >}}
  {{< card link="../../using/howto-create-scenario/" title="Create a scenario" subtitle="Draw or edit a scenario in JuPedSim Web." >}}
{{< /cards >}}

pyFDS-Evac is research software, provided without warranty.
