"""Run a scenario and report it as events, for a front end in another process.

:func:`stream_run` is the body of the child process a terminal UI (#485)
starts: it loads the scenario, builds the run as ``pyfds-evac`` does
(``build_run_kwargs``, ``run_scenario``, ``apply_outputs``) and sends the
events of :mod:`pyfds_evac.config.events` and
:class:`~pyfds_evac.core.scenario.ProgressEvent` to *emit* instead of
printing. :func:`child_main` wraps it for ``multiprocessing``: the events go
to a queue.

The run is the CLI's: the same options give the same outputs, with or
without plan-view frames (off unless asked for).

Provisional public API (0.3.0): names may change in 0.3.x.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import traceback
from collections.abc import Callable, Mapping
from typing import Any

from pyfds_evac.config import events
from pyfds_evac.config.parameters import DEFAULTS

from .plan_view import DEFAULT_MAX_HZ, DEFAULT_SMOKE_HZ, FrameRecorder, plan_event

Emit = Callable[[Any], None]


class RunCancelled(Exception):
    """The front end asked to stop the run."""


class _Clock:
    """The simulated time of the last progress sample, for warnings."""

    sim_time: float | None = None


class _WarningEvents(logging.Handler):
    """Send WARNING-and-above records as :class:`WarningEvent`."""

    def __init__(self, emit: Emit, clock: _Clock) -> None:
        super().__init__(level=logging.WARNING)
        self._emit = emit
        self._clock = clock

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
        except Exception:  # never let logging break a run
            return
        self._emit(
            events.WarningEvent(
                text, record.levelname, record.name, self._clock.sim_time
            )
        )


class _StdoutEvents(io.TextIOBase):
    """Turn printed lines into events; drop the ``\\r`` progress line."""

    def __init__(self, emit: Emit, clock: _Clock) -> None:
        self._emit = emit
        self._clock = clock
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._line(line.rsplit("\r", 1)[-1].rstrip())
        # A progress line is rewritten in place; keep only its last state.
        self._buf = self._buf.rsplit("\r", 1)[-1]
        return len(s)

    def _line(self, line: str) -> None:
        if not line:
            return
        if line.startswith("Warning:"):
            self._emit(
                events.WarningEvent(line, "WARNING", "stdout", self._clock.sim_time)
            )
            return
        self._emit(events.LogEvent(line))


def _status_line(emit: Emit) -> Callable[[str], None]:
    """The ``log`` of ``build_run_kwargs`` and ``apply_outputs``."""

    def log(line: str) -> None:
        if line.startswith("Configuring visibility"):
            emit(events.PhaseEvent(events.PHASE_VISIBILITY, line))
        elif line.startswith("Configuring"):
            emit(events.PhaseEvent(events.PHASE_INITIALISING, line))
        elif line.startswith("Warning:"):
            emit(events.WarningEvent(line, "WARNING", "pyfds_evac"))
        else:
            emit(events.LogEvent(line))

    return log


def _files(artifacts: list[str]) -> tuple[str, ...]:
    """The paths of ``apply_outputs``'s ``"<what>: <path>"`` lines."""
    return tuple(a.split(": ", 1)[1] for a in artifacts if ": " in a)


def _result_event(
    result: Any, files: tuple[str, ...], exit_counts: dict[str, int] | None
) -> events.ResultEvent:
    from pyfds_evac.cli import _summary_line

    status = events.result_status(result.success)
    metrics = result.metrics
    return events.ResultEvent(
        status=status,
        exit_code=events.EXIT_CODES[status],
        summary=_summary_line(result),
        fds_outside=metrics.get("fds_outside"),
        files=files,
        evacuated=int(metrics["agents_evacuated"]),
        total=int(metrics["total_agents"]),
        remaining=int(metrics["agents_remaining"]),
        incapacitated=int(result.agents_incapacitated),
        not_spawned=int(metrics["agents_not_spawned"]),
        end_time_s=float(metrics["evacuation_time"]),
        seed=metrics.get("seed"),
        exit_counts=exit_counts,
    )


