"""The package ships its type hints (PEP 561)."""

from importlib.resources import files

from pyfds_evac.core.fed import heat_flux_row_fields


def test_py_typed_marker_ships():
    assert (files("pyfds_evac") / "py.typed").is_file()


def test_heat_flux_row_fields_without_a_heat_model_is_empty():
    assert heat_flux_row_fields(None, 20.0) == {}
