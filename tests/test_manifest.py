"""Run manifest written next to the trajectory by ``run_scenario``."""

import json
import pathlib
from types import SimpleNamespace

import pytest

from pyfds_evac.core import manifest
from pyfds_evac.core.smoke_speed import (
    ConstantExtinctionField,
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

SMV_HEAD = "TITLE\n case \n\nFDSVERSION\nFDS-6.10.1-0-g12efa16-release\n\nENDF\n"


def test_parse_fds_version():
    assert manifest.parse_fds_version(SMV_HEAD) == "FDS-6.10.1-0-g12efa16-release"


def test_parse_fds_version_missing_block():
    assert manifest.parse_fds_version("TITLE\n case\n") is None


def test_fds_version_reads_smv_in_dir(tmp_path):
    (tmp_path / "case.smv").write_text(SMV_HEAD)
    assert manifest.fds_version(tmp_path) == "FDS-6.10.1-0-g12efa16-release"


@pytest.mark.parametrize("fds_dir", [None, "does/not/exist"])
def test_fds_version_none_without_case(fds_dir):
    assert manifest.fds_version(fds_dir) is None


def test_fds_version_none_without_smv(tmp_path):
    assert manifest.fds_version(tmp_path) is None


def test_fds_dir_from_models_skips_unset_and_constant(tmp_path):
    unset = SimpleNamespace(config=SimpleNamespace(fds_dir=None))
    constant = SimpleNamespace(
        field=ConstantExtinctionField(1.0), config=SimpleNamespace(fds_dir=".")
    )
    fed = SimpleNamespace(config=SimpleNamespace(fds_dir=str(tmp_path)))
    found = manifest.fds_dir_from_models(None, unset, constant, fed)
    assert found == str(tmp_path.resolve())
    assert manifest.fds_dir_from_models(None, unset, constant) is None


def _project(root, name):
    (root / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n')
    (root / "uv.lock").write_text("lock")
    nested = root / "pyfds_evac" / "core"
    nested.mkdir(parents=True)
    return nested


def test_find_uv_lock_walks_up_to_pyfds_evac_project(tmp_path):
    nested = _project(tmp_path, "pyfds-evac")
    assert manifest.find_uv_lock(nested) == tmp_path / "uv.lock"


def test_find_uv_lock_ignores_unrelated_project(tmp_path):
    nested = _project(tmp_path, "someone-else")
    assert manifest.find_uv_lock(nested) is None


def test_find_uv_lock_ignores_lock_without_pyproject(tmp_path):
    (tmp_path / "uv.lock").write_text("lock")
    assert manifest.find_uv_lock(tmp_path) is None


def test_git_state_outside_a_repo(tmp_path):
    assert manifest.git_state(None) == (None, None)
    assert manifest.git_state(tmp_path) == (None, None)


def test_fds_dir_from_models_prefers_field_dir(tmp_path):
    field = SimpleNamespace(fds_dir=str(tmp_path))
    model = SimpleNamespace(field=field, config=SimpleNamespace(fds_dir=None))
    assert manifest.fds_dir_from_models(model) == str(tmp_path.resolve())
    model.config.fds_dir = "elsewhere"
    assert manifest.fds_dir_from_models(model) == str(tmp_path.resolve())


def test_from_fds_records_source_dir():
    case = "assets/iso_table21_coupled/fds"
    model = SmokeSpeedModel(ExtinctionField.from_fds(case), SmokeSpeedConfig())
    assert model.field.fds_dir == case
    found = manifest.fds_dir_from_models(model)
    assert found == str(pathlib.Path(case).resolve())
    assert manifest.fds_version(found) == "FDS-6.10.1-0-g12efa16-release"


def test_build_manifest_fields(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text("lock")
    (tmp_path / "case.smv").write_text(SMV_HEAD)
    data = manifest.build_manifest(
        seed=7,
        scenario_path="s.json",
        fds_dir=str(tmp_path),
        uv_lock=lock,
        project_root=tmp_path,
    )
    assert set(data["versions"]) == {"pyfds-evac", "jupedsim", "fdsreader", "fdsvismap"}
    assert data["versions"]["pyfds-evac"] is not None
    assert data["uv_lock_sha256"] == manifest.sha256_of(lock)
    assert len(data["uv_lock_sha256"]) == 64
    assert data["git_commit"] is None
    assert data["git_dirty"] is None
    assert data["seed"] == 7
    assert data["scenario_path"] == "s.json"
    assert data["fds_version"] == "FDS-6.10.1-0-g12efa16-release"
    assert data["created_utc"].endswith("+00:00")


def test_build_manifest_without_lock_or_fds(tmp_path):
    data = manifest.build_manifest(
        seed=None, scenario_path=None, fds_dir=None, uv_lock=tmp_path / "missing"
    )
    assert data["uv_lock_sha256"] is None
    assert data["fds_version"] is None


def _short_constant_run():
    from pyfds_evac import load_scenario, run_scenario

    scenario = load_scenario("assets/ISO-table21")
    scenario.set_max_time(2.0)
    model = SmokeSpeedModel(ConstantExtinctionField(1.0), SmokeSpeedConfig())
    return scenario, run_scenario(scenario, seed=420, smoke_speed_model=model)


def test_run_scenario_writes_manifest():
    scenario, result = _short_constant_run()
    try:
        assert result.manifest_file is not None
        data = json.loads(pathlib.Path(result.manifest_file).read_text())
        assert data["seed"] == 420
        assert data["scenario_path"] == scenario.source_path
        assert data["fds_version"] is None
        assert result.smoke_history
    finally:
        manifest_file = result.manifest_file
        result.cleanup()
    assert not pathlib.Path(manifest_file).exists()


@pytest.mark.parametrize("error", [OSError("disk full"), ValueError("bad value")])
def test_manifest_failure_keeps_the_run(monkeypatch, caplog, error):
    from pyfds_evac.core import scenario as scenario_module

    def _fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(scenario_module, "write_manifest", _fail)
    _, result = _short_constant_run()
    try:
        assert result.manifest_file is None
        assert result.sqlite_file and pathlib.Path(result.sqlite_file).exists()
        assert "run manifest" in caplog.text
    finally:
        result.cleanup()


def test_cli_copies_manifest_beside_output_sqlite(tmp_path):
    import run

    _, result = _short_constant_run()
    output = tmp_path / "out" / "trajectory.sqlite"
    opts = run._build_parser().parse_args(
        ["--scenario", "s.json", "--output-sqlite", str(output), "--cleanup"]
    )
    artifacts = run.apply_outputs(result, None, opts, log=lambda *_: None)

    copied = tmp_path / "out" / "trajectory.manifest.json"
    assert output.exists()
    assert json.loads(copied.read_text())["seed"] == 420
    assert f"Run manifest: {copied}" in artifacts
    assert result.manifest_file is None
