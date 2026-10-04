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
    inside or flow agents not yet spawned (#139, #444). The outcome does not
    say why agents remain: the incapacitated count is shown on its own
    (:func:`incapacitated_text`), because the engine does not guarantee that
    incapacitated agents are among those inside (#593).
    """

    complete: bool | None
    label: str
    time_label: str


def agents_label(count: int | None) -> str:
    """``"1 agent"`` or ``"<count> agents"``."""
    return f"{count} agent" if count == 1 else f"{count} agents"


def run_outcome(
    status: str | None,
    remaining: int | None,
    not_spawned: int | None,
) -> Outcome:
    """The :class:`Outcome` of a run from the values it reported."""
    if status is None:
        return Outcome(None, "Outcome not reported", "Simulated time")
    if status == "completed":
        return Outcome(True, "Complete: all agents evacuated", "Evacuation time")
    label = f"Incomplete: time limit reached, {agents_label(remaining)} inside"
    if not_spawned:
        label += f", {not_spawned} not spawned"
    return Outcome(False, label, "Simulated time (limit reached)")


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
    recorded but stops nobody. ``run_settings`` is provisional (0.3.0);
    #141 asks the engine to report this itself.
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
