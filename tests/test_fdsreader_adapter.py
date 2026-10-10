"""Reading FDS output leaves the case directory unchanged (#716).

fdsreader 1.11.7 writes ``<CHID>.pickle`` next to the ``.smv``, deletes a
pickle it cannot read, and deletes it when caching is off. Every test here
restores fdsreader's own pickle path (tests/conftest.py moves it per xdist
worker), so a loader that bypasses ``fdsreader_adapter`` changes the case.
"""

from __future__ import annotations

import ast
import copy
import os
import pickle
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

fdsreader = pytest.importorskip("fdsreader")
from fdsreader import settings  # noqa: E402
from fdsreader.simulation import Simulation  # noqa: E402
from fdsreader.utils.data import create_hash  # noqa: E402

from pyfds_evac.core import fdsreader_adapter  # noqa: E402
from pyfds_evac.core.fds_inventory import inspect_fds_quantities  # noqa: E402
from pyfds_evac.core.fdsreader_adapter import (  # noqa: E402
    fdsreader_without_cache,
    open_fds_simulation,
)
from pyfds_evac.core.fed import FdsFedField  # noqa: E402
from pyfds_evac.core.smoke_speed import ExtinctionField  # noqa: E402
from pyfds_evac.core.visibility import _build_vismap  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
VIS_CASE = REPO / "assets" / "vis_slice_height" / "fds"
FED_CASE = REPO / "assets" / "fed_slice_height" / "fds"
ISO21 = REPO / "assets" / "iso_table21_coupled"


def _upstream_pickle_filename(cls, root_path: str, chid: str) -> str:
    """fdsreader 1.11.7's ``Simulation._get_pickle_filename``."""
    return os.path.join(root_path, chid + ".pickle")


@pytest.fixture(params=[True, False], ids=["caching_on", "caching_off"])
def upstream_cache(request, monkeypatch):
    """fdsreader's cache in the case directory, with the user's setting."""
    monkeypatch.setattr(
        Simulation, "_get_pickle_filename", classmethod(_upstream_pickle_filename)
    )
    monkeypatch.setattr(settings, "ENABLE_CACHING", request.param)
    return request.param


def _add_pickle(case: Path, pickle_state: str) -> None:
    """Put fdsreader's ``<CHID>.pickle`` into *case*: valid, stale or corrupt."""
    chid = next(case.glob("*.smv")).stem
    if pickle_state == "corrupt":
        (case / f"{chid}.pickle").write_bytes(b"not a pickle")
        return
    if pickle_state not in ("valid", "stale"):
        return
    # As fdsreader writes it (simulation.py:198-202); stale: another .smv.
    with fdsreader_without_cache():
        sim = Simulation.__new__(Simulation, str(case))
        sim.__init__(str(case))
    valid = pickle_state == "valid"
    sim._hash = create_hash(sim.smv_file_path) if valid else "stale"
    with open(case / f"{chid}.pickle", "wb") as f:
        pickle.dump(sim, f, protocol=4)


def _copy(src: Path, dst: Path, pickle_state: str) -> Path:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.pickle"))
    _add_pickle(dst, pickle_state)
    return dst


def _listing(root: Path) -> dict[str, tuple[int, int]]:
    """(size, mtime in ns) of every entry under *root*, by relative path."""
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in [root, *root.rglob("*")]
    }


def _open(case: Path) -> None:
    open_fds_simulation(case).slices  # noqa: B018


def _extinction(case: Path) -> None:
    ExtinctionField.from_fds(str(case), slice_height_m=2.0).sample_extinction(
        0.0, 0.5, 0.5
    )


def _inventory(case: Path) -> None:
    inspect_fds_quantities(case)


def _vismap(case: Path) -> None:
    sign = {"x": 1.0, "y": 1.0, "alpha": None, "c": 3}
    _build_vismap(str(case), {"exit": sign}, time_step_s=10.0, slice_height_m=2.0)


