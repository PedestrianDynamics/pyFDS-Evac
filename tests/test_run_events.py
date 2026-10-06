"""Runner and configuration additions for the terminal UI (#485).

- R1: whether every option applies, also at its default
  (``config.rules.applies``), and the common/advanced tier (R2).
- R4: the plan-view events (``PlanEvent``, ``FrameEvent``) and the smoke
  grid, which only read the run.
- R10: the complete ``ResultEvent`` of ``core.run_stream.stream_run``.

FDS fixture: ``assets/iso_table21_coupled/fds`` (soot extinction slices at
z = 1.5 m and 2.0 m; no gas, no temperature).
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import pickle
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from pyfds_evac import cli
from pyfds_evac.config import PARAMETERS, effective_configuration, events
from pyfds_evac.config.parameters import (
    GUI_HIDDEN,
    GUI_SECTIONS,
    TIER_ADVANCED,
    TIER_COMMON,
)
from pyfds_evac.config.rules import (
    FdsFacts,
    applicability,
    applies,
    inactive_settings,
    is_set,
    predict_mechanisms,
)

REPO = Path(__file__).resolve().parents[1]
ISO21 = REPO / "assets" / "iso_table21_coupled"
ISO21_CONFIG = str(ISO21 / "config.json")
ISO21_FDS = str(ISO21 / "fds")
T_JUNCTION = str(REPO / "assets" / "t_junction" / "config.json")
NO_JOURNEY = str(REPO / "assets" / "familiarity_test_no_journey")
WORLD77 = str(REPO / "assets" / "world_77")

_SIGNS = {"exits": {"e": {"sign": {"x": 0.0, "y": 0.0}}}}
_DISCOVERY = {"distributions": {"a": {"parameters": {"familiarity": 0.0}}}}
_ALL = FdsFacts(frozenset({"extinction", "co", "co2", "o2", "temperature"}))
_SMOKE_ONLY = FdsFacts(frozenset({"extinction"}))


def _parse(*argv: str) -> argparse.Namespace:
    return cli._build_parser().parse_args(["--scenario", "x", *argv])


def _load(path: str):
    from pyfds_evac.core.scenario import load_scenario

    return load_scenario(path)


# --- R1: applies, at any value ----------------------------------------------


def test_heat_options_at_default_say_why_they_are_off():
    """Spec A6: greyed out with "needs --enable-heat-fed", the switch active."""
    raw = {**_DISCOVERY, **_SIGNS}
    with_fds = _parse("--fds-dir", "case")
    found = applicability(with_fds, raw, _ALL)
    assert found["enable_heat_fed"].active
    assert found["heat_emissivity"] == (False, "D13", "without --enable-heat-fed")
    assert found["heat_fed_threshold"].reason == "without --enable-heat-fed"
    no_fds = applicability(_parse(), raw)
    assert no_fds["enable_heat_fed"] == (False, "D14", "without --fds-dir")
    assert no_fds["heat_clothing"] == (False, "D14", "without --fds-dir")
    no_temperature = applies("enable_heat_fed", with_fds, raw, _SMOKE_ONLY)
    assert no_temperature.rule == "D12"


def test_heat_options_follow_the_heat_law_once_on():
    raw = {**_DISCOVERY, **_SIGNS}
    found = applicability(_parse("--fds-dir", "c", "--enable-heat-fed"), raw, _ALL)
    assert found["heat_clothing"].active and found["heat_fed_method"].active
    assert found["heat_emissivity"].rule == "D16"
    assert found["heat_u_factor"].rule == "D18"
    assert found["heat_layer_height"].rule == "D19"


@pytest.mark.parametrize(
    ("argv", "raw", "dest", "expected"),
    [
        ([], _SIGNS, "clear_air_visibility", (True, None, None)),
        (
            ["--fds-dir", "c"],
            _SIGNS,
            "clear_air_visibility",
            (False, "D26", "with --fds-dir (they conflict)"),
        ),
        (
            [],
            {},
            "clear_air_visibility",
            (False, "D27", "because the scenario has no signs"),
        ),
        (
            ["--no-visibility"],
            _SIGNS,
            "vis_cache",
            (False, "D27", "with --no-visibility"),
        ),
        (
            ["--no-enable-rerouting"],
            _SIGNS,
            "vis_cache",
            (False, "D25", "with --no-enable-rerouting (they conflict)"),
        ),
        (["--smoke-blind"], _SIGNS, "enable_rerouting", (False, "D24", None)),
        ([], _SIGNS, "seed", (True, None, None)),
        ([], _SIGNS, "output_fed_history", (True, None, None)),
    ],
)
def test_switches_at_default_report_what_switching_them_on_does(
    argv, raw, dest, expected
):
    found = applies(dest, _parse(*argv), raw, _ALL)
    assert found.active == expected[0]
    assert found.rule == expected[1]
    if expected[2] is not None:
        assert found.reason == expected[2]


_CONTEXTS = [
    ([], None),
    (["--fds-dir", "c"], _ALL),
    (["--fds-dir", "c"], _SMOKE_ONLY),
    (["--fds-dir", "c", "--enable-heat-fed"], _ALL),
    (["--fds-dir", "c", "--smoke-blind"], _ALL),
    (["--fds-dir", "c", "--disable-tenability"], _ALL),
    (["--constant-extinction", "0.5"], None),
    (["--no-enable-rerouting"], None),
    (["--no-visibility"], None),
]
_SETTINGS = [
    ["--smoke-slice-height", "2.0"],
    ["--smoke-update-interval", "2"],
    ["--allow-fds-horizon-hold", "--require-fds-coverage"],
    ["--enable-fic-speed", "--fic-alpha", "0.5", "--fic-min-factor", "0.2"],
    ["--incapacitation-mode", "probabilistic", "--susceptibility-sigma", "0.5"],
    ["--o2-threshold-percent", "19.5", "--fed-threshold", "0.3"],
    ["--enable-heat-fed", "--heat-emissivity", "0.9", "--heat-u-factor", "0.5"],
    ["--heat-clothing", "unclothed", "--heat-endpoint", "fatal"],
    ["--heat-view-factor", "1", "--heat-fed-threshold", "0.5"],
    [
        "--heat-incapacitation-mode",
        "probabilistic",
        "--heat-susceptibility-sigma",
        "0.5",
    ],
    ["--reroute-interval", "5", "--vis-cell-size", "0.5"],
    ["--max-sign-distance", "10", "--disable-tenability"],
    ["--clear-air-visibility"],
    ["--vis-cache", "v.npz"],
    # Invalid values: an error, never inactive (#509 I1).
    ["--enable-heat-fed", "--heat-emissivity", "2"],
    ["--clear-air-visibility", "--vis-cell-size", "0"],
    ["--max-sign-distance", "-1"],
    ["--enable-heat-fed", "--heat-regime", "layer"],
]


@pytest.mark.parametrize("context", _CONTEXTS)
@pytest.mark.parametrize("raw", [{}, {**_DISCOVERY, **_SIGNS}])
def test_applies_agrees_with_the_effective_configuration(context, raw):
    """Greying out and the Review's "no effect" list come from one rule."""
    argv, facts = context
    fds = facts if facts is not None else _ALL
    for setting in _SETTINGS:
        opts = _parse(*argv, *setting)
        cfg = effective_configuration(opts, raw, fds=fds, inspect_fds=False)
        warned = {i.option: i for i in cfg.inactive}
        for param in PARAMETERS:
            if not param.run_option or not is_set(opts, param.dest):
                continue
            found = applies(param.dest, opts, raw, fds)
            listed = warned.get(param.dest)
            assert found.active == (listed is None), (argv, setting, param.dest)
            if listed is not None:
                assert (found.rule, found.reason) == (listed.rule, listed.reason)


