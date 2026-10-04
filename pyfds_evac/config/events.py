"""Status events of a run, for a front end that runs it in another process.

A terminal UI (#485) runs ``build_run_kwargs`` and ``run_scenario`` in a
child process and must not parse stdout: progress lines use carriage
returns and warnings go to the logger. The child sends these events
instead. They hold only plain values, so they pickle across a process
boundary, and this module imports nothing from the simulation stack.

Progress itself is ``pyfds_evac.core.scenario.ProgressEvent`` (sim time,
wall time, evacuated / total, percent, incapacitated, not yet spawned).
No ETA exists.

A plan view draws :class:`PlanEvent` (once, the geometry and how smoke is
modelled) and :class:`FrameEvent` (agents and smoke, throttled by wall
time). Arrays travel as little-endian ``bytes``; the ``*_values`` helpers
decode them with the standard library only. ``pyfds_evac.core.run_stream``
sends all of these from a run.

Provisional public API (0.3.0): fields may change in 0.3.x.
"""

from __future__ import annotations

import struct
from array import array
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
    """A logger warning or a ``Warning:`` status line.

    ``sim_time`` [s] is the simulated time of the last progress sample
    before the warning (at most about 0.5 s earlier), or None before the
    first step.
    """

    text: str
    level: str = "WARNING"
    logger: str = ""
    sim_time: float | None = None


@dataclass(frozen=True)
class ResultEvent:
    """How the run ended.

    ``files`` lists the files written (also after a cancel). ``error`` is
    ``"<type>: <message>"`` of a failure; the traceback is sent only on
    request.

    The counts come from the run's metrics and are None when the run did
    not finish (failed, cancelled): ``total`` agents that entered,
    ``evacuated`` of them, ``remaining`` still inside at the end (the
    incapacitated included), ``incapacitated`` (ever, by gas or heat),
    ``not_spawned`` flow agents the time limit kept out. ``end_time_s`` is
    the simulated time the run stopped at: the evacuation time of a
    complete run, the time limit of an incomplete one. ``seed`` is the seed
    the run used. ``exit_counts`` is the agents per exit of the frame
    stream (see :class:`FrameEvent`), None without frames.
    ``incapacitation_modelled`` says whether the run could incapacitate
    anyone (:func:`~pyfds_evac.config.frontend.incapacitation_modelled`);
    ``incapacitated`` is meaningful only when it is True.
    """

    status: str
    exit_code: int | None
    summary: str = ""
    fds_outside: dict[str, Any] | None = None
    files: tuple[str, ...] = ()
    error: str | None = None
    traceback: str | None = None
    evacuated: int | None = None
    total: int | None = None
    remaining: int | None = None
    incapacitated: int | None = None
    not_spawned: int | None = None
    end_time_s: float | None = None
    seed: int | None = None
    exit_counts: dict[str, int] | None = None
    incapacitation_modelled: bool | None = None


@dataclass(frozen=True)
class ValidationEvent:
    """A configuration error caught before the run (rule, option, message)."""

    rule: str
    option: str | None
    message: str
    extra: dict[str, Any] = field(default_factory=dict)


# --- plan view -------------------------------------------------------------

# How the run models smoke, for the plan view's legend.
SMOKE_FDS = "fds"  # FDS extinction slice; agents feel it
SMOKE_CONSTANT = "constant"  # one K everywhere (--constant-extinction)
SMOKE_NONE = "none"  # no fire input
SMOKE_BLIND = "blind"  # smoke recorded, agents walk as in clear air
SMOKE_MODES = (SMOKE_FDS, SMOKE_CONSTANT, SMOKE_NONE, SMOKE_BLIND)

# Agent state codes of FrameEvent.states. Evacuated agents are not in the
# arrays; incapacitated ones stay, at the place they fell.
AGENT_WALKING = 0
AGENT_INCAPACITATED = 1
AGENT_STATES = {AGENT_WALKING: "walking", AGENT_INCAPACITATED: "incapacitated"}

Point = tuple[float, float]
Ring = tuple[Point, ...]


