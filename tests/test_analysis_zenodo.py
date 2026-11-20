"""The ASET/RSET module against the data release of Schröder et al. (2020).

Opt-in: set ``SCHROEDER2020_RELEASE`` to the unpacked release
(doi:10.5281/zenodo.3875550, the folder with ``0_ASET``). The release carries
no licence text, so nothing from it is stored in the repository and these
tests only read it.

Stage 1 is exact. The measures of the released difference map, counted by
the release's rules, are the study plan's: min DIFF -29 s, 54 cells with
DIFF <= 0 (19.44 m²), C -310 m² s. The released ``DIFF_map.txt`` (18 x 51)
cannot be rebuilt from the released ``aset_map.txt`` (17 x 50), so stage 1
checks the released DIFF, not a rebuild.

Stage 2 rebuilds ASET and RSET on PedPy's grid with the module and compares
with row A of ``scripts/docs/schroeder2020_reproduce.py`` (release RSET, ASET
rebuilt at its grid points) within the tolerance that script predeclares:
min DIFF within 10 s and the failing area within 10 %. The tolerance is not
changed to pass. It holds for the ``nearest`` rule (the release's) and for
the default ``exists`` rule (block maximum); row A is a nearest-node
reference, so ``exists`` is checked against it, not against the release's
own cell rule. Row A itself now uses the module's ``first_crossing_level``
and ``release_measures``, so stage 2 checks the rebuild of the grid and the
RSET, not those two functions; stage 1 and the released ``aset_map.txt``
are the independent anchor for them.
"""

import importlib.util
import math
import os
from pathlib import Path

import numpy as np
import pytest

pedpy = pytest.importorskip("pedpy", minversion="1.5.1")

from pyfds_evac.analysis import (  # noqa: E402
    PointCrossing,
    PointSeries,
    aset_map,
    diff_map,
    first_crossing_level,
    grid_from_walkable,
    measures,
    pool_rset,
    release_measures,
    rset_map,
)

RELEASE = Path(os.environ.get("SCHROEDER2020_RELEASE", "release-not-set"))
ROOT = Path(__file__).resolve().parents[1]
K_LIMIT = 0.23  # 1/m, the release's threshold
T_END = 120.0  # s, last slice
EXPECTED = {"min_diff_s": -29.0, "n_le0": 54, "c_binned_m2s": -310.0}

pytestmark = [
    pytest.mark.external_data,
    pytest.mark.skipif(
        not (RELEASE / "0_ASET").is_dir(),
        reason="set SCHROEDER2020_RELEASE to the unpacked Zenodo release",
    ),
]


def test_stage1_released_diff_map_by_the_release_counting():
    diff = np.loadtxt(RELEASE / "2_DIFF" / "DIFF_map.txt")
    r = release_measures(diff)
    for key, expected in EXPECTED.items():
        assert math.isclose(getattr(r, key), expected, abs_tol=0.5), key
    assert math.isclose(r.area_le0_m2, 19.44, abs_tol=0.01)


def test_stage1_default_rules_give_other_numbers_on_the_same_map():
    """DIFF = 0 passes (n_lt0, not n_le0) and C is bin-free (c_free, not binned)."""
    diff = np.loadtxt(RELEASE / "2_DIFF" / "DIFF_map.txt")
    r = release_measures(diff)
    assert r.n_lt0 <= r.n_le0
    print(
        f"release counting: {r.n_le0} cells, C binned {r.c_binned_m2s:.1f}; "
        f"default rules: {r.n_lt0} cells, C {r.c_free_m2s:.1f}"
    )


def _script():
    path = ROOT / "scripts" / "docs" / "schroeder2020_reproduce.py"
    spec = importlib.util.spec_from_file_location("schroeder2020_reproduce", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rebuild(script, rule):
    """ASET and pooled RSET on PedPy's grid, built with the module."""
    slices = script.read_slices(RELEASE)
    seeds = script.read_seeds(RELEASE)
    room = script.read_room(RELEASE / "1_RSET" / "1254" / "corridor_geo.xml")
    grid = grid_from_walkable(room, script.CELL)
    times = np.array(sorted(slices))
    nodes_y, nodes_x = np.meshgrid(
        np.arange(51) * script.DX_SLICE, np.arange(151) * script.DX_SLICE, indexing="ij"
    )
    frames = np.stack([slices[t].ravel() for t in times])
    series = PointSeries(
        nodes_x.ravel(), nodes_y.ravel(), times, np.arange(len(times)), frames
    )
    first = first_crossing_level(series, K_LIMIT)
    crossing = PointCrossing("K 0.23", series.x, series.y, first, T_END)
    aset = aset_map(grid, [crossing], cell_rule=rule)
    walkable = pedpy.WalkableArea(room)
    rsets = []
    for rate, traj in seeds.values():
        data = pedpy.TrajectoryData(data=traj, frame_rate=rate)
        left = {int(i): 0.0 for i in traj["id"].unique()}  # every seed empties
        rsets.append(rset_map(data, walkable, grid, exit_times=left))
    rset, _ = pool_rset(rsets, "p95")
    return grid, aset, rset


@pytest.mark.parametrize("rule", ["nearest", "exists"])
def test_stage2_rebuild_is_within_the_predeclared_tolerance_of_row_a(rule):
    script = _script()
    slices = script.read_slices(RELEASE)
    ref_rset = np.loadtxt(RELEASE / "1_RSET" / "RSET_map_all_seeds.txt")
    row_a = script._release_grid_measures(
        script.filled(script._release_rset_grid_aset(slices)), ref_rset
    )
    grid, aset, rset = _rebuild(script, rule)
    m = measures(diff_map(aset, rset, grid, zero_fails=True))
    ours = {"min": m.min_diff_s, "n_fail": m.n_fail}
    verdict = script._tolerance(ours, row_a)
    print(f"module ({rule}) vs row A: {verdict}")
    assert verdict.startswith("PASS"), verdict
