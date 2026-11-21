# b16: FDS decks for the C/VM2 ballroom study (#808)

**Nothing here has been run with FDS.** No FDS exists on the machine the
decks were written on. Every statement about what FDS 6.7.7 does comes from
reading its source and guides, not from a run. The first run is the test.

`make_decks.py` (standard library only) is the single source. It writes:

| Deck | CHID | `&MISC` | Run |
|---|---|---|---|
| `cvm2_ballroom_fire.fds` | `cvm2_ballroom_fire` | `NO_EVACUATION` | fire part only, the stand-alone fire test |
| `cvm2_ballroom_evac.fds` | `cvm2_ballroom` | `EVACUATION_INITIALIZATION` | phase 1: evacuation mesh only, a drill |
| `cvm2_ballroom_evac_fed.fds` | `cvm2_ballroom` | `EVACUATION_WRITE_FED` | phase 2: fire meshes only, the production fire run |
| `cvm2_ballroom_evac_mc.fds` | `cvm2_ballroom` | `EVACUATION_MC_MODE` | phase 3: evacuation in the fire, every repeat |
| `cvm2_ballroom_evac_dx050.fds` | `cvm2_ballroom_dx050` | `EVACUATION_INITIALIZATION` | phase 1 on the 0.5 m evacuation grid |

The three phase decks differ only in the `&MISC` line and its comment. The
fire lines are the same in all five. Regenerate with
`python3 make_decks.py`; `--t-end 10 --out DIR` writes short copies for a
syntax test.

## Sources read

- MBIE (2012), *Commentary for Verification Method C/VM2*, ISBN
  978-0-478-39942-4: printed pp. 40, 43, 49, 56, 88, 187, 190, 199, 202–205,
  228, as extracted text. Figures B1 and B2 could not be read as images;
  door positions are taken from the earlier study (below).
