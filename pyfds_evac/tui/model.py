"""State of the terminal UI that needs neither Textual nor the run stack.

- scenarios: the examples under ``./assets`` and a light reader of a
  scenario's JSON (no ``load_scenario``, so no geometry is parsed);
- FDS folders: suggestions and the file-system checks of the FDS step;
- :class:`Form`: the text of every field, parsed by the ``pyfds-evac``
  parser itself, and the options namespace a run gets;
- :class:`RunSnapshot`: the frozen configuration of one submitted run;
- :class:`Recent`: ``recent.json`` (last runs and the theme).

Every default, unit, rule and message comes from :mod:`pyfds_evac.config`;
this module keeps none of its own.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import functools
import json
import os
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pyfds_evac.config import frontend
from pyfds_evac.config.parameters import (
    DEFAULTS,
    GROUP_ASET,
    GROUP_FDS,
    GROUP_GAS,
    GROUP_HEAT,
    GROUP_OUTPUTS,
    GROUP_ROUTING,
    GROUP_RUN,
    GROUP_SIGHT,
    GUI_HIDDEN,
    PARAMETERS,
    RUN_OPTIONS,
    TIER_ADVANCED,
    Parameter,
    parameter,
)

THEMES = ("evac-dark", "solarized-light")
DEFAULT_THEME = "evac-dark"
DOCS_URL = "https://pedestriandynamics.org/pyFDS-Evac/"

#: Sections of the Configure step: the CLI help groups, outputs last.
SECTIONS: tuple[str, ...] = (
    GROUP_RUN,
    GROUP_FDS,
    GROUP_GAS,
    GROUP_HEAT,
    GROUP_ROUTING,
    GROUP_SIGHT,
    GROUP_ASET,
    GROUP_OUTPUTS,
)

#: Model page of each section, for the help panel (no per-option anchors
#: exist yet, #485 R6).
SECTION_DOCS: dict[str, str] = {
    GROUP_FDS: DOCS_URL + "models/smoke-speed/",
    GROUP_GAS: DOCS_URL + "models/fed/",
    GROUP_HEAT: DOCS_URL + "models/heat/",
    GROUP_ROUTING: DOCS_URL + "models/routing/",
    GROUP_SIGHT: DOCS_URL + "models/wayfinding/",
}
USAGE_DOCS = DOCS_URL + "docs/usage/"
FDS_DOCS = DOCS_URL + "docs/fds-case-requirements/"

#: Options set on other steps (scenario, FDS folder) or derived from the
#: output folder; they are not fields of the Configure step.
_OUTPUT_DESTS = frozenset(frontend.output_paths("", ""))
_NOT_FIELDS = frozenset({"scenario", "fds_dir"}) | _OUTPUT_DESTS

#: A run option no front end sets: kept at its default.
UNSUPPORTED = (
    frozenset(
        d for d in RUN_OPTIONS if d in GUI_HIDDEN or parameter(d).group == GROUP_OUTPUTS
    )
    - _OUTPUT_DESTS
)


def label(param: Parameter) -> str:
    """The domain label of an option, as the GUI derives it, with its unit."""
    text = param.dest.replace("_", " ").capitalize()
    return f"{text} [{param.unit}]" if param.unit else text


def help_text(param: Parameter) -> str:
    """The short help of an option (the GUI's wording, else the CLI's)."""
    return (param.gui_help or param.help).strip()


def fields(section: str) -> list[Parameter]:
    """The editable options of *section*, common tier first, in flag order."""
    found = [
        p
        for p in PARAMETERS
        if p.group == section
        and p.run_option
        and p.dest not in GUI_HIDDEN
        and p.dest not in _NOT_FIELDS
    ]
    return sorted(found, key=lambda p: p.tier == TIER_ADVANCED)


def all_fields() -> list[Parameter]:
    return [p for section in SECTIONS for p in fields(section)]


# --- scenarios ---------------------------------------------------------------


class ScenarioError(ValueError):
    """A path that is not a scenario; ``details`` holds the technical part."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


