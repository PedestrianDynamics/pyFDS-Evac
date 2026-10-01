"""The example zips build reproducibly and hold what their pages use.

``scripts/docs/bundle_examples.py`` zips the inputs of each page listed in
``site/data/examples.toml``. These tests check that every zip is built, that
two builds give the same bytes, that each zip holds every repository file
its page names, and that the README.txt states the versions of the commit
and the result the page shows.
"""

import importlib.util
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = tomllib.loads((ROOT / "site" / "data" / "examples.toml").read_text())
SCIEBO = Path.home() / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
T_JUNCTION_FDS = Path(
    os.environ.get(
        "T_JUNCTION_FDS", SCIEBO / "fds-evac-data" / "t_junction" / "fire_2MW_PVC"
    )
)
# A repository path on a page: `assets/...`, `examples/...`, `scripts/...`
# or `run.py`, in backticks or in a GitHub link. Paths under site/ are
# outputs, not inputs.
_PAGE_PATH = re.compile(
    r"(?:`|blob/main/)((?:assets|examples|scripts)/[\w./-]+?|run\.py)/?(?=[`)\s])"
)


def _bundler():
    path = ROOT / "scripts" / "docs" / "bundle_examples.py"
    spec = importlib.util.spec_from_file_location("bundle_examples", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Two builds of the same commit, into separate folders."""
    bundler = _bundler()
    runs = []
    for label in ("a", "b"):
        out = tmp_path_factory.mktemp(label)
        facts = bundler.build(out, out / "facts.json")
        runs.append((out, facts))
    return runs


def _names(out: Path, name: str) -> list[str]:
    with zipfile.ZipFile(out / SPEC[name]["zip"]) as archive:
        prefix = Path(SPEC[name]["zip"]).stem + "/"
        return [n.removeprefix(prefix) for n in archive.namelist()]


def _readme(out: Path, name: str) -> str:
    stem = Path(SPEC[name]["zip"]).stem
    with zipfile.ZipFile(out / SPEC[name]["zip"]) as archive:
        return archive.read(f"{stem}/README.txt").decode()


@pytest.mark.parametrize("name", SPEC)
def test_zip_is_built(built, name):
    out, facts = built[0]
    path = out / SPEC[name]["zip"]
    assert path.is_file()
    assert facts[name]["bytes"] == path.stat().st_size


@pytest.mark.parametrize("name", SPEC)
def test_two_builds_give_the_same_bytes(built, name):
    (out_a, _), (out_b, _) = built
    zip_name = SPEC[name]["zip"]
    assert (out_a / zip_name).read_bytes() == (out_b / zip_name).read_bytes()


@pytest.mark.parametrize("name", SPEC)
def test_zip_holds_every_file_its_page_names(built, name):
    page = (ROOT / SPEC[name]["source"]).read_text()
    named = set(_PAGE_PATH.findall(page))
    assert named, f"{SPEC[name]['source']} names no repository file"
    entries = _names(built[0][0], name)
    for path in sorted(named):
        assert (ROOT / path).exists(), f"the page names {path}, not in the repo"
        if (ROOT / path).is_dir():
            assert any(e.startswith(path + "/") for e in entries), path
        else:
            assert path in entries, f"{path} is on the page but not in the zip"


@pytest.mark.parametrize("name", SPEC)
def test_readme_states_commit_versions_and_result(built, name):
    readme = _readme(built[0][0], name)
    bundler = _bundler()
    versions = bundler._locked_versions()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    assert sha in readme
    for package in bundler.KEY_PACKAGES:
        assert re.search(
            rf"^  {package} +{re.escape(versions[package])}$", readme, re.M
        )
    for line in SPEC[name]["expected"]:
        assert f"  {line}\n" in readme
    assert "CC-BY-4.0" in readme and "MIT" in readme
    if SPEC[name]["fds"]:
        assert SPEC[name]["fds"] in readme


def _run(*args: str) -> str:
    proc = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_quickstart_prints_the_expected_result():
    """The README's expected lines are what the example prints on this commit."""
    out = _run("examples/quickstart.py")
    for line in SPEC["quickstart"]["expected"]:
        assert line in out


def test_first_fds_case_clear_air_result():
    out = _run("examples/first_fds_case.py")
    line = "evacuated: 144/150 in 300 s"
    assert line in out
    assert line in SPEC["first-fds-case"]["expected_note"]


@pytest.mark.external_data
@pytest.mark.skipif(
    not (T_JUNCTION_FDS / "t_junction.smv").is_file(),
    reason="t_junction FDS output not available",
)
def test_first_fds_case_fire_result():
    """The fire result on the page and in the README, from the FDS output."""
    out = _run("examples/first_fds_case.py", str(T_JUNCTION_FDS))
    for line in SPEC["first-fds-case"]["expected"]:
        assert line in out
