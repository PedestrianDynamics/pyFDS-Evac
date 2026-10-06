"""Walkable-area providers for the FDS deck importer.

The importer needs the space an occupant can walk on, in FDS (x, y) metres.
How that polygon is made is a dependency behind one interface::

    provider(deck: FdsDeck, floor: FloorSpec) -> WalkableResult

Exit and spawn construction use only the resulting polygon and the deck
records, so a better provider (or a hand-drawn ``--walkable`` WKT) changes
nothing else.

The default provider wraps ``scripts/generate_walkable_from_fds.py`` as it is.
Its known defects (``&HOLE`` ignored, the domain-edge rule, line-based
parsing, ...) are tracked separately and are not worked around here.

Workaround, layer rules: the script always treats its Station-calibrated CAD
layers (``HORIZONTAL_FINISHES``) as free and any obstruction whose trailing
comment contains "door" as an opening. Defaults must not be calibrated on one
scenario, so unless ``layer_rules="station"`` is asked for, the provider
empties both tuples on its own private copy of the script module, and every
obstruction in the z band blocks. Affected: the script at this revision.
Upstream issue: none yet (follow-up F10 of the import task record).
Regression test: ``tests/test_fds_import.py::test_script_provider_layer_rules``.
Remove when the script takes the rules as arguments.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from .fds_deck import FdsDeck, NamelistRecord

#: The script the default provider wraps (present in a source checkout only).
WALKABLE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "generate_walkable_from_fds.py"
)
#: Layer-rule sets the default provider accepts.
LAYER_RULES = ("none", "station")
# The script's defaults for the grid half-cell and the smallest kept hole.
_SCRIPT_HALF_CELL_M = 0.05
_SCRIPT_MIN_HOLE_M2 = 0.25


class WalkableError(ValueError):
    """The walkable area could not be derived; the message says what to do."""


@dataclass(frozen=True)
class FloorSpec:
    """The floor the importer asks a provider for.

    ``z_band`` is absolute [m]; ``domain`` is the union of the selected
    evacuation meshes (legacy deck) or of the fire meshes (modern deck);
    ``obstructions`` are the ``&OBST`` records that apply to this floor
    (``EVACUATION`` and ``MESH_ID`` honoured).
    """

    z_floor: float
    z_band: tuple[float, float]
    domain: Any
    evac_mesh_ids: tuple[str, ...] | None = None
    obstructions: tuple[NamelistRecord, ...] = ()


@dataclass(frozen=True)
class WalkableResult:
    """A provider's polygon and its diagnostics."""

    polygon: Any
    diagnostics: list[str] = field(default_factory=list)
    source: str = "derived"


WalkableProvider = Callable[[FdsDeck, FloorSpec], WalkableResult]


def _load_script() -> ModuleType:
    """Load a private copy of the walkable script."""
    if not WALKABLE_SCRIPT.is_file():
        raise WalkableError(
            "deriving the walkable area needs scripts/generate_walkable_from_fds.py "
            "from a source checkout, which this installation lacks; "
            "pass --walkable FILE.wkt"
        )
    spec = importlib.util.spec_from_file_location(
        "_pyfds_evac_walkable_script", WALKABLE_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise WalkableError(f"cannot load {WALKABLE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def script_walkable(
    deck: FdsDeck, floor: FloorSpec, *, layer_rules: str = "none"
) -> WalkableResult:
    """Default provider: ``generate_walkable_from_fds.extract`` on the deck."""
    if layer_rules not in LAYER_RULES:
        raise WalkableError(
            f"unknown layer rules {layer_rules!r}; choose one of {LAYER_RULES}"
        )
    if deck.path is None:
        raise WalkableError("the walkable script needs the deck file; pass --walkable")
    script = _load_script()
    if layer_rules == "none":
        setattr(script, "HORIZONTAL_FINISHES", ())  # noqa: B010
        setattr(script, "OPENINGS", ())  # noqa: B010
    lo, hi = floor.z_band
    try:
        polygon, parts, n_solids, domain, doors = script.extract(
            deck.path, lo, hi, _SCRIPT_HALF_CELL_M, _SCRIPT_MIN_HOLE_M2
        )
    except SystemExit as exc:
        raise WalkableError(
            f"deriving the walkable area of {deck.path} at z=[{lo:g}, {hi:g}] m "
            f"failed: {exc}. Draw the walkable area and pass --walkable FILE.wkt"
        ) from None
    diagnostics = [
        f"scripts/generate_walkable_from_fds.py, layer rules {layer_rules!r}",
        f"{n_solids} blocking obstructions in z=[{lo:g}, {hi:g}] m",
        f"script domain {domain.area:.3f} m2 (union of every &MESH)",
        f"{len(parts)} free regions; the largest one off the domain edge kept",
    ]
    return WalkableResult(polygon, diagnostics, f"derived:script:{layer_rules}")
