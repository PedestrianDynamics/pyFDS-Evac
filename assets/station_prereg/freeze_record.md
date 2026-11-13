# Station pre-registration: values recorded at freeze

The tag `station-prereg-v1` freezes `preregistration.md` (§7). Every file named
here is in the tagged tree; `SHA256SUMS` lists its checksum. Check with
`shasum -a 256 -c assets/station_prereg/SHA256SUMS` from the repository root.

## Software

| Item | Value |
|---|---|
| pyFDS-Evac | the tagged commit `aaeda1f3` (`git rev-list -n 1 station-prereg-v1`); archived on Zenodo, [10.5281/zenodo.24190605](https://doi.org/10.5281/zenodo.24190605) |
| JuPedSim | 1.4.2 (installed, `importlib.metadata`; `uv.lock` resolves 1.4.2) |
| fdsvismap | 0.3.3 (pinned `==0.3.3`) |
| fdsreader | 1.14.0 |
| shapely, numpy | 2.1.2, 2.4.4 |
| Python | 3.12.13 |
| `uv.lock` | checksum in `SHA256SUMS` |
| FDS | 6.10.1, `FDS-6.10.1-0-g12efa16-release`, the validated JURECA build (`$PROJECT/fds/bin/fds.build.txt`) |

## FDS decks

`fds/` holds the six decks as copied to JURECA on 2026-11-13, the generator
`make_deck.py` and the digitised HRR `nist_fig5_42_hrr.csv`. The generator's
input, NIST's `Station210_clean.fds`, is not redistributed; its SHA-256 is
`68bf49722bb75a0424aee1927dadc2c801ea695c2800ed09ee50a6919532a7bb`.

| Deck | Use | Meshes | `T_END` |
|---|---|---|---|
| `station_dx020_central` | central fire, V2, V3, V6 | 32 | 250 s |
| `station_dx020_low`, `station_dx020_high` | yield triplet | 32 | 250 s |
| `station_dx020_central_m15` | HRR −15 s | 32 | 234 s |
| `station_dx020_central_p15` | HRR +15 s | 32 | 250 s |
| `station_dx010_central` | V6 grid check only | 128 | 250 s |

Each JURECA run records the SHA-256 of the deck it read
(`<deck>/provenance/<chid>.deck.sha256`); it must match `SHA256SUMS`.

Before the freeze, each deck ran a 2 s smoke test (jobs 15843769–15843771).
Only the run records were read (§6).

## Seeds

1–3 pilot, not scored. 4–23 scored, in every arm and every fire variant (O5).

## Build commands

From the repository root. The committed configs (`assets/station_nist/` and
`assets/station_fahy/`, `config_full.json`) are the default build: arm C+jam,
and the base of arms U and R. Every other row is built into its own directory,
which gets a `build_options.json` record. `DECK` is `station_nist`, or
`station_fahy` for the V1 geometry row.

```bash
B=".venv/bin/python assets/DECK/build_scenario.py"
$B --t-jam none        --out build/DECK/C          # arm C (V1)
$B --horizon 234       --out build/DECK/h234       # -15 s fire variant
$B --t-jam 71          --out build/DECK/tjam71
$B --t-jam 102         --out build/DECK/tjam102
$B --premovement zero    --out build/DECK/pm_zero
$B --premovement tracked --out build/DECK/pm_tracked
$B --w-queue 0.024     --out build/DECK/wq0024     # Fahy fit, labelled as one
$B --no-anticipate     --out build/DECK/r_na       # R-na
```

## Run commands

`CFG` is a built `config_full.json`; `FDS` is a fetched fire output folder
(`station_fire/<deck>/`); `S` runs over the seeds.

| Arm | Command |
|---|---|
| C, C+jam | `.venv/bin/python run.py --scenario CFG --seed S --output-sqlite OUT` |
| U | the same, plus `--fds-dir FDS --smoke-slice-height 1.5 --smoke-blind` |
| R | the same, plus `--fds-dir FDS --smoke-slice-height 1.5` |
| Dose only | R, plus `--disable-tenability` |

`--smoke-slice-height 1.5` names the slice the 0.2 m decks hold (§5, C24).
The −15 s variant uses `build/DECK/h234` with
`--fds-dir station_fire/station_dx020_central_m15`. Its arms U and R are
paired with a C+jam baseline built the same way (`h234`, no `--fds-dir`), so
every arm of that row has the 234 s horizon (§3). `validate.py` takes the
horizon from `--config`, so it censors that row at 234 s.

## Scoring

```bash
.venv/bin/python assets/station_fahy/validate.py RUN_seed04.sqlite ... RUN_seed23.sqlite \
    --config CFG [--t-jam 86] [--against OTHER_seed04.sqlite ... OTHER_seed23.sqlite]
```

`--against` gives the paired per-seed differences of V3 and V3m on the
same-agent set.
