"""Two defects at the edge of the FDS domain (#426, #427).

Outside the FDS slices pyFDS-Evac reads ambient air and clear sight, as
FDS+Evac does (``evac.f90`` sets every evacuation cell outside the fire meshes
to ambient and clear). These tests use only API that predates the fix, so
they fail on the defective revision by assertion:

* #427: a point that some gas slices cover and others do not read ambient
  for every gas, silently. It now raises, as heat already did.
* #426: an observer off the vismap grid was clamped onto the edge cell, so it
  read the sight line of a cell somewhere else and its reading distance was
  measured from that cell. It now gets clear-air sight within the reading
  distance, measured from the observer.

The synthetic slices are one-cell rectangles with a value per frame, shared
with ``test_fds_domain.py``; the real vismap case uses the committed
``assets/iso_table21_coupled`` output, a corridor x -50..50 m, y -1..1 m with
K = 1/m at 1.6 and 2.0 m.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import SliceFieldSampler
from pyfds_evac.core.fed import DefaultFedInputs, FdsFedField
from pyfds_evac.core.visibility import VisibilityModel, _VisMapCache

_REPO = Path(__file__).resolve().parents[1]
_ISO = _REPO / "assets" / "iso_table21_coupled"


class _Slice:
    """One cell per subslice, frames 0..10 s, value = 0.01 * frame.

    Each extent (x_start, x_end, y_start, y_end) is one subslice (one mesh).
    """

    def __init__(self, name, *extents):
        self.times = np.arange(0.0, 11.0)
        self.quantity = SimpleNamespace(name=name)
        self.subslices = [_subslice(*extent) for extent in extents]

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _subslice(x0, x1, y0, y1):
    return SimpleNamespace(
        extent=SimpleNamespace(x_start=x0, x_end=x1, y_start=y0, y_end=y1),
        mesh=SimpleNamespace(coordinates={"x": np.array([x0]), "y": [y0]}),
        cell_centered=False,
        data=0.01 * np.arange(11.0).reshape(11, 1, 1),
    )


def _sampler(name, *extents):
    return SliceFieldSampler(_Slice(name, *(extents or [(0.0, 1.0, 0.0, 1.0)])))


_FAR = (5.0, 6.0, 0.0, 1.0)  # a slice that misses the point (0.5, 0.5)


def _fed_field(co=None, co2=None, o2=None, **kwargs):
    return FdsFedField(
        _sampler("CARBON MONOXIDE VOLUME FRACTION", co or (0.0, 1.0, 0.0, 1.0)),
        _sampler("CARBON DIOXIDE VOLUME FRACTION", co2 or (0.0, 1.0, 0.0, 1.0)),
        _sampler("OXYGEN VOLUME FRACTION", o2 or (0.0, 1.0, 0.0, 1.0)),
        **kwargs,
    )


def test_partial_gas_coverage_raises_naming_point_and_quantity():
    """CO misses a point that CO2 and O2 cover: no silent ambient (#427)."""
    field = _fed_field(co=_FAR)
    with pytest.raises(ValueError, match="CARBON MONOXIDE") as excinfo:
        field.sample_inputs(3.0, 0.5, 0.5)
    assert "(0.5, 0.5)" in str(excinfo.value)


def test_optional_species_missing_where_the_trio_covers_raises():
    field = _fed_field(hcn=_sampler("HYDROGEN CYANIDE VOLUME FRACTION", _FAR))
    with pytest.raises(ValueError, match="HYDROGEN CYANIDE"):
        field.sample_inputs(3.0, 0.5, 0.5)


def test_optional_species_covering_where_the_trio_does_not_raises():
    field = _fed_field(
        co=_FAR,
        co2=_FAR,
        o2=_FAR,
        hcl=_sampler("HYDROGEN CHLORIDE VOLUME FRACTION"),
    )
    with pytest.raises(ValueError, match="CARBON MONOXIDE"):
        field.sample_inputs(3.0, 0.5, 0.5)


def test_every_gas_outside_still_reads_ambient():
    """The FDS+Evac default outside the domain is unchanged."""
    assert (
        _fed_field(co=_FAR, co2=_FAR, o2=_FAR).sample_inputs(3.0, 0.5, 0.5)
        == DefaultFedInputs()
    )


def test_inside_values_are_the_same_floats():
    """In the domain the volume fractions convert exactly as before."""
    inputs = _fed_field().sample_inputs(3.0, 0.5, 0.5)
    assert inputs.co_volume_fraction_percent == 100.0 * 0.03
    assert inputs.o2_volume_fraction_percent == 100.0 * 0.03


def _vis_model(visible: bool, signs=None, **kwargs):
    """A 3 x 1 vismap grid at x = 0, 1, 2 m (cells reach -0.5..2.5 m)."""
    shape = (2, 1, 1, 3)
    cache = _VisMapCache(
        time_points=np.array([0.0, 10.0]),
        x_coords=np.array([0.0, 1.0, 2.0]),
        y_coords=np.array([0.0]),
        vis=np.full(shape, visible, dtype=bool),
        metres=np.full(shape, 12.0 if visible else 0.0),
    )
    signs = signs or {"s": {"x": 1.0, "y": 0.0}}
    with patch("pyfds_evac.core.visibility._resolve_vis", return_value=cache):
        return VisibilityModel("unused", signs, **kwargs)


def test_observer_off_the_grid_beyond_the_cap_does_not_see_the_sign():
    """101 m from the sign, 30 m cap: invisible, whatever the edge cell says."""
    model = _vis_model(visible=True)
    assert model.node_is_visible(0.0, -100.0, 0.0, "s") is False


def test_observer_off_the_grid_within_the_cap_sees_in_clear_air():
    """Smoke at the edge cell does not reach an observer outside (D-3 a)."""
    model = _vis_model(visible=False)
    assert model.node_is_visible(0.0, -20.0, 0.0, "s") is True


def test_a_sign_reading_distance_is_measured_from_the_observer():
    model = _vis_model(
        visible=True, signs={"s": {"x": 1.0, "y": 0.0, "max_distance": 5}}
    )
    assert model.node_is_visible(0.0, -3.0, 0.0, "s") is True  # 4 m
    assert model.node_is_visible(0.0, -5.0, 0.0, "s") is False  # 6 m


def test_sighting_distance_off_the_grid_is_none():
    model = _vis_model(visible=True)
    assert model.visibility_to_node(0.0, -20.0, 0.0, "s") is None


def test_observer_on_the_grid_reads_the_grid():
    """Within half a cell of the edge the cell still answers (I1)."""
    model = _vis_model(visible=False)
    assert model.node_is_visible(0.0, -0.5, 0.0, "s") is False
    assert model.node_is_visible(0.0, 2.5, 0.0, "s") is False
    assert _vis_model(visible=True).visibility_to_node(0.0, 2.4, 0.0, "s") == 12.0


def test_real_vismap_observer_beyond_the_mesh_reads_clear_air(tmp_path):
    """K = 1/m in the corridor: from inside, a sign 18 m away is hidden (3 m).

    From x = 58 m, outside the mesh, the old clamp read the edge cell at
    x = 50 m, 10 m from the sign, and hid it too. Outside is clear air now,
    and 18 m is within the 30 m reading distance.
    """
    signs = {"s": {"x": 40.0, "y": 0.0}, "far": {"x": 55.0, "y": 0.0}}
    with patch.object(logging.getLogger("pyfds_evac.core.visibility"), "warning"):
        model = VisibilityModel(
            str(_ISO / "fds"), signs, time_step_s=50.0, slice_height_m=2.0
        )
    assert model.node_is_visible(50.0, 22.0, 0.0, "s") is False
    assert model.node_is_visible(50.0, 58.0, 0.0, "s") is True
