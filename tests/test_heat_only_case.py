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

from pyfds_evac.core import run_config
from pyfds_evac.core.fds_inventory import inspect_fds_quantities
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.smoke_speed import SmokeSpeedModel
from pyfds_evac.core.visibility import VisibilityModel

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


def _opts(**overrides) -> Namespace:
    return Namespace(**{**_DEFAULT_OPTS, **overrides})


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(_SCENARIO_DIR)


def _mentions_extinction(caplog) -> bool:
    for record in caplog.records:
        # fdsreader warns on the root logger about the files it lacks.
        if record.levelno < logging.WARNING or not record.name.startswith("pyfds_evac"):
            continue
        # The fixture's name contains "soot"; other warnings (e.g. FED
        # disabled) quote its path, so drop the name before matching.
        text = record.getMessage().lower().replace("heat_only_no_soot", "")
        if "extinction" in text or "soot" in text:
            return True
    return False


# Distinctive phrases of the two fallback warnings in run_config.
_SMOKE_WARNING = "smoke speed reduction is disabled"
_VIS_WARNING = "visibility falls back to clear air"


def _count_warnings(caplog, phrase: str) -> int:
    return sum(
        1
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and record.name.startswith("pyfds_evac")
        and phrase in record.getMessage().lower()
    )


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


def test_workaround_flags_build_heat_fed(scenario, caplog):
    """The documented workaround keeps working after the fix.

    With both flags nothing reads extinction, so nothing may warn about it;
    this is also the negative control for ``_mentions_extinction``.
    """
    with caplog.at_level(logging.WARNING):
        kwargs = build_run_kwargs(
            scenario, _opts(constant_extinction=0.0, no_visibility=True)
        )
    assert not _mentions_extinction(caplog)
    assert isinstance(kwargs["smoke_speed_model"], SmokeSpeedModel)
    assert kwargs["vis_model"] is None
    assert kwargs["fed_model"] is None
    assert kwargs["heat_fed_model"] is not None
    assert kwargs["tenability_config"].enable_heat_incapacitation is True


def test_heat_only_case_builds_without_workaround(scenario, caplog):
    """No flags: smoke speed is off, heat FED is on, and each fallback warns once."""
    with caplog.at_level(logging.WARNING):
        kwargs = build_run_kwargs(scenario, _opts())
    assert kwargs["smoke_speed_model"] is None
    assert isinstance(kwargs["vis_model"], VisibilityModel)
    assert kwargs["fed_model"] is None
    assert kwargs["heat_fed_model"] is not None
    assert kwargs["tenability_config"].enable_heat_incapacitation is True
    assert _count_warnings(caplog, _SMOKE_WARNING) == 1
    assert _count_warnings(caplog, _VIS_WARNING) == 1


def test_missing_soot_falls_back_to_clear_air_visibility(scenario, caplog):
    """Visibility falls back to clear air: sign facing still gates sight.

    An explicit constant extinction isolates the visibility builder, so only
    its warning may appear. Expected answers come from the fixture's sign
    alone: ``cp_SW_1`` stands at (5, 5) with alpha = 0 (readable from the
    north, see VisibilityModel). A viewer 5 m north at (5, 10) is in front of
    it; a viewer 4 m south at (5, 1) is behind it. Both are in the open 30 m
    room and within the 30 m sign distance cap, and clear air hides nothing,
    so facing alone decides.
    """
    with caplog.at_level(logging.WARNING):
        kwargs = build_run_kwargs(scenario, _opts(constant_extinction=0.0))
    assert isinstance(kwargs["smoke_speed_model"], SmokeSpeedModel)
    assert kwargs["heat_fed_model"] is not None
    assert _count_warnings(caplog, _SMOKE_WARNING) == 0
    assert _count_warnings(caplog, _VIS_WARNING) == 1
    vis = kwargs["vis_model"]
    assert isinstance(vis, VisibilityModel)
    assert vis.node_is_visible(0.0, 5.0, 10.0, "cp_SW_1") is True
    assert vis.node_is_visible(0.0, 5.0, 1.0, "cp_SW_1") is False


def test_inventory_errors_are_raised(scenario, monkeypatch):
    """The fallback is decided by the inventory, not by swallowing its errors."""

    def broken_inventory(_fds_dir):
        raise IndexError("broken inventory")

    monkeypatch.setattr(run_config, "inspect_fds_quantities", broken_inventory)
    # Each builder on its own: the FED builders read the inventory too.
    with pytest.raises(IndexError, match="broken inventory"):
        run_config._build_smoke_model(_opts(), run_config._noop)
    with pytest.raises(IndexError, match="broken inventory"):
        run_config._build_vis_model(scenario, _opts(), run_config._noop)


def test_extinction_reader_errors_are_raised(scenario, monkeypatch):
    """With a soot slice reported, a failing reader surfaces, not a fallback."""

    def broken_reader(*_args, **_kwargs):
        raise IndexError("broken reader")

    monkeypatch.setattr(run_config, "_has_extinction_slice", lambda _fds_dir: True)
    monkeypatch.setattr(run_config.ExtinctionField, "from_fds", broken_reader)
    with pytest.raises(IndexError, match="broken reader"):
        run_config._build_smoke_model(_opts(), run_config._noop)


def test_constant_extinction_overrides_missing_soot(scenario):
    """An explicit --constant-extinction still wins over the missing slice."""
    kwargs = build_run_kwargs(
        scenario, _opts(constant_extinction=0.3, no_visibility=True)
    )
    model = kwargs["smoke_speed_model"]
    assert isinstance(model, SmokeSpeedModel)
    assert model.field.sample_extinction(0.0, 15.0, 15.0) == pytest.approx(0.3)
