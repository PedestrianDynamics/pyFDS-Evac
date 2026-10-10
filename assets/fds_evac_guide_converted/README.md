# Converted FDS+Evac guide cases

This collection contains **94 single-floor pyFDS-Evac/JuPedSim scenarios**, with
**42 separate fire-only FDS decks**. The other 52 scenarios are evacuation-only
and require no FDS calculation. The **88 excluded original scenarios** and their
reasons are listed in [SCENARIOS.md](SCENARIOS.md) and [manifest.json](manifest.json).

Originals: [Timo Korhonen's FDS+Evac guide / InputFiles](https://github.com/tkorhon1/FDS-Evac-Guide/tree/master/InputFiles).
The source snapshot is `10eb1a4448ae771ad2187a238a8330c819550008`. Every case's
`provenance.json` links its original file at that commit, records its original
SHA-256, and identifies modifications. Unmodified originals are not duplicated
in this collection; the repository also carries them in `../fds_evac_guide`.

## Contents

Each directory under `cases/` contains:

- `config.json`: populations, placement areas, exits, behavioural settings and horizon.
- `geometry.wkt`: JuPedSim walkable geometry, including holes and obstacles.
- `import_report.json`: detailed mapping, approximations and unsupported parameters.
- `provenance.json`: source link, checksums and subsequent adjustments.
- `fire.fds`, where applicable: modern FDS input containing only fire/flow data.

The JSON/WKT pair is the JuPedSim material used through pyFDS-Evac. It can also be
opened as a scenario bundle in the pyFDS-Evac interface. No FDS+Evac executable,
old evacuation mesh, or external geometry file is needed to run a converted case.
Generated FDS output, trajectories and logs are created by the runner; they are
not source assets and are not committed here.

## Version and installation

The evacuation checks used pyFDS-Evac source commit
`3435dc440fe89740690aed62ba9e6e144ec3475f`, Python 3.12.13, JuPedSim 1.4.2,
Shapely 2.1.2, NumPy 2.4.4, fdsreader 1.11.7 and fdsvismap 0.3.2.
The package reports version 0.3.1, but the published `v0.3.1` tag is a different
commit: use this contribution's checkout and its `uv.lock`, not only that version
number. Fire-input checks used **FDS 6.10.1**.

From the repository root, install the locked environment:

```sh
uv sync --python 3.12 --locked
uv run python scripts/run_fds_evac_guide.py --list
```

Install FDS separately and put its executable on `PATH`, or supply `--fds-exe`.
On Windows, use the full path to `fds.exe`; the runner adds the sibling `mpi`
directory to the child process environment when present.

## Run every case

The default `auto` phase runs each available fire deck first, then runs its
evacuation scenario against the resulting fire data. Evacuation-only cases run
in clear air. These commands run the original configured horizons with **no
wall-clock timeout**:

```sh
uv run python scripts/run_fds_evac_guide.py --output guide-runs --jobs 2
```

Windows example:

```powershell
uv run python scripts/run_fds_evac_guide.py --output guide-runs --jobs 2 --fds-exe "C:\Program Files\firemodels\FDS6\bin\fds.exe"
```

Use a new output directory for each invocation. Output contains one folder per
case, FDS files where applicable, `evac/trajectory.sqlite`, logs and a batch
`summary.json`. The runner continues after an individual failure and reports
it. FDS can return exit code zero after an input error, so the runner also checks
its successful-completion message. Missing required coupling quantities are
errors, not silent clear-air runs.

Run only clear-air evacuation, or select a case:

```sh
uv run python scripts/run_fds_evac_guide.py --phase evac --output clear-air-runs --jobs 2
uv run python scripts/run_fds_evac_guide.py --phase evac --case Examples/DoorFlowExample --output door-flow-run
```

To separate the fire and evacuation work:

```sh
uv run python scripts/run_fds_evac_guide.py --phase fds --output fire-runs --jobs 2
uv run python scripts/run_fds_evac_guide.py --phase coupled --fds-root fire-runs --output coupled-runs --jobs 2
```

For a quick input/integration check, cap time **only in generated copies**:

```sh
uv run python scripts/run_fds_evac_guide.py --duration 1 --timeout 300 --jobs 2 --output short-check
```

`--duration` is simulated seconds; `--timeout` is optional wall seconds per
subprocess. Neither changes the committed inputs. Exit code 0 means successful
completion, 2 means at least one evacuation reached its horizon with people
remaining, and 1 means an error or wall timeout. Code 2 is expected for short
checks, the nine initialization cases and the twelve FED cases whose initial
delay exceeds their horizon. It does not mean an input crash. Full runs of the
larger crowds can take considerably longer than five minutes.

## Adjustments and interpretation

These are runnable conversions and adjusted examples, not proof of numerical or
behavioural equivalence between FDS+Evac and JuPedSim. Review each import report:
some FDS+Evac settings have no counterpart; three-circle bodies become JuPedSim
circles (default radius 0.2 m), and some speed distributions are approximated.
For 37 scenarios, point/line placement regions were expanded to areas with a
0.6 m transverse width to support placement. Original benchmark material
properties were described as fabricated and remain benchmark inputs.

**DoorFlowExample is adjusted.** Two regions contain 50 people each: x=4.6–7.5 m
and x=7.5–10.4 m, both y=4.8–9.8 m. Total placement area increases from 25 to
29 m² (**16%**). Splitting the original area alone was insufficient. Geometry,
population, body radius and original 200 s horizon are retained, but the initial
distribution changes, including the clearance at the seam. Placement passed
seeds 42 and 0–9; the full seed-42 run evacuated all 100 people in 51.28 simulated
seconds on both tested source commits. This is not a claim that the expansion
is minimal or works for every random seed. See its `placement_change.json`.

**Fire decks:** legacy evacuation namelists, evacuation-only meshes/objects and
EVAC parameters are removed. Fire meshes, obstructions, vents, materials,
sources, initial concentrations and reaction yields are retained. Horizontal
coupling slices are added and `DT_SLCF` is capped at 1 s. Zero-initial-fraction
CO/soot species are explicitly declared where needed for output in zero-yield
reacting tests; no positive yields are invented.

**DoorAlgo_A and DoorAlgo_B:** the imported smoke height of 2.1 m lies outside
their 0–2 m fire mesh. Configurations and slices use the evacuation-plane
midpoint, 1.5 m, instead. This is an explicit sampling adjustment; their import
reports retain the original conversion values.

**Eight `soot_vs_speed2_*` cases** retain the original non-reacting `AIR`
background and prescribed soot. These are smoke-speed-only tests; they supply
extinction and temperature, with gas FED intentionally unavailable. No oxygen
or CO2 composition is invented for the original lumped AIR species. The other
34 fire cases supply extinction, CO, CO2, O2 and temperature. Heat FED remains
off by default. Running a case with fire coupling does not reproduce a legacy
`EVACUATION_DRILL` switch: use `--phase evac` for clear-air comparison.

## Verification limits

The earlier seed-42 **clear-air** audit, including the repaired DoorFlow case,
recorded **45 complete evacuations, 21 normal horizon stops, and 28 wall
timeouts at 300 seconds**. All 94 passed a short initialization/run check.
The 28 timeouts are not evidence of input errors or deadlock; full evacuation
completion remains unverified. The exact case outcomes are in the manifest and
scenario table. Nine horizon stops are initialization tests; twelve FED tests
have 200 s premovement but only a 100 s horizon.

All 42 modified fire inputs completed a **one-second FDS 6.10.1 integration**
and supplied the quantities required for their declared coupling mode. This
does not establish full fire-run completion or physical equivalence. See
`validation.json` for the packaged integration checks and their scope.

The packaged runner also passed short checks for **all 94 cases**, using fire
coupling for the 42 fire cases. Two initial 300 s wall timeouts passed on retry
in a fresh locked environment outside OneDrive (28 and 32 s, unchanged inputs).
Three representative coupled runs used full horizons: `soot_vs_speed_1000` and
`soot_vs_speed2_1000` evacuated completely; `fed_CO_verificationA` reached its
100 s horizon normally. Other full coupled runs remain unverified.

Warnings need interpretation: some original fire meshes cover less than the
evacuation geometry, so agents outside the FDS slices receive ambient air and
clear sight. Those meshes were not enlarged. Thin walls in 22 cases can be lost
on the default 0.25 m visibility grid. The supplied `fdsreader` can also warn
that its vents metadata parser cannot parse an FDS 6.10.1 comment; coupling uses
slice data, which was checked separately. The retained custom AIR/fuel species
can produce FDS property warnings. Do not describe these examples as warning-free
or as validated evacuation design predictions.

## Exclusions and licence

84 originals use unsupported stairs/inclines/inter-floor corridor records;
four Atrium cases require multiple evacuation floors. They are documented,
not replaced by flattened geometry. `OfficeStairsV2_1p0.fds` also has a missing
slash on its original RADI record; correcting it does not remove its unsupported
stair records.

The derived scenario files under `cases/` retain the originals' **GPL-3.0-only**
licence and attribution to Timo Korhonen / VTT Technical Research Centre of
Finland. See [the licence text](../../LICENSES/GPL-3.0-only.txt), the original
repository licence and `REUSE.toml`. Modifications are dated 2026-10-08 in each
provenance file. These assets are excluded from the wheel and source
distribution, as are the original guide decks. The runner and collection
documentation use the repository's MIT licence.
