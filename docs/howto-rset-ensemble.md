---
title: "How do I get the egress time and its spread from an ensemble of seeds?"
linkTitle: "Egress time from an ensemble"
weight: 14
---

**This how-to reads tracked FDS output. You do not need to run FDS.** Part 1
needs no FDS output at all.

Run the scenario once per seed. Read each agent's exit time from the trajectory
file, not from `result.evacuation_time`. Then report the last exit time over the
seeds as a mean, a standard deviation (SD), a range and a high percentile, not
as a single value.

## What the simulation gives you

ISO/TR 16738 splits the required safe escape time as

*RSET* = *t*<sub>det</sub> + *t*<sub>a</sub> + *t*<sub>pre</sub> + *t*<sub>trav</sub>

where *t*<sub>det</sub> is the detection time, *t*<sub>a</sub> the alarm
time, *t*<sub>pre</sub> the pre-movement time and *t*<sub>trav</sub> the travel
time, all in seconds.

A pyFDS-Evac run starts at *t* = 0 and gives at most
*t*<sub>pre</sub> + *t*<sub>trav</sub>. It includes *t*<sub>pre</sub> only if
the scenario models pre-movement (`use_premovement` in a spawn area). You add
*t*<sub>det</sub> and *t*<sub>a</sub> yourself. The scenario in Part 1 models no
pre-movement, so its exit times are travel times only.

## Why not `result.evacuation_time`?

