"""The import report: what the FDS deck importer did with every record.

Status of a mapping, as in the import contract:

- ``S`` supported: mapped exactly;
- ``A`` approximated: mapped with a stated difference (warning);
- ``D`` dropped: no counterpart (warning, or error when it breaks the run);
- ``C`` cosmetic: ignored, only counted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

STATUSES = ("S", "A", "D", "C")
LEVELS = ("info", "warning", "error")


@dataclass(frozen=True)
class ReportItem:
    """One mapping decision, tied to a namelist record when there is one."""

    status: str
    level: str
    group: str
    id: str | None
    line: int | None
    message: str

    def format(self) -> str:
        where = f"&{self.group}" if self.group.isupper() else self.group
        if self.id is not None:
            where += f" {self.id!r}"
        if self.line is not None:
            where += f" (line {self.line})"
        return f"[{self.status}] {self.level}: {where}: {self.message}"


@dataclass
class ImportReport:
    """Provenance and diagnostics of one import (``import_report.json``)."""

    deck: str
    chid: str | None
    kind: str
    floor: dict[str, Any] = field(default_factory=dict)
    floors_not_imported: list[dict[str, Any]] = field(default_factory=list)
    walkable: dict[str, Any] = field(default_factory=dict)
    items: list[ReportItem] = field(default_factory=list)
    exits: list[dict[str, Any]] = field(default_factory=list)
    distributions: list[dict[str, Any]] = field(default_factory=list)
    recommendations: dict[str, Any] = field(default_factory=dict)
    not_runnable: list[str] = field(default_factory=list)

    @property
    def runnable(self) -> bool:
        return not self.not_runnable

    @property
    def errors(self) -> list[ReportItem]:
        """Items dropped at error level (an exit, a spawn area, ...)."""
        return [item for item in self.items if item.level == "error"]

    def add(
        self,
        status: str,
        level: str,
        group: str,
        message: str,
        record: Any = None,
        *,
        id: str | None = None,
    ) -> None:
        """Record a decision; *record* supplies the ID and line when given."""
        if status not in STATUSES or level not in LEVELS:
            raise ValueError(f"bad report item status/level: {status!r}/{level!r}")
        line = getattr(record, "line", None)
        item_id = id if id is not None else getattr(record, "id", None)
        self.items.append(ReportItem(status, level, group, item_id, line, message))

    def counts(self) -> dict[str, dict[str, int]]:
        """Per group, the number of S, A, D and C items."""
        tally: dict[str, Counter] = {}
        for item in self.items:
            tally.setdefault(item.group, Counter())[item.status] += 1
        return {
            group: {status: counter.get(status, 0) for status in STATUSES}
            for group, counter in sorted(tally.items())
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck": self.deck,
            "chid": self.chid,
            "kind": self.kind,
            "floor": self.floor,
            "floors_not_imported": self.floors_not_imported,
            "walkable": self.walkable,
            "counts": self.counts(),
            "items": [asdict(item) for item in self.items if item.status != "C"],
            "exits": self.exits,
            "distributions": self.distributions,
            "recommendations": self.recommendations,
            "runnable": self.runnable,
            "not_runnable_reasons": self.not_runnable,
        }

    def summary_text(self) -> str:
        """The stdout summary: header, counts, every A/D item, verdict."""
        lines = [
            f"Imported {self.deck} ({self.kind} deck, CHID {self.chid})",
            _floor_line(self.floor),
            _walkable_line(self.walkable),
        ]
        lines += [
            f"  not imported: {_floor_brief(f)}" for f in self.floors_not_imported
        ]
        lines.append(
            f"Exits: {len(self.exits)}; spawn areas: {len(self.distributions)}"
        )
        lines.append("Mappings (S supported, A approximated, D dropped, C cosmetic):")
        lines += [
            f"  &{g:<6s} " + " ".join(f"{s}={n}" for s, n in c.items())
            for g, c in self.counts().items()
        ]
        notes = [i.format() for i in self.items if i.status in ("A", "D")]
        notes += [
            i.format() for i in self.items if i.status == "S" and i.level != "info"
        ]
        lines += ["Notes:"] + [f"  {n}" for n in notes] if notes else []
        lines += _verdict(self)
        return "\n".join(lines)


def _floor_line(floor: dict[str, Any]) -> str:
    band = floor.get("z_band")
    band_text = f"[{band[0]:g}, {band[1]:g}]" if band else "?"
    return (
        f"Floor: {floor.get('id')} z_floor={floor.get('z_floor')} m, "
        f"z band {band_text} m"
    )


def _walkable_line(walkable: dict[str, Any]) -> str:
    return (
        f"Walkable: {walkable.get('source')}, {walkable.get('area_m2')} m2, "
        f"{walkable.get('components')} component(s), {walkable.get('holes')} hole(s)"
    )


def _floor_brief(floor: dict[str, Any]) -> str:
    return (
        f"floor {floor['id']} (z_floor {floor['z_floor']} m): "
        f"{floor['agents']} agents, {floor['evac']} &EVAC, "
        f"{floor['exit']} &EXIT, {floor['door']} &DOOR"
    )


def _verdict(report: ImportReport) -> list[str]:
    if report.runnable:
        return ["Runnable: yes"]
    return ["Runnable: no"] + [f"  {reason}" for reason in report.not_runnable]


# --- objects the importer builds ----------------------------------------------


@dataclass(frozen=True)
class Floor:
    """One evacuation floor (legacy) or the chosen level (modern)."""

    id: str
    meshes: tuple[Any, ...]
    z_floor: float
    slab: tuple[float, float]
    dx: float | None


@dataclass
class ImportedExit:
    """An exit polygon and where it came from."""

    id: str
    polygon: Any
    source: str
    segment: tuple[float, float, float, float]
    sign: dict[str, float] | None = None
    open_from_s: float | None = None
    closed_after_s: float | None = None
    role: str | None = None


@dataclass
class ImportedSpawn:
    """A spawn area with its JSON parameters."""

    id: str
    polygon: Any
    source: str
    parameters: dict[str, Any]
    placeholder: bool = False
    #: The deck record the area comes from, ("EVAC", line) or ("ENTR", line);
    #: None for an inferred area. Not written to any file.
    parent: tuple[str, int] | None = None
    #: How a point or line ``&EVAC`` was grown to an area (import report).
    expansion: dict[str, Any] | None = None
