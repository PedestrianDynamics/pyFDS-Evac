"""Background run manager that drives a single scenario at a time.

A run executes ``run_scenario`` on a daemon thread so the web server stays
responsive. Progress is exposed as observable *state* (``status`` plus the
latest ``last_event``) rather than a drainable queue, so the SSE endpoint is
idempotent: any number of (re)connecting streams read the same state and all
deliver the same terminal event. Only one run is active at a time.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import functools
import io
import logging
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from pyfds_evac.core import ProgressEvent, ScenarioResult, run_scenario
from pyfds_evac.core.manifest import find_project_root, git_state, package_versions

_MAX_LOG_LINES = 800
_MAX_WARNINGS = 50


class RunCancelled(Exception):
    """Raised inside the progress callback to unwind an in-flight run.

    A worker thread can't be killed from outside, so cancellation is
    cooperative: ``cancel()`` sets a flag and the next progress tick raises
    this, which propagates out of ``run_scenario``'s step loop. Ticks fire
    roughly once per simulated second, so a cancel lands promptly.
    """


@dataclasses.dataclass(frozen=True)
class RunSpec:
    """Immutable record of what one submitted run used.

    Built from the resolved options at submission, so later form edits and
    the request handler's own mutations of ``opts`` cannot reach it. Fields
    the run has not confirmed stay None and are reported as "not recorded";
    nothing is filled in after the fact from the current form.
    """

    run_id: int
    scenario_name: str
    scenario_path: str
    # Deep copy of vars(opts) exactly as handed to build_run_kwargs.
    opts: Mapping[str, Any]
    started_at: str
    pyfds_evac_version: str | None
    git_commit: str | None
    git_dirty: bool | None
    # Seed the run would use at submission: opts.seed, else scenario.seed.
    expected_seed: int | None
    # Seed the finished run reports (result.metrics["seed"]), set only when it
    # agrees with expected_seed.
    seed_used: int | None = None
    status: str = "running"
    total_agents: int | None = None
    agents_evacuated: int | None = None
    agents_remaining: int | None = None
    evacuation_time: float | None = None
    error: str | None = None

    def namespace(self) -> argparse.Namespace:
        """A fresh, independent Namespace of the recorded options."""
        return argparse.Namespace(**copy.deepcopy(dict(self.opts)))


def utc_now() -> str:
    """The current UTC time as a run's ``started_at``, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_stamp(started_at: str) -> str:
    """A filesystem-safe stamp of *started_at*, e.g. ``20260929T142301Z``.

    It names a run's derived output folder and its exported script, so both
    stay distinct across GUI sessions, where run numbers restart at 1.
    """
    stamp = datetime.fromisoformat(started_at).astimezone(timezone.utc)
    return stamp.strftime("%Y%m%dT%H%M%SZ")


def discard_result(result: Any) -> None:
    """Delete the temporary trajectory and manifest *result* holds.

    ``run_scenario`` writes them to the system temp directory and the GUI
    copies them to the run's output folder; the copies stay. A file still
    locked (Windows) is left for the OS to reclaim.
    """
    cleanup = getattr(result, "cleanup", None)
    if cleanup is None:
        return
    with contextlib.suppress(OSError):
        cleanup()


@functools.cache
def code_provenance() -> tuple[str | None, str | None, bool | None]:
    """``(pyfds-evac version, git commit, dirty)`` of the running code.

    Read once per process: the code that is running does not change when
    the checkout does.
    """
    commit, dirty = git_state(find_project_root())
    return package_versions().get("pyfds-evac"), commit, dirty


