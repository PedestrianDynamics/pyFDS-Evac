"""Shared test setup."""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from packaging.version import Version

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


#: fdsreader versions whose cache the worker patch below was checked against.
FDSREADER_TESTED = (Version("1.11.7"), Version("1.15"))


def check_fdsreader_version(version: str) -> None:
    """Stop the run if the worker cache patch was not checked on *version*."""
    low, high = FDSREADER_TESTED
    if not low <= Version(version) < high:
        raise pytest.UsageError(
            "cannot move the fdsreader cache per xdist worker: the patch in "
            f"tests/conftest.py was checked on fdsreader >={low},<{high}, "
            f"found {version}"
        )


def pytest_configure(config):
    """Give each xdist worker its own fdsreader cache.

    fdsreader 1.11.7 to 1.14.0 write ``<CHID>.pickle`` next to the ``.smv``,
    rewrites it on every open after the first in a process, and deletes
    a pickle it cannot read. Workers opening the same tracked case then
    read each other's half-written pickle and race on deleting it
    (FileNotFoundError). Each worker keeps the cache in its own folder.
    Child processes, which this patch does not reach, open the tracked
    cases only in tests marked ``xdist_group("fds_assets_child")``;
    ``--dist loadgroup`` runs those one after another in one worker.
    Upstream issue: none yet. Remove when fdsreader writes its cache
    atomically or lets the cache folder be set.
    """
    worker = getattr(config, "workerinput", {}).get("workerid")
    if worker is None:
        return
    import fdsreader
    from fdsreader.simulation import Simulation

    check_fdsreader_version(fdsreader.__version__)
    if not hasattr(Simulation, "_get_pickle_filename"):
        raise pytest.UsageError(
            "cannot move the fdsreader cache per xdist worker: fdsreader "
            f"{fdsreader.__version__} has no Simulation._get_pickle_filename"
        )
    cache = Path(tempfile.mkdtemp(prefix=f"fdsreader-{worker}-"))
    config.add_cleanup(lambda: shutil.rmtree(cache, ignore_errors=True))

    def pickle_filename(cls, root_path: str, chid: str) -> str:
        key = hashlib.sha256(os.fsencode(os.path.abspath(root_path))).hexdigest()
        folder = cache / key[:16]
        folder.mkdir(exist_ok=True)
        return str(folder / f"{chid}.pickle")

    Simulation._get_pickle_filename = classmethod(pickle_filename)


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


class SearchPops:
    """Counts the heap pops of ``StageGraph._dijkstra``."""

    #: No test graph needs more; a search past it is not going to stop.
    LIMIT = 10_000

    def __init__(self) -> None:
        self.count = 0


@pytest.fixture
def bounded_search(monkeypatch):
    """Fail a ``StageGraph`` search that pops the heap too often.

    A relaxation that accepts equal cost never ends on a zero-weight
    self-loop. Without a bound that is a hang, which a mutation run cannot
    tell from a slow test; with it, the search fails the test. Returns the
    pop counter.
    """
    import heapq
    from types import SimpleNamespace

    from pyfds_evac.core import route_graph

    pops = SearchPops()

    def counted_pop(heap):
        pops.count += 1
        if pops.count > SearchPops.LIMIT:
            raise AssertionError(
                f"StageGraph search popped its heap more than {SearchPops.LIMIT} times"
            )
        return heapq.heappop(heap)

    monkeypatch.setattr(
        route_graph,
        "heapq",
        SimpleNamespace(heappush=heapq.heappush, heappop=counted_pop),
    )
    return pops


_DESELECTED_EXTERNAL: list[str] = []


def pytest_deselected(items):
    """Remember the ``external_data`` tests a ``-m`` expression deselected."""
    _DESELECTED_EXTERNAL.extend(
        item.nodeid for item in items if item.get_closest_marker("external_data")
    )


def pytest_sessionfinish(session):
    """Hand an xdist worker's deselected ids to the controller."""
    output = getattr(session.config, "workeroutput", None)
    if output is not None:
        output["external_deselected"] = list(_DESELECTED_EXTERNAL)


def pytest_testnodedown(node, error):
    """Collect the ids a finished xdist worker deselected."""
    for nodeid in getattr(node, "workeroutput", {}).get("external_deselected", []):
        if nodeid not in _DESELECTED_EXTERNAL:
            _DESELECTED_EXTERNAL.append(nodeid)


def pytest_terminal_summary(terminalreporter):
    """Say which end-to-end checks on external FDS output did not run."""
    if not _DESELECTED_EXTERNAL:
        return
    terminalreporter.section("external_data tests that did not run")
    terminalreporter.write_line(
        f"{len(_DESELECTED_EXTERNAL)} deselected: they read FDS output from the "
        "external data store (sciebo) and CI does not provide it. A green run "
        "says nothing about them."
    )
    for nodeid in _DESELECTED_EXTERNAL:
        terminalreporter.write_line(f"  {nodeid}")
