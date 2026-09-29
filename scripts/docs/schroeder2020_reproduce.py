"""Reproduce the ASET-RSET map measures of Schröder et al. (2020), phase 0.

Source: B. Schröder, L. Arnold, A. Seyfried, "A map representation of the
ASET-RSET concept", Fire Safety Journal 115 (2020) 103154,
doi:10.1016/j.firesaf.2020.103154. Data and reference implementation:
B. Schröder, L. Arnold, A. Seyfried, "A Map Representation of the ASET-RSET
Concept - Reference Implementation", v1.0.1, Zenodo, 2020,
doi:10.5281/zenodo.3875550.

The release carries no licence text (Zenodo "Other (Open)", no LICENSE
file), so nothing from it is stored in this repository or redistributed, and
this script writes no figures made from it. Download the release from the
DOI yourself and unpack it anywhere; ``DATA`` is the unpacked folder that
contains ``0_ASET``, ``1_RSET`` and ``2_DIFF``::

    uv run --with "pedpy>=1.5.1" python scripts/docs/schroeder2020_reproduce.py \\
        --data DATA

Nothing of pyFDS-Evac is used: the script reads the release's ASCII
extinction slices (``0_ASET/HRR_60kW/ascii_slices/extinction/sf_*.txt``,
z = 2.0 m, every 10 s), its JuPedSim trajectories (``1_RSET/12*/``,
1 fps) and its maps, and prints

* stage 1: the measures of the released difference map (min DIFF, negative
  area, C), with the release's counting and with the corrected one, plus
  checks that the released ASET and RSET maps rebuild from the inputs;
* stage 2: ASET and RSET rebuilt on one shared grid (PedPy's edges) with
  the study plan's rules, and each difference to stage 1 with its cause;
* the cell-rule table (F3) and the 10 s against 30 s table (F8).
"""

import argparse
import math
import warnings
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

K_TH = 0.23  # 1/m, the release's threshold (paper Sect. 2.2.4, p. 3)
T_END = 120.0  # s, last slice; the release fills unexceeded cells with it
CELL = 0.6  # m, map cell size of the paper and the release
DX_SLICE = 0.2  # m, FDS cell size of the release (slice nodes)
BIN = 20.0  # s, bin width of the release's C
PERCENTILE = 95  # pooling over seeds in the release's code
RULES = ("exists", "nearest", "forall", "centre")
RULE_TEXT = {
    "exists": "∃ any node in the cell (block maximum)",
    "nearest": "release: one node, PIL nearest resize",
    "forall": "∀ all nodes in the cell",
    "centre": "field interpolated at the cell centre",
}
# Our own earlier reproduction of the released DIFF (study plan Sect. 1). The
# paper prints none of these in its text; they are consistent, to read-off
# precision, with its Figs. 5, 7 and 8 (60 kW, N = 100).
EXPECTED = {"min": -29.0, "n_le0": 54, "c_binned": -310.0}


# --- Reading the release -------------------------------------------------


def read_slices(data):
    """Return {t: K[ny, nx]} with row 0 at y = 0 (the release's orientation)."""
    folder = data / "0_ASET" / "HRR_60kW" / "ascii_slices" / "extinction"
    files = sorted(folder.glob("sf_*.txt"), key=lambda p: int(p.stem[3:]))
    if not files:
        raise SystemExit(f"no extinction slices under {folder}")
    slices = {float(p.stem[3:]): np.loadtxt(p) for p in files}
    shapes = {a.shape for a in slices.values()}
    assert shapes == {(51, 151)}, f"unexpected slice shape {shapes}"
    return slices


def read_trajectories(path):
    """Return (frame rate, DataFrame id/frame/x/y) of one JuPedSim XML file."""
    root = ET.parse(path).getroot()
    rate = float(root.findtext("header/frameRate"))
    rows = [
        (int(a.get("ID")), int(f.get("ID")), float(a.get("x")), float(a.get("y")))
        for f in root.iter("frame")
        for a in f.iter("agent")
    ]
    return rate, pd.DataFrame(rows, columns=["id", "frame", "x", "y"])


def read_room(path):
    """Return the room polygon from the JuPedSim geometry (both wall lines)."""
    from shapely import Polygon

    root = ET.parse(path).getroot()
    xy = [
        (float(v.get("px")), float(v.get("py")))
        for poly in root.iter("polygon")
        for v in poly.iter("vertex")
    ]
    return Polygon(xy).buffer(0)


