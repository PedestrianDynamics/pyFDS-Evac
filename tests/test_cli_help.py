"""The ``--help`` page is grouped and short; the flags behind it are unchanged.

``tests/golden/cli_options.json`` is the option table of 0.2.1, before the
help was grouped: option strings, dest, default, choices, type, nargs,
required, const and action class, plus the flags added since: ``--debug``
(#486). Grouping the help must not change it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyfds_evac import cli

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden" / "cli_options.json"
CONSOLE_SCRIPT = Path(sys.executable).parent / "pyfds-evac"

GROUPS = (
    "Scenario & run",
    "Outputs",
    "FDS input & smoke",
    "Toxic gas (FED/FIC)",
    "Heat",
    "Routing",
    "Visibility & signs",
    "ASET/RSET tools",
)


def _table(parser) -> dict[str, dict]:
    table = {}
    for action in parser._actions:
        table[" ".join(action.option_strings)] = {
            "action": type(action).__name__,
            "choices": list(action.choices) if action.choices else None,
            "const": action.const,
            "default": action.default,
            "dest": action.dest,
            "nargs": action.nargs,
            "required": action.required,
            "type": getattr(action.type, "__name__", None),
        }
    return table


def test_option_table_is_unchanged():
    assert _table(cli._build_parser()) == json.loads(GOLDEN.read_text())


def test_every_flag_is_in_exactly_one_named_group():
    parser = cli._build_parser()
    titles = [group.title for group in parser._action_groups]
    assert titles[-len(GROUPS) :] == list(GROUPS)
    seen: list[str] = []
    for group in parser._action_groups:
        dests = [action.dest for action in group._group_actions]
        if group.title in GROUPS:
            assert dests, group.title
            seen += dests
        else:
            assert dests in ([], ["help"]), group.title
    flags = [a.dest for a in parser._actions if a.dest != "help"]
    assert sorted(seen) == sorted(flags)


def test_help_is_short_and_grouped():
    text = cli._build_parser().format_help()
    assert text.splitlines()[0].endswith(" --scenario PATH [--fds-dir DIR] [options]")
    for title in GROUPS:
        assert f"\n{title}:\n" in text, title
    assert "--enable-heat-fed" in text.split("\nHeat:\n", 1)[1].split("\n\n", 1)[0]
    assert "fds-evac repository" not in text
    assert "pyfds-evac-gui" in text.split("\nexamples:\n", 1)[1]


def _help(program: list[str], extra_env: dict[str, str]) -> str:
    env = {**os.environ, "COLUMNS": "100", **extra_env}
    env.pop("FORCE_COLOR", None)
    shown = subprocess.run(
        [*program, "--help"], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert shown.returncode == 0, shown.stderr
    return shown.stdout


@pytest.mark.parametrize("env", [{}, {"NO_COLOR": "1"}], ids=["plain", "no-color"])
@pytest.mark.parametrize("command", ["run.py", "module", "console-script"])
def test_help_exits_zero_and_is_plain_off_a_terminal(command, env):
    """Piped or with NO_COLOR, --help is plain text with every group."""
    if command == "console-script" and not CONSOLE_SCRIPT.is_file():
        pytest.skip(f"{CONSOLE_SCRIPT} not installed; run uv sync")
    env = {**env, "TERM": "xterm-256color"}
    program = {
        "run.py": [sys.executable, "run.py"],
        "module": [sys.executable, "-m", "pyfds_evac"],
        "console-script": [str(CONSOLE_SCRIPT)],
    }[command]
    text = _help(program, env)
    assert "\x1b[" not in text
    assert text.startswith("usage: ")
    assert " --scenario PATH [--fds-dir DIR] [options]\n" in text.splitlines(True)[0]
    for title in GROUPS:
        assert f"\n{title}:\n" in text, title