def stream_run(
    opts: argparse.Namespace,
    emit: Emit,
    *,
    frames: bool = False,
    max_hz: float = DEFAULT_MAX_HZ,
    smoke_hz: float = DEFAULT_SMOKE_HZ,
    cancel: Callable[[], bool] | None = None,
    send_traceback: bool = False,
) -> events.ResultEvent:
    """Run *opts* (the parsed ``pyfds-evac`` options) and send its events.

    Order: phase and log events while the run is built; the
    :class:`~pyfds_evac.config.events.PlanEvent` once the models are built
    (it states the smoke mode and slice height the run uses); progress and,
    with *frames*, frame events (at most *max_hz* per wall second, the smoke
    grid at most *smoke_hz*); the final frame; the
    :class:`~pyfds_evac.config.events.ResultEvent`, which is also returned.
    *cancel* is polled at each progress sample and between phases.
    Warnings carry the simulated time of the last progress sample.
    """
    from pyfds_evac.cli import _configure_logging, apply_outputs

    from .run_config import build_run_kwargs
    from .scenario import load_scenario, run_scenario

    clock = _Clock()
    files: tuple[str, ...] = ()
    recorder: FrameRecorder | None = None

    def check_cancel() -> None:
        if cancel is not None and cancel():
            raise RunCancelled()

    def on_progress(event: Any) -> None:
        clock.sim_time = float(event.sim_time)
        emit(event)
        check_cancel()

    _configure_logging(bool(getattr(opts, "debug", False)))
    handler = _WarningEvents(emit, clock)
    root = logging.getLogger()
    root.addHandler(handler)
    log = _status_line(emit)
    try:
        with contextlib.redirect_stdout(_StdoutEvents(emit, clock)):
            emit(events.PhaseEvent(events.PHASE_INITIALISING))
            scenario = load_scenario(str(opts.scenario))
            run_kwargs = build_run_kwargs(scenario, opts, log=log)
            check_cancel()
            emit(
                plan_event(
                    scenario,
                    smoke_speed_model=run_kwargs.get("smoke_speed_model"),
                    smoke_blind=bool(run_kwargs.get("smoke_blind")),
                )
            )
            if frames:
                recorder = FrameRecorder(emit, max_hz=max_hz, smoke_hz=smoke_hz)
            emit(events.PhaseEvent(events.PHASE_RUNNING))
            result = run_scenario(
                scenario,
                progress_callback=on_progress,
                frame_recorder=recorder,
                **run_kwargs,
            )
            emit(events.PhaseEvent(events.PHASE_WRITING_OUTPUTS))
            files = _files(apply_outputs(result, scenario, opts, log=log))
        exit_counts = None if recorder is None else dict(recorder.exit_counts)
        outcome = _result_event(result, files, exit_counts)
    except RunCancelled:
        outcome = events.ResultEvent(
            events.STATUS_CANCELLED, events.EXIT_CODES[events.STATUS_CANCELLED]
        )
    except Exception as exc:  # reported to the front end, not raised
        outcome = events.ResultEvent(
            events.STATUS_FAILED,
            events.EXIT_CODES[events.STATUS_FAILED],
            files=files,
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc() if send_traceback else None,
        )
    finally:
        root.removeHandler(handler)
    emit(events.PhaseEvent(events.PHASE_DONE))
    emit(outcome)
    return outcome


def options(values: Mapping[str, Any]) -> argparse.Namespace:
    """A complete options namespace: the defaults overlaid with *values*."""
    return argparse.Namespace(**{**DEFAULTS, **values})


def child_main(
    values: Mapping[str, Any],
    queue: Any,
    cancel_event: Any = None,
    **stream_options: Any,
) -> None:
    """Entry point of a child process: :func:`stream_run` onto *queue*.

    *values* are plain option values (see :func:`options`); *cancel_event*
    is a ``multiprocessing.Event``. Keyword arguments go to
    :func:`stream_run`.
    """
    cancel = None if cancel_event is None else cancel_event.is_set
    stream_run(options(values), queue.put, cancel=cancel, **stream_options)
