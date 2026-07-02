# Record of upstream Smokeview issue #2597

**Filed:** 2026-04-22 as
[firemodels/smv#2597 — "Per-particle avatar rotation via PRT5"](https://github.com/firemodels/smv/issues/2597).

**Status:** answered. Glenn Forney confirmed per-particle rotation
is not supported by current Smokeview; the evac visualization code
was removed when `&EVAC` left FDS. Reviving it would require adding
AZIMUTH as an FDS particle quantity type.

**Takeaway for this repo:** our exporter defaults `--smv-with-azimuth`
off and `--smv-avatar-style` to `human`. The minimal repro attached
to the issue lives at [`smv-repro/case/`](smv-repro/case/) with a
regenerator script at [`smv-repro/build_repro.py`](smv-repro/build_repro.py).

The remainder of this file is the text of the issue as posted,
kept verbatim so the source-level pointers we traced, the
`evac.f90::DUMP_EVAC` excerpt, and the `fread_mv` secondary
finding stay searchable inside the repo even if the upstream
issue is later edited, archived, or moved.

---

## Context

I'm bringing a JuPedSim pedestrian-evacuation simulation into
Smokeview by emitting a `.prt5` stream next to the FDS output and
appending a `PROP` + `CLASS_OF_PARTICLES` + `PRT5` block to the case
`.smv`. The agents are post-processing artefacts — no FDS `&PART`
is involved.

For each frame I write per-particle `XYZ`, `tags`, and one float
quantity whose shortlabel is `AZIMUTH` (degrees in `[0, 360)`)
computed as `atan2(ori_y, ori_x)` from the JuPedSim trajectory. I
ship a per-case `<CHID>.svo` with a custom AVATARDEF that declares
`:AZIMUTH=0` in its header and applies `$AZIMUTH rotatez` at the top
of its draw program.

Smokeview version:

```
SMV-6.10.1-0-gfe486ab05-release (Apr 4 2025, OSX64)
```

`smokeview -info` confirms both the global `objects.svo` and my
per-case `demo.svo` are loaded:

```
objects.svo      : /Applications/FDS/FDS6/smvbin/objects.svo
67 object definitions read from /Applications/FDS/FDS6/smvbin/objects.svo
1 object definitions read from fds_data/demo/demo.svo
```

## What works

- The custom AVATARDEF is picked up (shape is my custom geometry, not
  the `missing_device` fallback).
- Agents stand on the floor (z=0).
- With a minimal "arrow" AVATARDEF (body sphere + red directional
  marker) sized via `1.0 scaleauto`, agents render at the expected
  size in a 30 × 13 × 3 m scene.
- When I write the PRT5 with a per-particle AZIMUTH (deg) quantity,
  the column is successfully ingested: the quantity appears on the
  colorbar menu with the correct 0–360° range, particles colour by
  heading as expected, and I can independently verify by parsing the
  PRT5 with a separate reader that the values vary sensibly over
  time. (That variant also triggers the separate bounds-scanner bug
  described in "Secondary finding" below, which is why the attached
  repro ships a `numtypes=0` PRT5 instead.)

## What doesn't work: per-particle rotation

Despite the AZIMUTH column being present and varying, **every agent
faces the same direction**. In the "arrow" avatar the red marker is
rigidly offset in the same world-space direction for every particle
and every frame, regardless of AZIMUTH.

## What I've traced in the source

I read the current `master` of `firemodels/smv` locally. The
per-particle quantity → AVATARDEF token substitution chain *looks
like* it should work:

1. `readobject.c::UpdatePartClassDepend` walks the class's quantity
   shortlabels (`partclassi->vars_dep[i]`) and resolves each to a
   token index via `GetObjectFrameTokenLoc(shortlabel, obj_frame)`.
   For my class that successfully returns the index of the
   `:AZIMUTH=0` symbol in my AVATARDEF.
2. At render time, `smokeview/IOobjects.c` around L4164–4173 copies
   `prop->fvars_dep[i]` into `framei->tokens[vars_dep_index[i]].var`
   — which is exactly what `$AZIMUTH rotatez` should consume.

On the other hand, `readsmvfile.c::GetLabels` sets `col_azimuth` when
it sees an `AZIMUTH` quantity shortlabel, but `rg col_azimuth` across
the whole tree returns only the two assignments in `readsmvfile.c` —
no reader, no consumer. And `IOpart.c:366` applies the rotation from
a **class-level scalar** (`partclassbase->azimuth`, populated from a
`DEVICE` line only, never per-particle):

```c
glRotatef(datacopy->partclassbase->azimuth, 0.0, 0.0, 1.0);
```

## Why I think this path is incomplete

Looking at the old `fds-smv_deprecated` repo, `FDS_Source/evac.f90::DUMP_EVAC`
used a **different PRT5 binary layout** — seven floats per particle in
the `XYZ` Fortran record, not three:

```fortran
! fds-smv_deprecated/FDS_Source/evac.f90:14970-14971
WRITE(LU_PART(NM)) (XP(I),I=1,NPLIM),(YP(I),I=1,NPLIM),(ZP(I),I=1,NPLIM), &
     (AP(I,1),I=1,NPLIM),(AP(I,2),I=1,NPLIM),(AP(I,3),I=1,NPLIM),(AP(I,4),I=1,NPLIM)
```

where

| column | content |
|---|---|
| `AP(:,1)` | body angle in degrees (`180·HR%Angle/π`) — drives rotation |
| `AP(:,2)` | body diameter = `2·HR%Radius` |
| `AP(:,3)` | torso diameter = `2·HR%r_torso` |
| `AP(:,4)` | height scale = `1.80·HR%Radius/0.27` |

And the matching `.smv` block was `CLASS_OF_HUMANS`, not
`CLASS_OF_PARTICLES`. Both sides of that mechanism have been removed:

- Current Smokeview: `grep -r CLASS_OF_HUMANS Source/` returns
  nothing, and `IOpart.c:17` defines `NXYZ_COMP_PART 3` — the XYZ
  record is strictly 3 floats per particle.
- Current FDS: `Source/dump.f90::DUMP_PART` writes the standard
  3-float XYZ layout only; `&EVAC` is gone.

So the Ralph-Siu-2017 FDS+Evac videos (where avatars visibly turn to
face their direction of travel) apparently relied on a path that no
longer exists at either end.

## Questions

1. **Is per-particle avatar rotation supported at all in current
   Smokeview's PRT5 path?** If the substitution chain through
   `UpdatePartClassDepend` / `vars_dep_index` / `fvars_dep` *was*
   meant to replace the removed `CLASS_OF_HUMANS` reader, what am I
   missing in my PRT5 / SMV text / AVATARDEF to make it actually rotate
   the figure?

2. **If it's not supported**, is the recommended path to:
   - (a) restore/port the FDS+Evac 7-float-XYZ layout into an
     extension of the PRT5 reader,
   - (b) add a new per-particle AZIMUTH pipeline in `IOpart.c` (e.g.
     honour `col_azimuth` in the draw loop),
   - or (c) something else I haven't seen?

3. Orthogonally — is the `col_azimuth` field in `partclassdata` dead
   code (never consumed anywhere in the tree)? If so, would a PR that
   either wires it up or removes it be welcome?

## Secondary finding: `CreatePartBoundFile` breaks on `numtypes > 0`

While reducing the repro I hit a separate bug that's likely worth a
bug report on its own — I'll open a GitHub issue for this if it
doesn't turn out to be known / already fixed on `master`.

In `smokeview/IOpart.c::CreatePartBoundFile` around L1018–1020:

```c
if(numtypes_local[2*jj]>0){
    FORTREAD_mv((void **)&rvals_local, 4,
                nparts_local*numtypes_local[2*jj], stream);
    if(count_read != nparts_local * numtypes_local[2 * jj])goto wrapup;
}
```

`FORTREAD_mv` expands to `fread_mv`, which in `shared/stdio_m.c:186`
is:

```c
size_t fread_mv(void **ptr, size_t size, size_t nmemb, FILE_m *stream_m){
  if(stream_m->stream != NULL) return 0;   // ← fails on file-backed streams
  *ptr = stream_m->buffer;
  stream_m->buffer += size*nmemb;
  return nmemb;
}
```

`CreatePartBoundFile` opens the PRT5 via `fopen_b(file, NULL, 0, "rb")`
(`IOpart.c:963`), which takes the file-backed path at `fopen_b`
L120–126 and sets `stream_m->stream = FOPEN(...)`. Every `fread_mv`
call on that stream immediately returns 0, so on the very first
frame with `numtypes > 0` the function hits `goto wrapup` and
writes a `.bnd` containing just that single frame.

The derived `.sz` file therefore also has one entry, and
`GetSizeFileAll` at `IOpart.c:1706–1741` reports `parti->ntimes = 1`.
`MergeGlobalTimes` at L1282 then contributes a single time point to
`global_times`, and the result is a stuck playback like the one I
originally hit — and what prompted me to drop the AZIMUTH quantity
from the repro attached above. With `numtypes = 0` the scanner
skips the `FORTREAD_mv` call (gated on `if(numtypes_local[2*jj]>0)`)
and walks the file correctly, yielding a 404-line `.bnd` / `.sz`
for the 202 frames in the repro case.

The main particle loader (`GetPartData`, L1226) uses a different
stream opened by `fopen_m(..., "rbm")` (memory-mapped), where the
`stream_m->stream == NULL` branch of `fread_mv` is taken and reads
succeed — so actual particle rendering works. The bounds/size
cache, which only `CreatePartBoundFile` writes, is what's broken.

Fix (I think): either extend `fread_mv` to handle the file-backed
stream case the same way `fread_m` does (`stdio_m.c:162–176`), or
change `CreatePartBoundFile` to open via `fopen_m(..., "rbm")` so
both branches stay consistent. I can open a PR for whichever you
prefer.

## Minimal repro

Attached (`repro.zip`, ~12 KB):

| file | contents |
|---|---|
| `repro.fds` | 20-second FDS input — 10 × 10 × 3 m mesh, four 1 m stub walls around the perimeter, no fire, no smoke. One `fds repro.fds` invocation produces the supporting `repro.smv`. |
| `repro.smv` | FDS-produced `.smv` with our `PROP` + `CLASS_OF_PARTICLES` + `PRT5` block appended. |
| `repro_agents.prt5` | standard 3-float XYZ PRT5, `numtypes=(0,0)` (**no quantity column** — see note below), 202 frames. Smokeview rebuilds `.bnd`/`.sz` bounds/size caches on first load. |
| `repro.svo` | custom AVATARDEF `agent_arrow` declaring `:AZIMUTH=0` and using `$AZIMUTH rotatez` — a body sphere plus a small red directional marker offset in local +X. |
| `repro.ini` | sets `partclassdataVIS=4` so particles render as SVO avatars on first launch. |
| `README.md` | run instructions + expected vs observed. |

Three agents walk concentric circles around `(5, 5)` with different
angular velocities. If per-particle rotation worked, the red marker
on each agent would orbit around the body as it walks the circle
(tangent-following). In `SMV-6.10.1-0-gfe486ab05-release` the marker
is rigidly offset in world `+X` for every agent and every frame.

**Why the attached PRT5 has no quantity column:** my production
exporter computes `AZIMUTH = atan2(ori_y, ori_x) mod 360` per particle
and emits it as a `numtypes=(1,0)` PRT5, which is the natural input
for the `$AZIMUTH rotatez` substitution path I'm asking about. But
that triggers the bounds-scanner bug documented in "Secondary finding"
above — Smokeview's derived `.sz` cache ends up with one entry and
playback sticks on frame 0. To isolate the rotation question from
that bug, I regenerated the attached PRT5 with `numtypes=(0,0)` so
the scanner walks the full file and playback runs through all 20 s.
With no quantity, `$AZIMUTH rotatez` just evaluates to its
`:AZIMUTH=0` default — which is exactly what I *already observed*
with the `numtypes=1` variant anyway, so the visible behaviour of
the attached case is the same as the original, minus the stuck
playback. If you prefer to look at the `numtypes=1` variant, run
`python docs/smv-repro/build_repro.py --with-azimuth` (from the
pyFDS-Evac repo) to regenerate the case with the quantity column.

Steps:

```bash
unzip repro.zip && cd case
smokeview repro.smv
# Load → Particles → Human → ▶
```

The exporter is open-source at [link to pyFDS-Evac repo];
`pyfds_evac/core/smv_export.py` is the entire output path, and
`docs/smv-repro/build_repro.py` produced the attached case (plus
one invocation of `fds repro.fds` to generate the supporting SMV).

Thanks — happy to contribute a PR or a documentation patch once the
intended mechanism is clear.

---

## Notes (not for the post)

- Size was a red herring. My first draft worried about a double
  `SCALE2SMV` in `IOpart.c` making avatars 1/30 of expected. In fact
  `--smv-avatar-style arrow/sphere` (small AVATARDEFs using the
  standard `scaleauto` idiom like stock `sensor` / `sprinkler_*`)
  render at the expected size. The ~10 cm humans came from the
  compounded `0.579 × 0.3 × SX` chain we inherited from
  `human_altered_with_data`; dropping that fixes size independently
  of the rotation question. So keep the forum post focused on
  rotation only.
- Make sure to paste the `evac.f90:DUMP_EVAC` excerpt in the post —
  it's the strongest evidence that the PRT5 rotation mechanism that
  used to work was genuinely different from what's in master today.
- Include the `smokeview -info` output (proves `.svo` loaded) and a
  hex/Python dump of two frames' worth of AZIMUTH values (proves the
  exporter isn't writing zeros). Front-loads the "yes we checked"
  before anyone asks.
