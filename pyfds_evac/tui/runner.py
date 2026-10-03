"""The run of the terminal UI: ``core.run_stream`` in a child process.

:class:`ProcessRunner` starts :func:`pyfds_evac.core.run_stream.child_main`
in a ``spawn`` process and hands every event to a callback, from a reader
thread. The child is the CLI's run: the same options give the same files.

What the TUI adds around the child (agreed with backend-engineer, #485):

- its file descriptors 1 and 2 go to ``child.log`` in the run folder, so
  Python warnings, native-library output and ``--debug`` lines never print
  over the TUI (#519);
- its temporary directory is a private one that is removed after the
  child has exited, whatever the status, so a cancelled or killed run
  leaves no temporary trajectory behind (#331);
- a cancel sets the child's cancel event; when no result arrives within
  :data:`CANCEL_GRACE_S` the child is terminated, and killed
  :data:`KILL_AFTER_S` later. Once outputs are being written it is never
  stopped (the writes are not atomic).

This module imports neither Textual nor the simulation stack.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import queue
import shutil
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyfds_evac.config import events

CANCEL_GRACE_S = 10.0
KILL_AFTER_S = 3.0
CHILD_LOG = "child.log"
_POLL_S = 0.2


@dataclass(frozen=True)
class Progress:
    """``core.scenario.ProgressEvent`` as plain values.

    The child converts each progress sample, so the TUI process never
    imports ``core.scenario`` (and with it JuPedSim) to unpickle one.
    """

    evacuated: int
    total: int
    sim_time: float
    wall_time: float
    pct: int
    incapacitated: int = 0
    not_spawned: int = 0


class _PlainQueue:
    """The child's event queue: progress samples go as :class:`Progress`."""

    def __init__(self, event_queue: Any) -> None:
        self._queue = event_queue

    def put(self, event: Any) -> None:
        if type(event).__name__ == "ProgressEvent":
            event = Progress(
                int(event.evacuated),
                int(event.total),
                float(event.sim_time),
                float(event.wall_time),
                int(event.pct),
                int(getattr(event, "incapacitated", 0)),
                int(getattr(event, "not_spawned", 0)),
            )
        self._queue.put(event)


@dataclass(frozen=True)
class ChildExited:
    """The child ended without a ResultEvent (crash, or stopped on cancel)."""

    exit_code: int | None
    log_tail: str
    log_path: str
    stopped: bool  # True when the TUI terminated it after a cancel


@dataclass(frozen=True)
class Stopping:
    """The cancel grace period ran out; the TUI is stopping the process."""

    killed: bool = False


def frame_rate() -> float:
    """Plan-view frames per wall second: 5, 2 over SSH, 1 with reduced motion."""
    if os.environ.get("PYFDS_EVAC_TUI_REDUCED_MOTION"):
        return 1.0
    if os.environ.get("SSH_CONNECTION"):
        return 2.0
    return 5.0


def _tail(path: Path, lines: int = 20) -> str:
    with contextlib.suppress(OSError):
        text = path.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    return ""


class _Stop:
    """The child's cancel flag: the TUI asked, or the TUI is gone.

    A hang-up (the terminal closed) or a parent that no longer exists
    (killed) stops the run at the next progress sample, as a cancel does.
    """

    def __init__(self, cancel_event: Any) -> None:
        self._event = cancel_event
        self._parent = os.getppid()
        self.hung_up = False

    def orphaned(self) -> bool:
        return self.hung_up or os.getppid() != self._parent

    def is_set(self) -> bool:
        return self._event.is_set() or self.orphaned()


def child_entry(
    values: Mapping[str, Any],
    event_queue: Any,
    cancel_event: Any,
    log_path: str,
    tmp_dir: str,
    stream_options: Mapping[str, Any],
) -> None:
    """Body of the child process (see the module docstring)."""
    log = open(log_path, "ab", buffering=0)  # noqa: SIM115 (lives with the process)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    os.environ["TMPDIR"] = tmp_dir
    tempfile.tempdir = tmp_dir
    stop = _Stop(cancel_event)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, lambda *_: setattr(stop, "hung_up", True))
    from pyfds_evac.core.run_stream import child_main

    try:
        child_main(values, _PlainQueue(event_queue), stop, **stream_options)
    finally:
        sys.stdout.flush()
        if stop.orphaned():  # nobody else will remove it
            shutil.rmtree(tmp_dir, ignore_errors=True)


TMP_PREFIX = "pyfds-evac-run-"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists, owned by someone else
    return True


def sweep_temp_dirs(root: str | None = None) -> list[str]:
    """Remove run folders of TUI processes that no longer exist.

    Each folder is named ``pyfds-evac-run-<TUI pid>-…``; a TUI that was
    killed could not remove its own. Returns the folders removed.
    """
    removed = []
    for path in Path(root or tempfile.gettempdir()).glob(f"{TMP_PREFIX}*"):
        owner = path.name[len(TMP_PREFIX) :].split("-", 1)[0]
        if owner.isdigit() and int(owner) != os.getpid() and not _alive(int(owner)):
            shutil.rmtree(path, ignore_errors=True)
            removed.append(str(path))
    return removed


