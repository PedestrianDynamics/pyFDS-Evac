"""Public API of ``pyfds_evac``: lazy re-exports and config defaults."""

import subprocess
import sys

import pytest

import pyfds_evac


@pytest.mark.parametrize("name", pyfds_evac.__all__)
def test_exported_name_resolves_to_defining_module(name):
    value = getattr(pyfds_evac, name)
    assert value.__name__ == name
    assert value.__module__.startswith("pyfds_evac.core.")


def test_unknown_name_raises_attribute_error():
    with pytest.raises(AttributeError, match="no_such_name"):
        pyfds_evac.no_such_name  # noqa: B018


def test_dir_lists_exports():
    assert set(pyfds_evac.__all__) <= set(dir(pyfds_evac))


def test_bare_import_does_not_load_heavy_modules():
    code = (
        "import sys, pyfds_evac\n"
        "heavy = [m for m in ('pandas', 'matplotlib', 'pyfds_evac.core') "
        "if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_fds_dir_defaults_to_none():
    assert pyfds_evac.SmokeSpeedConfig().fds_dir is None
    assert pyfds_evac.DefaultFedConfig().fds_dir is None


def test_smoke_speed_model_without_fds_dir():
    model = pyfds_evac.SmokeSpeedModel(
        pyfds_evac.ConstantExtinctionField(1.0), pyfds_evac.SmokeSpeedConfig()
    )
    extinction, factor = model.sample(0.0, 0.0, 0.0)
    assert extinction == 1.0
    assert 0.0 < factor < 1.0
