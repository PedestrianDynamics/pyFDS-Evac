"""Tests for the shared option-to-kwargs builder used by the CLI and GUI."""

from argparse import Namespace
from types import SimpleNamespace

import pytest

from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.smoke_speed import SmokeSpeedModel

# Defaults mirror run.py's argparse dests for the fields build_run_kwargs reads.
_DEFAULT_OPTS = dict(
    seed=None,
    fds_dir=None,
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
)


def _opts(**overrides) -> Namespace:
    return Namespace(**{**_DEFAULT_OPTS, **overrides})


def _scenario(raw=None):
    return SimpleNamespace(raw=raw if raw is not None else {})


def test_defaults_produce_no_models():
    kwargs = build_run_kwargs(_scenario(), _opts())
    assert kwargs["smoke_speed_model"] is None
    assert kwargs["fed_model"] is None
    assert kwargs["tenability_config"] is None
    assert kwargs["reroute_config"] is None
    assert kwargs["vis_model"] is None
    assert kwargs["collect_route_cost_history"] is False
    assert kwargs["seed"] is None


def test_constant_extinction_builds_smoke_model():
    kwargs = build_run_kwargs(_scenario(), _opts(constant_extinction=0.5))
    assert isinstance(kwargs["smoke_speed_model"], SmokeSpeedModel)
    # No FDS dir means no FED model and therefore no tenability config.
    assert kwargs["fed_model"] is None
    assert kwargs["tenability_config"] is None


def test_rerouting_builds_reroute_config():
    kwargs = build_run_kwargs(_scenario(), _opts(enable_rerouting=True))
    assert kwargs["reroute_config"] is not None
    assert kwargs["reroute_config"].reevaluation_interval_s == 1.0


def test_reroute_uses_scenario_routing_overrides():
    scenario = _scenario({"routing": {"w_fed": 42.0}})
    kwargs = build_run_kwargs(scenario, _opts(enable_rerouting=True))
    assert kwargs["reroute_config"].cost_config.w_fed == 42.0


def test_collect_route_cost_history_from_output_flag():
    kwargs = build_run_kwargs(
        _scenario(), _opts(output_route_cost_history="routes.csv")
    )
    assert kwargs["collect_route_cost_history"] is True


def test_collect_route_cost_history_explicit_flag():
    opts = _opts()
    opts.collect_route_cost_history = True
    kwargs = build_run_kwargs(_scenario(), opts)
    assert kwargs["collect_route_cost_history"] is True


def test_vis_cache_requires_fds_dir():
    with pytest.raises(ValueError, match="--vis-cache requires --fds-dir"):
        build_run_kwargs(_scenario(), _opts(vis_cache="cache.pkl"))


def test_vis_cache_requires_rerouting():
    with pytest.raises(ValueError, match="--vis-cache requires --enable-rerouting"):
        build_run_kwargs(_scenario(), _opts(vis_cache="cache.pkl", fds_dir="fds_data"))


def test_log_callable_receives_status_lines():
    messages = []
    build_run_kwargs(_scenario(), _opts(constant_extinction=0.5), log=messages.append)
    assert any("smoke" in m.lower() for m in messages)
