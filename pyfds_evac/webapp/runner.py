"""Background run manager that drives a single scenario at a time.

A run executes ``run_scenario`` on a daemon thread so the web server stays
responsive. Progress is exposed as observable *state* (``status`` plus the
latest ``last_event``) rather than a drainable queue, so the SSE endpoint is
idempotent: any number of (re)connecting streams read the same state and all
deliver the same terminal event. Only one run is active at a time.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from pyfds_evac.core import ProgressEvent, ScenarioResult, run_scenario


class RunManager:
    """Owns at most one active scenario run and its progress state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.status: str = "idle"  # idle | running | done | error
        self.result: Optional[ScenarioResult] = None
        self.error: Optional[str] = None
        self.scenario_name: Optional[str] = None
        self.artifacts: List[str] = []
        self.last_event: Optional[ProgressEvent] = None

    @property
    def running(self) -> bool:
        return self.status == "running"

    def start(
        self,
        scenario: Any,
        run_kwargs: Dict[str, Any],
        scenario_name: str,
        post_run: Optional[Callable[[ScenarioResult], List[str]]] = None,
    ) -> None:
        """Start a run on a background thread. Raises if one is already active.

        ``post_run`` runs in the worker after the simulation and before the
        status flips to ``done``; its returned strings (e.g. written output
        files) are stored on ``self.artifacts``.
        """
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A run is already in progress.")

        self.status = "running"
        self.result = None
        self.error = None
        self.scenario_name = scenario_name
        self.artifacts = []
        self.last_event = None

        def on_progress(ev: ProgressEvent) -> None:
            self.last_event = ev

        def worker() -> None:
            try:
                result = run_scenario(
                    scenario, progress_callback=on_progress, **run_kwargs
                )
                self.result = result
                if post_run is not None:
                    self.artifacts = post_run(result)
                self.status = "done"
            except Exception as exc:  # surface any run failure to the UI
                self.error = f"{type(exc).__name__}: {exc}"
                self.status = "error"
            finally:
                self._lock.release()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