def test_an_invalid_value_stays_editable():
    """The field holding an error is never greyed out."""
    opts = _parse("--fds-dir", "c", "--enable-heat-fed", "--heat-emissivity", "2")
    cfg = effective_configuration(opts, _SIGNS, fds=_ALL, inspect_fds=False)
    assert [e.option for e in cfg.errors] == ["heat_emissivity"]
    assert applies("heat_emissivity", opts, _SIGNS, _ALL).active


def test_no_new_warning_for_the_default_only_rule():
    """D24 at the default is for greying out; the run logs nothing new."""
    opts = _parse("--smoke-blind", "--no-enable-rerouting")
    mechanisms = predict_mechanisms(opts, {}, _ALL)
    assert all(
        i.option != "enable_rerouting" for i in inactive_settings(opts, mechanisms)
    )


def test_applicability_covers_every_run_option():
    found = applicability(_parse(), {})
    assert list(found) == [p.dest for p in PARAMETERS if p.run_option]
    with pytest.raises(KeyError, match="unknown run option"):
        applies("no_such_option", _parse(), {})


# --- R2: tier ---------------------------------------------------------------


def test_common_tier_is_the_gui_sections():
    sections = {dest for _title, dests in GUI_SECTIONS for dest in dests}
    common = {p.dest for p in PARAMETERS if p.tier == TIER_COMMON}
    assert common == sections
    advanced = {p.dest for p in PARAMETERS if p.tier == TIER_ADVANCED}
    assert advanced == {p.dest for p in PARAMETERS} - sections
    # The GUI's "Other" section of the R2 proposal, plus the hidden flags.
    other = {
        "debug",
        "heat_endpoint",
        "heat_fed_method",
        "heat_emissivity",
        "heat_convective_coefficient",
        "heat_skin_temperature",
        "heat_radiant_source",
        "heat_u_factor",
        "heat_regime",
        "heat_layer_height",
        "heat_view_factor",
        "heat_layer_emissivity",
        "vis_cell_size",
        "max_sign_distance",
        "clear_air_visibility",
        "no_visibility",
    }
    assert advanced - (GUI_HIDDEN & advanced) == other


