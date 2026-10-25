# ISO 20414 Test 16 with FDS smoke (#850)

ISO 20414:2020 Test 16 (Table 18) asks whether an occupant affiliated with exit
2 uses it more than an unfamiliar one. The synthetic test
`tests/test_iso_test_16_familiar_exit.py` fills the east of the room and the
door strip of exit 2 with a static extinction coefficient K and measures how
three occupants react. This asset puts the same box into five FDS decks, so the
extinction reaches the router through the FDS slice reader and the sampler.

**Question.** Do the three occupants take the same exits when K comes from an
FDS slice as when it comes from the synthetic box?

- A: `discovery` with `entrance: "exit_2"` (the ISO 16 sub-model). It knows
  exit 2 only and walks through any smoke.
- B: full familiarity and a journey to exit 2 with `allocation: "preference"`.
  The allocation yields when the exit-2 route is dirtier than exit 1's by more
  than the deadband.
- C: full familiarity, no journey. It takes the cheapest known exit, exit 1.

With the route through the box L = 4.5 m long, the hand values are tau₂ = K × 4.5
against the refusal limit 6 and the deadband 0.6 (K = 0.13 /m).

## What the FDS variant covers

The box is there from t = 0 in the synthetic test and in FDS, so there is no
limit of its own. The decks are K = 0.05, 0.5 and 3 /m (the three levels of the
synthetic test) and K = 0.10 and 0.20 /m (below and above the deadband).

Tests 9 and 11 have no FDS variant. Test 9 needs the exit to become unavailable
after 1 s, and an `&INIT` acts at t = 0 only. Test 11's field is uniform and
constant, which `assets/iso_table21_coupled` already checks from committed
output.

## Files

| File | Purpose |
|------|---------|
| `build_geometry.py` | Writes the decks, `config.json` and `geometry.wkt`. |
| `iso_test_16_fire_k0p05.fds`, `_k0p10`, `_k0p20`, `_k0p5`, `_k3` | FDS decks; the suffix is K in 1/m with `p` for the decimal point. |
| `config.json` | Occupant A at seed 1, for `run.py`. |
| `geometry.wkt` | The walkable area. |

Regenerate with `cd assets/iso_test_16_fire && python build_geometry.py`; the
output is byte-identical to the committed files.

## Deck rules

- Mesh `IJK=48,60,6` over `XB=-1.0,11.0,0.0,15.0,0.0,3.0` (0.25 × 0.25 × 0.5 m);
  x = 6.0 m is a cell face.
- One `&INIT` over `XB=6.0,11.0,0.0,15.0,0.0,3.0`, the full height and the exit-2
  strip. Its soot mass fraction is `K × 9.5893E-05` (8700 m²/kg), and its
  temperature is the one at which the soot does not change the density, so the
  gas stays still (4 decimals).
- The OXYGEN species carries `MASS_FRACTION_0=0.231`. FDS defaults the ambient
  oxygen to 0, which gives a density contrast outside the box and a gravity
  current within seconds.
- No obstructions: the walls live in `geometry.wkt`. `T_END=70`, `DT_SLCF=5`.
- Two slices of `EXTINCTION COEFFICIENT` with `SPEC_ID='SOOT'` at 2.0 m and
  1.6 m; FDS snaps 1.6 m to the 1.5 m face, which pyFDS-Evac reads by default.

## Run FDS

There is one mesh, so no MPI. Run outside the sync folder, then copy:

```bash
SCIEBO="$HOME/sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
REPO=/path/to/pyFDS-Evac   # checkout that holds this asset
A=iso_test_16_fire
ls "$REPO"/assets/$A/${A}_k*.fds > /dev/null || exit 1   # stop if REPO is wrong
for DECK in "$REPO"/assets/$A/${A}_k*.fds; do
  CHID=$(basename "$DECK" .fds); K=${CHID#${A}_}
  RUN=/tmp/fds850/$A/$K; mkdir -p "$RUN"; cp "$DECK" "$RUN"/
  (cd "$RUN" && OMP_NUM_THREADS=1 /Applications/FDS/FDS6/bin/fds "$CHID.fds" &&
    grep -q "FDS completed successfully" "$CHID.out") || { echo "FDS failed: $CHID"; continue; }
  mkdir -p "$SCIEBO/fds-evac-data/$A/$K"; cp "$RUN"/* "$SCIEBO/fds-evac-data/$A/$K/"
done
```

The subdirectories are `k0p05`, `k0p10`, `k0p20`, `k0p5` and `k3`. Each deck
takes under a minute and writes about 0.3 MB; the output goes to the data store
and is never committed. Check `<CHID>.out` for the FDS revision (6.10.1) and
for SOOT W = 12.011.

The tests read `$ISO_TEST_16_FIRE_FDS`, which defaults to
`$SCIEBO/fds-evac-data/iso_test_16_fire`, and skip when
`<root>/<k>/<CHID>.smv` is absent:

```bash
.venv/bin/python -m pytest -q tests/test_iso_test_16_fire.py
```
