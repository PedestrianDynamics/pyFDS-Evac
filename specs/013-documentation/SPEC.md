# 013 — Documentation plan

## Problem

The documentation decides whether pyFDS-Evac gets adopted, but it grew by
accretion. The material is good, but it is spread across five places:
`README.md`, 14 files in `docs/`, 6 pages in `site/content/models/`,
`tests/verification/README.md` and the asset READMEs. Nothing in it
answers the first questions a newcomer asks:

1. *What do I import?* `pyfds_evac/__init__.py` exports nothing.
   `run_scenario` and `load_scenario` live in `pyfds_evac.core.scenario`,
   and the module docstring (`scenario.py:7`) shows a wrong import path.
2. *Can I try it without running FDS?* Yes, but no page says how. A public
   path already exists: `ConstantExtinctionField` and the
   `--constant-extinction` flag (`run.py:53`). FDS output is also
   tracked for `assets/iso_table21_coupled/fds/` (28 kB, runs in ~10 s)
   and `assets/iso_table22_coupled/fds/{a,b,c,d}`.
3. *Which entry point do I use?* The options are `run.py`,
   `run_scenario()` / `build_run_kwargs()`, the web GUI and
   `scripts/run_and_plot.sh`.
4. *I used FDS+Evac. Where did my inputs go, and what is lost?* Only one
   row of `model-comparison.md` addresses this.
5. *Can I trust a result?* The evidence exists but is hard to find, and
   some of it is mislabelled. The `ISO-table21/22` assets are ISO 20414
   Tests 18/19, but the docs call them ISO 13571 (`usage.md:320`).
   `model-comparison.md` also contradicts the code (see Corrections).

Some topics are covered twice or three times. Routing appears in
`docs/routing.md`, `models/routing.md` and `docs/route-cost-gate.md`.
Smoke speed appears in `docs/smoke-speed-model.md` and
`models/smoke-speed.md`.

