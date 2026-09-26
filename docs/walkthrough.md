---
title: "Real-FDS walkthrough"
weight: 5
---

**This page reads FDS output, but you do not need to run FDS.** The output of
two small FDS cases is tracked in the repository, and the page uses it as is.

## Goal

Go from FDS output to an evacuation result:

1. list what an FDS case contains;
2. slow an agent with the extinction coefficient read from an FDS slice;
3. accumulate a toxic dose (FED, fractional effective dose) from the CO, CO2
   and O2 slices;
4. see a run that finishes normally but has no FED in it, and learn how to
   detect it.

## Prerequisites

- A clone of the repository and its environment (`uv sync`). fdsreader, which
  reads the FDS output, is a core dependency.
- Run every command from the repository root. The paths are relative to it.
- Runtime: about 15 s.
- Read [What your FDS case must provide](fds-case-requirements.md). This page
  shows two of the failure modes listed there.

The full script is [`examples/walkthrough.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/examples/walkthrough.py).
Run it with:

```bash
uv run python examples/walkthrough.py
```

It uses two tracked cases, because neither has everything this page needs:

| FDS case | Slices | Scenario | Used for |
|---|---|---|---|
| `assets/iso_table21_coupled/fds` | extinction coefficient | 1 agent walks a 100 m corridor through *K* ≈ 1 1/m | smoke speed, exit time |
| `assets/iso_table22_coupled/fds/a` | CO, CO2, O2, extinction coefficient | 1 occupant held still for 1150 s in a 10 m × 10 m room | FED history |

The occupant in the second case never leaves: its pre-movement time is drawn
above 1.2 × 10⁷ s, as ISO 20414 Test 19 asks. So that case gives a FED history
but no exit time.

## Steps

The script starts with these imports and paths. Everything from pyFDS-Evac is
imported from `pyfds_evac`.

```python
import json
import pathlib
import shutil
import tempfile
from types import SimpleNamespace

from pyfds_evac import (
    DefaultFedConfig,
    DefaultFedModel,
    ExtinctionField,
    FdsFedField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    TenabilityConfig,
    build_run_kwargs,
    load_scenario,
    run_scenario,
)

SMOKE_DIR = "assets/iso_table21_coupled/fds"
GAS_DIR = "assets/iso_table22_coupled/fds/a"
```

### 1. List what the FDS case contains

Before any run, list the slices. The command-line runner does this with
`--inspect-fds`:

```bash
uv run python run.py --scenario assets/iso_table22_coupled/config_a.json \
    --fds-dir assets/iso_table22_coupled/fds/a --inspect-fds
```

Expected output:

```text
Initialization started.
{
  "data_3d": [],
  "devices": [],
  "slices": [
    "CARBON DIOXIDE VOLUME FRACTION",
    "CARBON MONOXIDE VOLUME FRACTION",
    "OXYGEN VOLUME FRACTION",
    "SOOT EXTINCTION COEFFICIENT"
  ],
  "smoke_3d": []
}
```

The same command on `assets/iso_table21_coupled/fds` lists only
`"SOOT EXTINCTION COEFFICIENT"`. That case can drive the smoke-speed model, but
not FED.

FED needs all three of `CARBON MONOXIDE VOLUME FRACTION`,
`CARBON DIOXIDE VOLUME FRACTION` and `OXYGEN VOLUME FRACTION`. Heat FED needs
`TEMPERATURE`. Neither tracked case has a `TEMPERATURE` slice.

fdsreader may also log `Module csv: [Errno 2] No such file or directory: …_hrr.csv`
and `…_steps.csv`, followed by "The error can be safely ignored if not requiring
the csv module". The tracked cases carry no CSV output. These messages come from
fdsreader and do not affect the run.

### 2. Smoke: extinction from FDS slows the walk

```python
corridor = load_scenario("assets/iso_table21_coupled")
clear = run_scenario(corridor, seed=420)

extinction = ExtinctionField.from_fds(SMOKE_DIR)
smoke = SmokeSpeedModel(extinction, SmokeSpeedConfig())
smoky = run_scenario(corridor, seed=420, smoke_speed_model=smoke)

row = smoky.smoke_history[-1]
print(f"K sampled:    {row['extinction_per_m']:.5f} 1/m")
print(f"speed factor: {row['speed_factor']:.6f}")
print(
    f"exit time:    {clear.evacuation_time:.2f} s clear, "
    f"{smoky.evacuation_time:.2f} s in smoke"
)

manifest = json.loads(pathlib.Path(smoky.manifest_file).read_text())
print(f"manifest: fds_dir={manifest['fds_dir']}")
print(f"          fds_version={manifest['fds_version']}")
```

Expected output:

```text
Evacuated 1/1  sim=78.1s  wall=0m00s  done
Evacuated 1/1  sim=85.0s  wall=0m00s  done
K sampled:    0.99545 1/m
speed factor: 0.919631
exit time:    78.14 s clear, 84.97 s in smoke
manifest: fds_dir=/…/fds-evac/assets/iso_table21_coupled/fds
          fds_version=FDS-6.10.1-0-g12efa16-release
```

The manifest stores `fds_dir` as an absolute path; it is shortened here.

`ExtinctionField.from_fds` reads the `SOOT EXTINCTION COEFFICIENT` slice
nearest to `slice_height_m` (default 2.0 m). The deck prescribes a soot density
that gives *K* = 1.0 1/m. The slice returns 0.99545 1/m, and the default speed
law turns it into a speed factor of 0.919631. The ratio of the exit times,
84.97 / 78.14 = 1.0874, matches 1 / 0.919631 = 1.0874 to four decimals.

`ExtinctionField.from_fds` remembers the directory it read. The run manifest
records that directory and reads the FDS version from the `FDSVERSION` line of
its `.smv` file. The manifest also records the package versions, the seed, the
scenario path, the `uv.lock` hash, and the git commit (`git_commit`) and
whether the working tree had uncommitted changes (`git_dirty`). With `run.py
--output-sqlite PATH`, the manifest is copied next to the trajectory as
`<stem>.manifest.json`.

### 3. Gas: FED from the CO, CO2 and O2 slices

```python
room = load_scenario("assets/iso_table22_coupled/config_a.json")
fed = DefaultFedModel(FdsFedField.from_fds(GAS_DIR), DefaultFedConfig())
tenability = TenabilityConfig(incapacitation_mode="deterministic")
exposed = run_scenario(room, seed=420, fed_model=fed, tenability_config=tenability)

for row in exposed.fed_history[::200]:
    print(
        f"t={row['time_s']:6.0f} s  CO={row['co_percent']:.3f} %  "
        f"FED={row['fed_cumulative']:.3f}"
    )
crossing = next(r for r in exposed.fed_history if r["fed_cumulative"] >= 1.0)
print(
    f"FED >= 1 at t = {crossing['time_s']:.0f} s; "
    f"incapacitated: {exposed.fed_history[-1]['incapacitated']}"
)
print(f"FED max: {exposed.metrics['fed_max']:.3f}")
```

Expected output:

```text
Evacuated 0/1  sim=1150.0s  wall=0m05s  done
t=     0 s  CO=0.100 %  FED=0.000
t=   200 s  CO=0.100 %  FED=0.204
t=   400 s  CO=0.100 %  FED=0.407
t=   600 s  CO=0.100 %  FED=0.611
t=   800 s  CO=0.100 %  FED=0.815
t=  1000 s  CO=0.100 %  FED=1.019
FED >= 1 at t = 982 s; incapacitated: True
FED max: 1.170
```

The deck fills the room with 0.10 % CO, 2.0 % CO2 and 15.0 % O2. The hand
calculation for this mixture reaches FED = 1 at 981.7 s
(`assets/iso_table22_coupled/build_geometry.py`), and the run crosses it at
982 s. `fed_history` has one row per agent per update interval (1 s by
default).

`TenabilityConfig()` defaults to `incapacitation_mode="probabilistic"`, which
draws a log-normal threshold for each agent with median `fed_threshold = 1.0`.
This page uses `"deterministic"`, so the threshold is exactly 1.0, as in
FDS+Evac. The command-line equivalent is `--incapacitation-mode deterministic`.

The incapacitated occupant stays in the simulation, so the run continues to
`max_simulation_time` and `exposed.evacuation_time` reports 1150 s. It is not
an exit time ([#141](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/141)).

`FdsFedField.from_fds` takes the first slice of each gas and does not match
the slice height. `ExtinctionField.from_fds` and `FdsHeatField.from_fds` do.

### 4. Checkpoint: a run that succeeds but is wrong

This step copies case `a` to a temporary directory and deletes its CO slice:
the `.sf` and `.sf.bnd` files, and the five-line `SLCF` entry in the `.smv`
file that points to them. The copy looks like FDS output from a deck that
never asked for a CO slice.

```python
broken = pathlib.Path(tempfile.mkdtemp()) / "a"
shutil.copytree(GAS_DIR, broken, ignore=shutil.ignore_patterns("*.pickle"))
for path in broken.glob("iso_table22_a_1_1.sf*"):  # the CO slice
    path.unlink()
smv = broken / "iso_table22_a.smv"
lines = smv.read_text().splitlines(keepends=True)
start = next(i for i, line in enumerate(lines) if "iso_table22_a_1_1.sf" in line) - 1
smv.write_text("".join(lines[:start] + lines[start + 5 :]))
```

The `*.pickle` file is a cache that fdsreader writes into the case directory.
It is skipped so that the copy is read fresh.

**If you build the FED field yourself, the missing slice fails loudly:**

```python
try:
    FdsFedField.from_fds(str(broken))
except IndexError as error:
    print(f"FdsFedField.from_fds: IndexError: {error}")
```

```text
FdsFedField.from_fds: IndexError: tuple index out of range
```

The message does not name the missing slice.

**If you go through `build_run_kwargs`, the run continues without FED.**
`build_run_kwargs` is what `run.py` and the web GUI call. It turns their
options into `run_scenario` keywords:

```python
opts = SimpleNamespace(
    seed=420,
    fds_dir=str(broken),
    constant_extinction=None,
    smoke_update_interval=1.0,
    smoke_slice_height=2.0,
    disable_tenability=False,
    fed_threshold=1.0,
    fic_alpha=0.7,
    fic_min_factor=0.3,
    incapacitation_mode="deterministic",
    enable_rerouting=False,
    reroute_interval=1.0,
    vis_cache=None,
)
kwargs = build_run_kwargs(room, opts)
silent = run_scenario(room, **kwargs)
print(
    f"finished at {silent.evacuation_time:.0f} s, "
    f"{silent.agents_remaining} agent still in the room"
)
```

```text
Evacuated 0/1  sim=1150.0s  wall=0m05s  done
finished at 1150 s, 1 agent still in the room
```

The run finishes at the same time as in step 3, with no error. But no dose was
computed. In step 3, the same occupant in the same gas was incapacitated at
982 s.

### 5. Detect it

**Read the warnings.** `build_run_kwargs` logs this to stderr (the temporary
path differs):

```text
WARNING:pyfds_evac.core.run_config:FED is disabled for /tmp/tmp3i0w6sml/a: it has no CO slice, and all three of CO, CO2 and O2 are needed. Results will report zero dose and no incapacitation. FDS only writes these species when the &REAC line asks for them (CO needs CO_YIELD); see docs/fds-case-requirements.md.
WARNING:pyfds_evac.core.run_config:Heat FED is disabled for /tmp/tmp3i0w6sml/a: it has no TEMPERATURE slice. Results will report zero heat dose and no thermal incapacitation. Add `&SLCF QUANTITY='TEMPERATURE'` to the FDS deck; see docs/fds-case-requirements.md.
```

`build_run_kwargs` logs the `Heat FED is disabled` warning for every case
without a `TEMPERATURE` slice, including the intact case `a`. (Step 3 builds
its models by hand, so it logs neither warning.) The fdsreader `csv`
messages from step 1 appear in the same stream, so search for `FED is disabled`
rather than for "warning".

**Check before the run** that `build_run_kwargs` returned a FED model, and
**check after the run** that the metrics hold `fed_max`:

```python
print(f"before: fed_model = {kwargs['fed_model']}")
print(
    f"after:  fed_history = {silent.fed_history}, "
    f"'fed_max' in metrics = {'fed_max' in silent.metrics}"
)
```

```text
before: fed_model = None
after:  fed_history = None, 'fed_max' in metrics = False
```

Here FED and heat FED are both off, so the result carries no FED at all:
`fed_history` is `None` and `metrics` has no `fed_max` key. It does not report
FED = 0 ([#137](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/137)). With `run.py`, `--output-fed-history` writes no file in this case.

`fed_history` alone is not a reliable check. `run_scenario` fills it whenever
either FED track runs. A case with a `TEMPERATURE` slice but no CO slice runs
heat FED only: `fed_history` then exists, every `fed_cumulative` in it is 0.0,
and `metrics` has `heat_fed_max` but no `fed_max`. That zero column looks
exactly like a case where nobody received a dose. `metrics` holds `fed_max` only when the gas FED
model ran, so check `fed_max`, and `kwargs["fed_model"]` before the run.

A third check is the inventory from step 1: if any of CO, CO2 and O2 is
missing from `"slices"`, FED will not run.

The script ends by calling `cleanup()` on each result and deleting the
temporary copy.

## Next steps

- [What your FDS case must provide](fds-case-requirements.md): the slices to
  add to your deck and the full list of failure modes.
- [How do I get RSET with its spread from an ensemble of seeds?](howto-rset-ensemble.md)
- [FDS sampling](fds-sampling.md): how slices are selected and sampled.

pyFDS-Evac is research software, provided without warranty.
