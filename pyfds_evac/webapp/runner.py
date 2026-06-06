"""Background run manager that drives a single scenario at a time.

A run executes ``run_scenario`` on a daemon thread so the web server stays
responsive. Progress events flow through a thread-safe queue that the SSE
endpoint drains. Only one run is active at a time, guarded by a lock.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Dict, List, Optional

from pyfds_evac.core import ScenarioResult, run_scenario


class RunManager:
    """Owns at most one active scenario run and its progress stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self.status: str = "idle"  # idle | running | done | error
        self.result: Optional[ScenarioResult] = None
        self.error: Optional[str] = None
        self.scenario_name: Optional[str] = None
        self.artifacts: List[str] = []

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
        ``done`` event; its returned strings (e.g. written output files) are
        stored on ``self.artifacts``.
        """
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A run is already in progress.")

        self._queue = queue.Queue()
        self.status = "running"
        self.result = None
        self.error = None
        self.scenario_name = scenario_name
        self.artifacts = []

        def worker() -> None:
            try:
                result = run_scenario(
                    scenario,
                    progress_callback=lambda ev: self._queue.put(("progress", ev)),
                    **run_kwargs,
                )
                self.result = result
                if post_run is not None:
                    self.artifacts = post_run(result)
                self.status = "done"
                self._queue.put(("done", result))
            except Exception as exc:  # surface any run failure to the UI
                self.error = f"{type(exc).__name__}: {exc}"
                self.status = "error"
                self._queue.put(("error", self.error))
            finally:
                self._lock.release()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def try_get(self) -> Optional[tuple[str, Any]]:
        """Return the next ``(kind, payload)`` event, or ``None`` if none ready.

        Non-blocking, so an async SSE loop can poll without stalling the event
        loop.
        """
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None
