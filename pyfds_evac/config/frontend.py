"""Run folders and outcome wording shared by the front ends (GUI and TUI).

The web GUI and the terminal UI write a run's files to the same layout,
``<results root>/<scenario>/<mode>/seed<seed>/<stamp>``, and word a
finished run the same way (:func:`run_outcome`). This module imports only
the standard library, so the TUI can use it without the GUI extra and
without the simulation stack.

Provisional public API (0.3.0): names may change in 0.3.x.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parameters import default

#: Derived output folders go under this root when it is set.
RESULTS_ENV = "PYFDS_EVAC_RESULTS_DIR"


def utc_now() -> str:
    """The current UTC time as a run's ``started_at``, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_stamp(started_at: str) -> str:
    """A filesystem-safe stamp of *started_at*, e.g. ``20260929T142301Z``.

    It names a run's derived output folder and its exported script, so both
    stay distinct across sessions, where run numbers restart at 1.
    """
    stamp = datetime.fromisoformat(started_at).astimezone(timezone.utc)
    return stamp.strftime("%Y%m%dT%H%M%SZ")


def run_name(scenario: Any) -> str:
    """Filename stem for a scenario's artifacts.

    ``clean()`` in the GUI sidebar's preview script mirrors this, so the
    file names the sidebar shows are the ones a run writes.
    """
    name = str(scenario or "")
    return name.replace(".json", "").replace("/", "_") if name else "run"


def results_root(work_root: Path) -> Path:
    """Root of the derived output folders: :data:`RESULTS_ENV` when set,
    else ``results/`` under *work_root*."""
    configured = os.environ.get(RESULTS_ENV, "").strip()
    return Path(configured).expanduser() if configured else work_root / "results"


def default_output_base(
    scenario: Any, mode: Any, seed: Any, stamp: str, results: Path
) -> str:
    """Derived output folder of one run under the results root *results*.

    ``<results>/<scenario>/<mode>/seed<seed>/<stamp>``: *seed* is the one
    the run uses, and *stamp* the run's start time, so no two runs share a
    folder. When the folder exists anyway, a numeric suffix is added.
    """
    return unique_run_folder(
        results
        / run_name(scenario)
        / str(mode or default("incapacitation_mode"))
        / f"seed{seed if seed is not None else 'default'}",
        stamp,
    )


def typed_output_base(typed: str, stamp: str, results: Path) -> str:
    """Run folder under a typed "Output folder": ``<typed>/<stamp>``.

    Each run gets its own start-time folder under the typed one, as under
    the derived path, so a second run never overwrites the first. A
    relative path is taken under the results root *results*.
    """
    base = Path(typed).expanduser()
    if not (base.is_absolute() or re.match(r"[A-Za-z]:/", typed)):
        base = results / typed
    return unique_run_folder(base, stamp)


def unique_run_folder(parent: Path, stamp: str) -> str:
    """``parent/stamp``, or ``parent/stamp-N`` when that folder exists."""
    folder = parent / stamp
    candidate, n = folder, 2
    while candidate.exists():
        candidate = folder.with_name(f"{stamp}-{n}")
        n += 1
    return candidate.as_posix()


def output_paths(base: str, name: str) -> dict[str, str]:
    """The output options a front end sets for a run folder *base*.

    *name* is the file stem (:func:`run_name`).
    """
    return {
        "output_sqlite": f"{base}/{name}.sqlite",
        "output_smoke_history": f"{base}/{name}_smoke_history.csv",
        "output_fed_history": f"{base}/{name}_fed_history.csv",
        "output_route_history": f"{base}/{name}_route_history.csv",
        "output_route_cost_history": f"{base}/{name}_route_cost_history.csv",
        "output_exit_history": f"{base}/{name}_exit_history.csv",
        "export_app_bundle": f"{base}/bundle",
    }


