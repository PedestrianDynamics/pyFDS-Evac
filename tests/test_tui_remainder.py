"""TUI form parsing, status wording and plan-view smoke bins (#836 item 1).

Expected values are hand derived: the choices are those documented in
docs/usage.md, the bin of a K value is the number of fixed edges
(0.1, 0.5, 1, 3, 10 1/m) at or below it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("textual")

from pyfds_evac.config import events  # noqa: E402
from pyfds_evac.tui import model  # noqa: E402
from pyfds_evac.tui.app import status_word  # noqa: E402
from pyfds_evac.tui.planview import PlanView, _Raster  # noqa: E402

CHOICE_OPTIONS = [
    "incapacitation_mode",
    "heat_clothing",
    "heat_incapacitation_mode",
    "heat_endpoint",
    "heat_fed_method",
    "heat_radiant_source",
    "heat_regime",
]


@pytest.mark.parametrize("dest", CHOICE_OPTIONS)
def test_value_outside_the_choices_is_rejected(dest):
    with pytest.raises(ValueError, match="invalid choice"):
        model.parse_value(dest, "not-a-choice")


def test_unparsable_field_keeps_its_default_and_reports_the_error():
    form = model.Form()
    form.text["reroute_interval"] = "abc"
    values, errors = form.values()
    assert values["reroute_interval"] == 1.0  # docs/usage.md default
    assert "invalid float value" in errors["reroute_interval"]


@pytest.mark.parametrize(
    ("status", "word"),
    [
        (events.STATUS_SUCCESS, "complete"),
        (events.STATUS_INCOMPLETE, "incomplete"),
        (events.STATUS_FAILED, "failed"),
        (events.STATUS_CANCELLED, "cancelled"),
    ],
)
def test_status_word_names_each_outcome(status, word):
    assert status_word(SimpleNamespace(status=status)) == word


def _bins_of_a_ten_metre_room():
    """A 10 m x 10 m room, K varying by column only (cells of 1 m).

    Raster for a 12 x 7 widget: s = 1 m, columns 1..10 hold the room
    (column c centre x = c - 0.5), rows 1..5 hold it (row centres 9, 7, 5,
    3, 1); column 0, column 11, row 0 and row 6 are outside the room.
    """
    import struct

    ring = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    plan = events.PlanEvent(
        extent=(0.0, 0.0, 10.0, 10.0),
        walkable=((ring, ()),),
        exits={},
        exit_openings={},
        signs=(),
        spawn_areas={},
        smoke_mode=events.SMOKE_FDS,
    )
    k_by_column = [20.0, 0.25, 0.5, 1.0, 3.0, 10.0, 0.0, 0.0, 0.0, 20.0]
    values = struct.pack("<100e", *(k for _ in range(10) for k in k_by_column))
    grid = events.SmokeGrid(
        x0=0.0, y0=0.0, cell_m=1.0, nx=10, ny=10, values=values,
        fds_time_s=0.0, z_m=1.6,
    )  # fmt: skip
    view = PlanView()
    view.plan, view.smoke = plan, grid
    raster = _Raster(plan, 12, 7)
    return raster, view._bins(raster)


def test_smoke_bin_counts_the_edges_at_or_below_k():
    raster, (upper, lower) = _bins_of_a_ten_metre_room()
    # 20 -> 5, 0.25 -> 1, 0.5 -> 2, 1 -> 3, 3 -> 4, 10 -> 5, 0 -> 0
    expected = [5, 1, 2, 3, 4, 5, 0, 0, 0, 5]
    for half in (upper, lower):
        for row in range(1, 6):
            assert list(half[row, 1:11]) == expected


def test_smoke_bins_are_clear_outside_the_walkable_area():
    raster, (upper, lower) = _bins_of_a_ten_metre_room()
    for half in (upper, lower):
        assert (half[~raster.inside] == 0).all()
        assert (half[:, 0] == 0).all() and (half[:, 11] == 0).all()
        assert (half[0] == 0).all() and (half[6] == 0).all()
