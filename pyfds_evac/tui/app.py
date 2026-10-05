"""The terminal UI: Scenario → FDS → Configure → Review → Run → Results.

Interaction: ``studies/tui_interaction_spec.md``; look:
``studies/tui_visual_design.md``. Every name, default, unit, rule and
message comes from :mod:`pyfds_evac.config`; the run is
``core.run_stream`` in a child process (:mod:`.runner`).

Seams for tests (#485 R9): ``runner`` (an object with ``start(values,
folder, post)``, ``cancel()``, ``stop()`` and ``running``) and
``inspector`` (a callable that turns an FDS folder into ``FdsFacts``).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
import shutil
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Collapsible,
    ContentSwitcher,
    Input,
    OptionList,
    RichLog,
    Select,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual.widgets.option_list import Option

from pyfds_evac.config import events, frontend
from pyfds_evac.config.parameters import GROUP_FDS, GROUP_HEAT, GROUP_OUTPUTS, GROUP_RUN

from . import model
from .planview import PlanView, legend, scrubber
from .runner import (
    ChildExited,
    ProcessRunner,
    Progress,
    Stopping,
    inspect_fds,
    prepare_processes,
)
from .theme import EVAC_DARK, THEME_NAMES
from .widgets import (
    STEP_TITLES,
    BrowseList,
    ConfirmScreen,
    EvacFooter,
    FieldRow,
    FileScreen,
    FindScreen,
    PathBox,
    ScrollText,
    StepBar,
    TextBox,
    TextScreen,
    TooSmall,
    m,
)

RECENT_GLYPHS = {
    "complete": "✓ ",
    "incomplete": "◐ ",
    "failed": "✗ ",
    "cancelled": "■ ",
}
STEPS = ("scenario", "fds", "configure", "review", "run", "results")
# Rich colour systems below truecolor, with the number of colours they show.
COLOR_SYSTEM_COLOURS = {"256": "256", "standard": "16", "windows": "16"}
MIN_SIZE = (80, 24)
SECTION_LEAD = {GROUP_HEAT: "enable_heat_fed"}
PHASE_WORDS = {
    events.PHASE_INITIALISING: "initialising",
    events.PHASE_FDS_INSPECTION: "FDS inspection",
    events.PHASE_VISIBILITY: "visibility",
    events.PHASE_RUNNING: "running",
    events.PHASE_WRITING_OUTPUTS: "writing outputs",
    events.PHASE_DONE: "done",
}


def _short(path: Any, width: int = 40) -> str:
    """*path* shortened in the middle: ``…/assets/t_junction/fds``."""
    text = str(path)
    if len(text) <= width:
        return text
    parts = Path(text).parts
    tail = ""
    for part in reversed(parts):
        candidate = f"/{part}{tail}"
        if len(candidate) + 1 > width:
            break
        tail = candidate
    return f"…{tail}" if tail else f"…{text[-(width - 1) :]}"


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _bar(fraction: float, width: int) -> Content:
    n = max(0, min(width, int(round(fraction * width))))
    return m("[$primary]$a[/][$text-muted]$b[/]", a="█" * n, b="░" * (width - n))


@dataclass
class RunState:
    """Everything the TUI received from one run."""

    snapshot: model.RunSnapshot
    started: float = field(default_factory=time.monotonic)
    phase: str | None = None
    phase_detail: str = ""
    progress: Progress | None = None
    plan: events.PlanEvent | None = None
    frames: list[tuple[events.FrameEvent, events.SmokeGrid | None]] = field(
        default_factory=list
    )
    smoke: events.SmokeGrid | None = None
    warnings: list[events.WarningEvent] = field(default_factory=list)
    result: events.ResultEvent | None = None
    exited: ChildExited | None = None
    cancelling: bool = False
    stopping: str | None = None
    ended: float | None = None
    output_folder: str = ""

    @property
    def done(self) -> bool:
        return self.result is not None or self.exited is not None

    @property
    def wall(self) -> float:
        return (self.ended or time.monotonic()) - self.started

    @property
    def status(self) -> str:
        """``running``, or how the run ended (``success`` … ``died``)."""
        if self.result is not None:
            return self.result.status
        if self.exited is not None:
            return events.STATUS_CANCELLED if self.exited.stopped else "died"
        return "running"


# --- steps ---------------------------------------------------------------------


class Step(Vertical):
    """A step of the flow; :meth:`enter` runs when it becomes current."""

    @property
    def tui(self) -> EvacTui:
        return cast("EvacTui", self.app)

    def enter(self) -> None:
        """Focus the step's first control."""


class ScenarioStep(Step):
    BINDINGS = [Binding("ctrl+n", "app.next_step", "next")]

    def compose(self) -> ComposeResult:
        with TabbedContent(id="sc-tabs"):
            with TabPane("Recent", id="tab-recent"):
                yield OptionList(id="recent")
            with TabPane("Examples", id="tab-examples"):
                yield TextBox(placeholder="type to filter", id="ex-filter")
                yield OptionList(id="examples")
            with TabPane("Open file", id="tab-open"):
                yield PathBox(
                    placeholder="path to a .json, .zip or folder (Tab completes, "
                    "~ is home)",
                    id="open-path",
                )
                yield BrowseList("#open-path", id="open-list")
        yield Static(id="sc-info")
        yield Static(id="sc-error")

    def enter(self) -> None:
        tab = self.query_one("#sc-tabs", TabbedContent).active
        focus = {"tab-recent": "#recent", "tab-examples": "#ex-filter"}
        self.query_one(focus.get(tab, "#open-path")).focus()