def _fed(case: Path) -> None:
    FdsFedField.from_fds(str(case))


LOADERS = [
    (VIS_CASE, _open),
    (VIS_CASE, _extinction),
    (VIS_CASE, _inventory),
    (VIS_CASE, _vismap),
    (FED_CASE, _fed),
]


@pytest.mark.parametrize("pickle_state", ["none", "valid", "corrupt"])
@pytest.mark.parametrize(
    ("src", "load"), LOADERS, ids=[load.__name__ for _, load in LOADERS]
)
def test_reading_a_case_leaves_its_directory_unchanged(
    tmp_path, upstream_cache, src, load, pickle_state
):
    case = _copy(src, tmp_path / "case", pickle_state)
    before = _listing(case)
    load(case)
    assert _listing(case) == before


def test_a_coupled_run_leaves_the_fds_directory_unchanged(tmp_path, upstream_cache):
    from pyfds_evac.core.run_config import build_run_kwargs
    from pyfds_evac.core.scenario import load_scenario, run_scenario

    case = _copy(ISO21 / "fds", tmp_path / "fds", "corrupt")
    before = _listing(case)
    scenario = load_scenario(str(ISO21 / "config.json"))
    opts = SimpleNamespace(
        seed=420,
        fds_dir=str(case),
        constant_extinction=None,
        smoke_update_interval=0.1,
        smoke_slice_height=2.0,
        disable_tenability=True,
        fed_threshold=1.0,
        fic_alpha=0.7,
        fic_min_factor=0.3,
        enable_rerouting=False,
        reroute_interval=1.0,
        vis_cache=None,
        incapacitation_mode="deterministic",
        susceptibility_sigma=0.0,
    )
    outcome = run_scenario(scenario, **build_run_kwargs(scenario, opts))
    try:
        assert outcome.agents_evacuated == outcome.total_agents > 0
    finally:
        outcome.cleanup()
    assert _listing(case) == before


def test_the_block_restores_fdsreaders_cache_settings(upstream_cache):
    original = Simulation.__dict__["_get_pickle_filename"]
    with fdsreader_without_cache():
        assert settings.ENABLE_CACHING is False
        assert Simulation.__dict__["_get_pickle_filename"] is not original
    assert settings.ENABLE_CACHING is upstream_cache
    assert Simulation.__dict__["_get_pickle_filename"] is original


def test_the_block_restores_the_settings_after_an_error(upstream_cache, tmp_path):
    original = Simulation.__dict__["_get_pickle_filename"]
    with pytest.raises(OSError):
        open_fds_simulation(tmp_path / "no_case")
    assert settings.ENABLE_CACHING is upstream_cache
    assert Simulation.__dict__["_get_pickle_filename"] is original


def test_an_fdsreader_without_the_cache_hooks_is_refused(monkeypatch):
    monkeypatch.delattr(settings, "ENABLE_CACHING")
    with pytest.raises(RuntimeError, match="has no settings.ENABLE_CACHING"):
        with fdsreader_without_cache():
            pass


def test_a_chid_cannot_move_the_redirected_pickle_out_of_the_temp_folder(
    tmp_path, upstream_cache
):
    """The .smv's CHID ends up in the pickle path; it must not reach a file.

    fdsreader deletes the file at that path when caching is off, so a CHID
    that is an absolute path or climbs out with ``..`` must not name one.
    """
    victim = tmp_path / "elsewhere" / "victim.pickle"
    victim.parent.mkdir()
    victim.write_bytes(b"someone's cache")
    stem = str(victim.with_suffix(""))
    for chid in (stem, "../" * 40 + stem.lstrip("/"), "sub/dir/case"):
        case = _copy(VIS_CASE, tmp_path / f"case{len(chid)}", "none")
        smv = next(case.glob("*.smv"))
        text = smv.read_text()
        smv.write_text(text.replace("CHID\n vis_slice_height\n", f"CHID\n {chid}\n"))
        assert smv.read_text() != text
        before = _listing(case)
        open_fds_simulation(case)
        assert _listing(case) == before
        assert victim.read_bytes() == b"someone's cache"


