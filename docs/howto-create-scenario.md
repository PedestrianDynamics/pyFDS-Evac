---
title: "Create a scenario"
weight: 5
aliases: [/docs/howto-create-scenario/]
---

A scenario is two files: `config.json` (exits, spawn areas, agents, journeys,
settings) and `geometry.wkt` (the walkable area). They sit in a folder or a
ZIP, and `pyfds-evac --scenario` reads either. There are three ways to get
them:

| Route | Use it when |
|---|---|
| [Draw it in JuPedSim Web](#draw-it-in-jupedsim-web) | You start from a plan, a CAD drawing or nothing. |
| [Start from an example](#start-from-an-example) | A small change to a working scenario is enough. |
| [Match the FDS deck](#match-the-fds-deck) | You couple the run to FDS output. Do this in addition to one of the first two. |

Whatever the route, [check the scenario](#check-the-scenario) before you
use its results. The keys of `config.json` and their defaults are on
[Scenario JSON](scenario-json.md).

## Draw it in JuPedSim Web

[JuPedSim Web](https://app.jupedsim.org) is the browser app of JuPedSim. You
draw the walkable area, obstacles, exits, spawn areas (called
*distributions*), checkpoints, zones and journeys. It imports geometry from
DXF (CAD) and IFC (BIM) files. Creating and saving scenarios needs a login
with Helmholtz AAI, which accepts external accounts (see the
[FZJ page of the app](https://www.fz-juelich.de/en/ias/ias-7/services/software/jupedsim-app-en)). To run the app on your own machine, see the
Docker set-up in
[jupedsim-web-community](https://github.com/PedestrianDynamics/jupedsim-web-community)
(`docker/README.md`).

{{% steps %}}

### Draw and export

Draw the scenario and export it with **Download as ZIP (JSON + WKT)**. The
ZIP holds `config.json` and `geometry.wkt`. **Download Project ZIP** adds a
`README.md`, `run.py` and `requirements.txt`; pyFDS-Evac reads that ZIP too.

### Load the ZIP

There is no need to unzip it:

```bash
pyfds-evac --scenario scenario.zip --print-summary --export-only
```

In a source checkout, prefix the commands on this page with `uv run`, as in
`uv run pyfds-evac` or `uv run python -m …`.

{{< checkpoint title="The files load" >}}
For a ZIP built by hand in the app's export format, with one spawn area of 50 agents and one exit:

```text
Initialization started.
Scenario: .../scenario.zip
  Model:         CollisionFreeSpeedModel
  Seed:          42
  Max time:      300s
  Exits:         1
  Distributions: 1
  Stages:        0
  Zones:         0
  Journeys:      1
  Agents:        ~50
  Journey elems: 2
  Route:         1 distribution, 0 checkpoint, 1 exit
  Sequence:      jps-distributions_0 -> jps-exits_0
    jps-distributions_0: 50 agents
```

The counts match what you drew. This shows that the files parse; it does not
show that the scenario runs. Run it next, as in
[Check the scenario](#check-the-scenario).
{{< /checkpoint >}}

### Add the pyFDS-Evac keys last

The app writes the movement model, seed, exits, spawn areas, checkpoints,
zones, journeys and exit or checkpoint signs. It does not know pyFDS-Evac's
route choice, exit schedules, familiarity or FDS options. Add those keys by
hand in `config.json`:

| Key | Where | Reference |
|---|---|---|
| `routing` | top level | [Route choice](scenario-json.md#route-choice-routing) |
| `open_from_s`, `closed_after_s`, `capacity_agents_per_s` | `exits.<id>` | [Exits](scenario-json.md#exits-exitsid) |
| `max_distance` | `sign` | [Signs](scenario-json.md#signs-sign) |
| `familiarity`, `entrance` | `distributions.<id>.parameters` | [Spawn areas](scenario-json.md#spawn-areas-distributionsidparameters) |
| `waypoint_routing` | top level | [Journey splits](scenario-json.md#journey-splits-waypoint_routing) |

FDS settings (`--fds-dir`, the slice height and the others) are command-line
options and never go into the JSON; see [Usage](usage.md).

{{% /steps %}}

{{< callout type="warning" >}}
The app's export rebuilds the exits and the top level of `config.json` from
its own state. A re-export drops `routing`, `open_from_s`, `closed_after_s`,
`capacity_agents_per_s` and the sign's `max_distance`. Finish the geometry,
exits, spawn areas and journeys in the app, export, and only then add the
pyFDS-Evac keys. Keep a note or a small script of your hand edits, so you
can apply them again after the next export
([jupedsim-web-community#182](https://github.com/PedestrianDynamics/jupedsim-web-community/issues/182)).
{{< /callout >}}

{{< details title="What the app writes, key by key" closed="true" >}}
- `project_version`.
- `config.simulation_settings`: `simulationParams` (the `model_type`, the
  model constants, `max_simulation_time`, `dt`), `numberOfSimulations` and
  `baseSeed`. pyFDS-Evac reads neither `dt` nor `numberOfSimulations`.
- `config.ui_state` (`useShortestPaths`, `boundaries`): layout data for the
  app. The run does not read it.
- `exits.<id>`: `coordinates`, `enable_throughput_throttling`,
  `max_throughput`, and an optional `sign`.
- `distributions.<id>.parameters`: `number`, `distribution_mode` and
  `percentage`, the `v0*` and `radius*` keys, `use_premovement` and the
  `premovement_*` keys, `use_flow_spawning` with `flow_start_time` and
  `flow_end_time`; and next to the parameters, `journey_weights`.
- `checkpoints.<id>`: `waiting_time` with its distribution and spread, the
  throughput keys, `speed_factor` (always 1) and an optional `sign`.
- `zones.<id>.speed_factor`, and `obstacles` with their heights.
- `journeys: []`, `transitions: []` and `journeys_v2`, which holds each
  journey as a sequence of exits and checkpoints.

**Signs.** The app's sign editor (**Edit Sign**) sets the position, the
bearing (° from north) and the contrast factor *c* (Jin), with the presets
*Reflective (3)* and *Light-emitting (8)*. It writes `sign: {x, y, alpha, c}`
on exits and checkpoints. `alpha` is the bearing the sign faces, clockwise
from north (+y); the sign is readable only from the side it faces. The app
does not write `max_distance`.

**Journeys.** `load_scenario` converts `journeys_v2` into `journeys` and
`transitions` (`_migrate_journeys_v2` in `pyfds_evac/core/scenario.py`). It
does so only when `journeys` is empty, and only for a spawn area with exactly
one `journey_weights` entry. A spawn area split over several journeys is not
converted.
{{< /details >}}

{{< details title="Agents that never move: journeys without transitions" closed="true" >}}
A file whose `journeys` list `stages` but which has no `transitions` runs
with agents that never move. No warning is printed, and `--print-summary`
looks normal
([#504](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/504)).
Older app exports have this shape, for example the `bottleneck-zone` example
and 23 of the 55 scenario ZIPs of jupedsim-web-community, which also carry
`journeys_v2`.

If the file also has `journeys_v2`, set `"journeys": []` and
`"transitions": []` so that `journeys_v2` is converted. Otherwise export the
scenario again from the current app, or add the `transitions` by hand.
{{< /details >}}

### Open a scenario in the app again

`--export-app-bundle DIR` writes the scenario as the app reads it, as
`config.json` and `geometry.wkt`. Add `--export-only` to skip the run:

```bash
pyfds-evac --scenario scenario.zip --export-app-bundle bundle --export-only
```

```text
Initialization started.
```

The folder `bundle` then holds `config.json` and `geometry.wkt`. Zip the two
files and load the ZIP in the app. The GUI writes the same bundle to
`<run folder>/bundle`.

{{< details title="What the bundle holds" closed="true" >}}
`_export_app_bundle` in `pyfds_evac/cli.py` writes the scenario JSON as
loaded and the walkable area as WKT. The command-line options, such as
`--seed`, are not written. Loading adds two things:

- `simulationParams.max_simulation_time` (300 s) when it is missing;
- `journeys` and `transitions` built from `journeys_v2`.

`journeys_v2`, `ui_state` and keys the app does not know are kept. The app
ignores the unknown keys and drops them on its next export, so apply your
hand edits again afterwards.
{{< /details >}}

## Start from an example

Each example page has a Files box with a ZIP of its inputs. Two good
starting points:

- [Quickstart](quickstart.md): `assets/ISO-table21`, one agent in a corridor
  100 m long and 2 m wide. No FDS output and no journeys.
- [A crowd in a fire](first-fds-case.md): `assets/t_junction`, two exits
  with signs, a `routing` block, flow spawning, and the FDS deck.

A ZIP keeps the layout of the repository: the scenario is in
`assets/<name>/config.json` and `assets/<name>/geometry.wkt`. The steps
below use the Quickstart scenario, from a source checkout or from the
unpacked Quickstart ZIP (`cd pyfds-evac-quickstart` first).

{{% steps %}}

### Copy the scenario

```bash
cp -r assets/ISO-table21 my-scenario
```

### Edit what you need

Open `my-scenario/config.json` and `my-scenario/geometry.wkt` in an editor.
The keys most often changed:

- **Walkable area**: `geometry.wkt`, one `POLYGON` in metres, with holes
  for obstacles. ISO-table21 is
  `POLYGON((-50 1, 50 1, 50 -1, -50 -1, -50 1))`.
- **Exits**: `exits.<id>.coordinates`, a closed ring with the first point
  repeated at the end.
- **Spawn areas**: `distributions.<id>.coordinates`.
- **Number of agents**: `distributions.<id>.parameters.number`, with
  `distribution_mode: "by_number"`.
- **Seed**: `config.simulation_settings.baseSeed` (default 42; `--seed`
  overrides it).
- **Duration**:
  `config.simulation_settings.simulationParams.max_simulation_time`
  (default 300 s).

Exits, spawn areas and checkpoints must lie inside the walkable area. With
`--fds-dir`, `max_simulation_time` must not exceed the last FDS slice time by
more than one output interval, unless you pass `--allow-fds-horizon-hold`.

For a first try, change the number of agents from 1 to 3:

```text
"number": 3,
```

### Run it

```bash
pyfds-evac --scenario my-scenario --print-summary --export-only
pyfds-evac --scenario my-scenario
```

{{< checkpoint title="Three agents evacuated" >}}
The summary shows the copied settings and the new count:

```text
  Model:         SocialForceModel
  Seed:          420
  Max time:      300s
  ...
  Agents:        ~3
    jps-distributions_0: 3 agents
```

The run ends with:

```text
Simulation finished in 80.11 s (3/3 evacuated).
```
{{< /checkpoint >}}

{{% /steps %}}

{{< details title="If the run stops with \"requested 20 agents but area can hold at most ~6\"" closed="true" >}}
The spawn area of ISO-table21 is about 0.94 m × 1.81 m. With `"number": 20`
the summary still reads `Agents: ~20`, but the run stops with exit status 1
and a traceback ending in:

```text
ValueError: Distribution 0: requested 20 agents but area can hold at most ~6. Reduce the number of agents or enlarge the distribution area.
```

The estimate is an upper bound. With `"number": 5` the traceback ends in:

```text
jupedsim.distributions.AgentNumberError: Only 4 of 5  could be placed. density: 2.35 p/m²
```

Enlarge the polygon in `distributions.<id>.coordinates`, or lower `number`.
{{< /details >}}

## Check the scenario

Three checks, from weakest to strongest:

1. **The files load.** `pyfds-evac --scenario DIR --print-summary --export-only`
   prints the model, seed, maximum time, the counts and the journeys. It
   returns before the JuPedSim set-up. It does not catch an agent that never
   moves, a spawn area too small for its agents, or a polygon outside the
   walkable area.
2. **The scenario runs.** Run it without `--export-only`. Set a small
   `max_simulation_time` first if the full run is long. A complete run ends
   with `Simulation finished in … s (N/N evacuated).` and exit status 0.
   A run in which not every agent left ends with
   `Simulation incomplete: time limit reached …` and exit status 2
   (`EXIT_INCOMPLETE` in `pyfds_evac/cli.py`). With `max_simulation_time`
   set to 30 in the copy above:

   ```text
   Simulation incomplete: time limit reached after 30.00 s (0/3 evacuated, 3 remaining).
   ```

3. **In the GUI.** Upload the folder's two files or the ZIP in **Core** and
   click **Add to list**; see [Web GUI](web-gui.md#pick-a-scenario).

## Match the FDS deck

When you pass `--fds-dir`, the walkable area and the FDS deck must use the
same coordinate frame: x and y in metres, the same origin, no swapped axes.
The walkable area, exits, spawn areas, checkpoints and signs must lie inside
the FDS meshes and inside the slices pyFDS-Evac samples. Outside the slices,
agents read ambient air and clear sight (*K* = 0), as in
[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source). The
slices a deck must write are on
[What your FDS case must provide](fds-case-requirements.md).

### Check the coverage

Run once with `--fds-dir DIR`. When everything lies inside the slices, no
coverage line is printed. In a source checkout, the ISO-table21 corridor
coupled to its tracked FDS output is such a case:

```bash
pyfds-evac --scenario assets/iso_table21_coupled \
    --fds-dir assets/iso_table21_coupled/fds
```

```text
...
Simulation finished in 85.30 s (1/1 evacuated).
```

When something lies outside, the set-up prints what and how much, and the
run still finishes. This excerpt is from a scenario coupled to the FDS output
of a different geometry: the `bottleneck-zone` example of
jupedsim-web-community (25 m × 10 m, 50 agents) with `transitions` added and
its zone removed, run with `--fds-dir assets/iso_table21_coupled/fds` and
`--allow-fds-horizon-hold`, because its `max_simulation_time` of 300 s
exceeds the 150 s of FDS output:

```text
WARNING:pyfds_evac.core.fds_coverage:FDS coverage: outside the FDS slices (SOOT EXTINCTION COEFFICIENT), agents read ambient air and clear sight: walkable area 185.00 m² (90.2 %); exit jps-exits_0 18.00 m²; distribution jps-distributions_0 34.00 m²; sign jps-exits_0; edge jps-distributions_0 -> jps-exits_0 21.50 m.
...
Simulation finished in 59.21 s (50/50 evacuated).
Outside the FDS domain: 50 agent(s), 2106 sample(s), about 2106.0 agent-seconds of ambient air and clear sight.
```

`--require-fds-coverage` turns the warning into an error (`FdsDomainError`)
and the run stops with exit status 1. Each row of the smoke and FED histories
has an `in_fds_domain` column. The details are on
[FDS slice sampling](fds-sampling.md#outside-the-fds-slices).

### Deck first: draw the walkable area in the deck's frame

Read the extent of the meshes and obstructions from the deck. `XB` on
`&MESH` and `&OBST` lists x0, x1, y0, y1, z0, z1. Draw the walkable area
with these coordinates, by hand or in JuPedSim Web. If the deck was built
from a CAD plan, the app can import the same DXF file; check the coordinates
after the import against the deck.

{{< details title="Generating the walkable area from the deck" closed="true" >}}
`scripts/generate_walkable_from_fds.py` (source checkout only; see
[Usage](usage.md#walkable-area-from-fds-obstructions--generate_walkable_from_fdspy))
subtracts the blocking `&OBST` records from the mesh footprint. It works only
for a building fully enclosed inside a larger mesh, with single-line
namelists and CAD layer names in the `&OBST` comments. It ignores `&HOLE`. On
the 41 decks under `assets/` it wrote a polygon for 10 and stopped on 31,
among them the T-junction of [A crowd in a fire](first-fds-case.md), with:

```text
every free region touches the domain edge, so the interior cannot be told from the outdoors -- check the z band and the layer rules
```

A general tool is tracked in
[#505](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/505), and the
consistency between deck and WKT in
[#26](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/26).
{{< /details >}}

### Walkable area first: generate the deck geometry

`wkt_to_fds` writes the FDS geometry from a walkable area, in the same frame
by construction:

```bash
python -m pyfds_evac.core.wkt_to_fds geometry.wkt --geometry-only --chid bottleneck > bottleneck.fds
```

For a bottleneck 25 m × 10 m:

```text
&HEAD CHID='bottleneck', TITLE='Generated from JuPedSim walkable WKT' /
&MESH IJK=102,42,12, XB=-0.250,25.250,-0.250,10.250,0.0,3.0 /
&TIME T_END=120.0 /
&MISC TMPA=20.0 /

! --- walls: complement of the walkable area (6 OBSTs) ---
&OBST XB=-0.250,25.250,-0.250,0.000,0.0,3.0 /
...
&OBST XB=25.000,25.250,0.000,10.000,0.0,3.0 /

&TAIL /
```

The walls are the complement of the walkable area within the mesh, closed
all round. The deck has no `&VENT SURF_ID='OPEN'` at the exits; add openings
where your fire scenario needs them.

{{< details title="Options and the fire template" closed="true" >}}
The cell size is set from the smallest gap between vertex coordinates,
which in a rectilinear plan is the thinnest wall (default 0.25 m, at least
0.1 m); `--dx` sets it. `--z-max` sets the height (3 m), `--meshes NX NY`
splits the domain into NX × NY meshes, and `--t-end` sets the end time
(120 s).

Without `--geometry-only`, the deck also gets a placeholder burner
(`--hrrpua`, default 800 kW/m², on a 0.5 m square at `--fire-xy`) and the
extinction and CO, CO2, O2 slices at 1.6 m. This fire is a template. Replace
it with your design fire.

Sources: the module docstring and `wkt_to_fds` in
`pyfds_evac/core/wkt_to_fds.py`; tests in `tests/test_wkt_to_fds.py`.
{{< /details >}}

## Next steps

- [Scenario JSON](scenario-json.md): every key that changes a result.
- [Usage](usage.md): the command-line options.
- [What your FDS case must provide](fds-case-requirements.md): the slices and
  yields a coupled run reads.
- [Troubleshooting](troubleshooting.md): error messages and their fixes.
