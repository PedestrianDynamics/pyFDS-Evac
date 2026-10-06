"""What ``pyfds-evac init`` prints: a short summary, not the whole report.

Presentation only: ``import_report.json`` keeps every item, and the exit
status is decided by the caller from the report.

- Errors come first, one line each, with the deck line and the reason.
- Approximated or dropped inputs (A, D), at any level, print once per
  pattern with the number of records they concern: each can change what
  runs. Exact (S) and cosmetic (C) items stay in ``import_report.json``.
- ``verbose`` prints every report line instead, as the report's own text.
- Paths are relative to the working directory when that is shorter.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: How a record of each namelist group is counted in a note.
_UNITS = {
    "EVAC": "groups",
    "ENTR": "entries",
    "PERS": "agent types",
    "EXIT": "exits",
    "DOOR": "doors",
    "VENT": "vents",
    "EVHO": "holes",
}
_NO_COUNTERPART = re.compile(r"^([A-Z0-9_()]+) has no counterpart$")
_VALUE = re.compile(r"'[^']*'|\[[^\]]*\]|-?\d+(?:\.\d+)?(?:e-?\d+)?")
_EXIT_GROUPS = ("EXIT", "DOOR", "VENT")
#: A note longer than this is cut; the full text is in import_report.json.
_NOTE_WIDTH = 88


def show_path(path: str | Path) -> str:
    """*path* relative to the working directory when that is shorter."""
    absolute = os.path.abspath(path)
    try:
        relative = os.path.relpath(absolute)
    except ValueError:  # another drive on Windows
        return absolute
    return relative if len(relative) < len(absolute) else absolute


@dataclass
class _Group:
    """Report items that print as one line."""

    label: str
    unit_group: str
    records: set = field(default_factory=set)
    keys: list[str] = field(default_factory=list)
    varies: bool = False

    def text(self) -> str:
        if self.keys:
            return f"{', '.join(self.keys)}: no counterpart, ignored"
        text = _first_clause(self.label)
        return _cut(f"e.g. {text}" if self.varies else text)

    def count(self) -> str:
        n = len(self.records)
        unit = _UNITS.get(self.unit_group, "records")
        return f"{n} {unit if n != 1 else unit.rstrip('s')}"


def _first_clause(text: str) -> str:
    return text.split("; ", 1)[0]


def _cut(text: str) -> str:
    return text if len(text) <= _NOTE_WIDTH else text[: _NOTE_WIDTH - 1] + "…"


def group_notes(items: list[Any]) -> list[_Group]:
    """Approximated (A) and dropped (D) notes, whatever their level,
    grouped by pattern in first-seen order: each can change what runs.
    Exact mappings (S) and cosmetic keys (C) stay in import_report.json.
    A record dropped with an error shows only its error.
    """
    failed = {(i.group, i.id, i.line) for i in items if i.level == "error"}
    groups: dict[str, _Group] = {}
    for item in items:
        if item.status not in ("A", "D"):
            continue
        if (item.group, item.id, item.line) in failed:
            continue
        _add_to_group(groups, item)
    return list(groups.values())


def _add_to_group(groups: dict[str, _Group], item: Any) -> None:
    record = (item.group, item.id, item.line)
    match = _NO_COUNTERPART.match(item.message)
    if match:
        group = groups.setdefault(
            f"no-counterpart:{item.group}", _Group("", item.group)
        )
        if match.group(1) not in group.keys:
            group.keys.append(match.group(1))
        group.records.add(record)
        return
    key = f"{item.status}:{item.group}:{_VALUE.sub('#', item.message)}"
    group = groups.setdefault(key, _Group(item.message, item.group))
    group.varies = group.varies or item.message != group.label
    group.records.add(record)


def format_errors(items: list[Any]) -> list[str]:
    """Every error-level item, one line each."""
    errors = [i for i in items if i.level == "error"]
    if not errors:
        return []
    lines = [f"✗ {len(errors)} error{'s' if len(errors) != 1 else ''}"]
    for item in errors:
        where = item.id or f"&{item.group}"
        line = f" (line {item.line})" if item.line is not None else ""
        lines.append(f"  {where}{line}: {item.message}")
    return lines


def format_notes(items: list[Any]) -> list[str]:
    groups = group_notes(items)
    if not groups:
        return []
    width = max(len(g.text()) for g in groups) + 4
    lines = [
        f"! {len(groups)} approximation{'s' if len(groups) != 1 else ''} "
        "(details: import_report.json)"
    ]
    lines += [f"  {g.text():<{width}}{g.count()}" for g in groups]
    return lines


def format_header(result: Any, out_dir: str) -> list[str]:
    report = result.report
    kind = "FDS+Evac deck" if report.kind == "legacy" else "FDS deck"
    walkable = report.walkable
    areas = walkable.get("components", 0)
    exits = [e["id"] for e in report.exits]
    dropped = [i for i in report.errors if i.group in _EXIT_GROUPS]
    spawns = report.distributions
    agents = sum(d.get("number", 0) for d in spawns)
    placeholder = " placeholder" if any(d.get("placeholder") for d in spawns) else ""
    left = [
        f"Walkable  {walkable.get('area_m2', 0):.1f} m², {areas} area{'s' if areas != 1 else ''}",
        f"{_spawn_label(result, len(spawns))} ({agents}{placeholder} agents)",
    ]
    right = [
        f"Exits    {len(exits)} of {len(exits) + len(dropped)}{_names(exits)}",
        f"Floor    z = {report.floor.get('z_floor', 0):g} m",
    ]
    width = max(len(text) for text in left) + 4
    return [
        f"{show_path(result.deck_path)} → {show_path(out_dir)}{os.sep}   ({kind})",
        "",
    ] + [f"  {a:<{width}}{b}" for a, b in zip(left, right, strict=True)]


def _spawn_label(result: Any, n_areas: int) -> str:
    """Deck groups (&EVAC/&ENTR records) when there are any, else areas."""
    parents = {s.parent for s in getattr(result, "spawns", []) if s.parent}
    if parents:
        return f"Groups    {len(parents)}"
    return f"Spawn     {n_areas} area{'s' if n_areas != 1 else ''}"


def _names(exits: list[str]) -> str:
    if not exits:
        return ""
    shown = ", ".join(exits[:3]) + (", …" if len(exits) > 3 else "")
    return f" ({shown})"


def format_fds_output(rec: dict, no_fds: bool) -> list[str]:
    """One line when FDS output sits next to the deck (Q10: say it loudly)."""
    found = rec.get("fds_output_found")
    if not found:
        return []
    if rec.get("fds_dir"):
        return [
            f"FDS output found: {show_path(found)}; the run uses it "
            "(--no-fds leaves it out)."
        ]
    reason = "--no-fds given" if no_fds else rec.get("fds_dir_note", "")
    return [f"FDS output found: {show_path(found)}, not used ({reason})."]


def format_fixes(reasons: list[str]) -> list[str]:
    lines = ["✗ Not runnable, so no run command:"]
    lines += [f"  - {reason}" for reason in reasons]
    lines.append(
        "  Fix these (or pass --walkable, --exit, --agents), then run "
        "pyfds-evac init again."
    )
    return lines


def next_steps(result: Any, out_dir: str, no_fds: bool) -> list[str]:
    """Run FDS if its output is missing, run the scenario, refine it."""
    rec = result.report.recommendations
    deck_dir = show_path(result.deck_path.parent)
    scenario = f"pyfds-evac --scenario {show_path(out_dir)}"
    steps: list[list[str]] = []
    if not no_fds and result.report.kind == "legacy":
        steps.append(_fire_only_step(result))
        steps.append(
            [
                f"{scenario} --fds-dir <folder of the fire-only run>",
                "(clear air: drop --fds-dir)",
            ]
        )
    elif not no_fds and not rec.get("fds_output_found"):
        steps.append(_fds_step(result, deck_dir))
        steps.append(
            [f"{scenario} --fds-dir {deck_dir}", "(clear air: drop --fds-dir)"]
        )
    elif rec.get("fds_dir"):
        steps.append([f"{scenario} --fds-dir {show_path(rec['fds_dir'])}"])
    else:
        steps.append([scenario])
    steps.append(
        ["Refine in JuPedSim Web (https://app.jupedsim.org) or pyfds-evac-tui"]
    )
    return ["Next:"] + [
        line for n, step in enumerate(steps, 1) for line in _step_lines(n, step)
    ]


def _fds_step(result: Any, deck_dir: str) -> list[str]:
    name = result.deck_path.name
    meshes = result.report.recommendations.get("fds_meshes") or 1
    run = f"fds {name}" if meshes == 1 else f"mpiexec -n {meshes} fds {name}"
    command = run if deck_dir == "." else f"cd {deck_dir} && {run}"
    return ["Run FDS:", f"  {command}"]


def _fire_only_step(result: Any) -> list[str]:
    """FDS+Evac deck: the run needs the output of a fire-only FDS run."""
    meshes = result.report.recommendations.get("fds_meshes") or 1
    copy = "<fire-only copy>.fds"
    run = f"fds {copy}" if meshes == 1 else f"mpiexec -n {meshes} fds {copy}"
    return [
        "Run FDS on a fire-only copy of the deck: remove the evacuation "
        "namelists and meshes",
        "  (&EVAC, &PERS, &EXIT, &DOOR, &ENTR, &EVHO, &CORR, &STRS, &EVSS, "
        "&EDEV and every &MESH with EVACUATION=.TRUE.), then",
        f"  {run}",
    ]


def _step_lines(n: int, step: list[str]) -> list[str]:
    first, *rest = step
    return [f"  {n}. {first}"] + [f"     {line}" for line in rest]


def summary_lines(result: Any, out_dir: str, no_fds: bool, verbose: bool) -> list[str]:
    """Everything ``pyfds-evac init`` prints after a successful write."""
    report = result.report
    if verbose:
        body = [report.summary_text()] + format_fds_output(
            report.recommendations, no_fds
        )
    else:
        body = format_header(result, out_dir)
        body += _section(format_errors(report.items))
        body += _section(format_notes(report.items))
        body += _section(format_fds_output(report.recommendations, no_fds))
    tail = (
        format_fixes(report.not_runnable)
        if not report.runnable
        else next_steps(result, out_dir, no_fds)
    )
    return body + [""] + tail


def _section(lines: list[str]) -> list[str]:
    return [""] + lines if lines else []
