"""Generate the parameter form from run.py's argparse and parse it back.

The form is derived by introspecting ``run.py``'s parser so every CLI flag is
represented and new flags appear automatically. Fields are grouped for
display; ``form_to_opts`` reverses a submitted form into an
``argparse.Namespace`` whose attributes match the parser's ``dest`` names —
the same keys :func:`pyfds_evac.core.run_config.build_run_kwargs` consumes.
"""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

import monsterui.all as mu
from fasthtml.common import Option, Span

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_parser() -> argparse.ArgumentParser:
    """Import run.py's argparse parser, adding the repo root to sys.path."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    import run  # top-level CLI module at the repository root

    return run._build_parser()


# Display grouping keyed by argparse dest. Every rendered flag is applied by
# the run; the Output group writes files to the given paths.
FIELD_GROUPS: List[tuple[str, List[str]]] = [
    ("Core", ["scenario", "seed"]),
    (
        "Smoke",
        [
            "fds_dir",
            "constant_extinction",
            "smoke_update_interval",
            "smoke_slice_height",
        ],
    ),
    (
        "FED & Tenability",
        ["disable_tenability", "fic_alpha", "fic_min_factor", "fed_threshold"],
    ),
    ("Rerouting", ["enable_rerouting", "reroute_interval"]),
    ("Visibility", ["vis_cache"]),
    (
        "Output files",
        [
            "output_sqlite",
            "output_smoke_history",
            "output_fed_history",
            "output_route_history",
            "output_route_cost_history",
            "export_app_bundle",
        ],
    ),
]

# CLI-only flags with no meaning in the GUI (console output or control flow):
# not rendered. cleanup is excluded because the GUI keeps the trajectory
# SQLite alive to draw plots.
_HIDDEN = {"help", "print_summary", "export_only", "inspect_fds", "cleanup"}


def _is_bool(action: argparse.Action) -> bool:
    return action.nargs == 0 and action.const is True


def _scenario_options() -> List[tuple[str, str]]:
    """(label, value) pairs for the scenario picker.

    Each runnable scenario directory (one containing config.json) yields the
    directory itself (value = dir name, which loads config.json) plus one entry
    per additional *.json config in that directory (value = "dir/file.json").
    This mirrors the CLI ``--scenario``, which accepts a JSON file path, so
    alternate configs like config_full.json are selectable.
    """
    assets = _REPO_ROOT / "assets"
    if not assets.is_dir():
        return []
    options: List[tuple[str, str]] = []
    for p in sorted(assets.iterdir()):
        if not (p.is_dir() and (p / "config.json").exists()):
            continue
        options.append((p.name, p.name))
        for json_file in sorted(p.glob("*.json")):
            if json_file.name == "config.json":
                continue
            options.append(
                (f"{p.name} / {json_file.name}", f"{p.name}/{json_file.name}")
            )
    return options


def _browse_button(target_id: str, mode: str) -> Any:
    """A Browse button that opens the directory/file picker for a field."""
    label = "Browse folder…" if mode == "dir" else "Browse file…"
    return mu.Button(
        mu.UkIcon("folder" if mode == "dir" else "file"),
        label,
        type="button",
        hx_get=f"/browse-dir?mode={mode}&field={target_id}",
        hx_target="#dir-modal",
        hx_swap="innerHTML",
        cls=(mu.ButtonT.secondary, "btn-sm"),
    )


def _help_badge(action: argparse.Action) -> Any:
    """A '?' badge whose hover tooltip shows the flag's help text."""
    text = (action.help or "").strip()
    if not text or text == "show this help message and exit":
        return None
    # Help text rides in the native `title` attribute (safe for any
    # characters); uk-tooltip only carries options, so it can't be broken by
    # colons/semicolons in the help string. title is also the no-JS fallback.
    return Span(
        "?",
        cls="help-badge",
        title=text,
        **{"uk-tooltip": "pos: right; delay: 80"},
    )


def _label(text: str, action: argparse.Action) -> Any:
    """Label text plus an optional help badge, for a MonsterUI Label* control."""
    badge = _help_badge(action)
    return Span(text, badge, cls="lbl-help") if badge else text


def _field(action: argparse.Action) -> Any:
    """Render one argparse action as a MonsterUI form control."""
    dest = action.dest
    label = _label(dest.replace("_", " "), action)

    if dest == "scenario":
        options = _scenario_options()
        values = [v for _, v in options]
        default = "demo" if "demo" in values else (values[0] if values else None)
        opts = [
            Option(opt_label, value=value, selected=(value == default))
            for opt_label, value in options
        ]
        return mu.LabelSelect(*opts, label=label, id="scenario")

    if dest == "seed":
        # Default to a fixed seed so runs are reproducible out of the box.
        return mu.LabelInput(label, id=dest, type="number", step="1", value="42")

    if dest == "fds_dir":
        return mu.DivVStacked(
            mu.LabelInput(label, id=dest),
            _browse_button("fds_dir", "dir"),
            cls="space-y-1",
        )

    if dest == "vis_cache":
        return mu.DivVStacked(
            mu.LabelInput(label, id=dest),
            _browse_button("vis_cache", "file"),
            cls="space-y-1",
        )

    if _is_bool(action):
        return mu.LabelSwitch(label, id=dest)

    if action.type in (int, float):
        step = "1" if action.type is int else "any"
        value = "" if action.default is None else str(action.default)
        return mu.LabelInput(label, id=dest, type="number", step=step, value=value)

    value = "" if action.default is None else str(action.default)
    return mu.LabelInput(label, id=dest, value=value)


def build_form(post_url: str) -> Any:
    """Build the sidebar parameter form posting to ``post_url``."""
    parser = _load_parser()
    by_dest = {
        a.dest: a for a in parser._actions if a.dest not in _HIDDEN and a.option_strings
    }

    grouped = set()
    sections = []
    for title, dests in FIELD_GROUPS:
        fields = [_field(by_dest[d]) for d in dests if d in by_dest]
        if not fields:
            continue
        grouped.update(dests)
        sections.append(
            mu.AccordionItem(
                title, mu.DivVStacked(*fields, cls="space-y-3 mt-2"), open=True
            )
        )

    other = [_field(a) for d, a in by_dest.items() if d not in grouped]
    if other:
        sections.append(
            mu.AccordionItem("Other", mu.DivVStacked(*other, cls="space-y-3 mt-2"))
        )

    return mu.Form(
        mu.Accordion(*sections, multiple=True),
        mu.Button("Run scenario", cls=mu.ButtonT.primary, type="submit"),
        hx_post=post_url,
        hx_target="#run-panel",
        # show:top scrolls the status panel into view so feedback is never
        # off-screen below a long form.
        hx_swap="innerHTML show:top",
        cls="space-y-4",
    )


def form_to_opts(form: Dict[str, Any]) -> Namespace:
    """Reverse a submitted form into a Namespace matching argparse dests."""
    parser = _load_parser()
    opts: Dict[str, Any] = {}
    for action in parser._actions:
        dest = action.dest
        if dest == "help":
            continue
        if _is_bool(action):
            raw = form.get(dest)
            opts[dest] = (
                str(raw).lower() in ("on", "true", "1", "yes") if raw else False
            )
            continue
        raw = form.get(dest)
        if raw is None or str(raw).strip() == "":
            opts[dest] = action.default
            continue
        opts[dest] = action.type(raw) if action.type else str(raw)

    # The GUI always collects route-cost history so it can colour trajectories
    # and plot route costs, regardless of the (CLI-only) output flag.
    opts["collect_route_cost_history"] = True
    return Namespace(**opts)
