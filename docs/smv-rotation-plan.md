# Plan: enable per-particle avatar rotation in Smokeview

Goal: make `$AZIMUTH rotatez` inside a custom `AVATARDEF` receive the
per-particle float that the PRT5 quantity column already carries, so
agents turn to face their direction of travel.

Scope: patches to the local Smokeview source tree at `../smv/` on
branch `feat/per-particle-azimuth-rotation`. No changes to
`pyfds_evac/` beyond removing the `--smv-with-azimuth` workaround
once upstream works. Tracks
[firemodels/smv#2597](https://github.com/firemodels/smv/issues/2597).

## Known blockers (from `docs/smv-avatars.md`)

1. **`fread_mv` bounds-cache bug** — `Source/shared/stdio_m.c:186`
   early-returns 0 when `stream_m->stream != NULL`. Every
   `FORTREAD_mv` callsite that reads from a real file returns
   zero bytes. The bounds scanner
   `IOpart.c::CreatePartBoundFile` (L1017) therefore sees no
   quantity data, stops after frame 1, writes a 1-entry `.sz`,
   and `parti->ntimes` collapses to 1 — the time slider never
   advances. Symptom: PRT5 with any `numtypes > 0` plays one
   frame and freezes.

2. **Token substitution not firing** — `UpdatePartClassDepend`
   (`readobject.c:1668`) and the render-time copy at
   `IOobjects.c:4169` look correct on inspection, but in practice
   `$AZIMUTH rotatez` does not receive per-particle values.
   `agent_arrow`'s red marker stays in world +X for every agent.
   Needs a source-level trace to find where the chain breaks —
   candidates: (a) shortlabel lookup casing / whitespace,
   (b) `vars_dep` array not populated for single-quantity classes,
   (c) `fvars_dep` not refreshed per frame, (d) token `loc`
   resolved against the wrong frame.

## Approach

Fix (1) first — it's small, isolated, and without it we can't
observe whether (2) is solved. Then diagnose (2) empirically with
the repro case already staged in `docs/smv-repro/`.

### Phase 1 — unblock the bounds scanner

- Read `fread_mv` callers and `FILE_m` lifecycle in
  `shared/stdio_m.c` to confirm the intended contract: is the
  `stream != NULL` guard dead code, or was `fread_mv` meant for
  in-memory buffers only (with callers expected to use `fread_b`
  for real streams)?
- If `fread_mv` is meant to dispatch: replace the early-return
  with an `fread(*ptr, size, nmemb, stream_m->stream)` branch and
  verify it doesn't regress the buffer path.
- If `fread_mv` is strictly in-memory: fix the caller
  `CreatePartBoundFile` to use `fread_b` / `FORTREAD_b` on the
  quantity record instead of `FORTREAD_mv`.
- Build locally (`../smv/build-fork/`), rerun the
  `docs/smv-repro/` case with `--smv-with-azimuth`, confirm the
  time slider advances to the end of the PRT5.

### Phase 2 — make `$AZIMUTH rotatez` actually rotate

- Instrument `UpdatePartClassDepend` and the render-time copy in
  `IOobjects.c:4169–4173` with stderr prints of: the resolved
  `vars_dep_index`, the token the index points at, the float
  copied per particle per frame.
- Run the repro with `agent_arrow` and read the instrumentation:
  - If `vars_dep_index[0]` resolves to `-1` or the wrong token,
    fix `GetObjectFrameTokenLoc` / `:AZIMUTH` header declaration.
  - If the copy fires with a constant value, fix how
    `fvars_dep[i]` is refreshed per particle (trace back to
    where `GetPartData` fills `parti->data_frame[j]->rvals`).
  - If the copy fires with the right value but rotation is still
    wrong, the issue is in the draw-program interpreter at render
    time (`IOobjects.c` `rotatez` token handler).
- Visual check: `agent_arrow` marker points along velocity; the
  `human_rotating` figure faces its direction of travel.

### Phase 3 — upstream & post-processor cleanup

- Write regression test: minimal PRT5 with 2 agents, AZIMUTH
  values 0° and 90°, assert the `.sz` bounds cache has
  `ntimes == frames_written` and (where testable) that the
  substituted float in `fvars_dep` matches the input.
- Open PR against `firemodels/smv` referencing issue #2597.
- Once merged, drop `--smv-with-azimuth` from
  `pyfds_evac/core/smv_export.py` (make azimuth the default
  again) and update `docs/smv-avatars.md` to remove the
  "unsupported" warnings.

## Test case

`docs/smv-repro/` already contains a minimal reproducer (CHID
`repro`) with the three custom AVATARDEFs
(`human_rotating`, `agent_arrow`, `agent_sphere`) and a PRT5
carrying per-particle AZIMUTH. Use it as the build-verify
harness for each phase.

## Out of scope for this branch

- Adding AZIMUTH as an FDS particle quantity type (Glenn's
  suggested long-term fix). We're making Smokeview's existing
  PRT5-quantity path work; FDS-side changes are a separate
  effort.
- Per-agent body sizes, FED, speed, colour-index columns. Same
  substitution pipeline, but each is its own column and out of
  scope here.
