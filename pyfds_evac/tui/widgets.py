"""Widgets of the terminal UI: field rows, the step bar, dialogs."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from typing import Any, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalGroup, Vertical, VerticalScroll
from textual.content import Content
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Footer,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    Switch,
    TextArea,
)
from textual.widgets._footer import FooterKey
from textual.widgets.option_list import Option

from pyfds_evac.config.parameters import Parameter, parameter

from . import model

STEP_TITLES = ("Scenario", "FDS", "Configure", "Review", "Run", "Results")
_FLAG = re.compile(r"--(?:no-)?([a-z0-9-]+)")


def m(markup: str, **values: Any) -> Content:
    """Markup with *values* inserted as plain text (never parsed as markup)."""
    return Content.from_markup(markup, **{k: str(v) for k, v in values.items()})


def enabling_option(reason: str | None) -> str | None:
    """The option a disabled field's reason names ("without --enable-heat-fed").

    The reason text is the model's (``applies``); the first flag in it that
    is a run option is the control that changes the answer.
    """
    for match in _FLAG.finditer(reason or ""):
        dest = match.group(1).replace("-", "_")
        try:
            parameter(dest)
        except KeyError:
            continue
        return dest
    return None


def _target_name(dest: str) -> str:
    """Where Enter on a disabled row goes, in words."""
    if dest == "fds_dir":
        return "FDS output folder (step 2)"
    return model.label(parameter(dest))


class StepBar(Static):
    """`` 1 Scenario › 2 FDS › … `` with the state of each step."""

    def show(self, current: int, marks: dict[int, str], width: int) -> None:
        parts = [m("[b]pyFDS-Evac[/]  ")]
        for i, title in enumerate(STEP_TITLES, start=1):
            mark = marks.get(i, "")
            text = f"{i}{mark}" if width < 100 else f"{i} {title}{mark}"
            if i == current:
                parts.append(m("[reverse b] $t [/]", t=text))
            else:
                parts.append(m("[$text-muted] $t [/]", t=text))
            if width >= 100 and i < len(STEP_TITLES):
                parts.append(m("[dim]›[/]"))
        self.update(Content.assemble(*parts))


class FieldRow(Vertical):
    """One option: label, control, marker, and a help line when focused.

    When the option does not apply, the control is disabled and the row
    itself takes focus, so the reason can be read (spec §2.3).
    """

    DEFAULT_CSS = """
    FieldRow { height: auto; padding: 0 0 0 1; }
    FieldRow > Horizontal { height: auto; }
    FieldRow .label { width: 30; padding: 0 1 0 0; content-align: left middle; }
    FieldRow Input, FieldRow Select { width: 1fr; max-width: 32; }
    FieldRow Switch { width: 6; height: 1; border: none; padding: 0; }
    FieldRow Switch:focus { border: none; background: $primary 30%; }
    FieldRow .marker { width: 1fr; padding: 0 0 0 1; color: $text-muted; }
    FieldRow .help { display: none; color: $text-muted; padding: 0 0 0 2; }
    FieldRow:focus-within .help, FieldRow:focus .help { display: block; }
    FieldRow.-inactive .label, FieldRow.-inactive .marker { text-style: dim; }
    FieldRow.-invalid .marker { color: $error; }
    /* As the command palette: a hover band, and the cursor band on top. */
    FieldRow:hover { background: $block-hover-background; }
    FieldRow:focus, FieldRow:focus-within {
        background: $block-cursor-blurred-background;
    }
    FieldRow:focus .label, FieldRow:focus-within .label { text-style: bold; }
    """

    BINDINGS = [Binding("enter", "enable", "go to the setting", show=False)]

    class Changed(Message):
        def __init__(self, dest: str) -> None:
            super().__init__()
            self.dest = dest

    def __init__(self, param: Parameter, form: model.Form) -> None:
        super().__init__(id=f"row-{param.dest}")
        self.param = param
        self.form = form
        self.reason: str | None = None
        self.rule: str | None = None
        self.can_focus = False

    @property
    def dest(self) -> str:
        return self.param.dest

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(model.label(self.param), classes="label", markup=False)
            yield self._control()
            yield Static("default", classes="marker")
        yield Static("", classes="help")

    def _control(self) -> Widget:
        p, ident = self.param, f"f-{self.param.dest}"
        if p.kind == "bool":
            return Switch(self.form.switch[p.dest], id=ident)
        if p.kind == "choice":
            value = self.form.text[p.dest] or Select.NULL
            return Select(
                [(c, c) for c in p.choices or ()],
                prompt="not set",
                allow_blank=p.default is None,
                value=value,
                id=ident,
                compact=True,
            )
        placeholder = "not set" if p.default is None else ""
        return TextBox(
            self.form.text[p.dest], placeholder=placeholder, id=ident, compact=True
        )

    @property
    def control(self) -> Widget:
        return self.query_one(f"#f-{self.param.dest}")

    def sync_control(self) -> None:
        """Put the form's value into the control (after a reset)."""
        control, dest = self.control, self.dest
        if isinstance(control, Switch):
            control.value = self.form.switch[dest]
        elif isinstance(control, Select):
            control.value = self.form.text[dest] or Select.NULL
        elif isinstance(control, Input):
            control.value = self.form.text[dest]

    def on_click(self) -> None:
        """A click on an inactive row focuses it, so its reason shows."""
        if self.reason is not None:
            self.focus()

    def action_enable(self) -> None:
        """Enter on a disabled row: go to the control that enables it."""
        if self.reason is None:
            return
        dest = enabling_option(self.reason)
        if dest is not None:
            cast(Any, self.app).focus_field(dest)
        else:
            self.app.notify(f"{model.label(self.param)}: {self.reason}", markup=False)

    @on(Input.Changed)
    def _input(self, event: Input.Changed) -> None:
        event.stop()
        if self.form.text.get(self.dest) != event.value:
            self.form.text[self.dest] = event.value
            self.post_message(self.Changed(self.dest))

    @on(Switch.Changed)
    def _switch(self, event: Switch.Changed) -> None:
        event.stop()
        if self.form.switch.get(self.dest) != event.value:
            self.form.switch[self.dest] = event.value
            self.post_message(self.Changed(self.dest))

    @on(Select.Changed)
    def _select(self, event: Select.Changed) -> None:
        event.stop()
        value = "" if event.value is Select.NULL else str(event.value)
        if self.form.text.get(self.dest) != value:
            self.form.text[self.dest] = value
            self.post_message(self.Changed(self.dest))

    def update_state(
        self,
        active: bool,
        rule: str | None,
        reason: str | None,
        option: Any,
        error: str | None,
    ) -> None:
        """Show whether the option applies, its marker and its help line."""
        self.reason, self.rule = (None, None) if active else (reason, rule)
        self.set_class(not active, "-inactive")
        self.set_class(error is not None, "-invalid")
        control = self.control
        if control.disabled == active:
            control.disabled = not active
            self.can_focus = not active
        self.query_one(".marker", Static).update(self._marker(option, error, active))
        self.query_one(".help", Static).update(self._help(error, active))

    def _marker(self, option: Any, error: str | None, active: bool) -> Content:
        marker = self._state_marker(option, error, active)
        if self.param.kind != "bool":
            return marker
        state = "on " if self.form.switch.get(self.dest) else "off"
        return Content.assemble(m("[b]$s[/]  ", s=state), marker)

    def _state_marker(self, option: Any, error: str | None, active: bool) -> Content:
        if error is not None:
            return m("[$error]✗ invalid[/]")
        if option is None:
            return m("[dim]default[/]")
        if option.departs_from_fds_evac:
            fds = self.param.fds_evac
            return m("[$warning]! departs from FDS+Evac ($v)[/]", v=fds)
        if option.overridden:
            return m("[$primary]* changed[/]")
        return m("[dim]default[/]") if active else m("[dim]– inactive[/]")

    def _help(self, error: str | None, active: bool) -> Content:
        flag = self.param.flag
        if error is not None:
            return m("[$error]$e[/]  [dim]$f[/]", e=error, f=flag)
        if not active:
            target = enabling_option(self.reason)
            where = "" if target is None else f" · Enter: go to {_target_name(target)}"
            return m("– $r  [dim]$f$w[/]", r=self.reason, f=flag, w=where)
        text = model.help_text(self.param)
        default = self.param.default
        tail = "" if default is None else f" · default {default}"
        return m("$h  [dim]$f$t · F1 more[/]", h=text, f=flag, t=tail)


