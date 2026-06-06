"""Entry point for the pyFDS-Evac web GUI.

Run with: ``uv run app.py`` (requires ``uv sync --extra gui``).
Serves on http://localhost:5001 by default.
"""

from pyfds_evac.webapp.app import app, serve  # noqa: F401  (serve reads `app`)

if __name__ == "__main__":
    serve()
