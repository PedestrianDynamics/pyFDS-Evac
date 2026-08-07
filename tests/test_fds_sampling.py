"""load_slice_sampler candidate-quantity resolution.

`EXTINCTION` and `SOOT EXTINCTION COEFFICIENT` are two unrelated FDS slice
quantities (FDS User Guide Sec. 22.10.29 vs. Sec. 22.10.5): the former is a
0/1/-1 combustion-suppression flag, the latter is the K [1/m] smoke
extinction coefficient. Older code treated `EXTINCTION` as a fallback
spelling of the soot slice, so a case missing the real slice would silently
sample the combustion flag instead and feed 0/1/-1 into the smoke-speed
model as if it were K. These tests pin down that the fallback is gone.
"""

from types import SimpleNamespace

import pytest

from pyfds_evac.core.fds_sampling import load_slice_sampler


class _FakeExtent:
    def __init__(self):
        self.x_start, self.x_end = 0.0, 10.0
        self.y_start, self.y_end = 0.0, 10.0
        self.z_start, self.z_end = 1.9, 2.1


class _FakeSlice:
    def __init__(self):
        self.extent = _FakeExtent()
        self.subslices = []


def _sim_with(quantity_to_slices: dict):
    """Build a stand-in for `fdsreader.Simulation` keyed by quantity name."""

    def filter_by_quantity(name):
        return list(quantity_to_slices.get(name, []))

    return SimpleNamespace(slices=SimpleNamespace(filter_by_quantity=filter_by_quantity))


def test_soot_extinction_coefficient_resolves():
    soot_slice = _FakeSlice()
    sim = _sim_with({"SOOT EXTINCTION COEFFICIENT": [soot_slice]})
    sampler = load_slice_sampler("case", "SOOT EXTINCTION COEFFICIENT", simulation=sim)
    assert sampler._slice is soot_slice


def test_bare_extinction_slice_is_not_used_as_a_fallback():
    """A case with only the combustion-flag slice must not resolve silently.

    `EXTINCTION` is a distinct FDS quantity, not an alias for the smoke
    extinction coefficient, so it must never be substituted in.
    """
    sim = _sim_with({"EXTINCTION": [_FakeSlice()]})
    with pytest.raises(IndexError) as excinfo:
        load_slice_sampler("case", "SOOT EXTINCTION COEFFICIENT", simulation=sim)
    assert "SOOT EXTINCTION COEFFICIENT" in str(excinfo.value)


def test_extinction_field_from_fds_does_not_fall_back_to_the_combustion_flag():
    from pyfds_evac.core.smoke_speed import ExtinctionField

    sim = _sim_with({"EXTINCTION": [_FakeSlice()]})
    with pytest.raises(IndexError):
        ExtinctionField.from_fds("case", simulation=sim)
