---
title: "Coming from FDS+Evac"
weight: 3
---

This page is for engineers who have an FDS+Evac input file and want to run the
same case in pyFDS-Evac. It maps each FDS+Evac input to its place here, and it
lists what has no equivalent. Read [Limitations](limitations.md) before you
rely on a result.

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

**Smoke is read, not computed alongside.** pyFDS-Evac never runs FDS. It reads
the slice files of a finished FDS run and samples them at the agents'
positions. The coupling is one-way: the fire acts on the occupants, and
nothing the occupants do (opening a door, for example) acts on the fire.

A case therefore has three parts: the FDS output directory, a scenario JSON,
and a walkable geometry as WKT (well-known text, a plain-text polygon format). `uv run python run.py --scenario <json|dir|zip> --fds-dir
<fds output>` combines them.

## Where each FDS+Evac input goes

Section numbers refer to the FDS+Evac Technical Reference and User's Guide
(Korhonen 2021). "JSON" means the scenario JSON. Its stage layout
(`distributions`, `exits`, `checkpoints`, `journeys`) is the one the JuPedSim
web editor writes, and `load_scenario` converts the editor's `journeys_v2`
routes on load. The pyFDS-Evac web GUI (graphical user interface, `app.py`)
runs uploaded scenarios. It does not edit geometry or stages.

