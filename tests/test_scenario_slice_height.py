"""``simulationParams.smoke_slice_height`` sets the slice height of a run.

The key is how an imported FDS+Evac deck carries z_floor +
HUMAN_SMOKE_HEIGHT (maintainer decision Q6); ``--smoke-slice-height`` given
on the command line overrides it, and without the key nothing changes.
"""

from __future__ import annotations

import argparse

import pytest

from pyfds_evac import cli
from pyfds_evac.core.run_config import scenario_smoke_slice_height


class _Scenario:
    def __init__(self, params):
        self.sim_params = params


def _args(argv):
    namespace = argparse.Namespace(smoke_slice_height=cli._NOT_GIVEN)
    return cli._build_parser().parse_args(
        ["--scenario", "x", *argv], namespace=namespace
    )


def test_scenario_slice_height_applies_when_the_flag_is_absent():
    args = _args([])
    cli._apply_scenario_settings(_Scenario({"smoke_slice_height": 5.7}), args)
    assert args.smoke_slice_height == 5.7


def test_cli_slice_height_overrides_the_scenario():
    args = _args(["--smoke-slice-height", "1.6"])
    cli._apply_scenario_settings(_Scenario({"smoke_slice_height": 5.7}), args)
    assert args.smoke_slice_height == 1.6


def test_without_the_key_the_default_is_unchanged():
    args = _args([])
    cli._apply_scenario_settings(_Scenario({}), args)
    plain = cli._build_parser().parse_args(["--scenario", "x"])
    assert args.smoke_slice_height == plain.smoke_slice_height


@pytest.mark.parametrize("bad", ["high", float("nan"), True])
def test_bad_scenario_slice_height_is_an_error(bad):
    with pytest.raises(ValueError, match="smoke_slice_height"):
        scenario_smoke_slice_height(_Scenario({"smoke_slice_height": bad}))


def test_run_warns_when_it_samples_away_from_the_scenario_height(caplog):
    from pyfds_evac.core import run_config

    opts = argparse.Namespace(smoke_slice_height=1.6)
    with caplog.at_level("WARNING", logger=run_config.__name__):
        run_config._warn_slice_height_differs(
            _Scenario({"smoke_slice_height": 5.7}), opts
        )
        run_config._warn_slice_height_differs(_Scenario({}), opts)
    [record] = caplog.records
    assert "5.7 m" in record.getMessage() and "1.6 m" in record.getMessage()