def prepare_processes() -> None:
    """Start multiprocessing's resource tracker with stderr on the null device.

    Call it from the UI thread before the first child starts. Textual
    replaces ``sys.stderr`` while it runs, and the tracker passes
    ``sys.stderr.fileno()`` to its own process, which then fails ("bad
    value(s) in fds_to_keep") or would print over the screen.
    """
    from multiprocessing import resource_tracker

    saved = sys.stderr
    with open(os.devnull, "w") as null:
        sys.stderr = null
        try:
            resource_tracker.ensure_running()
        finally:
            sys.stderr = saved


def _quiet() -> None:
    """Child initialiser: send fds 1 and 2 to the null device."""
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)


def _read_facts(path: str) -> Any:
    from pyfds_evac.config.rules import FdsFacts

    return FdsFacts.read(path)


def inspect_fds(path: str) -> Any:
    """``FdsFacts.read(path)`` in a child process.

    fdsreader then never loads into the TUI process, and its warnings
    (numpy, "Module vents …") never print over the screen.
    """
    from concurrent.futures import ProcessPoolExecutor

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(1, mp_context=ctx, initializer=_quiet) as pool:
        return pool.submit(_read_facts, path).result()


class ProcessRunner:
    """One run at a time in a child process.

    ``start`` takes the run's options (plain values), its run folder and a
    callback; the callback gets every event of the run from a reader thread
    (wrap it with ``App.call_from_thread``).
    """

    def __init__(self, *, frames: bool = True, max_hz: float | None = None) -> None:
        self.frames = frames
        self.max_hz = max_hz
        self._proc: Any = None
        self._thread: threading.Thread | None = None
        self._cancel: Any = None
        self._cancel_at: float | None = None
        self._phase: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self, values: Mapping[str, Any], folder: str, post: Callable[[Any], None]
    ) -> None:
        if self.running:
            raise RuntimeError("A run is already in progress.")
        prepare_processes()
        ctx = multiprocessing.get_context("spawn")
        Path(folder).mkdir(parents=True, exist_ok=True)
        log_path = str(Path(folder) / CHILD_LOG)
        sweep_temp_dirs()
        tmp_dir = tempfile.mkdtemp(prefix=f"{TMP_PREFIX}{os.getpid()}-")
        event_queue = ctx.Queue()
        self._cancel = ctx.Event()
        self._cancel_at = None
        self._phase = None
        options = {
            "frames": self.frames,
            "max_hz": self.max_hz or frame_rate(),
            "send_traceback": True,
        }
        self._proc = ctx.Process(
            target=child_entry,
            args=(dict(values), event_queue, self._cancel, log_path, tmp_dir, options),
            name="pyfds-evac-run",
            daemon=True,
        )
        try:
            self._proc.start()
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        self._thread = threading.Thread(
            target=self._read,
            args=(self._proc, event_queue, post, Path(log_path), tmp_dir),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> bool:
        """Ask the child to stop. Returns whether a run was in progress."""
        if not self.running or self._cancel is None:
            return False
        self._cancel.set()
        if self._cancel_at is None:
            self._cancel_at = time.monotonic()
        return True

    def stop(self) -> None:
        """Stop the child now (quitting the TUI during a run)."""
        self.cancel()
        proc = self._proc
        if proc is not None and proc.is_alive():
            proc.terminate()
            proc.join(KILL_AFTER_S)
            if proc.is_alive():
                proc.kill()

    def join(self, timeout: float | None = None) -> bool:
        if self._thread is not None:
            self._thread.join(timeout)
        return not self.running

    def _read(
        self,
        proc: Any,
        event_queue: Any,
        post: Callable[[Any], None],
        log_path: Path,
        tmp_dir: str,
    ) -> None:
        got_result = False
        stopped = killed = False
        terminated_at: float | None = None
        try:
            while True:
                try:
                    event = event_queue.get(timeout=_POLL_S)
                except queue.Empty:
                    if not proc.is_alive():
                        got_result = self._drain(event_queue, post) or got_result
                        break
                    stop = self._overdue(terminated_at)
                    if stop == "terminate":
                        terminated_at = time.monotonic()
                        stopped = True
                        post(Stopping())
                        proc.terminate()
                    elif stop == "kill" and not killed:
                        killed = True
                        post(Stopping(killed=True))
                        proc.kill()
                    continue
                if isinstance(event, events.PhaseEvent):
                    self._phase = event.phase
                post(event)
                if isinstance(event, events.ResultEvent):
                    got_result = True
                    break
            proc.join(5.0)
            if proc.is_alive():
                proc.terminate()
                proc.join(KILL_AFTER_S)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if not got_result:
            post(ChildExited(proc.exitcode, _tail(log_path), str(log_path), stopped))

    def _overdue(self, terminated_at: float | None) -> str | None:
        """``terminate`` or ``kill`` when a cancel waited too long, else None."""
        if self._cancel_at is None or self._phase == events.PHASE_WRITING_OUTPUTS:
            return None
        now = time.monotonic()
        if terminated_at is None and now - self._cancel_at > CANCEL_GRACE_S:
            return "terminate"
        if terminated_at is not None and now - terminated_at > KILL_AFTER_S:
            return "kill"
        return None

    def _drain(self, event_queue: Any, post: Callable[[Any], None]) -> bool:
        """Post what the child sent before it ended; True on a ResultEvent."""
        got = False
        while True:
            try:
                event = event_queue.get(timeout=_POLL_S)
            except (queue.Empty, EOFError, OSError):
                return got
            post(event)
            got = got or isinstance(event, events.ResultEvent)
