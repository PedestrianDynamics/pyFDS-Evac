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
    B,
    Div,
    EventStream,
    I,
    Link,
    NotStr,
    P,
    Pre,
    Script,
    Title,
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
    DivLAligned,
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

from . import docs, params, plots, theme, trajviz
from .runner import RunManager

_PLOTLY_CDN = Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js")
# htmx core ships with fast_app(); the SSE extension that powers live progress
# (hx-ext="sse") is separate and must be loaded explicitly.
_HTMX_SSE = Script(src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.3/dist/sse.js")
# KaTeX renders the model equations in the documentation tab.
_KATEX = (
    Link(
        rel="stylesheet",
        href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css",
    ),
    Script(src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"),
    Script(
        src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
    ),
)

# Theme headers load after franken-ui's so the override variables win.
app, rt = fast_app(
    hdrs=(*Theme.blue.headers(), *theme.headers(), _HTMX_SSE, _PLOTLY_CDN, *_KATEX)
)
manager = RunManager()

_TIERS = [
    ("safe", "Safe"),
    ("alert", "Alert"),
    ("critical", "Critical"),
    ("severe", "Severe"),
]


def _header() -> Div:
    legend = Div(
        *[Div(I(cls="sw"), label, cls=f"tier {name}") for name, label in _TIERS],
        cls="tier-legend",
    )
    return Div(
        Div(
            Div(
                Div("pyFDS", B("·EVAC"), cls="brand"),
                Div(I(cls="dot"), "ready", cls="status"),
                cls="brand-line",
            ),
            Div("fire-coupled evacuation · FDS × JuPedSim × ISO 13571", cls="tagline"),
        ),
        legend,
        cls="app-header rise",
    )


def _sidebar() -> Div:
    return Card(
        Subtitle("Parameters", cls="uk-card-title"),
        params.build_form("/run"),
        cls="lg:col-span-1 rise",
        style="animation-delay:.06s",
    )


def _run_panel_idle() -> Div:
    return Div(
        Card(
            Div(
                Div(I(cls="dot"), "Standby", cls="standby-label"),
                P(
                    "Select a scenario and run to stream live telemetry, "
                    "then explore trajectories, FED dose, smoke and route cost.",
                    cls="standby-hint",
                ),
                cls="standby",
            ),
        ),
        id="run-panel",
        cls="lg:col-span-2 rise",
        style="animation-delay:.12s",
    )


# Derive Output-file defaults from the selected scenario name. Fields the user
# has edited (data-user-edited) are left untouched; changing the scenario
# refills the rest. Runs client-side so paths are visible and editable.
_AUTOFILL_JS = """
(function () {
  var OUT = {
    output_sqlite: function (n) { return 'results/' + n + '.sqlite'; },
    output_smoke_history: function (n) { return 'results/' + n + '_smoke_history.csv'; },
    output_fed_history: function (n) { return 'results/' + n + '_fed_history.csv'; },
    output_route_history: function (n) { return 'results/' + n + '_route_history.csv'; },
    output_route_cost_history: function (n) { return 'results/' + n + '_route_cost_history.csv'; }
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


_NAV = NotStr(
    '<div class="tab-nav">'
    '<button class="tab-btn active" data-tab="sim" type="button">Simulation</button>'
    '<button class="tab-btn" data-tab="model" type="button">Model</button>'
    "</div>"
)

_TAB_JS = """
document.addEventListener('click', function (e) {
  var b = e.target.closest && e.target.closest('.tab-btn');
  if (!b) return;
  var t = b.dataset.tab;
  document.querySelectorAll('.tab-btn').forEach(function (x) {
    x.classList.toggle('active', x === b);
  });
  document.getElementById('tab-sim').classList.toggle('hidden', t !== 'sim');
  document.getElementById('tab-model').classList.toggle('hidden', t !== 'model');
  if (t === 'model' && window._renderMath) window._renderMath();
});
"""

_MATH_JS = """
window._renderMath = function () {
  if (!window.renderMathInElement) return;
  renderMathInElement(document.getElementById('tab-model') || document.body, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$', right: '$', display: false }
    ],
    throwOnError: false
  });
};
window._renderMath();
document.addEventListener('DOMContentLoaded', window._renderMath);
"""


@rt("/")
def index():
    body = Div(
        _sidebar(),
        _run_panel_idle(),
        cls="grid grid-cols-1 lg:grid-cols-3 gap-6",
    )
    # Empty overlay container that the directory browser swaps into.
    return (
        Title("pyFDS-Evac · control"),
        _header(),
        _NAV,
        Container(
            Div(body, id="tab-sim"),
            Div(docs.model_docs(), id="tab-model", cls="hidden"),
            cls=ContainerT.xl,
        ),
        Div(id="dir-modal"),
        Script(_AUTOFILL_JS),
        Script(_TAB_JS),
        Script(_MATH_JS),
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

    # Live region (#run-status: progress -> done) plus a streaming console
    # (#console-log: console). sse-close stops HTMX reconnecting once finished.
    return Div(
        Div(_running_card(None), id="run-status", sse_swap="progress,done"),
        Card(
            DivLAligned(UkIcon("terminal"), H3("Console", cls="m-0")),
            Div(
                Pre("Waiting for output…"),
                id="console-log",
                cls="console-box mt-2",
                sse_swap="console",
                # keep the log scrolled to the newest line after each update
                **{"hx-on:htmx:after-swap": "this.scrollTop = this.scrollHeight"},
            ),
            cls="mt-4",
        ),
        hx_ext="sse",
        sse_connect="/progress",
        sse_close="done",
    )


def _console_view() -> Pre:
    text = "\n".join(manager.log_lines[-300:]) or "Waiting for output…"
    return Pre(text)


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
    metrics = [
        ("Status", f"{status} ({result.metrics.get('success')})"),
        ("Evacuation time", f"{result.evacuation_time:.1f} s"),
        ("Evacuated", f"{result.agents_evacuated}/{result.total_agents}"),
        ("Remaining", f"{result.agents_remaining}"),
    ]
    grid = Div(
        *[
            Div(Div(k, cls="metric-k"), Div(v, cls="metric-v"), cls="metric-cell")
            for k, v in metrics
        ],
        cls="metrics-grid",
    )
    body = [grid]
    if manager.artifacts:
        body.append(Div("Artifacts written", cls="metric-k mt-3 mb-1"))
        body.extend(Div(a, cls="artifact") for a in manager.artifacts)
    summary = Card(
        H3(f"Finished: {manager.scenario_name}"),
        Div(*body, cls="mt-1"),
    )

    def plot_card(title, fig, div_id):
        return Card(H3(title), plots.figure_html(fig, div_id))

    return Div(
        summary,
        trajviz.trajectory_component(result, scenario),
        plot_card("Cumulative FED", plots.fed_figure(result), "fig-fed"),
        plot_card("Smoke", plots.smoke_figure(result), "fig-smoke"),
        plot_card("Route cost", plots.route_cost_figure(result), "fig-route"),
        cls="space-y-6",
    )


@rt("/progress")
async def progress():
    # State-based and idempotent: reads manager status/last_event so any
    # (re)connecting stream delivers the same terminal "done" event exactly
    # once, then closes (no queue to race, no competing consumers).
    async def gen():
        last = None
        last_log = -1
        while True:
            # stream captured console output as it grows
            n = len(manager.log_lines)
            if n != last_log:
                last_log = n
                yield sse_message(_console_view(), event="console")

            status = manager.status
            if status == "done":
                yield sse_message(_finished_view(), event="done")
                return
            if status == "error":
                yield sse_message(
                    Alert(f"Run failed: {manager.error}", cls=AlertT.error),
                    event="done",
                )
                return
            if status == "idle":
                return
            ev = manager.last_event
            if ev is not None and ev != last:
                last = ev
                yield sse_message(_running_card(ev), event="progress")
            await asyncio.sleep(0.1)

    return EventStream(gen())


if __name__ == "__main__":
    serve()
