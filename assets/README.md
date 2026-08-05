# Scenario assets

One folder per scenario. A folder is a valid `--scenario` target when it holds
a `config.json`; the FDS deck beside it is what `--fds-dir` reads.

| File | Role |
|------|------|
| `config.json` | JuPedSim scenario: geometry references, exits, spawn distributions, journeys |
| `geometry.wkt` | Walkable area as a Shapely WKT polygon |
| `<name>.fds` | FDS deck for the fire/gas field |
| `config_*.json` | Alternate configs selectable as `--scenario <dir>/<file>.json` |
| `build_geometry.py` | Regenerates `geometry.wkt` parametrically |

Everything FDS writes beside these (`.smv`, `.out`, `.sf`, `_devc.csv`, and the
rest) is untracked. See the ignore rules in [`.gitignore`](../.gitignore).

## Tracked scenarios

| Folder | What it is | Fire | Detail |
|--------|------------|------|--------|
| `ISO-table21` | ISO 20414 corridor, single agent, single exit. Also the default small fixture for unrelated tests. | deck | [README](../README.md#assets) |
| `ISO-table22` | ISO 20414 stationary benchmark, one non-moving agent in a fixed gas concentration. | no | [README](../README.md#assets) |
| `t_junction` | T-corridor, cable fire at the junction, two exits. The rerouting case. | deck | [t_junction/README.md](t_junction/README.md) |
| `fed_incap_co_2000ppm`<br>`fed_incap_co_4000ppm`<br>`fed_incap_co_8000ppm` | Sealed uniform room at three constant CO concentrations, 100 non-evacuating agents, 4 MPI meshes. | deck | [testing-homogeneous.md](../docs/testing-homogeneous.md) |
| `familiarity_test_full`<br>`familiarity_test_discovery` | Hand-drawn 20 x 18 m floor plan, 20 agents. The pair differs only in the spawn distribution's `familiarity` value. | deck | [testing-familiarity.md](../docs/testing-familiarity.md) |
| `exit_visibility_alpha` | 4 x 30 m corridor, 40 discovery agents, two exits. The pair differs only in one exit sign's viewing bearing. | deck | [test_exit_visibility_alpha.py](../tests/test_exit_visibility_alpha.py) |
| `cognitive_map_memory` | 4 x 32 m corridor with a side alcove, 20 discovery agents. A side exit's sign is legible only from y in [12.5, 27.5]. | deck | [test_cognitive_map_memory.py](../tests/test_cognitive_map_memory.py) |

What each one proves, and where that proof is checked, is in the
[Assets section of the main README](../README.md#assets).

Note that the component verification suite,
[`tests/verification/`](../tests/verification/README.md), does not load these
folders. It builds its scenarios in code and injects synthetic fields so the
expected behaviour stays closed-form with no FDS run. The assets here are for
running the real coupled pipeline.

## Adding a scenario

More cases are planned, signage among them. A new folder needs at minimum a
`config.json` and a `geometry.wkt`; add a `<name>.fds` if the case involves
fire, and a `build_geometry.py` if the layout is worth regenerating rather than
hand-editing. Add a row above, and a description in the main README saying what
the scenario proves and where that is checked.

Two lessons from the retired folders below, both worth avoiding: a scenario with
no geometry and no deck cannot run no matter what its config says, and a
scenario nothing asserts against tends to get copied rather than extended.

## Retired

No longer tracked, but preserved in git history. Recover any of them by finding
the removing commit and checking out its parent:

```bash
git log --diff-filter=D --name-only -- assets/haspel
```

| Folder | Was | Dropped because |
|--------|-----|-----------------|
| `demo2` | Copy of the T-corridor case | Differed from `t_junction` only in README wording and two configs |
| `beam_detector_no_mesh`, `beam_detector_w_mesh` | Bare FDS decks | No scenario config, referenced nowhere |
| `fed_incap_co_v1`, `fed_incap_co_v2`, `fed_incap_co_smol` | Earlier FED iterations | Superseded by the ppm ladder; `_smol` never had a deck |
| `basic` | Fire-free fixture: two exits, 1000 agents, flow spawning | Exercised JuPedSim only, never built on |
| `social_force` | Fire-free fixture: `SocialForceModel`, checkpoint journeys | Exercised JuPedSim only, never built on |
| `haspel` | Three-exit, three-zone config | Never had a geometry or a deck, so it could not run |
| `maze_test_full`, `maze_test_discovery` | 50 x 50 m corn maze, full vs discovery pair | No deck, so pure wayfinding only; `familiarity_test_*` covers the same question with a fire |
