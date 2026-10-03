"""Status events of a run, for a front end that runs it in another process.

A terminal UI (#485) runs ``build_run_kwargs`` and ``run_scenario`` in a
child process and must not parse stdout: progress lines use carriage
returns and warnings go to the logger. The child sends these events
instead. They hold only plain values, so they pickle across a process
boundary, and this module imports nothing from the simulation stack.

Progress itself is ``pyfds_evac.core.scenario.ProgressEvent`` (sim time,
wall time, evacuated / total, percent, incapacitated, not yet spawned).
No ETA exists.

Provisional public API (0.3.0): fields may change in 0.3.x.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Phases of a run, in order.
PHASE_INITIALISING = "initialising"
PHASE_FDS_INSPECTION = "fds-inspection"
PHASE_VISIBILITY = "visibility"
PHASE_RUNNING = "running"
PHASE_WRITING_OUTPUTS = "writing-outputs"
PHASE_DONE = "done"
PHASES = (
    PHASE_INITIALISING,
    PHASE_FDS_INSPECTION,
    PHASE_VISIBILITY,
    PHASE_RUNNING,
    PHASE_WRITING_OUTPUTS,
    PHASE_DONE,
)

# How a run ended, and the exit status of ``pyfds-evac`` for it. An
# argparse usage error also exits 2, so 2 alone does not mean incomplete.
STATUS_SUCCESS = "success"
STATUS_INCOMPLETE = "incomplete"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
EXIT_CODES: dict[str, int | None] = {
    STATUS_SUCCESS: 0,
    STATUS_INCOMPLETE: 2,
    STATUS_FAILED: 1,
    STATUS_CANCELLED: None,
}


@dataclass(frozen=True)
class PhaseEvent:
    """The run entered *phase*; *detail* is the status line, e.g. a
    ``Configuring …`` step."""

    phase: str
    detail: str = ""


@dataclass(frozen=True)
class LogEvent:
    """A status line, as the CLI prints it."""

    text: str


@dataclass(frozen=True)
class WarningEvent:
    """A logger warning or a ``Warning:`` status line."""

    text: str
    level: str = "WARNING"
    logger: str = ""


@dataclass(frozen=True)
class ResultEvent:
    """How the run ended.

    ``files`` lists the files written (also after a cancel). ``error`` is
    ``"<type>: <message>"`` of a failure; the traceback is sent only on
    request.
    """

    status: str
    exit_code: int | None
    summary: str = ""
    fds_outside: dict[str, Any] | None = None
    files: tuple[str, ...] = ()
    error: str | None = None
    traceback: str | None = None


@dataclass(frozen=True)
class ValidationEvent:
    """A configuration error caught before the run (rule, option, message)."""

    rule: str
    option: str | None
    message: str
    extra: dict[str, Any] = field(default_factory=dict)


def result_status(success: bool) -> str:
    """``success`` or ``incomplete`` for a run that finished."""
    return STATUS_SUCCESS if success else STATUS_INCOMPLETE
