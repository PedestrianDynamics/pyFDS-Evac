"""Themes of the terminal UI: ``evac-dark`` (default) and Solarized Light.

The tokens of ``evac-dark`` come from the docs site (see
``studies/tui_visual_design.md`` §2.1). ``solarized-light`` is Textual's
built-in theme. ``NO_COLOR`` gives Textual's monochrome rendering; the plan
view then switches to shade glyphs itself.
"""

from __future__ import annotations

import os

from textual.theme import Theme

EVAC_DARK = Theme(
    name="evac-dark",
    dark=True,
    primary="#3DB1FF",
    secondary="#9CA3AF",
    accent="#3DB1FF",
    success="#3FB950",
    warning="#D29922",
    error="#F85149",
    foreground="#E6EDF3",
    background="#121A24",
    surface="#18222F",
    panel="#1F2B3A",
)

#: The two themes that ship, with their palette names.
THEME_NAMES: dict[str, str] = {
    "evac-dark": "evac dark",
    "solarized-light": "Solarized Light",
}

#: Fixed extinction bin edges [1/m], the same for every run (design §2.3).
K_EDGES = (0.1, 0.5, 1.0, 3.0, 10.0)
RAMP_LIGHT = ("#F8E3A1", "#F7C04A", "#EC8A2E", "#A52C60", "#4A0C6B")
RAMP_DARK = ("#3D1659", "#7E2367", "#D2552F", "#F5A524", "#FCE68A")
INK = "#1A1A1A"
PAPER_LIGHT = "#FFFFFF"
PAPER_DARK = "#F5F5F5"
SHADES = ("░", "▒", "▓", "█", "█")


def no_color() -> bool:
    """Whether ``NO_COLOR`` asks for monochrome output (any non-empty value)."""
    return bool(os.environ.get("NO_COLOR"))


def agent_colour(bin_index: int, dark: bool) -> str:
    """Ink or paper, whichever contrasts more with smoke bin *bin_index*.

    *bin_index* is 0 for clear air and 1-5 for the bins of :data:`K_EDGES`.
    """
    if dark:
        return INK if bin_index >= 3 else PAPER_DARK
    return PAPER_LIGHT if bin_index >= 4 else INK
