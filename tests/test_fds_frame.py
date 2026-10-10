"""A walkable area in another frame than the FDS output (#26).

The setup coverage check (#426) reports how much of the walkable area lies
outside the FDS slices. These tests pin what makes a frame mismatch
recognisable in that report: the bounds of both areas and a hint when a swap
of x and y or a shift would bring the walkable area inside. They also pin
that the end-of-run count of samples outside reaches the run manifest.

The FDS output is the committed ``assets/iso_table21_coupled`` case, a
corridor x -50..50 m, y -1..1 m.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from shapely.affinity import translate
from shapely.geometry import Polygon
from test_fds_domain import _iso_run
from test_fds_domain_defects import _ISO, _sampler

from pyfds_evac.core.fds_coverage import (
    apply_coverage_policy,
    check_fds_coverage,
)
from pyfds_evac.core.fds_sampling import FdsDomainError, load_slice_sampler

_CORRIDOR = Polygon([(-50, -1), (50, -1), (50, 1), (-50, 1)])


@pytest.fixture(scope="module")
def samplers():
    sampler = load_slice_sampler(
        str(_ISO / "fds"), "SOOT EXTINCTION COEFFICIENT", slice_height_m=1.6
    )
    return [sampler]


def _summary(walkable, samplers) -> str:
    return check_fds_coverage(walkable=walkable, raw={}, samplers=samplers).summary()


def test_transposed_walkable_names_the_swap(samplers, caplog):
    transposed = Polygon([(-1, -50), (1, -50), (1, 50), (-1, 50)])
    report = check_fds_coverage(walkable=transposed, raw={}, samplers=samplers)
    with caplog.at_level(logging.WARNING):
        apply_coverage_policy(report, require_fds_coverage=False)
    message = caplog.records[-1].getMessage()
    assert "walkable area 196.00 m² (98.0 %)" in message
    assert "Walkable area x -1.00..1.00, y -50.00..50.00 m" in message
    assert "FDS domain x -50.00..50.00, y -1.00..1.00 m" in message
    assert (
        "With x and y swapped, at most 1 % of the walkable area would lie "
        "outside the FDS domain; if it should lie inside, check the axis order"
    ) in message


def test_offset_walkable_names_the_shift(samplers):
    shifted = translate(_CORRIDOR, 100.0, 5.0)
    message = _summary(shifted, samplers)
    assert "walkable area 200.00 m² (100.0 %)" in message
    assert "Walkable area x 50.00..150.00, y 4.00..6.00 m" in message
    assert "Shifted by (-100.00, -5.00) m, at most 1 % of the walkable" in message
    assert "check the origin of the geometry" in message


def test_transposed_and_offset_walkable_names_both(samplers):
    moved = translate(Polygon([(-1, -50), (1, -50), (1, 50), (-1, 50)]), 0.0, 60.0)
    message = _summary(moved, samplers)
    assert "With x and y swapped and shifted by (-60.00, +0.00) m, at most" in message
    assert "check the origin and axis order" in message


def test_partial_coverage_gives_bounds_but_no_hint(samplers):
    """A corridor reaching 10 m past the mesh: neither a swap nor a shift fits."""
    longer = Polygon([(-50, -1), (60, -1), (60, 1), (-50, 1)])
    message = _summary(longer, samplers)
    assert "walkable area 20.00 m²" in message
    assert "Walkable area x -50.00..60.00, y -1.00..1.00 m" in message
    assert "swapped" not in message and "Shifted" not in message


def test_partial_coverage_narrower_than_the_domain_gets_no_hint(samplers):
    """98 m of a 100 m domain, 3 m past one end: a shift would fit, but with
    3 % outside a frame mistake is not plausible; bounds only."""
    corridor = Polygon([(-45, -1), (53, -1), (53, 1), (-45, 1)])
    message = _summary(corridor, samplers)
    assert "walkable area 6.00 m²" in message
    assert "Walkable area x -45.00..53.00, y -1.00..1.00 m" in message
    assert "at most 1 %" not in message


@pytest.mark.parametrize(
    ("extent", "walkable"),
    [
        # A mesh margin of 2 m, the walkable area 1 m past it in x only.
        ((-2.0, 32.0, -2.0, 15.0), Polygon([(0, 0), (33, 0), (33, 13), (0, 13)])),
        # A 20 m x 6 m corridor 5 m past the mesh.
        ((-2.0, 28.0, -2.0, 8.0), Polygon([(13, 0), (33, 0), (33, 6), (13, 6)])),
    ],
    ids=["mesh-margin", "corridor-overhang"],
)
def test_ordinary_overhang_gets_bounds_only(extent, walkable):
    samplers = [_sampler("SOOT EXTINCTION COEFFICIENT", extent)]
    message = _summary(walkable, samplers)
    assert "Walkable area x" in message and "FDS domain x" in message
    assert "at most 1 %" not in message


def test_strict_error_advice_is_coherent_with_a_hint(samplers):
    report = check_fds_coverage(
        walkable=translate(_CORRIDOR, 100.0, 5.0), raw={}, samplers=samplers
    )
    with pytest.raises(FdsDomainError) as excinfo:
        apply_coverage_policy(report, require_fds_coverage=True)
    message = str(excinfo.value)
    assert "Walkable area x 50.00..150.00, y 4.00..6.00 m" in message
    assert (
        "check the origin of the geometry against the FDS deck. Otherwise extend "
        "the FDS meshes or slices over these objects, or run without"
    ) in message


def test_only_an_exit_outside_gives_no_bounds():
    """The walkable area lies inside; an exit and its sign reach outside."""
    samplers = [_sampler("SOOT EXTINCTION COEFFICIENT", (0.0, 10.0, 0.0, 10.0))]
    raw = {"exits": {"A": {"coordinates": [(12, 0), (13, 0), (13, 1), (12, 1)]}}}
    report = check_fds_coverage(walkable=_ROOM, raw=raw, samplers=samplers)
    message = report.summary()
    assert not report.is_empty
    assert "exit A 1.00 m²" in message and "sign A" in message
    assert message.endswith("sign A.")
    assert "Walkable area x" not in message


_ROOM = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


@pytest.mark.parametrize(
    "second",
    [(20.0, 30.0, 0.0, 10.0), (10.0, 20.0, 0.0, 10.0)],
    ids=["disjoint", "touching-edge"],
)
def test_samplers_sharing_no_area_give_no_bounds(second, caplog):
    """The domain is empty or a line: no bounds or hint, the report as before."""
    samplers = [
        _sampler("SOOT EXTINCTION COEFFICIENT", (0.0, 10.0, 0.0, 10.0)),
        _sampler("TEMPERATURE", second),
    ]
    report = check_fds_coverage(walkable=_ROOM, raw={}, samplers=samplers)
    assert report.walkable_outside_m2 == pytest.approx(100.0)
    assert report.walkable_bounds is None and report.frame_hint is None
    with caplog.at_level(logging.WARNING):
        apply_coverage_policy(report, require_fds_coverage=False)
    message = caplog.records[-1].getMessage()
    assert "walkable area 100.00 m² (100.0 %)." in message
    assert "Walkable area x" not in message


def test_differing_sampler_extents_report_their_intersection():
    samplers = [
        _sampler("SOOT EXTINCTION COEFFICIENT", (0.0, 30.0, 0.0, 13.0)),
        _sampler("TEMPERATURE", (0.0, 20.0, 0.0, 13.0)),
    ]
    walkable = Polygon([(0, 0), (30, 0), (30, 13), (0, 13)])
    message = _summary(walkable, samplers)
    assert "FDS domain x 0.00..20.00, y 0.00..13.00 m." in message
    assert "at most 1 %" not in message


_L_EXTENTS = ((0.0, 10.0, 0.0, 2.0), (0.0, 2.0, 0.0, 10.0))
_L_SHAPE = Polygon([(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)])


def test_l_shaped_domain_names_the_shift():
    samplers = [_sampler("SOOT EXTINCTION COEFFICIENT", *_L_EXTENTS)]
    message = _summary(translate(_L_SHAPE, 20.0, 5.0), samplers)
    assert "FDS domain x 0.00..10.00, y 0.00..10.00 m." in message
    assert "Shifted by (-20.00, -5.00) m, at most 1 %" in message


def test_l_shaped_domain_does_not_cover_its_bounding_box():
    """The room over the L reaches into the L's notch: no swap or shift fits."""
    samplers = [_sampler("SOOT EXTINCTION COEFFICIENT", *_L_EXTENTS)]
    message = _summary(_ROOM, samplers)
    assert "walkable area 64.00 m²" in message
    assert "at most 1 %" not in message


@pytest.mark.parametrize(("height", "hint"), [(10.1, True), (10.2, False)])
def test_hint_threshold_is_one_percent_outside(height, hint):
    """After the shift 0.1 m of the height stays outside: 1 m² of 101 m² is
    under 1 %, 2 m² of 102 m² is over it."""
    samplers = [_sampler("SOOT EXTINCTION COEFFICIENT", (0.0, 10.0, 0.0, 10.0))]
    walkable = Polygon([(20, 0), (30, 0), (30, height), (20, height)])
    message = _summary(walkable, samplers)
    assert ("Shifted by (-20.00, +0.00) m" in message) is hint


def test_inside_the_domain_the_summary_has_no_bounds(samplers):
    message = _summary(_CORRIDOR, samplers)
    assert "all lie inside" in message
    assert "Walkable area x" not in message


def test_manifest_records_the_count_outside(tmp_path: Path):
    result = _iso_run(tmp_path)
    try:
        manifest = json.loads(Path(result.manifest_file).read_text())
        assert manifest["fds_outside"] == result.metrics["fds_outside"]
        assert manifest["fds_outside"]["rows"] > 0
    finally:
        result.cleanup()
