---
title: "A crowd in a real fire"
weight: 3
---

This page runs a larger case end to end: 150 people try to leave a T-shaped
corridor while a 2 MW PVC fire, computed by FDS, fills it with smoke. Each
step shows the command and what it produces.

It builds on the [Quickstart](quickstart.md) (one agent, prescribed smoke) and
the [Real-FDS walkthrough](walkthrough.md) (small tracked FDS cases). Unlike
those, it needs FDS output that is not in the repository; step 3 says how to
get it.

## 1. Check the scenario runs

Run every command on this page from the repository root, in the environment
installed with `uv sync`. Without FDS output the example runs the scenario in
clear air, in about 5 s:

```bash
uv run python examples/first_fds_case.py
```

The last line of the output is:

```text
evacuated: 142/150 in 300 s
```

## 2. The scenario

The scenario is a folder, `assets/t_junction`: a JuPedSim `config.json` and
the walkable area as `geometry.wkt`. It sits beside the FDS deck that made its
fire.

```bash
uv run python run.py --scenario assets/t_junction --print-summary --export-only
```

```text
  Model:         CollisionFreeSpeedModel
  Seed:          42
  Max time:      300s
  Exits:         2
  …
  Sequence:      jps-distributions_0 -> jps-checkpoints_0 -> exit_A_left -> exit_B_right
    jps-distributions_0: 200 agents (flow: 0-400s)
```

In plan view:

![Plan view of the T-junction: a 30 m by 3 m corridor along the top with a green exit at each end, a 6 m by 10 m branch below it with a dashed spawn area, a dotted junction waypoint where the branch meets the corridor, three yellow sign markers with arrows showing which way each sign faces, and a red burner in the corridor between the junction and exit B](/images/first-fds-case/scenario.png)

Agents enter the branch one every 2 s. The run stops at 300 s, so 150 of the
200 planned agents take part. Every agent walks to the junction, then to
exit A, 20 m from the junction, or exit B, 10 m from it and past the fire.

The agents are `discovery` agents (`"familiarity": "discovery"` in
`config.json`). They start knowing only the spawn area. They learn the
junction and the exits when they can read their signs. Smoke can hide a sign.
The rules are on the [wayfinding](/models/wayfinding.md) page.

## 3. The fire

The fire comes from FDS. pyFDS-Evac does not run FDS; it reads the slice
files that FDS wrote.

**Get the FDS output.** The deck is `assets/t_junction/t_junction.fds`: a
2 MW PVC fire on a 2 m × 1 m burner, 300 s, four meshes. Either run it
yourself:

```bash
mkdir -p fire && cp assets/t_junction/t_junction.fds fire/
cd fire && mpiexec -n 4 fds t_junction.fds && cd ..
```