# --- events -----------------------------------------------------------------


def _frame(**extra) -> events.FrameEvent:
    import numpy as np

    values = {
        "sim_time": 1.0,
        "wall_time": 0.5,
        "ids": np.array([3, 9], dtype="<i4").tobytes(),
        "x": np.array([1.5, 2.5], dtype="<f4").tobytes(),
        "y": np.array([0.25, -1.0], dtype="<f4").tobytes(),
        "states": bytes([events.AGENT_WALKING, events.AGENT_INCAPACITATED]),
        "evacuated": 4,
        "exit_counts": {"a": 3},
        "unattributed": 1,
        "incapacitated": 1,
        "not_spawned": 0,
    }
    return events.FrameEvent(**{**values, **extra})


def test_plan_view_events_pickle_and_decode():
    import numpy as np

    grid = events.SmokeGrid(
        0.0, 0.0, 0.5, 2, 1, np.array([0.1, np.nan], "<f2").tobytes(), 10.0, 1.5
    )
    frame = _frame(smoke=grid)
    assert pickle.loads(pickle.dumps(frame)) == frame
    assert frame.agents() == [(3, 1.5, 0.25, 0), (9, 2.5, -1.0, 1)]
    k = grid.k_values()
    assert k[0] == pytest.approx(0.1, abs=1e-3) and k[1] != k[1]
    result = events.ResultEvent(events.STATUS_SUCCESS, 0, evacuated=1, seed=7)
    assert pickle.loads(pickle.dumps(result)) == result


