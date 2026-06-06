"""FastHTML + MonsterUI web GUI for pyFDS-Evac.

Layout: a left sidebar parameter form (generated from run.py's flags) and a
main pane that streams live run progress over SSE, then shows interactive
Plotly results. Runs execute in-process on a background thread via RunManager.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import quote

from fasthtml.common import (
    Div,
    EventStream,
    P,
    Script,
    Titled,
    fast_app,
    serve,
    sse_message,
)
from monsterui.all import (
    Alert,
    AlertT,
    Button,
    ButtonT,
    Card,
    Container,
    ContainerT,
    DivFullySpaced,
    DivVStacked,
    H3,
    Loading,
    LoadingT,
    Subtitle,
    Theme,
    UkIcon,
)
from starlette.requests import Request

from pyfds_evac.core import load_scenario
from pyfds_evac.core.run_config import build_run_kwargs

from . import params, plots
from .runner import RunManager

_PLOTLY_CDN = Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js")
# htmx core ships with fast_app(); the SSE extension that powers live progress
# (hx-ext="sse") is separate and must be loaded explicitly.
_HTMX_SSE = Script(src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.3/dist/sse.js")

app, rt = fast_app(hdrs=(*Theme.blue.headers(), _HTMX_SSE, _PLOTLY_CDN))
manager = RunManager()


def _sidebar() -> Div:
    return Card(
        Subtitle("Parameters"),
        params.build_form("/run"),
        cls="lg:col-span-1",
    )


def _run_panel_idle() -> Div:
    return Div(
        P("Configure parameters and run a scenario.", cls="text-muted-foreground"),
        id="run-panel",
        cls="lg:col-span-2",
    )


# Derive Output-file defaults from the selected scenario name. Fields the user
# has edited (data-user-edited) are left untouched; changing the scenario
# refills the rest. Runs client-side so paths are visible and editable.
_AUTOFILL_JS = """
(function () {
  var OUT = {
    output_sqlite: function (n) { return n + '.sqlite'; },
    output_smoke_history: function (n) { return n + '_smoke_history.csv'; },
    output_fed_history: function (n) { return n + '_fed_history.csv'; },
    output_route_history: function (n) { return n + '_route_history.csv'; },
    output_route_cost_history: function (n) { return n + '_route_cost_history.csv'; }
  };
  function scenarioName() {
    var inp = document.querySelector('input[name="scenario"]');
    var sel = document.querySelector('#scenario select');
    return (inp && inp.value) || (sel && sel.value) || '';
  }
  function fill(n) {
    Object.keys(OUT).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.dataset.userEdited) el.value = n ? OUT[id](n) : '';
    });
  }
  // Poll the scenario value: robust regardless of how the select widget
  // reports changes. Refills only when the scenario actually changes.
  var last = null;
  setInterval(function () {
    var n = scenarioName();
    if (n !== last) { last = n; fill(n); }
  }, 250);
  // Stop auto-filling a field once the user edits it.
  document.addEventListener('input', function (e) {
    if (e.target && OUT[e.target.id]) e.target.dataset.userEdited = '1';
  });
})();
"""


@rt("/")
def index():
    body = Div(
        _sidebar(),
        _run_panel_idle(),
        cls="grid grid-cols-1 lg:grid-cols-3 gap-6",
    )
    # Empty overlay container that the directory browser swaps into.
    return Titled(
        "pyFDS-Evac",
        Container(body, cls=ContainerT.xl),
        Div(id="dir-modal"),
        Script(_AUTOFILL_JS),
    )


# Directory browser confined to the user's home tree (a localhost dev tool).
_DIR_ROOT = Path.home()


def _safe_dir(path: str) -> Path:
    """Resolve a requested path, clamped to the home tree; default = repo root."""
    candidate = Path(path) if path else params._REPO_ROOT
    try:
        resolved = candidate.resolve()
    except Exception:
        return _DIR_ROOT
    if resolved != _DIR_ROOT and _DIR_ROOT not in resolved.parents:
        return _DIR_ROOT
    return resolved if resolved.is_dir() else _DIR_ROOT


_CLOSE_MODAL = "document.getElementById('dir-modal').innerHTML=''"


def _nav_row(label: str, target: Path, mode: str, field: str):
    """A folder row that navigates the picker into ``target``."""
    href = f"/browse-dir?path={quote(str(target))}&mode={mode}&field={field}"
    return Button(
        UkIcon("folder"),
        label,
        type="button",
        hx_get=href,
        hx_target="#dir-modal",
        hx_swap="innerHTML",
        cls=(ButtonT.ghost, "w-full justify-start"),
    )


def _file_row(target: Path, field: str):
    """A file row that selects ``target`` into ``field`` and closes the modal."""
    pick = f"document.getElementById({json.dumps(field)}).value={json.dumps(str(target))};{_CLOSE_MODAL}"
    return Button(
        UkIcon("file"),
        target.name,
        type="button",
        onclick=pick,
        cls=(ButtonT.ghost, "w-full justify-start"),
    )


@rt("/browse-dir")
def browse_dir(path: str = "", mode: str = "dir", field: str = "fds_dir"):
    current = _safe_dir(path)
    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        entries = []
    subdirs = sorted(
        (e for e in entries if e.is_dir() and not e.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )

    rows = []
    if current != _DIR_ROOT:
        rows.append(_nav_row("..", current.parent, mode, field))
    rows.extend(_nav_row(d.name, d, mode, field) for d in subdirs)
    if mode == "file":
        files = sorted(
            (e for e in entries if e.is_file() and not e.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
        rows.extend(_file_row(f, field) for f in files)
    if not rows:
        rows.append(P("Empty folder.", cls="text-sm text-muted-foreground p-2"))

    title = "Select a folder" if mode == "dir" else "Select a file"
    footer = [
        Button("Cancel", type="button", onclick=_CLOSE_MODAL, cls=ButtonT.secondary)
    ]
    if mode == "dir":
        use = f"document.getElementById({json.dumps(field)}).value={json.dumps(str(current))};{_CLOSE_MODAL}"
        footer.append(
            Button("Use this folder", type="button", onclick=use, cls=ButtonT.primary)
        )

    dialog = Card(
        H3(title),
        P(str(current), cls="text-sm text-muted-foreground break-all mb-2"),
        Div(*rows, cls="max-h-72 overflow-auto my-2 divide-y rounded border"),
        DivFullySpaced(*footer, cls="mt-3"),
        cls="w-[36rem] max-w-[90vw]",
    )
    return Div(
        dialog,
        cls="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4",
    )


@rt("/run")
async def post(request: Request):
    form = dict(await request.form())
    scenario_name = form.get("scenario")
    if not scenario_name:
        return Alert("Select a scenario first.", cls=AlertT.error)

    try:
        scenario = load_scenario(f"assets/{scenario_name}")
        opts = params.form_to_opts(form)
        run_kwargs = build_run_kwargs(scenario, opts)
        import run as cli  # shared CLI helpers (apply_outputs)

        def post_run(result):
            return cli.apply_outputs(result, scenario, opts, log=lambda _m: None)

        manager.start(scenario, run_kwargs, scenario_name, post_run=post_run)
    except Exception as exc:
        return Alert(f"{type(exc).__name__}: {exc}", cls=AlertT.error)

    # Single live region: progress events update it, done/error replace it.
    return Div(
        Div(_running_card(None), id="run-status", sse_swap="progress,done,error"),
        hx_ext="sse",
        sse_connect="/progress",
    )


def _running_card(ev) -> Div:
    line = (
        f"evacuated {ev.evacuated}/{ev.total} · sim {ev.sim_time:.1f}s · "
        f"wall {ev.wall_time:.0f}s · {ev.pct}%"
        if ev
        else "Initialising…"
    )
    return Card(
        DivVStacked(
            H3(f"Running: {manager.scenario_name}"),
            Div(Loading(cls=LoadingT.dots), P(line, cls="inline ml-2")),
        )
    )


def _finished_view() -> Div:
    result = manager.result
    scenario = None
    try:
        scenario = load_scenario(f"assets/{manager.scenario_name}")
    except Exception:
        pass

    status = "finished" if result.agents_remaining == 0 else "stopped"
    rows = [
        P(f"Status: {status} ({result.metrics.get('success')})"),
        P(f"Evacuation time: {result.evacuation_time:.1f} s"),
        P(f"Evacuated: {result.agents_evacuated}/{result.total_agents}"),
        P(f"Remaining: {result.agents_remaining}"),
    ]
    if manager.artifacts:
        rows.append(P("Artifacts written:", cls="font-semibold mt-2"))
        rows.extend(P(a, cls="text-sm break-all") for a in manager.artifacts)
    summary = Card(
        H3(f"Finished: {manager.scenario_name}"),
        DivVStacked(*rows, cls="space-y-1"),
    )

    def plot_card(title, fig, div_id):
        return Card(H3(title), plots.figure_html(fig, div_id))

    return Div(
        summary,
        plot_card(
            "Trajectories", plots.trajectories_figure(result, scenario), "fig-traj"
        ),
        plot_card("Cumulative FED", plots.fed_figure(result), "fig-fed"),
        plot_card("Smoke", plots.smoke_figure(result), "fig-smoke"),
        plot_card("Route cost", plots.route_cost_figure(result), "fig-route"),
        cls="space-y-6",
    )


@rt("/progress")
async def progress():
    async def gen():
        while True:
            item = manager.try_get()
            if item is None:
                await asyncio.sleep(0.1)
                continue
            kind, payload = item
            if kind == "progress":
                yield sse_message(_running_card(payload), event="progress")
            elif kind == "done":
                yield sse_message(_finished_view(), event="done")
                break
            elif kind == "error":
                yield sse_message(
                    Alert(f"Run failed: {payload}", cls=AlertT.error), event="error"
                )
                break

    return EventStream(gen())


if __name__ == "__main__":
    serve()