It takes 20 to 30 minutes on four cores. Or use the output the maintainers
keep in their data store, `fds-evac-data/t_junction/fire_2MW_PVC/` (about
125 MB). The data store is not public; ask for it on the
[issue tracker](https://github.com/PedestrianDynamics/pyFDS-Evac/issues).

The rest of this page calls the output directory `$FDS`:

```bash
FDS=fire   # or the path to fire_2MW_PVC
```

**Check what it contains.**

```bash
uv run python run.py --scenario assets/t_junction --fds-dir "$FDS" --inspect-fds
```

```text
{
  "data_3d": [],
  "devices": [],
  "slices": [
    "CARBON DIOXIDE VOLUME FRACTION",
    "CARBON MONOXIDE VOLUME FRACTION",
    "HYDROGEN CHLORIDE VOLUME FRACTION",
    "OXYGEN VOLUME FRACTION",
    "SOOT EXTINCTION COEFFICIENT",
    "SOOT VISIBILITY"
  ],
  "smoke_3d": []
}
```

The extinction coefficient slows the agents and hides signs. CO, CO2 and O2
give the toxic dose (FED). The deck has no `TEMPERATURE` slice, and heat FED
is off by default anyway.

![Four plan views of the T-junction at 20, 30, 45 and 90 s, shaded by the extinction coefficient on a log scale from 0.1 to 30 per metre, with a red dashed contour where visibility drops to 3 m; smoke spreads from the burner along the corridor, reaches the branch by 45 s, and fills the whole T by 90 s](/images/first-fds-case/fire.png)

Smoke reaches the junction at about 30 s. By 90 s it fills the whole T, with a
median extinction coefficient *K* of 8 1/m, a visibility of about 0.4 m.

The deck writes its slices at z = 2.0 m only. pyFDS-Evac samples at 1.6 m by
default, the FDS+Evac head height, and takes the nearest slice, here 2.0 m.

## 4. Run it

```bash
mkdir -p tj
uv run python run.py --scenario assets/t_junction --fds-dir "$FDS" \
    --output-sqlite tj/tj_fire.sqlite \
    --output-smoke-history tj/tj_fire_smoke.csv \
    --output-fed-history tj/tj_fire_fed.csv \
    --output-route-history tj/tj_fire_routes.csv
```

It takes about 45 s. Most of that goes into computing which signs are
readable through the smoke. The output ends with:

```text
Configuring smoke calculation.
Configuring FED calculation.
Heat FED is off; pass --enable-heat-fed to accumulate it.
Configuring rerouting.
Configuring visibility model (3 signs).
Configuring tenability (FIC slowdown=off, FIC alpha=0.7, min=0.3, FED median=1.0, incapacitation=deterministic, heat FED median=1.0, heat incapacitation=deterministic).
Initialization finished.
Simulation started.
…
Simulation stopped after 300.00 s (75/150 evacuated, 75 remaining).
Route switches: 164
```

Before this, fdsreader logs `Module vents: could not convert string to float`
for this deck, and the terminal also shows `Reroute debug` and `Waypoint`
lines and numpy `UserWarning`/`RuntimeWarning` messages. None of them affects
the run. The progress
line counts the 200 planned agents, not the 150 that spawned
([#279](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/279)).

These are the defaults, as in [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source):
every agent is incapacitated at FED = 1, heat FED is off, and irritants (the
HCl slice) slow nobody unless you pass `--enable-fic-speed`.

The run writes five files:

| File | What it holds |
|---|---|
| `tj_fire.sqlite` | trajectories at 10 frames/s (JuPedSim format), with FED and speed per agent |
| `tj_fire.manifest.json` | versions, seed, scenario, FDS directory and FDS version |
| `tj_fire_smoke.csv` | per agent and second: position, extinction *K*, speed factor |
| `tj_fire_fed.csv` | per agent and second: gas concentrations, FED, FIC, incapacitated |
| `tj_fire_routes.csv` | every route change, with its time and reason |

For the clear-air comparison below, run the same command without `--fds-dir`:

```bash
uv run python run.py --scenario assets/t_junction \
    --output-sqlite tj/tj_clear.sqlite
```

**The same run from Python.** `examples/first_fds_case.py` takes the FDS
directory as its argument:

```bash
uv run python examples/first_fds_case.py "$FDS"
```

`build_run_kwargs` is the function `run.py` calls, so the run is the same.
The script imports:

```python
import sys
from collections import Counter
from types import SimpleNamespace

from pyfds_evac import build_run_kwargs, load_scenario, run_scenario

FDS_DIR = sys.argv[1] if len(sys.argv) > 1 else None
```

and runs:

```python
scenario = load_scenario("assets/t_junction")
opts = SimpleNamespace(
    seed=None,  # the scenario's baseSeed, 42
    fds_dir=FDS_DIR,
    constant_extinction=None,
    smoke_update_interval=1.0,
    smoke_slice_height=1.6,
    disable_tenability=False,
    fed_threshold=1.0,
    fic_alpha=0.7,
    fic_min_factor=0.3,
    enable_rerouting=True,
    reroute_interval=1.0,
    vis_cache=None,
)
result = run_scenario(scenario, **build_run_kwargs(scenario, opts))

print(f"evacuated: {result.agents_evacuated}/{result.total_agents} in 300 s")
if FDS_DIR is not None:
    print(f"FED max:   {result.metrics['fed_max']:.2f}")
    reasons = Counter(r["reason"] for r in result.route_history)
    print(f"route changes: {dict(reasons)}")
```

```text
evacuated: 75/150 in 300 s
FED max:   0.36
route changes: {'smoke_reroute': 10, 'wander': 154}
```

Run one scenario per Python process. A second run in the same process can
give a different result
([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198); see
[Limitations › Reproducibility](limitations.md#reproducibility)).

## 5. Results

The figures below are drawn from these files by
[`scripts/docs/first_fds_case_figures.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/scripts/docs/first_fds_case_figures.py):

```bash
uv run python scripts/docs/first_fds_case_figures.py --data "$FDS" --runs tj
```

### Where the agents went

![Two plan views of walked trajectories; in clear air all 142 agents who left walk from the branch to exit B, 8 are still in the branch; in the fire, 10 agents walk left to exit A, 65 walk past the burner to exit B, and 75 are still in the branch or at the junction at 300 s](/images/first-fds-case/trajectories.png)

In clear air everyone takes the nearer exit B. In the fire, 10 early agents
turn to exit A as smoke builds up on B's side. Half the agents are still inside at
300 s.

### The run, animated

![Animation of the fire run at 16 times real time: agents enter the branch as dots, the corridor darkens with smoke from the burner, and the dots turn from blue to red and grow as the smoke slows them, until a crowd of slow red dots fills the branch and the junction](/images/first-fds-case/agents_smoke.gif)

The background is the extinction field the agents read. Red, large dots are
agents the smoke has slowed. From about 120 s almost every agent crawls.

### Evacuated over time

![Number of agents out of the building against time; the clear-air curve follows the spawn line and reaches 142 at 300 s; the fire curve falls behind from about 45 s and reaches 75](/images/first-fds-case/evacuated.png)

In clear air, agents leave about as fast as they arrive. In the fire, the gap
opens at about 45 s, when the smoke has filled the junction.

### Dose and speed

![Top: FED against time, one grey line per agent, the highest in red reaching 0.36, all well below the dashed incapacitation line at FED 1. Bottom: median speed factor of the agents inside, falling from 1 at 40 s to the floor of 0.1 at 120 s and staying there](/images/first-fds-case/exposure.png)

Nobody is incapacitated: the highest FED is 0.36. The smoke acts through
speed. The default speed law (`lund`) multiplies the walking speed by
`1 + beta * K / alpha`, clamped to [0.1, 1]. At *K* = 3 1/m this is
`1 + (-0.057 × 3.0) / 0.706` = 0.76. Above *K* = 11 1/m it is the floor, 0.1,
and from 120 s the median agent is there.

### Exit usage

![Stacked horizontal bars: clear air, 142 through exit B and 8 inside; fire, 10 through exit A, 65 through exit B and 75 inside](/images/first-fds-case/exits.png)

The route log explains the fire run. The 10 agents who switched to exit A
(`smoke_reroute`) did so in the first 27 s, and all 10 left by it. 18 agents,
spawned between 26 and 120 s, never learned an exit: no exit sign was readable
to them. They walk back and forth between the spawn area and the junction
(`wander`, 154 of the 164 route changes), and all 18 are still inside at
300 s.

## What next

- [What your FDS case must provide](fds-case-requirements.md), before you use
  your own FDS output.
- [Real-FDS walkthrough](walkthrough.md): FED from FDS slices, and how to spot
  a run that finishes but has no FED in it.
- [How do I get RSET with its spread from an ensemble of seeds?](howto-rset-ensemble.md)
- Models: [smoke and speed](/models/smoke-speed.md),
  [FED](/models/fed.md), [wayfinding](/models/wayfinding.md),
  [routing](/models/routing.md).
- Verification: [ISO 20414](/verification/iso-20414.md), the tests the
  models are checked against.
- Fundamentals, the published laws behind the models:
  [walking speed in smoke](/fundamentals/walking-speed.md),
  [asphyxiant FED](/fundamentals/asphyxiant-fed.md),
  [visibility](/fundamentals/visibility.md).

pyFDS-Evac is research software, provided without warranty.
