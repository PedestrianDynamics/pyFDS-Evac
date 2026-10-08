"""Checks of ``scripts/verification/familiarity_grid_study.py`` (#168)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _study_module():
    path = Path("scripts/verification/familiarity_grid_study.py")
    spec = importlib.util.spec_from_file_location("familiarity_grid_study", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_commit_is_unknown_outside_a_git_checkout(tmp_path, monkeypatch):
    """An unpacked archive has no git history; the driver still runs."""
    study = _study_module()
    monkeypatch.setattr(study, "ROOT", tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert study.commit() == "unknown"


def test_commit_names_the_checkout():
    study = _study_module()
    assert study.commit() != "unknown"
