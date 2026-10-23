"""The size limit of free parts and interior rings in ``deck_walkable``.

Free parts of at most ``MIN_PART_M2`` (0.25 m2) are dropped and interior rings
below it are filled (module docstring of ``walkable_provider``). The areas
below are products of binary-exact numbers (0.5 * 0.5), so the boundary is
exact, not a rounding case.
"""

from __future__ import annotations

from shapely.geometry import Polygon, box

from pyfds_evac.core.fds_deck import parse_fds_text
from pyfds_evac.core.walkable_provider import FloorSpec, deck_walkable

_DECK = parse_fds_text("&HEAD CHID='x' /")


def _walk(domain):
    floor = FloorSpec(z_floor=0.0, z_band=(0.0, 2.0), domain=domain)
    return deck_walkable(_DECK, floor)


def _free_parts_domain():
    """A 10 x 10 room and three pockets of 0.25, 0.2501 and 0.3 m2."""
    return box(0, 0, 10, 10).union(
        box(20, 0, 20.5, 0.5)
        .union(box(30, 0, 30.5, 0.5002))
        .union(box(40, 0, 40.5, 0.6))
    )


def test_a_free_part_of_exactly_the_limit_is_dropped():
    """0.25 m2 goes; 0.2501 and 0.3 m2 stay with the room."""
    result = _walk(_free_parts_domain())
    polygon = result.polygon
    areas = sorted(round(p.area, 4) for p in polygon.geoms)
    assert areas == [0.2501, 0.3, 100.0]
    assert (
        "3 free component(s); 1 part(s) of <= 0.25 m2 dropped, 0 hole(s) below it filled"
        in result.diagnostics[2]
    )


def test_a_ring_of_exactly_the_limit_is_kept_and_a_smaller_one_filled():
    """A 0.25 m2 hole stays an obstacle; a 0.2499 m2 hole is filled.

    The code keeps a ring of area >= 0.25 (``fill_small_rings``); the module
    docstring says "smaller than that", the comment on ``MIN_PART_M2`` says "or
    less". The expectation is recorded from the code and the docstring.
    """
    shell = [(0, 0), (10, 0), (10, 10), (0, 10)]
    kept = [(2, 2), (2.5, 2), (2.5, 2.5), (2, 2.5)]
    filled = [(5, 5), (5.5, 5), (5.5, 5.4998), (5, 5.4998)]
    domain = Polygon(shell, holes=[kept, filled])
    result = _walk(domain)
    assert len(result.polygon.interiors) == 1
    assert Polygon(result.polygon.interiors[0]).area == 0.25
    assert "1 hole(s) below it filled" in result.diagnostics[2]
