"""Run manifest: the provenance record written next to a trajectory file.

The manifest answers "which code, which inputs, which FDS build produced
this run?" so a result can be traced and reproduced later.
"""

import hashlib
import json
import pathlib
import subprocess
import tomllib
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from .smoke_speed import ConstantExtinctionField

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


def fds_dir_from_models(*models: Any) -> str | None:
    """Return the first FDS directory any of *models* reads, or None.

    The directory a field was loaded from (``field.fds_dir``, set by
    ``from_fds``) wins over ``config.fds_dir``. A model sampling a
    ``ConstantExtinctionField`` reads no FDS output, so its ``fds_dir``
    (possibly a placeholder such as ``"."``) is skipped.
    """
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
    fds_dir: str | None,
    uv_lock: pathlib.Path | None = None,
    project_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Collect the provenance fields for one run."""
    root = project_root if project_root is not None else find_project_root()
    lock = uv_lock if uv_lock is not None else find_uv_lock(root)
    commit, dirty = git_state(root)
    return {
        "versions": package_versions(),
        "uv_lock_sha256": sha256_of(lock),
        "git_commit": commit,
        "git_dirty": dirty,
        "seed": seed,
        "scenario_path": scenario_path,
        "fds_dir": fds_dir,
        "fds_version": fds_version(fds_dir),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def manifest_path_for(trajectory_file: str | pathlib.Path) -> pathlib.Path:
    """Return the manifest path that sits next to *trajectory_file*."""
    trajectory = pathlib.Path(trajectory_file)
    return trajectory.with_name(trajectory.stem + MANIFEST_SUFFIX)


def write_manifest(trajectory_file: str | pathlib.Path, **fields: Any) -> str:
    """Write the manifest next to *trajectory_file* and return its path."""
    path = manifest_path_for(trajectory_file)
    path.write_text(json.dumps(build_manifest(**fields), indent=2) + "\n")
    return str(path)
