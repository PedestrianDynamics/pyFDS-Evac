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
from fasthtml.common import Option, P

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_parser() -> argparse.ArgumentParser:
    """Import run.py's argparse parser, adding the repo root to sys.path."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    import run  # top-level CLI module at the repository root

    return run._build_parser()


# Display grouping keyed by argparse dest. Flags not listed fall into "Other".
# The Output group holds CLI-oriented flags that the GUI does not apply (it
# shows results as interactive plots instead of writing files); they are
# rendered read-only so the full flag surface stays visible.
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
        "SMV export",
        [
            "smv_export",
            "smv_particle_z",
            "smv_class_id",
            "smv_avatar_style",
            "smv_with_azimuth",
        ],
    ),
]

# Flags rendered read-only: the GUI run path does not act on them.
_CLI_ONLY = {
    "print_summary",
    "output_sqlite",
    "cleanup",
    "export_app_bundle",
    "export_only",
    "inspect_fds",
    "output_smoke_history",
    "output_fed_history",
    "output_route_history",
    "output_route_cost_history",
    "smv_export",
    "smv_particle_z",
    "smv_class_id",
    "smv_avatar_style",
    "smv_with_azimuth",
}


def _is_bool(action: argparse.Action) -> bool:
    return action.nargs == 0 and action.const is True


def _scenario_names() -> List[str]:
    """List runnable scenario directories under assets/."""
    assets = _REPO_ROOT / "assets"
    if not assets.is_dir():
        return []
    names = [
        p.name
        for p in sorted(assets.iterdir())
        if p.is_dir() and (p / "config.json").exists()
    ]
    return names


def _field(action: argparse.Action) -> Any:
    """Render one argparse action as a MonsterUI form control."""
    dest = action.dest
    label = dest.replace("_", " ")
    disabled = dest in _CLI_ONLY

    if dest == "scenario":
        opts = [Option(n, value=n) for n in _scenario_names()]
        return mu.LabelSelect(*opts, label="scenario", id="scenario")

    if _is_bool(action):
        return mu.LabelSwitch(label, id=dest, disabled=disabled)

    if action.type in (int, float):
        step = "1" if action.type is int else "any"
        value = "" if action.default is None else str(action.default)
        return mu.LabelInput(
            label, id=dest, type="number", step=step, value=value, disabled=disabled
        )

    value = "" if action.default is None else str(action.default)
    return mu.LabelInput(label, id=dest, value=value, disabled=disabled)


def build_form(post_url: str) -> Any:
    """Build the sidebar parameter form posting to ``post_url``."""
    parser = _load_parser()
    by_dest = {a.dest: a for a in parser._actions if a.dest != "help"}

    grouped = set()
    sections = []
    for title, dests in FIELD_GROUPS:
        fields = [_field(by_dest[d]) for d in dests if d in by_dest]
        grouped.update(dests)
        sections.append(
            mu.AccordionItem(
                title, mu.DivVStacked(*fields, cls="space-y-3 mt-2"), open=True
            )
        )

    other = [
        _field(a) for d, a in by_dest.items() if d not in grouped and a.option_strings
    ]
    if other:
        sections.append(
            mu.AccordionItem(
                "Output / CLI-only",
                mu.DivVStacked(
                    P(
                        "Shown for completeness; the GUI presents results as plots "
                        "rather than acting on these flags.",
                        cls=mu.TextPresets.muted_sm,
                    ),
                    *other,
                    cls="space-y-3 mt-2",
                ),
            )
        )

    return mu.Form(
        mu.Accordion(*sections, multiple=True),
        mu.Button("Run scenario", cls=mu.ButtonT.primary, type="submit"),
        hx_post=post_url,
        hx_target="#run-panel",
        hx_swap="innerHTML",
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
