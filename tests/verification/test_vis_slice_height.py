"""Sign legibility reads the extinction slice nearest the sampling height (#296).

``assets/vis_slice_height`` is a sealed 10 x 10 x 3 m room around the plan
origin with soot in three layers at t = 0, so the extinction coefficient is
about 3.0 1/m below 1 m, 1.0 1/m from 1 to 2 m and 0.3 1/m above 2 m. Its
slices are declared in an adversarial order: a vertical slice through the plan
origin first, then 0.5 m, then 2.5 m, and the sign-height slice (PBZ=1.6,
placed by FDS at 1.5 m) last. The FDS output is committed (about 12 kB) so
this runs in CI.

Expected values come from the deck, not from pyFDS-Evac. fdsreader's
``SliceCollection.get_nearest``, which fdsvismap uses by default, returns the
vertical slice here, and the first horizontal slice listed (0.5 m) when there
is none; walking speed and FED read the 1.5 m slice.
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from pyfds_evac.core import fds_sampling
from pyfds_evac.core.visibility import VisibilityModel, _build_vismap

pytest.importorskip("fdsreader")
pytest.importorskip("fdsvismap")

FDS_DIR = Path(__file__).resolve().parents[2] / "assets" / "vis_slice_height" / "fds"
SIGN = {"s0": {"x": 0.0, "y": 0.0, "c": 3}}
# Requested height -> (z of the slice FDS wrote, K of that layer in 1/m).
LAYERS = {0.5: (0.5, 3.0), 1.6: (1.5, 1.0), 2.6: (2.5, 0.3)}
# The layers mix slightly at the slice planes in the 2 s run; 5 % separates
# layers that differ by a factor of 3.
REL = 0.05


def _vismap(height):
    return _build_vismap(str(FDS_DIR), SIGN, time_step_s=1.0, slice_height_m=height)


@pytest.mark.parametrize("height", sorted(LAYERS))
def test_each_height_reads_its_layer(height):
    z, k = LAYERS[height]
    vis = _vismap(height)
    assert vis.slc.extent.z_start == pytest.approx(z)
    assert vis.slc.to_global()[-1].mean() == pytest.approx(k, rel=REL)


def test_sighting_distance_follows_the_sign_height_layer():
    """The path a run takes: 1.6 m sees c / K = 3 / 1.0 m, not 3 / 3.0 m."""
    model = VisibilityModel(str(FDS_DIR), SIGN, time_step_s=1.0, slice_height_m=1.6)
    assert model.visibility_to_node(1.0, 2.0, 0.0, "s0") == pytest.approx(3.0, rel=REL)


def test_a_vertical_slice_listed_first_is_never_chosen():
    for height in (0.0, 1.5, 3.0):
        assert _vismap(height).slc.orientation == 3


def test_selection_is_the_one_the_slice_sampler_uses(caplog):
    """One rule for every FDS reading: horizontal, nearest z, warned when far."""
    with patch.object(
        fds_sampling,
        "select_horizontal_slice",
        wraps=fds_sampling.select_horizontal_slice,
    ) as spy:
        with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
            vis = _vismap(5.0)
    spy.assert_called_once()
    assert vis.slc.extent.z_start == pytest.approx(2.5)
    assert "at z=2.50 m (2.50 m away" in caplog.text


def test_the_deck_puts_a_vertical_slice_first():
    """Guard the adversarial order the tests above rely on."""
    fdsreader = pytest.importorskip("fdsreader")
    sim = fdsreader.Simulation(str(FDS_DIR))
    slices = sim.slices.filter_by_quantity("SOOT EXTINCTION COEFFICIENT")
    assert [s.orientation for s in slices] == [2, 3, 3, 3]
    assert [s.extent.z_start for s in slices] == [0.0, 0.5, 2.5, 1.5]