class TextBox(Input):
    """An Input that leaves ``?`` to the app, so the footer's ``? keys`` holds."""

    def check_consume_key(self, key: str, character: str | None) -> bool:
        return character != "?" and super().check_consume_key(key, character)


# The keys every footer shows on the right, whatever the step (#598).
FIXED_KEYS = (("ctrl+q", "quit", "quit"), ("question_mark", "field_help", "keys"))


class EvacFooter(Footer):
    """The footer: the step's keys, then a fixed group ``^q quit ? keys ^k palette``.

    The group is docked right, so on a narrow terminal the step keys are
    cut first and the way out and the key list stay visible.
    """

    DEFAULT_CSS = """
    EvacFooter { overflow-x: hidden; }
    EvacFooter #fixed-keys {
        dock: right;
        width: auto;
        border-left: vkey $foreground 20%;
    }
    EvacFooter #fixed-keys FooterKey:last-child { padding-right: 1; }
    """

    def __init__(self) -> None:
        super().__init__(show_command_palette=False)

    def compose(self) -> ComposeResult:
        yield from super().compose()
        palette = (self.app.COMMAND_PALETTE_BINDING, "command_palette", "palette")
        with HorizontalGroup(id="fixed-keys"):
            for key, action, label in (*FIXED_KEYS, palette):
                display = self.app.get_key_display(Binding(key, action, label))
                yield FooterKey(key, display, label, action).data_bind(
                    compact=Footer.compact
                )


