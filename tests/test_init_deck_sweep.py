"""``pyfds-evac init`` on every tracked FDS deck gives its pinned outcome.

The decks are the 182 FDS+Evac guide decks in ``assets/fds_evac_guide/``
(they include the 94 cases of #662) and the plain decks under ``assets/``
and ``artifacts/``, as tracked by git. Per deck, ``init_decks.tsv`` pins
the exit status ``init`` returns (0 runnable, 3 written but not runnable or
an input dropped at error level, 1 error), the walkable area, the exit and
agent counts, a short reason and the SHA-256 of the ``config.json`` it
writes; ``init_deck_exits.json`` pins every exit polygon. A change in any
of them fails here; regenerate both files on purpose with

    uv run python tests/test_init_deck_sweep.py

and list the changed rows in the pull request (#606).
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pyfds_evac.core.fds_import import import_fds_deck

ROOT = Path(__file__).resolve().parents[1]
TABLE = Path(__file__).with_name("init_decks.tsv")
EXITS = Path(__file__).with_name("init_deck_exits.json")
COLUMNS = ("deck", "status", "area_m2", "exits", "agents", "reason", "config_sha256")
AREA_TOL_M2 = 0.01
COORD_TOL_M = 1e-6


def _decks() -> list[str]:
    """The tracked ``.fds`` files under ``assets/`` and ``artifacts/``."""
    listed = subprocess.run(
        ["git", "ls-files", "--", "assets/*.fds", "artifacts/*.fds"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(listed.stdout.split())


def _reason(report) -> str:
    reasons = [r.split(": add exits")[0] for r in report.not_runnable]
    dropped = sorted({f"dropped &{i.group}" for i in report.errors})
    return "; ".join(reasons + dropped)


def _config_sha(raw: dict) -> str:
    """SHA-256 of ``config.json`` as ``ImportResult.write`` writes it."""
    text = json.dumps(raw, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def outcome(deck: str) -> tuple[dict[str, str], dict[str, list]]:
    """What ``init`` makes of *deck*: one table row and its exit polygons."""
    try:
        result = import_fds_deck(ROOT / deck)
    except ValueError as exc:
        message = str(exc).replace(str(ROOT) + "/", "").splitlines()[0]
        row = (deck, "1", "", "", "", message[:100], "")
        return dict(zip(COLUMNS, row, strict=True)), {}
    report = result.report
    status = 0 if report.runnable and not report.errors else 3
    agents = sum(
        int(d["parameters"].get("number", 0))
        for d in result.raw["distributions"].values()
    )
    row = (
        deck,
        str(status),
        f"{report.walkable['area_m2']:.2f}",
        str(len(result.raw["exits"])),
        str(agents),
        _reason(report),
        _config_sha(result.raw),
    )
    exits = {k: v["coordinates"] for k, v in result.raw["exits"].items()}
    return dict(zip(COLUMNS, row, strict=True)), exits


def _pinned() -> dict[str, dict[str, str]]:
    with TABLE.open(encoding="utf-8", newline="") as handle:
        return {row["deck"]: row for row in csv.DictReader(handle, delimiter="\t")}


# Empty when the files are being regenerated for the first time.
PINNED = _pinned() if TABLE.exists() else {}
PINNED_EXITS = json.loads(EXITS.read_text(encoding="utf-8")) if EXITS.exists() else {}


def test_table_lists_every_tracked_deck():
    assert sorted(PINNED) == _decks()
    assert sorted(PINNED_EXITS) == _decks()


def _same_ring(got: list, want: list) -> bool:
    return len(got) == len(want) and all(
        abs(a - b) <= COORD_TOL_M
        for p, q in zip(got, want, strict=True)
        for a, b in zip(p, q, strict=True)
    )


@pytest.mark.parametrize("deck", sorted(PINNED))
def test_init_outcome_is_pinned(deck):
    (got, exits), want = outcome(deck), PINNED[deck]
    assert got["status"] == want["status"], got["reason"]
    if want["area_m2"]:
        assert float(got["area_m2"]) == pytest.approx(
            float(want["area_m2"]), abs=AREA_TOL_M2
        )
    for column in ("exits", "agents", "reason"):
        assert got[column] == want[column], column
    pinned_exits = PINNED_EXITS[deck]
    assert sorted(exits) == sorted(pinned_exits)
    moved = [k for k in exits if not _same_ring(exits[k], pinned_exits[k])]
    assert moved == []
    assert got["config_sha256"] == want["config_sha256"]


@pytest.mark.parametrize(
    ("deck", "radii"),
    [
        ("Validation/HUT_Library/HUT_Library.fds", {"": 0.15}),  # Adult
        ("Verification/imo/CompTest9a.fds", {"": 0.16}),  # Male
        (
            "Validation/SportsHall/sportshall_A.fds",
            {"Ave": 0.15, "Male": 0.16, "Female": 0.14, "Child": 0.12},
        ),
    ],
)
def test_guide_deck_radius_is_the_torso_radius(deck, radii):
    """#699: every spawn area gets the mean torso radius of its &PERS type."""
    result = import_fds_deck(ROOT / "assets" / "fds_evac_guide" / deck)
    got = {k: d["parameters"]["radius"] for k, d in result.raw["distributions"].items()}
    assert got
    for name, radius in got.items():
        prefix = max((p for p in radii if name.startswith(p)), key=len)
        assert radius == radii[prefix], name


def _regenerate() -> None:
    rows, exits = [], {}
    for name in _decks():
        row, exits[name] = outcome(name)
        rows.append(row)
    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    text = json.dumps(exits, indent=1, sort_keys=True, separators=(",", ":"))
    EXITS.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    _regenerate()
