---
title: "Quickstart"
weight: 1
aliases: [/docs/quickstart/]
---

Run the same evacuation twice, once in clear air and once in smoke, and see
how smoke changes walking speed and evacuation time.

**What you will do**

1. Run a clear-air evacuation.
2. Add a prescribed smoke field.
3. Compare both runs.
4. Change the smoke density yourself.
5. Inspect the manifest that records how the run was produced.

Runtime: about 3 s. No FDS output is needed.

{{< tutorial-progress "Clear air" "Smoke" "Compare" "Experiment" "Reproducibility" >}}

## Before you start

You need:

- a clone of the repository;
- the environment installed with `uv sync`;
- a shell opened in the repository root.

The complete example is [`examples/quickstart.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/examples/quickstart.py).
Run it with:

```bash
uv run python examples/quickstart.py
```

The scenario is `assets/ISO-table21`: a corridor 2 m wide and 100 m long, with
one agent walking at 1.25 m/s from one end to the exit at the other. It is the
geometry of ISO 20414 Test 18.

## 1. Import the API

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

{{< details title="What are these objects?" closed="true" >}}
- `load_scenario` loads a tracked JuPedSim scenario.
- `run_scenario` runs it and returns the result.
- `ConstantExtinctionField` is a prescribed smoke field: the same extinction
  coefficient *K* everywhere, at all times.
- `SmokeSpeedModel` slows the agents according to the smoke they stand in.
- `SmokeSpeedConfig` chooses and configures the speed law.
{{< /details >}}

## 2. Run in clear air

```python
scenario = load_scenario("assets/ISO-table21")
clear = run_scenario(scenario, seed=420)
print(f"clear air:   {clear.evacuation_time:.2f} s")
```

{{< checkpoint title="Clear-air run completed" >}}
```text
Evacuated 1/1  sim=78.8s  wall=0m00s  done
clear air:   78.77 s
```

The agent reached the exit in about 79 s. `run_scenario` prints the
`Evacuated …` progress line itself.
{{< /checkpoint >}}

## 3. Run in smoke

Now run the same scenario, with the same seed, in a uniform smoke field.

```python
smoke = SmokeSpeedModel(
    ConstantExtinctionField(K_PER_M),
    SmokeSpeedConfig(),
)

smoky = run_scenario(
    scenario,
    seed=420,
    smoke_speed_model=smoke,
)

print(f"K = {K_PER_M} 1/m: {smoky.evacuation_time:.2f} s")
```

{{< checkpoint title="Smoke run completed" >}}
```text
Evacuated 1/1  sim=103.8s  wall=0m00s  done
K = 3.0 1/m: 103.77 s
```

The same evacuation now takes about 104 s instead of 79 s.
{{< /checkpoint >}}

{{< comparison label-a="Clear air" value-a="78.77" label-b="Smoke, K = 3 1/m" value-b="103.77" unit="s" >}}

In this example, one agent in one corridor, the evacuation time grows by about
a third. Other scenarios change by other amounts.

{{< details title="Why did the agent slow down?" closed="true" >}}
`ConstantExtinctionField(K)` returns the same extinction coefficient *K* at
every point and time. `SmokeSpeedConfig()` selects the default speed law,
`"lund"`, which multiplies the walking speed by a factor that falls linearly
with *K*:

```text
speed factor = 1 + beta × K / alpha,  clamped to [min_speed_factor, 1.0]
```

With the defaults, *K* = 3.0 1/m gives `1 + (-0.057 × 3.0) / 0.706` = 0.7578.
The agent walks at about 76 % of its clear-air speed. The clamp matters only
above *K* ≈ 11 1/m, where the factor would drop below `min_speed_factor` = 0.1.

With a visibility factor *C* = 3 (a reflective sign), the visibility is
*S* = *C*/*K* = 1 m.

The [smoke-speed model](/models/smoke-speed.md) page has the laws, their
parameters and their sources.
{{< /details >}}

## 4. Compare the runs

```python
factor = smoky.smoke_history[-1]["speed_factor"]
ratio = smoky.evacuation_time / clear.evacuation_time

print(f"speed factor in smoke: {factor:.4f}")
print(f"time ratio smoke/clear: {ratio:.4f}")
```

{{< checkpoint title="What this tells us" >}}
```text
speed factor in smoke: 0.7578
time ratio smoke/clear: 1.3174
```

Walking speed in smoke: 75.8 % of the clear-air speed.
Evacuation time: 131.7 % of the clear-air time.
{{< /checkpoint >}}

{{< details title="Why is the time ratio not exactly 1 / speed factor?" closed="true" >}}
1 / 0.7578 = 1.3196, but the runs give 1.3174. The evacuation time comes
from the full JuPedSim run, not from distance divided by speed. Time that does
not scale with the speed, such as the agent's start-up, makes the two differ
slightly.
{{< /details >}}

## 5. Try it yourself

Before running another simulation, explore what the smoke-speed model
predicts when the extinction coefficient changes.

{{< smoke-speed-experiment k="3" min-k="0" max-k="5" step="0.1" >}}

### Try this

Set *K* = 1.0 1/m. Before running the simulation, ask yourself:

- Is the visibility higher or lower?
- Is the speed factor higher or lower?
- Should the evacuation be faster or slower than with *K* = 3.0 1/m?

{{< details title="Show the expected trend" closed="true" >}}
With less extinction, the visibility increases and the speed factor moves
closer to 1. The evacuation should therefore be faster than in the
*K* = 3.0 1/m case. The exact evacuation time still has to come from the
simulation.
{{< /details >}}

To check, change one line of `examples/quickstart.py`:

```text
K_PER_M = 1.0
```

and run the example again:

```bash
uv run python examples/quickstart.py
```

## 6. Find the run manifest

```python
print(f"manifest: {smoky.manifest_file}")
```

{{< checkpoint title="Manifest written" >}}
```text
manifest: /tmp/tmp_3v2ol2t.manifest.json
```

The path is a new temporary file on every run. Each run writes a manifest
next to its trajectory file. It records enough to identify how the run was
produced.
{{< /checkpoint >}}

{{< details title="What does the manifest record?" closed="true" >}}
- the versions of pyFDS-Evac, JuPedSim, fdsreader and fdsvismap;
- the `uv.lock` hash;
- the git commit and whether the working tree had uncommitted changes;
- the random seed;
- the scenario path;
- the FDS directory and FDS version.

The FDS directory and version are `null` here, because no FDS output was read.
`run_scenario` writes the trajectory to a temporary SQLite file and the
manifest next to it, as `<trajectory stem>.manifest.json`.
{{< /details >}}

## 7. Clean up

```python
clear.cleanup()
smoky.cleanup()
```

This deletes the temporary trajectory files and their manifests. Copy them
before calling `cleanup()` if you want to keep them.

{{< checkpoint title="You completed the quickstart" >}}
You have:

- run one evacuation in clear air;
- run the same evacuation in smoke;
- seen a smoke speed factor of about 0.758;
- seen the evacuation time increase from about 79 s to about 104 s;
- explored how *K* changes the visibility and the walking speed;
- found the run manifest.
{{< /checkpoint >}}

If the smoke run is not slower, check that you passed `smoke_speed_model=`.
Without it, `run_scenario` models no smoke.

## Next step

Use real FDS output instead of a prescribed uniform smoke field:

{{< cards >}}
  {{< card link="../walkthrough/" title="Real-FDS walkthrough →" subtitle="Extinction and toxic gases read from FDS slices, and how to spot a run that succeeds but is wrong." >}}
{{< /cards >}}

Also:

- [A crowd in a real fire](first-fds-case.md): 150 agents in a 2 MW FDS fire,
  with figures for every step.
- [What your FDS case must provide](fds-case-requirements.md), before you
  point the tool at your own FDS output.
- [How do I get RSET with its spread from an ensemble of seeds?](howto-rset-ensemble.md)
- [Smoke-speed model](/models/smoke-speed.md): the speed laws and their
  parameters.

pyFDS-Evac is research software, provided without warranty.
