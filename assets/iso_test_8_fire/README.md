# ISO 20414 Test 8 with FDS smoke (#850)

ISO 20414:2020 Test 8 (Table 9) allocates the occupants of a corridor with
rooms to a main and a secondary exit. The synthetic test
`tests/test_iso_test_8_route_allocation.py` puts a box of extinction in the
main passage. This asset puts the same box into an FDS deck, so the extinction
reaches the router through the FDS slice reader and the sampler.

**Question.** Does the allocation behave the same when the smoke comes from an
FDS slice as when it comes from the synthetic box?

## What the FDS variant covers

The soot box is set by an `&INIT`, which acts at t = 0. The smoke is therefore
there when the occupants spawn. The variant covers:

- the preference allocation yields at spawn: every main-allocated occupant
  switches to the secondary exit with `allocation_preference` at t = 0, at
  K = 5 /m (`k5`) and at K = 1 /m (`k1`);
- the hard allocation holds: no route row, the smoke is walked at the reduced
  speed and the run ends later than in clear air;
- the foresight setting (`anticipate`) gives the preference result.

It does not cover the 5 s onset, the before/inside/past groups or the 1.255 m
threshold of the synthetic test. Those stay synthetic-only.

Tests 9 and 11 have no FDS variant. Test 9 needs the exit to become unavailable
after 1 s, and an `&INIT` acts at t = 0 only. Test 11's field is uniform and
constant, which `assets/iso_table21_coupled` already checks from committed
output.

## Files

| File | Purpose |
|------|---------|
| `build_geometry.py` | Writes the decks, `config.json` and `geometry.wkt`. |
| `iso_test_8_fire_k5.fds`, `iso_test_8_fire_k1.fds` | FDS decks, K = 5 and 1 /m. |
| `config.json` | The preference variant of the scenario, for `run.py`. |
| `geometry.wkt` | The walkable area. |

Regenerate with `cd assets/iso_test_8_fire && python build_geometry.py`; the
output is byte-identical to the committed files.

## Deck rules

- Mesh `IJK=95,51,6` over `XB=-10.0,9.0,-4.7,5.5,0.0,3.0` (0.2 × 0.2 × 0.5 m).
  y = 0.3 m and y = 2.3 m fall on cell faces and set L = 2.0 m.
- One `&INIT` over `XB=-4.0,-2.6,0.3,2.3,0.0,3.0`: the synthetic box widened in
  x into the wall thickness, so x is grid-aligned and the edge smear falls
  outside the 1.1 m passage. Its soot mass fraction is `K × 9.5893E-05`
  (8700 m²/kg), and its temperature is the one at which the soot does not
  change the density, so the gas stays still (4 decimals).
- The OXYGEN species carries `MASS_FRACTION_0=0.231`. FDS defaults the ambient
  oxygen to 0, which gives a density contrast outside the box and a gravity
  current within seconds.
- No obstructions: the walls live in `geometry.wkt`.
- `T_END=0.1`, `DT_SLCF=0.1`: the deck is frozen at t = 0. Nothing in FDS holds
  the soot in the box, and it mixes out through the two ends that cross the
  passage (one cell inside them, K is 11 % low at 10 s and 19 % low at 20 s,
  FDS 6.10.1). The run holds the 0.1 s frame, as the synthetic box holds its
  value: pass `--allow-fds-horizon-hold` to `run.py`.
- Two slices of `EXTINCTION COEFFICIENT` with `SPEC_ID='SOOT'` at 2.0 m and
  1.6 m; FDS snaps 1.6 m to the 1.5 m face, which pyFDS-Evac reads by default.

## Run FDS

There is one mesh, so no MPI. Run outside the sync folder, then copy:

```bash
SCIEBO="$HOME/sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
REPO=/path/to/pyFDS-Evac   # checkout that holds this asset
A=iso_test_8_fire
ls "$REPO"/assets/$A/${A}_k*.fds > /dev/null || exit 1   # stop if REPO is wrong
for DECK in "$REPO"/assets/$A/${A}_k*.fds; do
  CHID=$(basename "$DECK" .fds); K=${CHID#${A}_}
  RUN=/tmp/fds850/$A/$K; mkdir -p "$RUN"; cp "$DECK" "$RUN"/
  (cd "$RUN" && OMP_NUM_THREADS=1 /Applications/FDS/FDS6/bin/fds "$CHID.fds" &&
    grep -q "FDS completed successfully" "$CHID.out") || { echo "FDS failed: $CHID"; continue; }
  mkdir -p "$SCIEBO/fds-evac-data/$A/$K"; cp "$RUN"/* "$SCIEBO/fds-evac-data/$A/$K/"
done
```

The subdirectories are `k5` and `k1`. Each deck takes a few seconds and
writes well under 1 MB; the output goes to the data store and is never committed.
Check `<CHID>.out` for the FDS revision (6.10.1) and for SOOT W = 12.011.

The tests read `$ISO_TEST_8_FIRE_FDS`, which defaults to
`$SCIEBO/fds-evac-data/iso_test_8_fire`, and skip when
`<root>/<k>/<CHID>.smv` is absent:

```bash
.venv/bin/python -m pytest -q tests/test_iso_test_8_fire.py
```
