"""`load_slice_sampler`: which quantity resolves, and which slice of it.

Two independent concerns, merged here because they exercise the same entry
point.

**Quantity resolution.** `EXTINCTION` and `SOOT EXTINCTION COEFFICIENT` are
unrelated FDS quantities (User Guide Sec. 22.10.29 vs. Sec. 22.10.5): the
former is a 0/1/-1 combustion-suppression flag, the latter the K [1/m] smoke
extinction coefficient. Older code treated `EXTINCTION` as a fallback spelling
of the soot slice, so a case missing the real slice silently sampled the
combustion flag and fed 0/1/-1 into the smoke-speed model as if it were K.

**Slice selection.** Height only ever breaks ties between slices of the *same*
quantity. A case holding exactly one such slice uses it whatever its z, which
is the quiet failure the height tests pin down: the run continues with readings
from the wrong part of the smoke layer unless something says so.
"""

import logging
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fds_sampling import load_slice_sampler


class _FakeExtent:
    def __init__(self, z_start=1.9, z_end=2.1):
        self.x_start, self.x_end = 0.0, 10.0
        self.y_start, self.y_end = 0.0, 10.0
        self.z_start, self.z_end = z_start, z_end


class _FakeSlice:
    def __init__(self, z_start=1.9, z_end=2.1):
        self.extent = _FakeExtent(z_start, z_end)
        self.subslices = []


def _sim_with_quantities(quantity_to_slices: dict):
    """Stand-in keyed by quantity name, for tests about *which quantity* wins."""

    def filter_by_quantity(name):
        return list(quantity_to_slices.get(name, []))

    return SimpleNamespace(
        slices=SimpleNamespace(filter_by_quantity=filter_by_quantity)
    )


def _sim_with(*slices):
    """Stand-in returning these slices for any name, for tests about *which
    slice of one quantity* wins -- the quantity is not the variable there."""
    matched = list(slices)
    return SimpleNamespace(
        slices=SimpleNamespace(filter_by_quantity=lambda name: matched)
    )


def test_soot_extinction_coefficient_resolves():
    soot_slice = _FakeSlice()
    sim = _sim_with_quantities({"SOOT EXTINCTION COEFFICIENT": [soot_slice]})
    sampler = load_slice_sampler("case", "SOOT EXTINCTION COEFFICIENT", simulation=sim)
    assert sampler._slice is soot_slice


def test_bare_extinction_slice_is_not_used_as_a_fallback():
    """A case with only the combustion-flag slice must not resolve silently.

    `EXTINCTION` is a distinct FDS quantity, not an alias for the smoke
    extinction coefficient, so it must never be substituted in.
    """
    sim = _sim_with_quantities({"EXTINCTION": [_FakeSlice()]})
    with pytest.raises(IndexError) as excinfo:
        load_slice_sampler("case", "SOOT EXTINCTION COEFFICIENT", simulation=sim)
    assert "SOOT EXTINCTION COEFFICIENT" in str(excinfo.value)


def test_extinction_field_from_fds_does_not_fall_back_to_the_combustion_flag():
    from pyfds_evac.core.smoke_speed import ExtinctionField

    sim = _sim_with_quantities({"EXTINCTION": [_FakeSlice()]})
    with pytest.raises(IndexError):
        ExtinctionField.from_fds("case", simulation=sim)


def test_single_slice_is_used_whatever_its_height():
    only = _FakeSlice(0.4, 0.6)
    sampler = load_slice_sampler(
        "case",
        "SOOT EXTINCTION COEFFICIENT",
        simulation=_sim_with(only),
        slice_height_m=2.0,
    )
    assert sampler._slice is only


def test_nearest_slice_wins_when_several_match():
    low, mid, high = _FakeSlice(0.4, 0.6), _FakeSlice(1.9, 2.1), _FakeSlice(4.9, 5.1)
    sampler = load_slice_sampler(
        "case",
        "SOOT EXTINCTION COEFFICIENT",
        simulation=_sim_with(low, mid, high),
        slice_height_m=2.0,
    )
    assert sampler._slice is mid


def test_height_mismatch_warns(caplog):
    with caplog.at_level(logging.WARNING):
        load_slice_sampler(
            "case",
            "SOOT EXTINCTION COEFFICIENT",
            simulation=_sim_with(_FakeSlice(0.4, 0.6)),
            slice_height_m=2.0,
        )
    assert "SOOT EXTINCTION COEFFICIENT" in caplog.text
    # The message must name both heights so the mismatch is actionable.
    assert "2.00" in caplog.text
    assert "0.50" in caplog.text


