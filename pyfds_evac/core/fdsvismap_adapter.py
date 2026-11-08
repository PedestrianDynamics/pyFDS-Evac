"""Obstruction state in time for fdsvismap, from the FDS ``.smv`` toggles.

fdsvismap 0.3.3 builds one obstruction map from ``Simulation.obstructions``
and never reads ``SubObstruction.hide_times`` / ``show_times``, so an
``&OBST`` that FDS removes or creates during the run blocks sight lines at
every time. This module decides which sub-obstructions FDS has at a time and
splits the vismap time points into periods in which that set does not change;
``visibility._build_vismap`` builds one ray-casting cache per period.

The rule: a sub-obstruction is hidden at *t* when its last toggle at or before
*t* is a hide. A piece created later is hidden at 0.0 and shown later; a piece
removed later is only hidden later. FDS has already resolved every ``&HOLE``
into the pieces it writes, so nothing here reads the ``.fds`` deck.
``SubObstruction.get_visible_times`` is not used: it matches times by exact
equality and misses both cases.

Workaround record. Reason: fdsvismap ignores ``hide_times`` / ``show_times``.
Affected versions: fdsvismap 0.2.1 to 0.3.3 (pinned exactly). Upstream issue:
fdsvismap#63. Regression tests: ``tests/test_timed_obstructions.py``. Remove
when fdsvismap reads the toggle times itself.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ObstructionPeriod:
    """Vismap time points that share one obstruction set.

    ``obstructions`` has the shape of ``VisMap.obstructions_collection``: one
    list of present sub-obstructions per FDS obstruction.
    """

    time_points: tuple[float, ...]
    obstructions: list[list[Any]]


def _spans_height(sub: Any, slice_height_m: float) -> bool:
    """The z test fdsvismap applies, with inclusive bounds."""
    z_range = sub.extent["z"]
    return bool(z_range[0] <= slice_height_m <= z_range[1])


def _is_hidden(sub: Any, time: float, label: str) -> bool:
    hides, shows = sorted(sub.hide_times), sorted(sub.show_times)
    n_hide, n_show = bisect_right(hides, time), bisect_right(shows, time)
    if n_hide == 0:
        return False
    if n_show == 0:
        return True
    last_hide, last_show = hides[n_hide - 1], shows[n_show - 1]
    if last_hide == last_show:
        raise ValueError(
            f"Obstruction state at t = {time} s is undefined for {label}: FDS "
            f"hides and shows it at the same time ({last_hide} s), and "
            "fdsreader does not keep their order."
        )
    return last_hide > last_show


def _label(obstruction: Any, sub: Any) -> str:
    mesh = getattr(getattr(sub, "mesh", None), "id", "?")
    return f"obstruction {getattr(obstruction, 'id', '?')} on mesh {mesh}"


def toggle_times(
    collection: Sequence[Any], slice_height_m: float, last_time: float
) -> list[float]:
    """Distinct toggle times in (0, *last_time*] of the pieces at the slice height.

    A hide at 0.0 is part of the initial state, not a change. Pieces outside
    the slice height never reach the obstruction map and open no period.
    """
    times: set[float] = set()
    for obstruction in collection:
        for sub in obstruction:
            if not _spans_height(sub, slice_height_m):
                continue
            times.update(float(t) for t in (*sub.hide_times, *sub.show_times))
    return sorted(t for t in times if 0.0 < t <= last_time)


def _present(
    collection: Sequence[Any], slice_height_m: float, time: float
) -> list[list[Any]]:
    return [
        [
            sub
            for sub in obstruction
            if not _spans_height(sub, slice_height_m)
            or not _is_hidden(sub, time, _label(obstruction, sub))
        ]
        for obstruction in collection
    ]


def obstruction_periods(
    collection: Sequence[Any],
    slice_height_m: float,
    time_points: Sequence[float],
) -> list[ObstructionPeriod]:
    """Group *time_points* by the obstruction set FDS has at each of them.

    With sorted toggles T_1 < ... < T_n, period k covers [T_k, T_k+1) and a
    time point belongs to period ``bisect_right(T, time)``: a toggle exactly
    on a point applies at that point. Periods without a point are skipped, and
    neighbouring periods with the same present pieces are merged. Without
    toggles the result is one period holding every point and every piece.
    """
    points = sorted(float(t) for t in time_points)
    if not points:
        return []
    toggles = toggle_times(collection, slice_height_m, points[-1])
    grouped: dict[int, list[float]] = {}
    for time in points:
        grouped.setdefault(bisect_right(toggles, time), []).append(time)
    periods: list[ObstructionPeriod] = []
    previous: frozenset[int] | None = None
    for index in sorted(grouped):
        present = _present(collection, slice_height_m, grouped[index][0])
        ids = frozenset(id(sub) for obstruction in present for sub in obstruction)
        if previous == ids:
            last = periods[-1]
            periods[-1] = ObstructionPeriod(
                (*last.time_points, *grouped[index]), last.obstructions
            )
            continue
        periods.append(ObstructionPeriod(tuple(grouped[index]), present))
        previous = ids
    return periods
