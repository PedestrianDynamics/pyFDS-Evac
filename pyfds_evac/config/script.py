"""The equivalent Python script of a run configuration (#484).

The script rebuilds the options as an ``argparse.Namespace`` and calls
``build_run_kwargs`` and ``run_scenario`` itself, so it runs what the CLI
and the GUI run. Every value is written as a Python literal via ``repr``
and checked with ``ast.literal_eval``; text that reaches a comment goes
through :func:`_safe`, so no option text can break out into code.

The GUI's "Show equivalent Python" (``pyfds_evac.webapp.pyexport``) adds
its header to the same body. Provisional public API (0.3.0).
"""

from __future__ import annotations

import ast
import math
import pathlib
import re
from collections.abc import Mapping
from typing import Any

from .parameters import PARAMETERS

# Flags that steer the command, not the run (--show-config).
_COMMAND_ONLY = frozenset(p.dest for p in PARAMETERS if not p.run_option)

# Options that are paths on this machine. They go into the PATHS block,
# resolved to absolute paths, so they are easy to find and edit.
_PATH_KEYS = ("scenario", "fds_dir", "vis_cache")

# Output files the CLI and the GUI write through apply_outputs. The script
# does not write them; the keys are set to None (build_run_kwargs reads only
# output_route_cost_history, and collect_route_cost_history keeps that
# history on).
OMITTED_OUTPUT_KEYS = (
    "output_sqlite",
    "output_smoke_history",
    "output_fed_history",
    "output_route_history",
    "output_route_cost_history",
    "output_exit_history",
    "export_app_bundle",
)

_PLAIN = re.compile(r"[\w.+:@/-]*")


class ExportError(ValueError):
    """The configuration holds a value that cannot be written as a literal."""


def _safe(text: Any) -> str:
    """Return *text* for a comment: plain as is, anything else as ``repr``.

    ``repr`` escapes newlines, carriage returns and every other line or
    paragraph separator, so a hostile name cannot end the comment line.
    """
    s = str(text)
    return s if _PLAIN.fullmatch(s) else repr(s)


def _literal(key: str, value: Any) -> str:
    """Return ``repr(value)``, refusing anything that is not a plain literal."""
    if value is not None and not isinstance(value, (bool, int, float, str)):
        raise ExportError(f"{key}: {type(value).__name__} is not exportable")
    if isinstance(value, float) and not math.isfinite(value):
        raise ExportError(f"{key}: {value!r} is not a finite number")
    text = repr(value)
    if ast.literal_eval(text) != value:  # pragma: no cover - defensive
        raise ExportError(f"{key}: {value!r} does not round-trip")
    return text


def _abs_path(value: Any) -> str | None:
    """Resolve a path option as this process sees it, or keep None."""
    if value is None or str(value).strip() == "":
        return None
    return str(pathlib.Path(str(value)).expanduser().resolve())


def export_options(opts: Mapping[str, Any], seed: Any) -> dict[str, Any]:
    """The non-path options the script passes, in a stable order."""
    options = {"seed": seed}
    for key in sorted(opts):
        if key in _PATH_KEYS or key == "seed" or key in _COMMAND_ONLY:
            continue
        options[key] = None if key in OMITTED_OUTPUT_KEYS else opts[key]
    return options


def _body(
    paths: dict[str, str | None],
    output_dir: str,
    options: dict[str, Any],
    seed_comment: str,
) -> list[str]:
    """Imports, PATHS, settings, the run and the result check."""
    lines = [
        "",
        "import argparse",
        "import pathlib",
        "import shutil",
        "import sys",
        "",
        "from pyfds_evac.core import load_scenario, run_scenario",
        "from pyfds_evac.core.manifest import manifest_path_for",
        "from pyfds_evac.core.run_config import build_run_kwargs",
        "",
        "# PATHS: from the computer that made this script; edit on another machine.",
        f"SCENARIO = {_literal('scenario', paths['scenario'])}",
        f"FDS_DIR = {_literal('fds_dir', paths['fds_dir'])}",
        f"VIS_CACHE = {_literal('vis_cache', paths['vis_cache'])}",
        "# A new folder: the script never writes into a front end's run folder.",
        f"OUTPUT_DIR = pathlib.Path({_literal('output_dir', output_dir)})",
        "",
        "# Settings: the resolved configuration passed to build_run_kwargs.",
        "OPTIONS = {",
    ]
    for key, value in options.items():
        comment = seed_comment if key == "seed" else ""
        lines.append(f"    {_literal(key, key)}: {_literal(key, value)},{comment}")
    lines += [
        "}",
        "",
        "opts = argparse.Namespace(",
        "    **OPTIONS,",
        "    scenario=SCENARIO,",
        "    fds_dir=FDS_DIR,",
        "    vis_cache=VIS_CACHE,",
        ")",
        "",
        "scenario = load_scenario(SCENARIO)",
        "run_kwargs = build_run_kwargs(scenario, opts, log=print)",
        "result = run_scenario(scenario, **run_kwargs)",
        "",
        "# The summary and exit status of run.py: a run the time limit stops with",
        "# agents inside or flow agents not yet spawned is incomplete (exit 2).",
        "if result.success:",
        "    print(",
        '        f"Simulation finished in {result.evacuation_time:.2f} s "',
        '        f"({result.agents_evacuated}/{result.total_agents} evacuated)."',
        "    )",
        "else:",
        "    not_spawned = (",
        '        f", {result.agents_not_spawned} not spawned"',
        "        if result.agents_not_spawned",
        '        else ""',
        "    )",
        "    print(",
        '        "Simulation incomplete: time limit reached after "',
        '        f"{result.evacuation_time:.2f} s "',
        '        f"({result.agents_evacuated}/{result.total_agents} evacuated, "',
        '        f"{result.agents_remaining} remaining{not_spawned})."',
        "    )",
        "",
        "OUTPUT_DIR.mkdir(parents=True, exist_ok=True)",
        "if result.sqlite_file:",
        '    trajectory = OUTPUT_DIR / "trajectory.sqlite"',
        "    shutil.copy2(result.sqlite_file, trajectory)",
        '    print(f"Trajectory SQLite: {trajectory.resolve()}")',
        "    if result.manifest_file:",
        "        shutil.copy2(result.manifest_file, manifest_path_for(trajectory))",
        "result.cleanup()  # remove the temporary copies run_scenario wrote",
        "if not result.success:",
        "    sys.exit(2)",
        "",
    ]
    return lines


def python_script(
    opts: Any,
    *,
    output_dir: str = "pyfds_evac_output",
    header: str = "# Equivalent Python of a pyfds-evac run configuration.",
) -> str:
    """The script that runs *opts* through the Python API.

    *opts* has the attributes of the ``pyfds-evac`` options; its paths are
    resolved to absolute paths. Output files other than the trajectory and
    its manifest are not written (see :data:`OMITTED_OUTPUT_KEYS`).
    """
    values = vars(opts) if not isinstance(opts, Mapping) else dict(opts)
    paths = {key: _abs_path(values.get(key)) for key in _PATH_KEYS}
    options = export_options(values, values.get("seed"))
    code = "\n".join([header, *_body(paths, output_dir, options, "")])
    ast.parse(code)  # a rendering bug must never reach the user as code
    return code
