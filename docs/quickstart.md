---
title: "Quickstart"
weight: 1
---

**No FDS output is needed.** This page runs a scenario tracked in the
repository with a uniform, prescribed smoke field.

## Goal

Run one evacuation twice, once in clear air and once in smoke, and see how much
the smoke slows the agent. Then find the run manifest, which records how the
run was produced.

## Prerequisites

- A clone of the repository and its environment (`uv sync`).
- Run every command from the repository root. The scenario paths are relative
  to it.
- Runtime: about 3 s.

The full script is [`examples/quickstart.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/examples/quickstart.py).
Run it with:

```bash
uv run python examples/quickstart.py
```

The scenario is `assets/ISO-table21`: a corridor 2 m wide and 100 m long, with
one agent at one end walking at 1.25 m/s towards the exit at the other end. It
is the geometry of ISO 20414 Test 18.

## Steps

### 1. Import the public API

Everything is imported from `pyfds_evac`.

```python
from pyfds_evac import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)

K_PER_M = 3.0  # extinction coefficient K [1/m]; visibility S = 3/K = 1 m
```

*K* is the extinction coefficient in 1/m. With a visibility factor *C* = 3
(a reflective sign), the visibility is *S* = *C*/*K* = 1 m.

### 2. Run in clear air

```python
scenario = load_scenario("assets/ISO-table21")
clear = run_scenario(scenario, seed=420)
print(f"clear air:   {clear.evacuation_time:.2f} s")
```

Expected output:

```text
Evacuated 1/1  sim=78.8s  wall=0m00s  done
clear air:   78.77 s
```

`run_scenario` prints the `Evacuated …` progress line itself. The last line is
the evacuation time in seconds.

### 3. Run in smoke

`ConstantExtinctionField` returns the same *K* at every point and time.
`SmokeSpeedConfig()` uses the default speed law (`"lund"`), which scales the
walking speed by `1 + beta * K / alpha`, clamped to `[min_speed_factor, 1.0]`,
with the defaults listed on the
[smoke-speed model](/models/smoke-speed.md#parameters) page.

```python
smoke = SmokeSpeedModel(ConstantExtinctionField(K_PER_M), SmokeSpeedConfig())
smoky = run_scenario(scenario, seed=420, smoke_speed_model=smoke)
print(f"K = {K_PER_M} 1/m: {smoky.evacuation_time:.2f} s")
```

Expected output:

```text
Evacuated 1/1  sim=103.8s  wall=0m00s  done
K = 3.0 1/m: 103.77 s
```

### 4. Check the speed factor and find the manifest

```python
factor = smoky.smoke_history[-1]["speed_factor"]
print(f"speed factor in smoke: {factor:.4f}")
print(f"time ratio smoke/clear: {smoky.evacuation_time / clear.evacuation_time:.4f}")
print(f"manifest: {smoky.manifest_file}")
```

Expected output (the manifest path is a new temporary file on every run):

```text
speed factor in smoke: 0.7578
time ratio smoke/clear: 1.3174
manifest: /tmp/tmpxbcef0vs.manifest.json
```

`run_scenario` writes the trajectory to a temporary SQLite file and the
manifest next to it, as `<trajectory stem>.manifest.json`. The manifest records
the versions of pyFDS-Evac, JuPedSim, fdsreader and fdsvismap, the `uv.lock`
hash, the seed, the scenario path, and the FDS directory and version (both
`null` here, because no FDS output was read).

### 5. Clean up

```python
clear.cleanup()
smoky.cleanup()
```

`cleanup()` deletes the temporary trajectory file and its manifest. Copy them
first if you want to keep them.

## Checkpoint

- Both runs print `Evacuated 1/1`. Nobody is left in the corridor.
- The smoke run is slower than the clear run.
- The speed factor is `1 + (-0.057 × 3.0) / 0.706 = 0.7578`, as the code
  computes it.
- The time ratio (1.3174) is close to `1 / 0.7578 = 1.3196`, but not equal to
  it. The evacuation time comes from the full JuPedSim run, not from distance
  divided by speed.

If the smoke run is not slower, check that you passed `smoke_speed_model=`.
Without it, `run_scenario` models no smoke.

## Next steps

- [What your FDS case must provide](fds-case-requirements.md), before you point
  the tool at your own FDS output.
- [Real-FDS walkthrough](walkthrough.md): the same steps with extinction and
  gas read from FDS slices, and how to spot a run that succeeds but is wrong.
- [How do I get RSET with its spread from an ensemble of seeds?](howto-rset-ensemble.md)
- [Smoke-speed model](smoke-speed-model.md) for the speed laws and their
  parameters.

pyFDS-Evac is research software, provided without warranty.
