# pyFDS-Evac Web GUI — Design Spec

Date: 2026-06-06
Status: Approved (pending spec review)

## Goal

A responsive, local web GUI to configure and run pyFDS-Evac scenarios,
watch a run progress live, and explore results with interactive plots.
The terminal CLI (`run.py`) remains the canonical interface; the GUI is a
thin alternative front-end that shares the same execution path so the two
never diverge.

Stack: [FastHTML](https://fastht.ml/) + [MonsterUI](https://monsterui.answer.ai/),
charts via Plotly.js (CDN). Single local user, one active run at a time.

## Non-goals

- Multi-user / authentication / deployment beyond localhost.
- Concurrent runs or a job queue.
- Live in-browser trajectory animation *during* a run (results are
  animated post-run via a time scrubber, not streamed mid-run).
- Editing scenario `config.json` content (agent counts, sources,
  geometry) from the GUI. The GUI sets run-time options (the CLI flag
  surface); scenario definition stays file-based.

## Architecture

Served via `app.py` at repo root (`uv run app.py` → `http://localhost:5001`).
`run_scenario()` is called **in-process on a background thread**; a single
active run is enforced by a lock.

```
app.py                          # entry point, serves the FastHTML app
pyfds_evac/webapp/__init__.py
pyfds_evac/webapp/app.py        # routes + MonsterUI layout
pyfds_evac/webapp/runner.py     # RunManager: threaded run + thread-safe progress queue
pyfds_evac/webapp/params.py     # argparse introspection -> form spec; form POST -> opts dict
pyfds_evac/webapp/plots.py      # ScenarioResult + sqlite -> Plotly JSON traces
pyfds_evac/core/run_config.py   # NEW shared builder: opts dict -> run_scenario kwargs
tests/test_run_config.py
tests/test_webapp.py
```

### Shared option builder (`core/run_config.py`)

`run.py`'s `main()` currently wires ~30 argparse flags into the model
config objects (`SmokeSpeedConfig`/`SmokeSpeedModel`, `DefaultFedModel`,
`TenabilityConfig`, `RerouteConfig`, `VisibilityModel`) and into output
options inline. This wiring is extracted into:

```python
def build_run_kwargs(opts: dict) -> RunPlan:
    """Translate a flat options dict (same keys as run.py flags) into the
    objects run_scenario() needs plus output/export directives."""
```

`RunPlan` carries: `run_scenario` kwargs (models/configs/flags) and the
output directives (sqlite copy, cleanup, history CSVs, SMV export,
export-only). Both `run.py` and the webapp call `build_run_kwargs`, so the
GUI and CLI produce identical runs from identical options. `run.py.main()`
is refactored to delegate to it; its observable behavior is unchanged.

Validation rules currently enforced by `argparse`/`parser.error` (e.g.
`--smv-export requires --fds-dir`, `--vis-cache requires --enable-rerouting`)
move into `build_run_kwargs` and raise `ValueError`; `run.py` maps those to
`parser.error`, the webapp maps them to a form error message.

### Required core change (`core/scenario.py`)

Add an optional parameter to `run_scenario`:

```python
progress_callback: Callable[[ProgressEvent], None] | None = None
```

`ProgressEvent` is a small frozen dataclass:
`(evacuated: int, total: int, sim_time: float, wall_time: float, pct: int)`.

The existing stdout `\rEvacuated…` block is preserved unchanged for CLI
use. When `progress_callback` is not `None`, the same loop also constructs
and emits a `ProgressEvent` at the existing throttle cadence (every 0.5 s
or on agent-count change). Default `None` ⇒ behavior is byte-for-byte
identical to today (regression-tested).

### Run manager (`webapp/runner.py`)

`RunManager` holds at most one active run:

- `start(plan: RunPlan)`: acquires the run lock (rejects if a run is
  active), spawns a `threading.Thread` that calls `run_scenario(...,
  progress_callback=self._queue.put)`, stores the resulting
  `ScenarioResult` (or the exception) on completion, releases the lock.
- A thread-safe `queue.Queue` carries `ProgressEvent`s plus terminal
  sentinels (`done`, `error`).
- State exposed to routes: `idle | running | done | error`, last result,
  last error.

Threading is the starting point. Risk: if JuPedSim's C-extension does not
release the GIL, SSE progress may stutter. If observed, fall back to a
`multiprocessing` worker (progress over a `multiprocessing.Queue`); the
`RunManager` interface is designed so this swap is internal.

### Routes (`webapp/app.py`)

- `GET /` — full page: sidebar form + empty main pane.
- `POST /run` — parse form → `opts` → `build_run_kwargs` → `RunManager.start`;
  return the live-progress panel (which opens the SSE stream). Form errors
  (ValueError from the builder, or run-already-active) render inline.
- `GET /progress` (SSE) — drains the progress queue, emitting
  MonsterUI-formatted progress lines; on the terminal sentinel, swaps in
  the results view (or error view).
- `GET /results/<tab>` — renders a results tab's Plotly figure JSON on
  demand (trajectories / FED / route cost / smoke / metrics).
- `GET /scenarios` — lists scenario directories under `assets/` for the
  picker.

### Form generation (`webapp/params.py`)

The form is generated by introspecting `run.py`'s argparse parser
(`_build_parser()`), so **every flag** is represented and new flags appear
automatically:

- `store_true` → checkbox; `type=float|int` → number input; `type=str`
  with a small known value set (e.g. `--smoke-update-interval`, paths) →
  text/number; `--scenario` → select populated from `assets/`.
- Flags are grouped for display: Core, Smoke, FED & Tenability, Rerouting,
  Visibility, SMV, Output/Export. Grouping is a static map keyed by flag
  name; flags not in the map fall into "Other" so nothing is dropped.
- Help strings become field tooltips/labels.
- POST handler reverses the mapping into a flat `opts` dict whose keys
  match the argparse `dest` names — the same keys `build_run_kwargs`
  consumes.

### Results & plots (`webapp/plots.py`)

After a run, `plots.py` builds Plotly figure JSON (trace dicts emitted as
JSON; Plotly.js loaded from CDN — no Python Plotly dependency):

- **Trajectories** — per-agent x/y paths from the run's SQLite (read via
  `pedpy`, mirroring `scripts/plot_trajectories.py`), coloured by assigned
  exit (from `route_cost_history`), drawn over walkable geometry and exit
  polygons parsed from `config.json`. Includes a time-step scrubber
  (Plotly slider/animation frames).
