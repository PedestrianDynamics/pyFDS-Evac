# Haspel

A real-building asset, not a synthetic test deck: the ground floor of the BUW Campus Haspel building (Gebäude HC), with 260 agents and an FDS fire. It is a demonstration case. It has no citable reference result: an earlier comparison with a PathFinder student project was dropped, because that project is unpublished and cannot be cited (#230).

This scenario places 260 agents: 100 Hörsaal, 30 at the Mensa food counter, 30 eating in the Mensa, 50 roaming the Foyer and 50 roaming the exhibition area.

## Routes

The scenario has no journeys. Each agent's exit, and its way to it through the building, is chosen by pyfds-evac's route choice, not prescribed. The stages are:

| Stage | Where | Role |
|---|---|---|
| `jps-exits_0` | east door (x 58.2–58.8) | exit |
| `jps-exits_1` | south door (y 8.1–8.4) | exit |

These are the only two exits. The scenario has no checkpoints; the north exit and the four door checkpoints were removed with #229. Every sign faces the agents walking towards it (`alpha` is the bearing the sign faces).

| Spawn area | Where | Agents |
|---|---|---|
| `jps-distributions_0` | exhibition area (x 16–26, y 13–17), roaming | 50 |
| `jps-distributions_1` | Mensa food counter (x 37–51, y 20.9–24.9) | 30 |
| `jps-distributions_2` | Foyer (x 27.5–36.3, y 15.5–34.5), roaming | 50 |
| `jps-distributions_3`, `_5` … `_16` | Hörsaal, seated: one strip per desk row behind each of the 13 desks (x 13.93–24.26, 0.55–0.6 m deep), 7 or 8 per row | 100 |
| `jps-distributions_4` | Mensa seating (x 37–54, y 27–36.5), eating | 30 |

Until #894 the scenario prescribed three journeys with fixed exit shares (85/15, 90/10), and two of its checkpoints sat in doorways the agents then had to walk back from: the Hörsaal group turned back into its own queue at the north door, and the Mensa group walked north to the Foyer door and back south to `exit_south`. In clear air 74 of 300 agents deadlocked (#894, #132).

## Results

Clear air (no `--fds-dir`), seeds 1–10, this population: all 260 agents leave in every seed, the last after 114.4–122.9 s (median 117.2 s); 204–212 of them leave by `jps-exits_1` (south). The desk rows of the Hörsaal are closed at their west end in the WKT (a 0.2 m wall at x 13.73–13.93 joins the 13 desks), so each row opens only to the east aisle. With both ends open, the shortest path cut through the 0.58 m gaps between desks, and in 3 of 5 seeds an agent walking through a row met a seated agent walking out of it head-on at the west end, a deadlock with 2 agents left. The FDS deck keeps the desks as they were. The earlier result, 400 agents out by 103.2 s at seed 42, was for the old population and exits.

**1. The FDS output predates the deck.**
`haspel.fds` was changed for #229: the mesh now covers the whole floor plan (x 6.25–61.25, y 5.75–43.25, 0.1 m cells, 88 meshes, about 10.3 million cells against 6.75 million before), so both exits lie inside the sampled smoke field. Walls 0.2 m thick, 5 m high, now follow the WKT outline, and the domain sides are open (`SURF_ID='OPEN'`), so smoke leaves the building only through the two exits. The strip between the building and the outline, including the strip north of the long wall at y ≈ 37.1 that the floor plan treats as outdoors, is therefore an enclosed walkway in FDS. The burner (2 × 2 m, x 33.5–35.5, y 12.5–14.5, top at 1 m) is in the south corner of the Foyer, about 3 m east of the entrance vestibule that most agents pass on their way to `jps-exits_1`; the WKT has the same 2 × 2 m as an obstacle, so agents walk around it. The fire ramps linearly to 200 kW (50 kW/m² × 4 m²) at 60 s, then stays at 200 kW. The deck writes its gas slices at z = 2 m, cell-centred, so pyfds-evac reads smoke, CO, CO₂ and O₂ at z = 2.05 m, not at its 1.6 m default, and says so in a setup warning.

FDS output: FDS 6.10.1 (FDS-6.10.1-0-g12efa16) on JURECA, 88 MPI processes, T_END 1200 s, run `jureca-2026-11` (Slurm jobs 15850945, 15850956, 15850957), deck sha256 `2e7becb7…e436eb`, ended with `STOP: FDS completed successfully`. The slices, `.out` and provenance records are in `<sciebo>/fds-evac-data/Haspel/jureca-2026-11/`; the job files are not in this repository.

Fire against clear air, seeds 1–10, same code, `--fds-dir` the run above:

| | Clear air | Fire |
|---|---|---|
| Last agent out, median | 117.2 s | 117.4 s |
| Last agent out, range | 114.4–122.9 s | 116.1–122.7 s |
| Leave by `jps-exits_1` (south) | 204–212 | the same as clear air in every seed |
| Evacuated | 260/260 | 260/260 |
| Largest FED of any agent | – | 1.7 × 10⁻⁵ |
| Smallest smoke speed factor | – | 0.988 (about 75 agents slowed per seed) |

The fire has no measurable effect on this evacuation. The burner reaches 200 kW only at 60 s and the last agent leaves at about 117 s, before the smoke at the slice height is dense enough to slow anyone by more than 1.2 % or to give a dose. Single seeds move by −5.4 s to +3.2 s against clear air because these small slowdowns change how the crowd interacts; no agent changes its exit. A fire comparison needs a faster or larger fire, or a later evacuation start.

## Parameters

`config.json` overrides these routing defaults for this scenario only; the code defaults are unchanged.

| Key | Value | Default | Source |
|---|---|---|---|
| `routing.fed_rejection_threshold` | 0.3 | 1.0 | not stated; consistent with the ISO 13571 threshold for susceptible populations |
| `routing.visibility_extinction_threshold` | 0.15 1/m | 0.5 1/m | not stated; with C = 3 this is S = 3/K = 20 m |
| `routing.w_smoke` | 40 | 1.0 | not stated |
| `v0` | 1.4 m/s | | not stated |

In `haspel.fds` the fuel is labelled `N-HEPTANE`, but `HEAT_OF_COMBUSTION=20000` kJ/kg, `SOOT_YIELD=0.015` and `CO_YIELD=0.008` have no stated source. FDS produces soot and CO from yield × HRR / ΔHc, so the extinction field, and every agent's visibility and FED, depend on these values. Treat them as a generic fuel assumption.

## `inifile_template.json` is not a second scenario

A leftover from an old, unrelated JuPedSim format, not a real scenario. The picker lists it anyway since it's technically openable JSON. Ignore it.