class ConfirmScreen(ModalScreen[bool]):
    """A yes/no question; *yes* and *no* name the keys and actions."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical {
        width: 64; height: auto; padding: 1 2; background: $panel;
        border: tall $primary;
    }
    """
    BINDINGS = [
        Binding("y", "answer(True)", "yes", show=False),
        Binding("r", "answer(True)", "yes", show=False),
        Binding("n", "answer(False)", "no", show=False),
        Binding("escape", "answer(False)", "back"),
    ]

    def __init__(self, question: str, choices: str) -> None:
        super().__init__()
        self.question = question
        self.choices = choices

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(m("[b]$q[/]", q=self.question))
            yield Static(m("[dim]$c[/]", c=self.choices))

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class TextScreen(ModalScreen[None]):
    """A read-only text (command, script, traceback, list) in a dialog."""

    DEFAULT_CSS = """
    TextScreen { align: center middle; }
    TextScreen > Vertical {
        width: 96%; height: 90%; padding: 0 1; background: $panel;
        border: tall $primary;
    }
    TextScreen TextArea { height: 1fr; }
    """
    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("c", "copy", "copy"),
    ]

    def __init__(self, title: str, text: str, note: str = "") -> None:
        super().__init__()
        self.title_text = title
        self.text = text
        self.note = note

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(m("[b]$t[/]", t=self.title_text))
            yield TextArea(self.text, read_only=True, soft_wrap=True, id="text")
            yield Static(m("[dim]$n[/]", n=self.note or "c copy · Esc close"))

    def action_close(self) -> None:
        self.dismiss(None)

    def action_copy(self) -> None:
        self.app.copy_to_clipboard(self.text)
        self.app.notify(
            "Sent to clipboard (OSC 52). If nothing was copied, select the text."
        )


class FileScreen(TextScreen):
    """An output file: its path, a preview, and keys to copy the path or open it."""

    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("y", "copy_path", "copy path"),
        Binding("o", "open", "open"),
    ]

    def __init__(self, path: str, preview: str, opener: list[str] | None) -> None:
        keys = (
            "y copy path · o open · Esc close" if opener else "y copy path · Esc close"
        )
        super().__init__(path, preview, keys)
        self.path = path
        self.opener = opener

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "open":
            return self.opener is not None
        return True

    def action_copy_path(self) -> None:
        self.app.copy_to_clipboard(self.path)
        self.app.notify(f"Sent to clipboard (OSC 52): {self.path}", markup=False)

    def action_open(self) -> None:
        if self.opener is None:
            return
        subprocess.Popen(
            [*self.opener, self.path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.app.notify(f"Opening {self.path}", markup=False)


class FindScreen(ModalScreen[str | None]):
    """Find a setting by label, flag or unit (``ctrl+f``)."""

    DEFAULT_CSS = """
    FindScreen { align: center middle; }
    FindScreen > Vertical {
        width: 76; height: 20; padding: 0 1; background: $panel;
        border: tall $primary;
    }
    FindScreen OptionList { height: 1fr; }
    """
    BINDINGS = [Binding("escape", "close", "close")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(m("[b]Find a setting[/]  [dim]label, flag or unit[/]"))
            yield Input(placeholder="heat, --fic, °C", id="find")
            yield OptionList(id="found")

    def on_mount(self) -> None:
        self._fill("")

    @on(Input.Changed, "#find")
    def _changed(self, event: Input.Changed) -> None:
        self._fill(event.value)

    @on(Input.Submitted, "#find")
    def _submitted(self) -> None:
        found = self.query_one("#found", OptionList)
        if found.option_count:
            self.dismiss(found.get_option_at_index(0).id)

    @on(OptionList.OptionSelected, "#found")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def _fill(self, query: str) -> None:
        q = query.strip().lower()
        found = self.query_one("#found", OptionList)
        found.clear_options()
        for p in model.all_fields():
            hay = f"{model.label(p)} {p.flag} {p.unit or ''} {p.group}".lower()
            if q and q not in hay:
                continue
            found.add_option(
                Option(
                    m("$l  [dim]$f · $g[/]", l=model.label(p), f=p.flag, g=p.group),
                    id=p.dest,
                )
            )

    def action_close(self) -> None:
        self.dismiss(None)


class TooSmall(ModalScreen[None]):
    """The size notice of spec §7; leaves on its own when the terminal grows."""

    DEFAULT_CSS = """
    TooSmall { align: center middle; }
    TooSmall Static { width: auto; padding: 1 2; background: $panel; }
    """

    def compose(self) -> ComposeResult:
        yield Static(id="notice")

    def on_resize(self, event: Any) -> None:
        cast(Any, self.app)._check_size(event.size)

    def show(self, width: int, height: int) -> None:
        self.query_one("#notice", Static).update(
            m(
                "Terminal is $w×$h; the TUI needs 80×24.\nResize, or zoom out.\n"
                "[dim]A run continues meanwhile.[/]",
                w=width,
                h=height,
            )
        )


class ScrollText(VerticalScroll):
    """A scrollable block of Content (Review, Results)."""

    DEFAULT_CSS = "ScrollText { height: 1fr; } ScrollText Static { height: auto; }"

    def compose(self) -> ComposeResult:
        yield Static(id="body")

    def show(self, content: Content | str) -> None:
        self.query_one("#body", Static).update(content)


Callback = Callable[[Any], None]