def test_events_module_stays_light():
    probe = (
        "import sys, pyfds_evac.config.events\n"
        "print([m for m in ('numpy', 'shapely', 'jupedsim', 'fdsreader')"
        " if m in sys.modules])"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


# --- smoke grid -------------------------------------------------------------


def _sampler_state(sampler):
    return (
        sampler._last_subslice,
        sampler._cached_time_s,
        sampler._cached_t_index,
        sampler._warned_horizon,
    )


def test_smoke_grid_reads_the_slice_without_touching_the_sampler():
    import numpy as np

    from pyfds_evac.core.fds_sampling import load_slice_sampler

    sampler = load_slice_sampler(
        ISO21_FDS, "SOOT EXTINCTION COEFFICIENT", slice_height_m=1.6
    )
    sampler.sample(30.0, 10.0, 0.0)
    before = _sampler_state(sampler)
    xs = np.array([-45.0, -10.0, 0.0, 10.0, 45.0, 60.0])
    ys = np.array([0.0])
    grid = sampler.grid(xs, ys)
    index = grid.time_index(60.0)
    values = grid.values(index)
    assert _sampler_state(sampler) == before
    # Same nearest values as the sampler; NaN outside the slice (x = 60).
    fresh = load_slice_sampler(
        ISO21_FDS, "SOOT EXTINCTION COEFFICIENT", slice_height_m=1.6
    )
    expected = [fresh.sample(60.0, x, 0.0) for x in xs[:-1]]
    assert values[0, :-1].tolist() == pytest.approx(expected)
    assert np.isnan(values[0, -1])
    half = fresh.output_interval_s / 2
    assert abs(grid.frame_time_s(index) - 60.0) <= half + 1e-6
    assert sampler.z_m == pytest.approx(1.5)


# --- plan event -------------------------------------------------------------


def test_plan_event_of_the_t_junction():
    from pyfds_evac.core.plan_view import plan_event

    plan = plan_event(_load(T_JUNCTION))
    assert plan.extent == (0.0, 0.0, 30.0, 13.0)
    assert plan.exit_openings == {
        "exit_A_left": ((0.0, 13.0), (0.0, 10.0)),
        "exit_B_right": ((30.0, 10.0), (30.0, 13.0)),
    }
    assert [s[0] for s in plan.signs] == [
        "exit_A_left",
        "exit_B_right",
        "jps-checkpoints_0",
    ]
    assert plan.signs[2][1:3] == (18.5, 10.5)
    assert plan.smoke_mode == events.SMOKE_NONE and plan.smoke_z_m is None
    assert plan.max_time_s == 300.0 and len(plan.walkable) == 1
    assert pickle.loads(pickle.dumps(plan)) == plan


def test_plan_event_states_the_smoke_the_run_uses():
    """Slice height read, not requested; constant K; smoke-blind."""
    from pyfds_evac.core.plan_view import plan_event
    from pyfds_evac.core.run_config import build_run_kwargs

    scenario = _load(ISO21_CONFIG)

    def plan(*argv: str):
        kwargs = build_run_kwargs(scenario, _parse(*argv))
        return plan_event(
            scenario,
            smoke_speed_model=kwargs["smoke_speed_model"],
            smoke_blind=kwargs["smoke_blind"],
        )

    fds = plan("--fds-dir", ISO21_FDS, "--smoke-slice-height", "1.8")
    # 1.8 m asked for, the nearest slice (2.0 m) read.
    assert (fds.smoke_mode, fds.smoke_z_m, fds.smoke_k) == ("fds", 2.0, None)
    constant = plan("--constant-extinction", "1.0")
    assert (constant.smoke_mode, constant.smoke_k) == ("constant", 1.0)
    assert constant.smoke_z_m is None
    blind = plan("--fds-dir", ISO21_FDS, "--smoke-blind")
    assert (blind.smoke_mode, blind.smoke_z_m) == ("blind", 1.5)


# --- frames -----------------------------------------------------------------


class _Clock:
    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def _run(path: str, recorder=None, *argv: str):
    from pyfds_evac.core.run_config import build_run_kwargs
    from pyfds_evac.core.scenario import run_scenario

    scenario = _load(path)
    opts = _parse("--seed", "7", *argv)
    return run_scenario(
        scenario, frame_recorder=recorder, **build_run_kwargs(scenario, opts)
    )


def _trajectory(result) -> list[tuple]:
    """Trajectory rows, agent ids numbered by first appearance.

    JuPedSim numbers agents per process, so a second run in the same
    process starts at a higher id.
    """
    with sqlite3.connect(result.sqlite_file) as db:
        rows = db.execute(
            "SELECT frame, id, pos_x, pos_y, ori_x, ori_y FROM trajectory_data"
            " ORDER BY frame, id"
        ).fetchall()
    order: dict[int, int] = {}
    return [(f, order.setdefault(i, len(order)), *rest) for f, i, *rest in rows]


def _without_ids(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if k != "agent_id"} for row in rows]


def test_frames_do_not_change_the_run():
    """Frames on every step, smoke grid each time: same trajectory and histories."""
    from pyfds_evac.core.plan_view import FrameRecorder

    frames: list[events.FrameEvent] = []
    recorder = FrameRecorder(frames.append, max_hz=1e9, smoke_hz=1e9)
    on = _run(ISO21_CONFIG, recorder, "--fds-dir", ISO21_FDS)
    off = _run(ISO21_CONFIG, None, "--fds-dir", ISO21_FDS)
    try:
        assert _trajectory(on) == _trajectory(off)
        assert on.smoke_history and _without_ids(on.smoke_history) == _without_ids(
            off.smoke_history
        )
        assert on.metrics["evacuation_time"] == off.metrics["evacuation_time"]
    finally:
        on.cleanup()
        off.cleanup()
    grids = [f.smoke for f in frames if f.smoke is not None]
    assert len(grids) > 1 and all(g.z_m == 1.5 for g in grids)
    assert len({g.fds_time_s for g in grids}) == len(grids)  # sent on change
    assert frames[-1].final and not any(f.final for f in frames[:-1])
    assert frames[-1].evacuated == on.agents_evacuated == 1


