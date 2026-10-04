"""``pyfds-evac-gui``: start the local web GUI of pyFDS-Evac.

Needs the ``gui`` extra (``pip install 'pyfds-evac[gui]'``). Imports nothing
from it before the arguments are parsed, so ``--help`` works without it and a
missing extra ends with an install hint instead of a traceback.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys

# Top-level modules of the gui extra that the GUI imports at start-up.
_GUI_MODULES = {"fasthtml", "monsterui", "starlette", "uvicorn"}
GUI_EXTRA_HINT = (
    "pyfds-evac-gui needs the GUI extra, which is not installed "
    "(missing module {name!r}). Install it with: pip install 'pyfds-evac[gui]'"
)


def _build_parser(prog: str = "pyfds-evac-gui") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Start the pyFDS-Evac web GUI. Scenarios are read from "
        "./assets and uploads and results are written under the working "
        "directory (in a source checkout: under the checkout).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to listen on (default: 127.0.0.1, this machine only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 5001)),
        help="Port to listen on (default: $PORT, else 5001)",
    )
    return parser


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def warn_if_exposed(host: str, port: int) -> None:
    """Warn on stderr when *host* makes the GUI reachable from other computers."""
    if _is_loopback(host):
        return
    print(
        f"Warning: the GUI listens on {host}:{port} and is reachable from other "
        "computers; --host 127.0.0.1 keeps it on this one.",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, check the GUI extra, and serve the GUI until stopped."""
    args = _build_parser().parse_args(argv)
    try:
        from fasthtml.common import serve

        import pyfds_evac.webapp.app  # noqa: F401  (fails early without the extra)
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] not in _GUI_MODULES:
            raise
        raise SystemExit(GUI_EXTRA_HINT.format(name=exc.name)) from exc
    warn_if_exposed(args.host, args.port)
    serve(
        appname="pyfds_evac.webapp.app",
        host=args.host,
        port=args.port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
