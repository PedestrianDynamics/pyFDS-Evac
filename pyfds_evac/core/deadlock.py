"""Whole-crowd deadlock detection for the run loop (#760).

A run is deadlocked when nobody who could still move has moved: every agent
inside but the incapacitated has a net displacement below
``DEADLOCK_DISPLACEMENT_M`` over the last ``DEADLOCK_WINDOW_S``, and no agent
is held (in pre-movement, at a waiting stage, or still to spawn from an open
flow source). The thresholds are those of the deadlock model study on #706.
The jam itself is a limitation of the operational model (#706, #359, #745);
the run only stops and reports it, it never moves an agent to clear it.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

# Window and net displacement of the #706 model study: a fixed rule, not a
# setting.
DEADLOCK_WINDOW_S = 100.0
DEADLOCK_DISPLACEMENT_M = 0.03
# Positions are kept once per interval, not every step, to keep the cost low.
DEADLOCK_SAMPLE_INTERVAL_S = 1.0
# Absorbs the rounding of a clock that advances in steps of dt.
_TIME_EPS_S = 1e-9


@dataclass(frozen=True)
class Deadlock:
    """A detected deadlock: the window start and the stuck agents' positions."""

    since_s: float
    positions: tuple[tuple[float, float], ...]

    @property
    def agents(self) -> int:
        """The number of stuck agents."""
        return len(self.positions)

    def to_dict(self) -> dict:
        """The manifest form: counts, window start and positions to 0.01."""
        return {
            "agents": self.agents,
            "since_s": round(self.since_s, 2),
            "positions": [[round(x, 2), round(y, 2)] for x, y in self.positions],
        }


class DeadlockDetector:
    """Keeps one position sample per interval over the window and applies the rule."""

    def __init__(self) -> None:
        self._samples: deque[tuple[float, dict[int, tuple[float, float]]]] = deque()
        self._last_s: float | None = None

    def due(self, time_s: float) -> bool:
        """Whether *time_s* is a sample time: one interval after the last observation."""
        if self._last_s is None:
            return True
        return time_s - self._last_s >= DEADLOCK_SAMPLE_INTERVAL_S - _TIME_EPS_S

    def observe(
        self,
        time_s: float,
        positions: Mapping[int, tuple[float, float]],
        *,
        held: bool,
    ) -> Deadlock | None:
        """Record *positions* at *time_s*; the deadlock if the rule holds now.

        *positions* maps each counted agent (inside, not incapacitated) to its
        position. *held* says some agent will still move later; it restarts
        the window, as does an empty crowd.
        """
        if not self.due(time_s):
            return None
        self._last_s = time_s
        if held or not positions:
            self._samples.clear()
            return None
        self._samples.append((time_s, dict(positions)))
        cutoff_s = time_s - DEADLOCK_WINDOW_S + _TIME_EPS_S
        while len(self._samples) > 1 and self._samples[1][0] <= cutoff_s:
            self._samples.popleft()
        start_s, start = self._samples[0]
        if start_s > cutoff_s or not _all_still(start, positions):
            return None
        return Deadlock(start_s, tuple(positions[a] for a in sorted(positions)))


def _all_still(
    start: Mapping[int, tuple[float, float]], now: Mapping[int, tuple[float, float]]
) -> bool:
    """Every agent of *now* was in *start* and moved less than the threshold."""
    for agent_id, (x, y) in now.items():
        if agent_id not in start:
            return False
        x0, y0 = start[agent_id]
        if math.hypot(x - x0, y - y0) >= DEADLOCK_DISPLACEMENT_M:
            return False
    return True