ISO22 = REPO / "assets" / "iso_table22_coupled"


def test_frames_do_not_change_a_fire_run_with_incapacitation(tmp_path):
    """FED, rerouting, smoke on iso22/a (one agent incapacitated at 982 s)."""
    from pyfds_evac.core.plan_view import FrameRecorder
    from pyfds_evac.core.run_stream import options, stream_run

    config, fds = str(ISO22 / "config_a.json"), str(ISO22 / "fds" / "a")
    frames: list[events.FrameEvent] = []
    recorder = FrameRecorder(frames.append, max_hz=1e9, smoke_hz=1e9)
    on = _run(config, recorder, "--fds-dir", fds)
    off = _run(config, None, "--fds-dir", fds)
    try:
        assert _trajectory(on) == _trajectory(off)
        for name in ("smoke_history", "fed_history", "route_history", "exit_history"):
            assert _without_ids(getattr(on, name) or []) == _without_ids(
                getattr(off, name) or []
            ), name
        assert on.metrics == off.metrics
        assert on.agents_incapacitated == off.agents_incapacitated == 1
    finally:
        on.cleanup()
        off.cleanup()
    fallen = [a for a in frames[-1].agents() if a[3] == events.AGENT_INCAPACITATED]
    assert len(fallen) == 1 and frames[-1].incapacitated == 1  # still inside

    sent: list = []
    values = {"scenario": config, "fds_dir": fds, "seed": 7}
    result = stream_run(options(values), sent.append)
    assert result.incapacitated == 1
    # #321: the count is meaningful here, and the plan says so before the run.
    assert result.incapacitation_modelled is True
    plan = next(e for e in sent if isinstance(e, events.PlanEvent))
    assert plan.incapacitation_modelled is True
    assert result.remaining == result.total - result.evacuated
    assert not any(isinstance(e, events.FrameEvent) for e in sent)  # off by default


def test_frames_are_throttled_by_wall_time():
    from pyfds_evac.core.plan_view import FrameRecorder

    frames: list[events.FrameEvent] = []
    # Each clock call advances 0.01 s; at most 5 frames per second.
    recorder = FrameRecorder(frames.append, max_hz=5.0, clock=_Clock(0.01))
    result = _run(WORLD77, recorder)
    result.cleanup()
    walls = [f.wall_time for f in frames[:-1]]
    assert all(b - a >= 0.2 - 1e-9 for a, b in zip(walls, walls[1:], strict=False))
    assert frames[-1].final


def test_frames_get_a_frozen_incapacitated_set():
    """The recorder gets a copy it cannot mutate, not the run's own set (#561)."""
    from pyfds_evac.core.plan_view import FrameRecorder

    received: list[object] = []

    class _Spy(FrameRecorder):
        def after_step(self, simulation, *, incapacitated, not_spawned):
            received.append(incapacitated)
            super().after_step(
                simulation, incapacitated=incapacitated, not_spawned=not_spawned
            )

        def finish(self, simulation, *, incapacitated, not_spawned):
            received.append(incapacitated)
            super().finish(
                simulation, incapacitated=incapacitated, not_spawned=not_spawned
            )

    result = _run(WORLD77, _Spy(lambda frame: None, max_hz=1e9))
    result.cleanup()
    assert received
    assert {type(i) for i in received} == {frozenset}
    with pytest.raises(AttributeError):
        received[-1].add(0)  # type: ignore[attr-defined]


