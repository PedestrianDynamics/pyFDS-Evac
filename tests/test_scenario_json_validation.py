"""Unknown keys and values in a scenario JSON are reported at load (#1033)."""

from __future__ import annotations

import json
import logging

import pytest

from pyfds_evac.config.rules import scenario_issue
from pyfds_evac.core.scenario import load_scenario

SQUARE = [[0, 0], [4, 0], [4, 4], [0, 4]]


def _load(tmp_path, parameters=None, routing=None):
    raw = {
        "walkable_area_wkt": "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))",
        "exits": {"e1": {"coordinates": [[9, 4], [10, 4], [10, 5], [9, 5]]}},
        "distributions": {"d1": {"coordinates": SQUARE, "parameters": parameters}},
    }
    if routing is not None:
        raw["routing"] = routing
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_scenario(str(path))


def _unknown_warnings(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "unknown" in r.getMessage()
    ]


def test_misspelled_parameter_key_warns_once_and_names_it(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load(tmp_path, {"numbr": 5, "number": 3})
    unknown = _unknown_warnings(caplog)
    assert len(unknown) == 1
    assert "'d1'" in unknown[0] and "'numbr'" in unknown[0]


@pytest.mark.parametrize(
    "parameters",
    [
        {"number": 3, "population": "adults", "fahy_row": 1, "fahy_class": "a"},
        {"desired_speed": 1.0, "desired_speed_std": 0.1, "premovement_offset_s": 2},
    ],
)
def test_known_and_label_keys_do_not_warn(tmp_path, caplog, parameters):
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load(tmp_path, parameters)
    assert _unknown_warnings(caplog) == []


@pytest.mark.parametrize(
    ("key", "value", "allowed"),
    [
        ("v0_distribution", "normal", "constant, gaussian"),
        ("desired_speed_distribution", "uniform", "constant, gaussian"),
        ("radius_distribution", "normal", "constant, gaussian"),
        (
            "distribution_mode",
            "by_count",
            "by_number, by_percentage, fill_area, until_full",
        ),
    ],
)
def test_unknown_enum_value_stops_the_load(tmp_path, key, value, allowed):
    with pytest.raises(ValueError) as excinfo:
        _load(tmp_path, {key: value})
    message = str(excinfo.value)
    assert "'d1'" in message and key in message and allowed in message


@pytest.mark.parametrize(
    "key",
    [
        "v0_distribution",
        "desired_speed_distribution",
        "radius_distribution",
        "distribution_mode",
    ],
)
def test_null_enum_value_reads_as_unset(tmp_path, key):
    scenario = _load(tmp_path, {key: None, "number": 3})
    assert scenario.raw["distributions"]["d1"]["parameters"][key] is None


@pytest.mark.parametrize("key", ["v0_std", "desired_speed_std", "radius_std"])
@pytest.mark.parametrize("value", [-0.1, "0.2", True, float("inf")])
def test_bad_std_stops_the_load(tmp_path, key, value):
    with pytest.raises(ValueError, match=f"'d1'.*{key}"):
        _load(tmp_path, {key: value})


@pytest.mark.parametrize("value", [0, 0.0, None, 0.3])
def test_zero_null_and_positive_std_load(tmp_path, value):
    _load(tmp_path, {"v0_distribution": "gaussian", "v0_std": value})


def test_scenario_issue_reports_a_bad_value(tmp_path):
    scenario = _load(tmp_path, {"v0_std": 0.1})
    scenario.raw["distributions"]["d1"]["parameters"]["v0_distribution"] = "normal"
    issue = scenario_issue(scenario.raw)
    assert issue is not None and "'d1'" in issue.message


@pytest.mark.parametrize("key", ["v0_std", "radius_std"])
def test_huge_int_std_is_a_named_error_not_an_overflow(tmp_path, key):
    with pytest.raises(ValueError, match=f"'d1'.*{key}"):
        _load(tmp_path, {key: -(10**400)})
    scenario = _load(tmp_path, {"number": 3})
    scenario.raw["distributions"]["d1"]["parameters"][key] = -(10**400)
    issue = scenario_issue(scenario.raw)
    assert issue is not None and "'d1'" in issue.message


def test_an_int_std_too_large_for_a_float_stops_the_load(tmp_path):
    # The run converts the std to a float; 10**400 would overflow there.
    with pytest.raises(ValueError, match="'d1'.*v0_std"):
        _load(tmp_path, {"v0_distribution": "gaussian", "v0_std": 10**400})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("radius_distribution", "normal"),
        ("distribution_mode", "by_count"),
        ("radius_std", -0.1),
    ],
)
def test_run_scenario_rejects_a_value_set_through_the_api(tmp_path, key, value):
    from pyfds_evac.core.scenario import run_scenario

    scenario = _load(tmp_path, {"number": 3})
    scenario.set_agent_params("d1", **{key: value})
    with pytest.raises(ValueError, match=f"'d1'.*{key}"):
        run_scenario(scenario)


