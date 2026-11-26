"""The stable ``pyfds_evac.core`` names are pinned; the rest stay importable."""

import importlib

import pytest

import pyfds_evac
import pyfds_evac.core

# The names docs/*.md and README.md import from or reach through
# ``pyfds_evac.core``. Changing this list changes the 1.x API: see
# "API stability" in docs/usage.md.
STABLE_CORE_NAMES = ["load_scenario", "run_scenario"]

DROPPED_FROM_ALL = sorted(set(pyfds_evac.core._EXPORTS) - set(STABLE_CORE_NAMES))


def test_core_all_is_pinned():
    assert sorted(pyfds_evac.core.__all__) == STABLE_CORE_NAMES
    assert sorted(dir(pyfds_evac.core)) == STABLE_CORE_NAMES


def test_stable_core_names_are_public_names_too():
    assert set(pyfds_evac.core.__all__) <= set(pyfds_evac.__all__)


@pytest.mark.parametrize("name", DROPPED_FROM_ALL)
def test_dropped_name_stays_importable(name):
    module = importlib.import_module("pyfds_evac.core")
    attribute = getattr(module, name)
    namespace: dict[str, object] = {}
    exec(f"from pyfds_evac.core import {name}", namespace)
    assert namespace[name] is attribute