@pytest.mark.parametrize("path", [NO_JOURNEY, WORLD77])
def test_exit_counts_add_up_to_the_evacuated(path):
    """Direct-steering removals (every shipped asset) are counted per exit."""
    from pyfds_evac.core.plan_view import FrameRecorder

    frames: list[events.FrameEvent] = []
    recorder = FrameRecorder(frames.append, max_hz=1e9)
    marked: list[int] = []
    leaves = recorder.leaves
    recorder.leaves = lambda agent, exit_id: (
        marked.append(agent),
        leaves(agent, exit_id),
    )
    result = _run(path, recorder)
    result.cleanup()
    last = frames[-1]
    assert sum(last.exit_counts.values()) + last.unattributed == last.evacuated
    assert last.evacuated == result.agents_evacuated > 0
    assert last.unattributed == 0
    assert len(marked) == last.evacuated
    for frame in frames:
        assert len(frame.ids) // 4 == len(frame.states)
    assert len(last.agents()) == result.metrics["agents_remaining"]


class _Agent:
    def __init__(self, agent_id: int, stage: int) -> None:
        self.id = agent_id
        self.stage_id = stage
        self.position = (float(agent_id), 0.0)


class _Simulation:
    """The reads FrameRecorder makes, for exit-stage removals."""

    def __init__(self) -> None:
        self.inside = {1: _Agent(1, 10), 2: _Agent(2, 20), 3: _Agent(3, 99)}
        self.listed: list[int] = []

    def removed_agents(self):
        return self.listed

    def agent(self, agent_id):
        return self.inside[agent_id]

    def agents(self):
        return list(self.inside.values())

    def elapsed_time(self):
        return 1.0


def test_exit_stage_removals_count_in_the_step_they_leave():
    """Listed after step n, gone in step n + 1: counted then, by its stage."""
    from pyfds_evac.core.plan_view import FrameRecorder

    frames: list[events.FrameEvent] = []
    recorder = FrameRecorder(frames.append, max_hz=1e9, smoke_hz=0)
    recorder.start({"a": 10, "b": 20, "d": -1}, ["a", "b", "d"], None, (0, 0, 1, 1))
    sim = _Simulation()
    sim.listed = [1, 3]  # 3 stands on a stage that is no exit
    recorder.after_step(sim, incapacitated={2}, not_spawned=0)
    assert frames[-1].evacuated == 0 and len(frames[-1].agents()) == 3
    del sim.inside[1], sim.inside[3]
    sim.listed = []
    recorder.after_step(sim, incapacitated={2}, not_spawned=0)
    last = frames[-1]
    assert last.exit_counts == {"a": 1, "b": 0, "d": 0}
    assert (last.unattributed, last.evacuated) == (1, 2)
    assert last.agents() == [(2, 2.0, 0.0, events.AGENT_INCAPACITATED)]
    assert last.smoke is None


class _Steps:
    """A fake run: wall and simulated time advance by fixed steps."""

    def __init__(self, wall_step: float, sim_step: float) -> None:
        self.wall = 0.0
        self.sim = _Simulation()
        self.sim_step = sim_step
        self.wall_step = wall_step
        self.sim.elapsed_time = lambda: self.t  # type: ignore[method-assign]
        self.t = 0.0

    def clock(self) -> float:
        return self.wall

    def run(self, recorder, steps: int) -> None:
        recorder.start({}, [], None, (0, 0, 1, 1))
        for _ in range(steps):
            self.wall += self.wall_step
            self.t += self.sim_step
            recorder.after_step(self.sim, incapacitated=set(), not_spawned=0)


@pytest.mark.parametrize(
    ("wall_step", "sim_step", "min_sim_s", "expected"),
    [
        # Wall only: 1/128 s of wall time per step, max_hz 5 -> every 26 steps.
        (0.0078125, 0.01, None, [0.01 + 0.26 * k for k in range(4)]),
        # A fast run without min_sim_s: unchanged, one frame per 0.2 s wall.
        (0.01, 1.0, None, [1.0 + 20 * k for k in range(5)]),
        # Sim only: fast run, at least one frame per 2 s of simulated time.
        (0.01, 1.0, 2.0, [1.0 + 2 * k for k in range(50)]),
        # Both: a slow run still gets the wall-time frames.
        (0.0625, 0.01, 0.5, [0.01 * (1 + 4 * k) for k in range(25)]),
    ],
)
def test_frame_cadence_by_wall_and_sim_time(wall_step, sim_step, min_sim_s, expected):
    from pyfds_evac.core.plan_view import FrameRecorder

    steps = _Steps(wall_step, sim_step)
    frames: list[events.FrameEvent] = []
    recorder = FrameRecorder(
        frames.append, max_hz=5.0, min_sim_s=min_sim_s, clock=steps.clock
    )
    steps.run(recorder, 100)
    assert [f.sim_time for f in frames] == pytest.approx(expected)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_min_sim_s_must_be_positive(bad):
    from pyfds_evac.core.plan_view import FrameRecorder

    with pytest.raises(ValueError, match="min_sim_s"):
        FrameRecorder(lambda e: None, min_sim_s=bad)


