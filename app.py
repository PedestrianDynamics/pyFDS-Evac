"""Entry point for the pyFDS-Evac web GUI.

Run with: ``uv run app.py`` (requires ``uv sync --extra gui``).
Serves on http://127.0.0.1:5001 with auto-reload; ``--host`` and ``--port``
as for ``pyfds-evac-gui``.
"""

from pyfds_evac.webapp.app import app, serve  # noqa: F401  (serve reads `app`)

if __name__ == "__main__":
    from pyfds_evac.webapp.launch import _build_parser, warn_if_exposed

    args = _build_parser(prog="app.py").parse_args()
    warn_if_exposed(args.host, args.port)
    serve(host=args.host, port=args.port)
