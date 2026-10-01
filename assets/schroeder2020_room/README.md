# ASET-RSET maps after Schröder et al. (2020)

Inputs of the study page
[ASET-RSET maps after Schröder et al. (2020)](../../docs/study-schroeder2020.md):
the 30 × 10 × 3 m demonstration room of B. Schröder, L. Arnold and
A. Seyfried, "A map representation of the ASET-RSET concept", Fire Saf. J.
115 (2020) 103154, doi:10.1016/j.firesaf.2020.103154, with a 60 kW fire
and 100 people.

Two families of inputs:

- **`rel_*`, the page's headline.** Room, door, fire, reaction and crowd
  are taken from the authors' release,
  [doi:10.5281/zenodo.3875550](https://doi.org/10.5281/zenodo.3875550)
  (tag [R] in the generators and decks). The release has no licence file,
  so no file of it is in this folder: the generators hold the values read
  from it, and the decks name the release file each value comes from.
- **`hrr060_*`, the page's sensitivity.** The same room rebuilt from the
  paper's text and figures alone, with an assumed fire (0.6 × 0.6 m
  burner, flexible PU foam). Nothing from the release is used.

Inputs only. FDS output and evacuation results are not kept in the
repository.

| File or folder | Role |
|---|---|
| `make_decks_rel.py` | Writes the three `rel_*` FDS decks |
| `make_configs_rel.py` | Writes the `rel_*` scenarios and `geometry.wkt` |
| `make_decks.py` | Writes the three `hrr060_*` FDS decks |
| `make_configs.py` | Writes the `hrr060_*` scenarios and `geometry.wkt` |
| `rel_1door/` | One door, 0.2 m grid |
| `rel_1door_dx010/` | One door, 0.1 m grid (the grid check) |
| `rel_2door/` | Two doors, 0.2 m grid; the scenarios are per seed in `seeds/` |
| `hrr060_1door/`, `hrr060_1door_dx010/`, `hrr060_2door/` | The same for the `hrr060_*` family |
| `hrr060_1door_pert/` | `hrr060_1door` with HRRPUA 166.87 instead of 166.7 kW/m² (+0.1 %); written by hand, see below |

Each one-door folder holds the FDS deck, `geometry.wkt` and five
scenarios that differ only in pre-movement: `config.json` and
`config_pre0.json` (none), `config_pre30.json` and `config_pre60.json`
(constant 30 s and 60 s), and `config_pre_default.json` (no pre-movement
key, so pyFDS-Evac applies its default of a constant 10 s). The two-door
folders hold one scenario per seed 1–10 and version in `seeds/`: the
west and east counts are drawn per seed from a binomial split of the
floor. The exit cap (1.00 persons/s for `rel_*`, 0.96 for `hrr060_*`) is
not in the scenarios; `scripts/docs/schroeder_room_maps.py` applies it per
run.

The comments in the decks and generators carry the tags of the page:
[P] stated in the paper, [F] read off a paper figure, [R] taken from the
release, [A] assumed.

## Regenerate the inputs

From the repository root, into a folder `OUT`:

```bash
uv run python assets/schroeder2020_room/make_decks_rel.py OUT
uv run python assets/schroeder2020_room/make_configs_rel.py OUT
uv run python assets/schroeder2020_room/make_decks.py OUT
uv run python assets/schroeder2020_room/make_configs.py OUT
```

The four generators write the 139 files of the six generated folders byte
for byte, and these are the files of the page's FDS and evacuation runs.
`hrr060_1door_pert/hrr060_1door_pert.fds` is `hrr060_1door.fds` with two
changes, CHID and HRRPUA; its title and comments still say 60 kW (the
actual HRR is 60.07 kW). The map script needs only its FDS output, so the
folder holds no scenario.

## Run

FDS 6.10.1 on 6 MPI processes, one folder at a time; `DATA` is a folder
outside the repository:

```bash
cp -R assets/schroeder2020_room/rel_1door "$DATA/"
(cd "$DATA/rel_1door" && mpiexec -n 6 fds rel_1door.fds)
```

The page's
[Reproduce](../../docs/study-schroeder2020.md#reproduce)
section gives the commands for the evacuations, maps and figures, and
the expected result.

Licence: decks, scenario files and geometry CC-BY-4.0; code MIT.