def test_sim_time_frames_do_not_change_the_run_and_send_grids_on_change():
    """min_sim_s=1: a frame per simulated second, outputs bit-identical."""
    from pyfds_evac.core.plan_view import FrameRecorder

    frames: list[events.FrameEvent] = []
    recorder = FrameRecorder(frames.append, max_hz=1e-6, smoke_hz=1e9, min_sim_s=1.0)
    on = _run(ISO21_CONFIG, recorder, "--fds-dir", ISO21_FDS)
    off = _run(ISO21_CONFIG, None, "--fds-dir", ISO21_FDS)
    try:
        assert _trajectory(on) == _trajectory(off)
        for name in ("smoke_history", "route_history", "exit_history"):
            assert _without_ids(getattr(on, name) or []) == _without_ids(
                getattr(off, name) or []
            ), name
        assert on.metrics == off.metrics
    finally:
        on.cleanup()
        off.cleanup()
    times = [f.sim_time for f in frames[:-1]]
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert len(times) > 10 and max(gaps) < 1.0 + 0.1
    grids = [f.smoke for f in frames if f.smoke is not None]
    assert len({g.fds_time_s for g in grids}) == len(grids)  # only on a change


def test_jupedsim_removal_semantics():
    """The FrameRecorder relies on these (JuPedSim 1.4.2).

    An agent reaching an exit stage is listed once by removed_agents(),
    still readable with its exit stage; it is gone after the next step. An
    agent marked for removal is not listed.
    """
    import jupedsim as jps
    from shapely import Polygon

    sim = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(),
        geometry=Polygon([(0, 0), (10, 0), (10, 2), (0, 2)]),
    )
    exit_stage = sim.add_exit_stage(Polygon([(9, 0), (10, 0), (10, 2), (9, 2)]))
    journey = sim.add_journey(jps.JourneyDescription([exit_stage]))
    params = jps.CollisionFreeSpeedModelAgentParameters
    walker = sim.add_agent(
        params(journey_id=journey, stage_id=exit_stage, position=(8.5, 1.0))
    )
    marked = sim.add_agent(
        params(journey_id=journey, stage_id=exit_stage, position=(1.0, 1.0))
    )
    sim.mark_agent_for_removal(marked)
    listed = []
    for _ in range(200):
        sim.iterate()
        removed = list(sim.removed_agents())
        if removed:
            assert sim.agent(removed[0]).stage_id == exit_stage
        listed += removed
        if sim.agent_count() == 0:
            break
    assert listed == [walker]


# --- stream_run: warnings, result, subprocess -------------------------------


def test_warnings_carry_the_sim_time():
    from pyfds_evac.core.run_stream import _Clock as SimClock
    from pyfds_evac.core.run_stream import _StdoutEvents, _WarningEvents

    sent: list = []
    clock = SimClock()
    handler = _WarningEvents(sent.append, clock)
    logger = logging.getLogger("pyfds_evac.test_run_events")
    logger.addHandler(handler)
    try:
        logger.warning("before")
        clock.sim_time = 12.5
        logger.warning("during %s", "run")
    finally:
        logger.removeHandler(handler)
    out = _StdoutEvents(sent.append, clock)
    out.write("\rEvacuated 1/2 sim=1.0s\rEvacuated 2/2 sim=2.0s done\n")
    out.write("Warning: no agents fit\nplain line\n")
    assert sent == [
        events.WarningEvent("before", "WARNING", logger.name, None),
        events.WarningEvent("during run", "WARNING", logger.name, 12.5),
        events.LogEvent("Evacuated 2/2 sim=2.0s done"),
        events.WarningEvent("Warning: no agents fit", "WARNING", "stdout", 12.5),
        events.LogEvent("plain line"),
    ]


