"""``simulationParams.smoke_slice_height`` sets the slice height of a run.

The key is how an imported FDS+Evac deck carries z_floor +
HUMAN_SMOKE_HEIGHT (maintainer decision Q6); ``--smoke-slice-height`` given
on the command line overrides it, and without the key nothing changes.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

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


def _scenario_dir(tmp_path, height):
    source = Path(__file__).resolve().parents[1] / "assets/familiarity_test_no_journey"
    raw = json.loads((source / "config.json").read_text(encoding="utf-8"))
    raw["config"]["simulation_settings"]["simulationParams"]["smoke_slice_height"] = (
        height
    )
    (tmp_path / "config.json").write_text(json.dumps(raw), encoding="utf-8")
    shutil.copy(source / "geometry.wkt", tmp_path / "geometry.wkt")
    return str(tmp_path)


def _main_height(monkeypatch, argv) -> float:
    """Run ``cli.main`` up to --show-config and return the height it used."""
    seen = {}

    def show(scenario, args):
        seen["height"] = args.smoke_slice_height
        return 0

    monkeypatch.setattr(cli, "_show_config", show)
    monkeypatch.setattr("sys.argv", ["pyfds-evac", *argv, "--show-config"])
    assert cli.main() == 0
    return seen["height"]


def test_main_applies_the_scenario_height(tmp_path, monkeypatch):
    folder = _scenario_dir(tmp_path, 5.7)
    assert _main_height(monkeypatch, ["--scenario", folder]) == 5.7
    flagged = ["--scenario", folder, "--smoke-slice-height", "1.6"]
    assert _main_height(monkeypatch, flagged) == 1.6


def test_main_reports_a_bad_scenario_height_without_a_traceback(tmp_path, monkeypatch):
    folder = _scenario_dir(tmp_path, "high")
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", folder])
    with pytest.raises(SystemExit, match="pyfds-evac: error: .*smoke_slice_height"):
        cli.main()