def test_clearing_the_persistent_cache_keeps_the_case_pickle(tmp_path, upstream_cache):
    case = _copy(VIS_CASE, tmp_path / "case", "valid")
    sim = open_fds_simulation(case)
    before = _listing(case)
    sim.clear_cache(clear_persistent_cache=True)
    sim.clear_cache()
    assert _listing(case) == before


@pytest.mark.parametrize("pickle_state", ["corrupt", "valid", "stale"])
@pytest.mark.parametrize(
    "duplicate",
    [copy.deepcopy, lambda sim: pickle.loads(pickle.dumps(sim))],
    ids=["deepcopy", "pickle"],
)
def test_a_copied_simulation_leaves_the_case_unchanged(
    tmp_path, upstream_cache, monkeypatch, duplicate, pickle_state
):
    """copy and unpickle go through Simulation.__new__ after the block.

    fdsreader reads (and on failure deletes) a pickle only on the first
    __new__ in a process, so ``_loading`` is reset here.
    """
    case = _copy(VIS_CASE, tmp_path / "case", "none")
    sim = open_fds_simulation(case)
    _add_pickle(case, pickle_state)
    monkeypatch.setattr(Simulation, "_loading", False)
    before = _listing(case)
    clone = duplicate(sim)
    assert _listing(case) == before
    assert isinstance(clone, Simulation)
    assert len(clone.slices) == len(sim.slices)


def test_nested_blocks_restore_the_settings_after_an_error(upstream_cache):
    original = Simulation.__dict__["_get_pickle_filename"]
    with pytest.raises(KeyError):
        with fdsreader_without_cache():
            with fdsreader_without_cache():
                raise KeyError("inner")
    assert settings.ENABLE_CACHING is upstream_cache
    assert Simulation.__dict__["_get_pickle_filename"] is original


def test_threads_opening_cases_leave_the_cases_and_settings_as_found(
    tmp_path, upstream_cache
):
    from concurrent.futures import ThreadPoolExecutor

    original = Simulation.__dict__["_get_pickle_filename"]
    cases = [_copy(VIS_CASE, tmp_path / f"case{i}", "valid") for i in range(4)]
    before = [_listing(case) for case in cases]
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(open_fds_simulation, cases * 5))
    assert [_listing(case) for case in cases] == before
    assert settings.ENABLE_CACHING is upstream_cache
    assert Simulation.__dict__["_get_pickle_filename"] is original


def _fdsreader_modules(tree: ast.Module) -> set[str]:
    """Expressions naming fdsreader or fdsreader.simulation in *tree*."""
    names = {"fdsreader", "fdsreader.simulation"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] != "fdsreader":
                    continue
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module == "fdsreader":
            names |= {
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "simulation"
            }
    return names


_GUARDS = {"fdsreader_without_cache", "fdsreader_adapter.fdsreader_without_cache"}
_DEFERRED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _calls_run_in(nodes: list[ast.stmt]) -> set[int]:
    """ids of the calls *nodes* make, not those of functions they define."""
    found: set[int] = set()
    todo: list[ast.AST] = list(nodes)
    while todo:
        node = todo.pop()
        if isinstance(node, _DEFERRED):
            continue
        if isinstance(node, ast.Call):
            found.add(id(node))
        todo.extend(ast.iter_child_nodes(node))
    return found