@dataclass(frozen=True)
class PlanEvent:
    """What the plan view draws under the agents; sent once before the run.

    Coordinates in metres, in the scenario's frame. ``walkable`` holds each
    polygon of the walkable area as ``(exterior, holes)``, simplified to
    ``tolerance_m``. ``exits`` and ``spawn_areas`` map an id to its polygon.
    ``exit_openings`` maps an exit id to the longest piece of the walkable
    boundary inside the exit polygon (the door in the wall); an exit with
    no such piece is absent. ``signs`` are the signs the scenario authors,
    ``(id, x, y, alpha)`` with ``alpha`` None for an omni-directional sign;
    the visibility model's default signs at the other nodes are not listed.

    ``smoke_mode`` is one of :data:`SMOKE_MODES`. ``smoke_k`` is the
    constant K [1/m] of the constant mode (also under smoke-blind).
    ``smoke_z_m`` is the height of the FDS extinction slice the run reads,
    not the one requested, or None without one. ``incapacitation_modelled``
    says whether the run about to start can incapacitate anyone, None when
    not stated.
    """

    extent: tuple[float, float, float, float]
    walkable: tuple[tuple[Ring, tuple[Ring, ...]], ...]
    exits: dict[str, Ring]
    exit_openings: dict[str, tuple[Point, Point]]
    signs: tuple[tuple[str, float, float, float | None], ...]
    spawn_areas: dict[str, Ring]
    smoke_mode: str
    smoke_k: float | None = None
    smoke_z_m: float | None = None
    max_time_s: float | None = None
    tolerance_m: float = 0.0
    incapacitation_modelled: bool | None = None


@dataclass(frozen=True)
class SmokeGrid:
    """A coarse extinction field K [1/m] at the FDS slice height.

    ``values`` is ``ny * nx`` float16 (little-endian), row by row from
    ``y0`` up; cell ``(i, j)`` covers ``[x0 + i*cell, x0 + (i+1)*cell]`` by
    the same in y and holds the slice value nearest its centre. NaN marks a
    cell outside the FDS slice. ``fds_time_s`` is the time of the slice
    frame read, ``z_m`` the slice height.
    """

    x0: float
    y0: float
    cell_m: float
    nx: int
    ny: int
    values: bytes
    fds_time_s: float
    z_m: float | None
    quantity: str = "SOOT EXTINCTION COEFFICIENT"

    def k_values(self) -> tuple[float, ...]:
        """The ``ny * nx`` values as floats, row by row."""
        return struct.unpack(f"<{self.nx * self.ny}e", self.values)


@dataclass(frozen=True)
class FrameEvent:
    """Agents at one simulated time, at most ``max_hz`` per wall second.

    ``ids`` (int32), ``x``, ``y`` (float32, m) and ``states`` (uint8, see
    :data:`AGENT_STATES`) are parallel arrays of the agents inside.
    ``exit_counts`` holds the agents evacuated so far per exit id and
    ``unattributed`` those whose exit is not known (they left between two
    frames without a recorded exit); their sum is ``evacuated``. ``smoke``
    is sent only when the FDS frame read has changed and at most
    ``smoke_hz`` per wall second; otherwise the last grid holds. The last
    frame of a run has ``final`` set and comes before the ResultEvent.
    """

    sim_time: float
    wall_time: float
    ids: bytes
    x: bytes
    y: bytes
    states: bytes
    evacuated: int
    exit_counts: dict[str, int]
    unattributed: int
    incapacitated: int
    not_spawned: int
    smoke: SmokeGrid | None = None
    final: bool = False

    def agents(self) -> list[tuple[int, float, float, int]]:
        """``(id, x, y, state)`` per agent."""
        ids = _decode("i", self.ids)
        xs = _decode("f", self.x)
        ys = _decode("f", self.y)
        return list(zip(ids, xs, ys, self.states, strict=True))


def _decode(code: str, data: bytes) -> array:
    """Little-endian *data* as an array of type *code*."""
    values = array(code)
    values.frombytes(data)
    if struct.pack("=i", 1) != struct.pack("<i", 1):
        values.byteswap()
    return values


def result_status(success: bool) -> str:
    """``success`` or ``incomplete`` for a run that finished."""
    return STATUS_SUCCESS if success else STATUS_INCOMPLETE
