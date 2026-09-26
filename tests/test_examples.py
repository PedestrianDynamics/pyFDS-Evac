"""The scripts in ``examples/`` run, and the docs pages quote them verbatim.

Each page in ``docs/`` pastes code from its script by hand. This test fails
when a fenced ``python`` block on a page no longer occurs, character for
character, in the script, so the two cannot drift apart unnoticed. It checks
that the examples run, not that their results are right.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PAGES = {
    "quickstart.py": "quickstart.md",
    "walkthrough.py": "walkthrough.md",
    "rset_ensemble.py": "howto-rset-ensemble.md",
}

_PYTHON_BLOCK = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture(scope="module")
def runs():
    """Run each example once, from the repository root like the pages say."""
    return {script: _run(f"examples/{script}") for script in PAGES}


@pytest.mark.parametrize("script", PAGES)
def test_example_runs(runs, script):
    proc = runs[script]
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("script, page", PAGES.items())
def test_page_code_occurs_verbatim_in_script(script, page):
    source = (ROOT / "examples" / script).read_text()
    blocks = _PYTHON_BLOCK.findall((ROOT / "docs" / page).read_text())
    assert blocks, f"{page} has no python block"
    for block in blocks:
        assert block in source, f"{page} block not found in {script}:\n{block}"


def test_walkthrough_shows_the_silent_fed_failure(runs):
    """The checkpoint on the page: FED is off, and only the log says so."""
    proc = runs["walkthrough.py"]
    assert "FED is disabled for" in proc.stderr
    assert "before: fed_model = None" in proc.stdout
    assert "after:  fed_history = None, 'fed_max' in metrics = False" in proc.stdout
    assert "FdsFedField.from_fds: IndexError" in proc.stdout


def test_walkthrough_inventory_command():
    """The shell command in step 1 of the walkthrough."""
    proc = _run(
        "run.py",
        "--scenario",
        "assets/iso_table22_coupled/config_a.json",
        "--fds-dir",
        "assets/iso_table22_coupled/fds/a",
        "--inspect-fds",
    )
    assert proc.returncode == 0, proc.stderr
    assert '"CARBON MONOXIDE VOLUME FRACTION"' in proc.stdout