def read_seeds(data):
    """Return {seed: (frame rate, DataFrame)} for every released seed."""
    folders = sorted(p for p in (data / "1_RSET").glob("12*") if p.is_dir())
    return {int(p.name): read_trajectories(p / "corridor_traj.xml") for p in folders}


# --- Maps ----------------------------------------------------------------


def first_crossing(slices, value_maps, times=None):
    """First time each cell's value reaches K_TH; inf when never."""
    times = sorted(slices) if times is None else times
    aset = np.full(value_maps[times[0]].shape, np.inf)
    for t in reversed(times):
        aset[value_maps[t] >= K_TH] = t
    return aset


def cell_values(field, rule, nx_cells, ny_cells):
    """Reduce one slice (row 0 at y = 0) to map cells with a cell rule.

    Cells are [i*CELL, (i+1)*CELL] with both edges included, so a node on a
    cell edge belongs to both cells. Cells that no node reaches get NaN.
    """
    step = round(CELL / DX_SLICE)
    ny, nx = field.shape
    out = np.full((ny_cells, nx_cells), np.nan)
    if rule == "nearest":
        # Pillow's nearest resize, as the release calls it (151 x 51 nodes to
        # its 50 x 17 room cells), picks node floor((i + 0.5) * n_in / n_out).
        # Cells past the room (PedPy's extra column) take the last node.
        room_x = round((nx - 1) * DX_SLICE / CELL)
        room_y = math.ceil((ny - 1) * DX_SLICE / CELL)
        ix = np.floor((np.arange(nx_cells) + 0.5) * nx / room_x).astype(int)
        iy = np.floor((np.arange(ny_cells) + 0.5) * ny / room_y).astype(int)
        return field[np.ix_(np.minimum(iy, ny - 1), np.minimum(ix, nx - 1))]
    if rule == "centre":
        xs = np.arange(nx) * DX_SLICE
        ys = np.arange(ny) * DX_SLICE
        xc = (np.arange(nx_cells) + 0.5) * CELL
        yc = (np.arange(ny_cells) + 0.5) * CELL
        along_x = np.array([np.interp(xc, xs, row) for row in field])
        return np.array([np.interp(yc, ys, col) for col in along_x.T]).T
    reduce = np.max if rule == "exists" else np.min
    for j in range(ny_cells):
        out[j] = _row_blocks(field[step * j : step * j + step + 1], reduce, nx_cells)
    return out


def _row_blocks(rows, reduce, nx_cells):
    step = round(CELL / DX_SLICE)
    vals = [rows[:, step * i : step * i + step + 1] for i in range(nx_cells)]
    return [reduce(v) if v.size else np.nan for v in vals]


def aset_map(slices, rule, nx_cells, ny_cells, times=None):
    """ASET per cell, row 0 at y = 0; inf = not by the last slice."""
    values = {t: cell_values(a, rule, nx_cells, ny_cells) for t, a in slices.items()}
    return first_crossing(slices, values, times)


def release_rset(traj, rate):
    """The release's RSET rule: last frame at the nearest point 0.6 k (max-norm)."""
    x = np.arange(0, 30 + 0.01, CELL)
    y = np.arange(0, 10.2 + 0.01, CELL)
    out = np.full((len(y), len(x)), np.nan)
    ix = np.abs(x[None, :] - traj.x.to_numpy()[:, None]).argmin(axis=1)
    iy = np.abs(y[None, :] - traj.y.to_numpy()[:, None]).argmin(axis=1)
    frame = traj.frame.to_numpy() / rate
    for j, i, t in sorted(zip(iy, ix, frame), key=lambda r: r[2]):
        out[j, i] = t
    return out


def pedpy_rset(traj, rate, area):
    """PedPy RSET map (RsetMethod.MAX), flipped back to row 0 at y = 0."""
    import pedpy

    data = pedpy.TrajectoryData(data=traj, frame_rate=rate)
    rset = pedpy.compute_rset_map(
        traj_data=data,
        walkable_area=area,
        grid_size=CELL,
        method=pedpy.RsetMethod.MAX,
    )
    return np.flipud(rset)


def pool(maps, how):
    """Pool seeds per cell over the seeds that visit it; NaN if none does."""
    stack = np.dstack(maps)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells
        if how == "max":
            return np.nanmax(stack, axis=2)
        return np.nanpercentile(stack, PERCENTILE, axis=2)