class FdsStep(Step):
    BINDINGS = [
        Binding("ctrl+n", "app.next_step", "next"),
        Binding("ctrl+p", "app.step_back", "scenario"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(m("[b]FDS output folder[/]"))
        yield PathBox(
            placeholder="folder that holds the .smv file (Tab completes, ~ is home)",
            id="fds-path",
        )
        yield BrowseList("#fds-path", id="fds-choices")
        yield Static(id="fds-panel")

    def enter(self) -> None:
        self.query_one("#fds-choices").focus()


class ConfigureStep(Step):
    BINDINGS = [
        Binding("ctrl+n", "app.next_step", "review"),
        Binding("ctrl+p", "app.step_back", "fds"),
        Binding("ctrl+f", "app.find", "find"),
        # Up/down move between the options, also out of a text box or a
        # closed dropdown (which would otherwise open on them).
        Binding("down", "app.move_field(1)", "next option", show=False, priority=True),
        Binding(
            "up", "app.move_field(-1)", "previous option", show=False, priority=True
        ),
    ]

    def compose(self) -> ComposeResult:
        form = self.tui.form
        with VerticalScroll(id="cfg-scroll"):
            for index, section in enumerate(model.SECTIONS):
                params = model.fields(section)
                with Collapsible(title=section, collapsed=index > 1, id=f"sec-{index}"):
                    if section == GROUP_RUN:
                        yield from self._run_rows()
                    if section == GROUP_FDS:
                        yield Static(id="cfg-fds")
                    if section == GROUP_OUTPUTS:
                        yield Static(id="cfg-outputs")
                    common = [p for p in params if p.tier == "common"]
                    advanced = [p for p in params if p.tier != "common"]
                    for p in common:
                        yield FieldRow(p, form)
                    if advanced:
                        with Collapsible(
                            title=f"Advanced ({len(advanced)})",
                            collapsed=True,
                            id=f"adv-{index}",
                        ):
                            for p in advanced:
                                yield FieldRow(p, form)

    def _run_rows(self) -> Iterable[Any]:
        with Horizontal(classes="plain-row"):
            yield Static("Output folder", classes="label")
            yield TextBox(
                self.tui.form.output_folder,
                placeholder="derived (results/<scenario>/…)",
                id="output-folder",
                compact=True,
            )
        yield Static(id="output-preview", classes="help-line")

    def enter(self) -> None:
        first = self.query("FieldRow Input, FieldRow Switch").first()
        first.focus()


class ReviewStep(Step):
    BINDINGS = [
        Binding("ctrl+r", "app.run", "run"),
        Binding("ctrl+p", "app.step_back", "configure"),
        # Shown only while a run is in progress: the way back to it.
        Binding("ctrl+n", "app.to_run", "back to run"),
        Binding("c", "app.copy_command", "copy"),
        Binding("s", "app.save", "save"),
        Binding("p", "app.show_python", "python"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="rv-outcome")
        yield OptionList(id="rv-errors")
        yield ScrollText(id="rv-body")
        yield Static(m("[b]Command[/]"))
        yield TextArea("", read_only=True, soft_wrap=True, id="rv-command")

    def enter(self) -> None:
        errors = self.query_one("#rv-errors", OptionList)
        (errors if errors.option_count else self.query_one("#rv-body")).focus()


class RunStep(Step):
    BINDINGS = [
        Binding("x", "app.cancel", "cancel"),
        Binding("ctrl+p", "app.step_back", "review"),
        Binding("ctrl+c", "app.cancel", "cancel", show=False, priority=True),
        Binding("v", "app.plan", "fullscreen"),
        Binding("w", "app.warnings", "warnings"),
        Binding("l", "app.log", "log"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="run-status")
        with Horizontal(id="run-body"):
            with Vertical(id="run-plan"):
                yield PlanView(id="run-planview")
                yield Static(id="run-scrubber")
                yield Static(id="run-legend")
            with Vertical(id="run-side"):
                yield Static(id="run-bars")
                yield Sparkline([0], id="run-spark")
        yield Static(id="run-note")
        yield RichLog(id="run-log", markup=False, wrap=True, max_lines=2000)

    def enter(self) -> None:
        self.query_one("#run-log").focus()


class ResultsStep(Step):
    BINDINGS = [
        Binding("ctrl+r", "app.run", "run again"),
        Binding("ctrl+p", "app.step_back", "configure"),
        # One footer entry for the four replay keys. Priority, so the focused
        # file list does not take ←/→ for scrolling.
        Binding("left", "app.scrub(-1)", "replay", key_display="←/→", priority=True),
        Binding("e", "app.change_settings", "change"),
        Binding("n", "app.new_scenario", "new"),
        Binding("c", "app.run_command", "command"),
        Binding("s", "app.save_run", "save"),
        Binding("w", "app.warnings", "warnings", show=False),
        Binding("t", "app.traceback", "traceback", show=False),
        Binding("v", "app.plan", "fullscreen"),
        Binding("right", "app.scrub(1)", "+1 s", show=False, priority=True),
        Binding("shift+left", "app.scrub(-10)", "−10 s", show=False, priority=True),
        Binding("shift+right", "app.scrub(10)", "+10 s", show=False, priority=True),
        Binding("y", "app.copy_path", "copy path", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="res-banner")
        yield Static(id="res-outcome")
        with Horizontal(id="res-body"):
            with Vertical(id="res-plan"):
                yield PlanView(id="res-planview")
                yield Static(id="res-scrubber")
                yield Static(id="res-legend")
            with Vertical(id="res-side"):
                yield Static(id="res-exits")
                yield Sparkline([0], id="res-spark")
        yield Static(m("[b]Output files[/]"), id="res-files-title")
        yield OptionList(id="res-files")

    def enter(self) -> None:
        self.query_one("#res-files").focus()


class PlanScreen(Screen[None]):
    """The plan view full screen (``v``)."""

    BINDINGS = [
        Binding("escape", "close", "back"),
        Binding("left", "app.scrub(-1)", "−1 s"),
        Binding("right", "app.scrub(1)", "+1 s"),
        Binding("shift+left", "app.scrub(-10)", "−10 s", show=False),
        Binding("shift+right", "app.scrub(10)", "+10 s", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="full-head")
        yield PlanView(id="full-planview")
        yield Static(id="full-scrubber")
        yield Static(id="full-legend")
        yield EvacFooter()

    def on_mount(self) -> None:
        cast("EvacTui", self.app).refresh_plans()

    def action_close(self) -> None:
        self.app.pop_screen()


# --- the app -------------------------------------------------------------------


class EvacTui(App[None]):
    """``pyfds-evac-tui``."""

    TITLE = "pyFDS-Evac"
    ENABLE_COMMAND_PALETTE = True
    # ``ctrl+p`` is "previous step", paired with ``ctrl+n``.
    COMMAND_PALETTE_BINDING = "ctrl+k"
    CSS = """
    Screen { layout: vertical; }
    #stepbar { height: 1; background: $panel; padding: 0 1; }
    #steps { height: 1fr; }
    #summary { height: 1; padding: 0 1; background: $surface; }
    Step { height: 1fr; }
    #sc-tabs { height: 1fr; }
    #sc-info, #sc-error { height: auto; padding: 0 1; }
    #sc-error { color: $error; }
    #examples, #recent { height: 1fr; }
    #open-list { height: 1fr; }
    #fds-choices { height: auto; max-height: 10; }
    #fds-panel { height: auto; padding: 0 1; }
    .plain-row { height: auto; padding: 0 0 0 1; }
    .plain-row .label { width: 30; padding: 0 1 0 0; }
    .plain-row Input { width: 1fr; }
    .help-line { color: $text-muted; padding: 0 0 0 2; height: auto; }
    #cfg-fds, #cfg-outputs { height: auto; padding: 0 0 0 1; }
    Collapsible { padding: 0; border-top: none; }
    Collapsible > Contents { padding: 0 0 0 1; }
    #rv-outcome { height: auto; padding: 0 1; }
    #rv-errors { height: auto; max-height: 6; }
    #rv-command { height: 5; }
    #run-status { height: 3; padding: 0 1; }
    #run-body { height: auto; }
    #run-plan { width: 1fr; display: none; }
    #run-side { width: 1fr; height: auto; padding: 0 1; }
    #run-spark { height: 2; display: none; }
    #run-note { height: auto; padding: 0 1; }
    #run-log { height: 1fr; border-top: solid $secondary 40%; }
    EvacTui.-wide #run-plan { display: block; height: 100%; }
    EvacTui.-wide #run-log { height: 8; }
    EvacTui.-wide #run-side { width: 38; }
    EvacTui.-wide #run-spark { display: block; }
    EvacTui.-wide #run-body { height: 1fr; }
    #res-banner { height: auto; padding: 0 1; color: $warning; }
    #res-outcome { height: auto; padding: 0 1; }
    #res-body { height: auto; }
    #res-plan { width: 1fr; display: none; }
    #res-side { width: 1fr; height: auto; padding: 0 1; }
    #res-spark { height: 2; }
    #res-files { height: 1fr; min-height: 3; }
    EvacTui.-wide #res-plan { display: block; height: 16; }
    EvacTui.-wide #res-side { width: 38; }
    #run-scrubber, #res-scrubber, #full-scrubber { height: 1; }
    #run-legend { height: 2; }
    #res-legend, #full-legend { height: auto; max-height: 3; }
    #full-head { height: 1; background: $panel; padding: 0 1; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "quit", priority=True, show=False),
        Binding("ctrl+r", "run", "run", show=False),
        # ``ctrl+p`` on each step is the advertised way back; Esc stays as a
        # fallback (tmux's escape-time can delay it).
        Binding("escape", "step_back", "back", show=False),
        # Priority, so ``?`` opens the keys also from a text box (#598);
        # the footer shows both quit and ``?`` on its own (EvacFooter).
        Binding("question_mark", "field_help", "keys", priority=True, show=False),
        Binding("f1", "field_help", "help", show=False),
    ]

    def __init__(
        self,
        *,
        theme: str | None = None,
        cwd: Path | None = None,
        runner: Any = None,
        inspector: Callable[[str], Any] | None = None,
        recent: model.Recent | None = None,
        debounce: float = 0.15,
    ) -> None:
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self.form = model.Form()
        self.recent = recent if recent is not None else model.Recent()
        self.runner = runner if runner is not None else ProcessRunner()
        self.inspector = inspector or inspect_fds
        self.debounce = debounce
        self.start_theme = theme or self.recent.theme or model.DEFAULT_THEME
        self.step = 0
        self.visited = {0}
        self.facts: Any = None
        self.facts_for: str | None = None
        self.facts_error: str | None = None
        self.inspecting = False
        self.cfg: Any = None
        self.appl: dict[str, Any] = {}
        self.mech: Any = None
        self.parse_errors: dict[str, str] = {}
        self.planned_base: str | None = None
        self.run_count = 0
        self.current_run: RunState | None = None
        self.scrub_index: int | None = None
        self.examples: list[model.Example] | None = None
        self.suggestions: list[Path] = []
        # The folder the FDS path box browses, and its listed subfolders.
        self.browse_folder: Path | None = None
        self.browsed: list[tuple[Path, bool]] = []
        # The same for the Open file box of the Scenario step.
        self.open_folder: Path | None = None
        self.open_found: list[tuple[Path, bool]] = []
        self._gen = 0
        self._cfg_timer: Any = None
        self.warned_confirmed = False
        self._ui_loop: asyncio.AbstractEventLoop | None = None
        self._ui_context = contextvars.copy_context()
        self._render_timer: Any = None
        self._quitting = False
        super().__init__()

    # --- set-up --------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield StepBar(id="stepbar")
        with ContentSwitcher(initial="step-scenario", id="steps"):
            yield ScenarioStep(id="step-scenario")
            yield FdsStep(id="step-fds")
            yield ConfigureStep(id="step-configure")
            yield ReviewStep(id="step-review")
            yield RunStep(id="step-run")
            yield ResultsStep(id="step-results")
        yield Static(id="summary")
        yield EvacFooter()

    def on_mount(self) -> None:
        self._ui_loop = asyncio.get_running_loop()
        # Textual's context (the active app), for callbacks from the reader.
        self._ui_context = contextvars.copy_context()
        self.register_theme(EVAC_DARK)
        self.theme = self.start_theme
        self._fill_recent()
        self._fill_examples("")
        self._browse_open(f"{self.cwd}{os.sep}")
        tabs = self.query_one("#sc-tabs", TabbedContent)
        if self.recent.runs:
            tabs.active = "tab-recent"
            self.query_one("#recent").focus()
        else:
            tabs.active = "tab-examples" if self.examples is not None else "tab-open"
            focus = "#ex-filter" if self.examples is not None else "#open-path"
            self.query_one(focus).focus()
        self.update_chrome()
        self._check_size()
        self._warn_color_system()

    def _warn_color_system(self) -> None:
        """Say when the terminal shows fewer colours than the theme needs (#599)."""
        colours = COLOR_SYSTEM_COLOURS.get(str(self.console.color_system))
        if self.no_color or colours is None:
            return
        self.notify(
            f"This terminal shows {colours} colours, so the theme colours are "
            "approximate. If it supports truecolor, set COLORTERM=truecolor "
            '(in tmux, enable RGB); see "Colours" on the Terminal UI docs page.',
            timeout=15,
            markup=False,
        )

    def on_unmount(self) -> None:
        """Let the reader thread remove the run's temporary folder."""
        self._quitting = True  # the screens are gone; drop late events
        if self._render_timer is not None:
            self._render_timer.stop()
        if self._cfg_timer is not None:
            self._cfg_timer.stop()
        self._render_timer = self._cfg_timer = None
        join = getattr(self.runner, "join", None)
        if join is not None:
            join(10.0)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        for command in super().get_system_commands(screen):
            if command.title != "Theme":
                yield command
        for name, title in THEME_NAMES.items():
            yield SystemCommand(
                f"Theme: {title}",
                f"Switch to the {title} theme",
                lambda n=name: self.set_theme(n),
            )
        for i, title in enumerate(STEP_TITLES):
            yield SystemCommand(
                f"Go to step {i + 1}: {title}", "", lambda i=i: self.goto(i)
            )
        yield SystemCommand(
            "Inspect FDS folder", "Read the .smv again", self.inspect_fds
        )
        yield SystemCommand(
            "Copy command",
            "The equivalent pyfds-evac command",
            self.action_copy_command,
        )
        yield SystemCommand(
            "Save command and script", "command.sh and run.py", self.action_save
        )
        yield SystemCommand(
            "Show Python", "The equivalent Python script", self.action_show_python
        )
        yield SystemCommand(
            "Reset all settings", "Back to the defaults (asks first)", self.reset_all
        )
        yield SystemCommand("Toggle advanced in all sections", "", self.toggle_advanced)
        yield SystemCommand("Open docs page", model.TUI_DOCS, self.show_docs)

    def set_theme(self, name: str) -> None:
        self.theme = name
        self.recent.set_theme(name)
        self.refresh_plans()

    def on_resize(self, event: Any) -> None:
        self._check_size(event.size)

    def _check_size(self, size: Any = None) -> None:
        w, h = size or self.size
        self.set_class(w >= 120 and h >= 35, "-wide")
        small = w < MIN_SIZE[0] or h < MIN_SIZE[1]
        notice = self.screen if isinstance(self.screen, TooSmall) else None
        if small and notice is None:
            screen = TooSmall()
            self.push_screen(screen)
            self.call_after_refresh(screen.show, w, h)
        elif small and notice is not None:
            notice.show(w, h)
        elif not small and notice is not None:
            self.pop_screen()
        self.update_chrome()

    # --- navigation ------------------------------------------------------------

    def goto(self, index: int) -> None:
        if index == 4 and self.current_run is None:
            self.notify("No run yet: Review → ctrl+r starts one.")
            return
        if index == 5 and (self.current_run is None or not self.current_run.done):
            self.notify("No finished run yet.")
            return
        self.step = index
        self.visited.add(index)
        self.query_one("#steps", ContentSwitcher).current = f"step-{STEPS[index]}"
        if index == 3:
            self.render_review()
        if index == 5:
            self.render_results()
        self.update_chrome()
        self.query_one(f"#step-{STEPS[index]}", Step).enter()

    def action_next_step(self) -> None:
        if self.step == 0:
            self._accept_scenario_tab()
            return
        if self.step == 1:
            self._accept_fds_choice()
            return
        if self.step < 3:
            self.goto(self.step + 1)
        elif self.step == 2:
            self.goto(3)

    def action_to_run(self) -> None:
        self.goto(4)

    def action_step_back(self) -> None:
        if self.step in (1, 2, 3):
            self.goto(self.step - 1)
        elif self.step == 4:
            self.goto(3)
        elif self.step == 5:
            self.goto(2)

    def action_change_settings(self) -> None:
        self.goto(2)

    def action_new_scenario(self) -> None:
        self.goto(0)

    def action_move_field(self, delta: int) -> None:
        if delta > 0:
            self.screen.focus_next()
        else:
            self.screen.focus_previous()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "move_field":
            # An open dropdown keeps up/down for its own list.
            return not any(s.expanded for s in self.screen.query(Select))
        if action == "run":
            return self.step in (2, 3, 5)
        if action == "to_run":
            return self.current_run is not None and not self.current_run.done
        if action == "field_help":
            # In a dialog, ``?`` and F1 go to the dialog (the find box types it).
            return not isinstance(self.screen, ModalScreen)
        return True

    # --- scenario step ---------------------------------------------------------

    def _fill_recent(self) -> None:
        recent = self.query_one("#recent", OptionList)
        recent.clear_options()
        for i, entry in enumerate(self.recent.runs):
            path = Path(str(entry.get("scenario")))
            fds = entry.get("fds_dir")
            missing = not path.exists() or (fds and not Path(fds).exists())
            line = m(
                "$n  [dim]$f[/]  $s  [dim]$d$x[/]",
                n=model.scenario_name(path) if path.exists() else path.name,
                f=_short(fds or "no FDS", 30),
                s=RECENT_GLYPHS.get(str(entry.get("status")), "")
                + str(entry.get("status", "")),
                d=str(entry.get("date", ""))[:16],
                x="  missing" if missing else "",
            )
            recent.add_option(Option(line, id=f"recent-{i}"))
        if recent.option_count:
            recent.highlighted = 0

    def _fill_examples(self, query: str) -> None:
        if self.examples is None:
            self.examples = model.list_examples(self.cwd)
        options = self.query_one("#examples", OptionList)
        options.clear_options()
        if self.examples is None:
            options.add_option(
                Option(
                    m(
                        "No assets/ folder here. Start the TUI in a folder that holds "
                        "one, for example an unpacked example zip from the docs:\n$u",
                        u=model.DOCS_URL,
                    ),
                    disabled=True,
                )
            )
            return
        q = query.strip().lower()
        for i, ex in enumerate(self.examples):
            if q and q not in f"{ex.variant_of or ''}/{ex.label}".lower():
                continue
            name = f"  ├ {ex.label}" if ex.variant_of else ex.label
            marker = ex.fds_marker
            colour = "$success" if ex.fds == "output" else "$text-muted"
            text = m(
                f"$n  [{colour}]$k[/]" + ("\n    [dim]$r[/]" if ex.readme else ""),
                n=name,
                k=marker,
                r=ex.readme[:70],
            )
            options.add_option(Option(text, id=f"ex-{i}"))
        if options.option_count:
            options.highlighted = 0

    @on(Input.Changed, "#ex-filter")
    def _filter(self, event: Input.Changed) -> None:
        self._fill_examples(event.value)

    @on(Input.Submitted, "#ex-filter")
    def _filter_enter(self) -> None:
        options = self.query_one("#examples", OptionList)
        if options.option_count and options.highlighted is not None:
            self._select_example(options.get_option_at_index(options.highlighted).id)

    def on_key(self, event: Any) -> None:
        if event.key == "down" and self.focused is self.query_one("#ex-filter"):
            self.query_one("#examples").focus()
            event.stop()

    @on(OptionList.OptionHighlighted, "#examples")
    def _example_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            examples = self.examples or []
            self._show_info(examples[int(event.option.id[3:])].path)

    @on(OptionList.OptionSelected, "#examples")
    def _example_selected(self, event: OptionList.OptionSelected) -> None:
        self._select_example(event.option.id)

    def _select_example(self, ident: str | None) -> None:
        if not ident or self.examples is None:
            return
        self.select_scenario(self.examples[int(ident[3:])].path)

    @on(OptionList.OptionSelected, "#recent")
    def _recent_selected(self, event: OptionList.OptionSelected) -> None:
        entry = self.recent.runs[int(str(event.option.id)[7:])]
        fds = entry.get("fds_dir")
        if fds and not Path(fds).is_dir():
            self._scenario_error(f"FDS folder missing: {fds}", "")
            return
        if self.select_scenario(Path(str(entry.get("scenario"))), advance=False):
            self.set_fds_dir(fds or None)
            self.goto(3)

    @on(Input.Submitted, "#open-path")
    def _open_path(self, event: Input.Submitted) -> None:
        self.select_scenario(Path(event.value))

    # --- browsing scenarios from the Open file box (dired-like) -----------------

    @on(Input.Changed, "#open-path")
    def _open_path_changed(self, event: Input.Changed) -> None:
        self._browse_open(event.value or f"{self.cwd}{os.sep}")

    @work(thread=True, exclusive=True, group="browse-open")
    def _browse_open(self, text: str) -> None:
        folder, found = model.browse_scenarios(text)
        self.call_from_thread(self._show_open, text, folder, found)

    def _show_open(
        self, text: str, folder: Path | None, found: list[tuple[Path, bool]]
    ) -> None:
        typed = self.query_one("#open-path", Input).value
        if text != (typed or f"{self.cwd}{os.sep}") or folder is None:
            return
        self.open_folder, self.open_found = folder, found
        listing = self.query_one("#open-list", OptionList)
        listing.clear_options()
        if folder.parent != folder:
            listing.add_option(
                Option(m("..  [dim]up to $p[/]", p=_short(folder.parent, 60)), id="up")
            )
        for i, (path, scenario) in enumerate(found):
            name = path.name + (os.sep if path.is_dir() else "")
            tag = "  [$success]scenario[/]" if scenario else ""
            listing.add_option(Option(m(f"$n{tag}", n=name), id=f"e-{i}"))
        if not found:
            listing.add_option(
                Option(
                    m(
                        "[dim]No folder, .json or .zip here: $p[/]",
                        p=_short(folder, 60),
                    ),
                    disabled=True,
                )
            )
        listing.highlighted = _first_entry(listing, "e-", text)

    @on(OptionList.OptionSelected, "#open-list")
    def _open_choice(self, event: OptionList.OptionSelected) -> None:
        folder, ident = self.open_folder, event.option.id or ""
        if folder is None:
            return
        if ident == "up":
            self._go_into(folder.parent, "#open-path")
            return
        path, scenario = self.open_found[int(ident[2:])]
        if scenario:
            self.select_scenario(path)
        else:
            self._go_into(path, "#open-path")

    def _accept_scenario_tab(self) -> None:
        tab = self.query_one("#sc-tabs", TabbedContent).active
        if tab == "tab-open":
            self.select_scenario(Path(self.query_one("#open-path", Input).value))
        elif tab == "tab-examples":
            self._filter_enter()
        elif self.form.scenario is not None:
            self.goto(1)

    def _show_info(self, path: Path) -> None:
        try:
            info = model.read_scenario(path)
        except model.ScenarioError as exc:
            self.query_one("#sc-info", Static).update(m("[$error]$e[/]", e=exc.message))
            return
        agents = "?" if info.agents is None else info.agents
        self.query_one("#sc-info", Static).update(
            m(
                "[b]$n[/]  [dim]$k[/]\n  agents $a   exits $x   max time $t s   seed $s",
                n=info.name,
                k=info.kind,
                a=agents,
                x=info.exits,
                t=f"{info.max_time:g}",
                s=info.seed,
            )
        )

    def _scenario_error(self, message: str, details: str) -> None:
        text = m("[b]$e[/]", e=message)
        if details:
            text = Content.assemble(
                text, m("\n[dim]Technical details: $d[/]", d=details)
            )
        self.query_one("#sc-error", Static).update(text)

    def select_scenario(self, path: Path, *, advance: bool = True) -> bool:
        """Load the scenario at *path*; on success go to the FDS step."""
        try:
            info = model.read_scenario(path)
        except model.ScenarioError as exc:
            self._scenario_error(exc.message, exc.details)
            return False
        self.query_one("#sc-error", Static).update("")
        changed = self.form.scenario is None or self.form.scenario.path != info.path
        self.form.scenario = info
        self._show_info(info.path)
        if changed:
            self.form.fds_dir = None
            self.facts, self.facts_for, self.facts_error = None, None, None
            self._fill_fds_choices()
        self.form_changed()
        if advance:
            self.goto(1)
        return True

    # --- FDS step ----------------------------------------------------------------

    @work(thread=True, exclusive=True, group="suggest")
    def _suggest(self, roots: list[Path]) -> None:
        found = model.find_fds_dirs(roots)
        self.call_from_thread(self._show_suggestions, found)

    def _fill_fds_choices(self) -> None:
        scenario = self.form.scenario
        if scenario is None:
            return
        folder = scenario.path if scenario.path.is_dir() else scenario.path.parent
        self.suggestions = []
        self._show_suggestions([])
        self._suggest([folder, self.cwd])

    def _show_suggestions(self, found: list[Path]) -> None:
        self.suggestions = found
        choices = self.query_one("#fds-choices", OptionList)
        choices.clear_options()
        for i, path in enumerate(found):
            rel = (
                os.path.relpath(path, self.cwd)
                if path.is_relative_to(self.cwd)
                else path
            )
            choices.add_option(
                Option(
                    m("[$success]Found FDS output[/]  $p", p=_short(rel, 60)),
                    id=f"fds-{i}",
                )
            )
        choices.add_option(
            Option(m("No FDS (clear air)  [dim]no fire input[/]"), id="no-fds")
        )
        choices.highlighted = 0
        self._render_fds_panel()

    @on(OptionList.OptionSelected, "#fds-choices")
    def _fds_choice(self, event: OptionList.OptionSelected) -> None:
        self._apply_fds_choice(event.option.id)

    # --- browsing folders from the path box (dired-like) -------------------------

    @on(Input.Changed, "#fds-path")
    def _fds_path_changed(self, event: Input.Changed) -> None:
        text = event.value
        if not text.strip() or text == (self.form.fds_dir or ""):
            self.browse_folder = None
            self._show_suggestions(self.suggestions)
            return
        self._browse(text)

    @work(thread=True, exclusive=True, group="browse")
    def _browse(self, text: str) -> None:
        folder, found = model.browse_dirs(text)
        usable = folder is not None and model.has_smv(folder)
        self.call_from_thread(self._show_browse, text, folder, found, usable)

    def _show_browse(
        self,
        text: str,
        folder: Path | None,
        found: list[tuple[Path, bool]],
        usable: bool,
    ) -> None:
        if text != self.query_one("#fds-path", Input).value or folder is None:
            return
        self.browse_folder, self.browsed = folder, found
        choices = self.query_one("#fds-choices", OptionList)
        choices.clear_options()
        if usable:
            choices.add_option(
                Option(
                    m(
                        "[$success]Use this folder[/]  $p  [dim]FDS output[/]",
                        p=_short(folder, 60),
                    ),
                    id="use",
                )
            )
        if folder.parent != folder:
            choices.add_option(
                Option(m("..  [dim]up to $p[/]", p=_short(folder.parent, 60)), id="up")
            )
        for i, (path, smv) in enumerate(found):
            tag = "  [$success]FDS output[/]" if smv else ""
            choices.add_option(Option(m(f"$n/{tag}", n=path.name), id=f"dir-{i}"))
        if not found:
            choices.add_option(
                Option(
                    m("[dim]No matching folder in $p[/]", p=_short(folder, 60)),
                    disabled=True,
                )
            )
        # The suggestions stay below the browsed folders.
        for i, path in enumerate(self.suggestions):
            choices.add_option(
                Option(
                    m("[$success]Found FDS output[/]  $p", p=_short(path, 60)),
                    id=f"fds-{i}",
                )
            )
        choices.add_option(
            Option(m("No FDS (clear air)  [dim]no fire input[/]"), id="no-fds")
        )
        choices.highlighted = _first_entry(choices, "dir-", text)

    def _go_into(self, folder: Path, box_id: str = "#fds-path") -> None:
        box = self.query_one(box_id, Input)
        box.value = str(folder) + os.sep
        box.cursor_position = len(box.value)

    # The path boxes and the lists they browse; Tab completes, Down goes down.
    PATH_BOXES = {
        "fds-path": (model.complete_dir, "#fds-choices"),
        "open-path": (model.complete_scenario, "#open-list"),
    }

    def action_complete_path(self) -> None:
        focused = self.focused
        in_list = isinstance(focused, BrowseList)
        box = self.query_one(focused.box_id, Input) if in_list else focused
        if not isinstance(box, Input) or box.id not in self.PATH_BOXES:
            return
        complete, listing = self.PATH_BOXES[box.id]
        completed = complete(box.value)
        if completed != box.value:
            box.value = completed
            box.cursor_position = len(completed)
        elif in_list:
            box.focus()
        else:
            self.query_one(listing).focus()

    def action_focus_choices(self) -> None:
        box = self.focused
        if isinstance(box, Input) and box.id in self.PATH_BOXES:
            self.query_one(self.PATH_BOXES[box.id][1]).focus()

    def _accept_fds_choice(self) -> None:
        typed = self.query_one("#fds-path", Input).value
        if self.focused is self.query_one("#fds-path") and typed.strip():
            self._fds_typed(typed)
            return
        choices = self.query_one("#fds-choices", OptionList)
        if choices.highlighted is None:
            self.goto(2)
            return
        self._apply_fds_choice(choices.get_option_at_index(choices.highlighted).id)

    def _apply_fds_choice(self, ident: str | None) -> None:
        browsing = ident in ("use", "up") or (ident or "").startswith("dir-")
        if browsing and self.browse_folder is not None:
            self._browse_choice(cast(str, ident))
            return
        if ident == "no-fds":
            self.set_fds_dir(None)
        elif ident:
            self.set_fds_dir(str(self.suggestions[int(ident[4:])]))
        self.goto(2)

    def _browse_choice(self, ident: str) -> None:
        folder = cast(Path, self.browse_folder)
        if ident == "up":
            self._go_into(folder.parent)
            return
        target = folder if ident == "use" else self.browsed[int(ident[4:])][0]
        if ident == "use" or self.browsed[int(ident[4:])][1]:
            self.browse_folder = None
            self.set_fds_dir(str(target.resolve()))
            self.goto(2)
            return
        self._go_into(target)

    @on(Input.Submitted, "#fds-path")
    def _fds_submitted(self, event: Input.Submitted) -> None:
        self._fds_typed(event.value)

    def _fds_typed(self, text: str) -> None:
        if not text.strip():
            self.query_one("#fds-panel", Static).update(
                m("Choose a folder or [b]No FDS (clear air)[/] in the list.")
            )
            self.query_one("#fds-choices").focus()
            return
        error, details = model.check_fds_dir(text)
        if error is not None:
            self.query_one("#fds-panel", Static).update(
                m("[$error]$e[/]\n[dim]$d[/]", e=error, d=details)
            )
            return
        self.set_fds_dir(details)
        self.goto(2)

    def set_fds_dir(self, path: str | None) -> None:
        if path == self.form.fds_dir:
            return
        self.form.fds_dir = path
        self.query_one("#fds-path", Input).value = path or ""
        self.facts, self.facts_for, self.facts_error = None, None, None
        if path:
            self.inspect_fds()
        self.form_changed()

    def inspect_fds(self) -> None:
        path = self.form.fds_dir
        if not path:
            return
        self.inspecting = True
        self._render_fds_panel()
        if self.inspector is inspect_fds:
            prepare_processes()
        self._inspect(path)

    @work(thread=True, exclusive=True, group="inspect")
    def _inspect(self, path: str) -> None:
        try:
            facts, error = self.inspector(path), None
        except Exception as exc:  # shown in the panel; the run is still allowed
            facts, error = None, f"{type(exc).__name__}: {exc}"
        self.call_from_thread(self._inspected, path, facts, error)

    def _inspected(self, path: str, facts: Any, error: str | None) -> None:
        if path != self.form.fds_dir:
            return
        self.inspecting = False
        self.facts, self.facts_for, self.facts_error = facts, path, error
        self._render_fds_panel()
        self.schedule_config()

    def _render_fds_panel(self) -> None:
        panel = self.query_one("#fds-panel", Static)
        path = self.form.fds_dir
        if not path:
            deck = self.form.scenario is not None and not self.suggestions
            panel.update(
                m(
                    "Not chosen yet: Enter on a suggestion, type a path, or choose "
                    "No FDS (clear air).$x",
                    x="\nThis example ships the FDS deck only. Run FDS first, or "
                    f"continue without fire: {model.FDS_DOCS}"
                    if deck
                    else "",
                )
            )
            return
        if self.inspecting:
            panel.update(m("$p\n… Inspecting (reads the .smv)", p=_short(path, 70)))
            return
        if self.facts_error:
            panel.update(
                m(
                    "[$warning]Could not inspect the FDS folder: $e[/]\n"
                    "[dim]The run is still allowed; Review shows Level 1.[/]",
                    e=self.facts_error,
                )
            )
            return
        if self.facts is None:
            return
        panel.update(self._facts_text())

    def _facts_text(self) -> Content:
        names = ("extinction", "co", "co2", "o2", "temperature", "integrated_intensity")
        parts = [m("$p\n", p=_short(self.form.fds_dir, 70))]
        for name in names:
            if self.facts.has(name):
                parts.append(m("[$success]✓[/] $n  ", n=name))
            else:
                parts.append(m("[dim]✗ $n[/]  ", n=name))
        horizon = self.facts.horizon
        if horizon is not None and self.form.scenario is not None:
            limit = self.form.scenario.max_time
            ok = limit <= horizon[0] + horizon[1]
            parts.append(
                m(
                    "\nFDS output ends at $e s; scenario runs to $l s $g",
                    e=f"{horizon[0]:.1f}",
                    l=f"{limit:.1f}",
                    g="✓" if ok else "! runs past the FDS end (D32)",
                )
            )
        return Content.assemble(*parts)

    # --- configuration ------------------------------------------------------------

    @on(FieldRow.Changed)
    def _field_changed(self, event: FieldRow.Changed) -> None:
        self.form_changed()

    @on(Input.Changed, "#output-folder")
    def _output_folder(self, event: Input.Changed) -> None:
        self.form.output_folder = event.value
        self.form_changed()

    def form_changed(self) -> None:
        """Any edit: the plan of the next run and the review are stale."""
        self.planned_base = None
        self.warned_confirmed = False
        self.schedule_config()
        self.update_chrome()

    def schedule_config(self) -> None:
        if self._cfg_timer is not None:
            self._cfg_timer.stop()
        if self.debounce <= 0:
            self._start_config()
            return
        self._cfg_timer = self.set_timer(self.debounce, self._start_config)

    def _results_root(self) -> Path:
        return frontend.results_root(self.cwd)

    def planned(self) -> str:
        """The run folder of the next run (fixed until the next edit)."""
        if self.planned_base is None:
            stamp = frontend.run_stamp(frontend.utc_now())
            self.planned_base = self.form.run_folder(stamp, self._results_root())
        return self.planned_base

    def namespace(self) -> Any:
        return self.form.namespace(self.form.output_paths(self.planned()))

    def _start_config(self) -> None:
        self._cfg_timer = None
        if self.form.scenario is None:
            return
        self._gen += 1
        facts = self.facts if self.facts_for == self.form.fds_dir else None
        self._compute(self._gen, self.namespace(), self.form.scenario.raw, facts)

    @work(thread=True, exclusive=True, group="config")
    def _compute(self, gen: int, ns: Any, raw: Any, facts: Any) -> None:
        result = compute_config(ns, raw, facts)
        self.call_from_thread(self._apply_config, gen, *result)

    def config_now(self) -> None:
        """Compute the configuration in the UI thread (before a run)."""
        if self.form.scenario is None:
            return
        self._gen += 1
        facts = self.facts if self.facts_for == self.form.fds_dir else None
        result = compute_config(self.namespace(), self.form.scenario.raw, facts)
        self._apply_config(self._gen, *result)

    def _apply_config(self, gen: int, cfg: Any, appl: Any, mech: Any) -> None:
        if gen != self._gen:
            return
        self.cfg, self.appl, self.mech = cfg, appl, mech
        _values, self.parse_errors = self.form.values()
        options = {o.option: o for o in cfg.options}
        for row in self.query(FieldRow):
            a = appl.get(row.dest)
            row.update_state(
                True if a is None else a.active,
                None if a is None else a.rule,
                None if a is None else a.reason,
                options.get(row.dest),
                self.parse_errors.get(row.dest),
            )
        self._update_sections()
        if self.step == 3:
            self.render_review()
        self.update_chrome()

    def _update_sections(self) -> None:
        for index, section in enumerate(model.SECTIONS):
            title = section
            lead = SECTION_LEAD.get(section)
            if lead is not None and self.mech is not None:
                title += "  on" if self.mech.heat_fed else "  off"
            rows = [r for r in self.query(f"#adv-{index} FieldRow").results(FieldRow)]
            changed = sum(
                1
                for r in rows
                if self.cfg is not None and _overridden(self.cfg, r.dest)
            )
            with_errors = [
                r
                for r in self.query(f"#sec-{index} FieldRow").results(FieldRow)
                if r.has_class("-invalid")
            ]
            if with_errors:
                title += f"  ✗ {len(with_errors)}"
            self.query_one(f"#sec-{index}", Collapsible).title = title
            if rows:
                adv = f"Advanced ({len(rows)})" + (
                    f" · {changed} changed" if changed else ""
                )
                self.query_one(f"#adv-{index}", Collapsible).title = adv
        fds = self.form.fds_dir
        self.query_one("#cfg-fds", Static).update(
            m(
                "FDS folder  $p  [dim](change: Esc to step 2)[/]",
                p=_short(fds, 44) if fds else "none, no fire input",
            )
        )
        base = self.planned()
        typed = self.form.output_folder.strip()
        self.query_one("#output-preview", Static).update(
            m(
                "$o  [dim]$k; fixed until you change a setting[/]",
                o=_short(base, 52),
                k="typed" if typed else "derived",
            )
        )
        paths = self.form.output_paths(base)
        lines = [m("[dim]Derived from the output folder (as in the GUI):[/]")]
        for dest, path in paths.items():
            lines.append(
                m("\n  $f  $p", f=f"--{dest.replace('_', '-')}", p=_short(path, 50))
            )
        self.query_one("#cfg-outputs", Static).update(Content.assemble(*lines))

    # --- chrome ------------------------------------------------------------------

    def invalid_count(self) -> int:
        n = len(self.parse_errors)
        if self.cfg is not None:
            n += len(self.cfg.errors)
        return n

    @property
    def settings_changed(self) -> bool:
        """Whether the form differs from the last run's snapshot.

        Output paths are left out: they follow the start time.
        """
        run = self.current_run
        if run is None or self.form.scenario is None:
            return False
        skip = set(frontend.output_paths("", ""))
        now = {k: v for k, v in vars(self.form.namespace()).items() if k not in skip}
        then = {k: v for k, v in run.snapshot.values.items() if k not in skip}
        return now != then or self.form.output_folder.strip() != run.output_folder

    def update_chrome(self) -> None:
        if not self.query("#stepbar"):
            return  # resize before the first compose
        marks: dict[int, str] = {}
        if self.form.scenario is not None:
            marks[1] = "✓"
            if 1 in self.visited:
                marks[2] = "✓"
            if 2 in self.visited:
                marks[3] = "✓"
        if self.invalid_count():
            marks[4] = "!"
        elif 3 in self.visited and self.form.scenario is not None:
            marks[4] = "✓"
        if self.current_run is not None:
            marks[5] = "⟳" if not self.current_run.done else "✓"
            if self.current_run.done:
                marks[6] = (
                    "✎" if self.settings_changed else outcome_glyph(self.current_run)
                )
        width = self.size.width or 80
        self.query_one("#stepbar", StepBar).show(self.step + 1, marks, width)
        summary = self.query_one("#summary", Static)
        summary.display = self.step in (1, 2, 3)
        summary.update(self.summary_line())

    def summary_line(self) -> Content:
        if self.form.scenario is None:
            return m("[dim]No scenario yet[/]")
        cfg, mech = self.cfg, self.mech
        if cfg is None or mech is None:
            return m("[dim]… computing the effective configuration[/]")
        if self.form.fds_dir and self.facts is None:
            level = "L1 … inspecting" if self.inspecting else "L1, FDS not inspected"
        else:
            level = f"L{cfg.level}"
        smoke = {"fds": "FDS", "constant": "K const"}.get(mech.smoke or "", "off")
        vis = {"smoky": "smoky", "clear-air": "clear air"}.get(
            mech.visibility or "", "off"
        )
        reroute = (
            f"{self.form.values()[0]['reroute_interval']:g} s"
            if mech.rerouting
            else "off"
        )
        parts = [
            level,
            f"smoke {smoke}",
            f"gas {'FED' if mech.gas_fed else 'off'}",
            f"heat {'on' if mech.heat_fed else 'off'}",
            f"FIC {'on' if mech.fic else 'off'}",
            f"reroute {reroute}",
            f"vis {vis}",
        ]
        if cfg.warnings:
            parts.append(
                f"{len(cfg.warnings)} warning{'s' if len(cfg.warnings) != 1 else ''}"
            )
        head = m("$t  ", t="  ".join(parts))
        n = self.invalid_count()
        tail = (
            m("[$error]✗ $n error$s[/]", n=n, s="s" if n != 1 else "")
            if n
            else m("[$success]✓ valid[/]")
        )
        return Content.assemble(head, tail)

    # --- review ----------------------------------------------------------------

    def render_review(self) -> None:
        if self.form.scenario is None:
            self.query_one("#rv-outcome", Static).update(
                m("[dim]Choose a scenario first (step 1).[/]")
            )
            return
        if self.cfg is None:
            self.config_now()
        cfg = self.cfg
        errors = self.query_one("#rv-errors", OptionList)
        errors.clear_options()
        for dest, text in self.parse_errors.items():
            errors.add_option(
                Option(
                    m(
                        "[$error]✗[/] $l: $t  [dim]Enter: go to field[/]",
                        l=model.label(model.parameter(dest)),
                        t=text,
                    ),
                    id=f"err-{dest}",
                )
            )
        for i, issue in enumerate(cfg.errors):
            errors.add_option(
                Option(
                    m(
                        "[$error]✗[/] $t  [dim]$r · Enter: go to field[/]",
                        t=issue.message,
                        r=issue.rule,
                    ),
                    id=f"err-{issue.option or ''}-{i}",
                )
            )
        errors.display = errors.option_count > 0
        n = self.invalid_count()
        running = self.current_run is not None and not self.current_run.done
        if running:
            outcome = m(
                "[b $primary]⟳ Run #$r in progress[/]",
                r=self.current_run.snapshot.run_id if self.current_run else "",
            )
        elif n:
            outcome = m(
                "[b $error]✗ $n error$s, the run cannot start[/]",
                n=n,
                s="s" if n != 1 else "",
            )
        elif cfg.warnings:
            outcome = m(
                "[b $success]✓ Ready to run[/]  [$warning]! $n warning$s[/]",
                n=len(cfg.warnings),
                s="s" if len(cfg.warnings) != 1 else "",
            )
        else:
            outcome = m("[b $success]✓ Ready to run[/]")
        level = m(
            "   [dim]Level $l$x[/]",
            l=cfg.level,
            x="" if cfg.level == 2 else ", FDS folder not inspected",
        )
        self.query_one("#rv-outcome", Static).update(Content.assemble(outcome, level))
        self.query_one("#rv-body", ScrollText).show(review_text(cfg))
        self.query_one("#rv-command", TextArea).text = cfg.command

    @on(OptionList.OptionSelected, "#rv-errors")
    def _goto_error(self, event: OptionList.OptionSelected) -> None:
        ident = str(event.option.id)[4:]
        dest = (
            ident.rsplit("-", 1)[0] if ident[-1].isdigit() and "-" in ident else ident
        )
        self.focus_field(dest or None)

    def focus_field(self, dest: str | None) -> None:
        if dest in (None, "fds_dir"):
            self.goto(1 if dest == "fds_dir" else 2)
            return
        self.goto(2)
        rows = list(self.query(f"#row-{dest}").results(FieldRow))
        if not rows:
            return
        row = rows[0]
        for ancestor in row.ancestors:
            if isinstance(ancestor, Collapsible):
                ancestor.collapsed = False
        target = row if row.control.disabled else row.control
        self.call_after_refresh(target.focus)
        self.call_after_refresh(row.scroll_visible)

    def action_find(self) -> None:
        self.push_screen(FindScreen(), self.focus_field)

    def action_field_help(self) -> None:
        focused = self.focused
        row = next(
            (
                a
                for a in ([focused] + list(focused.ancestors) if focused else [])
                if isinstance(a, FieldRow)
            ),
            None,
        )
        if row is None:
            self.push_screen(TextScreen("Keys", keys_text()))
            return
        text = f"{field_help(row.param)}\n\nKeys\n{keys_text()}"
        self.push_screen(TextScreen(model.label(row.param), text))

    def action_copy_command(self) -> None:
        if self.form.scenario is None:
            return
        self.config_now()  # an edit within the debounce is not configured yet
        if self.cfg is None:
            return
        self.copy_to_clipboard(self.cfg.command)
        self.notify(
            "Sent to clipboard (OSC 52). If nothing was copied, select the "
            "command above or press s."
        )

    def preview_script(self) -> str:
        name = self.form.scenario.name if self.form.scenario else "scenario"
        return model.python_for(
            self.namespace(),
            [
                "Current settings and the planned run folder; not started.",
                f"Scenario: {name}",
            ],
            output_dir=f"{self.planned()}/python_output",
        )

    def action_show_python(self) -> None:
        if self.form.scenario is None:
            return
        self.push_screen(
            TextScreen(
                "Equivalent Python (current settings, not a run)",
                self.preview_script(),
                "c copy · Esc close",
            )
        )

    def action_save(self) -> None:
        if self.form.scenario is None:
            return
        self.config_now()  # an edit within the debounce is not configured yet
        if self.cfg is None:
            return
        folder = Path(self.planned())
        sh, py = model.save_command(folder, self.cfg.command, self.preview_script())
        self.notify(f"Saved {sh} and {py}", timeout=8, markup=False)

    # --- run -----------------------------------------------------------------------

    def action_run(self) -> None:
        if self.current_run is not None and not self.current_run.done:
            self.notify(
                f"A run is in progress (run #{self.current_run.snapshot.run_id})."
            )
            return
        if self.form.scenario is None:
            self.notify("Choose a scenario first.")
            self.goto(0)
            return
        self.config_now()
        n = self.invalid_count()
        if n:
            self.notify(
                f"Fix {n} error{'s' if n != 1 else ''} first.", severity="error"
            )
            self.goto(3)
            return
        if self.cfg.warnings and self.step != 3 and not self.warned_confirmed:
            count = len(self.cfg.warnings)
            self.push_screen(
                ConfirmScreen(
                    f"{count} warning{'s' if count != 1 else ''}.",
                    "r Run anyway   Esc Review",
                ),
                self._confirmed_run,
            )
            return
        self.start_run()

    def _confirmed_run(self, yes: bool | None) -> None:
        if yes:
            self.warned_confirmed = True
            self.start_run()
        else:
            self.goto(3)

    def start_run(self) -> None:
        base = self.planned()
        if Path(base).exists() and any(
            p.name not in ("command.sh", "run.py") for p in Path(base).iterdir()
        ):
            self.planned_base = None
            self.config_now()
            base = self.planned()
        assert self.form.scenario is not None
        ns = self.namespace()
        self.run_count += 1
        facts = self.facts if self.facts_for == self.form.fds_dir else None
        snapshot = model.RunSnapshot.freeze(
            self.run_count,
            ns,
            scenario=self.form.scenario,
            base=base,
            started_at=frontend.utc_now(),
            fds_facts=facts,
        )
        self.current_run = RunState(
            snapshot, output_folder=self.form.output_folder.strip()
        )
        self.scrub_index = None
        self.planned_base = None
        self.query_one("#run-log", RichLog).clear()
        self.goto(4)
        self.render_run()
        self.runner.start(dict(snapshot.values), base, self._post)

    def _post(self, event: Any) -> None:
        """From the runner's reader thread: queue *event*, never wait."""
        loop = self._ui_loop
        if self._quitting or loop is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):  # the app has ended
            loop.call_soon_threadsafe(
                self.on_run_event, event, context=self._ui_context
            )

    def on_run_event(self, event: Any) -> None:
        run = self.current_run
        if run is None or self._quitting:
            return
        log = self.query_one("#run-log", RichLog)
        if isinstance(event, events.PhaseEvent):
            run.phase, run.phase_detail = event.phase, event.detail
            if event.detail:
                log.write(event.detail)
        elif isinstance(event, Progress):
            run.progress = event
        elif isinstance(event, events.LogEvent):
            log.write(event.text)
        elif isinstance(event, events.WarningEvent):
            run.warnings.append(event)
            log.write(f"WARNING {event.text}")
        elif isinstance(event, events.PlanEvent):
            run.plan = event
        elif isinstance(event, events.FrameEvent):
            if event.smoke is not None:
                run.smoke = event.smoke
            run.frames.append((event, run.smoke))
        elif isinstance(event, Stopping):
            run.stopping = "killing" if event.killed else "stopping"
        elif isinstance(event, events.ResultEvent):
            run.result = event
            self._finish_run()
        elif isinstance(event, ChildExited):
            run.exited = event
            self._finish_run()
        if not run.done and self._render_timer is None:
            self._render_timer = self.set_timer(0.1, self._render_tick)

    def _render_tick(self) -> None:
        """Redraw the Run step at most ten times per second."""
        self._render_timer = None
        if self._quitting:
            return  # the widgets render_run queries are gone
        if self.current_run is not None and not self.current_run.done:
            self.render_run()

    def _finish_run(self) -> None:
        run = self.current_run
        assert run is not None
        run.ended = time.monotonic()
        status = status_word(run)
        snap = run.snapshot
        self.recent.add(
            str(snap.values["scenario"]),
            snap.values.get("fds_dir"),
            status,
            frontend.utc_now(),
        )
        self._fill_recent()
        self.goto(5)

    def render_run(self) -> None:
        run = self.current_run
        if run is None:
            return
        snap = run.snapshot
        p = run.progress
        if run.stopping:
            state = m(
                "[b $primary]⟳ Cancelling…[/] [dim]$s the process[/]", s=run.stopping
            )
        elif run.cancelling:
            state = m(
                "[b $primary]⟳ Cancelling…[/] [dim](waiting for the current phase: $p)[/]",
                p=PHASE_WORDS.get(run.phase or "", "starting"),
            )
        else:
            state = m("[b $primary]⟳ Running[/]")
        phases = []
        for phase in events.PHASES:
            word = PHASE_WORDS[phase]
            phases.append(
                m("[b u]$w[/]" if phase == run.phase else "[dim]$w[/]", w=word)
            )
        if (self.size.width or 80) < 100:
            index = events.PHASES.index(run.phase) + 1 if run.phase else 0
            word = PHASE_WORDS.get(run.phase or "", "starting")
            stepper = m("· $w ($i/$n)", w=word, i=index, n=len(events.PHASES))
        else:
            stepper = Content(" › ").join(phases)
        sim = 0.0 if p is None else p.sim_time
        total = None if p is None else p.total
        # Incapacitated only once the plan says the run can incapacitate.
        modelled = run.plan is not None and bool(run.plan.incapacitation_modelled)
        counts = (
            m(
                "evacuated $e of $t planned ($c %)"
                + ("   incapacitated $i" if modelled else "")
                + "   not spawned $n",
                e=p.evacuated,
                t=p.total,
                c=p.pct,
                i=p.incapacitated,
                n=p.not_spawned,
            )
            if p is not None
            else m("[dim]waiting for the first progress sample[/]")
        )
        warn = len(run.warnings)
        status = Content.assemble(
            state,
            m("  "),
            stepper,
            m("\n"),
            m(
                "sim $s / $l s (limit)   wall $w   ",
                s=f"{sim:.1f}",
                l=f"{snap.max_time:g}",
                w=_clock(run.wall),
            ),
            counts,
            m("\n"),
            m(
                "[$warning]! $n warning$x[/]  [dim]w list[/]",
                n=warn,
                x="s" if warn != 1 else "",
            )
            if warn
            else m("[dim]no warnings[/]"),
            m("   [dim]$d[/]", d=run.phase_detail) if run.phase_detail else m(""),
        )
        self.query_one("#run-status", Static).update(status)
        width = 16 if self.has_class("-wide") else max(20, self.size.width - 30)
        frac_e = 0.0 if p is None or not total else (p.evacuated / total)
        frac_t = 0.0 if snap.max_time <= 0 else min(1.0, sim / snap.max_time)
        bars = Content.assemble(
            m("[b]Evacuated[/]\n"),
            _bar(frac_e, width),
            m(
                "  $e of $t planned\n",
                e=0 if p is None else p.evacuated,
                t="?" if total is None else total,
            ),
            m("[b]Simulated time[/]\n"),
            _bar(frac_t, width),
            m("  $s of $l s", s=f"{sim:.0f}", l=f"{snap.max_time:g}"),
        )
        self.query_one("#run-bars", Static).update(bars)
        self.query_one("#run-spark", Sparkline).data = evacuated_series(run) or [0]
        self.query_one("#run-note", Static).update(
            m(
                "[dim]The run stops if this terminal closes; use tmux or screen for long runs.[/]"
            )
        )
        self.refresh_plans()

    def refresh_plans(self) -> None:
        run = self.current_run
        if run is None:
            return
        frame, smoke = self._current_frame()
        ticks = [w.sim_time for w in run.warnings if w.sim_time is not None]
        t = (
            frame.sim_time
            if frame is not None
            else (run.progress.sim_time if run.progress else 0.0)
        )
        for prefix in ("run", "res", "full"):
            views = (
                list(self.screen.query(f"#{prefix}-planview").results(PlanView))
                if prefix == "full"
                else list(self.query(f"#{prefix}-planview").results(PlanView))
            )
            if not views:
                continue
            views[0].show(run.plan, frame, smoke)
            root = self.screen if prefix == "full" else self
            width = views[0].size.width or self.size.width
            root.query_one(f"#{prefix}-scrubber", Static).update(
                scrubber(t, run.snapshot.max_time, ticks, width, self.current_theme)
            )
            key = legend(run.plan, self.current_theme, smoke)
            if prefix != "run" and run.done and run.frames:
                key.append("\n ←/→ 1 s · shift+←/→ 10 s: replay the frames", "dim")
            root.query_one(f"#{prefix}-legend", Static).update(key)
        if isinstance(self.screen, PlanScreen):
            self.screen.query_one("#full-head", Static).update(
                m(
                    "[b]pyFDS-Evac[/]  run #$r  $n  seed $s  [dim]Esc back[/]",
                    r=run.snapshot.run_id,
                    n=run.snapshot.scenario_name,
                    s=run.snapshot.expected_seed,
                )
            )

    def _current_frame(self) -> tuple[Any, Any]:
        run = self.current_run
        if run is None or not run.frames:
            return None, None
        if self.scrub_index is None or not run.done:
            return run.frames[-1]
        return run.frames[max(0, min(self.scrub_index, len(run.frames) - 1))]

    def action_scrub(self, seconds: int) -> None:
        run = self.current_run
        if run is None or not run.done or not run.frames:
            return
        index = len(run.frames) - 1 if self.scrub_index is None else self.scrub_index
        target = run.frames[index][0].sim_time + seconds
        times = [f.sim_time for f, _s in run.frames]
        best = min(range(len(times)), key=lambda i: abs(times[i] - target))
        if best == index and seconds:
            best = max(0, min(len(times) - 1, index + (1 if seconds > 0 else -1)))
        self.scrub_index = best
        self.refresh_plans()

    def action_plan(self) -> None:
        if self.current_run is None:
            return
        self.push_screen(PlanScreen())

    def action_warnings(self) -> None:
        if self.current_run is None:
            return
        lines = [
            (f"t {w.sim_time:.1f} s  " if w.sim_time is not None else "") + w.text
            for w in self.current_run.warnings
        ]
        self.push_screen(TextScreen("Warnings", "\n".join(lines) or "No warnings."))

    def action_log(self) -> None:
        log = self.query_one("#run-log", RichLog)
        text = "\n".join(strip.text for strip in log.lines)
        self.push_screen(TextScreen("Log", text))

    def action_cancel(self) -> None:
        if self.current_run is None or self.current_run.done:
            return
        if self.current_run.cancelling:
            self.push_screen(
                ConfirmScreen("Stop the process now?", "y Stop now   n Keep waiting"),
                self._confirmed_stop,
            )
            return
        self.push_screen(
            ConfirmScreen(
                "Cancel run? Files already written are kept.",
                "y Cancel run   n Keep running",
            ),
            self._confirmed_cancel,
        )

    def _confirmed_cancel(self, yes: bool | None) -> None:
        if yes and self.current_run is not None and not self.current_run.done:
            self.current_run.cancelling = True
            self.runner.cancel()
            self.render_run()

    def _confirmed_stop(self, yes: bool | None) -> None:
        if yes and self.current_run is not None and not self.current_run.done:
            self.current_run.stopping = "stopping"
            self.runner.stop()
            self.render_run()

    async def action_quit(self) -> None:
        if self.current_run is not None and not self.current_run.done:
            self.push_screen(
                ConfirmScreen(
                    "A run is in progress. Quit and cancel it?",
                    "y Quit and cancel   n Keep running",
                ),
                self._confirmed_quit,
            )
            return
        self.exit()

    def _confirmed_quit(self, yes: bool | None) -> None:
        if yes:
            self._quitting = True
            self.runner.stop()
            self.exit()

    # --- results ---------------------------------------------------------------

    def render_results(self) -> None:
        run = self.current_run
        if run is None:
            return
        snap = run.snapshot
        banner = self.query_one("#res-banner", Static)
        banner.display = self.settings_changed
        banner.update(
            m(
                "✎ Previous settings. Settings changed since run #$r. These results show "
                "that run's settings, not the current ones. Run again to get results "
                "for the current settings.",
                r=snap.run_id,
            )
        )
        self.query_one("#res-outcome", Static).update(
            results_text(run, self.size.width or 80)
        )
        exits = run.result.exit_counts if run.result is not None else None
        parts = []
        if run.warnings:
            n = len(run.warnings)
            parts.append(
                m(
                    "[$warning]! $n warning$s[/]  [dim]w list[/]\n",
                    n=n,
                    s="s" if n != 1 else "",
                )
            )
        parts.append(m("[b]Per exit (end of run)[/]"))
        for exit_id, count in sorted((exits or {}).items()):
            parts.append(
                m("\n[$success]█[/] $e  $c", e=f"{exit_id:<16}", c=f"{count:>5}")
            )
        if not exits:
            parts.append(m("\n[dim]not reported for this run[/]"))
        self.query_one("#res-exits", Static).update(Content.assemble(*parts))
        spark = self.query_one("#res-spark", Sparkline)
        spark.data = evacuated_series(run) or [0]
        spark.display = bool(run.frames) and self.has_class("-wide")
        if spark.display:
            # The series has one point per plan frame, so it spans the frames,
            # not the scenario's time limit.
            end = run.frames[-1][0].sim_time
            parts.append(m("\n[dim]Evacuated over sim time, 0–$t s ↓[/]", t=f"{end:g}"))
            self.query_one("#res-exits", Static).update(Content.assemble(*parts))
        files = self.query_one("#res-files", OptionList)
        files.clear_options()
        if not result_files(run):
            files.add_option(
                Option(m("[dim]No output files were written.[/]"), disabled=True)
            )
        base = Path(snap.base)
        for i, path in enumerate(result_files(run)):
            shown = (
                os.path.relpath(path, base) if Path(path).is_relative_to(base) else path
            )
            files.add_option(
                Option(
                    m("$p  [dim]$s[/]", p=_short(shown, 60), s=_size(path)),
                    id=f"file-{i}",
                )
            )
        if result_files(run):
            files.highlighted = 0
        self.query_one("#res-files-title", Static).update(
            m(
                "[b]Output files[/]  [dim]in $b  · Enter preview · y copy path[/]",
                b=_short(base, 70),
            )
        )
        self.refresh_plans()

    @on(OptionList.OptionSelected, "#res-files")
    def _file_selected(self, event: OptionList.OptionSelected) -> None:
        if self.current_run is None:
            return
        path = result_files(self.current_run)[event.option_index]
        self.push_screen(FileScreen(path, file_preview(path), file_opener()))

    def action_copy_path(self) -> None:
        files = self.query_one("#res-files", OptionList)
        if self.current_run is None or files.highlighted is None:
            return
        path = result_files(self.current_run)[files.highlighted]
        self.copy_to_clipboard(path)
        self.notify(f"Sent to clipboard (OSC 52): {path}", markup=False)

    def run_script(self) -> str:
        run = self.current_run
        assert run is not None
        snap = run.snapshot
        ns = snap.namespace()
        lines = [
            f"Run #{snap.run_id}, started {snap.started_at}.",
            f"Scenario: {snap.scenario_name}",
        ]
        used = None if run.result is None else run.result.seed
        if ns.seed is None and used is not None and used == snap.expected_seed:
            ns.seed = used
            lines.append(
                f"Seed {used}: the seed run #{snap.run_id} used (scenario baseSeed)."
            )
        return model.python_for(ns, lines, output_dir=f"{snap.base}/python_output")

    def action_run_command(self) -> None:
        if self.current_run is None:
            return
        snap = self.current_run.snapshot
        text = f"{snap.command}\n\n{self.run_script()}"
        self.push_screen(
            TextScreen(
                f"Command and Python for run #{snap.run_id}",
                text,
                "From the run's snapshot, not the current settings. c copy",
            )
        )

    def action_save_run(self) -> None:
        if self.current_run is None:
            return
        snap = self.current_run.snapshot
        sh, py = model.save_command(Path(snap.base), snap.command, self.run_script())
        self.notify(f"Saved {sh} and {py}", timeout=8, markup=False)

    def action_traceback(self) -> None:
        run = self.current_run
        if run is None:
            return
        if run.result is not None and run.result.traceback:
            self.push_screen(TextScreen("Traceback", run.result.traceback))
        elif run.exited is not None:
            self.push_screen(TextScreen("End of child.log", run.exited.log_tail))

    # --- palette helpers ---------------------------------------------------------

    def reset_all(self) -> None:
        def done(yes: bool | None) -> None:
            if not yes:
                return
            self.form.reset(self.form.text.keys() | self.form.switch.keys())
            for row in self.query(FieldRow):
                row.sync_control()
            self.form_changed()

        self.push_screen(
            ConfirmScreen("Reset all settings to their defaults?", "y Reset   n Keep"),
            done,
        )

    def toggle_advanced(self) -> None:
        advanced = list(self.query("Collapsible").results(Collapsible))
        collapse = not any(
            c.id and c.id.startswith("adv-") and not c.collapsed for c in advanced
        )
        for c in advanced:
            if c.id and c.id.startswith("adv-"):
                c.collapsed = not collapse

    def show_docs(self) -> None:
        self.notify(f"Docs: {model.TUI_DOCS}", timeout=10, markup=False)


# --- text builders (no widget state) ----------------------------------------------


def compute_config(ns: Any, raw: Any, facts: Any) -> tuple[Any, Any, Any]:
    """The effective configuration, per-option applicability and models."""
    from pyfds_evac.config.effective import effective_configuration
    from pyfds_evac.config.rules import UNKNOWN_FDS, applicability, predict_mechanisms

    known = facts if facts is not None else UNKNOWN_FDS
    cfg = effective_configuration(ns, raw, fds=facts, inspect_fds=False)
    return cfg, applicability(ns, raw, known), predict_mechanisms(ns, raw, known)


def _overridden(cfg: Any, dest: str) -> bool:
    return any(o.option == dest and o.overridden for o in cfg.options)


def review_text(cfg: Any) -> Content:
    """The Review blocks of an effective configuration."""
    inputs = cfg.inputs
    parts = [m("[b]Inputs[/]\n")]
    parts.append(
        m(
            "  scenario   $s ($k)\n",
            s=_short(inputs["scenario"], 56),
            k=inputs["scenario_kind"],
        )
    )
    fds = inputs["fds_dir"]
    horizon = inputs["fds_horizon_s"]
    end = "" if horizon is None else f"   ends {horizon[0]:.1f} s"
    parts.append(
        m(
            "  FDS        $f$e\n",
            f=_short(fds, 52) if fds else "none, no fire input",
            e=end,
        )
    )
    parts.append(
        m(
            "  seed       $s, $o     time limit $t s, scenario\n",
            s=inputs["seed"],
            o=inputs["seed_origin"],
            t=f"{inputs['max_simulation_time_s']:g}",
        )
    )
    if inputs["outputs"]:
        folder = str(Path(next(iter(inputs["outputs"].values()))).parent)
        parts.append(m("  output     $o\n", o=_short(folder, 56)))
    parts.append(m("[b]Models[/]\n"))
    for mech in cfg.mechanisms:
        glyph = "[$success]✓ on [/]" if mech.on else "[dim]– off[/]"
        parts.append(m(f"  $n {glyph}  $d\n", n=f"{mech.name:<22}", d=mech.detail))
    changed = [
        o
        for o in cfg.options
        if o.overridden
        and o.option not in inputs["outputs"]
        and o.option not in ("scenario", "fds_dir")
    ]
    parts.append(m("[b]Changed settings[/]$n\n", n="  none" if not changed else ""))
    for o in changed:
        mark = (
            "  [$warning]! departs from FDS+Evac[/]" if o.departs_from_fds_evac else ""
        )
        unit = f" {o.unit}" if o.unit and o.value is not None else ""
        parts.append(
            m(
                f"  [$primary]*[/] $f $v$u  [dim]default $d[/]{mark}\n",
                f=o.flag,
                v=o.value,
                u=unit,
                d=o.default,
            )
        )
    if cfg.resolved:
        for key, value in cfg.resolved.items():
            parts.append(m("    [dim]resolved $k $v[/]\n", k=key, v=value))
    parts.append(m("[b]No effect[/]$n\n", n="  none" if not cfg.inactive else ""))
    for i in cfg.inactive:
        parts.append(m("  $f $v: $r\n", f=i.flag, v=i.value, r=i.reason))
    parts.append(m("[b]Warnings[/]$n\n", n="  none" if not cfg.warnings else ""))
    for w in cfg.warnings:
        parts.append(m("  [$warning]![/] $w\n", w=w))
    if cfg.routing:
        stars = [r.key for r in cfg.routing if r.overridden]
        parts.append(
            m(
                "[b]Scenario routing[/]  [dim]$s[/]\n",
                s="* " + ", ".join(stars) if stars else "code defaults",
            )
        )
    if cfg.level == 1 and inputs["fds_dir"]:
        parts.append(
            m(
                "[dim]FDS folder not inspected: checks that need its slices (D3, D6, "
                "D12, D17, D28, D32) are not shown yet. Palette: Inspect FDS folder.[/]\n"
            )
        )
    return Content.assemble(*parts)


def outcome_glyph(run: RunState) -> str:
    """The glyph of a finished run's state (spec §6)."""
    return {
        events.STATUS_SUCCESS: "✓",
        events.STATUS_INCOMPLETE: "◐",
        events.STATUS_CANCELLED: "■",
    }.get(run.status, "✗")


def status_word(run: RunState) -> str:
    return {
        events.STATUS_SUCCESS: "complete",
        events.STATUS_INCOMPLETE: "incomplete",
        events.STATUS_FAILED: "failed",
        events.STATUS_CANCELLED: "cancelled",
    }.get(run.status, "failed")


def results_text(run: RunState, width: int = 120) -> Content:
    """The outcome first (spec §2.6), worded as the GUI words it.

    Below 100 columns the incapacitated figure goes on its own line.
    """
    snap, r = run.snapshot, run.result
    head = m(
        "[dim]run #$i · $n · seed $s · wall $w[/]",
        i=snap.run_id,
        n=snap.scenario_name,
        s=snap.expected_seed if r is None or r.seed is None else r.seed,
        w=_clock(run.wall),
    )
    if r is not None and r.status in (events.STATUS_SUCCESS, events.STATUS_INCOMPLETE):
        status = "completed" if r.status == events.STATUS_SUCCESS else "incomplete"
        outcome = frontend.run_outcome(status, r.remaining, r.not_spawned)
        glyph, colour = ("✓", "$success") if outcome.complete else ("◐", "$warning")
        line = m(
            f"[b {colour}]$g $l[/]   [dim]exit $x[/]\n",
            g=glyph,
            l=outcome.label,
            x=r.exit_code,
        )
        evacuated = frontend.evacuated_text(
            r.evacuated or 0, r.total or 0, r.not_spawned
        )
        modelled = bool(r.incapacitation_modelled)
        incap = (
            f"Incapacitated {r.incapacitated}"
            if modelled and r.incapacitated is not None
            else f"Incapacitated: {frontend.INCAPACITATION_NOT_MODELLED}"
        )
        sep = "\n  " if width < 100 else "   "
        nums = m(
            "  $t $e s   Evacuated $v$s$i\n",
            t=outcome.time_label,
            e=f"{r.end_time_s:.1f}",
            v=evacuated,
            s=sep,
            i=incap,
        )
        frac = (r.evacuated or 0) / r.total if r.total else 0.0
        bar = Content.assemble(
            m("  "),
            _bar(frac, 40),
            m("  $v\n", v=evacuated),
        )
        extra = m("")
        if r.fds_outside and r.fds_outside.get("rows"):
            o = r.fds_outside
            extra = m(
                "  Outside the FDS domain: $a agent(s), $r sample(s)\n",
                a=o.get("agents"),
                r=o["rows"],
            )
        return Content.assemble(
            line, nums, bar, extra, m("  [dim]$s[/]\n", s=r.summary), head
        )
    if r is not None and r.status == events.STATUS_FAILED:
        where = (
            "" if run.plan is not None else " (during setup; the run was not started)"
        )
        return Content.assemble(
            m(
                "[b $error]✗ Run failed$w: $e[/]   [dim]exit $x · t traceback · e change settings[/]\n",
                w=where,
                e=r.error or "",
                x=r.exit_code,
            ),
            head,
        )
    if run.status == events.STATUS_CANCELLED:
        sim = run.progress.sim_time if run.progress else None
        how = "; the process was stopped" if run.exited is not None else ""
        return Content.assemble(
            m(
                "[b]■ $c$h[/]   [dim]no exit code[/]\n",
                c=frontend.cancelled_text(sim),
                h=how,
            ),
            head,
        )
    code = None if run.exited is None else run.exited.exit_code
    return Content.assemble(
        m(
            "[b $error]✗ The run stopped without a result (process exit $c).[/]  [dim]t: end of child.log[/]\n",
            c=code,
        ),
        head,
    )


def result_files(run: RunState) -> list[str]:
    """Files of the run: as the run reports them, else the outputs that exist."""
    log = str(Path(run.snapshot.base) / "child.log")
    if run.result is not None and run.result.files:
        files = list(run.result.files)
    else:
        files = [p for p in run.snapshot.output_files() if Path(p).exists()]
    if Path(log).exists() and Path(log).stat().st_size > 0:
        files.append(log)
    return files


def evacuated_series(run: RunState) -> list[float]:
    """Evacuated agents per frame, for the sparkline (frames only)."""
    return [float(frame.evacuated) for frame, _smoke in run.frames]


PREVIEW_LINES = 40
PREVIEW_WIDTH = 200


def _first_entry(options: OptionList, prefix: str, text: str) -> int:
    """The row to highlight: after a typed name, the first match (not ``..``
    or "Use this folder"), so Enter picks it; else row 0."""
    if not os.path.split(text)[1]:
        return 0
    for index in range(options.option_count):
        if (options.get_option_at_index(index).id or "").startswith(prefix):
            return index
    return 0


def file_preview(path: str) -> str:
    """What the file dialog shows: text lines, SQLite tables or a folder's files."""
    p = Path(path)
    try:
        if p.is_dir():
            names = sorted(str(f.relative_to(p)) for f in p.rglob("*") if f.is_file())
            return "\n".join([f"Folder, {len(names)} files:", *names])
        if p.suffix == ".sqlite":
            return _sqlite_preview(p)
        with p.open(encoding="utf-8", errors="replace") as fh:
            lines = [
                line.rstrip("\n")[:PREVIEW_WIDTH]
                for _, line in zip(range(PREVIEW_LINES + 1), fh)
            ]
    except (OSError, sqlite3.Error) as exc:
        return f"Cannot read the file: {exc}"
    if len(lines) > PREVIEW_LINES:
        lines = [*lines[:PREVIEW_LINES], f"… first {PREVIEW_LINES} lines shown"]
    return "\n".join(lines) or "(empty file)"


def _sqlite_preview(path: Path) -> str:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    lines = []
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        for (name,) in db.execute(query).fetchall():
            count = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            lines.append(f"  {name}: {count} rows")
    return "\n".join([f"SQLite database, {len(lines)} tables:", *lines])


def file_opener() -> list[str] | None:
    """The command that opens a file in the system app; None over SSH or if absent."""
    if os.environ.get("SSH_CONNECTION"):
        return None
    if sys.platform == "darwin":
        return ["open"]
    if sys.platform.startswith("linux") and shutil.which("xdg-open"):
        return ["xdg-open"]
    return None


def _size(path: str) -> str:
    try:
        p = Path(path)
        size: float = (
            p.stat().st_size
            if p.is_file()
            else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        )
    except OSError:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def field_help(param: Any) -> str:
    """The F1 help of an option: model help, flag, defaults, counterpart."""
    from pyfds_evac.config.parameters import NO_COUNTERPART, SAME

    lines = [model.help_text(param), "", f"Flag: {param.flag}"]
    if param.help != model.help_text(param):
        lines += ["", f"CLI help: {param.help}"]
    lines.append(f"Default: {param.default}")
    if param.python_default is not SAME:
        lines.append(f"Python API default: {param.python_default}")
    if param.fds_evac is not NO_COUNTERPART:
        lines.append(f"FDS+Evac counterpart: {param.fds_evac}")
    if param.unit:
        lines.append(f"Unit: {param.unit}")
    if param.checked:
        lines.append(f"Checked: {param.checked}")
    lines.append(f"Reaches: {param.python}")
    lines.append(f"Docs: {model.SECTION_DOCS.get(param.group, model.USAGE_DOCS)}")
    return "\n".join(lines)


def keys_text() -> str:
    return "\n".join(
        [
            "Tab / Shift+Tab   next / previous control",
            "Enter             activate; on a disabled row, go to the setting that enables it",
            "ctrl+n / ctrl+p   next / previous step (keeps all values; Esc also goes back)",
            "ctrl+r            run (Configure, Review, Results)",
            "ctrl+f            find a setting (Configure)",
            "? or F1           this list; on a field, its help first",
            "ctrl+k            command palette (themes, steps, save, reset)",
            "ctrl+q            quit (asks during a run)",
            "Run: x or ctrl+c cancel · v fullscreen plan · w warnings · l log",
            "Results: e change · n new · c command · s save · ←/→ scrub the plan",
        ]
    )
