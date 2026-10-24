"""The slice-height warning: tolerance, once per quantity and run (#165)."""

import logging
from types import SimpleNamespace

from pyfds_evac import cli
from pyfds_evac.config import messages
from pyfds_evac.config.effective import effective_configuration
from pyfds_evac.core import fds_sampling
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario

HEAT_SCENARIO = "assets/fed_incap_heat_150c"
HEAT_FDS = "assets/heat_only_no_soot/fds"
HEAT_ARGV = [
    "--scenario",
    HEAT_SCENARIO,
    "--fds-dir",
    HEAT_FDS,
    "--enable-heat-fed",
    "--allow-fds-horizon-hold",
]


def _at(z, name):
    return SimpleNamespace(extent=SimpleNamespace(z_start=z, z_end=z), name=name)


def _select(z_near, requested, quantity="q", fds_dir="d"):
    return fds_sampling.select_horizontal_slice(
        [_at(z_near, "a"), _at(9.0, "b")], requested, quantity, fds_dir
    )


def test_the_tolerance_is_0_2_m(caplog):
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        _select(2.0, 1.8)
    assert caplog.text == ""
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        _select(2.01, 1.8)
    assert len(caplog.records) == 1
    assert "0.21 m away" in caplog.text


def test_a_quantity_warns_once_inside_a_run(caplog):
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        with fds_sampling.height_warnings_once():
            _select(2.0, 1.6)
            _select(2.0, 1.6)
    assert len(caplog.records) == 1


def test_outside_a_run_every_call_warns(caplog):
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        _select(2.0, 1.6)
        _select(2.0, 1.6)
    assert len(caplog.records) == 2


def test_another_quantity_still_warns(caplog):
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        with fds_sampling.height_warnings_once():
            _select(2.0, 1.6, "q")
            _select(2.0, 1.6, "r")
    assert len(caplog.records) == 2


def test_the_memory_ends_with_the_context(caplog):
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        with fds_sampling.height_warnings_once():
            with fds_sampling.height_warnings_once():
                _select(2.0, 1.6)
            _select(2.0, 1.6)
        _select(2.0, 1.6)
    assert len(caplog.records) == 2


def test_each_run_warns_again(caplog):
    opts = cli._build_parser().parse_args(HEAT_ARGV)
    scenario = load_scenario(opts.scenario)
    for _ in range(2):
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            build_run_kwargs(scenario, opts)
        hits = [m for m in caplog.messages if m.startswith("Requested a 'TEMPERATURE'")]
        assert len(hits) == 1


def test_the_text_has_one_source(caplog):
    with caplog.at_level(logging.WARNING, logger=fds_sampling.__name__):
        _select(2.0, 1.6)
    assert caplog.messages == [messages.slice_height_mismatch("q", 1.6, "d", 2.0, 2)]


def test_the_prediction_lists_each_gas_and_extinction_warning_once(caplog):
    """--show-config predicts the warnings the run logs, once per quantity."""
    opts = cli._build_parser().parse_args(
        [
            "--scenario",
            "assets/iso_table22_coupled/config_a.json",
            "--fds-dir",
            "assets/iso_table22_coupled/fds/a",
            "--smoke-slice-height",
            "2.5",
        ]
    )
    scenario = load_scenario(opts.scenario)
    with caplog.at_level(logging.WARNING):
        build_run_kwargs(scenario, opts)
    logged = [m for m in caplog.messages if m.startswith("Requested a '")]
    predicted = [
        w
        for w in effective_configuration(opts, scenario).warnings
        if w.startswith("Requested a '")
    ]
    assert len(logged) == 4
    assert predicted == logged