def test_no_warning_when_the_slice_is_close_enough(caplog):
    with caplog.at_level(logging.WARNING):
        load_slice_sampler(
            "case",
            "SOOT EXTINCTION COEFFICIENT",
            simulation=_sim_with(_FakeSlice(1.9, 2.1)),
            slice_height_m=2.0,
        )
    assert caplog.text == ""


def test_no_warning_when_no_height_was_requested(caplog):
    with caplog.at_level(logging.WARNING):
        load_slice_sampler(
            "case",
            "SOOT EXTINCTION COEFFICIENT",
            simulation=_sim_with(_FakeSlice(0.4, 0.6)),
        )
    assert caplog.text == ""


def test_missing_quantity_names_every_candidate_tried():
    with pytest.raises(IndexError) as excinfo:
        load_slice_sampler(
            "case",
            ("SOOT EXTINCTION COEFFICIENT", "EXTINCTION"),
            simulation=_sim_with(),
        )
    assert "'SOOT EXTINCTION COEFFICIENT'" in str(excinfo.value)
    assert "'EXTINCTION'" in str(excinfo.value)


class _FakeVerticalSlice(_FakeSlice):
    """A PBY slice: spans the whole height, orientation 2 in fdsreader."""

    def __init__(self):
        super().__init__(0.0, 3.0)
        self.orientation = 2


def test_vertical_slice_is_not_chosen_by_height():
    """A vertical slice's mid-height can sit closest to the request; skip it."""
    vertical = _FakeVerticalSlice()  # mid-height 1.5 m
    horizontal = _FakeSlice(2.0, 2.0)
    horizontal.orientation = 3
    sampler = load_slice_sampler(
        "case",
        "SOOT EXTINCTION COEFFICIENT",
        simulation=_sim_with(vertical, horizontal),
        slice_height_m=1.6,
    )
    assert sampler._slice is horizontal


def test_vertical_slice_is_not_chosen_without_a_height():
    vertical = _FakeVerticalSlice()
    horizontal = _FakeSlice(2.0, 2.0)
    horizontal.orientation = 3
    sampler = load_slice_sampler(
        "case",
        "SOOT EXTINCTION COEFFICIENT",
        simulation=_sim_with(vertical, horizontal),
    )
    assert sampler._slice is horizontal


def test_only_vertical_slices_raise():
    with pytest.raises(IndexError, match="horizontal"):
        load_slice_sampler(
            "case",
            "SOOT EXTINCTION COEFFICIENT",
            simulation=_sim_with(_FakeVerticalSlice()),
            slice_height_m=1.6,
        )


def _layered(*heights):
    """A vertical slice first, then horizontal slices at these heights."""
    slices = [_FakeVerticalSlice()]
    for z in heights:
        s = _FakeSlice(z, z)
        s.orientation = 3
        slices.append(s)
    return slices


def test_fed_field_reads_every_species_at_the_requested_height():
    """Required and optional gases alike: nearest horizontal slice, not the first."""
    from pyfds_evac.core.fed import FdsFedField

    species = [
        "CARBON MONOXIDE VOLUME FRACTION",
        "CARBON DIOXIDE VOLUME FRACTION",
        "OXYGEN VOLUME FRACTION",
    ] + [quantity for _, quantity in FdsFedField._OPTIONAL_SPECIES]
    by_quantity = {q: _layered(0.5, 2.5, 1.5) for q in species}
    field = FdsFedField.from_fds(
        "case", simulation=_sim_with_quantities(by_quantity), slice_height_m=1.6
    )
    expected = by_quantity["CARBON MONOXIDE VOLUME FRACTION"][3]
    assert field._co._slice is expected
    assert field._co2._slice is by_quantity["CARBON DIOXIDE VOLUME FRACTION"][3]
    assert field._o2._slice is by_quantity["OXYGEN VOLUME FRACTION"][3]
    for attr, quantity in FdsFedField._OPTIONAL_SPECIES:
        assert getattr(field, attr)._slice is by_quantity[quantity][3], attr


def test_fed_field_leaves_absent_optional_species_unset():
    from pyfds_evac.core.fed import FdsFedField

    required = {
        q: _layered(1.5)
        for q in (
            "CARBON MONOXIDE VOLUME FRACTION",
            "CARBON DIOXIDE VOLUME FRACTION",
            "OXYGEN VOLUME FRACTION",
        )
    }
    field = FdsFedField.from_fds("case", simulation=_sim_with_quantities(required))
    assert field._hcn is None