@dataclass(frozen=True)
class Outcome:
    """How a finished run ended, worded for a results view.

    Taken from the run's own ``status`` metric (``completed`` or
    ``incomplete``), the same field ``success`` and run.py's exit status
    follow. A run is incomplete when the time limit stops it with agents
    inside or flow agents not yet spawned (#139, #444), or when it empties
    after its flow windows closed with agents not spawned (#742), or when
    every agent able to move has left and only incapacitated ones remain
    (#141), or when every mobile agent stood still over the deadlock window
    (#760). Incapacitated agents stay inside, so they are among the agents
    that remain; the incapacitated count is shown on its own
    (:func:`incapacitated_text`).
    """

    complete: bool | None
    label: str
    time_label: str


def agents_label(count: int | None) -> str:
    """``"1 agent"`` or ``"<count> agents"``."""
    return f"{count} agent" if count == 1 else f"{count} agents"


#: The words for each ``end_reason`` of an incomplete run; a missing or
#: unknown one is the time limit. The one place these are written.
STOP_REASONS = {
    "time_limit": "time limit reached",
    "flows_closed": "flow windows closed",
    "all_mobile_left": "all mobile agents left",
    "deadlock": "deadlock",
}


def stop_reason_phrase(
    end_reason: str | None, deadlock: Mapping[str, Any] | None = None
) -> str:
    """The phrase for why an incomplete run stopped, shared by every front end.

    *end_reason* is the run's ``end_reason`` metric; without it, or for
    ``time_limit``, the run is worded as stopped by the time limit. A
    ``deadlock`` end names the stuck agents and the time they stood still
    from *deadlock* (the run's ``metrics["deadlock"]``); the phrase ends in
    a comma because it is followed by `` after <t> s``. A deadlock that was
    seen but did not end the run (``ended_run`` False, #988) is not an
    ``end_reason`` and has no phrase here.
    """
    if end_reason == "deadlock":
        info = deadlock or {}
        stuck = info.get("agents", 0)
        since = float(info.get("since_s", 0.0))
        reason = STOP_REASONS["deadlock"]
        return f"{reason}, {agents_label(stuck)} stuck since t = {since:.2f} s,"
    return STOP_REASONS.get(end_reason or "", STOP_REASONS["time_limit"])


def run_outcome(
    status: str | None,
    remaining: int | None,
    not_spawned: int | None,
    end_reason: str | None = None,
    *,
    incapacitated: int | None = None,
) -> Outcome:
    """The :class:`Outcome` of a run from the values it reported.

    *end_reason* is the run's ``end_reason`` metric; without it an
    incomplete run is worded as stopped by the time limit. *incapacitated*
    is the number of agents incapacitated; an ``all_mobile_left`` run
    words it, and *remaining* when it is not given. A ``deadlock`` run
    words the mobile agents stuck inside.
    """
    if status is None:
        return Outcome(None, "Outcome not reported", "Simulated time")
    if status == "completed":
        return Outcome(True, "Complete: all agents evacuated", "Evacuation time")
    reason = STOP_REASONS.get(end_reason or "", STOP_REASONS["time_limit"])
    if end_reason == "flows_closed":
        label = f"Incomplete: {reason}, {not_spawned} not spawned"
        return Outcome(False, label, "Simulated time")
    if end_reason == "all_mobile_left":
        dead = remaining if incapacitated is None else incapacitated
        label = f"Incomplete: {reason}, {dead} incapacitated inside"
        if not_spawned:
            label += f", {not_spawned} not spawned"
        return Outcome(False, label, "Simulated time")
    if end_reason == "deadlock":
        stuck = (remaining or 0) - (incapacitated or 0)
        label = f"Incomplete: {reason}, {agents_label(stuck)} stuck"
        if not_spawned:
            label += f", {not_spawned} not spawned"
        return Outcome(False, label, "Simulated time")
    label = f"Incomplete: {reason}, {agents_label(remaining)} inside"
    if not_spawned:
        label += f", {not_spawned} not spawned"
    return Outcome(False, label, "Simulated time (limit reached)")


