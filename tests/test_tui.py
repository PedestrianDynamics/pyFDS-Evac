"""Headless tests of the terminal UI (#485), scenarios A1-A23 of the spec.

Every test drives the app with a fake runner that records what it got and
a fake FDS inspector, so no test imports JuPedSim or fdsreader, except the
slow CLI-equivalence test (A20), which runs the real child process.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import os
import shlex
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("textual")

from pyfds_evac.config import events, frontend  # noqa: E402
from pyfds_evac.config.rules import FdsFacts  # noqa: E402
from pyfds_evac.tui import model  # noqa: E402
from pyfds_evac.tui.app import EvacTui  # noqa: E402
from pyfds_evac.tui.runner import Progress  # noqa: E402
from pyfds_evac.tui.widgets import FieldRow, TooSmall, enabling_option  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets"
ALL_SLICES = frozenset(
    {"extinction", "co", "co2", "o2", "temperature", "integrated_intensity"}
)
FACTS = FdsFacts(ALL_SLICES, (600.0, 1.0))
FIXED_NOW = "2026-10-03T12:00:00+00:00"


# --- fixtures --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _tui_env(tmp_path, monkeypatch):
    """No test writes ~/.config or the checkout; a colour terminal."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv(frontend.RESULTS_ENV, str(tmp_path / "results"))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLORTERM", "truecolor")
    for name in ("NO_COLOR", "PYFDS_EVAC_TUI_THEME", "SSH_CONNECTION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(frontend, "utc_now", lambda: FIXED_NOW)


@pytest.fixture
def workdir(tmp_path):
    """A working folder with a copied subset of assets/."""
    work = tmp_path / "work"
    for name in ("t_junction", "iso_table21_coupled", "ISO-table21", "heat_radiometer"):
        shutil.copytree(ASSETS / name, work / "assets" / name)
    return work


class FakeRunner:
    """Records what a run gets; the test sends the events itself."""

    def __init__(self) -> None:
        self.started: list[tuple[dict, str]] = []
        self.cancelled = 0
        self.stopped = 0
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, values, folder, post) -> None:
        self.started.append((copy.deepcopy(dict(values)), folder))
        self._running = True

    def cancel(self) -> bool:
        self.cancelled += 1
        return True

    def stop(self) -> None:
        self.stopped += 1


def make_app(cwd, runner=None, facts=FACTS, **kwargs) -> EvacTui:
    return EvacTui(
        cwd=cwd,
        runner=runner or FakeRunner(),
        inspector=lambda path: facts,
        debounce=0,
        **kwargs,
    )


async def settle(pilot, app) -> None:
    """Wait for the configuration, inspection and suggestion workers."""
    groups = ("config", "inspect", "suggest")
    for _ in range(400):
        await pilot.pause()
        busy = [w for w in app.workers if w.group in groups and not w.is_finished]
        if not busy:
            await pilot.pause()
            return
        await asyncio.sleep(0.01)
    raise AssertionError("workers did not finish")


async def to_configure(pilot, app, scenario: Path, fds: Path | None) -> None:
    app.select_scenario(scenario)
    await settle(pilot, app)
    app.set_fds_dir(None if fds is None else str(fds))
    app.goto(2)
    await settle(pilot, app)


def run(coro):
    return asyncio.run(coro)


def text_of(app, selector: str) -> str:
    return str(app.query_one(selector).render())


def row(app, dest: str) -> FieldRow:
    return app.query_one(f"#row-{dest}", FieldRow)


def cli_options(command: str) -> dict:
    """The options ``pyfds-evac`` parses from *command*."""
    from pyfds_evac.cli import _build_parser

    args = shlex.split(command)[1:]
    return vars(_build_parser().parse_args(args))


# --- plan-view events of a tiny room (not the T-junction data) ----------------------


def _f32(values) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def tiny_plan(mode: str = events.SMOKE_FDS) -> events.PlanEvent:
    room = ((0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0), (0.0, 0.0))
    exit_ring = ((9.5, 1.5), (10.0, 1.5), (10.0, 2.5), (9.5, 2.5), (9.5, 1.5))
    return events.PlanEvent(
        extent=(0.0, 0.0, 10.0, 4.0),
        walkable=((room, ()),),
        exits={"exit_east": exit_ring},
        exit_openings={"exit_east": ((10.0, 1.5), (10.0, 2.5))},
        signs=(("sign_0", 5.0, 3.5, None),),
        spawn_areas={},
        smoke_mode=mode,
        smoke_k=1.0 if mode == events.SMOKE_CONSTANT else None,
        smoke_z_m=1.6 if mode in (events.SMOKE_FDS, events.SMOKE_BLIND) else None,
        max_time_s=60.0,
        incapacitation_modelled=True,
    )


def tiny_frame(t: float, evacuated: int, final: bool = False) -> events.FrameEvent:
    nx, ny = 20, 8
    values = [min(12.0, 0.2 * i) for j in range(ny) for i in range(nx)]
    grid = events.SmokeGrid(
        0.0, 0.0, 0.5, nx, ny, struct.pack(f"<{nx * ny}e", *values), t, 1.6
    )
    xs, ys = [1.0, 2.0, 2.2, 6.0], [1.0, 2.0, 2.1, 3.0]
    return events.FrameEvent(
        sim_time=t,
        wall_time=t / 10,
        ids=struct.pack("<4i", 1, 2, 3, 4),
        x=_f32(xs),
        y=_f32(ys),
        states=bytes([0, 0, 0, 1]),
        evacuated=evacuated,
        exit_counts={"exit_east": evacuated},
        unattributed=0,
        incapacitated=1,
        not_spawned=0,
        smoke=grid,
        final=final,
    )


def replay(app, result: events.ResultEvent | None = None) -> None:
    """Phase, plan, progress, two frames, a warning and the result."""
    send = app.on_run_event
    send(events.PhaseEvent(events.PHASE_INITIALISING, "Configuring smoke calculation."))
    send(tiny_plan())
    send(events.PhaseEvent(events.PHASE_RUNNING))
    send(Progress(1, 6, 10.0, 1.0, 16, 1, 0))
    send(tiny_frame(10.0, 1))
    send(events.WarningEvent("Agent 4 is incapacitated", sim_time=12.0))
    send(Progress(2, 6, 20.0, 2.0, 33, 1, 0))
    send(tiny_frame(20.0, 2, final=True))
    if result is not None:
        send(result)


def result_event(status: str, **kwargs) -> events.ResultEvent:
    base = {
        events.STATUS_SUCCESS: dict(
            evacuated=6,
            total=6,
            remaining=0,
            incapacitated=0,
            not_spawned=0,
            end_time_s=42.5,
            seed=7,
            summary="Simulation finished in 42.50 s (6/6 evacuated).",
        ),
        events.STATUS_INCOMPLETE: dict(
            evacuated=2,
            total=6,
            remaining=3,
            incapacitated=1,
            not_spawned=1,
            end_time_s=60.0,
            seed=7,
            summary="Simulation incomplete.",
            incapacitation_modelled=True,
        ),
        events.STATUS_FAILED: dict(error="ValueError: boom", traceback="Traceback …"),
        events.STATUS_CANCELLED: {},
    }[status]
    base.update(kwargs)
    return events.ResultEvent(status, events.EXIT_CODES[status], **base)


# --- A1 cold start -------------------------------------------------------------------


def test_a1_help_is_fast_and_imports_no_stack():
    code = (
        "import sys, time; t=time.perf_counter();"
        "from pyfds_evac.tui.launch import main\n"
        "try:\n main(['--help'])\nexcept SystemExit: pass\n"
        "heavy={'textual','jupedsim','fdsreader','numpy','shapely','matplotlib'}"
        "&set(m.split('.')[0] for m in sys.modules)\n"
        "print('HEAVY', sorted(heavy), time.perf_counter()-t)"
    )
    start = time.perf_counter()
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    elapsed = time.perf_counter() - start
    assert "pyfds-evac-tui" in out.stdout
    assert "HEAVY []" in out.stdout
    assert elapsed < 2.0, elapsed  # about 0.1 s here; generous for CI


def test_a1_first_screen_loads_no_simulation_stack(workdir):
    code = f"""
import asyncio, sys
from pyfds_evac.tui.app import EvacTui
class R:
    running = False
async def main():
    app = EvacTui(cwd={str(workdir)!r}, runner=R(), inspector=lambda p: None)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause(); await pilot.pause()
asyncio.run(main())
heavy = {{"jupedsim", "fdsreader", "fdsvismap", "matplotlib", "shapely"}}
print("HEAVY", sorted(heavy & {{m.split(".")[0] for m in sys.modules}}))
"""
    env = {**os.environ, "XDG_CONFIG_HOME": str(workdir / "xdg")}
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert "HEAVY []" in out.stdout, out.stdout + out.stderr


# --- A2-A5 scenario and FDS steps ------------------------------------------------------


