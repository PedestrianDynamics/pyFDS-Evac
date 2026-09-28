"""A heat-only FDS case (TEMPERATURE slice, no soot) must run (#248).

The fixture ``assets/heat_only_no_soot/fds`` is a real FDS 6.10.1 output of
``assets/heat_only_no_soot/heat_only_no_soot.fds``: one TEMPERATURE slice at
2.0 m and no SOOT EXTINCTION COEFFICIENT slice. It shares the 30x30 m
footprint of ``assets/fed_incap_heat_150c``, whose config (discovery agents
and signed checkpoints) drives it, so the build reaches both the smoke-speed
and the FDS visibility model.

The gas FED and heat FED builders skip themselves with a warning when their
slices are missing. The smoke-speed and visibility builders must degrade the
same way instead of raising, so a heat-only case no longer needs
``--constant-extinction 0 --no-visibility``.
"""

import logging
from argparse import Namespace
from pathlib import Path

import pytest

from pyfds_evac.core.fds_inventory import inspect_fds_quantities
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.smoke_speed import SmokeSpeedModel

_REPO = Path(__file__).resolve().parent.parent
_FDS_DIR = str(_REPO / "assets" / "heat_only_no_soot" / "fds")
_SCENARIO_DIR = str(_REPO / "assets" / "fed_incap_heat_150c")

# Defaults mirror run.py's argparse dests for the fields build_run_kwargs reads.
_DEFAULT_OPTS = dict(
    seed=42,
    fds_dir=_FDS_DIR,
    constant_extinction=None,
    smoke_update_interval=1.0,
    smoke_slice_height=2.0,
    enable_rerouting=False,
    reroute_interval=1.0,
    vis_cache=None,
    disable_tenability=False,
    fic_alpha=1.2,
    fic_min_factor=0.0,
    fed_threshold=1.0,
    output_route_cost_history=None,
    enable_heat_fed=True,
)

# Today the smoke builder raises IndexError (fds_sampling) and the visibility
# builder AttributeError (fdsvismap finds no soot slice and reads None).
_pending_248 = pytest.mark.xfail(
    strict=True, reason="#248", raises=(IndexError, AttributeError)
)


def _opts(**overrides) -> Namespace:
    return Namespace(**{**_DEFAULT_OPTS, **overrides})


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(_SCENARIO_DIR)


def _mentions_extinction(caplog) -> bool:
    for record in caplog.records:
        if record.levelno < logging.WARNING:
            continue
        text = record.getMessage().lower()
        if "extinction" in text or "soot" in text:
            return True
    return False


def test_fixture_has_temperature_and_no_soot():
    """Pin the fixture: the bug needs TEMPERATURE present and soot absent."""
    names = inspect_fds_quantities(_FDS_DIR).canonical_slice_names()
    assert "temperature" in names
    assert "extinction" not in names


def test_scenario_reaches_fds_visibility_model(scenario):
    """Pin the config: discovery agents and signs, so vis is built from FDS."""
    from pyfds_evac.core.run_config import _has_discovery_agents
    from pyfds_evac.core.visibility import extract_sign_descriptors

    assert _has_discovery_agents(scenario)
    assert extract_sign_descriptors(scenario.raw)


def test_workaround_flags_build_heat_fed(scenario):
    """The documented workaround keeps working after the fix."""
    kwargs = build_run_kwargs(
        scenario, _opts(constant_extinction=0.0, no_visibility=True)
    )
    assert isinstance(kwargs["smoke_speed_model"], SmokeSpeedModel)
    assert kwargs["vis_model"] is None
    assert kwargs["fed_model"] is None
    assert kwargs["heat_fed_model"] is not None
    assert kwargs["tenability_config"].enable_heat_incapacitation is True


@_pending_248
def test_heat_only_case_builds_without_workaround(scenario, caplog):
    """No flags: smoke speed is off, heat FED is on, and a warning says why."""
    with caplog.at_level(logging.WARNING):
        kwargs = build_run_kwargs(scenario, _opts())
    assert kwargs["smoke_speed_model"] is None
    assert kwargs["fed_model"] is None
    assert kwargs["heat_fed_model"] is not None
    assert kwargs["tenability_config"].enable_heat_incapacitation is True
    assert _mentions_extinction(caplog)


@_pending_248
def test_missing_soot_does_not_break_visibility(scenario, caplog):
    """An explicit constant extinction isolates the visibility builder.

    Whether the fallback is no visibility model (agents learn by contact) or
    a clear-air model (geometry and sign facing still gate sight) is left to
    the fix; either way the build must not raise and must warn.
    """
    with caplog.at_level(logging.WARNING):
        kwargs = build_run_kwargs(scenario, _opts(constant_extinction=0.0))
    assert isinstance(kwargs["smoke_speed_model"], SmokeSpeedModel)
    assert kwargs["heat_fed_model"] is not None
    assert _mentions_extinction(caplog)


def test_constant_extinction_overrides_missing_soot(scenario):
    """An explicit --constant-extinction still wins over the missing slice."""
    kwargs = build_run_kwargs(
        scenario, _opts(constant_extinction=0.3, no_visibility=True)
    )
    model = kwargs["smoke_speed_model"]
    assert isinstance(model, SmokeSpeedModel)
    assert model.field.sample_extinction(0.0, 15.0, 15.0) == pytest.approx(0.3)
