# Smokeview avatars: how `--smv-export` renders humanoid figures

When you run

```bash
uv run python run.py --scenario ... --fds-dir fds_data/demo --smv-export
```

Smokeview renders the exported agents as tan-headed, blue-trunked
humanoid figures (matching the look of the original FDS+Evac
visualisations), not as point clouds. This page documents the
mechanism, the binary format, and the SMV text blocks we emit.

## The two things Smokeview needs

1. **A `.prt5` binary** with agent positions per frame. Smokeview
   already knows how to read this — it's the same Lagrangian particle
   file format FDS writes for droplet/soot particles.
2. **An SMV text block** that binds the particle class to an avatar
   drawing recipe from `objects.svo` (shipped alongside Smokeview).

The avatar geometry itself is entirely Smokeview's concern. We don't
ship any mesh or texture; we just name which `AVATARDEF` to use.

## The avatar recipe lives in `objects.svo`

Smokeview's `objects.svo` contains a block marked
`// avatar object definitions` with, among others, an `AVATARDEF`
called `human_fixed`:

```text
AVATARDEF
 human_fixed
 :DUM1 :DUM2 :DUM3 :W :D=0.1 :H1 :SX :SY :SZ :R=0 :G=0 :B=0 :HX :HY :HZ
 90.0 rotatez
 "TAN" setcolor                          // head
 0.3 0.3 0.3 scalexyz
 push  0.0 0.0 5.2 translate 1.1 drawsphere
   "BLUE" setcolor
   push -0.25 -0.4 0.05 translate 0.2 drawsphere pop   // eye
   push  0.25 -0.4 0.05 translate 0.2 drawsphere pop   // eye
 pop
 28 64 140 setrgb                        // trunk color
 push 0.0 0.0 3.55 translate 0.5 0.3 1.0 scalexyz 2.5 drawsphere pop
 ...
 39 64 139 setrgb                        // ROYAL BLUE 4 legs
 ...
```

That's the full figure: a tan head sphere with two small blue eye
spheres, a blue trunk sphere, two tan arm spheres, two Royal-Blue-4
leg spheres. No external mesh asset. Other avatars available in the
shipped `objects.svo` are `human_altered_with_data`, `ellipsoid`,
`disk`, `fire_fighter`, and `fire_fighter_with_gear`.

## How our SMV block binds the class to `human_fixed`

`pyfds_evac/core/smv_export.py::patch_smv_file` appends two blocks
to the `.smv`:

```text
PROP
 Human_props
  2
 human_fixed
 ellipsoid
  1
 D=0.2

CLASS_OF_PARTICLES
 Human % % Human_props
      0.10000      0.40000      0.90000
  0
PRT5     1
 demo_agents.prt5
      1
      1
```

Why this works, step by step, based on Smokeview's own parser in
`Source/shared/readsmvfile.c`:

1. Smokeview reads `CLASS_OF_PARTICLES`, then the next line, and splits
   it on `%` via `GetLabels(buffer, &device_ptr, &prop_id)`. For
   `Human % % Human_props` this yields `tok0="Human"`, `tok1=""`
   (trimmed to NULL), `tok2="Human_props"`. So `device_ptr=NULL` and
   `prop_id="Human_props"`.
2. On a second pass Smokeview runs
   `partclassi->prop = GetPropID(scase, "Human_props")`, resolving the
   class to the `PROP` block of the same ID.
3. The `PROP` lists candidate SVO avatar names (`human_fixed`,
   `ellipsoid`). Smokeview picks one (the user can switch between
   them at runtime) and uses its `AVATARDEF` draw program to render
   each particle.
4. `CLASS_OF_PARTICLES` must appear **before** `PRT5` in the file.
   Smokeview parses single-pass and crashes otherwise; the
   `test_patch_smv_idempotent` test asserts the ordering.

## The `.prt5` binary we write

We write the standard Smokeview PRT5 layout (little-endian,
FORTRAN-unformatted records of `[u32 len][payload][u32 len]`):

```text
Header (once)
    1:  int32  one              (= 1, endian flag)
    2:  int32  version          (= 600)
    3:  int32  n_classes        (= 1)
    4:  int32  numtypes[2]      (= 0, 0   — no quantities)

Per frame (skip frames with 0 agents mid-stream)
    1:  float32 time_s
    2:  int32   n_points
    3:  float32[3*N]  xyz       (column-major: all X, all Y, all Z)
    4:  int32[N]      tags      (per-agent labels)

Terminator
    final frame with n_points = 0
```

This is the minimum Smokeview's `IOpart.c::ReadPart` needs. The Z
coordinate is constant (`--smv-particle-z`, default 1.0 m) because
the JuPedSim trajectory is 2-D.

## Orientation: how avatars follow the walking direction

We emit one quantity column per particle with the shortlabel
`AZIMUTH`, computed as `atan2(ori_y, ori_x) · 180/π mod 360°` from
the JuPedSim trajectory SQLite's `ori_x, ori_y` columns. The
`CLASS_OF_PARTICLES` block declares it:

```text
CLASS_OF_PARTICLES
 Human % % Human_props
      0.10000      0.40000      0.90000
  1
 body angle
 AZIMUTH
 deg
...
```

Smokeview's `CLASS_OF_PARTICLES` parser recognises the `AZIMUTH`
shortlabel (`readsmvfile.c` L6314) and stores the column index in
`partclassi->col_azimuth`. When rendering each particle it rotates
the bound AVATARDEF by the per-particle azimuth so the figure faces
the walking direction.

