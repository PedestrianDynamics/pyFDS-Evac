# What your FDS case must provide

Read this before pointing `--fds-dir` at a case for the first time.

**pyFDS-Evac never runs FDS.** It reads the output of a finished FDS run.
A deck written for some other purpose usually will not work as-is: it has to
be told to dump the specific slices this tool samples.

## The slices

```
&SLCF PBZ=2.0, QUANTITY='EXTINCTION COEFFICIENT' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /
&DUMP DT_SLCF=1.0 /
```

Nothing here is dumped by default. FDS writes only what the deck asks for.

For the default species (soot), FDS records the extinction-coefficient
slice internally as `SOOT EXTINCTION COEFFICIENT`, and that is the exact
quantity name `load_slice_sampler` looks up
([fds-sampling.md](fds-sampling.md)).

| Slice | Feeds | If absent |
|-------|-------|-----------|
| Extinction coefficient | smoke-speed, visibility gating, GUI smoke layer | `IndexError` when `--fds-dir` is given without `--constant-extinction` |
| CO, CO2, O2 | FED toxic dose | Skipped for that species |

`EXTINCTION` and `EXTINCTION COEFFICIENT` are two unrelated gas-phase output
quantities (FDS User Guide Table 22.4) — don't confuse them. `EXTINCTION`
(Sec. 22.10.29) is a combustion-suppression flag with no units: 0 if the
extinction routine did not prevent combustion, 1 if it did, -1 if there was
no fuel or oxidizer. `EXTINCTION COEFFICIENT` (Sec. 22.10.5) is the light
extinction coefficient K [1/m] that the smoke-speed model actually needs.
If your deck has `QUANTITY='EXTINCTION'` where you meant the extinction
coefficient, fix it to `QUANTITY='EXTINCTION COEFFICIENT'` and rerun FDS.

## Declaring a slice is not enough

The species also has to exist in the run. Under simple chemistry, `OXYGEN`,
`NITROGEN`, `WATER VAPOR` and `CARBON DIOXIDE` are always present, but
`CARBON MONOXIDE` only exists if `CO_YIELD` is set on `&REAC`, and `SOOT` only
if `SOOT_YIELD` is set. A plain `&REAC FUEL='PROPANE' /` cannot produce FED no
matter what `&SLCF` lines you add. Fix it at the source:

```
&REAC FUEL='CABLE_FUEL', C=3, H=5, O=0, N=1,
      SOOT_YIELD=0.172, CO_YIELD=0.063, HCN_YIELD=0.006,
      HEAT_OF_COMBUSTION=16400 /
```

That is the `t_junction` reaction. Yields are fuel properties: take them from
your material's data rather than copying these.

## Failure modes

| Symptom | Cause |
|---------|-------|
| `IndexError: No slice with quantity 'SOOT EXTINCTION COEFFICIENT' found in <dir>` | The deck never declared `&SLCF QUANTITY='EXTINCTION COEFFICIENT'`, or the species was never tracked. |
| `ValueError: Point (x, y) is outside the sampled FDS slice domain` | Walkable area extends past the slice extent. |
