"""Fahy, Proulx & Flynn (2011) Table 2 as data, plus the targets derived from it.

Fahy, Proulx & Flynn, "The Station Nightclub Fire -- An analysis of witness
statements", Fire Safety Science 10:197-209, doi:10.3801/IAFSS.FSS.10-197.
Rows are where a survivor was at ignition; columns are the exit actually used.
N = 355 survivors.

Transcribed and reconciled in
``docs/archive/superpowers/specs/2026-08-05-station-validation-design.md``: every column
total matches the aggregate percentages the paper states on p. 12, and
355 - 8 unknown = 347, the count whose exit usage could be determined.

Two things here are easy to get wrong and are handled explicitly:

**Windows are 27.9 % of egress and pyFDS-Evac has no windows.** The comparison
must therefore be against door users only -- and *per row*, not just in
aggregate. The discriminating row (near stage / dance floor) sent 45 of 75
people out windows; comparing model output against its raw counts would make
that row unmatchable by construction. :func:`door_shares` does the
renormalisation one row at a time.

**Only 333 of the 355 have a location.** The ``Unclear`` and
``Unknown / not reported`` rows total 22 and cannot be placed in a geometry, so
a run that reproduces this table places 333 agents, not 355.
"""

from __future__ import annotations

# Column order as printed in the paper.
COLUMNS = (
    "sunroom_window",
    "bar_door",
    "unspecified_door",
    "front",
    "kitchen",
    "main_bar_window",
    "window_door_right",
    "window_door_left",
    "stage",
    "unspecified_window",
    "unknown",
)

# The doors pyFDS-Evac models. "unspecified_door" is deliberately excluded: it
# names no door, so it can neither be matched nor fairly assigned to one.
DOORS = ("front", "bar_door", "stage", "kitchen")

# row label -> counts in COLUMNS order
TABLE2: dict[str, tuple[int, ...]] = {
    "Unclear": (0, 0, 0, 6, 0, 0, 0, 0, 0, 1, 1),
    "Stage": (0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0),
    "Near stage door": (1, 0, 1, 3, 1, 1, 0, 0, 10, 0, 0),
    "Near stage or on dance floor": (12, 4, 1, 16, 1, 28, 1, 0, 7, 5, 0),
    "Back wall platform": (0, 4, 0, 3, 1, 7, 0, 0, 0, 0, 0),
    "Sunroom": (6, 1, 0, 4, 0, 0, 0, 0, 2, 3, 0),
    "Behind dance floor": (3, 15, 1, 40, 1, 11, 0, 0, 0, 3, 0),
    "Back hallway": (2, 3, 0, 3, 3, 1, 0, 0, 0, 1, 1),
    "Between bars": (0, 9, 1, 15, 0, 2, 0, 1, 0, 0, 1),
    "Rear bar / dart room": (0, 10, 0, 4, 10, 3, 0, 0, 0, 1, 0),
    "Entryway": (0, 0, 0, 17, 0, 0, 0, 0, 0, 0, 0),
    "Main bar": (0, 24, 2, 8, 0, 2, 0, 0, 0, 1, 0),
    "Center stage-side": (0, 1, 0, 4, 1, 1, 0, 0, 0, 0, 0),
    "Unknown / not reported": (2, 0, 0, 4, 1, 1, 0, 0, 0, 1, 5),
}

# Rows that name no place in the building, so no agent can be spawned for them.
UNPLACEABLE = ("Unclear", "Unknown / not reported")

PLACEABLE = tuple(r for r in TABLE2 if r not in UNPLACEABLE)


def row_total(row: str) -> int:
    return sum(TABLE2[row])


def agents_per_row() -> dict[str, int]:
    """How many agents to spawn in each named area."""
    return {r: row_total(r) for r in PLACEABLE}


def total_agents() -> int:
    return sum(agents_per_row().values())


def door_counts(row: str) -> dict[str, int]:
    """Counts for the four modelled doors in *row*."""
    idx = {c: i for i, c in enumerate(COLUMNS)}
    return {d: TABLE2[row][idx[d]] for d in DOORS}


def door_shares(row: str) -> dict[str, float]:
    """*row* renormalised over the four modelled doors.

    This is the honest target: window users and unspecified-door users are
    dropped rather than redistributed, because pyFDS-Evac cannot produce them.
    Returns an empty mapping for a row whose occupants all left another way.
    """
    counts = door_counts(row)
    n = sum(counts.values())
    if n == 0:
        return {}
    return {d: c / n for d, c in counts.items()}


def aggregate_door_shares() -> dict[str, float]:
    """The whole table renormalised over modelled doors: the paper's 127/71/23/19."""
    totals = {d: 0 for d in DOORS}
    for row in TABLE2:
        for d, c in door_counts(row).items():
            totals[d] += c
    n = sum(totals.values())
    return {d: c / n for d, c in totals.items()}


def front_door_attempt_floor() -> float:
    """At least this share of survivors tried or succeeded in using the front door.

    127 used it; at least another 62 tried and failed (34 left by a window, 25
    by another door). The paper draws the conclusion explicitly on p. 12.
    """
    return (127 + 62) / 355
