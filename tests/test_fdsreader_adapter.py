"""Reading FDS output leaves the case directory unchanged (#716).

fdsreader 1.11.7 writes ``<CHID>.pickle`` next to the ``.smv``, deletes a
pickle it cannot read, and deletes it when caching is off. Every test here
restores fdsreader's own pickle path (tests/conftest.py moves it per xdist
worker), so a loader that bypasses ``fdsreader_adapter`` changes the case.
"""

from __future__ import annotations

import ast
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


def _copy(src: Path, dst: Path, pickle_state: str) -> Path:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.pickle"))
    chid = next(dst.glob("*.smv")).stem
    if pickle_state == "valid":
        # As fdsreader writes it (simulation.py:198-202).
        sim = open_fds_simulation(dst)
        sim._hash = create_hash(sim.smv_file_path)
        with open(dst / f"{chid}.pickle", "wb") as f:
            pickle.dump(sim, f, protocol=4)
    elif pickle_state == "corrupt":
        (dst / f"{chid}.pickle").write_bytes(b"not a pickle")
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


def _fdsreader_names(tree: ast.Module) -> set[str]:
    """Names bound to the fdsreader package by ``import fdsreader [as x]``."""
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "fdsreader"
    }


def _guarded_calls(tree: ast.Module) -> set[int]:
    """ids of the calls inside ``with fdsreader_without_cache():``."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        names = {
            ast.unparse(item.context_expr.func)
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
        }
        if not names & {
            "fdsreader_without_cache",
            "fdsreader_adapter.fdsreader_without_cache",
        }:
            continue
        guarded |= {id(call) for call in ast.walk(node) if isinstance(call, ast.Call)}
    return guarded


def _bare_fdsreader_uses(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    packages = _fdsreader_names(tree)
    guarded = _guarded_calls(tree)
    found = []
    for node in ast.walk(tree):
        line = f"{path.relative_to(REPO)}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "fdsreader"
        ):
            if any(alias.name == "Simulation" for alias in node.names):
                found.append(f"{line} imports fdsreader's Simulation")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "Simulation"
            and isinstance(node.value, ast.Name)
            and node.value.id in packages
        ):
            found.append(f"{line} uses fdsreader.Simulation")
        elif isinstance(node, ast.Attribute) and node.attr == "ENABLE_CACHING":
            found.append(f"{line} touches fdsreader's ENABLE_CACHING")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_fds_data"
            and id(node) not in guarded
        ):
            found.append(f"{line} calls fdsvismap's read_fds_data unguarded")
    return found


def test_fds_output_is_opened_only_through_the_adapter():
    """Opening a case any other way may write into the user's FDS directory."""
    adapter = Path(fdsreader_adapter.__file__).resolve()
    files = [
        path
        for folder in ("pyfds_evac", "scripts", "examples", "assets")
        for path in sorted((REPO / folder).rglob("*.py"))
        if path.resolve() != adapter
    ] + [REPO / "run.py", REPO / "app.py"]
    found = [use for path in files for use in _bare_fdsreader_uses(path)]
    assert found == []