@dataclass(frozen=True)
class ScenarioInfo:
    """A scenario read from its JSON, without loading the geometry."""

    path: Path
    kind: str  # "directory", "json" or "zip"
    name: str  # what names its run folder (see frontend.run_name)
    raw: Mapping[str, Any] = field(repr=False)

    @property
    def sim_settings(self) -> Mapping[str, Any]:
        return self.raw.get("config", {}).get("simulation_settings", {}) or {}

    @property
    def max_time(self) -> float:
        from pyfds_evac.config.effective import DEFAULT_MAX_SIMULATION_TIME_S

        params = self.sim_settings.get("simulationParams", {}) or {}
        return float(params.get("max_simulation_time", DEFAULT_MAX_SIMULATION_TIME_S))

    @property
    def seed(self) -> Any:
        from pyfds_evac.config.effective import DEFAULT_SEED

        return self.sim_settings.get("baseSeed", DEFAULT_SEED)

    @property
    def exits(self) -> int:
        return len(self.raw.get("exits") or {})

    @property
    def agents(self) -> int | None:
        """Agents the spawn areas ask for, when every one gives a number."""
        total = 0
        for dist in (self.raw.get("distributions") or {}).values():
            number = (dist.get("parameters") or {}).get("number")
            if not isinstance(number, int):
                return None
            total += number
        return total


def _json_and_wkt(directory: Path) -> tuple[list[Path], list[Path]]:
    """The JSON and WKT files ``load_scenario`` would pick, in its order."""
    config, geometry = directory / "config.json", directory / "geometry.wkt"
    jsons = [config] if config.exists() else sorted(directory.glob("*.json"))
    wkts = [geometry] if geometry.exists() else sorted(directory.glob("*.wkt"))
    return jsons, wkts


def scenario_name(path: Path) -> str:
    """The name of a scenario's run folder: the GUI's picker value."""
    if path.is_dir() or path.suffix.lower() == ".zip":
        return path.stem if path.suffix.lower() == ".zip" else path.name
    if path.name == "config.json":
        return path.parent.name
    return f"{path.parent.name}/{path.name}"


def read_scenario(text: str | os.PathLike[str]) -> ScenarioInfo:
    """Read the scenario at *text* with ``json.load``; raise ScenarioError."""
    path = Path(os.path.expanduser(str(text))).resolve()
    if not path.exists():
        raise ScenarioError(f"Not found: {path}", f"cwd {Path.cwd()}")
    try:
        if path.is_dir():
            return _read_directory(path)
        if path.suffix.lower() == ".zip":
            return _read_zip(path)
        if path.suffix.lower() == ".json":
            return ScenarioInfo(path, "json", scenario_name(path), _load(path))
    except ScenarioError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ScenarioError(
            f"Cannot read {path.name}: {exc}", f"{type(exc).__name__}: {exc}"
        ) from exc
    raise ScenarioError(
        f"Not a scenario: {path.name} is not a .json file, a .zip file or a folder",
        str(path),
    )


