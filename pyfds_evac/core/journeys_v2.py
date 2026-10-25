"""Convert a scenario's old journeys to ``journeys_v2`` (#900).

The old shape is ``journeys`` / ``transitions`` / ``waypoint_routing``. The
converter writes one ``journeys_v2`` entry per distinct route a start area
walks and lists the entries in that start area's ``journey_weights``, weights
summing to 100. Exit shares at checkpoints become one weighted entry per
branch, a patrol that returns to its first checkpoint becomes ``"loop": true``,
and a start area that left the exit to the route choice gets no journey.

The loader reads the result (``scenario._migrate_journeys_v2``).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from pyfds_evac.core.simulation_init import _generate_journey_variants

OLD_KEYS = ("journeys", "transitions", "waypoint_routing")

_COLORS = (
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
    "#9c755f",
    "#bab0ac",
)

# (sequence, loop, weight)
_Route = tuple[list[str], bool, float]


class JourneyConversionError(ValueError):
    """The old journeys cannot be written as ``journeys_v2``."""


def convert_legacy_journeys(raw: dict) -> tuple[dict, list[str]]:
    """Return a copy of *raw* in ``journeys_v2`` form and the notes.

    A note is written for each start area whose journey was dropped; it
    starts with the start-area id.
    """
    out = copy.deepcopy(raw)
    if not any(out.get(key) for key in OLD_KEYS):
        _drop_old_keys(out)
        out["journeys_v2"] = out.get("journeys_v2") or []
        return out, []
    if out.get("journeys_v2"):
        raise JourneyConversionError(
            "the file has journeys and journeys_v2; the loader reads only the "
            "journeys, so remove one of them first"
        )
    builder = _Builder({journey["id"] for journey in out.get("journeys") or []})
    distributions = out.get("distributions") or {}
    for journey in out.get("journeys") or []:
        for start in _start_areas(journey, distributions):
            builder.add(journey, start, _routes_from(journey, start, out))
    for start, pairs in builder.weights.items():
        distributions[start]["journey_weights"] = _scaled(pairs)
    _drop_old_keys(out)
    out["journeys_v2"] = builder.entries
    return out, builder.notes


def _drop_old_keys(data: dict) -> None:
    for key in OLD_KEYS:
        data.pop(key, None)


def _choice_note(start: str, journey_id: str) -> str:
    return (
        f"{start}: journey {journey_id} lets the route choice pick the exit; "
        "no journey written"
    )


def _start_areas(journey: dict, distributions: dict) -> list[str]:
    stages = [stage for stage in journey["stages"] if stage in distributions]
    return list(dict.fromkeys(stages))


def _successors(journey: dict, raw: dict) -> dict[str, list[str]]:
    """The stages that follow each stage, from the journey's own transitions
    or else the top-level ones with its id."""
    transitions = journey.get("transitions") or [
        t for t in raw.get("transitions") or [] if t.get("journey_id") == journey["id"]
    ]
    successors: dict[str, list[str]] = defaultdict(list)
    for transition in transitions:
        if transition["to"] not in successors[transition["from"]]:
            successors[transition["from"]].append(transition["to"])
    return successors


def _has_shares(journey_id: str, waypoint_routing: dict | None) -> bool:
    return any(journey_id in node for node in (waypoint_routing or {}).values())


def _has_choice(start: str, successors: dict[str, list[str]]) -> bool:
    """Whether a stage reachable from *start* has more than one successor."""
    seen: set[str] = set()
    todo = [start]
    while todo:
        stage = todo.pop()
        if stage in seen:
            continue
        seen.add(stage)
        if len(successors.get(stage, [])) > 1:
            return True
        todo.extend(successors.get(stage, []))
    return False


def _routes_from(journey: dict, start: str, raw: dict) -> list[_Route] | None:
    """The routes of *journey* from *start*, or None when the exit is left
    to the route choice."""
    if _has_shares(journey["id"], raw.get("waypoint_routing")):
        return _shared_routes(journey, start, raw)
    successors = _successors(journey, raw)
    if _has_choice(start, successors):
        return None
    sequence, loop = _follow(journey["id"], start, successors, raw)
    return [(sequence, loop, 100.0)]


def _follow(
    journey_id: str, start: str, successors: dict[str, list[str]], raw: dict
) -> tuple[list[str], bool]:
    """The stages after *start* in walking order, and whether the last one
    leads back to the first."""
    distributions = raw.get("distributions") or {}
    sequence: list[str] = []
    stage = start
    while successors.get(stage):
        following = successors[stage][0]
        if following in sequence:
            _check_loop(journey_id, sequence, following, raw)
            return sequence, True
        if following in distributions:
            raise _error(journey_id, f"returns to the start area {following}")
        sequence.append(following)
        stage = following
    if not sequence:
        raise _error(journey_id, f"has no transition from {start}")
    return sequence, False


def _check_loop(journey_id: str, sequence: list[str], target: str, raw: dict) -> None:
    if target != sequence[0]:
        raise _error(journey_id, f"returns to {target}, not to its first stage")
    if len(sequence) < 2:
        raise _error(journey_id, "loops over a single stage")
    if sequence[-1] in (raw.get("exits") or {}):
        raise _error(journey_id, f"loops back from the exit {sequence[-1]}")


def _error(journey_id: str, problem: str) -> JourneyConversionError:
    return JourneyConversionError(f"journey {journey_id} {problem}")


def _shared_routes(journey: dict, start: str, raw: dict) -> list[_Route]:
    """One route per path through the exit shares, cut after its first exit."""
    distributions = raw.get("distributions") or {}
    exits = raw.get("exits") or {}
    variants = _generate_journey_variants(
        journey["id"], journey["stages"], raw["waypoint_routing"], {}, distributions
    )
    routes: list[_Route] = [
        (_cut_after_exit(stages, distributions, exits), False, percentage)
        for stages, percentage in variants
        if stages[0] == start
    ]
    if not routes:
        raise _error(journey["id"], f"has no route from {start} through its shares")
    return routes


def _cut_after_exit(stages: list[str], distributions: dict, exits: dict) -> list[str]:
    kept = [stage for stage in stages if stage not in distributions]
    for index, stage in enumerate(kept):
        if stage in exits:
            return kept[: index + 1]
    return kept


class _Builder:
    """Collects the ``journeys_v2`` entries, weights and notes."""

    def __init__(self, taken_ids: set[str]) -> None:
        self.entries: list[dict[str, Any]] = []
        self.notes: list[str] = []
        self.weights: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self._taken = taken_ids
        self._ids: dict[tuple, str] = {}

    def add(self, journey: dict, start: str, routes: list[_Route] | None) -> None:
        if routes is None:
            self.notes.append(_choice_note(start, journey["id"]))
            return
        for sequence, loop, weight in routes:
            self.weights[start].append(
                (self._entry_id(journey, sequence, loop), weight)
            )

    def _entry_id(self, journey: dict, sequence: list[str], loop: bool) -> str:
        """The id of the entry for this route; creates it on first use."""
        allocation = journey.get("allocation")
        key = (journey["id"], tuple(sequence), loop, json.dumps(allocation))
        if key in self._ids:
            return self._ids[key]
        entry_id = self._new_id(journey["id"])
        entry: dict[str, Any] = {
            "id": entry_id,
            "name": entry_id,
            "color": _COLORS[len(self.entries) % len(_COLORS)],
            "sequence": list(sequence),
        }
        if loop:
            entry["loop"] = True
        if allocation is not None:
            entry["allocation"] = allocation
        self.entries.append(entry)
        self._ids[key] = entry_id
        return entry_id

    def _new_id(self, journey_id: str) -> str:
        """The journey's own id for its first entry, then ``<id>_<n>``."""
        used = set(self._ids.values())
        if journey_id not in used:
            return journey_id
        number = 1
        while f"{journey_id}_{number}" in used | self._taken:
            number += 1
        return f"{journey_id}_{number}"


def _scaled(pairs: list[tuple[str, float]]) -> list[dict[str, Any]]:
    """``journey_weights`` entries with the weights scaled to sum to 100."""
    total = sum(weight for _, weight in pairs)
    return [
        {"journey_id": journey_id, "weight": weight * 100.0 / total}
        for journey_id, weight in pairs
    ]


def main(argv: list[str] | None = None) -> int:
    """``pyfds-evac-convert CONFIG -o OUT``: 0 written, 1 conversion error."""
    parser = argparse.ArgumentParser(
        prog="pyfds-evac-convert",
        description="Rewrite a scenario's old journeys as journeys_v2.",
    )
    parser.add_argument("config", help="scenario JSON with journeys / transitions")
    parser.add_argument("-o", "--output", required=True, help="file to write")
    args = parser.parse_args(argv)
    raw = json.loads(Path(args.config).read_text(encoding="utf-8"))
    try:
        converted, notes = convert_legacy_journeys(raw)
    except JourneyConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    Path(args.output).write_text(
        json.dumps(converted, indent=2) + "\n", encoding="utf-8"
    )
    for note in notes:
        print(note)
    return 0