def shared_edges(area):
    """PedPy's edges, computed with the same expression PedPy uses."""
    min_x, min_y, max_x, max_y = area.bounds
    x_edges = np.arange(min_x, max_x + CELL, CELL)
    y_edges = np.arange(min_y, max_y + CELL, CELL)
    return x_edges, y_edges


def check_orientation(area):
    """Assert PedPy's row 0 is max y, so the flip in pedpy_rset is right."""
    probe = pd.DataFrame({"id": [1], "frame": [7], "x": [0.1], "y": [0.1]})
    rset = pedpy_rset(probe, 1.0, area)
    assert rset[0, 0] == 7.0, "PedPy orientation changed: row 0 is not max y"


# --- Measures ------------------------------------------------------------


def release_measures(diff):
    """min DIFF, area and C exactly as 2_DIFF/diff_map.py computes them."""
    flat = diff[np.isfinite(diff)]
    bins = np.arange(-120, 0.01, BIN)  # last bin [-20, 0] closed: 0 counts
    freqs, bins = np.histogram(flat, bins=bins)
    c = float(np.sum(freqs * (bins[1:] - BIN / 2))) * CELL**2
    return {
        "min": float(flat.min()),
        "n_le0": int(freqs.sum()),
        "n_lt0": int((flat < 0).sum()),
        "c_binned": c,
        "c_free": float(flat[flat < 0].sum()) * CELL**2,
    }


def states(aset, rset):
    """Five cell states on visited cells (RSET finite); DIFF = 0 passes."""
    visited = np.isfinite(rset)
    censored = np.isinf(aset)
    exact = visited & ~censored
    diff = np.where(exact, aset - rset, np.nan)
    # Every seed is empty before T_END (asserted in main), so no RSET is
    # censored: the "<= bound" and "undetermined" states are empty here.
    assert np.nanmax(rset) < T_END, "RSET reaches T_END: censored states needed"
    return {
        "pass": int((diff >= 0).sum()),
        "fail": int((diff < 0).sum()),
        ">= bound": int((visited & censored).sum()),
        "<= bound": 0,
        "undetermined": 0,
    }, diff


def corrected_measures(aset, rset, zero_fails=False):
    """Measures on visited cells with exact DIFF; zero_fails = release counting."""
    counts, diff = states(aset, rset)
    exact = diff[np.isfinite(diff)]
    neg = exact[exact <= 0] if zero_fails else exact[exact < 0]
    # Binned C: the release's histogram, or the same 20 s bins with 0 excluded.
    centres = (np.floor(neg / BIN) + 0.5) * BIN
    c_binned = release_measures(diff)["c_binned"] if zero_fails else centres.sum()
    return {
        "min": float(exact.min()),
        "n_fail": int(neg.size),
        "area": neg.size * CELL**2,
        "c_free": float(neg.sum()) * CELL**2,
        "c_binned": float(c_binned) * (1 if zero_fails else CELL**2),
        "states": counts,
    }


def filled(aset):
    """The release's t_end fill: unexceeded cells get T_END."""
    return np.where(np.isinf(aset), T_END, aset)


# --- Report --------------------------------------------------------------


def line(label, m):
    return (
        f"  {label:<44} {m['min']:>6.0f} {m['n_fail']:>5d} {m['n_fail'] * CELL**2:>7.2f}"
        f" {m['c_free']:>8.1f} {m['c_binned']:>8.1f}"
    )


def header():
    return (
        f"  {'':<44} {'min':>6} {'fail':>5} {'A m²':>7} {'C free':>8}"
        f" {'C 20 s':>8}\n  {'':<44} {'s':>6} {'':>5} {'':>7} {'m²s':>8} {'m²s':>8}"
    )


