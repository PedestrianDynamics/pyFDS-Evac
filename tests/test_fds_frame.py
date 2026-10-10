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
from test_fds_domain_defects import _ISO

from pyfds_evac.core.fds_coverage import (
    apply_coverage_policy,
    check_fds_coverage,
)
from pyfds_evac.core.fds_sampling import load_slice_sampler

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
    assert "With x and y swapped" in message


def test_offset_walkable_names_the_shift(samplers):
    shifted = translate(_CORRIDOR, 100.0, 5.0)
    message = _summary(shifted, samplers)
    assert "walkable area 200.00 m² (100.0 %)" in message
    assert "Walkable area x 50.00..150.00, y 4.00..6.00 m" in message
    assert "Shifted by (-100.00, -5.00) m the walkable area" in message


def test_transposed_and_offset_walkable_names_both(samplers):
    moved = translate(Polygon([(-1, -50), (1, -50), (1, 50), (-1, 50)]), 0.0, 60.0)
    message = _summary(moved, samplers)
    assert "With x and y swapped and shifted by (-60.00, +0.00) m" in message


def test_partial_coverage_gives_bounds_but_no_hint(samplers):
    """A corridor reaching 10 m past the mesh: neither a swap nor a shift fits."""
    longer = Polygon([(-50, -1), (60, -1), (60, 1), (-50, 1)])
    message = _summary(longer, samplers)
    assert "walkable area 20.00 m²" in message
    assert "Walkable area x -50.00..60.00, y -1.00..1.00 m" in message
    assert "swapped" not in message and "Shifted" not in message


def test_partial_coverage_narrower_than_the_domain_gets_a_shift_hint(samplers):
    """3 m past the mesh, 3 m short of the other end: a shift fits, so the
    hint is given although the setup may be intended."""
    corridor = Polygon([(-47, -1), (53, -1), (53, 1), (-47, 1)])
    message = _summary(corridor, samplers)
    assert "walkable area 6.00 m²" in message
    assert "Shifted by (-3.00, +0.00) m the walkable area" in message


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