def _load(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("the file holds no JSON object")
    return raw


def _read_directory(path: Path) -> ScenarioInfo:
    jsons, wkts = _json_and_wkt(path)
    if not jsons:
        raise ScenarioError(f"Not a scenario: no config.json in {path}", str(path))
    if not wkts:
        raise ScenarioError(f"Not a scenario: no .wkt geometry in {path}", str(path))
    return ScenarioInfo(path, "directory", scenario_name(path), _load(jsons[0]))


def _read_zip(path: Path) -> ScenarioInfo:
    with zipfile.ZipFile(path) as zf:
        name = next((n for n in zf.namelist() if n.endswith(".json")), None)
        if name is None:
            raise ScenarioError(f"Not a scenario: no JSON file in {path.name}")
        raw = json.loads(zf.read(name))
    return ScenarioInfo(path, "zip", scenario_name(path), raw)


@dataclass(frozen=True)
class Example:
    """One scenario target under ``assets/``."""

    path: Path
    label: str
    variant_of: str | None
    readme: str
    fds: str  # "output", "deck" or "none"

    @property
    def fds_marker(self) -> str:
        return {"output": "FDS output found", "deck": "deck only"}.get(self.fds, "")


def _readme_line(directory: Path) -> str:
    readme = directory / "README.md"
    if not readme.is_file():
        return ""
    with contextlib.suppress(OSError, UnicodeDecodeError):
        for line in readme.read_text(encoding="utf-8").splitlines():
            text = line.strip().lstrip("#").strip()
            if text:
                return text
    return ""


def _fds_state(directory: Path) -> str:
    if find_fds_dirs([directory], max_depth=2):
        return "output"
    return "deck" if any(directory.glob("*.fds")) else "none"


def list_examples(root: Path) -> list[Example] | None:
    """The scenarios under ``root/assets``, or None when there is none.

    One row per folder with a ``config.json``, then one per
    ``config_*.json`` variant beside it.
    """
    assets = root / "assets"
    if not assets.is_dir():
        return None
    found: list[Example] = []
    for directory in sorted(assets.iterdir(), key=lambda p: p.name.lower()):
        if not (directory / "config.json").is_file():
            continue
        readme, fds = _readme_line(directory), _fds_state(directory)
        found.append(Example(directory, directory.name, None, readme, fds))
        for variant in sorted(directory.glob("config_*.json")):
            found.append(Example(variant, variant.stem, directory.name, "", fds))
    return found


# --- FDS folder --------------------------------------------------------------

_SKIP_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", "results"})


def find_fds_dirs(
    roots: Iterable[Path], *, max_depth: int = 2, max_entries: int = 4000
) -> list[Path]:
    """Folders at most *max_depth* below each root that hold a ``.smv`` file.

    The walk stops after *max_entries* directory entries, so a large
    working directory cannot stall the screen.
    """
    found: list[Path] = []
    seen = 0
    queue = [(Path(r), 0) for r in roots]
    while queue and seen < max_entries:
        directory, depth = queue.pop(0)
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        seen += len(entries)
        if any(e.is_file() and e.name.endswith(".smv") for e in entries):
            resolved = directory.resolve()
            if resolved not in found:
                found.append(resolved)
        if depth >= max_depth:
            continue
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                continue
            with contextlib.suppress(OSError):
                if entry.is_dir(follow_symlinks=False):
                    queue.append((Path(entry.path), depth + 1))
    return found


BROWSE_LIMIT = 200


def has_smv(path: Path) -> bool:
    """Whether *path* is a folder that holds a ``.smv`` file."""
    try:
        return any(e.is_file() and e.name.endswith(".smv") for e in os.scandir(path))
    except OSError:
        return False


def _browse(
    text: str, keep: Callable[[os.DirEntry[str]], bool | None]
) -> tuple[Path | None, list[tuple[Path, bool]]]:
    """The folder that *text* points into and its entries that *keep* accepts.

    ``"/a/b/"`` lists all of ``/a/b``; ``"/a/b/fd"`` the entries of ``/a/b``
    whose names start with ``fd`` (case-insensitive). Hidden entries show
    only when the typed name starts with a dot. *keep* returns None to drop
    an entry, else the flag stored with it. At most :data:`BROWSE_LIMIT`.
    """
    raw = os.path.expanduser(text.strip())
    if not raw:
        return None, []
    # Split the text itself: Path() would turn "a/." into "a".
    head, prefix = os.path.split(raw)
    folder = Path(head or ".")
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
    except OSError:
        return folder, []
    found: list[tuple[Path, bool]] = []
    for entry in entries:
        name = entry.name
        if name.startswith(".") and not prefix.startswith("."):
            continue
        if not name.lower().startswith(prefix.lower()):
            continue
        with contextlib.suppress(OSError):
            flag = keep(entry)
            if flag is not None:
                found.append((Path(entry.path), flag))
        if len(found) >= BROWSE_LIMIT:
            break
    return folder, found


def browse_dirs(text: str) -> tuple[Path | None, list[tuple[Path, bool]]]:
    """The subfolders *text* points at, each with whether it holds a ``.smv``."""
    return _browse(text, lambda e: has_smv(Path(e.path)) if e.is_dir() else None)


def _scenario_entry(entry: os.DirEntry[str]) -> bool | None:
    if entry.is_dir():
        jsons, wkts = _json_and_wkt(Path(entry.path))
        return bool(jsons and wkts)
    if Path(entry.name).suffix.lower() in (".json", ".zip"):
        return True
    return None


def browse_scenarios(text: str) -> tuple[Path | None, list[tuple[Path, bool]]]:
    """Folders and ``.json``/``.zip`` files *text* points at, each with
    whether it is a scenario (a file, or a folder with a JSON and a WKT)."""
    return _browse(text, _scenario_entry)


def _complete(text: str, browsed: tuple[Path | None, list[tuple[Path, bool]]]) -> str:
    folder, found = browsed
    if folder is None or not found:
        return text
    if len(found) == 1:
        path = found[0][0]
        return str(path) + os.sep if path.is_dir() else str(path)
    common = os.path.commonprefix([p.name for p, _flag in found])
    typed = os.path.split(os.path.expanduser(text.strip()))[1]
    if len(common) <= len(typed):
        return text
    return str(folder / common)


def complete_dir(text: str) -> str:
    """*text* completed as far as its matching folder names agree, as a shell does.

    One match completes to ``<folder>/``; several to their common prefix;
    none leaves *text* unchanged.
    """
    return _complete(text, browse_dirs(text))


def complete_scenario(text: str) -> str:
    """*text* completed over folders and ``.json``/``.zip`` files."""
    return _complete(text, browse_scenarios(text))


def check_fds_dir(text: str) -> tuple[str | None, str]:
    """``(error, details)`` of an FDS output folder; error None when usable.

    The folder checks of the FDS step (D35 is not in the model, #485 R7).
    """
    path = Path(os.path.expanduser(text)).resolve()
    if not path.is_dir():
        return "Folder does not exist", str(path)
    if not any(path.glob("*.smv")):
        listing = ", ".join(sorted(p.name for p in path.iterdir())[:10])
        return (
            f"No .smv file in {path}. Pick the folder FDS wrote into, not the "
            "deck folder.",
            f"First entries: {listing or '(empty)'}",
        )
    return None, str(path)


# --- the form ------------------------------------------------------------------


@functools.cache
def _parser() -> argparse.ArgumentParser:
    from pyfds_evac.cli import _build_parser

    return _build_parser()


@functools.cache
def _action(dest: str) -> argparse.Action:
    return next(a for a in _parser()._actions if a.dest == dest)


def parse_value(dest: str, text: str) -> Any:
    """Convert the text of a field as ``pyfds-evac`` converts its argument.

    Blank text means the option's default. Raises ValueError with the
    parser's own message ("invalid float value: 'abc'", "must be in
    [0.25, 1], got 2").
    """
    if text.strip() == "":
        return DEFAULTS[dest]
    parser, action = _parser(), _action(dest)
    try:
        value = parser._get_value(action, text.strip())
        parser._check_value(action, value)
    except argparse.ArgumentError as exc:
        raise ValueError(exc.message) from None
    return value


def initial_text(param: Parameter) -> str:
    return "" if param.default is None else str(param.default)


class Form:
    """What the user entered: text per value field, state per switch.

    The text of a field is kept as typed, also when it does not parse, so
    no step change or error loses it.
    """

    def __init__(self) -> None:
        self.text: dict[str, str] = {}
        self.switch: dict[str, bool] = {}
        for param in all_fields():
            if param.kind == "bool":
                self.switch[param.dest] = bool(param.default)
            else:
                self.text[param.dest] = initial_text(param)
        self.scenario: ScenarioInfo | None = None
        self.fds_dir: str | None = None
        self.output_folder: str = ""

    def reset(self, dests: Iterable[str]) -> None:
        for dest in dests:
            param = parameter(dest)
            if param.kind == "bool":
                self.switch[dest] = bool(param.default)
            else:
                self.text[dest] = initial_text(param)

    def values(self) -> tuple[dict[str, Any], dict[str, str]]:
        """``(values, errors)``: parsed values by dest, parse errors by dest.

        A field that does not parse keeps its default in *values*.
        """
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for dest, state in self.switch.items():
            values[dest] = state
        for dest, text in self.text.items():
            try:
                values[dest] = parse_value(dest, text)
            except ValueError as exc:
                errors[dest] = str(exc)
                values[dest] = DEFAULTS[dest]
        return values, errors

    def namespace(self, outputs: Mapping[str, str] | None = None) -> argparse.Namespace:
        """The ``pyfds-evac`` options of the form: run options only.

        *outputs* are the output paths of a run folder; without them the
        output options keep their defaults (None).
        """
        values, _errors = self.values()
        opts = {dest: DEFAULTS[dest] for dest in RUN_OPTIONS}
        opts.update(values)
        opts["scenario"] = None if self.scenario is None else str(self.scenario.path)
        opts["fds_dir"] = self.fds_dir or None
        opts.update(outputs or {})
        return argparse.Namespace(**opts)

    def run_folder(self, stamp: str, results: Path) -> str:
        """The folder a run started at *stamp* writes into (as the GUI)."""
        values, _errors = self.values()
        typed = self.output_folder.strip().replace("\\", "/").rstrip("/")
        if typed:
            return frontend.typed_output_base(typed, stamp, results)
        seed = values.get("seed")
        if seed is None and self.scenario is not None:
            seed = self.scenario.seed
        name = None if self.scenario is None else self.scenario.name
        mode = values.get("incapacitation_mode")
        return frontend.default_output_base(name, mode, seed, stamp, results)

    def output_paths(self, base: str) -> dict[str, str]:
        name = None if self.scenario is None else self.scenario.name
        return frontend.output_paths(base, frontend.run_name(name))


# --- runs ----------------------------------------------------------------------


@dataclass(frozen=True)
class RunSnapshot:
    """The configuration of one submitted run; later edits never reach it."""

    run_id: int
    values: Mapping[str, Any]
    scenario_name: str
    base: str
    started_at: str
    command: str
    max_time: float
    expected_seed: Any
    fds_facts: Any = None

    @classmethod
    def freeze(
        cls,
        run_id: int,
        opts: argparse.Namespace,
        *,
        scenario: ScenarioInfo,
        base: str,
        started_at: str,
        fds_facts: Any = None,
    ) -> RunSnapshot:
        from pyfds_evac.config.effective import cli_command

        values = copy.deepcopy(dict(vars(opts)))
        seed = values.get("seed")
        return cls(
            run_id=run_id,
            values=MappingProxyType(values),
            scenario_name=scenario.name,
            base=base,
            started_at=started_at,
            command=cli_command(opts),
            max_time=scenario.max_time,
            expected_seed=seed if seed is not None else scenario.seed,
            fds_facts=fds_facts,
        )

    def namespace(self) -> argparse.Namespace:
        return argparse.Namespace(**copy.deepcopy(dict(self.values)))

    def output_files(self) -> list[str]:
        """The output paths of this run, as set in its options."""
        return [
            str(self.values[d]) for d in sorted(_OUTPUT_DESTS) if self.values.get(d)
        ]


@functools.cache
def code_provenance() -> str:
    """``pyfds-evac <version>, commit <sha>`` of the running code."""
    from pyfds_evac.config.script import _safe
    from pyfds_evac.core.manifest import find_project_root, git_state, package_versions

    version = package_versions().get("pyfds-evac") or "version not recorded"
    commit, dirty = git_state(find_project_root())
    text = "commit not recorded" if not commit else f"commit {_safe(commit)}"
    if dirty:
        text += " (with uncommitted changes)"
    return f"pyfds-evac {_safe(version)}, {text}"


def python_for(opts: argparse.Namespace, header: list[str], output_dir: str) -> str:
    """The equivalent Python script of *opts* (``config.script``)."""
    from pyfds_evac.config.script import _safe, python_script

    lines = [f"# {_safe(line)}" if line else "#" for line in header]
    text = "\n".join(
        [
            "# Generated by pyfds-evac-tui.",
            f"# {code_provenance()}.",
            *lines,
            "# This file contains code only: the scenario folder and FDS results",
            "# are not included. On another machine, edit PATHS below.",
            "# Results can differ with other versions or on other platforms.",
        ]
    )
    return python_script(opts, output_dir=output_dir, header=text)


def save_command(folder: Path, command: str, script: str) -> tuple[Path, Path]:
    """Write ``command.sh`` and ``run.py`` into *folder*; return their paths."""
    folder.mkdir(parents=True, exist_ok=True)
    sh, py = folder / "command.sh", folder / "run.py"
    sh.write_text(command + "\n", encoding="utf-8")
    py.write_text(script + "\n", encoding="utf-8")
    return sh, py


# --- recent.json -----------------------------------------------------------------

MAX_RECENT = 10


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "pyfds-evac"


class Recent:
    """``recent.json``: the last runs (scenario, FDS folder, status) and theme.

    A file that cannot be read or written is ignored: the TUI works
    without it.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "recent.json"
        self.data: dict[str, Any] = {"theme": None, "runs": []}
        with contextlib.suppress(OSError, ValueError, TypeError):
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        if not isinstance(self.data.get("runs"), list):
            self.data["runs"] = []

    @property
    def theme(self) -> str | None:
        theme = self.data.get("theme")
        return theme if theme in THEMES else None

    @property
    def runs(self) -> list[dict[str, Any]]:
        return [r for r in self.data["runs"] if isinstance(r, dict)]

    def set_theme(self, theme: str) -> None:
        self.data["theme"] = theme
        self._save()

    def add(self, scenario: str, fds_dir: str | None, status: str, date: str) -> None:
        entry = {"scenario": scenario, "fds_dir": fds_dir, "status": status}
        entry["date"] = date
        runs = [
            r
            for r in self.runs
            if (r.get("scenario"), r.get("fds_dir")) != (scenario, fds_dir)
        ]
        self.data["runs"] = [entry, *runs][:MAX_RECENT]
        self._save()

    def _save(self) -> None:
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.path)
