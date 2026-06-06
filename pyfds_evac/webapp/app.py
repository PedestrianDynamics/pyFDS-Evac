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


@rt("/")
def index():
    body = Div(
        _sidebar(),
        _run_panel_idle(),
        cls="grid grid-cols-1 lg:grid-cols-3 gap-6",
    )
    # Empty overlay container that the directory browser swaps into.
    return Titled("pyFDS-Evac", Container(body, cls=ContainerT.xl), Div(id="dir-modal"))


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


def _dir_row(label: str, target: Path):
    return Button(
        UkIcon("folder"),
        label,
        type="button",
        hx_get=f"/browse-dir?path={quote(str(target))}",
        hx_target="#dir-modal",
        hx_swap="innerHTML",
        cls=(ButtonT.ghost, "w-full justify-start"),
    )


@rt("/browse-dir")
def browse_dir(path: str = ""):
    current = _safe_dir(path)
    try:
        subdirs = sorted(
            (d for d in current.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except (PermissionError, OSError):
        subdirs = []

    rows = []
    if current != _DIR_ROOT:
        rows.append(_dir_row("..", current.parent))
    rows.extend(_dir_row(d.name, d) for d in subdirs)
    if not rows:
        rows.append(P("No sub-folders.", cls="text-sm text-muted-foreground p-2"))

    close = "document.getElementById('dir-modal').innerHTML=''"
    use = f"document.getElementById('fds_dir').value={json.dumps(str(current))};{close}"
    dialog = Card(
        H3("Select FDS directory"),
        P(str(current), cls="text-sm text-muted-foreground break-all mb-2"),
        Div(*rows, cls="max-h-72 overflow-auto my-2 divide-y rounded border"),
        DivFullySpaced(
            Button("Cancel", type="button", onclick=close, cls=ButtonT.secondary),
            Button("Use this folder", type="button", onclick=use, cls=ButtonT.primary),
            cls="mt-3",
        ),
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
        manager.start(scenario, run_kwargs, scenario_name)
    except Exception as exc:
        return Alert(f"{type(exc).__name__}: {exc}", cls=AlertT.error)

    return Div(
        Card(
            DivVStacked(
                H3(f"Running: {scenario_name}"),
                Div(
                    Loading(cls=LoadingT.dots),
                    P("Initialising…", cls="inline ml-2"),
                    id="prog",
                    sse_swap="progress",
                ),
            ),
        ),
        Div(id="results", sse_swap="done,error"),
        hx_ext="sse",
        sse_connect="/progress",
    )


def _progress_line(ev) -> Div:
    return Div(
        Loading(cls=LoadingT.dots),
        P(
            f"evacuated {ev.evacuated}/{ev.total} · "
            f"sim {ev.sim_time:.1f}s · wall {ev.wall_time:.0f}s · {ev.pct}%",
            cls="inline ml-2",
        ),
    )


def _results_view() -> Div:
    result = manager.result
    scenario = None
    try:
        scenario = load_scenario(f"assets/{manager.scenario_name}")
    except Exception:
        pass

    m = result.metrics
    metrics = Card(
        H3("Metrics"),
        DivVStacked(
            P(f"Success: {m.get('success')}"),
            P(f"Evacuation time: {result.evacuation_time:.1f} s"),
            P(f"Evacuated: {result.agents_evacuated}/{result.total_agents}"),
            P(f"Remaining: {result.agents_remaining}"),
            cls="space-y-1",
        ),
    )

    def plot_card(title, fig, div_id):
        return Card(H3(title), plots.figure_html(fig, div_id))

    return Div(
        metrics,
        plot_card(
            "Trajectories", plots.trajectories_figure(result, scenario), "fig-traj"
        ),
        plot_card("Cumulative FED", plots.fed_figure(result), "fig-fed"),
        plot_card("Smoke", plots.smoke_figure(result), "fig-smoke"),
        plot_card("Route cost", plots.route_cost_figure(result), "fig-route"),
        cls="space-y-6 mt-4",
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
                yield sse_message(_progress_line(payload), event="progress")
            elif kind == "done":
                yield sse_message(_results_view(), event="done")
                break
            elif kind == "error":
                yield sse_message(
                    Alert(f"Run failed: {payload}", cls=AlertT.error), event="error"
                )
                break

    return EventStream(gen())


if __name__ == "__main__":
    serve()
