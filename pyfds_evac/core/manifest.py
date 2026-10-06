"""Run manifest: the provenance record written next to a trajectory file.

The manifest answers "which code, which inputs, which FDS build produced
this run?" so a result can be traced and reproduced later.
"""

import dataclasses
import hashlib
import json
import pathlib
import subprocess
import tomllib
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from .fed import heat_endpoint_validity

MANIFEST_SUFFIX = ".manifest.json"

_TRACKED_DISTRIBUTIONS = ("pyfds-evac", "jupedsim", "fdsreader", "fdsvismap")

_PROJECT_NAME = "pyfds-evac"
_SOURCE_DIR = pathlib.Path(__file__).resolve().parents[1]
_GIT_TIMEOUT_S = 2.0


def package_versions() -> dict[str, str | None]:
    """Return the installed version of each tracked distribution, or None."""
    return {name: _version_or_none(name) for name in _TRACKED_DISTRIBUTIONS}


def _version_or_none(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _is_project_root(directory: pathlib.Path) -> bool:
    """Return True if *directory* holds the pyfds-evac ``pyproject.toml``."""
    pyproject = directory / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        data = tomllib.loads(pyproject.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return data.get("project", {}).get("name") == _PROJECT_NAME


def find_project_root(start: str | pathlib.Path | None = None) -> pathlib.Path | None:
    """Return the pyfds-evac source checkout at or above *start*, or None.

    *start* defaults to the package source directory, so an editable
    install resolves to its checkout and an installed wheel to None.
    """
    base = pathlib.Path(start if start is not None else _SOURCE_DIR).resolve()
    for directory in (base, *base.parents):
        if _is_project_root(directory):
            return directory
    return None


def find_uv_lock(start: str | pathlib.Path | None = None) -> pathlib.Path | None:
    """Return the pyfds-evac ``uv.lock`` at or above *start*, or None.

    A ``uv.lock`` of any other project is never returned.
    """
    root = find_project_root(start)
    if root is None:
        return None
    lock = root / "uv.lock"
    return lock if lock.is_file() else None


def _git(root: pathlib.Path, *args: str) -> str | None:
    """Return the stripped stdout of ``git args`` in *root*, or None on failure."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def git_state(root: pathlib.Path | None) -> tuple[str | None, bool | None]:
    """Return ``(commit, dirty)`` of the checkout at *root*, or ``(None, None)``.

    ``dirty`` counts changes to tracked files only.
    """
    if root is None:
        return None, None
    commit = _git(root, "rev-parse", "HEAD")
    if not commit:
        return None, None
    status = _git(root, "status", "--porcelain", "--untracked-files=no")
    return commit, (None if status is None else bool(status))


def sha256_of(path: pathlib.Path | None) -> str | None:
    """Return the hex sha256 of *path*, or None when there is no file."""
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_settings(
    *,
    seed: int | None,
    smoke_speed_model: Any = None,
    fed_model: Any = None,
    heat_fed_model: Any = None,
    tenability_config: Any = None,
    reroute_config: Any = None,
    vis_model: Any = None,
    smoke_blind: bool = False,
    replay_exits: Any = None,
    require_fds_coverage: bool = False,
) -> dict[str, Any]:
    """What a run used: the seed, and the models with their parameters.

    Read from the objects ``run_scenario`` received, never from the options
    that produced them; a model that was not given is None (provisional).
    """
    return {
        "seed": seed,
        "smoke_speed": _smoke_settings(smoke_speed_model),
        "gas_fed": _gas_settings(fed_model),
        "heat_fed": _heat_settings(heat_fed_model),
        "tenability": _plain(tenability_config),
        "rerouting": _reroute_settings(reroute_config),
        "visibility": _vis_settings(vis_model),
        "smoke_blind": bool(smoke_blind),
        "replay_exits": replay_exits is not None,
        "require_fds_coverage": bool(require_fds_coverage),
    }


def _plain(obj: Any) -> dict[str, Any] | None:
    """The fields of a dataclass instance as a dict, or None."""
    if obj is None:
        return None
    return dataclasses.asdict(obj)


def _fed_config(config: Any) -> dict[str, Any]:
    return {
        "update_interval_s": getattr(config, "update_interval_s", None),
        "slice_height_m": getattr(config, "slice_height_m", None),
    }


def _smoke_settings(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    from .smoke_speed import ConstantExtinctionField  # numpy: not on --help

    field = getattr(model, "field", None)
    constant = isinstance(field, ConstantExtinctionField)
    return {
        "source": "constant" if constant else "fds",
        "extinction_per_m": getattr(field, "extinction_per_m", None),
        **_fed_config(getattr(model, "config", None)),
    }


def _gas_settings(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    config = getattr(model, "config", None)
    return {
        **_fed_config(config),
        "o2_threshold_percent": getattr(config, "o2_threshold_percent", None),
    }


_HEAT_ATTRIBUTES = (
    "method",
    "endpoint",
    "clothing",
    "emissivity",
    "convective_coefficient",
    "skin_temperature_celsius",
    "radiant_source",
    "u_factor",
    "regime",
    "view_factor",
    "layer_emissivity",
    "layer_height_m",
)


def _heat_settings(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    settings = {name: getattr(model, name, None) for name in _HEAT_ATTRIBUTES}
    return {**settings, **_fed_config(getattr(model, "config", None))}


def _reroute_settings(config: Any) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "reevaluation_interval_s": config.reevaluation_interval_s,
        "exit_switch_anchor": getattr(config, "exit_switch_anchor", None),
        "cost_config": _plain(getattr(config, "cost_config", None)),
    }


def _vis_settings(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    parameters = getattr(model, "parameters", None)
    if parameters is not None:
        return dict(parameters)
    return {"kind": "smoky" if getattr(model, "from_fds", False) else "clear-air"}


def fds_dir_from_models(*models: Any) -> str | None:
    """Return the first FDS directory any of *models* reads, or None.

    The directory a field was loaded from (``field.fds_dir``, set by
    ``from_fds``) wins over ``config.fds_dir``. A model sampling a
    ``ConstantExtinctionField`` reads no FDS output, so its ``fds_dir``
    (possibly a placeholder such as ``"."``) is skipped.
    """
    from .smoke_speed import ConstantExtinctionField

    for model in models:
        field = getattr(model, "field", None)
        if isinstance(field, ConstantExtinctionField):
            continue
        config = getattr(model, "config", None)
        fds_dir = getattr(field, "fds_dir", None) or getattr(config, "fds_dir", None)
        if fds_dir:
            return str(pathlib.Path(fds_dir).resolve())
    return None


def fds_version(fds_dir: str | pathlib.Path | None) -> str | None:
    """Return the FDS version from the ``FDSVERSION`` block of the case's .smv."""
    if fds_dir is None:
        return None
    directory = pathlib.Path(fds_dir)
    if not directory.is_dir():
        return None
    smv_files = sorted(directory.glob("*.smv"))
    if not smv_files:
        return None
    return parse_fds_version(smv_files[0].read_text(errors="replace"))


def parse_fds_version(smv_text: str) -> str | None:
    """Return the first non-empty line after ``FDSVERSION``, or None."""
    lines = iter(smv_text.splitlines())
    for line in lines:
        if line.strip() == "FDSVERSION":
            break
    else:
        return None
    for line in lines:
        if line.strip():
            return line.strip()
    return None


def build_manifest(
    *,
    seed: int | None,
    scenario_path: str | None,
    agent_seeding: str | None = None,
    fds_dir: str | None,
    uv_lock: pathlib.Path | None = None,
    project_root: pathlib.Path | None = None,
    heat_endpoint: str | None = None,
    heat_fed_method: str | None = None,
    heat_flux_parameters: dict[str, Any] | None = None,
    heat_clothing: str | None = None,
    heat_fed_threshold_override: float | None = None,
    smoke_blind: bool = False,
    replay_exits: dict[str, Any] | None = None,
    fds_coverage: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    sfm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect the provenance fields for one run.

    ``heat_endpoint`` and ``heat_validity`` are recorded only when
    ``--heat-endpoint`` was given; ``heat_fed_method`` and
    ``heat_flux_parameters`` only with ``--heat-fed-method total-flux``.
    ``heat_clothing`` is recorded when the ISO 13571:2012 convective law is
    in use, ``heat_fed_threshold_override`` only when the heat threshold was
    set apart from the gas threshold, a departure from ISO 13571:2012 §5.4.
    ``agent_seeding`` names how per-agent and per-distribution draws are
    derived from the seed (see ``agent_seed.SEEDING_SCHEME``); runs of
    another scheme draw differently under the same seed.
    ``smoke_blind`` and ``replay_exits`` are recorded only when on (#341);
    ``replay_exits`` holds the replayed agent count and a sha256 of the rows.
    ``fds_coverage`` is the setup check of the scenario geometry against the
    FDS slices (``FdsCoverageReport.to_dict``), recorded when FDS is sampled.
    ``outcome`` is how the run ended: ``status`` (``"completed"`` or
    ``"incomplete"``), ``agents_remaining`` and ``agents_not_spawned``.
    ``sfm`` is what a SocialForceModel run gave JuPedSim: ``body_force``,
    ``friction``, ``friction_requested`` and ``friction_clamped``
    (``scenario.sfm_model_settings``), recorded for that model only.
    """
    root = project_root if project_root is not None else find_project_root()
    lock = uv_lock if uv_lock is not None else find_uv_lock(root)
    commit, dirty = git_state(root)
    manifest = {
        "versions": package_versions(),
        "uv_lock_sha256": sha256_of(lock),
        "git_commit": commit,
        "git_dirty": dirty,
        "seed": seed,
        "agent_seeding": agent_seeding,
        "scenario_path": scenario_path,
        "fds_dir": fds_dir,
        "fds_version": fds_version(fds_dir),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if heat_endpoint is not None:
        manifest["heat_endpoint"] = heat_endpoint
        manifest["heat_validity"] = heat_endpoint_validity()
    if heat_fed_method == "total-flux":
        manifest["heat_fed_method"] = heat_fed_method
        manifest["heat_flux_parameters"] = heat_flux_parameters
    if heat_clothing is not None:
        manifest["heat_clothing"] = heat_clothing
    if heat_fed_threshold_override is not None:
        manifest["heat_fed_threshold_override"] = heat_fed_threshold_override
    if smoke_blind:
        manifest["smoke_blind"] = True
    if replay_exits:
        manifest["replay_exits"] = replay_exits
    if fds_coverage is not None:
        manifest["fds_coverage"] = fds_coverage
    if outcome is not None:
        manifest["outcome"] = outcome
    if sfm is not None:
        manifest["sfm"] = sfm
    return manifest


def manifest_path_for(trajectory_file: str | pathlib.Path) -> pathlib.Path:
    """Return the manifest path that sits next to *trajectory_file*."""
    trajectory = pathlib.Path(trajectory_file)
    return trajectory.with_name(trajectory.stem + MANIFEST_SUFFIX)


def write_manifest(trajectory_file: str | pathlib.Path, **fields: Any) -> str:
    """Write the manifest next to *trajectory_file* and return its path."""
    path = manifest_path_for(trajectory_file)
    path.write_text(json.dumps(build_manifest(**fields), indent=2) + "\n")
    return str(path)