The per-frame binary layout becomes XYZ record → tags record →
one additional Fortran record of `N` float32 azimuths. The PRT5
header's `numtypes[2]` is `(1, 0)`.

## What we still do not write

The original FDS+Evac writer `DUMP_EVAC` in
`fds-smv_deprecated/FDS_Source/evac.f90` packs **7 floats per
particle** into the XYZ record instead of 3:

```fortran
WRITE(LU_PART(NM)) (XP(I),I=1,NPLIM),(YP(I),I=1,NPLIM),(ZP(I),I=1,NPLIM), &
     (AP(I,1),I=1,NPLIM),(AP(I,2),I=1,NPLIM), &
     (AP(I,3),I=1,NPLIM),(AP(I,4),I=1,NPLIM)
```

where per particle:

| Extra column | Content |
|---|---|
| `AP(:,1)` | body angle in degrees (`180·HR%Angle/π`) — drives the `90.0 rotatez` in the AVATARDEF |
| `AP(:,2)` | body diameter = `2·HR%Radius` |
| `AP(:,3)` | torso diameter = `2·HR%r_torso` |
| `AP(:,4)` | height scale = `1.80·HR%Radius/0.27` |

FDS+Evac also writes a parallel `CLASS_OF_HUMANS` (not `CLASS_OF_PARTICLES`)
SMV block — a distinct keyword handled by a dedicated reader — and
optional extra-quantity records with `COLOR_INDEX`, `FED_DOSE`,
`SPEED`, `MOTIVE_ANGLE`, `DENSITY`, etc.

Our exporter now emits `AZIMUTH` (orientation, above) but still stops
short of:

- Per-agent body sizes. All avatars use the default `D=0.2` from the
  `PROP`; per-agent `HR%Radius` / `r_torso` / height are not wired up.
  Adding them means declaring `DIAMETER`, `LENGTH`, etc. as extra
  quantity columns.
- Per-agent FED / speed / colour index, which the FDS+Evac PRT5
  exposes in a second Fortran record so Smokeview can colour-map
  particles from the quantity menu.

Both would follow the same pattern as `AZIMUTH`: a shortlabel the
CLASS_OF_PARTICLES parser recognises, plus one extra float per agent
in the frame record.

## Enabling avatar rendering via the case `.ini`

Even with a correct `PROP` + `CLASS_OF_PARTICLES` binding, Smokeview
defaults `partclassi->vis_type` to `PART_POINTS` (enum value `1` in
`smv/Source/shared/datadefs.h`), so particles render as a point cloud
until the user toggles the mode. The override lives in the case
`.ini` under the `partclassdataVIS` keyword:

```text
partclassdataVIS
 1
 4
```

where the second number is the `vis_type` per class and `4` is
`PART_SMV_DEVICE` — render each particle by executing the bound
AVATARDEF program. `export_agents_to_smv` writes or patches
`<CHID>.ini` to set this automatically, so avatars are visible on
Smokeview's first launch without menu toggling.

## Re-running `--smv-export` after schema changes

`patch_smv_file` strips any prior `PROP` / `CLASS_OF_PARTICLES` /
`PRT5` blocks that reference the same `.prt5` basename before writing
the new ones. A stale `CLASS_OF_PARTICLES` with a different
`n_quantities` would desynchronise Smokeview's per-frame reader
(treating a quantity record as the next frame's XYZ) and segfault
Smokeview immediately on load. This regression was hit when `AZIMUTH`
was added: the old `.smv` still declared 0 quantities while the new
`.prt5` carried 1.

## Primary sources

- **SVO avatar definitions**:
  [`firemodels/smv` — `Build/for_bundle/objects.svo`](https://github.com/firemodels/smv/blob/master/Build/for_bundle/objects.svo),
  lines starting `AVATARDEF human_fixed`.
- **CLASS_OF_PARTICLES / PROP parser**:
  [`firemodels/smv` — `Source/shared/readsmvfile.c`](https://github.com/firemodels/smv/blob/master/Source/shared/readsmvfile.c),
  `GetLabels` (L1821), `GetPropID` (L1854), `CLASS_OF_PARTICLES` first
  pass (L6204), second pass (L7246), `PROP` block (L2039).
- **PRT5 binary reader**:
  [`firemodels/smv` — `Source/smokeview/IOpart.c`](https://github.com/firemodels/smv/blob/master/Source/smokeview/IOpart.c),
  `NXYZ_COMP_PART=3` (L17), frame read (L1295–1345).
- **Original FDS+Evac writer**:
  [`firemodels/fds-smv_deprecated` — `FDS_Source/evac.f90`](https://github.com/firemodels/fds-smv_deprecated/blob/master/FDS_Source/evac.f90),
  `DUMP_EVAC` at L14797.
- **Original FDS+Evac `.smv` emission** (including the `PROP` listing
  of `human_fixed`, `human_altered_with_data`, `ellipsoid`, `disk`):
  [`firemodels/fds-smv_deprecated` — `FDS_Source/dump.f90`](https://github.com/firemodels/fds-smv_deprecated/blob/master/FDS_Source/dump.f90),
  `EVAC_ONLY_PROPS` block at L1780.
- **Smokeview User's Guide**:
  [NIST SP 1017-1](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1017-1.pdf),
  sections on PROP, CLASS_OF_PARTICLES, and avatar selection.
