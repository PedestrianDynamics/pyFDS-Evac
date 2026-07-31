# Per-particle avatar rotation repro for Smokeview 6.10.x

A minimal FDS case (20 s, no fire, no smoke, four stub walls around a
10 × 10 × 3 m mesh) plus a hand-generated `.prt5` with three agents
walking concentric circles.

The custom AVATARDEF in `repro.svo` is `agent_arrow` — a blue body
sphere with a small red marker offset in the body's local +X — and
declares `:AZIMUTH=0` in its header plus `$AZIMUTH rotatez` at the
top of its draw program. In a 2017-era FDS+Evac + Smokeview setup
this chain rotated each avatar to face its direction of travel.

## Run

```bash
smokeview repro.smv
```

In the GUI:

1. **Load** → **Particles** → **Human**
2. Press **▶** on the time bar.

## Expected vs observed

- **Expected:** each agent's red marker orbits around its body as
  the agent walks the circle (marker points along the instantaneous
  velocity tangent).
- **Observed (SMV-6.10.1-0-gfe486ab05, macOS):** every red marker
  is rigidly offset in world `+X` for every agent and every frame.
  `$AZIMUTH rotatez` is evidently not substituted from per-particle
  data.

## A note on `numtypes=0` vs `numtypes>0`

This repro ships the PRT5 with `numtypes = (0, 0)` — no quantity
columns at all. That is *not* how I originally exported it; the
JuPedSim pipeline writes `numtypes = (1, 0)` with an `AZIMUTH` (deg)
quantity per particle, computed as `atan2(ori_y, ori_x) mod 360`.

I stripped it for the repro because **`CreatePartBoundFile` in
`smokeview/IOpart.c` has a secondary bug that breaks playback for
any PRT5 with `numtypes > 0`:**

- Line 1019 uses `FORTREAD_mv` → `fread_mv` to read the per-particle
  quantity record.
- `fread_mv` (`shared/stdio_m.c:186`) immediately returns `0`
  whenever `stream->stream != NULL`, which is always the case when
  `fopen_b` was called with `buffer == NULL` (the file-backed path
  at `fopen_b` L120–126).
- `count_read` therefore ends up `0`, `!= nparts_local * numtypes`,
  and the scanner hits `goto wrapup` at L1020 after only the first
  frame. The resulting `.bnd` has one line, the derived `.sz` has
  one entry, and `parti->ntimes = 1` → playback stops after frame 0.

With `numtypes = 0`, `CreatePartBoundFile` skips the `fread_mv` call
(gated by `if(numtypes_local[2*jj]>0)` at L1018) and scans the whole
file correctly, yielding a 404-line `.bnd` for the 202 frames in
this case.

Dropping the quantity is therefore both a workaround for the repro
and a way to isolate the rotation question from that bounds-scanner
bug.

## Files

| file | contents |
|---|---|
| `repro.fds` | 20 s FDS input — 10 × 10 × 3 m mesh, four 1 m stub walls, no fire |
| `repro.smv` | FDS-produced `.smv` with our `PROP` + `CLASS_OF_PARTICLES` + `PRT5` block appended |
| `repro_agents.prt5` (+ `.bnd`, `.sz`) | standard 3-float XYZ PRT5, `numtypes=(0,0)`, 202 frames |
| `repro.svo` | custom AVATARDEF `agent_arrow` declaring `:AZIMUTH=0` and using `$AZIMUTH rotatez` |
| `repro.ini` | sets `partclassdataVIS=4` so particles render as SVO avatars on first launch |

To regenerate without rerunning FDS:

```bash
uv run python ../build_repro.py
```