def test_unknown_routing_key_warns_and_names_it(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load(tmp_path, {"number": 3}, routing={"w_smok": 2.0, "w_smoke": 1.0})
    unknown = _unknown_warnings(caplog)
    assert len(unknown) == 1 and "routing" in unknown[0] and "'w_smok'" in unknown[0]


def test_known_routing_keys_do_not_warn(tmp_path, caplog):
    routing = {"cost_model": "gate", "w_fed": 1.0, "fed_rate_memo": True}
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load(tmp_path, {"number": 3}, routing=routing)
    assert _unknown_warnings(caplog) == []


def test_removed_routing_key_is_still_refused_without_the_unknown_warning(
    tmp_path, caplog
):
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        scenario = _load(tmp_path, {"number": 3}, routing={"tau_return_margin": 1.0})
    assert _unknown_warnings(caplog) == []
    issue = scenario_issue(scenario.raw)
    assert issue is not None and "tau_return_margin was removed" in issue.message


def _load_with(tmp_path, extra_top=None, sim_params=None):
    raw = {
        "walkable_area_wkt": "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))",
        "exits": {"e1": {"coordinates": [[9, 4], [10, 4], [10, 5], [9, 5]]}},
        "distributions": {"d1": {"coordinates": SQUARE, "parameters": {"number": 3}}},
        "config": {
            "simulation_settings": {"simulationParams": sim_params or {"dt": 0.05}}
        },
        **(extra_top or {}),
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_scenario(str(path))


def test_misspelled_top_level_key_warns_and_names_it(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load_with(tmp_path, extra_top={"routting": {"w_fed": 1.0}})
    unknown = _unknown_warnings(caplog)
    assert len(unknown) == 1 and "'routting'" in unknown[0]


def test_misspelled_simulation_param_warns_and_names_it(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load_with(tmp_path, sim_params={"dt": 0.05, "max_simulation_tim": 60})
    unknown = _unknown_warnings(caplog)
    assert len(unknown) == 1
    assert "simulationParams" in unknown[0] and "'max_simulation_tim'" in unknown[0]


def test_a_deck_of_known_keys_does_not_warn(tmp_path, caplog):
    params = {"dt": 0.05, "max_simulation_time": 60, "model_type": "WarpDriverModel"}
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load_with(tmp_path, extra_top={"zones": {}, "routing": {}}, sim_params=params)
    assert _unknown_warnings(caplog) == []


def test_web_app_keys_do_not_warn(tmp_path, caplog):
    top = {"project_version": "1", "obstacles": {}, "background_image": None}
    with caplog.at_level(logging.WARNING, logger="pyfds_evac"):
        _load_with(tmp_path, extra_top=top, sim_params={"T": 1.0, "s0": 0.4})
    assert _unknown_warnings(caplog) == []
