---
title: "Coming from FDS+Evac"
weight: 5
aliases: [/docs/coming-from-fds-evac/]
---

This page is for engineers who have an [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) input file and want to run the
same case in pyFDS-Evac. It maps each FDS+Evac input to its place here, and it
lists what has no equivalent. FDS+Evac was removed from FDS in December 2021
(FDS commit `6a1d48aa5e`). The last FDS release that contains it is FDS 6.7.7
(November 2021, Evac 2.6.1). The link above and every `evac.f90:NNNN`
reference in these docs point to FDS `6.7.6-404-gc9da70d7a` (August 2021,
Evac 2.6.0-draft), the version the 2021 guide describes. Read
[Limitations](limitations.md) before you rely on a result.

pyFDS-Evac is research software, provided without warranty. It is not intended
for regulatory or design use.

## What carries over and what changes

**The fire part of your deck carries over.** Remove the evacuation namelists
and the evacuation meshes, keep the fire meshes, obstructions, `&REAC` and
`&SURF` lines, and add the slices pyFDS-Evac reads
([What your FDS case must provide](fds-case-requirements.md)). Then run FDS
as usual.

**The occupants move in a different program.** FDS+Evac (Korhonen 2021)
computes movement inside the FDS executable, with its own social-force model
on 2-D evacuation meshes. In pyFDS-Evac, [JuPedSim](https://www.jupedsim.org)
moves the agents on a continuous walkable polygon. The operational model is
chosen in the scenario JSON (`model_type`, default `CollisionFreeSpeedModel`).

**Smoke is read from a finished FDS run.** pyFDS-Evac never runs FDS. It reads
the slice files of a finished FDS run and samples them at the agents'
positions. The coupling is one-way: the fire acts on the occupants, and
nothing the occupants do (opening a door, for example) acts on the fire.

**Each agent carries its own dose.** pyFDS-Evac sums the FED of every agent
at the agent's position, every `--smoke-update-interval` (1 s by default),
from the slices nearest `--smoke-slice-height` (1.6 m by default). New
Zealand's Verification Method C/VM2 asks for this quantity: a CO dose and a
thermal dose, summed in steps of at most 5 s at 2.0 m above the floor, along
the escape route of the last occupant to leave the room of fire origin
(MBIE 2012, *Commentary for Verification Method C/VM2*, pp. 47 and 49). The
equations differ: the gas FED follows FDS+Evac, not the ISO 13571 form that
C/VM2 names; the heat dose needs `--enable-heat-fed`, is convective only by
default, and gains a radiant term with `--heat-fed-method total-flux` (an
SFPE form, not ISO 13571's). See
[ASET and RSET](/fundamentals/aset-rset.md) for the C/VM2 criteria,
[Selecting a slice height](/docs/fds-sampling.md#selecting-a-slice-height)
for running at 2.0 m, and [Fractional effective dose](/models/fed.md) for the
equations.

`pyfds-evac init deck.fds` does much of this for you. It
keeps the evacuation namelists of one floor as exits and spawn areas, and
writes a report of everything it approximated or dropped
([Usage](usage.md#scenario-from-an-fds-deck--pyfds-evac-init)).
[Start from your own FDS case](start-from-fds-deck.md#5-an-fdsevac-deck)
walks through it on a guide deck.

In FDS+Evac the outer boundary of an evacuation mesh is solid by default
(Korhonen, *FDS+Evac Technical Reference and User's Guide*, Evac 2.6.0-draft, 2021,
ch. 8, p. 73). Agents leave a main evacuation mesh only through its EXITs and
DOORs. FDS+Evac places an outflow vent at each of them automatically, and
both the agents' wall forces and the guiding flow field treat that vent as
the opening (FDS `read.f90` and `evac.f90`, firemodels/fds commit
c9da70d7a0). pyFDS-Evac therefore treats the boundary of each main evacuation
mesh as a wall. `&ENTR` records and the fire meshes' `SURF_ID='OPEN'` vents do
not open it, and a `COUNT_ONLY` exit is a counter, not an exit: it is listed
in `import_report.json` with no counterpart.

A case therefore has three parts: the FDS output directory, a scenario JSON,
and a walkable geometry as WKT (well-known text, a plain-text polygon format). `uv run python run.py --scenario <json|dir|zip> --fds-dir
<fds output>` combines them.

## Defaults follow FDS+Evac

pyFDS-Evac is an enhancement of FDS+Evac. Where a mechanism has
a direct FDS+Evac counterpart, the default is the FDS+Evac form, so that a
case converted from FDS+Evac behaves as its author expects. Newer or
alternative forms stay available as options. Earlier pyFDS-Evac versions
used other defaults for eight mechanisms
([#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)):

| Mechanism | Default now (= FDS+Evac) | Previous pyFDS-Evac default | To get the previous behaviour |
|---|---|---|---|
| Sampling height | 1.6 m, `HUMAN_SMOKE_HEIGHT` (`evac.f90:1138`; Guide §8.7) | 2.0 m | `--smoke-slice-height 2.0`; `opts.smoke_slice_height = 2.0`, or `slice_height_m=2.0` in `SmokeSpeedConfig` and `DefaultFedConfig` |
| Irritant (FIC) slowdown | None; `evac.f90` imports only `FED` (`evac.f90:65`) | On whenever the gas FED is computed | `--enable-fic-speed`; `opts.enable_fic_speed = True`, or `TenabilityConfig(enable_fic_speed=True)` |
| HCN term of the FED | *C*HCN − (*C*NO + *C*NO2), offset 1/220 (function `FED` in FDS `func.f90`) | *C*HCN − *C*NO2, offset 0.0045 (Guide Eq. 14–15) | Not available; see the note below |
| O2 term of the FED | Applied only below 20 % O2 (function `FED` in FDS `func.f90`) | Applied below 19.5 % | `--o2-threshold-percent 19.5`; `opts.o2_threshold_percent = 19.5`, or `DefaultFedConfig(o2_threshold_percent=19.5)` |
| Pre-movement, when a spawn area sets none | Constant 10 s, `PRE_MEAN` (`evac.f90:1672`), with a warning in the log | 0 s | `"use_premovement": false` in the spawn area's `parameters` |
| Unimpeded walking speed `v0`, when a spawn area sets none | 1.25 m/s, `VEL_MEAN` (`evac.f90:1670`) | 1.2 m/s | `"v0": 1.2` in the spawn area's `parameters` |
| Convective heat dose | None (Guide §1.2) | On whenever the output has a `TEMPERATURE` slice | `--enable-heat-fed`; `opts.enable_heat_fed = True` |
| Gas incapacitation threshold | Every agent stops at FED = 1 (Guide §3.4) | Per-agent log-normal draw, median `--fed-threshold`, σ = 0.94 | `--incapacitation-mode probabilistic`; `opts.incapacitation_mode = "probabilistic"`, or `TenabilityConfig(incapacitation_mode="probabilistic")` ([#235](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/235)) |

The CLI flags that change a result are also fields of the [web GUI](web-gui.md) and the [terminal UI](terminal-ui.md), and the `opts` attributes are
what `build_run_kwargs` reads, so a script that builds its own options sets
them the same way. The [changelog](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/CHANGELOG.md)
lists the same changes.

**The HCN term follows the FED as FDS and FDS+Evac compute it.** FDS+Evac
calls the `FED` function of FDS, which has subtracted NO + NO2 from HCN,
with the offset 0.00454545 (about 1/220), since FDS commit 694e033 (2011);
earlier versions had no HCN term. The FDS+Evac Guide's Eq. 15 subtracts NO2
alone, which no FDS version computed, so pyFDS-Evac follows the code, not the
guide's text, and does not offer the guide's form as an option. The FDS
verification case `FED_FIC` separates the two forms and is part of the test
suite ([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)).

**What deliberately still differs:**

- Route choice, cognitive maps and sign visibility are enhancements with no
  one-to-one FDS+Evac counterpart
  ([#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)); see
  [Smoke-aware routing](routing.md).
- An agent that does not know an exit learns it from the exit's sign;
  FDS+Evac uses sight of the door. FDS+Evac counts a door as visible at any distance if nothing blocks the line of
  sight. pyFDS-Evac reads a sign only within its reading distance, 30 m by
  default even in clear air, and less off-axis or in smoke. See
  [Seeing a door vs reading a sign](#seeing-a-door-vs-reading-a-sign).
- Known issues: an agent incapacitated during its pre-movement time is
  released when that time ends
  ([#145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)).

## Where each FDS+Evac input goes

Section numbers refer to the FDS+Evac Technical Reference and User's Guide
(Korhonen 2021). "JSON" means the scenario JSON. Its stage layout
(`distributions`, `exits`, `checkpoints`, `journeys`) is the one the JuPedSim
web editor writes, and `load_scenario` converts the editor's `journeys_v2`
routes on load. The pyFDS-Evac web GUI (graphical user interface, `pyfds-evac-gui`,
or `app.py` in a source checkout) runs uploaded scenarios. It does not edit geometry or stages.

| FDS+Evac input | What it did | In pyFDS-Evac |
|---|---|---|
| Evacuation meshes (`&MESH EVACUATION=.TRUE.`, §8.1) | 2-D grids for movement, separate from the fire meshes | Replaced by one walkable polygon (WKT). `pyfds-evac init` derives it from the union of the floor's main evacuation meshes minus their `&OBST` records, less the `&HOLE` cuts, and treats the boundary of each main evacuation mesh as a wall (see below and [Usage](usage.md#scenario-from-an-fds-deck--pyfds-evac-init)). Two touching evacuation meshes of one floor are joined, with a warning in `import_report.json`. |
| `EVAC_Z_OFFSET` (§8.1) | Distance from the mid height of an evacuation mesh down to its floor, which is the reference level for `HUMAN_SMOKE_HEIGHT` | No equivalent: pyFDS-Evac has no evacuation meshes. |
| `HUMAN_SMOKE_HEIGHT` (§8.7) | Height above the floor at which smoke and FED are read, default 1.6 m (Guide §8.7 p. 81; VTT W119 p. 61) | `--smoke-slice-height` [m], default 1.6 as in FDS+Evac (2.0 before; pass `--smoke-slice-height 2.0` for it), an absolute z in the FDS domain rather than a height above the floor ([#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)). It selects the extinction, gas and temperature slices closest to it, so the deck must contain an `&SLCF PBZ=` at that height. |
| `&EVAC` (§8.8) | Places a group of agents in a rectangle | A `distributions` entry in the JSON: a polygon plus `parameters` (`number`, `v0`, `radius`, pre-movement, familiarity). `pyfds-evac init` grows a point or line `&EVAC` to a 0.6 m band across its zero-width axis (a 0.6 m square for a point), clipped to the walkable area, places the agents at random in it, and records this per group in `import_report.json`. |
| `&PERS` (§8.7) | Agent type: body size, speed, pre-movement, force constants | Per distribution in the JSON: `v0` [m/s], `radius` [m] and the pre-movement keys below. There are no named agent types and no three-circle body; an agent is a circle. |
| `&EVHO` (§8.9) | Area where no agents are placed | No JSON key. Draw the distribution polygon so that it excludes the area; `pyfds-evac init` does this by splitting the spawn area into pieces around the hole, sharing the agents by area. In a plain FDS deck, an `&EVHO` makes `init` read the deck as an FDS+Evac deck, which loses its exits ([#688](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/688)). |
| `&EXIT` (§8.10) | Line that removes agents | An `exits` entry in the JSON (a polygon). Optional `enable_throughput_throttling` and `max_throughput` cap the flow, and an optional `sign` feeds visibility. `pyfds-evac init` keeps the deck's line where it is: FDS+Evac moves it to the nearest evacuation grid lines, and `import_report.json` gives that position (`fds_evac_segment`) without applying it. An exit is not moved to reach the walkable area; one whose room-side strip is empty, or narrower than 0.1 m, is dropped with the reason. An exit used only as a flow-field target, such as the 0.1 m slots of `CorridorFlowExample`, is not imported. |
| `&DOOR` (§8.12) | Moves agents to another part of the calculation | No door object. A doorway is a gap in the walkable polygon; an intermediate target is a `checkpoints` entry in a journey. `pyfds-evac init` imports a `&DOOR` that leads off the floor, to a `&CORR` or `&STRS`, as an exit. |
| `&ENTR` (§8.11) | Adds agents at a constant rate | Flow spawning on a distribution: `use_flow_spawning`, `flow_start_time`, `flow_end_time` [s]. |
| `&CORR` (§8.13) | One-way corridor or stair between floors | Not supported. pyFDS-Evac is single-floor. |
| `&STRS` (§8.15) | Whole staircase with its own mesh | Not supported. |
| `&EVSS` (§8.14) | Incline with speed factors `FAC_V0_UP/DOWN/HORI` | Not supported as an incline. A `zones` or `checkpoints` entry with a `speed_factor` (0 to 3) scales the speed of agents inside a polygon, with no direction dependence. |
| `DET_*` and `PRE_*` (§8.7, §8.8) | Detection time plus reaction time, each from a distribution. The default reaction time is a constant `PRE_MEAN` = 10 s (`evac.f90:1672`; `PRE_EVAC_DIST` = 0 is a constant, Guide §8.7), added to the detection time, whose default `DET_MEAN` is `T_BEGIN` (`:1673`); a lone agent starts moving at `TDET + TPRE` (`:9209`), a group member at `TDET` (`:9211`) | One pre-movement delay per agent: `use_premovement`, `premovement_distribution`, `premovement_param_a`, `premovement_param_b`, `premovement_seed`. There is no separate detection phase. See the table below. |
| `TDET_SMOKE_DENS` (§8.7) | Smoke at the agent's position triggers detection | Not supported. The pre-movement delay does not depend on smoke. |
| `VELOCITY_DIST` and speed ranges (§8.7) | Unimpeded walking speed distribution; default `VEL_MEAN` = 1.25 m/s (`evac.f90:1670`) | `v0` [m/s], default 1.25 as in FDS+Evac (1.2 before; set `v0` per spawn area for it; [#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)), with `v0_distribution` = `"constant"` or `"gaussian"` and `v0_std`. `desired_speed`, `desired_speed_distribution` and `desired_speed_std` are aliases of these keys, accepted in the scenario JSON and by `Scenario.set_agent_params()` in Python; in the JSON, an alias and its `v0*` key with different values are an error. Gaussian draws are clipped to 0.1–5.0 m/s. There is no uniform speed distribution. |
| Smoke-speed reduction (Eq. 11), `SMOKE_MIN_SPEED_FACTOR` and `SMOKE_MIN_SPEED` | Linear speed reduction with extinction, floored at `SMOKE_MIN_SPEED_FACTOR` × *v*0 (default 0.1). The guide calls `SMOKE_MIN_SPEED` a factor too, but the code divides it by *v*0 (`evac.f90:8516`), so it is a speed in m/s | The default is the same law, Frantzich–Nilsson (the `lund` option; the linear FDS+Evac law). Its coefficients (`alpha`, `beta`, `min_speed_factor`) are library-level; see [What needs Python](#what-needs-python). |
| FED, fractional effective dose (§3.4) | Purser FED from CO, CO2, O2 (and optional gases), incapacitation at FED ≥ 1. The O2 term is applied only below 20 % O2 (function `FED` in FDS 6.7.6 `func.f90`, which FDS+Evac calls). The HCN term in the code (the same `FED` function) is exp(*C*CN/43)/220 − 0.00454545 (about 1/220) with *C*CN = *C*HCN − (*C*NO + *C*NO2); Guide Eq. 14–15 write the offset as 0.0045 and *C*CN = *C*HCN − *C*NO2. The code form has been in FDS since firemodels/fds 694e033 (2011); earlier versions had no HCN term. FDS's `FED_FIC` verification case reproduces only with it (0.97402 against the expected 0.97403 at 100 s; 6.17 with NO2 alone). The FDS User Guide was corrected to NO + NO2 in 2016 (903df07); the FDS+Evac Guide and the FDS Verification Guide were not. An agent that reaches FED ≥ 1 stays down for the rest of the run | Computed when the output has CO, CO2 and O2 slices; HCN, NOx and irritant slices are added when present. The O2 term is applied below 20 %, as in FDS+Evac; `--o2-threshold-percent 19.5` (`opts.o2_threshold_percent`) gives the previous 19.5 %. The HCN term is the one in the code FDS+Evac ran (*C*HCN − (*C*NO + *C*NO2), offset 1/220), and `FED_FIC` is reproduced in the test suite ([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)). Earlier pyFDS-Evac versions followed Guide Eq. 14–15 (*C*HCN − *C*NO2, offset 0.0045); the two differ materially only when NO is present: at 100 ppm HCN, 50 ppm NO and 10 ppm NO2 the CN rate is 0.007 /min now against 0.032 /min before; with no NO the difference is the offset alone, 4.5 × 10⁻⁵ /min. By default every agent stops at FED = 1, as in FDS+Evac. With `--incapacitation-mode probabilistic` each agent draws its own threshold instead (log-normal, median 1; spread on the [FED model](/models/fed.md#tenability-irritant-slowdown-and-incapacitation) page), so about half stop below FED = 1. The heat dose, which FDS+Evac does not have, is deterministic by default and uses the same threshold, as ISO 13571:2012 asks (§5.4). Thresholds are set with `--fed-threshold`; `--heat-fed-threshold` sets a separate heat threshold, a departure from ISO. An agent incapacitated while it is still waiting is released when its pre-movement time ends, a known bug ([#145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)). |
| Convective heat | None: gas temperature and radiation do not act on agents (Guide §1.2) | Off by default, as in FDS+Evac. With `--enable-heat-fed` (`opts.enable_heat_fed`), a separate heat dose is computed from the `TEMPERATURE` slice, by default with ISO 13571:2012 Eq. (9) for fully clothed subjects, and kept apart from the gas FED; it incapacitates at the same threshold as the gas dose unless `--heat-fed-threshold` sets another; before, this happened automatically whenever the output had such a slice. `--disable-tenability` turns off both stops ([#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)). |
| Irritant slowdown (FIC) | None: no FIC acts on the agents, since `evac.f90` imports only `FED` from FDS (`evac.f90:65`). Irritants enter only the FED sum. FDS can write FIC as an output quantity, and the guide tabulates *F*FIC (Table 2), but neither feeds the agents' speed | Off by default, as in FDS+Evac. `--enable-fic-speed` (`opts.enable_fic_speed`) turns on speed × max(0.3, 1 − 0.7 · FIC) whenever the gas FED is computed; before, it was on by default. The rule is a pyFDS-Evac assumption with no known source ([#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147), [#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)). |
| FED activity level | Input accepts rest, light work or heavy work, but the dose is always computed for light work (`evac.f90:16086–16088`) | Same as FDS+Evac 6.7.6: light work only (FDS+Evac reads the input but does not use it). See [issue #135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135). |
| `KNOWN_DOOR_NAMES`, `KNOWN_DOOR_PROBS` (§8.8) | Which exits an agent knows, with a probability per exit. An exit not listed is known only if its `&EXIT` or `&DOOR` line sets `KNOWN_DOOR`, which defaults to .FALSE. (`evac.f90:2291`, `:2733`), so by default agents rely on the exits they can see | `familiarity` on a distribution: `"full"`, `"discovery"`, or one probability in [0, 1] applied to every exit. The default is `"full"`: every agent knows every exit. The FDS+Evac default is closer to `"discovery"`. `entrance` names one exit, reachable from the spawn area, that the agents know from the start. A probability per exit is not supported; see [issue #136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136). |
| Door visibility (`Is_Visible_Door`) | A door is visible when the line of sight from the agent to the door centre is not blocked (or, for an `XB` door, to its centre from the correct side). There is no range limit, no contrast and no angle factor | A sign is legible when \(A \cdot U \cdot \min(C/\bar K, V_{\max}) \ge L\) (see [Wayfinding](/models/wayfinding.md#sign-visibility)). \(V_{\max}\) = 30 m by default (`--max-sign-distance`, or `"max_distance"` per sign), so a door farther than 30 m is not found by sight even in clear air. See [below](#seeing-a-door-vs-reading-a-sign). |
| Door selection with smoke (`FED_DOOR_CRIT`) | Ranks doors as smoke-free by FED or visibility. For a door in view, the smoke is the mean over the cells of the straight line to the door; for a door not in view, `See_door` stops at the first wall and uses only the smoke in the agent's own cell, with the L1 distance (`evac.f90:15762–15765`, `:15803–15806`; Guide §3.6). Smoke beyond a wall is never counted, and smoke along the way to a door out of view is ignored | Route choice is a different model, configured in the JSON `routing` block and switched on by default (`--enable-rerouting`). See [Smoke-aware routing](routing.md). |
| Queueing in door selection (`FAC_DOOR_QUEUE`) | On by default (1.3 persons/m/s, `evac.f90:1568`). Within `Change_Target_Door` the estimated queueing time ranks only the first preference tier, the doors that are both known and visible (`:16592`); the parameter also switches on the Nash iteration of the initial exit choice (`:7071`) and enters the queue estimates in `EVACUATE_HUMANS` (`:9364`) | Off by default: `w_queue` = 0 in the JSON `routing` block. When set, it counts all agents targeting an exit, not a local queue. |
| `TAU` (`TAU_MEAN` etc., §8.7) | Relaxation time of the social-force model | No equivalent. Movement parameters belong to the JuPedSim model named in `model_type`. |

### Seeing a door vs reading a sign

![Two plan views of the same hall with one exit and an obstacle. Left, FDS+Evac: every cell with an unblocked line of sight to the door sees it, at any distance. Right, pyFDS-Evac: only cells inside the 30 m reading circle and outside the obstacle's shadow read the sign](/images/wayfinding/sign_range_fds_evac.png)

*A 60 × 30 m hall with one exit and a 3 × 8 m obstacle; the door centre and the sign are the same point. Left: a re-implementation of FDS+Evac's door test, `See_door` (`evac.f90:15682–15813`), which marches the cells of the see-or-not mesh along the segment to the door centre and fails at the first solid wall face, at any distance; smoke along the way is averaged, not blocking. That mesh is a slab at `HUMAN_SMOKE_HEIGHT` ± `EVAC_DELTA_SEE` (0.29 m, `:1137`; Guide §1.3.5), so the obstacle here is taken to reach eye height: a low obstruction, or one marked `HIDDEN`, does not block the sight line in FDS+Evac. Right: the cells from which pyFDS-Evac's visibility model reads the sign, for an omni-directional sign (C = 3) in clear air with the default 30 m reading distance (dashed circle, drawn faintly on the left for reference). Both need a clear line of sight, so the obstacle casts the same shadow; the only difference is range. Agent 1 (12 m, in view) sees the exit in both; agent 2 (45 m, in view) sees the door in FDS+Evac but cannot read the sign; agent 3 (23 m, behind the obstacle) sees neither. A directional sign shrinks the right-hand region further by the angle factor, and smoke shrinks it again.*

Consequences for a deck carried over from FDS+Evac:

- In a space wider than 30 m, an agent that does not know an exit (a
  `discovery` agent, or one whose `familiarity` draw missed it) learns it only
  once it comes within reading distance of its sign. Egress times of such
  agents are longer than FDS+Evac's in large, open spaces.
- Off-axis, the reading distance shrinks with the angle factor \(A\): in
  clear air a sign is legible up to \(A \cdot V_{\max}\). An omni-directional
  sign (no `alpha`) has \(A = 1\).
- Smoke shortens it further, to \(A \cdot C/\bar K\) once
  \(C/\bar K < V_{\max}\). FDS+Evac's door visibility ignores smoke; smoke
  acts only in its door ranking.
- To model a sign that is read from farther away (a larger or illuminated
  sign), set its `"max_distance"`. To approximate FDS+Evac's unlimited range,
  raise `--max-sign-distance` above the largest distance in the deck.
- Agents with `familiarity` `"full"`, the default, know every exit and are
  unaffected.

### Pre-movement parameters

The two parameters mean different things for each distribution, so FDS+Evac
values cannot be copied across unchanged. The delay is in seconds.

| `premovement_distribution` | `premovement_param_a` | `premovement_param_b` | Preset (*a*, *b*) |
|---|---|---|---|
| `gamma` (default) | shape | scale [s] | 1.291, 103.901 |
| `lognormal` | mean of ln(*t*) | standard deviation of ln(*t*) | 4.586, 0.967 |
| `weibull` | scale [s] | shape | 139.285, 1.195 |
| `uniform` | lower bound [s] | upper bound [s] | 0.0, 60.0 |
| `constant` | delay [s] | unused | 10.0, - |

The gamma, log-normal and Weibull presets are the fits for office buildings
(Business Cluster 1: 11 evacuations, 10 of them drills, 4–14 floors, R²
0.55–0.57) in Lovreglio et al. (2019), Table 3, with the log-normal *a* taken
from the 2019 corrigendum
([doi:10.1016/j.firesaf.2018.12.009](https://doi.org/10.1016/j.firesaf.2018.12.009);
[doi:10.1016/j.firesaf.2019.102829](https://doi.org/10.1016/j.firesaf.2019.102829)).
The uniform preset is RiMEA's "speedy evacuation" scenario, a range set for
sensitivity tests. For other occupancies, set both
parameters from the matching table of that paper.

![Four panels of pre-movement time from 0 to 600 s. Gamma, log-normal and Weibull each rise to a peak near 30 to 40 s and fall off in a long right tail, with medians near 100 s and 95th percentiles of 368, 481 and 349 s. The uniform preset is a flat block from 0 to 60 s, with median 30 s and 95th percentile 57 s](/images/getting-started/premovement_presets.png)

*The first four presets of the table above. Curves: the probability density
with the preset (*a*, *b*). Grey bars: 10,000 draws made by pyFDS-Evac with
the same preset, which follow the curves. Solid line: median; dashed line:
95th percentile. The log-normal preset has the longest tail: 3.1 % of it
lies beyond 600 s. Script:
`scripts/figures/coming_from_premovement_presets.py`.*

The presets are used when `use_premovement` is `true` and `premovement_param_a`
or `premovement_param_b` is missing; both parameters must be given for either
to take effect (`constant` needs only `premovement_param_a`). A spawn area that
sets none of these keys gets the FDS+Evac default, a constant 10 s after
`T_BEGIN` (`PRE_MEAN`;
[#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)), and the
run logs a warning, since the FDS+Evac guide advises against relying on
defaults. With `use_premovement` false, agents start moving at *t* = 0, as
every spawn area without pre-movement keys did before. When
`premovement_seed` is null, the draws are seeded from the run seed, so they
repeat under a fixed `--seed`.

While an agent waits, its walking speed is not reduced by the smoke around
it. It starts at its full clear-air speed when it is released. Its toxic dose
does accumulate while it waits.

## What is lost

Some FDS+Evac features have no counterpart. The social-force movement model
with its three-circle body, and its dedicated counterflow algorithm, are
replaced by the JuPedSim model you choose. Floors, stairs, `&EVHO` holes,
smoke-triggered detection and per-exit known-door probabilities are not
supported. Each is described on the [Limitations](limitations.md) page. The
FED activity level is the same as in FDS+Evac 6.7.6: light work only
(FDS+Evac reads the input but does not use it).

## What needs Python

Some parameters cannot be set from the CLI or the scenario JSON. The
smoke-speed parameters are the main case. `speed_law` (`"lund"` or
`"fridolf"`), `alpha`, `beta`, `min_speed_factor`, `visibility_factor_c` and
the `fridolf_*` constants are fields of `SmokeSpeedConfig`, and `run.py`, the web GUI and the terminal UI build that
object with its defaults. A run started from any of them uses the
Frantzich–Nilsson law with the defaults listed on the [smoke-speed model](/models/smoke-speed.md#parameters) page.

To change them, build a `SmokeSpeedModel` yourself and pass it to
`run_scenario()` from Python.

The JSON `routing` block accepts keys with the same names (`alpha`, `beta`,
`min_speed_factor`). They set the speed factor used to estimate travel time
when a route is priced. Changing them changes what routes cost, not how fast
agents walk.

## Before you convert

- [ ] Read [What your FDS case must provide](fds-case-requirements.md) and add
      the slices it lists: extinction coefficient, CO, CO2, O2 and
      `TEMPERATURE`, with the `&REAC` yields that produce the gases.
- [ ] Put the slices at the height you will pass to `--smoke-slice-height`.
- [ ] Check that the building fits on one floor. Stairs and several floors
      are not supported. `pyfds-evac init` imports one floor, and every
      `&OBST` in its walking band blocks, stair treads included.
- [ ] Check the walkable polygon it writes (`geometry.wkt`) against the
      plan; `import_report.json` lists the parts it dropped.
- [ ] Translate pre-movement into one delay per agent (table above). Detection
      and reaction are no longer separate.
- [ ] Decide what each group knows (`familiarity`, `entrance`).
- [ ] Run FDS, then `uv run python run.py --scenario <json> --fds-dir <dir> --inspect-fds`
      to list the quantities pyFDS-Evac finds.
- [ ] Read the warnings of the first run. A missing gas slice switches FED off
      and the run still finishes, with no FED in the result: `metrics` has no
      `fed_max` ([Outputs](outputs.md#reading-the-results)).
- [ ] Read [Limitations](limitations.md) and the
      [verification status](https://pedestriandynamics.org/pyFDS-Evac/verification/).

## Words that changed meaning

> **Terminology.**
>
> - **`tau`** is an *optical depth* here: the mean extinction coefficient
>   along a route times its length, *τ* = *K*ave · *L* (dimensionless).
>   It is not the relaxation time `TAU` of FDS+Evac. The routing key
>   `tau_max` is an optical depth (default on the
>   [routing model](/models/routing.md#parameters) page).
> - **Stage** is a JuPedSim target: a distribution, a checkpoint or an exit.
>   Journeys are sequences of stages.
> - **Gate** has two meanings, and only two. The route-cost gate
>   (`routing.cost_model = "gate"`, the default) refuses routes whose
>   optical depth is too high. Sight gating decides whether an agent can
>   read a sign, and so which exits enter its cognitive map. The dose is not
>   a gate: when it reaches the agent's threshold, the agent stops.
> - **FIC**, Purser's fractional irritant concentration, which slows agents
>   when `--enable-fic-speed` is given,
>   is related to, but not the same as, the FEC (fractional effective
>   concentration) of ISO 13571, which uses different denominators.
> - **Cognitive map** is the graph of stages an agent knows. It is not meant
>   in the psychological sense.

## References

Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0-draft). VTT Technical
Research Centre of Finland.