def stage1(data, slices, seeds):
    print("STAGE 1 - measures of the released difference map (2_DIFF/DIFF_map.txt)")
    diff = np.loadtxt(data / "2_DIFF" / "DIFF_map.txt")
    m = release_measures(diff)
    area_le0 = m["n_le0"] * CELL**2
    print(
        f"  grid {diff.shape[0]} x {diff.shape[1]}, {np.isfinite(diff).sum()} visited"
    )
    print(f"  min DIFF                         {m['min']:.0f} s")
    print(
        f"  cells DIFF <= 0 (release)        {m['n_le0']} = {area_le0:.2f} m²"
        f"  (script prints int: {int(area_le0)} m²)"
    )
    print(
        f"  cells DIFF <  0 (DIFF = 0 passes) {m['n_lt0']} = {m['n_lt0'] * CELL**2:.2f} m²"
    )
    print(f"  C, 20 s bins, centres -10..-110  {m['c_binned']:.1f} m²s")
    print(f"  C, bin-free (sum DIFF<0 x 0.36)  {m['c_free']:.1f} m²s")
    ok = all(math.isclose(m[k], v, abs_tol=0.5) for k, v in EXPECTED.items())
    print(
        f"  matches plan Sect. 1 reproduction of the released DIFF"
        f" (-29 s / 54 cells / -310 m²s): {'YES' if ok else 'NO'}"
        "\n  The paper prints none of these in its text; they agree with its"
        "\n  Figs. 5, 7 and 8 (60 kW, N = 100) to read-off precision only."
    )

    released = np.loadtxt(data / "0_ASET" / "aset_map.txt")
    rebuilt = filled(aset_map(slices, "nearest", 50, 17))
    share = np.mean(rebuilt == released)
    print(
        f"\n  1b ASET rebuilt, nearest rule, t_end fill vs aset_map.txt: {share:.1%} of cells"
    )

    per_seed = [release_rset(traj, rate) for rate, traj in seeds.values()]
    pooled = pool(per_seed, "p95")
    ref = np.loadtxt(data / "1_RSET" / "RSET_map_all_seeds.txt")
    same = (
        np.array_equal(np.isnan(pooled), np.isnan(ref))
        and np.nanmax(np.abs(pooled - ref)) < 1e-9
    )
    print(
        f"     RSET rebuilt, release rule, p95 vs RSET_map_all_seeds.txt: {'identical' if same else 'DIFFERENT'}"
    )

    implied = diff + ref
    seen = np.isfinite(implied)
    print(
        f"\n  The released DIFF ({diff.shape[0]} x {diff.shape[1]}) cannot come from the released"
        f"\n  aset_map.txt ({released.shape[0]} x {released.shape[1]}): diff_map.py loads"
        f" '../0_ASET/ASET_map.txt', a file"
        f"\n  the release does not contain. The ASET it implies (DIFF + RSET) spans"
        f"\n  {np.nanmin(implied):.0f}-{np.nanmax(implied):.0f} s, while aset_map.txt has"
        f" {(released == T_END).sum()} cells not exceeded by {T_END:.0f} s."
    )
    near_pts = filled(_release_rset_grid_aset(slices))
    agree = np.mean(near_pts[seen] == implied[seen])
    print(
        f"  ASET rebuilt at the RSET grid's points (nearest node) agrees with the implied"
        f"\n  ASET in {agree:.0%} of the {seen.sum()} visited cells."
    )
    return m


def _release_rset_grid_aset(slices):
    """ASET at the RSET grid's points 0.6 k (nearest slice node)."""
    ix = np.minimum(np.rint(np.arange(51) * CELL / DX_SLICE).astype(int), 150)
    iy = np.minimum(np.rint(np.arange(18) * CELL / DX_SLICE).astype(int), 50)
    values = {t: a[np.ix_(iy, ix)] for t, a in slices.items()}
    return first_crossing(slices, values)


