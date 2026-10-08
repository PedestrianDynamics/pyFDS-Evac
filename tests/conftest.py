"""Shared test setup."""

import os
import shutil
from pathlib import Path

import pytest

SCIEBO = Path.home() / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
# The external FDS output the ``external_data`` tests read, resolved as the
# test modules resolve it. A test run must leave these folders unchanged.
EXTERNAL_DATA = (
    Path(
        os.environ.get(
            "HEAT_RADIOMETER_DATA", SCIEBO / "fds-evac-data" / "heat_radiometer"
        )
    ),
    Path(
        os.environ.get(
            "T_JUNCTION_FDS", SCIEBO / "fds-evac-data" / "t_junction" / "fire_2MW_PVC"
        )
    ),
)


@pytest.fixture(autouse=True)
def _plain_help(monkeypatch):
    """Render ``--help`` without ANSI styles, also under ``pytest -s``.

    The CLI's rich help formatter styles its output on a terminal; tests
    that search the help text need the plain text. A dumb terminal turns
    the styles off even when FORCE_COLOR is set.
    """
    monkeypatch.setenv("TERM", "dumb")


def _link_or_copy(src: str, dst: str) -> None:
    # fdsreader writes its cache next to the .smv, in the folder of the
    # path it opens; a real .smv keeps that folder the mirror.
    if src.endswith(".smv"):
        shutil.copy2(src, dst)
        return
    try:
        os.symlink(src, dst)
    except OSError:
        # No symlink privilege (Windows without Developer Mode): copy.
        # Never a hard link, which shares the source file.
        shutil.copy2(src, dst)


@pytest.fixture(scope="session")
def fds_read_only(tmp_path_factory):
    """Map external FDS output to a mirror in a temporary folder.

    fdsreader writes ``<CHID>.pickle`` next to the ``.smv`` it reads, and
    turning its cache off deletes an existing pickle instead. The mirror
    has real folders, a copied ``.smv`` and links to the data files, but
    no pickle, so fdsreader reads the data and writes its cache only in
    the mirror. One mirror per folder and session. The links isolate the
    cache, not writes to the data files, which fdsreader only reads.
    """
    mirrors: dict[Path, Path] = {}

    def mirror(src: Path) -> Path:
        src = Path(src).absolute()
        if src not in mirrors:
            dst = tmp_path_factory.mktemp("fds_read_only") / src.name
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns("*.pickle"),
                copy_function=_link_or_copy,
            )
            mirrors[src] = dst
        return mirrors[src]

    return mirror


def _manifest(root: Path) -> dict[str, tuple[int, int]]:
    """(size, mtime in ns) of every file under *root*, by relative path."""
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture(autouse=True)
def _external_data_unchanged(request):
    """Fail an ``external_data`` test that changes the external data folders."""
    if request.node.get_closest_marker("external_data") is None:
        yield
        return
    roots = [root for root in EXTERNAL_DATA if root.is_dir()]
    before = {root: _manifest(root) for root in roots}
    yield
    for root in roots:
        after = _manifest(root)
        changed = sorted(
            name
            for name in before[root].keys() | after.keys()
            if before[root].get(name) != after.get(name)
        )
        assert not changed, f"files changed in {root} during the test: {changed}"