def test_a2_examples_list(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            labels = [e.label for e in app.examples]
            variants = [e for e in app.examples if e.variant_of == "t_junction"]
            assert "t_junction" in labels
            assert len(variants) == 5
            assert "heat_radiometer" not in labels
            coupled = next(e for e in app.examples if e.label == "iso_table21_coupled")
            assert coupled.fds_marker == "FDS output found"

    run(go())


def test_a3_no_assets(tmp_path):
    async def go():
        app = make_app(tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.examples is None
            app.query_one("#sc-tabs").active = "tab-examples"
            await pilot.pause()
            text = str(app.query_one("#examples").get_option_at_index(0).prompt)
            assert "No assets/ folder here" in text
            assert model.DOCS_URL in text

    run(go())


def test_a4_invalid_scenario_path_keeps_text(workdir, tmp_path):
    empty = tmp_path / "not_a_scenario"
    empty.mkdir()

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one("#sc-tabs").active = "tab-open"
            await pilot.pause()
            app.query_one("#open-path").focus()
            for key in str(empty):
                await pilot.press(key if key != "/" else "slash")
            await pilot.press("enter")
            await pilot.pause()
            assert "Not a scenario: no config.json" in text_of(app, "#sc-error")
            assert app.query_one("#open-path").value == str(empty)
            assert app.step == 0

    run(go())


def test_a5_fds_suggested_not_set_and_checked(workdir, tmp_path):
    deck_only = tmp_path / "deck"
    deck_only.mkdir()
    (deck_only / "case.fds").write_text("&HEAD /\n")

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            app.select_scenario(workdir / "assets" / "iso_table21_coupled")
            await settle(pilot, app)
            fds = (workdir / "assets" / "iso_table21_coupled" / "fds").resolve()
            assert fds in app.suggestions
            assert app.form.fds_dir is None  # suggested, never set by itself
            app.query_one("#fds-path").value = str(deck_only)
            app._fds_typed(str(deck_only))
            await pilot.pause()
            assert "No .smv file in" in text_of(app, "#fds-panel")
            assert app.form.fds_dir is None
            choices = app.query_one("#fds-choices")
            choices.focus()
            # Typing a path lists its folders first; the suggestion follows.
            ids = [
                choices.get_option_at_index(i).id for i in range(choices.option_count)
            ]
            choices.highlighted = ids.index("fds-0")
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.fds_dir == str(fds)
            assert app.step == 2

    run(go())


# --- A6-A9 configure ---------------------------------------------------------------------


def test_a6_heat_path_reaches_the_runner(workdir):
    scenario = workdir / "assets" / "iso_table21_coupled"
    fds = scenario / "fds"
    runner = FakeRunner()

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(100, 30)) as pilot:
            await to_configure(pilot, app, scenario, fds)
            heat = row(app, "heat_clothing")
            assert heat.control.disabled
            assert heat.reason == "without --enable-heat-fed"
            app.query_one("#f-enable_heat_fed").focus()
            await pilot.press("enter")  # Switch toggles on Enter
            await settle(pilot, app)
            assert app.form.switch["enable_heat_fed"] is True
            assert not row(app, "heat_clothing").control.disabled
            app.form.text["heat_fed_method"] = "total-flux"
            app.form.text["heat_regime"] = "layer"
            row(app, "heat_fed_method").sync_control()
            row(app, "heat_regime").sync_control()
            app.form_changed()
            await settle(pilot, app)
            # D19 alone: the heat model's value check skips what D19 owns.
            assert app.invalid_count() == len(app.cfg.errors) == 1
            assert app.cfg.errors[0].rule == "D19"
            assert app.cfg.errors[0].option == "heat_layer_height"
            assert f"✗ {app.invalid_count()} error" in str(app.summary_line())
            for dest, value in (
                ("heat_layer_height", "2.5"),
                ("heat_view_factor", "1"),
                ("heat_layer_emissivity", "0.9"),
            ):
                app.focus_field(dest)
                await pilot.pause()
                for key in value:
                    await pilot.press("full_stop" if key == "." else key)
            await settle(pilot, app)
            assert app.invalid_count() == 0, app.cfg.errors
            assert "✓ valid" in str(app.summary_line())
            await pilot.press("ctrl+r")
            await pilot.pause()
            if isinstance(app.screen, type(app.screen)) and app.current_run is None:
                await pilot.press("r")  # one confirm for setup warnings
                await pilot.pause()
            values, _folder = runner.started[-1]
            assert values["enable_heat_fed"] is True
            assert values["heat_fed_method"] == "total-flux"
            assert values["heat_regime"] == "layer"
            assert values["heat_layer_height"] == 2.5
            parsed = cli_options(app.current_run.snapshot.command)
            assert {k: parsed[k] for k in values} == values

    run(go())


def test_a7_disabled_row_states_reason_and_enter_goes_to_switch(workdir):
    scenario = workdir / "assets" / "iso_table21_coupled"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await to_configure(pilot, app, scenario, scenario / "fds")
            target = row(app, "heat_incapacitation_mode")
            app.focus_field("heat_incapacitation_mode")
            await pilot.pause()
            assert app.focused is target
            assert "without --enable-heat-fed" in str(
                target.query_one(".help").render()
            )
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is app.query_one("#f-enable_heat_fed")

    run(go())


def test_a7_reason_names_the_enabling_option():
    assert enabling_option("without --enable-heat-fed") == "enable_heat_fed"
    assert enabling_option("with --no-enable-rerouting") == "enable_rerouting"
    assert enabling_option("because the FDS case has no TEMPERATURE slice") is None


def test_a8_values_survive_errors_and_steps(workdir):
    scenario = workdir / "assets" / "iso_table21_coupled"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            await to_configure(pilot, app, scenario, scenario / "fds")
            app.focus_field("smoke_slice_height")
            await pilot.pause()
            app.query_one("#f-smoke_slice_height").value = ""
            for key in "abc":
                await pilot.press(key)
            await settle(pilot, app)
            assert (
                app.parse_errors["smoke_slice_height"] == "invalid float value: 'abc'"
            )
            assert row(app, "smoke_slice_height").has_class("-invalid")
            await pilot.press("escape")
            await pilot.pause()
            assert app.step == 1
            app.goto(2)
            await settle(pilot, app)
            assert app.query_one("#f-smoke_slice_height").value == "abc"
            assert app.form.text["smoke_slice_height"] == "abc"

    run(go())


def test_a9_no_range_rejection(workdir):
    scenario = workdir / "assets" / "iso_table21_coupled"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            await to_configure(pilot, app, scenario, scenario / "fds")
            app.form.text["o2_threshold_percent"] = "50"
            app.form_changed()
            await settle(pilot, app)
            assert "o2_threshold_percent" not in app.parse_errors
            assert app.invalid_count() == 0

    run(go())


def test_parse_uses_the_cli_parser_messages():
    assert model.parse_value("heat_u_factor", "0.5") == 0.5
    with pytest.raises(ValueError, match=r"must be in \[0.25, 1"):
        model.parse_value("heat_u_factor", "2")
    with pytest.raises(ValueError, match="invalid int value"):
        model.parse_value("seed", "1.5")
    assert model.parse_value("seed", "") is None
    assert model.parse_value("smoke_slice_height", "") == 1.6


# --- A10-A11 review ------------------------------------------------------------------------


def test_a10_review_is_the_model(workdir):
    from pyfds_evac.config.effective import effective_configuration

    scenario = workdir / "assets" / "iso_table21_coupled"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await to_configure(pilot, app, scenario, scenario / "fds")
            app.form.text["fic_alpha"] = "0.5"  # inert without --enable-fic-speed
            app.form.text["seed"] = "7"
            app.form_changed()
            await settle(pilot, app)
            app.goto(3)
            await pilot.pause()
            expected = effective_configuration(
                app.namespace(), app.form.scenario.raw, fds=FACTS, inspect_fds=False
            ).to_dict()
            assert app.cfg.to_dict() == expected
            body = str(app.query_one("#rv-body #body").render())
            for name, mech in expected["mechanisms"].items():
                assert name in body
            for inactive in expected["inactive"]:
                assert inactive["reason"] in body
            for warning in expected["warnings"]:
                assert warning[:40] in body
            assert app.query_one("#rv-command").text == expected["command"]

    run(go())


def test_a11_copy_and_save(workdir, monkeypatch):
    scenario = workdir / "assets" / "iso_table21_coupled"

    async def go():
        app = make_app(workdir)
        copied: list[str] = []
        monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
        async with app.run_test(size=(100, 30)) as pilot:
            await to_configure(pilot, app, scenario, scenario / "fds")
            app.goto(3)
            await pilot.pause()
            await pilot.press("c")
            assert copied == [app.cfg.command]
            await pilot.press("s")
            await pilot.pause()
            folder = Path(app.planned())
            assert (folder / "command.sh").read_text() == app.cfg.command + "\n"
            assert (folder / "run.py").read_text() == app.preview_script() + "\n"
            compile((folder / "run.py").read_text(), "run.py", "exec")
            assert cli_options(app.cfg.command)["output_sqlite"].startswith(str(folder))

    run(go())


# --- A12-A16 run --------------------------------------------------------------------------


async def _started(pilot, app, workdir, runner=None):
    scenario = workdir / "assets" / "iso_table21_coupled"
    await to_configure(pilot, app, scenario, scenario / "fds")
    app.goto(3)
    await pilot.pause()
    await pilot.press("ctrl+r")
    await pilot.pause()
    assert app.current_run is not None


@pytest.mark.parametrize(
    ("status", "words", "never"),
    [
        (events.STATUS_SUCCESS, "✓ Complete: all agents evacuated", "Incomplete"),
        (
            events.STATUS_INCOMPLETE,
            "◐ Incomplete: time limit reached, 3 agents inside, 1 not spawned",
            "Complete:",
        ),
        (events.STATUS_FAILED, "✗ Run failed: ValueError: boom", "Complete"),
        (events.STATUS_CANCELLED, "■ Cancelled at sim 20.0 s", "Complete"),
    ],
)
def test_a12_run_states(workdir, status, words, never):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            replay(app, result_event(status))
            await pilot.pause()
            assert app.step == 5
            text = str(app.query_one("#res-outcome").render())
            assert words in text
            assert never not in text.split("\n")[0]

    run(go())


def test_a12_child_died_without_result(workdir):
    from pyfds_evac.tui.runner import ChildExited

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.on_run_event(ChildExited(-9, "Killed", "child.log", stopped=False))
            await pilot.pause()
            text = str(app.query_one("#res-outcome").render())
            assert "The run stopped without a result (process exit -9)" in text

    run(go())


def test_a13_cancel_asks_and_lists_kept_files(workdir):
    runner = FakeRunner()

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            replay(app)
            await pilot.press("ctrl+c")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert runner.cancelled == 0
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert runner.cancelled == 1
            assert "Cancelling" in text_of(app, "#run-status")
            kept = Path(app.current_run.snapshot.values["output_route_history"])
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_text("time_s\n")
            app.on_run_event(result_event(events.STATUS_CANCELLED))
            await pilot.pause()
            assert "■ Cancelled" in text_of(app, "#res-outcome")
            files = app.query_one("#res-files")
            prompts = [
                str(files.get_option_at_index(i).prompt)
                for i in range(files.option_count)
            ]
            assert any(kept.name in p for p in prompts)

    run(go())


def test_a14_one_run_at_a_time(workdir):
    runner = FakeRunner()

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.action_run()
            await pilot.pause()
            assert len(runner.started) == 1
            assert any(
                "A run is in progress (run #1)" in n.message for n in app._notifications
            )

    run(go())


def test_a15_snapshot_is_immutable(workdir):
    runner = FakeRunner()

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            before = copy.deepcopy(dict(app.current_run.snapshot.values))
            app.goto(2)
            app.query_one("#f-seed").value = "99"
            await settle(pilot, app)
            assert dict(app.current_run.snapshot.values) == before
            assert runner.started[0][0] == before
            with pytest.raises(TypeError):
                app.current_run.snapshot.values["seed"] = 1  # type: ignore[index]

    run(go())


def test_a16_settings_changed_banner(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            replay(app, result_event(events.STATUS_SUCCESS))
            await pilot.pause()
            assert not app.query_one("#res-banner").display
            app.goto(2)
            app.query_one("#f-seed").value = "3"
            await settle(pilot, app)
            app.goto(5)
            await pilot.pause()
            assert app.query_one("#res-banner").display
            assert "Settings changed since run #1" in text_of(app, "#res-banner")
            assert "6 Results✎" in text_of(app, "#stepbar")

    run(go())


def test_a16b_edit_during_a_run_marks_results_stale(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.goto(2)
            app.query_one("#f-seed").value = "99"
            await settle(pilot, app)
            replay(app, result_event(events.STATUS_INCOMPLETE))
            await pilot.pause()
            assert app.query_one("#res-banner").display
            assert "6 Results✎" in text_of(app, "#stepbar")
            app.goto(2)
            app.query_one("#f-seed").value = ""  # back to the run's settings
            await settle(pilot, app)
            app.goto(5)
            await pilot.pause()
            assert not app.query_one("#res-banner").display
            assert "6 Results◐" in text_of(app, "#stepbar")

    run(go())


def test_review_while_running_says_so(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.goto(3)
            await pilot.pause()
            assert "⟳ Run #1 in progress" in text_of(app, "#rv-outcome")

    run(go())


def test_save_writes_a_script_for_the_planned_folder(workdir):
    scenario = workdir / "assets" / "ISO-table21"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await to_configure(pilot, app, scenario, None)
            app.goto(3)
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            folder = app.planned()
            script = (Path(folder) / "run.py").read_text()
            assert f"{folder}/python_output" in script
            assert "not started" in script

    run(go())


def test_run_script_uses_the_seed_the_run_used(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            replay(app, result_event(events.STATUS_SUCCESS, seed=420))
            await pilot.pause()
            script = app.run_script()
            assert "'seed': 420" in script
            compile(script, "run.py", "exec")

    run(go())


# --- A17-A19 sizes, colour, themes, keyboard ----------------------------------------------------


def _horizontal_scroll(app) -> list[str]:
    """Containers that show a horizontal scrollbar (inputs scroll their text)."""
    from textual.widgets import Input, TextArea

    return [
        str(w)
        for w in app.screen.query("*")
        if w.display
        and not isinstance(w, (Input, TextArea))
        and getattr(w, "show_horizontal_scrollbar", False)
    ]


@pytest.mark.parametrize("size", [(80, 24), (100, 30), (120, 35), (200, 50)])
def test_a17_no_horizontal_scroll(workdir, size):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=size) as pilot:
            await _started(pilot, app, workdir)
            replay(app)
            for step in (4,):
                app.goto(step)
                await pilot.pause()
                assert not _horizontal_scroll(app), (step, _horizontal_scroll(app))
            app.on_run_event(result_event(events.STATUS_INCOMPLETE))
            await pilot.pause()
            for step in (0, 1, 2, 3, 5):
                app.goto(step)
                await pilot.pause()
                assert not _horizontal_scroll(app), (step, _horizontal_scroll(app))

    run(go())


def test_a17_size_notice_comes_and_goes(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(72, 20)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, TooSmall)
            assert "Terminal is 72×20" in str(app.screen.query_one("#notice").render())
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            assert not isinstance(app.screen, TooSmall)

    run(go())


@pytest.mark.parametrize("theme", ["evac-dark", "solarized-light"])
@pytest.mark.parametrize("no_color", [False, True])
def test_a18_themes_and_no_color_keep_words(workdir, monkeypatch, theme, no_color):
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")

    async def go():
        app = make_app(workdir, theme=theme)
        async with app.run_test(size=(120, 35)) as pilot:
            assert app.theme == theme
            await _started(pilot, app, workdir)
            replay(app, result_event(events.STATUS_INCOMPLETE))
            await pilot.pause()
            assert "◐ Incomplete" in text_of(app, "#res-outcome")
            legend = text_of(app, "#res-legend")
            assert "incapacitated" in legend
            if no_color:
                assert "░0.1" in legend  # shade glyphs carry the bins

    run(go())


def test_only_two_themes_in_the_palette(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            titles = [c.title for c in app.get_system_commands(app.screen)]
            themes = [t for t in titles if t.startswith("Theme")]
            assert themes == ["Theme: evac dark", "Theme: Solarized Light"]
            app.set_theme("solarized-light")
            assert model.Recent().theme == "solarized-light"

    run(go())


def test_a19_keyboard_only_to_a_run(workdir):
    runner = FakeRunner()

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(80, 24)) as pilot:
            for key in "iso_table21_c":
                await pilot.press("underscore" if key == "_" else key)
            await pilot.press("enter")
            await settle(pilot, app)
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.step == 2
            await pilot.press("ctrl+f")
            await pilot.pause()
            for key in "enable-heat":
                await pilot.press("minus" if key == "-" else key)
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is app.query_one("#f-enable_heat_fed")
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.switch["enable_heat_fed"]
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.step == 3
            await pilot.press("ctrl+r")
            await pilot.pause()
            values, _ = runner.started[-1]
            assert values["enable_heat_fed"] is True

    run(go())


# --- A21-A23 events, fallbacks, the demo path --------------------------------------------------


def test_a21_warning_in_log_and_counter(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.on_run_event(events.WarningEvent("Smoke slice missing", sim_time=3.0))
            await pilot.pause(0.2)  # the Run step redraws at most every 0.1 s
            log = "\n".join(s.text for s in app.query_one("#run-log").lines)
            assert "WARNING Smoke slice missing" in log
            assert "! 1 warning" in text_of(app, "#run-status")

    run(go())


def test_a22_plan_fallbacks(workdir, monkeypatch):
    from pyfds_evac.tui.planview import PlanView, legend_text

    assert legend_text(None) == "plan not available"
    assert legend_text(tiny_plan(events.SMOKE_NONE)) == "no fire input"
    assert (
        legend_text(tiny_plan(events.SMOKE_CONSTANT)) == "uniform K = 1 1/m (constant)"
    )
    assert "smoke-blind" in legend_text(tiny_plan(events.SMOKE_BLIND))

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await _started(pilot, app, workdir)
            await pilot.pause()
            view = app.query_one("#run-planview", PlanView)
            assert "plan not available" in str(view.render())
            app.on_run_event(tiny_plan())
            app.on_run_event(tiny_frame(5.0, 0))
            await pilot.pause(0.2)
            drawn = str(view.render())
            assert "east 0" in drawn and "•" in drawn and "x" in drawn
            monkeypatch.setenv("TERM", "dumb")
            assert "plan not available" in str(view.render())

    run(go())


def test_a23_demo_path(workdir):
    runner = FakeRunner()
    keys = [
        *"iso",
        "underscore",
        *"table21",
        "underscore",
        "c",
        "enter",
        "enter",
        "ctrl+r",
    ]

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(80, 24)) as pilot:
            pressed = 0
            for key in keys:
                await pilot.press(key)
                pressed += 1
                if key == "enter":
                    await settle(pilot, app)
            await pilot.pause()
            if not runner.started:
                await pilot.press("r")  # one confirm for setup warnings
                pressed += 1
                await pilot.pause()
            values, _ = runner.started[-1]
            scenario = (workdir / "assets" / "iso_table21_coupled").resolve()
            assert values["scenario"] == str(scenario)
            assert values["fds_dir"] == str(scenario / "fds")
            app.on_run_event(result_event(events.STATUS_SUCCESS))
            await pilot.pause()
            assert app.step == 5
            assert pressed <= 17, pressed

    run(go())


def test_recent_entry_reopens_review(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.on_run_event(result_event(events.STATUS_SUCCESS))
            await pilot.pause()
        second = make_app(workdir)
        async with second.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            assert second.query_one("#sc-tabs").active == "tab-recent"
            await pilot.press("enter")
            await settle(pilot, second)
            assert second.step == 3
            assert second.form.fds_dir.endswith("iso_table21_coupled/fds")

    run(go())


# --- model -------------------------------------------------------------------------------------


def test_form_namespace_holds_run_options_only():
    from pyfds_evac.config.parameters import RUN_OPTIONS

    form = model.Form()
    form.scenario = model.read_scenario(ASSETS / "ISO-table21")
    ns = form.namespace()
    assert set(vars(ns)) == set(RUN_OPTIONS)
    assert "collect_route_cost_history" not in vars(ns)


def test_run_folder_matches_the_gui_layout(tmp_path):
    form = model.Form()
    form.scenario = model.read_scenario(ASSETS / "t_junction" / "config_full.json")
    base = form.run_folder("S", tmp_path)
    assert (
        base == f"{tmp_path.as_posix()}/t_junction_config_full/deterministic/seed42/S"
    )
    form.output_folder = "mine"
    assert form.run_folder("S", tmp_path) == f"{tmp_path.as_posix()}/mine/S"


def test_recent_keeps_ten_and_survives_a_bad_file(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text("{not json")
    recent = model.Recent(path)
    for i in range(12):
        recent.add(f"s{i}", None, "complete", "d")
    assert len(model.Recent(path).runs) == model.MAX_RECENT
    assert model.Recent(path).runs[0]["scenario"] == "s11"


def test_fds_search_is_bounded(tmp_path):
    for i in range(50):
        (tmp_path / f"d{i}").mkdir()
    (tmp_path / "d1" / "case.smv").write_text("")
    assert model.find_fds_dirs([tmp_path]) == [(tmp_path / "d1").resolve()]
    assert model.find_fds_dirs([tmp_path], max_entries=10) == []


# --- #598 the footer always shows quit and keys ---------------------------------------


def fixed_keys(app) -> dict[str, object]:
    """The footer's fixed group of *app*'s current screen: label -> FooterKey."""
    from textual.widgets._footer import FooterKey

    group = app.screen.query_one("#fixed-keys")
    return {k.description: k for k in group.query(FooterKey)}


def assert_quit_and_keys(app) -> None:
    keys = fixed_keys(app)
    assert list(keys) == ["quit", "keys", "palette"]
    assert [k.key for k in keys.values()] == ["ctrl+q", "question_mark", "ctrl+k"]
    width = app.screen.size.width
    for key in keys.values():
        assert key.region.width > 0
        assert key.region.right <= width


async def _at_step(pilot, app, workdir, step: int) -> None:
    if step == 0:
        return
    scenario = workdir / "assets" / "ISO-table21"
    if step == 1:
        app.select_scenario(scenario)
        await settle(pilot, app)
        return
    await to_configure(pilot, app, scenario, None)
    if step == 2:
        return
    app.goto(3)
    await pilot.pause()
    if step == 3:
        return
    await pilot.press("ctrl+r")
    await pilot.pause()
    replay(app, result_event(events.STATUS_INCOMPLETE) if step == 5 else None)
    await pilot.pause(0.2)  # let the Run step's 0.1 s redraw timer fire


@pytest.mark.parametrize("step", range(6))
def test_598_footer_shows_quit_and_keys_on_every_step(workdir, step):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _at_step(pilot, app, workdir, step)
            await pilot.pause()
            assert app.step == step
            assert_quit_and_keys(app)

    run(go())


def test_598_footer_on_the_full_plan(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _at_step(pilot, app, workdir, 5)
            await pilot.press("v")
            await pilot.pause()
            assert type(app.screen).__name__ == "PlanScreen"
            assert_quit_and_keys(app)

    run(go())


@pytest.mark.parametrize("step", [4, 5])
def test_598_at_80_columns_the_step_keys_give_way(workdir, step):
    """Run and Results have the most step keys; the fixed group stays whole."""
    from textual.widgets._footer import FooterKey

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            await _at_step(pilot, app, workdir, step)
            await pilot.pause()
            assert_quit_and_keys(app)
            group = app.screen.query_one("#fixed-keys")
            fixed = set(fixed_keys(app).values())
            y = group.region.y
            # The fixed group is drawn on top of the step keys, every cell of it.
            for x in range(group.region.x, group.region.right):
                top, _ = app.screen.get_widget_at(x, y)
                assert top is group or top in fixed
            # The step keys start at the left and are what gets cut.
            first, _ = app.screen.get_widget_at(0, y)
            assert isinstance(first, FooterKey) and first not in fixed
            assert group.region.x > 40

    run(go())


def test_598_question_mark_opens_the_keys_from_a_text_box(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.focused is app.query_one("#ex-filter")
            await pilot.press("question_mark")
            await pilot.pause()
            assert type(app.screen).__name__ == "TextScreen"
            assert "ctrl+q" in app.screen.text
            assert app.query_one("#ex-filter").value == ""

    run(go())


def test_598_f1_works_outside_configure(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _at_step(pilot, app, workdir, 1)
            await pilot.press("f1")
            await pilot.pause()
            assert app.screen.title_text == "Keys"

    run(go())


def test_598_field_help_also_lists_the_keys(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _at_step(pilot, app, workdir, 2)
            assert app.focused is not None
            await pilot.press("question_mark")
            await pilot.pause()
            assert "Flag: --" in app.screen.text
            assert "ctrl+q            quit" in app.screen.text

    run(go())


def test_598_question_mark_types_in_the_find_box(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _at_step(pilot, app, workdir, 2)
            await pilot.press("ctrl+f")
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert type(app.screen).__name__ == "FindScreen"
            assert app.screen.query_one("#find").value == "?"

    run(go())


def test_598_quit_during_a_run_still_asks(workdir):
    runner = FakeRunner()

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(80, 24)) as pilot:
            await _at_step(pilot, app, workdir, 4)
            assert_quit_and_keys(app)
            await pilot.press("ctrl+q")
            await pilot.pause()
            assert type(app.screen).__name__ == "ConfirmScreen"
            await pilot.press("n")
            await pilot.pause()
            assert runner.stopped == 0
            assert app.is_running

    run(go())


# --- snapshots (SVGs also serve the docs) ---
# The Review screen is not snapshotted: its command holds absolute paths.
# --------------------------------------------------


def pin_wall(run, seconds: int) -> None:
    """Fix the wall time a snapshot shows (#553).

    ``started`` comes from time.monotonic(); ``(started + 44) - started``
    rounds to 43.999… for some start values (about 0.4 % of them shortly
    after boot), and the truncating clock then shows 0:43. Both ends are
    set to exact values instead.
    """
    run.started, run.ended = 1000.0, 1000.0 + seconds


def _snap_app(workdir, theme="evac-dark"):
    return make_app(workdir, theme=theme)


def steady(before=None):
    """Run *before*, then stop the cursors blinking (#553).

    A focused Input toggles its cursor every 0.5 s, so on a slow runner
    the capture can fall into the hidden phase. A cursor that does not
    blink stays visible.
    """

    async def run(pilot):
        if before is not None:
            await before(pilot)
        for widget in pilot.app.screen.query("*"):
            if hasattr(widget, "cursor_blink"):
                widget.cursor_blink = False
        await pilot.pause()

    return run


@pytest.mark.parametrize("theme", ["evac-dark", "solarized-light"])
def test_snapshot_scenario(workdir, snap_compare, theme):
    assert snap_compare(
        _snap_app(workdir, theme), terminal_size=(80, 24), run_before=steady()
    )


@pytest.mark.parametrize("theme", ["evac-dark", "solarized-light"])
def test_snapshot_configure(workdir, snap_compare, theme):
    async def before(pilot):
        await to_configure(pilot, pilot.app, workdir / "assets" / "ISO-table21", None)

    assert snap_compare(
        _snap_app(workdir, theme), terminal_size=(80, 24), run_before=steady(before)
    )


@pytest.mark.parametrize("theme", ["evac-dark", "solarized-light", "NO_COLOR"])
def test_snapshot_run_with_plan(workdir, snap_compare, monkeypatch, theme):
    if theme == "NO_COLOR":
        monkeypatch.setenv("NO_COLOR", "1")

    async def before(pilot):
        app = pilot.app
        await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
        app.goto(3)
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        replay(app)
        pin_wall(app.current_run, 44)
        await pilot.pause(0.2)
        app.render_run()
        await pilot.pause()

    app = _snap_app(workdir, "evac-dark" if theme == "NO_COLOR" else theme)
    assert snap_compare(app, terminal_size=(120, 35), run_before=steady(before))


def test_snapshot_results(workdir, snap_compare):
    async def before(pilot):
        app = pilot.app
        await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
        app.goto(3)
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        replay(app, result_event(events.STATUS_INCOMPLETE))
        pin_wall(app.current_run, 72)
        app.render_results()
        await pilot.pause()

    assert snap_compare(
        _snap_app(workdir), terminal_size=(80, 24), run_before=steady(before)
    )


# --- A20 CLI <-> TUI equivalence (slow, real child process) -----------------------------------


@pytest.mark.slow
def test_a20_tui_run_equals_cli(tmp_path, monkeypatch):
    from pyfds_evac.tui.runner import ProcessRunner

    # A temp root of its own: other runs sharing the system temp dir
    # (parallel suites, a TUI) do not affect the clean-up check (#551).
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    made: list[str] = []
    mkdtemp = tempfile.mkdtemp

    def recording_mkdtemp(*args, **kwargs):
        made.append(mkdtemp(*args, **kwargs))
        return made[-1]

    monkeypatch.setattr(tempfile, "mkdtemp", recording_mkdtemp)

    form = model.Form()
    form.scenario = model.read_scenario(ASSETS / "ISO-table21")
    form.text["seed"] = "7"
    base = form.run_folder("TUI", tmp_path)
    ns = form.namespace(form.output_paths(base))
    got: list = []
    runner = ProcessRunner()
    runner.start(vars(ns), base, got.append)
    assert runner.join(300)
    result = got[-1]
    assert isinstance(result, events.ResultEvent), got[-3:]
    assert result.seed == 7

    from pyfds_evac.config.effective import cli_command

    cli_base = form.run_folder("CLI", tmp_path)
    cli_ns = argparse.Namespace(**{**vars(ns), **form.output_paths(cli_base)})
    command = shlex.split(cli_command(cli_ns))
    exe = Path(sys.executable).with_name("pyfds-evac")
    done = subprocess.run([str(exe), *command[1:]], capture_output=True, text=True)
    assert done.returncode == events.EXIT_CODES[result.status], done.stderr

    def rows(path: str) -> list:
        with sqlite3.connect(path) as db:
            return db.execute(
                "SELECT * FROM trajectory_data ORDER BY frame, id"
            ).fetchall()

    assert rows(ns.output_sqlite) == rows(cli_ns.output_sqlite)
    for dest in (
        "output_smoke_history",
        "output_fed_history",
        "output_route_history",
        "output_exit_history",
        "output_route_cost_history",
    ):
        tui_file, cli_file = Path(getattr(ns, dest)), Path(getattr(cli_ns, dest))
        assert tui_file.exists() == cli_file.exists()
        if tui_file.exists():
            assert tui_file.read_bytes() == cli_file.read_bytes()
    # The child's private temporary folder was made here and is gone (#331).
    run_tmp = [Path(p) for p in made if Path(p).name.startswith("pyfds-evac-run-")]
    assert len(run_tmp) == 1 and run_tmp[0].parent == tmp, made
    assert not run_tmp[0].exists()
    assert list(tmp.glob("pyfds-evac-run-*")) == []
    assert (Path(base) / "child.log").exists()


def test_missing_extra_gives_the_install_hint():
    code = (
        "import sys; sys.modules['textual'] = None\n"
        "from pyfds_evac.tui.launch import main\n"
        "main([])\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 1
    assert "pip install 'pyfds-evac[tui]'" in out.stderr


def test_sweep_removes_folders_of_dead_tui_processes(tmp_path):
    from pyfds_evac.tui.runner import TMP_PREFIX, sweep_temp_dirs

    dead = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    stale = tmp_path / f"{TMP_PREFIX}{dead}-abc"
    mine = tmp_path / f"{TMP_PREFIX}{os.getpid()}-abc"
    other = tmp_path / f"{TMP_PREFIX}xyz"
    for folder in (stale, mine, other):
        folder.mkdir()
    assert sweep_temp_dirs(str(tmp_path)) == [str(stale)]
    assert mine.exists() and other.exists()


def _child_entry_with(parent: str, tmp_path: Path) -> tuple[Path, str]:
    """Run ``child_entry`` with a stub run and *parent* as the TUI's pid."""
    run_tmp = tmp_path / "run-tmp"
    run_tmp.mkdir()
    log = tmp_path / "child.log"
    code = f"""
import os, sys, types
stub = types.ModuleType("pyfds_evac.core.run_stream")
def child_main(values, queue, stop, **options):
    print("stopped" if stop.is_set() else "running", flush=True)
stub.child_main = child_main
sys.modules["pyfds_evac.core.run_stream"] = stub
import multiprocessing
from pyfds_evac.tui.runner import child_entry
child_entry({{}}, None, multiprocessing.Event(), {str(log)!r}, {str(run_tmp)!r},
            {{}}, {parent})
"""
    subprocess.run([sys.executable, "-c", code], check=True)
    return run_tmp, log.read_text() if log.exists() else ""


def test_child_started_after_the_tui_died_stops_and_cleans_up(tmp_path):
    """The TUI's pid comes from the TUI, not from the reparented child (#555)."""
    dead = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    run_tmp, log = _child_entry_with(dead, tmp_path)
    assert "running" not in log
    assert not run_tmp.exists()


def test_child_of_a_live_tui_runs_and_leaves_the_folder_to_it(tmp_path):
    run_tmp, log = _child_entry_with("os.getppid()", tmp_path)
    assert log.strip() == "running"
    assert run_tmp.exists()


@pytest.mark.slow
def test_child_stops_and_cleans_up_when_the_tui_is_killed(tmp_path):
    """A killed TUI (SIGKILL, terminal gone) leaves no run or temp folder."""
    import queue
    import signal
    import threading

    tmp = tmp_path / "tmp"
    tmp.mkdir()
    form = model.Form()
    form.scenario = model.read_scenario(ASSETS / "t_junction")
    base = form.run_folder("KILL", tmp_path)
    values = vars(form.namespace(form.output_paths(base)))
    parent = f"""
import os, sys, time
from pyfds_evac.tui.runner import Progress, ProcessRunner
seen = []
def post(event):
    if isinstance(event, Progress) and not seen:
        seen.append(event)
        print("in the run", flush=True)
runner = ProcessRunner()
runner.start({dict(values)!r}, {base!r}, post)
print(runner._proc.pid, flush=True)
time.sleep(600)
"""
    env = {**os.environ, "TMPDIR": str(tmp)}
    proc = subprocess.Popen(
        [sys.executable, "-c", parent], stdout=subprocess.PIPE, text=True, env=env
    )
    child = int(proc.stdout.readline())
    # Kill the TUI once the child reports progress (it is then inside the
    # run), not after a fixed sleep: under load the child may still be
    # starting after a few seconds.
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(
        target=lambda: [lines.put(line) for line in proc.stdout], daemon=True
    ).start()
    try:
        assert lines.get(timeout=120).strip() == "in the run"
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait()
    for _ in range(300):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.2)
    else:
        os.kill(child, signal.SIGKILL)
        raise AssertionError("the child kept running after the TUI was killed")
    assert list(tmp.glob("pyfds-evac-run-*")) == []


def test_events_from_the_reader_thread_run_in_the_app_context(workdir):
    """Events posted from another thread may start timers; quitting is clean."""
    import threading

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            sender = threading.Thread(
                target=app._post, args=(Progress(1, 6, 5.0, 0.5, 16, 0, 0),)
            )
            sender.start()
            sender.join()
            await pilot.pause(0.3)
            assert app.current_run.progress.sim_time == 5.0
            await pilot.pause()

    run(go())


def test_events_after_quit_are_dropped(workdir):
    """ctrl+q, y during a run: late events from the reader do nothing."""
    import threading

    runner = FakeRunner()
    errors: list = []

    async def go():
        app = make_app(workdir, runner)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app._ui_loop.set_exception_handler(lambda loop, ctx: errors.append(ctx))
            app._confirmed_quit(True)
            await pilot.pause()
        # The screens are gone; the loop still runs, as during a real exit.
        sender = threading.Thread(target=app._post, args=(events.LogEvent("late"),))
        sender.start()
        sender.join()
        await asyncio.sleep(0.1)
        assert runner.stopped == 1

    run(go())
    assert errors == []


def test_recent_records_the_run_scenario_not_the_form(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.select_scenario(workdir / "assets" / "ISO-table21", advance=False)
            await settle(pilot, app)
            app.on_run_event(result_event(events.STATUS_SUCCESS))
            await pilot.pause()
            entry = model.Recent().runs[0]
            assert entry["scenario"].endswith("iso_table21_coupled")
            assert entry["fds_dir"].endswith("iso_table21_coupled/fds")

    run(go())


# --- #526: smoke on a fast fire run ---------------------------------------------

T_JUNCTION_FDS = Path(
    os.environ.get(
        "T_JUNCTION_FDS",
        Path.home()
        / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
        / "fds-evac-data"
        / "t_junction"
        / "fire_2MW_PVC",
    )
)


def test_tui_asks_for_a_frame_per_sim_second_and_every_grid():
    from pyfds_evac.tui.runner import FRAME_SIM_S, SMOKE_HZ, stream_options

    options = stream_options(True, 2.0)
    assert options["min_sim_s"] == FRAME_SIM_S == 1.0
    assert options["smoke_hz"] == SMOKE_HZ >= 100
    assert options["max_hz"] == 2.0


async def _real_fire_run(pilot, app, scenario: Path, fds: Path) -> None:
    await to_configure(pilot, app, scenario, fds)
    app.goto(3)
    await pilot.pause()
    await pilot.press("ctrl+r")
    await pilot.pause()
    if app.current_run is None:
        await pilot.press("r")
    for _ in range(3000):
        await asyncio.sleep(0.1)
        if app.current_run is not None and app.current_run.done:
            break
    await pilot.pause()
    assert app.current_run.result is not None, app.current_run.exited


def _plan_shows_smoke(app, sim_time: float) -> tuple[float, float, int]:
    """Scrub to *sim_time*; return (frame t, FDS frame t, smoke cells drawn)."""
    from pyfds_evac.tui.planview import PlanView

    run = app.current_run
    times = [f.sim_time for f, _ in run.frames]
    app.scrub_index = min(range(len(times)), key=lambda i: abs(times[i] - sim_time))
    app.refresh_plans()
    frame, grid = run.frames[app.scrub_index]
    view = app.query_one("#res-planview", PlanView)
    view.render()
    upper, lower = view._bins(view._raster)
    return frame.sim_time, grid.fds_time_s, int((upper > 0).sum() + (lower > 0).sum())


@pytest.mark.slow
@pytest.mark.external_data
@pytest.mark.skipif(not T_JUNCTION_FDS.is_dir(), reason="t_junction FDS output absent")
def test_fire_run_draws_smoke_and_replays_it(tmp_path):
    """t_junction + fire_2MW_PVC through the real child: smoke after 10 s."""
    work = tmp_path / "work"
    shutil.copytree(ASSETS / "t_junction", work / "assets" / "t_junction")
    (work / "fire").symlink_to(T_JUNCTION_FDS)

    async def go():
        app = EvacTui(cwd=work, inspector=lambda path: None, debounce=0)
        async with app.run_test(size=(120, 35)) as pilot:
            await _real_fire_run(
                pilot, app, work / "assets" / "t_junction", work / "fire"
            )
            frames = app.current_run.frames
            gaps = [
                b.sim_time - a.sim_time for (a, _), (b, _) in zip(frames, frames[1:])
            ]
            assert max(gaps) <= 1.0 + 0.1
            seen = []
            for t in (5.0, 30.0, 120.0):
                frame_t, fds_t, cells = _plan_shows_smoke(app, t)
                seen.append((frame_t, fds_t, cells))
            (t5, _f5, _c5), (t30, f30, c30), (t120, f120, c120) = seen
            assert abs(t30 - 30.0) <= 1.0 and f30 > 0 and c30 > 0, seen
            assert abs(t120 - 120.0) <= 1.0 and f120 > f30 and c120 >= c30, seen

    run(go())


@pytest.mark.slow
def test_coupled_run_sends_grids_after_the_first_fds_frame(tmp_path):
    """In-repo FDS output: frames every simulated second, grids at t > 0."""
    from pyfds_evac.tui.runner import ProcessRunner

    form = model.Form()
    form.scenario = model.read_scenario(ASSETS / "iso_table21_coupled")
    form.fds_dir = str(ASSETS / "iso_table21_coupled" / "fds")
    base = form.run_folder("GRID", tmp_path)
    got: list = []
    runner = ProcessRunner()
    runner.start(vars(form.namespace(form.output_paths(base))), base, got.append)
    assert runner.join(300)
    frames = [e for e in got if isinstance(e, events.FrameEvent)]
    gaps = [b.sim_time - a.sim_time for a, b in zip(frames, frames[1:-1])]
    assert frames and max(gaps) <= 1.0 + 0.1
    grids = [f.smoke for f in frames if f.smoke is not None]
    assert any(g.fds_time_s > 0 for g in grids)


@pytest.mark.slow
def test_child_output_goes_to_child_log_not_the_terminal(tmp_path, monkeypatch, capfd):
    """Debug lines and warnings of the run never reach the TUI's terminal (#519)."""
    from pyfds_evac.tui.runner import ProcessRunner

    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    form = model.Form()
    form.scenario = model.read_scenario(ASSETS / "iso_table21_coupled")
    form.fds_dir = str(ASSETS / "iso_table21_coupled" / "fds")
    base = form.run_folder("LOG", tmp_path)
    values = {**vars(form.namespace(form.output_paths(base))), "debug": True}
    got: list = []
    runner = ProcessRunner(frames=False)
    capfd.readouterr()
    runner.start(values, base, got.append)
    assert runner.join(300)
    assert isinstance(got[-1], events.ResultEvent), got[-3:]
    out, err = capfd.readouterr()
    assert (out, err) == ("", "")
    assert "Reroute debug" in (Path(base) / "child.log").read_text()


# --- #532 round trip of every setting ----------------------------------------------
# The same values as the GUI half (tests/_round_trip.py). Paths: the form ->
# Review "Save" (command.sh, run.py) and a run's frozen snapshot -> its
# command, run script and saved files. Values must be equal; the format may
# differ. Recent stays a scenario shortcut (#534), so it is not tested here.


def _rt_profile(workdir, index: int) -> tuple[dict, Path | None]:
    """Profile *index* and the FDS folder it needs (profile B reads FDS)."""
    from _round_trip import PROFILE_A, PROFILE_B

    if index == 0:
        return dict(PROFILE_A), None
    return dict(PROFILE_B), workdir / "assets" / "iso_table21_coupled" / "fds"


async def _rt_configure(pilot, app, workdir, index: int) -> dict:
    profile, fds = _rt_profile(workdir, index)
    await to_configure(pilot, app, workdir / "assets" / "t_junction", fds)
    for dest, value in profile.items():
        if value in ("on", "off"):
            app.form.switch[dest] = value == "on"
        else:
            app.form.text[dest] = value
        row(app, dest).sync_control()
    app.form_changed()
    await settle(pilot, app)
    assert app.invalid_count() == 0, app.parse_errors or app.cfg.errors
    return profile


def _rt_check_command(command: str, ns: argparse.Namespace) -> None:
    """*command* parses back to the values of *ns*."""
    from _round_trip import same_path

    from pyfds_evac.config.parameters import RUN_OPTIONS, parameter

    got = cli_options(command)
    for key in RUN_OPTIONS:
        want = getattr(ns, key)
        if parameter(key).kind == "text" and want is not None:
            assert same_path(got[key], want), key
        else:
            assert got[key] == want, key


def _rt_check_script(code: str, ns: argparse.Namespace, seed) -> None:
    """run.py's PATHS and OPTIONS against *ns*; *seed* is the one expected."""
    from _round_trip import PATHS, hidden, same_path, script_literals

    from pyfds_evac.config.parameters import default
    from pyfds_evac.config.script import _PATH_KEYS, OMITTED_OUTPUT_KEYS

    lit = script_literals(code)
    rebuilt = dict(lit["OPTIONS"])
    rebuilt.update({key: lit[key.upper()] for key in _PATH_KEYS})
    expected = vars(ns)
    assert set(rebuilt) == set(expected)
    got = rebuilt.pop("seed")
    assert got == seed and (got is None) == (seed is None)  # 0 is not None
    for key, value in rebuilt.items():
        if key in OMITTED_OUTPUT_KEYS:
            assert value is None, key
        elif key in (*PATHS, "scenario") and value is not None:
            assert same_path(value, expected[key]), key
        else:
            assert value == expected[key], key
    for key in hidden():
        assert rebuilt[key] == default(key), key


def test_rt_fields_cover_every_shown_option():
    from _round_trip import PROFILE_A, PROFILE_B, hidden, shown

    assert {p.dest for p in model.all_fields()} | {"fds_dir"} == shown()
    assert set(PROFILE_A) | set(PROFILE_B) | {"fds_dir"} == shown()
    assert model.UNSUPPORTED == hidden()


@pytest.mark.parametrize("index", [0, 1], ids=["profile_a", "profile_b"])
def test_rt_review_save_keeps_every_option(workdir, index):
    from _round_trip import ZERO, argv

    from pyfds_evac.config.parameters import default

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            profile = await _rt_configure(pilot, app, workdir, index)
            app.goto(3)
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            ns = app.namespace()
            # The form maps each value as pyfds-evac parses it.
            words = ["--scenario", "x", *argv(profile)]
            api = cli_options("pyfds-evac " + shlex.join(words))
            for key in profile:
                assert getattr(ns, key) == api[key] != default(key), key
            for key in set(ZERO) & set(profile):
                assert getattr(ns, key) is not None and getattr(ns, key) == 0
            folder = Path(app.planned())
            _rt_check_command((folder / "command.sh").read_text(), ns)
            _rt_check_script((folder / "run.py").read_text(), ns, ns.seed)

    run(go())


@pytest.mark.parametrize("confirmed", [True, False], ids=["confirmed", "other"])
@pytest.mark.parametrize("index", [0, 1], ids=["profile_a", "profile_b"])
def test_rt_run_snapshot_keeps_every_option(workdir, index, confirmed):
    async def go():
        runner = FakeRunner()
        app = make_app(workdir, runner=runner)
        async with app.run_test(size=(100, 30)) as pilot:
            await _rt_configure(pilot, app, workdir, index)
            app.goto(3)
            await pilot.pause()
            await pilot.press("ctrl+r")
            await pilot.pause()
            snap = app.current_run.snapshot
            values = copy.deepcopy(dict(snap.values))
            assert runner.started[0][0] == values
            # A later edit never reaches the snapshot.
            app.form.text["fic_alpha"] = "0.9"
            app.form.switch["smoke_blind"] = not app.form.switch["smoke_blind"]
            app.form_changed()
            await settle(pilot, app)
            assert dict(snap.values) == values
            _rt_check_command(snap.command, snap.namespace())
            reported = snap.expected_seed if confirmed else 99
            replay(app, result_event(events.STATUS_SUCCESS, seed=reported))
            await pilot.pause()
            # A blank Seed becomes the seed the run used; an explicit 0 stays.
            seed = values["seed"]
            if seed is None and confirmed:
                seed = reported
            _rt_check_script(app.run_script(), snap.namespace(), seed)
            app.action_save_run()
            folder = Path(snap.base)
            _rt_check_command((folder / "command.sh").read_text(), snap.namespace())
            _rt_check_script((folder / "run.py").read_text(), snap.namespace(), seed)

    run(go())


def test_rt_blank_paths_resolve_to_none(workdir):
    """A blank path field is None, never "" (#557 needs "")."""
    from _round_trip import PATHS, script_literals

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "t_junction", None)
            app.set_fds_dir("")
            app.form.text["replay_exits"] = "  "
            app.form.text["vis_cache"] = ""
            app.form_changed()
            await settle(pilot, app)
            ns = app.namespace()
            for key in PATHS:
                assert getattr(ns, key) is None, key
            app.goto(3)
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            folder = Path(app.planned())
            assert "--fds-dir" not in (folder / "command.sh").read_text()
            lit = script_literals((folder / "run.py").read_text())
            assert lit["FDS_DIR"] is None and lit["VIS_CACHE"] is None

    run(go())


def test_rt_script_resolves_replay_exits(tmp_path, monkeypatch):
    """run.py passes an absolute replay_exits to the run (#558)."""
    from _round_trip import script_literals

    from pyfds_evac.cli import _build_parser

    monkeypatch.chdir(tmp_path)
    argv = ["--scenario", "s", "--replay-exits", "x/exits.csv"]
    code = model.python_for(_build_parser().parse_args(argv), [], "out")
    lit = script_literals(code)
    assert lit["REPLAY_EXITS"] == str(tmp_path.resolve() / "x" / "exits.csv")
    assert "replay_exits" not in lit["OPTIONS"]
    assert "    replay_exits=REPLAY_EXITS," in code.splitlines()


def test_rt_script_does_not_name_the_gui(tmp_path):
    """A TUI-made run.py says nothing about the GUI (#576)."""
    from pyfds_evac.cli import _build_parser

    ns = _build_parser().parse_args(["--scenario", str(tmp_path)])
    assert "GUI" not in model.python_for(ns, ["Scenario: s"], "out")


@pytest.mark.xfail(strict=True, reason="#559: Save writes a stale command.sh")
def test_rt_save_right_after_an_edit_writes_the_edit(workdir):
    async def go():
        app = EvacTui(
            cwd=workdir,
            runner=FakeRunner(),
            inspector=lambda path: FACTS,
            debounce=30.0,
        )
        async with app.run_test(size=(100, 30)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "t_junction", None)
            app.config_now()
            app.goto(3)
            await pilot.pause()
            app.form.text["seed"] = "11"
            app.form_changed()  # the configuration is due in 30 s
            app.action_save()
            folder = Path(app.planned())
            assert cli_options((folder / "command.sh").read_text())["seed"] == 11

    run(go())


# --- #321: result labels -------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "width", "words", "never"),
    [
        # No dose model: the 0 the engine reports is not a measured zero.
        (
            result_event(events.STATUS_SUCCESS),
            120,
            "Evacuated 6 of 6 agents   Incapacitated: not modelled in this run",
            "Incapacitated 0",
        ),
        (
            result_event(events.STATUS_INCOMPLETE),
            120,
            "Evacuated 2 of 6 that entered   Incapacitated 1",
            "not modelled",
        ),
        # Below 100 columns the incapacitated figure has its own line.
        (
            result_event(events.STATUS_INCOMPLETE),
            80,
            "Evacuated 2 of 6 that entered\n  Incapacitated 1",
            "entered   Incapacitated",
        ),
    ],
)
def test_321_results_incapacitated_and_denominator(
    workdir, result, width, words, never
):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(width, 30)) as pilot:
            await _started(pilot, app, workdir)
            replay(app, result)
            await pilot.pause()
            text = text_of(app, "#res-outcome")
            assert words in text
            assert never not in text

    run(go())


@pytest.mark.parametrize(("modelled", "shown"), [(True, True), (False, False)])
def test_321_live_line_shows_incapacitated_only_when_modelled(workdir, modelled, shown):
    import dataclasses

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await _started(pilot, app, workdir)
            send = app.on_run_event
            send(dataclasses.replace(tiny_plan(), incapacitation_modelled=modelled))
            send(events.PhaseEvent(events.PHASE_RUNNING))
            send(Progress(1, 6, 10.0, 1.0, 16, 1, 0))
            await pilot.pause()
            app.render_run()
            await pilot.pause()
            text = text_of(app, "#run-status")
            assert "evacuated 1 of 6 planned" in text
            assert ("incapacitated 1" in text) is shown
            # The run never finishes here: stop the pending redraw so it
            # cannot fire while the app tears down.
            if app._render_timer is not None:
                app._render_timer.stop()
                app._render_timer = None

    run(go())


def test_321_cancel_before_the_first_sample_is_not_sim_zero(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await _started(pilot, app, workdir)
            app.on_run_event(result_event(events.STATUS_CANCELLED))
            await pilot.pause()
            text = text_of(app, "#res-outcome")
            assert "■ Cancelled before the first progress sample" in text
            assert "at sim 0.0 s" not in text

    run(go())


# --- #599: colour system notice --------------------------------------------------


def _colour_notices(workdir) -> list[str]:
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            return [n.message for n in app._notifications if "colours" in n.message]

    return run(go())


def test_599_256_colours_say_theme_is_approximate(workdir, monkeypatch):
    monkeypatch.delenv("COLORTERM")
    notices = _colour_notices(workdir)
    assert len(notices) == 1
    assert "shows 256 colours" in notices[0]
    assert "COLORTERM=truecolor" in notices[0]


def test_599_truecolor_shows_no_notice(workdir):
    assert _colour_notices(workdir) == []


def test_599_no_color_shows_no_notice(workdir, monkeypatch):
    monkeypatch.delenv("COLORTERM")
    monkeypatch.setenv("NO_COLOR", "1")
    assert _colour_notices(workdir) == []


# --- ctrl+n / ctrl+p next / previous step; ctrl+k palette ---------------------------


def test_ctrl_p_goes_back_one_step_and_names_it(workdir):
    from textual.screen import ModalScreen
    from textual.widgets._footer import FooterKey

    scenario = workdir / "assets" / "iso_table21_coupled"

    def back_label(app) -> str | None:
        for key in app.screen.query(FooterKey):
            if key.key == "ctrl+p":
                return key.description
        return None

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            assert back_label(app) is None
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert app.step == 0
            assert not isinstance(app.screen, ModalScreen)
            await to_configure(pilot, app, scenario, scenario / "fds")
            app.goto(3)
            await pilot.pause()
            for label, before in (("configure", 2), ("fds", 1), ("scenario", 0)):
                assert back_label(app) == label
                await pilot.press("ctrl+p")
                await pilot.pause()
                assert app.step == before

    run(go())


def test_ctrl_k_opens_the_command_palette(workdir):
    from textual.command import CommandPalette

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("ctrl+k")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)

    run(go())


def test_results_arrow_keys_replay_with_the_file_list_focused(workdir):
    """←/→ scrub the plan on Results, not the focused file list."""
    from textual.widgets._footer import FooterKey

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
            app.goto(3)
            await pilot.pause()
            await pilot.press("ctrl+r")
            await pilot.pause()
            replay(app, result_event(events.STATUS_SUCCESS))
            app.render_results()
            await pilot.pause()
            assert app.step == 5
            assert app.focused is app.query_one("#res-files")
            labels = {k.description: k.key_display for k in app.screen.query(FooterKey)}
            assert labels.get("replay") == "←/→"
            assert labels.get("fullscreen") == "v"
            await pilot.press("left")
            await pilot.pause()
            assert app.scrub_index == 0
            await pilot.press("right")
            await pilot.pause()
            assert app.scrub_index == 1

    run(go())


# --- Enter on an output file: preview, copy path, open ------------------------------


def test_file_preview_text_sqlite_and_folder(tmp_path):
    import sqlite3

    from pyfds_evac.tui.app import PREVIEW_LINES, file_preview

    csv = tmp_path / "a.csv"
    csv.write_text("".join(f"{i},x\n" for i in range(PREVIEW_LINES + 5)))
    text = file_preview(str(csv))
    assert text.splitlines()[0] == "0,x"
    assert text.splitlines()[-1] == f"… first {PREVIEW_LINES} lines shown"

    db = tmp_path / "run.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE frames (t REAL)")
        con.executemany("INSERT INTO frames VALUES (?)", [(1.0,), (2.0,)])
    assert file_preview(str(db)) == "SQLite database, 1 tables:\n  frames: 2 rows"

    folder = tmp_path / "bundle"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "b.txt").write_text("b")
    assert file_preview(str(folder)) == "Folder, 1 files:\nsub/b.txt"


def test_file_opener_is_off_over_ssh(monkeypatch):
    from pyfds_evac.tui.app import file_opener

    monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 5 6.7.8.9 22")
    assert file_opener() is None


def test_enter_on_an_output_file_opens_its_preview(workdir, tmp_path):
    from pyfds_evac.tui.widgets import FileScreen

    out = tmp_path / "exit_history.csv"
    out.write_text("time,exit\n79.2,jps-exits_0\n")

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
            app.goto(3)
            await pilot.pause()
            await pilot.press("ctrl+r")
            await pilot.pause()
            replay(app, result_event(events.STATUS_SUCCESS, files=[str(out)]))
            app.render_results()
            await pilot.pause()
            assert app.focused is app.query_one("#res-files")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, FileScreen)
            assert app.screen.path == str(out)
            assert "79.2,jps-exits_0" in app.screen.text
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, FileScreen)

    run(go())


# --- Configure: up/down between options, Enter flips a switch, click shows why ----


def test_configure_up_down_moves_between_options_and_enter_flips(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 40)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
            app.focus_field("constant_extinction")
            await pilot.pause()
            assert app.focused is row(app, "constant_extinction").control
            await pilot.press("down")
            await pilot.pause()
            # Without FDS output the option is inactive: the row takes focus.
            assert app.focused in (
                row(app, "smoke_update_interval"),
                row(app, "smoke_update_interval").control,
            )
            await pilot.press("up")
            await pilot.pause()
            assert app.focused is row(app, "constant_extinction").control
            app.focus_field("enable_rerouting")
            await pilot.pause()
            before = app.form.switch["enable_rerouting"]
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.switch["enable_rerouting"] is (not before)
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.switch["enable_rerouting"] is before

    run(go())


def test_click_on_an_inactive_switch_shows_why(workdir):
    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 40)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
            hold = row(app, "allow_fds_horizon_hold")
            assert hold.control.disabled
            await pilot.click(hold.control)
            await pilot.pause()
            assert app.focused is hold
            assert "inactive" in str(hold.query_one(".marker").render()) or hold.reason

    run(go())


def test_results_chart_label_spans_the_frames(workdir):
    """The evacuated chart covers the plan frames (to 20 s), not the 300 s limit."""

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await to_configure(pilot, app, workdir / "assets" / "ISO-table21", None)
            app.goto(3)
            await pilot.pause()
            await pilot.press("ctrl+r")
            await pilot.pause()
            replay(app, result_event(events.STATUS_SUCCESS))
            app.render_results()
            await pilot.pause()
            text = text_of(app, "#res-exits")
            assert "Evacuated over sim time, 0–20 s" in text
            assert "0–300 s" not in text

    run(go())


# --- FDS step: browse folders from the path box (dired-like) --------------------


def _fds_tree(root: Path) -> Path:
    """root/{alpha/, beta/case/run.smv, .hidden/}."""
    (root / "alpha").mkdir(parents=True)
    (root / "beta" / "case").mkdir(parents=True)
    (root / "beta" / "case" / "run.smv").write_text("")
    (root / ".hidden").mkdir()
    return root


def test_browse_dirs_lists_matching_folders_and_marks_fds_output(tmp_path):
    root = _fds_tree(tmp_path / "t")
    folder, found = model.browse_dirs(f"{root}/")
    assert folder == root
    assert [(p.name, smv) for p, smv in found] == [("alpha", False), ("beta", False)]
    _, found = model.browse_dirs(f"{root}/b")
    assert [p.name for p, _ in found] == ["beta"]
    _, found = model.browse_dirs(f"{root}/beta/")
    assert [(p.name, smv) for p, smv in found] == [("case", True)]
    _, found = model.browse_dirs(f"{root}/.")
    assert [p.name for p, _ in found] == [".hidden"]


def test_complete_dir_completes_like_a_shell(tmp_path):
    root = _fds_tree(tmp_path / "t")
    assert model.complete_dir(f"{root}/al") == f"{root}/alpha/"
    assert model.complete_dir(f"{root}/zz") == f"{root}/zz"
    (root / "alps").mkdir()
    assert model.complete_dir(f"{root}/a") == f"{root}/alp"


def test_fds_path_box_browses_and_enters_folders(workdir, tmp_path):
    root = _fds_tree(tmp_path / "t")

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            app.select_scenario(workdir / "assets" / "ISO-table21")
            await settle(pilot, app)
            app.goto(1)
            await settle(pilot, app)
            box = app.query_one("#fds-path")
            box.focus()
            box.value = f"{root}/b"
            await pilot.press("tab")
            await settle(pilot, app)
            assert box.value == f"{root}/beta/"
            await pilot.press("down")
            await settle(pilot, app)
            choices = app.query_one("#fds-choices")
            assert app.focused is choices
            ids = [
                choices.get_option_at_index(i).id for i in range(choices.option_count)
            ]
            assert ids[:2] == ["up", "dir-0"]
            choices.highlighted = 1
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.fds_dir == str((root / "beta" / "case").resolve())
            assert app.step == 2

    run(go())


def test_browse_scenarios_marks_scenarios(tmp_path):
    root = tmp_path / "s"
    (root / "case").mkdir(parents=True)
    (root / "case" / "config.json").write_text("{}")
    (root / "case" / "geometry.wkt").write_text("")
    (root / "other").mkdir()
    (root / "run.zip").write_text("")
    (root / "notes.txt").write_text("")
    folder, found = model.browse_scenarios(f"{root}/")
    assert folder == root
    assert [(p.name, s) for p, s in found] == [
        ("case", True),
        ("other", False),
        ("run.zip", True),
    ]
    assert model.complete_scenario(f"{root}/ru") == f"{root}/run.zip"


def test_open_file_browses_to_a_scenario(workdir):
    assets = workdir / "assets"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            app.query_one("#sc-tabs").active = "tab-open"
            await settle(pilot, app)
            listing = app.query_one("#open-list")
            ids = [
                listing.get_option_at_index(i).id for i in range(listing.option_count)
            ]
            names = [p.name for p, _ in app.open_found]
            assert app.open_folder == workdir and "assets" in names
            listing.focus()
            listing.highlighted = ids.index(f"e-{names.index('assets')}")
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.query_one("#open-path").value == f"{assets}{os.sep}"
            names = [p.name for p, _ in app.open_found]
            assert app.open_folder == assets and "ISO-table21" in names
            i = names.index("ISO-table21")
            assert app.open_found[i][1]  # marked as a scenario
            ids = [
                listing.get_option_at_index(k).id for k in range(listing.option_count)
            ]
            listing.highlighted = ids.index(f"e-{i}")
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.scenario is not None
            assert app.form.scenario.path == (assets / "ISO-table21").resolve()
            assert app.step == 1

    run(go())


def test_match_rank_is_fzf_like():
    assert model.match_rank("fic", "fic_vs_fed_speed") == 0
    assert model.match_rank("vs", "fic_vs_fed_speed") == 1
    assert model.match_rank("fvs", "fic_vs_fed_speed") == 2
    assert model.match_rank("zz", "fic_vs_fed_speed") is None


def test_typing_in_the_browse_list_narrows_it(workdir):
    assets = workdir / "assets"

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            app.query_one("#sc-tabs").active = "tab-open"
            box = app.query_one("#open-path")
            box.value = f"{assets}{os.sep}"
            await settle(pilot, app)
            listing = app.query_one("#open-list")
            listing.focus()
            before = len(app.open_found)
            for key in "iso21":
                await pilot.press(key)
            await settle(pilot, app)
            assert app.focused is listing
            assert box.value == f"{assets}{os.sep}iso21"
            names = [p.name for p, _ in app.open_found]
            assert names and len(names) < before
            assert all(model.match_rank("iso21", n) is not None for n in names)
            # Enter picks the best match, not "..".
            highlighted = listing.get_option_at_index(listing.highlighted).id
            assert highlighted == "e-0"
            await pilot.press("backspace")
            await settle(pilot, app)
            assert box.value == f"{assets}{os.sep}iso2"

    run(go())


def test_tab_in_the_fds_list_completes_the_path(workdir, tmp_path):
    root = _fds_tree(tmp_path / "t")

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            app.select_scenario(workdir / "assets" / "ISO-table21")
            await settle(pilot, app)
            assert app.step == 1
            choices = app.query_one("#fds-choices")
            assert app.focused is choices  # the step opens on the list
            box = app.query_one("#fds-path")
            box.value = f"{root}/b"
            await settle(pilot, app)
            await pilot.press("tab")
            await settle(pilot, app)
            assert box.value == f"{root}/beta/"
            assert app.focused is choices

    run(go())


def test_review_offers_the_way_back_to_a_running_run(workdir):
    from textual.widgets._footer import FooterKey

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            await _started(pilot, app, workdir)
            app.goto(3)
            await pilot.pause()
            labels = [k.description for k in app.screen.query(FooterKey)]
            assert "back to run" in labels
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert app.step == 4

    run(go())


def test_enter_after_tab_chooses_an_fds_folder_with_subfolders(workdir, tmp_path):
    """A trailing / (what Tab leaves) keeps "Use this folder" highlighted."""
    root = _fds_tree(tmp_path / "t")
    case = root / "beta" / "case"
    (case / "sub").mkdir()

    async def go():
        app = make_app(workdir)
        async with app.run_test(size=(120, 35)) as pilot:
            app.select_scenario(workdir / "assets" / "ISO-table21")
            await settle(pilot, app)
            box = app.query_one("#fds-path")
            box.value = f"{case}{os.sep}"
            await settle(pilot, app)
            choices = app.query_one("#fds-choices")
            choices.focus()
            assert choices.get_option_at_index(choices.highlighted).id == "use"
            await pilot.press("enter")
            await settle(pilot, app)
            assert app.form.fds_dir == str(case.resolve())

    run(go())
