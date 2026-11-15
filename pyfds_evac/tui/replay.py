"""Bounded store of the plan frames kept for the replay."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import overload

from pyfds_evac.config import events

Entry = tuple[events.FrameEvent, events.SmokeGrid | None]

#: Most frames kept before the store thins itself.
DEFAULT_CAP = 2000
#: Finest spacing kept, in simulated seconds; the replay steps by 1 s.
BASE_INTERVAL_S = 1.0
#: Slack so a frame a rounding error short of the spacing is still kept.
_TOLERANCE_S = 1e-6


class FrameStore(Sequence[Entry]):
    """Frames with their smoke grid, thinned evenly once *cap* is reached.

    A frame is kept when it is at least ``interval`` simulated seconds
    after the last kept one. At *cap* kept frames, every other one is
    dropped and ``interval`` doubles, so the whole run stays replayable at
    a coarser step. The latest frame is always readable, so the final
    frame is never lost. A smoke grid equal to the previous one is stored
    as that same object.
    """

    def __init__(self, cap: int = DEFAULT_CAP, interval: float = BASE_INTERVAL_S):
        self.cap = max(2, cap)
        self.interval = interval
        self._kept: list[Entry] = []
        self._tail: Entry | None = None
        self._smoke: events.SmokeGrid | None = None

    def append(self, entry: Entry) -> None:
        event, smoke = entry
        if smoke is not None and smoke == self._smoke:
            smoke = self._smoke
            if event.smoke is not None:
                event = dataclasses.replace(event, smoke=smoke)
        self._smoke = smoke if smoke is not None else self._smoke
        entry = (event, smoke)
        gap = event.sim_time - self._kept[-1][0].sim_time if self._kept else None
        if gap is not None and gap < self.interval - _TOLERANCE_S:
            self._tail = entry
            return
        self._tail = None
        self._kept.append(entry)
        if len(self._kept) > self.cap:
            self._thin()

    def _thin(self) -> None:
        last = self._kept[-1]
        self._kept = self._kept[::2]
        self.interval *= 2
        if self._kept[-1] is not last:
            self._tail = last

    def _all(self) -> list[Entry]:
        return self._kept + [self._tail] if self._tail else self._kept

    def __len__(self) -> int:
        return len(self._kept) + (self._tail is not None)

    @overload
    def __getitem__(self, index: int) -> Entry: ...
    @overload
    def __getitem__(self, index: slice) -> list[Entry]: ...
    def __getitem__(self, index: int | slice) -> Entry | list[Entry]:
        return self._all()[index]

    def at(self, sim_time: float) -> Entry | None:
        """The latest kept frame at or before *sim_time*, else the first."""
        frames = self._all()
        before = [e for e in frames if e[0].sim_time <= sim_time]
        return before[-1] if before else (frames[0] if frames else None)
