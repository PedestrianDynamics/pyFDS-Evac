"""``simulationParams.dt`` is the time step of the run (#922).

The key used to be ignored: every run stepped at 0.01 s whatever a deck
said. Now it reaches ``jps.Simulation`` and ``Result.dt``; the trajectory
keeps 10 frames per second (a frame every 0.1 s), so ``dt`` must divide
0.1 s; ``run_scenario`` refuses a step that would hang or never end, and a
force-based model above 0.01 s is warned about.

The deck is the synthetic 10 x 6 m room of ``test_run_outcome``.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sqlite3
from types import SimpleNamespace

import jupedsim as jps
import pytest
from test_run_outcome import ENOUGH_S, SEED, _scenario

from pyfds_evac.config.effective import effective_configuration
from pyfds_evac.config.rules import scenario_issue, spawn_issue
from pyfds_evac.core import route_graph
from pyfds_evac.core import scenario as scenario_module
from pyfds_evac.core.route_graph import RerouteConfig, compute_eval_offset
from pyfds_evac.core.scenario import load_scenario, run_scenario
from pyfds_evac.core.time_step import large_step_warning, output_stride

BAD_FOR_THE_RUN = [0, -0.01, float("nan"), float("inf"), True, "fast"]
NOT_A_DIVISOR = [0.03]
GOOD = [0.01, 0.02, 0.05]


def _scenario_dt(dt, number=2, **extra):
    scenario = _scenario(ENOUGH_S, number=number, **extra)
    if dt is not None:
        scenario.set_model_params(dt=dt)
    return scenario


def _run(scenario, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(scenario, seed=SEED, **kwargs)


def _metadata(result):
    con = sqlite3.connect(result.sqlite_file)
    try:
        return dict(con.execute("SELECT key, value FROM metadata"))
    finally:
        con.close()


def _frame_times(result):
    con = sqlite3.connect(result.sqlite_file)
    try:
        frames = [
            r[0] for r in con.execute("SELECT DISTINCT frame FROM trajectory_data")
        ]
    finally:
        con.close()
    return sorted(frames)


@pytest.fixture
def seen_dt(monkeypatch):
    """The ``dt`` every ``jps.Simulation`` of the test was built with."""
    seen = []
    real = jps.Simulation

    def spy(*args, **kwargs):
        seen.append(kwargs.get("dt", "not passed"))
        return real(*args, **kwargs)

    monkeypatch.setattr(scenario_module.jps, "Simulation", spy)
    return seen


def test_dt_reaches_the_simulation_and_the_result(seen_dt):
    result = _run(_scenario_dt(0.05))
    try:
        assert seen_dt == [0.05]
        assert result.dt == 0.05
        # Exit times are whole steps (JuPedSim's clock is iteration * dt).
        steps = result.evacuation_time / 0.05
        assert abs(steps - round(steps)) < 1e-9
    finally:
        result.cleanup()


def test_a_deck_without_dt_keeps_the_jupedsim_default(seen_dt):
    result = _run(_scenario_dt(None))
    try:
        assert seen_dt == [0.01]
        assert result.dt == 0.01
        assert result.frame_rate == 10.0
        assert float(_metadata(result)["fps"]) == 10.0
    finally:
        result.cleanup()


@pytest.mark.parametrize("dt", [0.01, 0.02, 0.05])
def test_the_trajectory_stays_at_ten_frames_per_second(dt):
    result = _run(_scenario_dt(dt))
    try:
        assert result.dt == dt
        assert result.frame_rate == pytest.approx(10.0)
        assert float(_metadata(result)["fps"]) == pytest.approx(10.0)
        # A written frame every 0.1 s: the stored frame numbers are 0, 1, 2 ...
        frames = _frame_times(result)
        assert frames == list(range(len(frames)))
        assert (len(frames) - 1) / 10.0 == pytest.approx(
            result.evacuation_time, abs=0.1 + dt
        )
    finally:
        result.cleanup()


@pytest.mark.parametrize("dt", BAD_FOR_THE_RUN + NOT_A_DIVISOR)
def test_run_scenario_rejects_a_dt_that_cannot_step(monkeypatch, dt):
    def refuse(*_args, **_kwargs):
        raise AssertionError("jps.Simulation was built")

    monkeypatch.setattr(scenario_module.jps, "Simulation", refuse)
    scenario = _scenario(ENOUGH_S)
    scenario.sim_params["dt"] = dt
    with pytest.raises(ValueError, match=r"simulationParams\.dt"):
        _run(scenario)


@pytest.mark.parametrize("dt", BAD_FOR_THE_RUN + NOT_A_DIVISOR)
def test_the_rules_reject_a_bad_dt_with_one_error(dt):
    raw = _scenario_dt(None).raw
    raw["config"]["simulation_settings"]["simulationParams"]["dt"] = dt
    issue = scenario_issue(raw)
    assert issue is not None
    assert "simulationParams.dt" in issue.message


@pytest.mark.parametrize("dt", GOOD)
def test_the_rules_pass_a_dt_that_divides_a_tenth_of_a_second(dt):
    raw = _scenario_dt(dt).raw
    assert scenario_issue(raw) is None


def test_the_rules_pass_a_deck_without_dt():
    assert scenario_issue(_scenario_dt(None).raw) is None


@pytest.mark.parametrize(
    ("dt", "stride"),
    [(0.1, 1), (0.05, 2), (0.025, 4), (0.02, 5), (0.01, 10), (0.005, 20)],
)
def test_the_output_stride_keeps_a_frame_every_tenth_of_a_second(dt, stride):
    assert output_stride(dt) == stride
    assert stride * dt == pytest.approx(0.1)


@pytest.mark.parametrize(
    "model", ["SocialForceModel", "GeneralizedCentrifugalForceModel"]
)
def test_force_models_above_the_default_step_are_warned_about(model):
    assert "0.02" in large_step_warning(model, 0.02)
    assert large_step_warning(model, 0.01) is None


@pytest.mark.parametrize(
    "model", ["CollisionFreeSpeedModel", "CollisionFreeSpeedModelV2", "WarpDriverModel"]
)
def test_speed_based_models_are_not_warned_about(model):
    assert large_step_warning(model, 0.05) is None


def test_a_run_of_the_social_force_model_at_a_larger_step_warns(caplog):
    scenario = _scenario_dt(0.02)
    scenario.set_model_type("SocialForceModel")
    with caplog.at_level(logging.WARNING):
        result = _run(scenario)
    result.cleanup()
    assert any(
        "SocialForceModel" in r.getMessage() and "0.02" in r.getMessage()
        for r in caplog.records
    )


def test_a_run_at_the_default_step_does_not_warn(caplog):
    scenario = _scenario_dt(0.01)
    scenario.set_model_type("SocialForceModel")
    with caplog.at_level(logging.WARNING):
        result = _run(scenario)
    result.cleanup()
    assert not [r for r in caplog.records if "simulationParams.dt" in r.getMessage()]


@pytest.mark.parametrize("dt", [0.01, 0.05])
def test_the_reevaluation_stagger_is_whole_steps_of_the_dt(dt):
    offsets = {compute_eval_offset(i, 1.0, dt) for i in range(1, 200)}
    for offset in offsets:
        steps = offset / dt
        assert abs(steps - round(steps)) < 1e-9
    assert max(offsets) == pytest.approx(1.0 - dt)


def test_a_run_passes_its_dt_to_the_reevaluation_stagger(monkeypatch):
    seen = []
    real = route_graph.compute_eval_offset

    def spy(agent_id, interval_s, dt_s=0.01):
        seen.append(dt_s)
        return real(agent_id, interval_s, dt_s)

    monkeypatch.setattr(scenario_module, "compute_eval_offset", spy)
    result = _run(
        _scenario_dt(0.05, number=4),
        reroute_config=RerouteConfig(reevaluation_interval_s=1.0),
    )
    result.cleanup()
    assert seen
    assert set(seen) == {0.05}


def _flow_deck(dt):
    """10 agents in a 0.3 s window: 0.1 s of steps at 0.01, 0.5 s at 0.05."""
    scenario = _scenario_dt(dt)
    scenario.set_flow_schedule(
        "jps-distributions_0",
        [{"flow_start_time": 0, "flow_end_time": 0.3, "number": 10}],
    )
    return scenario


def test_the_flow_window_check_of_export_only_uses_the_dt_of_the_deck():
    assert spawn_issue(_flow_deck(0.01)) is None
    issue = spawn_issue(_flow_deck(0.05))
    assert issue is not None
    assert "0.05 s step" in issue.message
    assert "at least 0.5 s" in issue.message


def test_the_run_refuses_the_window_that_export_only_refuses():
    scenario = _flow_deck(0.05)
    with pytest.raises(ValueError, match="0.05 s step"):
        _run(scenario)


def test_the_manifest_records_the_dt_of_the_run():
    result = _run(_scenario_dt(0.05))
    try:
        manifest = json.loads(open(result.manifest_file, encoding="utf-8").read())
        assert manifest["dt"] == 0.05
    finally:
        result.cleanup()


def test_the_effective_inputs_show_the_dt_and_where_it_comes_from():
    opts = SimpleNamespace(scenario="deck.json")
    given = effective_configuration(opts, _scenario_dt(0.02), inspect_fds=False).inputs
    assert (given["dt_s"], given["dt_origin"]) == (0.02, "scenario")
    default = effective_configuration(
        opts, _scenario_dt(None), inspect_fds=False
    ).inputs
    assert (default["dt_s"], default["dt_origin"]) == (0.01, "default")


def test_the_effective_configuration_reports_a_bad_dt_as_an_error():
    opts = SimpleNamespace(scenario="deck.json")
    cfg = effective_configuration(opts, _scenario_dt(0.03), inspect_fds=False)
    assert [e.message for e in cfg.errors if "simulationParams.dt" in e.message]
    shown = effective_configuration(
        opts, _scenario_dt(0.02), inspect_fds=False
    ).format_text()
    assert "dt                      0.02 s (scenario)" in shown


def test_the_committed_decks_name_a_valid_dt():
    for path in (
        "assets/iso_table21_coupled/config.json",
        "assets/station_nist/config.json",
    ):
        scenario = load_scenario(path)
        assert scenario_issue(scenario.raw) is None
        assert scenario.sim_params["dt"] == 0.01


def _main(monkeypatch, scenario, *args):
    from pyfds_evac import cli

    monkeypatch.setattr(cli, "load_scenario", lambda _path: scenario)
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", "unused", *args])
    with contextlib.redirect_stdout(io.StringIO()):
        return cli.main()


@pytest.mark.parametrize("args", [(), ("--print-summary", "--export-only")])
def test_the_command_refuses_a_dt_that_does_not_divide_the_output_interval(
    monkeypatch, args
):
    with pytest.raises(SystemExit) as stop:
        _main(monkeypatch, _scenario_dt(0.03), *args)
    assert "simulationParams.dt" in str(stop.value.code)


def test_the_command_passes_a_dt_that_divides_it(monkeypatch):
    scenario = _scenario_dt(0.05)
    assert _main(monkeypatch, scenario, "--print-summary", "--export-only") == 0


@pytest.mark.parametrize("agent", [1, 7, 20, 99, 150])
@pytest.mark.parametrize("interval", [1.0, 2.0, 10.0])
def test_the_reevaluation_stagger_does_not_depend_on_the_step(agent, interval):
    fine = compute_eval_offset(agent, interval, 0.01)
    coarse = compute_eval_offset(agent, interval, 0.05)
    assert abs(fine - coarse) < 0.05
    assert coarse < interval
    # On the default step the offset is the 0.01 s grid value, unchanged.
    assert fine == (agent % round(interval / 0.01)) * 0.01


def _exit_opened_times(dt):
    """Times of the ``exit_opened`` switches of the 40-agent scheduled room."""
    from shapely.geometry import box
    from test_scheduled_exits import REROUTE_OFTEN, T_OPEN_S, _coords, _scenario

    scenario = _scenario({"east": {"open_from_s": T_OPEN_S}})
    near_east = box(22.0, 0.3, 29.7, 9.7)
    scenario.raw["distributions"]["room"]["coordinates"] = _coords(near_east)
    scenario.set_model_params(dt=dt)
    result = _run(scenario, reroute_config=REROUTE_OFTEN)
    try:
        return sorted(
            r["time_s"]
            for r in result.route_history or []
            if r.get("reason") == "exit_opened"
        )
    finally:
        result.cleanup()


def test_exit_opened_switches_fall_at_the_same_times_at_both_steps():
    fine = _exit_opened_times(0.01)
    coarse = _exit_opened_times(0.05)
    # The agents that switch differ with the step (positions differ), the
    # times at which switches happen do not.
    assert fine and coarse
    assert len(set(fine)) == len(set(coarse))
    assert (
        max(abs(a - b) for a, b in zip(sorted(set(fine)), sorted(set(coarse)))) < 0.05
    )