def make_run_spec(
    opts: Any,
    scenario: Any,
    scenario_name: str,
    scenario_path: str,
    started_at: str | None = None,
) -> RunSpec:
    """Freeze the resolved options of a run about to be submitted.

    ``started_at`` is the submission time the output folder was named after;
    it defaults to now.
    """
    version, commit, dirty = code_provenance()
    seed = getattr(opts, "seed", None)
    return RunSpec(
        run_id=0,
        scenario_name=scenario_name,
        scenario_path=scenario_path,
        opts=MappingProxyType(copy.deepcopy(dict(vars(opts)))),
        started_at=started_at or utc_now(),
        pyfds_evac_version=version,
        git_commit=commit,
        git_dirty=dirty,
        expected_seed=seed if seed is not None else getattr(scenario, "seed", None),
    )


def _finished_spec(
    spec: RunSpec, outcome: str, result: Any, error: str | None
) -> RunSpec:
    """Return *spec* with the run's outcome and confirmed seed recorded."""
    fields: dict[str, Any] = {"status": outcome, "error": error}
    if result is not None:
        reported = result.metrics.get("seed")
        if reported is not None and reported == spec.expected_seed:
            fields["seed_used"] = reported
        fields.update(
            total_agents=result.total_agents,
            agents_evacuated=result.agents_evacuated,
            agents_remaining=result.agents_remaining,
            evacuation_time=result.evacuation_time,
        )
    return dataclasses.replace(spec, **fields)