| FDS+Evac input | What it did | In pyFDS-Evac |
|---|---|---|
| Evacuation meshes (`&MESH EVACUATION=.TRUE.`, §8.1) | 2-D grids for movement, separate from the fire meshes | Replaced by one walkable polygon (WKT). `scripts/generate_walkable_from_fds.py` derives it from the `&OBST` lines of a deck (see [Usage](usage.md)). |
| `EVAC_Z_OFFSET` (§8.1) | Height at which smoke and FED are read | `--smoke-slice-height` [m], default 2.0. It selects among the slices in the output, so the deck must contain an `&SLCF PBZ=` at that height. |
| `&EVAC` (§8.8) | Places a group of agents in a rectangle | A `distributions` entry in the JSON: a polygon plus `parameters` (`number`, `v0`, `radius`, pre-movement, familiarity). |
| `&PERS` (§8.7) | Agent type: body size, speed, pre-movement, force constants | Per distribution in the JSON: `v0` [m/s], `radius` [m] and the pre-movement keys below. There are no named agent types and no three-circle body; an agent is a circle. |
| `&EVHO` (§8.9) | Area where no agents are placed | Not supported. Draw the distribution polygon so that it excludes the area. |
| `&EXIT` (§8.10) | Line that removes agents | An `exits` entry in the JSON (a polygon). Optional `enable_throughput_throttling` and `max_throughput` cap the flow, and an optional `sign` feeds visibility. |
| `&DOOR` (§8.12) | Moves agents to another part of the calculation | No door object. A doorway is a gap in the walkable polygon; an intermediate target is a `checkpoints` entry in a journey. |
| `&ENTR` (§8.11) | Adds agents at a constant rate | Flow spawning on a distribution: `use_flow_spawning`, `flow_start_time`, `flow_end_time` [s]. |
| `&CORR` (§8.13) | One-way corridor or stair between floors | Not supported. pyFDS-Evac is single-floor. |
| `&STRS` (§8.15) | Whole staircase with its own mesh | Not supported. |
| `&EVSS` (§8.14) | Incline with speed factors `FAC_V0_UP/DOWN/HORI` | Not supported as an incline. A `zones` or `checkpoints` entry with a `speed_factor` (0 to 3) scales the speed of agents inside a polygon, with no direction dependence. |
| `DET_*` and `PRE_*` (§8.7, §8.8) | Detection time plus reaction time, each from a distribution | One pre-movement delay per agent: `use_premovement`, `premovement_distribution`, `premovement_param_a`, `premovement_param_b`, `premovement_seed`. There is no separate detection phase. See the table below. |
| `TDET_SMOKE_DENS` (§8.7) | Smoke at the agent's position triggers detection | Not supported. The pre-movement delay does not depend on smoke. |
| `VELOCITY_DIST` and speed ranges (§8.7) | Unimpeded walking speed distribution | `v0` [m/s], default 1.2, with `v0_distribution` = `"constant"` or `"gaussian"` and `v0_std`. These are the keys the run reads from the JSON. `desired_speed`, `desired_speed_distribution` and `desired_speed_std` are aliases accepted only by `Scenario.set_agent_params()` in Python, which writes the `v0` keys; in the JSON they are ignored. Gaussian draws are clipped to 0.1–5.0 m/s. There is no uniform speed distribution. |
| Smoke-speed reduction (Eq. 11) and `SMOKE_MIN_SPEED` | Linear speed reduction with extinction, floored at `SMOKE_MIN_SPEED` × *v*0 | The default is the same law, Frantzich–Nilsson (the `lund` option; the linear FDS+Evac law). Its coefficients (`alpha`, `beta`, `min_speed_factor`) are library-level; see [What needs Python](#what-needs-python). |
| FED, fractional effective dose (§3.4) | Purser FED from CO, CO2, O2 (and optional gases), incapacitation at FED ≥ 1 | Computed when the output has CO, CO2 and O2 slices; HCN, NOx and irritant slices are added when present. A separate convective heat dose is computed from a `TEMPERATURE` slice. By default each agent draws its own threshold (log-normal, median 1, spread 0.94), so about half stop below FED = 1. Use `--incapacitation-mode deterministic` (and `--heat-incapacitation-mode deterministic`) to stop every agent at FED = 1 as FDS+Evac does. Thresholds are set with `--fed-threshold` and `--heat-fed-threshold`. |
| FED activity level | Rest, light work or heavy work | Not supported. The CO term is fixed. See [issue #135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135). |
| `KNOWN_DOOR_NAMES`, `KNOWN_DOOR_PROBS` (§8.8) | Which exits an agent knows, with a probability per exit | `familiarity` on a distribution: `"full"`, `"discovery"`, or one probability in [0, 1] applied to every exit. `entrance` names one exit the agents always know. A probability per exit is not supported; see [issue #136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136). |
| Door selection with smoke (`FED_DOOR_CRIT`) | Ranks doors as smoke-free by FED or visibility | Route choice is a different model, configured in the JSON `routing` block and switched on by default (`--enable-rerouting`). See [Smoke-aware routing](routing.md). |
| `TAU` (`TAU_MEAN` etc., §8.7) | Relaxation time of the social-force model | No equivalent. Movement parameters belong to the JuPedSim model named in `model_type`. |

### Pre-movement parameters

The two parameters mean different things for each distribution, so FDS+Evac
values cannot be copied across unchanged. The delay is in seconds.

| `premovement_distribution` | `premovement_param_a` | `premovement_param_b` | Preset (*a*, *b*) |
|---|---|---|---|
| `gamma` (default) | shape | scale [s] | 1.291, 103.901 |
| `lognormal` | mean of ln(*t*) | standard deviation of ln(*t*) | 4.586, 0.967 |
| `weibull` | scale [s] | shape | 139.285, 1.195 |
| `uniform` | lower bound [s] | upper bound [s] | 0.0, 60.0 |

The presets are illustrative, not from a cited dataset. Set both parameters
from data for your occupancy.

The presets are used when `use_premovement` is `true` and `premovement_param_a`
or `premovement_param_b` is missing; both parameters must be given for either
to take effect. With `use_premovement` false, which is the default, agents
start moving at *t* = 0. When `premovement_seed` is null, the draws are seeded
from the run seed, so they repeat under a fixed `--seed`.

While an agent waits, its walking speed is not reduced by the smoke around
it. It starts at its full clear-air speed when it is released. Its toxic dose
does accumulate while it waits.

## What is lost

Some FDS+Evac features have no counterpart. The social-force movement model
with its three-circle body, and its dedicated counterflow algorithm, are
replaced by the JuPedSim model you choose. Floors, stairs, `&EVHO` holes,
smoke-triggered detection, per-exit known-door probabilities and the FED
activity level are not supported. Each is described on the
[Limitations](limitations.md) page.

## What needs Python

Some parameters cannot be set from the CLI or the scenario JSON. The
smoke-speed parameters are the main case. `speed_law` (`"lund"` or
`"fridolf"`), `alpha`, `beta`, `min_speed_factor` and `visibility_factor_c`
are fields of `SmokeSpeedConfig`, and `run.py` and the web GUI build that
object with its defaults. A run started from either one uses the
Frantzich–Nilsson law with `alpha` = 0.706, `beta` = −0.057 and `min_speed_factor` =
0.1.

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
      are not supported. `generate_walkable_from_fds.py` treats stair treads
      and risers as floor, so a staircase in the deck becomes flat floor
      walked at full speed.
- [ ] Check the walkable polygon it produces (`--plot`, `--report`). The
      script decides what blocks from the CAD layer name in the comment after
      each `&OBST`, so a deck without such comments needs checking by hand.
- [ ] Translate pre-movement into one delay per agent (table above). Detection
      and reaction are no longer separate.
- [ ] Decide what each group knows (`familiarity`, `entrance`).
- [ ] Run FDS, then `uv run python run.py --scenario <json> --fds-dir <dir> --inspect-fds`
      to list the quantities pyFDS-Evac finds.
- [ ] Read the warnings of the first run. A missing gas slice switches FED off
      and the run still finishes, reporting FED = 0.
- [ ] Read [Limitations](limitations.md) and the
      [verification status](https://pedestriandynamics.org/pyFDS-Evac/models/verification/).

## Words that changed meaning

> **Terminology.**
>
> - **`tau`** is an *optical depth* here: the mean extinction coefficient
>   along a route times its length, *τ* = *K*ave · *L* (dimensionless).
>   It is not the relaxation time `TAU` of FDS+Evac. The routing key
>   `tau_max` (default 6.0) is an optical depth.
> - **Stage** is a JuPedSim target: a distribution, a checkpoint or an exit.
>   Journeys are sequences of stages.
> - **Gate** has two meanings, and only two. The route-cost gate
>   (`routing.cost_model = "gate"`, the default) refuses routes whose
>   optical depth is too high. Sight gating decides whether an agent can
>   read a sign, and so which exits enter its cognitive map. The dose is not
>   a gate: when it reaches the agent's threshold, the agent stops.
> - **FIC**, Purser's fractional irritant concentration, which slows agents,
>   is called FEC (fractional effective concentration) in ISO 13571.
> - **Cognitive map** is the graph of stages an agent knows. It is not meant
>   in the psychological sense.

## References

Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0). VTT Technical
Research Centre of Finland.
