"""The agents queued ahead of an agent at an exit (#89).

An agent pays for an exit the time the holders of that exit who are
strictly closer to it need to pass, ``N_ahead / capacity``. A holder is an
agent counted at the exit in ``exit_counts``. Closeness is the straight-line
distance to the exit point, taken from the positions of the reroute pass.
The index keeps, per exit, the sorted holder distances: building it costs
O(N log N), a lookup O(log N), a switch O(N).
"""

from __future__ import annotations

import math
from bisect import bisect_left, insort
from collections.abc import Iterable, Mapping

Point = tuple[float, float]


class ExitQueueIndex:
    """Holders of each exit, ordered by distance to the exit point."""

    def __init__(self, exit_points: Mapping[str, Point]) -> None:
        self._points = dict(exit_points)
        self._distances: dict[str, list[float]] = {e: [] for e in self._points}
        self._held: dict[int, tuple[str, float, Point]] = {}

    def build(self, holders: Iterable[tuple[int, str | None, Point]]) -> None:
        """Replace the holders with ``(agent_id, exit_id, position)`` rows."""
        for distances in self._distances.values():
            distances.clear()
        self._held.clear()
        for agent_id, exit_id, position in holders:
            self._insert(agent_id, exit_id, position)
        for distances in self._distances.values():
            distances.sort()

    def ahead(self, agent_id: int, position: Point) -> dict[str, int]:
        """Per exit, the holders strictly closer to it than the agent.

        The agent's own indexed position is used when it holds an exit, so
        its own entry is at distance equal to its own and never counts.
        """
        held = self._held.get(agent_id)
        at = held[2] if held is not None else position
        return {
            exit_id: bisect_left(self._distances[exit_id], _distance(at, point))
            for exit_id, point in self._points.items()
        }

    def move(self, agent_id: int, new_exit: str | None, position: Point) -> None:
        """Move one agent's entry to *new_exit* (None removes it)."""
        held = self._held.pop(agent_id, None)
        if held is not None:
            old_exit, old_distance, held_position = held
            distances = self._distances[old_exit]
            del distances[bisect_left(distances, old_distance)]
            position = held_position
        if new_exit in self._points:
            self._insert(agent_id, new_exit, position, ordered=True)

    def _insert(
        self,
        agent_id: int,
        exit_id: str | None,
        position: Point,
        ordered: bool = False,
    ) -> None:
        if exit_id not in self._points:
            return
        distance = _distance(position, self._points[exit_id])
        self._held[agent_id] = (exit_id, distance, position)
        if ordered:
            insort(self._distances[exit_id], distance)
            return
        self._distances[exit_id].append(distance)


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