def execution_outcome(
    execution: str,
    outcome: str,
    *,
    remaining: int | None = None,
    not_spawned: int | None = None,
    end_reason: str | None = None,
    incapacitated: int | None = None,
    sim_time: float | None = None,
) -> Outcome:
    """The :class:`Outcome` of a run from its (execution, outcome) pair.

    A finished run with a result (``completed`` or ``incomplete``) goes to
    :func:`run_outcome` with the counts. A ``rejected`` run was refused before
    the simulation started; a ``no_result`` run is cancelled (*sim_time* is
    its last progress sample) or crashed. Raises ``ValueError`` for a pair
    a run cannot have.
    """
    if (execution, outcome) == ("cancelled", "no_result"):
        return Outcome(None, cancelled_text(sim_time), "Simulated time")
    if (execution, outcome) == ("crashed", "no_result"):
        return Outcome(None, "Run crashed, no result", "Simulated time")
    if (execution, outcome) == ("finished", "rejected"):
        return Outcome(
            None, "Configuration rejected, no simulation was run", "Simulated time"
        )
    if execution != "finished" or outcome not in ("completed", "incomplete"):
        raise ValueError(
            f"illegal run state: execution={execution!r}, outcome={outcome!r}"
        )
    return run_outcome(
        outcome,
        remaining,
        not_spawned,
        end_reason,
        incapacitated=incapacitated,
    )


#: The short header of a run that ended without a result, by (execution,
#: outcome); the full sentence is :func:`execution_outcome`'s label.
NO_RESULT_HEADERS = {
    ("finished", "rejected"): "Configuration rejected",
    ("crashed", "no_result"): "Run crashed",
}


#: Extinction-coefficient bin edges K [1/m] of the smoke layers: below the
#: first edge is clear air, the last bin is open-ended. Shared by the GUI
#: replay and the TUI plan view so both draw smoke on one fixed scale.
SMOKE_K_EDGES = (0.1, 0.5, 1.0, 3.0, 10.0)

#: Shown instead of an incapacitated count when the run modelled none.
INCAPACITATION_NOT_MODELLED = "not modelled in this run"


def incapacitation_modelled(run_settings: Mapping[str, Any] | None) -> bool:
    """Whether a run could incapacitate agents, from its ``run_settings``.

    True when tenability was configured with gas incapacitation and a gas
    FED model, or heat incapacitation and a heat FED model. False without a
    dose model, with FED disabled for missing species, and under
    ``disable_tenability`` or ``smoke_blind``, where a dose may still be
    recorded but stops nobody. #141 asks the engine to report this itself.
    """
    if not run_settings:
        return False
    tenability = run_settings.get("tenability")
    if not tenability:
        return False
    gas = bool(tenability.get("enable_incapacitation")) and (
        run_settings.get("gas_fed") is not None
    )
    heat = bool(tenability.get("enable_heat_incapacitation")) and (
        run_settings.get("heat_fed") is not None
    )
    return gas or heat


def incapacitated_text(count: int | None, modelled: bool) -> str:
    """The incapacitated figure of a finished run: ``"j agents"`` or why not."""
    if not modelled or count is None:
        return INCAPACITATION_NOT_MODELLED
    return agents_label(count)


def evacuated_text(evacuated: int, total: int, not_spawned: int | None) -> str:
    """``"e of n agents"``, or ``"e of n that entered"`` when flow agents
    were cut off, so the denominator never reads as the planned count."""
    if not_spawned:
        return f"{evacuated} of {total} that entered"
    return f"{evacuated} of {total} agents"


def cancelled_text(sim_time: float | None) -> str:
    """Where a cancelled run stopped, from its last progress sample."""
    if sim_time is None:
        return "Cancelled before the first progress sample"
    return f"Cancelled at sim {sim_time:.1f} s"