- `result.evacuation_time` is the time at which the simulation loop stopped.
  The loop stops when no agent is left, or at `max_simulation_time`. An
  incapacitated agent stays in the simulation, so one incapacitation makes
  `evacuation_time` equal to `max_simulation_time`
  ([#141](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/141)).
- `result.success` is `True` when the run reaches `max_simulation_time`, even
  with agents still inside
  ([#139](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/139)).

Part 2 below shows both.

## Runnable example

The full script is [`examples/rset_ensemble.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/examples/rset_ensemble.py).
Run it from the repository root (runtime about 10 s):

```bash
uv run python examples/rset_ensemble.py
```

```python
import json
import pathlib
import sqlite3

import numpy as np
from matplotlib.figure import Figure

from pyfds_evac import (
    DefaultFedConfig,
    DefaultFedModel,
    FdsFedField,
    TenabilityConfig,
    load_scenario,
    run_scenario,
)

SEEDS = [1, 2, 3, 4, 5]
FIGURE = pathlib.Path("site/static/images/howto/egress_exit_curve.png")
COLOURS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9"]  # Okabe-Ito
```

### Read exit times from the trajectory

`run_scenario` writes the trajectory to a SQLite file (`result.sqlite_file`)
at 10 frames per second. An agent's exit time is the time of the last frame
it appears in, so it is accurate to 0.1 s. Agents still inside at the end
appear up to the last frame and are dropped. The incapacitated agents are
read from `result.fed_history`, which exists only when a FED model ran.

```python
def exit_times(result):
    """Exit time [s] of every agent that left, from the trajectory file."""
    con = sqlite3.connect(result.sqlite_file)
    try:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()[0]
        )
        last = con.execute("SELECT MAX(frame) FROM trajectory_data GROUP BY id")
        times = sorted(frame / fps for (frame,) in last)
    finally:
        con.close()
    # Agents still inside at the end are the ones seen in the last frames.
    return times[: len(times) - result.agents_remaining]


def incapacitated(result):
    """Number of agents incapacitated during the run."""
    rows = result.fed_history or []
    return len({row["agent_id"] for row in rows if row["incapacitated"]})
```

### Part 1: one run per seed

The scenario is `assets/fic_vs_fed_speed`: 30 agents at one end of a
4 m × 50 m corridor with one exit, in clear air. Each run writes a manifest
next to its trajectory, and the loop reads the seed back from it.

```python
scenario = load_scenario("assets/fic_vs_fed_speed")
for name, dist in scenario.distributions.items():
    params = dist["parameters"]
    print(
        f"{name}: {params['number']} agents, "
        f"use_premovement={params.get('use_premovement', False)}"
    )

curves = {}
for seed in SEEDS:
    result = run_scenario(scenario, seed=seed)
    manifest = json.loads(pathlib.Path(result.manifest_file).read_text())
    curves[manifest["seed"]] = exit_times(result)
    print(
        f"seed {manifest['seed']}: last exit {curves[seed][-1]:.1f} s, "
        f"evacuated {len(curves[seed])}, incapacitated {incapacitated(result)}, "
        f"remaining {result.agents_remaining}"
    )
    result.cleanup()
print(f"versions: {manifest['versions']}")
print(f"git: {manifest['git_commit']}, dirty: {manifest['git_dirty']}")
```

Expected output, without the `Evacuated 30/30 … done` progress line that
`run_scenario` prints for each run:

```text
jps-distributions_0: 30 agents, use_premovement=False
seed 1: last exit 44.4 s, evacuated 30, incapacitated 0, remaining 0
seed 2: last exit 43.0 s, evacuated 30, incapacitated 0, remaining 0
seed 3: last exit 43.6 s, evacuated 30, incapacitated 0, remaining 0
seed 4: last exit 44.3 s, evacuated 30, incapacitated 0, remaining 0
seed 5: last exit 42.2 s, evacuated 30, incapacitated 0, remaining 0
versions: {'pyfds-evac': '0.1.0', 'jupedsim': '1.4.2', 'fdsreader': '1.11.7', 'fdsvismap': '0.2.1'}
git: 3f47897b351d9f8c403782611282c0bc2a2bdcb0, dirty: True
```

The versions and the git state depend on your checkout. `dirty: True` means the
working tree had uncommitted changes when the run started. The seed changes
where the agents start in their spawn area, so each seed gives a different
time. There is no fire in Part 1, so nobody is incapacitated.

### Summarise the last exit over the seeds

```python
last = np.array([times[-1] for times in curves.values()])
print(f"n = {len(last)} seeds")
print(f"mean = {last.mean():.1f} s, SD = {last.std(ddof=1):.1f} s")
print(f"min-max = {last.min():.1f}-{last.max():.1f} s")
print(f"95th percentile = {np.percentile(last, 95):.1f} s")
```

```text
n = 5 seeds
mean = 43.5 s, SD = 0.9 s
min-max = 42.2-44.4 s
95th percentile = 44.4 s
```

**Five seeds are too few for a study.** They keep this example fast. The SD and
the percentiles need many more runs to settle. The 95th percentile uses NumPy's
default linear interpolation; with five values it lies between the two largest.
Increase `SEEDS`, and check that the summary no longer changes much when you
add runs.

### Plot the exit curves

```python
fig = Figure(figsize=(6, 4))
ax = fig.subplots()
for (seed, times), colour in zip(curves.items(), COLOURS):
    counts = np.arange(1, len(times) + 1)
    ax.step(times, counts, where="post", color=colour, label=f"seed {seed}")
ax.set_xlabel("time since start of simulation [s]")
ax.set_ylabel("agents evacuated [-]")
ax.legend()
FIGURE.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(FIGURE, dpi=150, bbox_inches="tight")
print(f"figure: {FIGURE}")
```

![Five step curves of agents evacuated against time, one per seed; each rises from 1 near 33–35 s to 30 between 42 and 45 s](/images/howto/egress_exit_curve.png)

*Cumulative number of agents evacuated [-] against time since the start of the
simulation [s], `assets/fic_vs_fed_speed`, N = 30 agents, clear air, no
pre-movement. One line per seed, n = 5 seeds. Exit times are read from the
trajectory at 0.1 s resolution. Regenerated by `examples/rset_ensemble.py`.*

### Part 2: an incapacitated agent and `evacuation_time`

No tracked FDS case gives incapacitations and exits in the same run within a
few seconds of runtime. Part 2 therefore uses the ISO 20414 Test 19 room of the
[Real-FDS walkthrough](walkthrough.md): one occupant held still in 0.10 % CO,
2.0 % CO2 and 15.0 % O2, read from the FDS slices in
`assets/iso_table22_coupled/fds/a`.

```python
room = load_scenario("assets/iso_table22_coupled/config_a.json")
gas_dir = "assets/iso_table22_coupled/fds/a"
fed = DefaultFedModel(FdsFedField.from_fds(gas_dir), DefaultFedConfig())
tenability = TenabilityConfig(incapacitation_mode="deterministic")
fire = run_scenario(room, seed=420, fed_model=fed, tenability_config=tenability)
print(
    f"evacuation_time {fire.evacuation_time:.0f} s "
    f"(max_simulation_time {room.max_simulation_time:.0f} s), "
    f"success {fire.success}"
)
print(
    f"exit times {exit_times(fire)}, incapacitated {incapacitated(fire)}, "
    f"remaining {fire.agents_remaining}"
)
fire.cleanup()
```

```text
evacuation_time 1150 s (max_simulation_time 1150 s), success True
exit times [], incapacitated 1, remaining 1
```

The occupant is incapacitated at 982 s and never leaves. Nevertheless
`evacuation_time` reports the time limit and `success` is `True`. The exit
times, the incapacitated count and the remaining count tell you what happened.

## Incapacitation mode

`TenabilityConfig()` defaults to `incapacitation_mode="probabilistic"`. Each
agent then draws its own threshold, `fed_threshold * exp(susceptibility_sigma * Z)`
with *Z* ~ N(0, 1): a log-normal with median `fed_threshold`. The defaults
are on the [FED model](/models/fed.md#tenability-irritant-slowdown-and-incapacitation) page. For results comparable with FDS+Evac, where
every agent is incapacitated at FED = 1, use
`TenabilityConfig(incapacitation_mode="deterministic")`, or
`--incapacitation-mode deterministic` on the command line. Part 2 uses the
deterministic mode.

## Related options

- To add smoke or FED from FDS output to an ensemble, pass the same models to
  `run_scenario` inside the loop, as in the [Real-FDS walkthrough](walkthrough.md).
- Pre-movement is set per spawn area in the scenario JSON, with
  `use_premovement`, `premovement_distribution` (`gamma`, `lognormal`,
  `weibull` or `uniform`), `premovement_param_a`, `premovement_param_b` and
  `premovement_seed`. If `premovement_seed` is `null`, it is derived from the
  run seed, so the pre-movement times change with the seed. If it is set, they
  stay the same across seeds.
- Each manifest also records `uv_lock_sha256`, `scenario_path`, `fds_dir`,
  `fds_version` and `created_utc`. `cleanup()` deletes it with the trajectory,
  so copy both first if you want to keep them. With `run.py --output-sqlite
  PATH`, the manifest is copied next to `PATH` as `<stem>.manifest.json`.

## See also

- [Quickstart](quickstart.md)
- [Real-FDS walkthrough](walkthrough.md)
- [Limitations](limitations.md)

pyFDS-Evac is research software, provided without warranty.