- FDS at tag `FDS6.7.7` (https://github.com/firemodels/fds/tree/FDS6.7.7):
  `Source/read.f90`, `Source/evac.f90`,
  `Manuals/FDS_User_Guide/FDS_User_Guide.tex`,
  `Manuals/FDS_Evacuation_Guide/FDS+EVAC_Guide.tex`. The guides were read
  as LaTeX, so they are cited by section, not by page.
- `$FDS_EVAC_DATA/cvm2-function-centre/` (README, `build/geometry.py`,
  `build/make_decks.py`) and `assets/schroeder2015_route/a047_cvm2_h40/`.

## What FDS 6.7.7 does differently from the plan in #808

1. **Fire and evacuation never run together.** FDS 6.7.7 carries Evac 2.6.1
   (`evac.f90` l. 88). A deck without an evacuation keyword on `&MISC` runs
   the fire only and skips every evacuation mesh (`read.f90` ll. 585–586,
   2204–2214). The calculation has three phases (guide, "Starting a FDS+Evac
   Calculation"; `read.f90` ll. 2194–2318):
   1. `EVACUATION_INITIALIZATION`: evacuation meshes only. Runs a drill and
      writes `CHID_evac.eff` (flow fields) and `CHID_evac.xyz`.
   2. `EVACUATION_WRITE_FED`: fire meshes only. Reads `CHID_evac.xyz`,
      writes the usual fire output and `CHID_evac.fed`. It stops if the
      `.xyz` file is missing.
   3. `EVACUATION_MC_MODE`: evacuation meshes only. Reads `.eff` and `.fed`.

   So "fire + FDS+Evac run 1, then nine repeats" becomes phase 1 once,
   phase 2 once, phase 3 ten times. The guide states that an evacuation run
   cannot use a fire run that had no evacuation meshes in its deck
   ("Updating an Existing FDS Input File"). **pyFDS-Evac must therefore
   read the slices of phase 2**, not those of `cvm2_ballroom_fire.fds`.
2. **Output names.** Phase 1 writes `cvm2_ballroom_evac.csv`; phase 3
   writes `cvm2_ballroom_evmc.csv` and `cvm2_ballroom_evmc_info.out`
   (`read.f90` ll. 2315–2317, `evac.f90` ll. 5441–5464). Each phase 3 run
   overwrites them: run each repeat in its own folder with copies of
   `cvm2_ballroom_evac.eff` and `.fed`, or rename the files after each run.
3. **No seed input.** The seed is `31*seconds + 29*milliseconds` of the
   wall clock (`evac.f90` ll. 5500–5507). `NOT_RANDOM=.TRUE.` on `&PERS`
   gives the fixed seed 2819. "Ten seeds" for FDS+Evac means ten runs
   started at different times; a run cannot be repeated by number.
4. **`FED_DOOR_CRIT` default.** −1000 at the tag (`evac.f90` l. 1525);
   −100 in the guide and in `materials/evac.f90` (Evac 2.6.0). The tag's
   file differs from `materials/evac.f90` in 466 lines. The deck writes the
   value out.
5. **`SMOKE_MIN_SPEED`.** In the code it is a speed in m/s; the factor is
   `SMOKE_MIN_SPEED_FACTOR`, default 0.1 (`evac.f90` ll. 2154–2156,
   8237–8241). The guide describes `SMOKE_MIN_SPEED` as the factor. The
   deck sets neither, so the floor is 0.1·v0.
6. **`FAC_DOOR_QUEUE` can be switched off** with exactly 0 (`evac.f90`
   ll. 9088, 10911, 16315; guide, `PERS`). A negative value selects another
   formula (l. 9093), so "less than 0.001" in the guide is not exact.

## Run order (unrun)

```
fds cvm2_ballroom_evac.fds                      # phase 1, one process
mpiexec -n 21 fds cvm2_ballroom_evac_fed.fds    # phase 2, same folder
fds cvm2_ballroom_evac_mc.fds                   # phase 3, ten times
pyfds-evac init cvm2_ballroom_evac.fds          # scenario for pyFDS-Evac
```

Phases 1 and 3 have one mesh and take one MPI process. Before phase 2,
look at phase 1 in Smokeview: flow fields toward all four exits, no agent
outside the walls, all agents placed.

## Values

Tags: **[P]** read from the Commentary (printed page); **[D]** the document
contradicts itself, the value used is stated; **[A]** assumed here.

| Item | Value | Tag | Source |
|---|---|---|---|
| Room | 20 × 50 m, ceiling 5 m; origin at the SW inner corner, x east | [P] | Fig. B1 p. 187; Table B1 p. 190 |
| Doors | 4 double doors, 2 in the east wall, 2 in the west; leaf 950 × 2,100 mm | [P] | pp. 190, 204 |
| Door width in BRANZFIRE | 1.60 m per double door; the hand calculation uses 2 × 0.95 m. 1.90 m is followed | [D] | Table B12 p. 228; p. 204 |
| Door centres | y 11.5 and 41.5 m on both walls: the earlier study's 31.5 and 61.5, shifted by −20 m | [P] ±1 m | Fig. B2, as read in `geometry.py`; not re-read here |
| Door on the grid | 2.0 m wide, 2.0 m high (4.00 m² against 3.99 m²) | [A] | 0.25 m grid |
| Walls | east and west 0.5 m thick, outside the 20 m clear width; other surfaces are the mesh boundary, INERT | [A] | |
| Fire growth | 0.0469 t² kW | [P] | Table 2.1 p. 56; p. 199 |
| Peak | 2,700 kW, then constant; taken from the example, not re-derived | [P] | p. 202 |
| Yields | soot 0.07, CO 0.04, CO₂ 1.5, H₂O 1.0 kg/kg | [P] | Table 2.1 p. 56 |
| ΔH<sub>c</sub>, χ<sub>r</sub> | 20 MJ/kg, 0.35 | [P] | Table 2.1 p. 56 |
| Fuel formula | CH<sub>2.686</sub>O<sub>0.592</sub> | [A] | derived below |
| Fire position | room centre (10, 25) | [P] | p. 202 |
| Burner | 2.0 × 2.0 m, top at 0.5 m. The example has 0.4 m; C/VM2 2.2.1(k) allows at most 0.5 m | [A] | p. 202; p. 40 |
| Occupants | 1,000, evenly distributed | [P] | Table B1 p. 190; p. 88 |
| Detection + notification | 66 + 30 = 96 s → `DET_MEAN` | [P] | p. 203 |
| Pre-travel | 30 s → `PRE_MEAN` | [P] | p. 203 |
| Detector criterion | OD 0.097 m⁻¹, radial distance 7 m, ≥ 25 mm below the ceiling | [P] | Table 3.2 p. 88; p. 203 |
| Detector layout | 3 × 6 grid, 6.67 × 8.33 m, z 4.9 m | [A] | |
| Tenability height | 2.0 m → `HUMAN_SMOKE_HEIGHT`, slices | [P] | p. 49 |
| Simulated time | 1,200 s | [P] | p. 202, Fig. B4 |
| Free speed | 1.2 m/s, constant | [A] | #808 |
| Body | `DIA_MEAN` 0.51 m, constant; torso 0.30, shoulder 0.19 m | [A] | FDS+Evac Adult mean |
| Exit knowledge | all four known, probability 1 | [A] | #808 |
| Furniture | none; the example calls the layout unknown | [P] | p. 203 |
| Leakage | none (below) | [A] | |

## Arithmetic

- **Ramp.** t = √(2700 / 0.0469) = 239.94 s. `TAU_Q=-239.9` gives
  Q = 2700 (t / 239.9)², that is α = 0.046914 kW/s² (+0.03 %), then
  constant (User Guide, "Time-Dependent Functions").
- **Burner.** 2.0 × 2.0 = 4.0 m²; HRRPUA = 2700 / 4.0 = 675 kW/m².
- **Fuel.** Per kg of fuel: C = 1.5 · 12.011/44.01 + 0.04 · 12.011/28.01
  + 0.07 = 0.4965 kg; H = 1.0 · 2.016/18.015 = 0.1119 kg; O = the rest
  = 0.3916 kg. Per C atom: H 2.6856, O 0.5920. Soot is counted as carbon.
  The oxygen consumed is 1.610 kg/kg, so the heat per kg of oxygen is
  20,000 / 1.610 = 12,420 kJ/kg (FDS default 13,100).
- **D\*.** (2700 / (1.204 · 1.005 · 293 · √9.81))^0.4 = 1.43 m.
  D\*/dx = 5.7 at 0.25 m, 7.1 at 0.2 m.
- **Cells.** x −2.5…22.5 (100), y 0…50 (200), z 0…5 (20): 400,000. The
  room alone is 320,000; walls 16,000; exterior strips 64,000.
- **Mesh split.** 3 × 7 = 21 meshes, one MPI process each. I = 30, 40, 30;
  J = 32, 32, 24, 24, 24, 40, 24; K = 20 (J and K factor into 2, 3, 5).
  14,400–32,000 cells per mesh, mean 19,048. No cut is closer than 1.5 m
  to a door or 2 m to the burner.
- **Evacuation mesh.** x −0.5…20.5, y 0…50, z 0.4…1.6: 84 × 200 cells at
  0.25 m, 42 × 100 at 0.5 m. Floor at z 0 (`EVAC_Z_OFFSET` 1.0).
- **Density.** 1000 / (1000 − 4) m² = 1.00 persons/m².
- **Detector.** 1 − 10^(−0.097) = 20.0 %/m; K = 2.303 · 0.097 = 0.223 m⁻¹.
- **Cost of phase 2.** The earlier C/VM2 run (1,669,900 cells at 0.2 m,
  64 processes, 19,196 s, FDS 6.10.1 on JURECA) is 6.1 × 10⁻⁴ core-s per
  cell and simulated second. Scaled by the time step (0.2/0.25):
  400,000 · 1200 · 6.1 × 10⁻⁴ · 0.8 = 2.4 × 10⁵ core-s, **about 65
  core-hours, 3 h on 21 processes**. Range 35–130 core-hours: FDS 6.7.7,
  another compiler and the `.fed` output are not in that measurement. #808
  says 10–30. The fire test costs the same if it runs to 1,200 s. Phases 1
  and 3 are serial and not estimated.

## Open choices named in #808

**Confirm** = the maintainer decides before a run.

| Choice | Used here | Reason | |
|---|---|---|---|
| Door coordinates | y 11.5 and 41.5 m, east and west | the earlier study's reading of Fig. B2; 30 m apart (≥ 20 m, p. 190) | Confirm |
| Fuel for `&REAC` | CH<sub>2.686</sub>O<sub>0.592</sub> on `&REAC` | returns all five Table 2.1 values; FDS 6.10.1 gave CO₂ 1.500, H₂O 1.000 for it in the earlier study | Confirm |
| Fire mesh | 0.25 m | one 0.5 m lattice holds the fire grid, both evacuation grids, walls, doors and burner; door centres fall on it. Cost: D\*/dx 5.7, burner top 0.5 m, 2.0 m doors | **Confirm** |
| MPI split | 21 meshes | above | |
| West doors | exits to safety; no foyer | #808 measures the time the room is clear (C/VM2 RSET, p. 88). For the fire they open to ambient air, so no smoke returns from a foyer | **Confirm** |
| Door state | open from t = 0 | FDS+Evac geometry is static (guide, "Features of Limited Functionality"). The example keeps them closed until the evacuation (p. 202) | **Confirm** |
| Free speed | 1.2 m/s constant | the C/VM2 cap; 1.03 m/s already contains density | **Confirm** |
| Body size | `DIA_MEAN` 0.51 m constant; `init` maps it to radius 0.15 m | Adult mean; the pyFDS-Evac radius (0.15 torso, 0.2 default) is open | **Confirm** |
| Relaxation time | Adult default, uniform 0.8–1.2 s | #808 does not name it | Confirm |
| Evacuation grid | 0.25 m | equals the fire cell, so "constant per evacuation cell" adds no averaging; the guide calls 0.25 m and coarser safe | Confirm |
| Second grid | 0.5 m, phase 1 only | phase 1 is a full clear-air evacuation, so the two grids can be compared without a second fire run | Confirm |
| `FAC_DOOR_QUEUE` | default 1.3, not switched off | it can be set to 0. Proposed: headline with the default, ten more phase 3 runs with 0 beside pyFDS-Evac `w_queue` 0. Whether 0 also needs a new phase 1 is unverified | **Confirm** |

Further choices made here:

- `FED_DOOR_CRIT=-1000.0`: the default of the code that runs. **Confirm**
  (−100 is the documented value).
- `HUMAN_SMOKE_HEIGHT` 2.0 m is a cell face at 0.25 m (and at 0.2 m).
  Which cell FDS+Evac reads there, 1.75–2.0 or 2.0–2.25 m, could not be
  determined; the pyFDS-Evac slice at 2.0 m averages both. **Confirm** or
  move both to a cell centre.
- Doorways are cut into the evacuation meshes over the full height
  (`&HOLE ... EVACUATION=.TRUE.`). The visibility mesh spans
  2.0 ± 0.29 m (guide, chapter 8, `EVAC_DELTA_SEE`), and the fire-mesh
  door ends at 2.0 m, so its head might otherwise hide the exits.
- The "1.6 m" slices are written at 1.5 m, the nearest grid plane.
  `init --check` at the default height accepts them.
- Detection is reported by `OD_*` (optical density at the detector, the
  C/VM2 criterion) and by `SD_*` (Heskestad detector, with entry lag).
  `DET_MEAN` stays 96 s whatever FDS finds; the difference is reported.
- No `DT_RESTART`: the guide calls a restart with `.fed` output fragile.

## Differences from the existing C/VM2 decks

| | Here | `cvm2-function-centre` f1 | `a047_cvm2_h40` |
|---|---|---|---|
| FDS | 6.7.7 | 6.10.1 | current |
| Cell | 0.25 m | 0.2 m | 0.2 m |
| Domain | ballroom + 2 m strips | north wing + street band | Schröder geometry |
| Doors | open, 2.0 × 2.0 m | timed, 1.8 × 2.2 m | open |
| Walls | 0.5 m | 0.2 m | 0.2 m |
| Burner | 2.0 × 2.0 × 0.5 m, 675 kW/m² | 2.4 × 2.4 × 0.4 m, 468.75 kW/m² | 3 × 2 m vent, 250 kW/m² |
| Fuel | CH<sub>2.686</sub>O<sub>0.592</sub> on `&REAC` | the same | CH₂O<sub>0.5</sub> through `&SPEC` |
| Leakage | none | Table B12 vents | none |
| Sprinkler links | none | check devices | none |
| Ramp | `TAU_Q` (#808 says `RAMP_Q`; same curve) | `TAU_Q` | `TAU_Q` |

Leakage is left out because four open doors (16 m²) dwarf the Table B12
slots (about 4 m²). The one-cell leak vent that crashed the earlier decks
therefore cannot occur. If the doors become timed, the leak vents must
come back, each at least three cells long.

## Keywords

Every namelist keyword in the decks was found in the namelist of
`read.f90` or `evac.f90` at `FDS6.7.7`; every output quantity and species
name in the 6.7.7 User Guide. None is unverified by name. What only a run
can show:

- that devices and fire slices are skipped silently in phases 1 and 3
  (`read.f90` ll. 13087–13178, 14561–14563);
- that the `EVACUATION=.TRUE.` holes open the visibility mesh;
- that an `&EXIT` on the mesh boundary behind a wall hole works as in
  the guide's Example 1 (`RightExit`);
- that 1,000 agents are placed at 1.0 persons/m² in one attempt;
- the fuel warning ("not predefined") and the yields in the `.out` file.

`EVACUATION_ALL_STEPS` (`read.f90` l. 2216) would pick the phase from the
files on disk with one deck. It is in the code but not in the guide, so
the decks use the three documented keywords.

## Checks run here

- `python3 make_decks.py` reproduces the five committed decks byte for
  byte; `ruff check` and `ruff format --check` pass.
- `pyfds-evac init cvm2_ballroom_fire.fds --check`: exit 0, extinction, CO,
  CO₂, O₂ at 1.5 m (requested 1.6 m), `T_END` 1200 s, `DT_SLCF` 1 s.
- `pyfds-evac init cvm2_ballroom_evac.fds --check`: exit 0, the same at
  2.0 m.
- `pyfds-evac init cvm2_ballroom_evac.fds` (to a scratch folder): runnable;
  walkable 1000.0 m², 4 exits, 1,000 agents in two spawn areas, constant
  pre-movement 126 s, v0 1.2 m/s, radius 0.15 m, `smoke_slice_height` 2.0.
  Warnings: `FED_DOOR_CRIT` has no counterpart; one circle for the body.