def _guarded_calls(tree: ast.Module) -> set[int]:
    """ids of the calls run inside ``with fdsreader_without_cache():``."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        names = {
            ast.unparse(item.context_expr.func)
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
        }
        if names & _GUARDS:
            guarded |= _calls_run_in(node.body)
    return guarded


def _bare_uses(source: str, name: str) -> list[str]:
    tree = ast.parse(source, filename=name)
    modules = _fdsreader_modules(tree)
    guarded = _guarded_calls(tree)
    found = []
    for node in ast.walk(tree):
        line = f"{name}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "fdsreader"
        ):
            if any(alias.name == "Simulation" for alias in node.names):
                found.append(f"{line} imports fdsreader's Simulation")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "Simulation"
            and ast.unparse(node.value) in modules
        ):
            found.append(f"{line} uses fdsreader's Simulation")
        elif isinstance(node, ast.Attribute) and node.attr in (
            "ENABLE_CACHING",
            "_get_pickle_filename",
        ):
            found.append(f"{line} touches fdsreader's cache settings")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_fds_data"
            and id(node) not in guarded
        ):
            found.append(f"{line} calls fdsvismap's read_fds_data unguarded")
    return found


@pytest.mark.parametrize(
    "source",
    [
        "import fdsreader\nfdsreader.Simulation(d)",
        "import fdsreader as fds\nfds.Simulation(d)",
        "from fdsreader import Simulation as S\nS(d)",
        "from fdsreader.simulation import Simulation\nSimulation(d)",
        "from fdsreader import simulation as s\ns.Simulation(d)",
        "import fdsreader.simulation as s\ns.Simulation(d)",
        "import fdsreader.simulation\nfdsreader.simulation.Simulation(d)",
        "import fdsreader\nfdsreader.settings.ENABLE_CACHING = False",
        "vis.read_fds_data(d)",
        "with fdsreader_without_cache():\n    def later():\n        vis.read_fds_data(d)\nlater()",
        "with fdsreader_without_cache():\n    f = lambda: vis.read_fds_data(d)\nf()",
    ],
)
def test_the_guard_finds_a_bare_fdsreader_use(source):
    assert _bare_uses(source, "snippet.py")


@pytest.mark.parametrize(
    "source",
    [
        "with fdsreader_without_cache():\n    vis.read_fds_data(d)",
        "with fdsreader_adapter.fdsreader_without_cache():\n    vis.read_fds_data(d)",
        "import jupedsim as jps\njps.Simulation(model=m)",
        "open_fds_simulation(d)",
    ],
)
def test_the_guard_accepts_the_adapter(source):
    assert _bare_uses(source, "snippet.py") == []


# The adapter, and its copy for the standalone verification scripts.
_OWNERS = {
    Path(fdsreader_adapter.__file__).resolve(),
    (REPO / "scripts" / "verification" / "_fdsreader_open.py").resolve(),
}


def test_fds_output_is_opened_only_through_the_adapter():
    """Opening a case any other way may write into the user's FDS directory."""
    files = [
        path
        for folder in ("pyfds_evac", "scripts", "examples", "assets")
        for path in sorted((REPO / folder).rglob("*.py"))
        if path.resolve() not in _OWNERS
    ] + [REPO / "run.py", REPO / "app.py"]
    found = [
        use
        for path in files
        for use in _bare_uses(path.read_text(), str(path.relative_to(REPO)))
    ]
    assert found == []


def test_the_verification_scripts_open_cases_without_touching_them(
    tmp_path, upstream_cache
):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_fdsreader_open", REPO / "scripts" / "verification" / "_fdsreader_open.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = Simulation.__dict__["_get_pickle_filename"]
    for state in ("none", "valid", "corrupt"):
        case = _copy(VIS_CASE, tmp_path / state, state)
        before = _listing(case)
        assert len(module.open_fds_case(case).slices) == 4
        assert _listing(case) == before
    assert Simulation.__dict__["_get_pickle_filename"] is original


def test_the_verification_scripts_refuse_an_fdsreader_without_the_hooks(
    tmp_path, monkeypatch
):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_fdsreader_open", REPO / "scripts" / "verification" / "_fdsreader_open.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delattr(settings, "ENABLE_CACHING")
    with pytest.raises(RuntimeError, match="has no settings.ENABLE_CACHING"):
        module.open_fds_case(_copy(VIS_CASE, tmp_path / "case", "none"))