class _WarningCapture(logging.Handler):
    """Collect WARNING-and-above records from the model into a list.

    The console capture below only sees ``stdout``, so anything the engine
    reports through ``logging`` never reached the GUI at all.  That hid the
    warnings that matter most -- a slice sampled at the wrong height, or agents
    walking outside the FDS domain -- because both produce a run that finishes
    cleanly and looks entirely normal.
    """

    def __init__(self, sink: list[str]) -> None:
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

    def __init__(self, sink: list[str], echo: Any) -> None:
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
        self._cancel = threading.Event()
        # Guards status transitions that race between cancel() and the worker.
        self._state = threading.Lock()
        self._thread: threading.Thread | None = None
        # idle | running | cancelling | done | error | cancelled
        self.status: str = "idle"
        # Bumped by every start(), so a progress stream can tell its own run
        # from a later one.
        self.run_id: int = 0
        self.result: ScenarioResult | None = None
        self.error: str | None = None
        self.scenario_name: str | None = None
        self.fds_dir: str | None = None
        self.results_only: bool = False
        self.opts: Any = None
        self.spec: RunSpec | None = None
        # The scenario object that ran, so views need not reload it by name.
        self.scenario: Any = None
        self.artifacts: list[str] = []
        self.last_event: ProgressEvent | None = None
        self.fed_snapshots: list[tuple] = []  # (sim_time, max_fed, mean_fed)
        self.log_lines: list[str] = []
        self.warnings: list[str] = []

    @property
    def running(self) -> bool:
        """True until the worker has ended, including while it unwinds."""
        return self.status in ("running", "cancelling")

    def start(
        self,
        scenario: Any,
        build_run_kwargs: Callable[[], dict[str, Any]],
        scenario_name: str,
        post_run: Callable[[ScenarioResult], list[str]] | None = None,
        fds_dir: str | None = None,
        results_only: bool = False,
        opts: Any = None,
        spec: RunSpec | None = None,
    ) -> None:
        """Start a run on a background thread. Raises if one is already active.

        ``build_run_kwargs`` is a zero-arg callable that builds the
        ``run_scenario`` kwargs, called on the worker thread rather than by
        the caller -- it's where FDS directory inspection happens (parsing
        every slice header via fdsreader), which can take real time for a
        large deck. Building it inline in the request handler blocked the
        HTTP response until it finished, so the browser sat on the old page
        with no visible progress for however long that parse took, even
        though the button had already flipped to "in progress". Deferring it
        here means the SSE-driven progress view mounts immediately instead.

        ``post_run`` runs in the worker after the simulation and before the
        status flips to ``done``; its returned strings (e.g. written output
        files) are stored on ``self.artifacts``. ``fds_dir`` is remembered so
        the results view can render the smoke field from the same FDS case.
        ``results_only`` selects the finished view that skips building the
        trajectory viewer and plots; ``opts`` is kept so that view can report
        on every output path that was requested.

        A cancel is honoured at every phase: inside the step loop via the
        progress callback, and between phases (after ``build_run_kwargs``,
        after ``run_scenario``, after ``post_run``). A phase already under way
        is not interrupted, so a cancel that lands during ``post_run`` still
        ends the run as ``cancelled``, but files it already wrote stay on disk.

        ``spec`` is the frozen record of the submitted configuration (see
        :func:`make_run_spec`); it gets this run's id, and its outcome once
        the run ends.
        """
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A run is already in progress.")

        # Taken so a worker still publishing its terminal status can't
        # overwrite this run's fresh state.
        with self._state:
            previous = self.result
            self._cancel.clear()
            self.run_id += 1
            self.status = "running"
            self.result = None
            self.error = None
            self.scenario_name = scenario_name
            self.fds_dir = fds_dir
            self.results_only = results_only
            self.opts = opts
            self.scenario = scenario
            self.spec = (
                None if spec is None else dataclasses.replace(spec, run_id=self.run_id)
            )
            self.artifacts = []
            self.last_event = None
            self.fed_snapshots = []
            self.log_lines = []
            self.warnings = []
        discard_result(previous)

        def check_cancel() -> None:
            if self._cancel.is_set():
                raise RunCancelled()

        def on_progress(ev: ProgressEvent) -> None:
            check_cancel()
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
            outcome = "error"
            try:
                with contextlib.redirect_stdout(capture):
                    run_kwargs = build_run_kwargs()
                    check_cancel()
                    result = run_scenario(
                        scenario, progress_callback=on_progress, **run_kwargs
                    )
                    check_cancel()
                    self.result = result
                    if post_run is not None:
                        self.artifacts = post_run(result)
                outcome = "done"
            except RunCancelled:
                outcome = "cancelled"
            except Exception as exc:  # surface any run failure to the UI
                self.error = f"{type(exc).__name__}: {exc}"
                outcome = "error"
            finally:
                model_logger.removeHandler(warning_handler)
                model_logger.setLevel(previous_level)
                self._finish(outcome)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _finish(self, outcome: str) -> None:
        """Release the run lock and publish the run's terminal status."""
        with self._state:
            if outcome == "done" and self._cancel.is_set():
                outcome = "cancelled"
            if outcome == "cancelled":
                # A deliberate stop, not a failure: leave no error for the UI
                # to report and drop any partial result.
                discard_result(self.result)
                self.result = None
                self.error = None
            if self.spec is not None:
                self.spec = _finished_spec(self.spec, outcome, self.result, self.error)
            # Release before publishing: a client that sees the terminal
            # status may start the next run straight away.
            self._lock.release()
            self.status = outcome

    def cancel(self) -> bool:
        """Ask an in-flight run to stop. Returns whether one was running."""
        with self._state:
            if self.status != "running":
                return False
            self._cancel.set()
            self.status = "cancelling"
        return True

    def join(self, timeout: float | None = None) -> bool:
        """Wait for the worker thread to end. Returns whether it has ended."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def reset(self) -> None:
        """Drop the finished run's state and return the manager to idle.

        Only meaningful once a run has ended -- an active run owns the lock
        and must be cancelled, not reset out from under itself.
        """
        with self._state:
            if self.running:
                return
            discard_result(self.result)
            self.status = "idle"
            self.result = None
            self.error = None
            self.scenario_name = None
            self.spec = None
            self.scenario = None
            self.last_event = None
            self.artifacts = []
            self.fed_snapshots = []
            self.log_lines = []
            self.warnings = []

    @contextlib.contextmanager
    def snapshot(self) -> Iterator[RunManager]:
        """Hold the state lock so a reader sees a single run throughout.

        ``start`` and ``reset`` swap a run's state under the same lock, so
        everything read inside the block belongs to one run. Never yield to
        the event loop, or call back into the manager, inside it.
        """
        with self._state:
            yield self