def stage2(data, slices, seeds, released):
    from pedpy import WalkableArea

    area = WalkableArea(read_room(data / "1_RSET" / "1254" / "corridor_geo.xml"))
    check_orientation(area)
    x_edges, y_edges = shared_edges(area)
    nx_cells, ny_cells = len(x_edges) - 1, len(y_edges) - 1
    per_seed = [pedpy_rset(traj, rate, area) for rate, traj in seeds.values()]
    assert per_seed[0].shape == (ny_cells, nx_cells), "RSET and ASET grids differ"
    rset = pool(per_seed, "p95")
    rset_max = pool(per_seed, "max")
    asets = {r: aset_map(slices, r, nx_cells, ny_cells) for r in RULES}

    print("\nSTAGE 2 - ASET and RSET rebuilt on one shared grid")
    print(
        f"  grid: PedPy edges from the room bounds {area.bounds}, {CELL} m,"
        f" {ny_cells} x {nx_cells} cells,"
        f"\n  x {x_edges[0]:.1f}-{x_edges[-1]:.1f} m, y {y_edges[0]:.1f}-{y_edges[-1]:.1f} m."
        f" The last row (y 9.6-10.2 m) and the last column (x 30.0-30.6 m)"
        f"\n  reach outside the 30 x 10 m room; PedPy's float arange adds that column."
    )
    print(
        "  ASET: K >= 0.23 1/m at z = 2.0 m, slices every 10 s, first crossing never undone,"
        "\n        unexceeded cells censored (not filled). RSET: PedPy compute_rset_map MAX per"
        f"\n        seed at the release's {seeds[min(seeds)][0]:.0f} fps, p{PERCENTILE} over"
        f" {len(seeds)} seeds (nanpercentile, as the release)."
    )
    print("\n  From the released DIFF to the corrected one, one change per row:")
    print(header())
    nearest = asets["nearest"]
    ref = np.loadtxt(data / "1_RSET" / "RSET_map_all_seeds.txt")
    rows = [
        ("0 released DIFF, DIFF <= 0 fails", {**released, "n_fail": released["n_le0"]}),
        (
            "A release RSET, ASET rebuilt at its points",
            _release_grid_measures(filled(_release_rset_grid_aset(slices)), ref),
        ),
        (
            "B release RSET, aset_map.txt padded 18 x 51",
            _release_grid_measures(_padded_release_aset(data), ref),
        ),
        (
            "1 shared grid, nearest rule, t_end fill",
            corrected_measures(filled(nearest), rset, zero_fails=True),
        ),
        ("2 + DIFF = 0 passes", corrected_measures(filled(nearest), rset)),
        ("3 + censored cells kept, not filled", corrected_measures(nearest, rset)),
        (
            "4 + cell rule exists (plan default)",
            corrected_measures(asets["exists"], rset),
        ),
        (
            f"4' pooled by max ({len(seeds)} seeds) not p95",
            corrected_measures(asets["exists"], rset_max),
        ),
    ]
    for label, m in rows:
        print(line(label, m))
    print(
        "\n  'fail' counts DIFF <= 0 in rows 0, A, B, 1 and DIFF < 0 from row 2 on. 'C free' is the"
        "\n  sum of the failing DIFF times 0.36 m²; 'C 20 s' bins them at 20 s (release bins)."
        "\n  0 -> A/B: only the ASET source changes (release grid, RSET and window kept):"
        "\n          the ASET_map.txt behind row 0 is not in the release (stage 1)."
        "\n  A -> 1: the half-cell offset (release RSET centred on 0.6 k, ASET on 0.6 k + 0.3),"
        "\n          and window vs PedPy bin."
        "\n  1 -> 2: cells with DIFF = 0 pass."
        "\n  2 -> 3: t_end fill removed; censored ASET cells become '>= bound'. No change here:"
        "\n          every RSET is below 120 s, so those cells passed with the fill too."
        "\n  3 -> 4: one node per cell replaced by the block maximum: earlier ASET, more fails."
    )
    by = dict(rows)
    row1 = by["1 shared grid, nearest rule, t_end fill"]
    print(
        "  1c tolerance (min DIFF +-10 s, area +-10 %):"
        f"\n     row 1 vs row 0: {_tolerance(row1, rows[0][1])}"
        "\n       not rebuildable: row 0 rests on an ASET map not in the release."
        f"\n     row 1 vs row A: {_tolerance(row1, rows[1][1])}"
        "\n       our own changes only (grid, window vs bin, half-cell offset)."
    )
    states_exists = by["4 + cell rule exists (plan default)"]["states"]
    print(f"\n  Cell states, rule exists, p{PERCENTILE}: {states_exists}")
    return asets, rset, (nx_cells, ny_cells), _in_room(area, x_edges, y_edges)


def _release_grid_measures(aset, ref):
    """Release counting on the release's 18 x 51 RSET grid (DIFF <= 0 fails)."""
    m = release_measures(np.where(np.isfinite(ref), aset - ref, np.nan))
    return {**m, "n_fail": m["n_le0"]}


def _padded_release_aset(data):
    """aset_map.txt (17 x 50) padded to 18 x 51 by repeating its last row/column."""
    released = np.loadtxt(data / "0_ASET" / "aset_map.txt")
    return np.pad(released, ((0, 1), (0, 1)), mode="edge")


def _tolerance(m, ref):
    d_min = m["min"] - ref["min"]
    d_area = (m["n_fail"] - ref["n_fail"]) / ref["n_fail"]
    ok = abs(d_min) <= 10 and abs(d_area) <= 0.10
    verdict = "PASS" if ok else "FAIL"
    return f"{verdict} (min DIFF {d_min:+.0f} s, area {d_area:+.0%})"