def test_result_event_is_the_run_outcome(tmp_path):
    from pyfds_evac.core.run_stream import options, stream_run

    sent: list = []
    sqlite = tmp_path / "run.sqlite"
    values = {
        "scenario": T_JUNCTION,
        "seed": 3,
        "output_sqlite": str(sqlite),
        "output_exit_history": str(tmp_path / "exits.csv"),
    }
    result = stream_run(options(values), sent.append, frames=True)
    assert sent[-1] == result
    assert result.status == events.STATUS_INCOMPLETE and result.exit_code == 2
    assert result.total == result.evacuated + result.remaining
    assert result.not_spawned > 0 and result.end_time_s == 300.0
    assert result.seed == 3 and result.incapacitated == 0
    # #321: no dose model, so that 0 is "not modelled", not a measured zero.
    assert result.incapacitation_modelled is False
    plan = next(e for e in sent if isinstance(e, events.PlanEvent))
    assert plan.incapacitation_modelled is False
    assert set(result.files) == {
        str(sqlite.resolve()),
        str((tmp_path / "exits.csv").resolve()),
        str(sqlite.with_suffix(".manifest.json").resolve()),
    }
    assert sum(result.exit_counts.values()) == result.evacuated
    manifest = json.loads(sqlite.with_suffix(".manifest.json").read_text())
    assert manifest["seed"] == 3
    assert manifest["outcome"]["agents_not_spawned"] == result.not_spawned


def test_a_failed_run_is_a_result_event(tmp_path):
    from pyfds_evac.core.run_stream import options, stream_run

    sent: list = []
    missing = str(tmp_path / "missing.json")
    result = stream_run(options({"scenario": missing}), sent.append)
    assert result.status == events.STATUS_FAILED and result.exit_code == 1
    assert result.error.startswith("FileNotFoundError") or "missing" in result.error
    assert result.evacuated is None and result.traceback is None


def _drain(queue, process) -> list:
    received = []
    while True:
        event = queue.get(timeout=300)
        received.append(event)
        if isinstance(event, events.ResultEvent):
            break
    process.join(timeout=60)
    return received


def test_a_child_process_streams_the_run(tmp_path, monkeypatch):
    """Order of the events, the result, and the CLI's SQLite."""
    # The geometry hash in frame_data follows the hash seed; both
    # processes inherit this one.
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    from pyfds_evac.core.run_stream import child_main

    child_db = tmp_path / "child.sqlite"
    values = {
        "scenario": ISO21_CONFIG,
        "fds_dir": ISO21_FDS,
        "seed": 7,
        "output_sqlite": str(child_db),
    }
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(
        target=child_main, args=(values, queue), kwargs={"frames": True}
    )
    process.start()
    received = _drain(queue, process)
    assert process.exitcode == 0
    kinds = [type(e).__name__ for e in received]
    plan = kinds.index("PlanEvent")
    first_frame = kinds.index("FrameEvent")
    assert plan < first_frame < kinds.index("ResultEvent")
    assert kinds[-2:] == ["PhaseEvent", "ResultEvent"]
    frames = [e for e in received if isinstance(e, events.FrameEvent)]
    assert frames[-1].final
    assert received[plan].smoke_mode == events.SMOKE_FDS
    result = received[-1]
    assert (result.status, result.evacuated, result.total) == ("success", 1, 1)
    assert result.end_time_s == pytest.approx(frames[-1].sim_time, abs=0.01)

    cli_db = tmp_path / "cli.sqlite"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pyfds_evac.cli",
            "--scenario",
            ISO21_CONFIG,
            "--fds-dir",
            ISO21_FDS,
            "--seed",
            "7",
            "--output-sqlite",
            str(cli_db),
        ],
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(child_db) as a, sqlite3.connect(cli_db) as b:
        assert list(a.iterdump()) == list(b.iterdump())


def test_a_cancelled_child_reports_cancelled():
    from pyfds_evac.core.run_stream import child_main

    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    cancel = context.Event()
    cancel.set()
    process = context.Process(
        target=child_main, args=({"scenario": ISO21_CONFIG}, queue, cancel)
    )
    process.start()
    result = _drain(queue, process)[-1]
    assert (result.status, result.exit_code) == (events.STATUS_CANCELLED, None)