The biggest adoption risk is not a failed run. It is a run that succeeds
while the user cannot tell whether the result means anything. A case with
a missing gas slice finishes with FED disabled (no FED history, no `fed_max`;
see #137), which is easy to read as a genuinely safe case.

## Status and scope of the software

The software is maintained by one researcher at Forschungszentrum Jülich
(IAS-7). pyFDS-Evac is **research software, provided without warranty**.
It is not intended for regulatory or design use, and it has no release
policy yet. The docs say this on the index page and on the Limitations
page, and they do not suggest otherwise anywhere.

**The docs describe what is implemented, not what is planned.** Missing
features appear only on the Limitations page, as "not supported", with a
link to their issue. A feature is documented in the same pull request that
implements it. Two such issues exist:
- FED activity level: [#135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135).
- Per-exit familiarity: [#136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136).

## Principles

1. **Say what is checked, and say what is not.** Every model claim links
   to its evidence, or says "not tested" and why. A green docs build shows
   that an example runs, not that its result is right, so the docs never
   claim that examples "cannot rot".
2. **Readers enter by their situation; pages are sorted by type.** The
   index offers four entrances. Each one is a short, ordered path through
   shared pages, so no content is written twice. Diátaxis is an editing
   discipline, not the navigation.
3. **Document the code as it is.** Build on the paths that already work.
   Change code only where a page cannot be written without it (spec 014).
4. **Put interpretation first.** The engineer needs one-way coupling, the
   separate dose tracks and the parameter split in order to read a
   result, so these come early. Developer internals sit behind the
   contributor entrance. That includes object lifecycles, the API
   reference, commit hashes and phase labels.

## Reference design

The layout model is <https://scenarios.jupedsim.org/>. We copy its
structure, not its toolchain:

| Section | What it does | Page anatomy |
|---|---|---|
| Index | Pitch, install, a 5-line quick start, where to next, citation, status | One screen |
| Quickstart / tutorial | One guided run on a tiny scenario shipped with the repo | Executed notebook |
| Concepts | The object model and the rules that "prevent most surprises" | Prose + short snippets |
| Choosing an entrypoint | A table mapping "You want to…" to a call and an example | Table |
| How-tos | One question per page, titled as a question and grouped by goal | Short executed notebook |
| Cookbook | Complete studies with a reference, a sweep, a figure and a CI | Executed notebook |
| CLI, API reference | Every flag and every public name | Generated |
| Troubleshooting | Symptom → cause → wrong/right code | Prose |

## Audiences and entrances

| Entrance (on index) | Reader | Path |
|---|---|---|
| **Coming from FDS+Evac** | Fire safety engineer with an FDS+Evac deck; knows FDS well, Python moderately | FDS+Evac guide → Your FDS case → Real-FDS walkthrough → Limitations → Verification |
| **Assess and run your case** | Engineer or researcher with a finished FDS run | Quickstart → Your FDS case → Real-FDS walkthrough → Concepts → Limitations |
| **Reproduce a study** | Researcher | Models → Verification → Ensemble how-to → Cite |
| **Integrate and contribute** | Developer | Concepts → Public API → Verification suite → Dev notes |

## Toolchain: Hugo/hextra (decided)

The site stays on Hugo at <https://pedestriandynamics.org/pyFDS-Evac/>
and is deployed by `docs.yml`. The `../docs → content/docs` mount, the
`*-notes.md` exclusion and the Slidev `clean-exclude` stay as they are.

Phase 1 needs no new Hugo machinery. Code on pages comes from
scripts in a top-level `examples/` directory, which `tests.yml` runs. The
code is pasted into the page by hand, and a test checks that the pasted
code matches the script.

`examples/` must not go under `docs/`: the `docs/` mount would publish it,
because `excludeFiles` covers only `*-notes.md`.

Deferred to phase 2, after a spike:
- An `include-code` shortcode. `readFile` probably cannot read outside
  `site/` (inferred from Hugo's source, not tested). The alternative is
  to mount `examples/` into `assets/` and read it with
  `resources.Get … | .Content`.
- The generated CLI reference, from `run.py:_build_parser()`, with no new
  dependency.
- The generated API reference.

## Prerequisite code changes (spec 014)

These are code changes, so they get their own spec and pull request. The
docs describe the code, and they land after it.

1. **Fix the local build.** `uv sync` / `uv run` currently fail to build
   the package: hatchling → pathspec → `typing_extensions` is missing
   from the build environment. One fix is
   `[tool.uv.extra-build-dependencies]`. CI (`tests.yml`) is green, so
   the failure is local only.
2. **Lazy public re-exports.** Add a PEP 562 `__getattr__` in
   `pyfds_evac/__init__.py`. Eager imports are ruled out: importing
   `pyfds_evac.core` takes about 3 s cold, because `simulation_init`
   pulls in pandas and matplotlib, and every webapp and script import
   would pay that. The exported names are:
   - Scenarios: `load_scenario`, `run_scenario`, `build_run_kwargs`,
     `Scenario`, `ScenarioResult`, `ProgressEvent`.
   - Smoke speed: `SmokeSpeedModel`, `SmokeSpeedConfig`,
     `ExtinctionField`, `ConstantExtinctionField`.
   - FED: `DefaultFedModel`, `DefaultFedConfig`, `FdsFedField`,
     `DefaultHeatFedModel` (not exported from `core` today), `FdsHeatField`,
     `TenabilityConfig`.
   - Routing and visibility: `RerouteConfig`, `RouteCostConfig`,
     `VisibilityModel`.

   `load_slice_sampler` stays internal. It fills no `run_scenario`
   keyword, because it returns a `SliceFieldSampler` with `sample()`, not
   `sample_extinction()`. `pyfds_evac/core/__init__.py` has uncommitted
   work that already re-exports most of these names, and that work has to
   land first.
3. **`fds_dir` defaults to `None`** in `SmokeSpeedConfig` and
   `DefaultFedConfig` (`smoke_speed.py:86`, `fed.py:40`), so a synthetic
   run needs no fake directory.
4. **Fix the docstring** import path at `scenario.py:7`.
5. **Run manifest.** `run_scenario` writes `manifest.json` next to the
   trajectory. It records the versions of pyFDS-Evac, JuPedSim, fdsreader
   and fdsvismap, the `uv.lock` hash, the seed, the scenario path and the
   FDS version from the `.smv` `FDSVERSION` line. Estimated effort: about
   half a day.

## Phase 1 — smallest shippable slice

1. **Quickstart** (`examples/quickstart.py`): a synthetic smoke run on a
   tracked asset, built with `ConstantExtinctionField`. It uses no new
   package code beyond spec 014, and CI runs it.
2. **Real-FDS walkthrough** on the tracked `iso_table21_coupled` output.
   It goes from FDS output to the run, the FED histories and the exit
   times. It ends with a **"successful but wrong" checkpoint**: the same
   run with one gas slice missing also finishes, with FED disabled (#137), and
   the page teaches the reader how to detect this. The FED part uses
   `iso_table22_coupled/fds/a`, because `iso_table21_coupled` has only the
   extinction slice.
3. **One engineering how-to**: *How do I get the egress time and its spread
   from an ensemble of seeds?* It reports last-exit times from the
   trajectory, not `evacuation_time` (#141) or `success` (#139), and reads
   the run manifest (spec 014).
4. **Trust repairs:**
   - Audit `model-comparison.md` against the code, and delete §8 ("PDF
     claims vs reality").
   - Relabel `ISO-table21/22` as ISO 20414 Tests 18/19 in `usage.md:320`,
     `assets.md` and the page cards.
   - Remove commit hashes, `evac.f90` line numbers and "Phase n" labels
     from user-facing pages.
5. **"Coming from FDS+Evac"** as a single page:
   - A table mapping each concept to its new key or step. For example,
     pre-movement is configurable in the JSON
     (`simulation_init.py:933-939`), and the walkable area comes from
     `generate_walkable_from_fds.py`.
   - What is lost.
   - What needs Python, for example the smoke-speed parameters.
   - Anything unsupported links to its issue (#135, #136).
6. **Limitations and a verification status table.**
   - Limitations states the research-software status first, then the
     parameter split, then what is not modelled:
     - radiant heat;
     - heat does not affect route choice or speed;
     - multi-floor buildings and stairs;
     - FED activity level (#135);
     - per-exit familiarity (#136).
     It also states that only aggregate outcomes reproduce under a fixed
     seed.
   - Verification holds a test-by-test table against ISO 20414. Tests
     18/19 come first. Then come the tests in scope but not yet run, then
     the tests out of scope, each with a one-line reason.
   - Movement verification is inherited from JuPedSim, with a link to its
     evidence. Every page states that it shows verification, not
     validation.

Exit criteria:
- A new user finishes the quickstart in under 5 minutes on a fresh
  `uv sync`, without FDS.
- An FDS+Evac user reaches Limitations within two clicks of the index.
- No page contradicts the code.

## Phase 1 status (2026-09-26)

Implemented on branch `docs/phase1-foundations` and not yet committed. Every
item above is done. Issues found while writing the docs: #137, #138, #139,
#140, #141, #142, #143, #144, #145. Each affected page documents the current
behaviour and links its issue.

## Later phases

- **Phase 2 — structure.**
  - Build the four-entrance index.
  - Merge the duplicate routing and smoke-speed pages, with `aliases` on
    the surviving page of each merge.
  - Update the cards in `site/content/docs/_index.md`, which link pages
    that will be merged away.
  - Write Concepts, then shrink the README.
  - Run the `readFile`/`resources.Get` spike and add `site/archetypes/`.
- **Phase 3 — reference.** Generate the CLI reference, then the API
  reference over the lazy public surface.
- **Phase 4 — more how-tos, driven by user questions:**
  - pre-movement distributions;
  - sensitivity sweeps;
  - the FED 0.3 threshold for sensitive populations;
  - generating walkable geometry from FDS;
  - loading results into PedPy.
- **Phase 5 — cookbook, one recipe at a time:**
  - ISO 20414 Tests 18/19;
  - FIC vs FED speed;
  - T-junction exit choice;
  - staff vs visitors;
  - Fahy station;
  - blind-spawn discovery.
- **Phase 6 — citation.** Add the `cite` and `references` shortcodes over
  `site/data/references.yaml`, get a Zenodo DOI, and link the paper.

**Dropped:**
- tracking `t_junction` output (the deck only; full output would be tens
  of MB and would be published through the `static/` mount);
- promoting `tests/verification/fields.py` to public API (the synthetic
  gas fields are in `harness.py` anyway);
- `load_slice_sampler` in the public API;
- the pytest harness as a user entrance;
- a claim-to-evidence register (the verification table replaces it);
- the claim that the existing URLs stay unchanged (use `aliases`).

## Migration of existing pages

| Current | Target | Action | Phase |
|---|---|---|---|
| `README.md` | Index | Shrink to pitch, status, install, quick start and links | 2 |
| `site/content/_index.md` | Index | Four entrances, research-software status | 2 |
| `site/content/docs/_index.md` (cards) | Section index | Repoint the cards at the merged pages | 2 |
| `site/content/models/_index.md`, `talks/_index.md` | same | Keep | — |
| `docs/usage.md` | CLI reference + How-tos | Split; fix the ISO label now | 1 / 3 |
| `docs/fds-case-requirements.md` | Your FDS case | Keep; link from the walkthrough | 1 |
| `docs/fds-sampling.md` | Concepts + API | Merge | 2 |
| `docs/assets.md` | Cookbook index | Merge; fix the ISO label now | 1 / 5 |
| `docs/smoke-speed-model.md` + `models/smoke-speed.md` | Models / smoke speed | Merge, with `aliases` | 2 |
| `docs/routing.md` + `models/routing.md` + `docs/route-cost-gate.md` | Models / routing | Merge, with `aliases` | 2 |
| `models/fed.md`, `models/visibility.md` | Models | Keep | — |
| `models/verification.md` + `tests/verification/README.md` | Verification | Add the ISO 20414 status table; keep the catalogue in the tests README | 1 |
| `docs/model-comparison.md` | Models / FDS+Evac comparison | **Audit against the code**, delete §8 | 1 |
| `docs/testing-{homogeneous,heat,familiarity}.md` | Verification subpages | Move | 2 |
| `docs/*-notes.md`, `docs/superpowers/`, `docs/archive/` | `dev/` (unpublished) | Move out of the site | 2 |
| `notebooks/fds-evac.ipynb` | Real-FDS walkthrough | Rewrite against the public API as `examples/walkthrough.py` | 1 |
| `assets/*/README.md` | Cookbook recipes | Link, do not copy | 5 |

## Corrections (apply regardless of phase)

- `model-comparison.md` contradicts the code and itself:
  - It says incapacitation means "route is rejected" (l. 376), but the
    agent stops.
  - It says "Temperature: not implemented" (l. 379), but convective heat
    FED ships.
  - It orders routes by optical depth in §2 but by travel time under
    Advantages.
  - It says "sight test falls back", but `usage.md` says "the gate reads
    no vismap".
- `ISO-table21/22` are ISO 20414 Tests 18/19, not ISO 13571.
- The web GUI needs `uv sync --extra gui` before `uv run app.py`.
- "Gate" has three meanings in the current pages (the route-cost gate,
  the sight gate, and a removed second gate). `tau` means optical depth
  here but a relaxation time in FDS+Evac. The glossary fixes both, and
  the FDS+Evac guide warns about `tau`.

## Writing conventions

- **Page types stay distinct, with one exception.** Tutorials teach,
  how-tos answer one question, Concepts and Models explain, and reference
  pages list. The exception is walkthroughs, which may include short
  interpretation checkpoints ("if FED stays 0, check …").
- **Units everywhere.** Use SI and state the unit in every table and axis
  label. Write extinction coefficient as *K* [1/m] and visibility as
  *S* = *C*/*K* [m].
- **Terminology.** Keep one glossary, with FDS+Evac equivalents where they
  exist. The terms are extinction coefficient, optical depth, FED, FIC,
  tenability, incapacitation, familiarity tier, cognitive map, gate and
  stage. "Cognitive map" is defined as the graph of stages an agent knows,
  not in the psychological sense.
- **Executed examples** use fixed seeds and small agent counts, so CI
  stays fast.
- **Troubleshooting** entries are titled with the symptom (the exact
  error text where there is one), followed by the cause, the fix and how
  to confirm the fix.

### Scientific standard for Models, Verification and Cookbook

These are the pages that reviewers and fire engineers cite, so they are
held to the standard of a methods paper.

- **Prose, not bullets.** Explanation is written in paragraphs. Lists are
  kept for parameter tables, input requirements and flags.
- **Model pages** are structured like a Methods section:
  - *Basis:* the source law and the data it was fitted to.
  - *Implementation:* the equation as coded, and what is sampled from FDS
    and when.
  - *Parameters:* each with its default, unit and source, quoted from the
    code.
  - *Scope:* the conditions the law was derived under. For example, the
    K range of the Frantzich–Nilsson and Fridolf/Jin laws, shown on the
    same page.
- **Verification pages** state the design (control, treatment and null
  field), the reference solution, the tolerance and the number of seeds.
  Aggregate outcomes are given with their spread, never from a single run.
- **Verification is not validation.** Every page that shows agreement
  says which of the two it is.
- **Claims are calibrated.** Established facts go in the present tense
  with a citation. Findings from a run go in the past tense with their
  conditions ("*k* of *N* agents rerouted over *n* seeds").
- **Citations** are author–year in the text, with a DOI and the primary
  source. Every DOI is checked.
- **Abbreviations are defined at first use on every page**, because
  readers arrive by search.
- **Figures stand alone.** The caption gives the scenario, *N* agents,
  *n* seeds, what the shading means and the units. Every figure can be
  regenerated from a script, and the palette is colour-blind-safe.
- **Notation is fixed once.** A notation table on the Concepts page is
  shared by the Models pages and the paper.

### Page templates

| Type | Skeleton |
|---|---|
| README | What it does → Status (research software, no warranty) → Install → Quick start → Docs links → Cite → License |
| Tutorial / walkthrough | Goal → Prerequisites (extras, FDS output or not, runtime) → Steps, each with its expected output → Checkpoint → Next steps |
| How-to | Question as title → One-sentence answer → Runnable example → Expected output → Related options → See also |
| API | Purpose → Parameters (types, units, constraints) → Returns → Raises → Runnable example |
| CLI | Command → Flag table (flag, type, default, unit, the `run_scenario` keyword it sets) → 2–3 invocations |
| Troubleshooting | Symptom → Likely cause → Fix → Confirmation |

Setup requirements come before usage. A page that needs FDS output, the
`gui` extra or fdsvismap says so in its first lines.

### Definition of done (per page)

- Every code block comes from `examples/`, which CI runs, or is a shell
  command that CI also runs.
- Every documented behaviour and default was checked against the current
  code. Nothing planned or unimplemented is described as available.
- Every error the page mentions comes with its cause and a fix.
- Terms match the glossary. "Simply", "just" and "easily" are not used
  for steps that can fail.
- Sentences are short and active, and there is no marketing language.

## Open questions

- Who lands the uncommitted `core/__init__.py` work that spec 014
  depends on?
- API reference generator (phase 3): add a dev dependency
  (griffe/pydoc-markdown, or pdoc as standalone HTML), or write an in-repo
  `inspect` script?
