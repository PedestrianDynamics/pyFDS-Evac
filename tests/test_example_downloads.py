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
    left_out = {path for path, _ in SPEC[name].get("not_in_zip", [])}
    for path in sorted(named):
        assert (ROOT / path).exists(), f"the page names {path}, not in the repo"
        if path in left_out:
            continue
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


@pytest.mark.parametrize("name", SPEC)
def test_zip_holds_no_fds_output(built, name):
    """Users run FDS themselves; the zips hold inputs only."""
    bundler = _bundler()
    output = [e for e in _names(built[0][0], name) if bundler.FDS_OUTPUT.search(e)]
    assert not output, output


@pytest.mark.parametrize("name", SPEC)
def test_left_out_paths_are_fds_output_written_by_a_step(name):
    """A page path left out of the zip is FDS output that a README step writes."""
    commands = "\n".join(line for _, lines in SPEC[name]["steps"] for line in lines)
    for path, _ in SPEC[name].get("not_in_zip", []):
        files = [p for p in (ROOT / path).rglob("*") if p.is_file()]
        assert files and all(_bundler().FDS_OUTPUT.search(p.name) for p in files)
        assert "fds " in commands, f"{name}: no step runs FDS for {path}"


def test_schroeder2020_names_the_release_and_ships_none_of_it(built):
    """The release (doi:10.5281/zenodo.3875550) has no licence file."""
    readme = _readme(built[0][0], "study-schroeder2020")
    assert "doi:10.5281/zenodo.3875550" in " ".join(readme.split())
    for entry in _names(built[0][0], "study-schroeder2020"):
        assert entry.startswith(("assets/schroeder2020_room/", "scripts/")) or (
            entry in {"README.txt", "LICENSE", "requirements.txt", "run.py"}
        ), entry


def test_schroeder2020_generators_write_the_committed_inputs(tmp_path):
    """The four generators write every generated input byte for byte."""
    folder = ROOT / "assets" / "schroeder2020_room"
    for script in ("make_decks_rel", "make_configs_rel", "make_decks", "make_configs"):
        subprocess.run(
            [sys.executable, str(folder / f"{script}.py"), str(tmp_path)],
            check=True,
            capture_output=True,
        )
    written = sorted(
        p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()
    )
    assert len(written) == 139
    for path in written:
        assert (tmp_path / path).read_bytes() == (folder / path).read_bytes(), path
    committed = {
        p.relative_to(folder)
        for p in folder.rglob("*")
        if p.is_file() and p.suffix in {".fds", ".json", ".wkt"}
    }
    hand_written = {Path("hrr060_1door_pert/hrr060_1door_pert.fds")}
    assert committed == set(written) | hand_written


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


@pytest.mark.parametrize("name", ["walkthrough", "rset-ensemble"])
def test_example_prints_the_expected_result(name):
    """Run on the FDS output in the repository, which FDS rewrites byte for byte."""
    script = SPEC[name]["files"][0][0]
    assert script.startswith("examples/")
    out = _run(script)
    for line in SPEC[name]["expected"]:
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
def test_first_fds_case_fire_result(fds_read_only):
    """The fire result on the page and in the README, from the FDS output."""
    out = _run("examples/first_fds_case.py", str(fds_read_only(T_JUNCTION_FDS)))
    for line in SPEC["first-fds-case"]["expected"]:
        assert line in out


NOT_RECHECKED = {
    "walkthrough",
    "rset-ensemble",
    "iso-test-18",
    "iso-test-19",
    "heat-radiometer",
    "study-schroeder2020",
    "study-schroeder2015",
}


def test_results_note_marks_the_results_not_rechecked_for_0_4():
    """Results made before 0.4.0's routing changes say so on their page."""
    notes = {name: ex.get("results_note") for name, ex in SPEC.items()}
    assert {n for n, note in notes.items() if note} == NOT_RECHECKED
    for name in NOT_RECHECKED:
        assert notes[name] == "Not re-checked for 0.4.0."


def test_results_note_is_rendered_under_the_commit():
    """The shortcode shows the note right after "made at commit ..."."""
    html = (ROOT / "site" / "layouts" / "shortcodes" / "example-files.html").read_text()
    commit = "made at commit <code>{{ $ex.results_commit }}</code></span>"
    note = (
        '{{ with $ex.results_note }}<br><span class="docs-files__note">'
        "{{ . }}</span>{{ end }}"
    )
    assert commit + note in html


@pytest.mark.skipif(
    subprocess.run(["which", "hugo"], capture_output=True).returncode != 0
    or not (ROOT / "site" / "data" / "example_bundles.json").is_file(),
    reason="needs hugo and the bundles of scripts/docs/bundle_examples.py",
)
def test_results_note_appears_on_the_built_page(tmp_path):
    """Hugo renders the note on a noted page and nothing on the others."""
    subprocess.run(
        ["hugo", "--quiet", "--destination", str(tmp_path)],
        cwd=ROOT / "site",
        check=True,
        capture_output=True,
    )
    page = tmp_path / "docs" / "getting-started" / "walkthrough" / "index.html"
    commit = SPEC["walkthrough"]["results_commit"]
    assert (
        f'made at commit <code>{commit}</code></span><br><span class="docs-files__note">'
        "Not re-checked for 0.4.0.</span>"
    ) in page.read_text()
    quick = tmp_path / "docs" / "getting-started" / "quickstart" / "index.html"
    assert "Not re-checked" not in quick.read_text()