def _in_room(area, x_edges, y_edges):
    """Cells (row 0 at y = 0) that lie entirely inside the room polygon."""
    from shapely import box

    room = area.polygon
    return np.array(
        [
            [room.covers(box(x0, y0, x1, y1)) for x0, x1 in pairwise(x_edges)]
            for y0, y1 in pairwise(y_edges)
        ]
    )


def table_rules(asets, rset, inside):
    print("\nF3 - cell rule (shared grid, 10 s slices, p95 RSET)")
    print(
        f"  {'rule':<8} {'never by 120 s':>14} {'> 80 s':>9} {'min':>6} {'n<0':>5} {'C free':>8}"
    )
    for r in RULES:
        a = asets[r]
        m = corrected_measures(a, rset)
        never = f"{int(np.isinf(a[inside]).sum())} ({int(np.isinf(a).sum())})"
        late = f"{int((a[inside] > 80).sum())} ({int((a > 80).sum())})"
        print(
            f"  {r:<8} {never:>14} {late:>9}"
            f" {m['min']:>6.0f} {m['n_fail']:>5d} {m['c_free']:>8.1f}   {RULE_TEXT[r]}"
        )
    print(
        f"  counts are of the {int(inside.sum())} cells entirely inside the room; in brackets"
        f"\n  of all {inside.size} grid cells, with PedPy's extra column and the top row that"
        "\n  lies partly outside (PedestrianDynamics/PedPy#581). min/n<0/C over visited cells."
    )
    print(
        "  '> 80 s' includes 'never'. The paper (p. 4) says every cell is exceeded by 80 s."
        "\n  Nodes on a cell edge belong to both cells. On the release's 17 x 50 grid"
        "\n  (all cells), exists / forall give 3 / 77 never-exceeded cells with closed and 4 / 50 with"
        "\n  half-open cells; an earlier estimate of 5 / 62 is not reproduced by either."
    )


def table_dt(slices, rset, shape):
    nx_cells, ny_cells = shape
    print("\nF8 - slice time step, 10 s vs 30 s (30 s by subsampling the 10 s slices)")
    print(
        f"  {'rule':<8} {'dt':>4} {'min':>6} {'n<0':>5} {'A<0 m²':>7} {'C free':>8} {'mean ASET shift':>16}"
    )
    coarse = [t for t in sorted(slices) if t % 30 == 0]
    for r in ("exists", "nearest"):
        fine = aset_map(slices, r, nx_cells, ny_cells)
        slow = aset_map(slices, r, nx_cells, ny_cells, times=coarse)
        both = np.isfinite(fine) & np.isfinite(slow)
        shift = float(np.mean(slow[both] - fine[both]))
        for dt, a, s in ((10, fine, ""), (30, slow, f"+{shift:.1f} s")):
            m = corrected_measures(a, rset)
            print(
                f"  {r:<8} {dt:>4d} {m['min']:>6.0f} {m['n_fail']:>5d} {m['area']:>7.2f}"
                f" {m['c_free']:>8.1f} {s:>16}"
            )
    print(
        "  The source is 10 s, so this is a lower bound of the bias against a continuous ASET."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="unpacked Zenodo release (doi:10.5281/zenodo.3875550), the folder with 0_ASET",
    )
    args = parser.parse_args()
    data = args.data.expanduser()
    if not (data / "0_ASET").is_dir():
        raise SystemExit(
            f"{data} has no 0_ASET; download doi:10.5281/zenodo.3875550 and unpack it"
        )
    try:
        from pedpy import compute_rset_map  # noqa: F401
    except ImportError:
        raise SystemExit('needs pedpy>=1.5.1: uv run --with "pedpy>=1.5.1" python ...')

    slices = read_slices(data)
    seeds = read_seeds(data)
    last = {s: int(traj.frame.max()) / rate for s, (rate, traj) in seeds.items()}
    assert max(last.values()) < T_END, "a seed is not empty before T_END"
    print(
        f"Release: {len(slices)} extinction slices {min(slices):.0f}-{max(slices):.0f} s,"
        f" {len(seeds)} seeds, last agent seen at {min(last.values()):.0f}-{max(last.values()):.0f} s"
        " of a 200 s run (no RSET censoring). Trajectories at 1 fps: Eq. 6 asks for"
        " dt <= w / v_max = 0.5 s.\n"
    )
    released = stage1(data, slices, seeds)
    asets, rset, shape, inside = stage2(data, slices, seeds, released)
    table_rules(asets, rset, inside)
    table_dt(slices, rset, shape)


if __name__ == "__main__":
    main()
