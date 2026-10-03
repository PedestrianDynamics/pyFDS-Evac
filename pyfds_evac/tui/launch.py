"""``pyfds-evac-tui``: start the terminal UI of pyFDS-Evac.

Needs the ``tui`` extra (``pip install 'pyfds-evac[tui]'``). Imports nothing
from it before the arguments are parsed, so ``--help`` is fast and works
without it, and a missing extra ends with an install hint.
"""

from __future__ import annotations

import argparse
import os

THEMES = ("evac-dark", "solarized-light")
THEME_ENV = "PYFDS_EVAC_TUI_THEME"
TUI_EXTRA_HINT = (
    "pyfds-evac-tui needs the TUI extra, which is not installed "
    "(missing module {name!r}). Install it with: pip install 'pyfds-evac[tui]'"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfds-evac-tui",
        description="Configure, run and inspect a pyFDS-Evac simulation in the "
        "terminal. Examples are read from ./assets; runs are written under "
        "./results (or $PYFDS_EVAC_RESULTS_DIR). Each run executes the same "
        "code as the pyfds-evac command, in a separate process.",
        epilog="Keys: ctrl+p command palette, ctrl+q quit. A run stops when "
        "the terminal closes; use tmux or screen for long runs.",
    )
    parser.add_argument(
        "--theme",
        choices=THEMES,
        default=None,
        help=f"Start theme (default: ${THEME_ENV}, else the last one used, "
        "else evac-dark)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, check the TUI extra, and run the TUI until it quits."""
    args = _build_parser().parse_args(argv)
    theme = args.theme or os.environ.get(THEME_ENV) or None
    if theme is not None and theme not in THEMES:
        raise SystemExit(
            f"{THEME_ENV}={theme!r} is not a theme; choose from {', '.join(THEMES)}"
        )
    try:
        from pyfds_evac.tui.app import EvacTui
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] not in {"textual", "rich"}:
            raise
        raise SystemExit(TUI_EXTRA_HINT.format(name=exc.name)) from exc
    EvacTui(theme=theme).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
