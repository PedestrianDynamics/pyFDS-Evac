"""Background run manager that drives a single scenario at a time.

A run executes ``run_scenario`` on a daemon thread so the web server stays
responsive. Progress is exposed as observable *state* (``status`` plus the
latest ``last_event``) rather than a drainable queue, so the SSE endpoint is
idempotent: any number of (re)connecting streams read the same state and all
deliver the same terminal event. Only one run is active at a time.
"""

from __future__ import annotations

import contextlib
import io
import logging
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

from pyfds_evac.core import ProgressEvent, ScenarioResult, run_scenario

_MAX_LOG_LINES = 800
_MAX_WARNINGS = 50


class _WarningCapture(logging.Handler):
    """Collect WARNING-and-above records from the model into a list.

    The console capture below only sees ``stdout``, so anything the engine
    reports through ``logging`` never reached the GUI at all.  That hid the
    warnings that matter most -- a slice sampled at the wrong height, or agents
    walking outside the FDS domain -- because both produce a run that finishes
    cleanly and looks entirely normal.
    """

    def __init__(self, sink: List[str]) -> None:
        super().__init__(level=logging.WARNING)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # never let logging break a run
            return
        if message not in self._sink:  # warn-once sources still repeat on rerun
            self._sink.append(message)
        if len(self._sink) > _MAX_WARNINGS:
            del self._sink[:-_MAX_WARNINGS]


class _ConsoleCapture(io.TextIOBase):
    """Collect printed lines for the GUI console while echoing to the terminal.

    Carriage-return progress chunks (the ``\\rEvacuated…`` spinner) are dropped
    because that telemetry is already shown in the status card; only newline-
    terminated log lines are kept.
    """

    def __init__(self, sink: List[str], echo: Any) -> None:
        self._sink = sink
        self._echo = echo
        self._buf = ""

    def write(self, s: str) -> int:
        if self._echo is not None:
            self._echo.write(s)
            self._echo.flush()
        if "\r" in s:
            return len(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._sink.append(line)
        if len(self._sink) > _MAX_LOG_LINES:
            del self._sink[:-_MAX_LOG_LINES]
        return len(s)

    def flush(self) -> None:
        if self._echo is not None:
            self._echo.flush()


class RunManager:
    """Owns at most one active scenario run and its progress state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.status: str = "idle"  # idle | running | done | error
        self.result: Optional[ScenarioResult] = None
        self.error: Optional[str] = None
        self.scenario_name: Optional[str] = None
        self.fds_dir: Optional[str] = None
        self.results_only: bool = False
        self.opts: Any = None
        self.artifacts: List[str] = []
        self.last_event: Optional[ProgressEvent] = None
        self.fed_snapshots: List[tuple] = []  # (sim_time, max_fed, mean_fed)
        self.log_lines: List[str] = []
        self.warnings: List[str] = []

    @property
    def running(self) -> bool:
        return self.status == "running"

    def start(
        self,
        scenario: Any,
        run_kwargs: Dict[str, Any],
        scenario_name: str,
        post_run: Optional[Callable[[ScenarioResult], List[str]]] = None,
        fds_dir: Optional[str] = None,
        results_only: bool = False,
        opts: Any = None,
    ) -> None:
        """Start a run on a background thread. Raises if one is already active.

        ``post_run`` runs in the worker after the simulation and before the
        status flips to ``done``; its returned strings (e.g. written output
        files) are stored on ``self.artifacts``. ``fds_dir`` is remembered so
        the results view can render the smoke field from the same FDS case.
        ``results_only`` selects the finished view that skips building the
        trajectory viewer and plots; ``opts`` is kept so that view can report
        on every output path that was requested.
        """
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A run is already in progress.")

        self.status = "running"
        self.result = None
        self.error = None
        self.scenario_name = scenario_name
        self.fds_dir = fds_dir
        self.results_only = results_only
        self.opts = opts
        self.artifacts = []
        self.last_event = None
        self.fed_snapshots = []
        self.log_lines = []
        self.warnings = []

        def on_progress(ev: ProgressEvent) -> None:
            self.last_event = ev
            _max = getattr(ev, "max_fed", None)
            _mean = getattr(ev, "mean_fed", None)
            if _max is not None:
                self.fed_snapshots.append(
                    (float(ev.sim_time), float(_max), float(_mean or 0.0))
                )

        def worker() -> None:
            capture = _ConsoleCapture(self.log_lines, echo=sys.__stdout__)
            warning_handler = _WarningCapture(self.warnings)
            model_logger = logging.getLogger("pyfds_evac")
            model_logger.addHandler(warning_handler)
            # A logger filters by level before handlers ever see a record, so an
            # app or root configured above WARNING would drop these silently.
            previous_level = model_logger.level
            if model_logger.getEffectiveLevel() > logging.WARNING:
                model_logger.setLevel(logging.WARNING)
            try:
                with contextlib.redirect_stdout(capture):
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
                model_logger.removeHandler(warning_handler)
                model_logger.setLevel(previous_level)
                self._lock.release()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