- **FED history** — from `ScenarioResult.fed_history` (in memory).
- **Route-cost history** — from `route_cost_history`.
- **Smoke history** — from `smoke_history`.
- **Metrics** — summary card from `ScenarioResult.metrics` (success,
  evacuation time, evacuated/remaining, totals).

Tabs render lazily via `GET /results/<tab>` so the page stays responsive.

### UI layout (MonsterUI)

Responsive two-column grid. Left sidebar: scenario picker + accordion
groups of all flags + Run button. Main pane: live progress panel →
results tabs. Collapses to single column on narrow viewports.

## Dependencies

New optional extra `[gui]` in `pyproject.toml`: `python-fasthtml`,
`monsterui`. Plotly.js via CDN `<script>`. `pedpy` already present.
Installed with `uv sync --extra gui`.

## Testing

- `test_run_config.py`: `build_run_kwargs` reproduces the existing
  `run.py` wiring for representative flag combinations (constant
  extinction, FDS dir + smoke, rerouting + vis-cache, tenability toggles,
  SMV export); validation errors raise `ValueError`.
- `scenario` regression: `run_scenario` with no `progress_callback`
  returns the same `ScenarioResult` as before (guards the core change).
- `test_webapp.py` (Starlette `TestClient`): `GET /` → 200; a run on a
  small fast scenario (`assets/basic`) reaches `done` with metrics
  present; the progress queue yields ≥1 `ProgressEvent`; a second
  `start()` while running is rejected.

## Out-of-scope / future

- Comparison view (run A vs run B side by side).
- Persisting run history across app restarts.
- multiprocessing execution backend (only if threading stutters).
- Live mid-run trajectory streaming.

## README / paper note

Per project convention, `README.md` gains a "Web GUI" section
(install + `uv run app.py`). No paper change: the GUI is tooling, not a
model feature.
