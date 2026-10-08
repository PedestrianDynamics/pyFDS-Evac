# FDS+Evac guide input decks

The 182 `.fds` input files of the FDS+Evac guide (Korhonen, *FDS+Evac:
Technical Reference and User's Guide*), copied unchanged from
[tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide) at
commit `10eb1a4448ae771ad2187a238a8330c819550008`, folder `InputFiles/`.
The folder tree is kept: `Examples/`, `Validation/` and `Verification/`.

The files are unmodified. Do not edit them; to change a deck, copy it to
a new location outside this folder and mark it as modified (GPLv3 §5
requires a notice stating the change and its date).
`SHA256SUMS`, computed from the upstream repository at the pinned commit,
holds each deck's checksum; `tests/test_fds_evac_guide_assets.py` fails on
any changed, added or removed deck.

## License

These files are licensed under the GNU General Public License, version 3
(`GPL-3.0-only`), as the source repository is; the license text is
[`LICENSES/GPL-3.0-only.txt`](../../LICENSES/GPL-3.0-only.txt). They are
not covered by pyFDS-Evac's MIT license. [`REUSE.toml`](../../REUSE.toml)
records this per path.

The folder is excluded from the wheel and the sdist, so the published
packages contain no GPL files.

## What it is for

Reference input for the FDS deck importer (`pyfds-evac import`): legacy
FDS+Evac decks with `&EXIT`, `&EVAC`, `&PERS` and the other evacuation
namelists, written by the author of FDS+Evac. They are not pyFDS-Evac
scenarios and have no `config.json`.

For runnable bundles, see the separate [converted collection](../fds_evac_guide_converted/README.md):
94 single-floor scenarios, fire-only FDS inputs where applicable, and a batch
runner. Its README documents adjustments, verification limits and 88 exclusions.

The guide's manual, figures and reference results are not copied here;
cite the guide instead.
