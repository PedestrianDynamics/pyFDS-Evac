#!/usr/bin/env python3
"""Build the Station V2 fire decks (FDS 6.10.1): Station geometry, prescribed
NIST Fig. 5-42 heat release, venting per NCSTAR Table 5-6.

Derived from the go/no-go generator (station_design_fire/gonogo_slow_0.2m/
make_deck.py). Kept from it: OBST extraction from Station210_clean.fds, the
crawlspace clip, z snapping to the 0.2 m lattice, the 3.6 m roof closure,
the plenum fill, removal of the 66 interior door leaves, hole probes and
devices. Changed: the t2 burner is replaced by foam/paneling burner surfaces
whose summed HRR follows the digitised Fig. 5-42 curve, the fuel is NIST's
C6.3H7.1NO2.1 with explicit yields, and doors and windows open at their
Table 5-6 times (T_REMOVE) instead of "doors open, windows closed".
See README.md.

Usage:
  python make_deck.py --all                 # the six production decks
  python make_deck.py --dx 0.2 --yields central [--meshes 32] [--shift-s -15]
  python make_deck.py --smoke               # station_smoke/, T_END=5, 8 meshes
  python make_deck.py --sealed              # station_sealed/, leak test
"""

from __future__ import annotations

import argparse
import functools
import itertools
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "Station210_clean.fds"
WALKABLE = HERE / "walkable_station-walkable_2985860.wkt"
HRR_CSV = HERE / "nist_fig5_42_hrr.csv"
DZ = 0.2  # z lattice of the geometry, in every deck (see README)
Z_TOP = 3.8
T_END = 250.0

# Yield scale factor on CO_YIELD and HCN_YIELD (not soot). The maintainer
# registered the yields as published (decisions.md, 2026-11-07): 1.0.
# The per-energy match to Purser's pairing would be 22.6/14.9 = 1.52.
YIELD_SCALE = 1.0

HEAT_OF_COMBUSTION = 22600.0  # kJ/kg: 13100 kJ/kg O2 x 7.025 x 32.00 / 130.3 (fire_inputs.md 2)
RADIATIVE_FRACTION = 0.35
# (SOOT_YIELD, CO_YIELD, HCN_YIELD) kg/kg, fire_inputs.md 3
YIELDS = {
    "low": (0.05, 0.010, 0.004),
    "central": (0.10, 0.246, 0.010),
    "high": (0.227, 0.246, 0.014),
}

_XB = re.compile(r"XB\s*=\s*([-\d.eE+]+(?:\s*,\s*[-\d.eE+]+){5})")
_RGB = re.compile(r"RGB\s*=\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)")
_SURF = re.compile(r"SURF_ID\s*=\s*'([^']*)'")
_TREM = re.compile(r"T_REMOVE\s*=\s*([-\d.eE+]+)")

# The L-shaped outline: 8 x-strips, z 0 - 3.8 m: (x0, x1, y0, y1).
STRIPS = [
    (-12.6, -8.4, -7.4, 3.8),
    (-8.4, -4.2, -19.2, 3.8),
    (-4.2, 0.0, -19.2, 3.8),
    (0.0, 4.2, -19.2, 3.8),
    (4.2, 8.4, -19.2, 3.8),
    (8.4, 12.6, -19.2, -1.4),
    (12.6, 16.0, -19.2, -1.4),
    (16.0, 20.6, -19.2, -1.4),
]
X0, Y0 = -12.6, -19.2

# Exterior faces of the L-shaped domain: 8 sides and 3 tops, all OPEN.
OPEN_VENTS = [
    (-12.6, -12.6, -7.4, 3.8, 0.0, Z_TOP),
    (-12.6, 8.4, 3.8, 3.8, 0.0, Z_TOP),
    (8.4, 8.4, -1.4, 3.8, 0.0, Z_TOP),
    (8.4, 20.6, -1.4, -1.4, 0.0, Z_TOP),
    (20.6, 20.6, -19.2, -1.4, 0.0, Z_TOP),
    (-8.4, 20.6, -19.2, -19.2, 0.0, Z_TOP),
    (-8.4, -8.4, -19.2, -7.4, 0.0, Z_TOP),
    (-12.6, -8.4, -7.4, -7.4, 0.0, Z_TOP),
    (-12.6, -8.4, -7.4, 3.8, Z_TOP, Z_TOP),
    (-8.4, 8.4, -19.2, 3.8, Z_TOP, Z_TOP),
    (8.4, 20.6, -19.2, -1.4, Z_TOP, Z_TOP),
]

# The four exits, cut by &HOLE to z = 2.0 m when the door leaf's T_REMOVE
# time (NCSTAR Table 5-6) is reached: (name, XB, time s).
HOLES = [
    ("front", (2.4, 4.4, -17.4, -17.0, 0.0, 2.0), 30),
    ("kitchen", (-6.4, -5.8, -8.6, -7.6, 0.0, 2.0), 60),
    ("main_bar_side", (-6.4, -5.8, -13.6, -12.6, 0.0, 2.0), 45),
    ("platform_exit", (17.6, 18.2, -12.4, -11.4, 0.0, 2.0), 29),
]
# Flow probes in each hole: (name, quantity, xyz); non-zero flow proves open.
HOLE_PROBES = [
    ("V_front", "V-VELOCITY", (3.4, -17.2, 1.0)),
    ("U_kitchen", "U-VELOCITY", (-6.1, -8.1, 1.0)),
    ("U_main_bar_side", "U-VELOCITY", (-6.1, -13.1, 1.0)),
    ("U_platform_exit", "U-VELOCITY", (17.9, -11.9, 1.0)),
]
# T_REMOVE times of the source deck, as Enrico mapped them (fire_inputs.md 5).
DOOR_TIMES = {29, 30, 45, 60}
WINDOW_TIMES = {78, 80, 100, 110, 120, 130}
FACE_NAMES = ("BAY WINDOW GLASS", "FRONT WINDOW", "A-WDWK", "A-DOOR-STND")

# NCSTAR 2 Sec. 5.3.4 head layout mapped to deck coordinates (logged only).
HEADS = [
    ("alcove", (19.0, -7.7, 3.5)),
    ("NE", (15.9, -5.9, 3.5)),
    ("SE", (15.9, -9.5, 3.5)),
    ("NW", (12.3, -5.9, 3.5)),
    ("SW", (12.3, -9.5, 3.5)),
]
HEAD_PROPS = ("NIST", "QR", "SR")

# K and T device trees, z = 0.2 ... 3.4 m every 0.2 m.
TREES: list[tuple[str, tuple[float, float]]] = [
    ("dance", (12.5, -12.5)),      # main room in front of the platform, 3.6 m ceiling
    ("mid", (5.1, -8.1)),          # centre of the building under the 2.6 m ceiling
    ("bar", (-5.1, -11.1)),        # main-bar room, west of the horseshoe bar, 2.6 m ceiling
    ("sunroom", (-3.1, 0.7)),
    ("westwing", (-10.3, -2.1)),
    ("frontdoor", (3.5, -16.3)),
    ("platexit", (17.1, -11.9)),
]
# V6 zone probes at 1.5 m (fire_inputs.md 4 and 6): (name, x, y).
ZONE_PROBES = [
    ("dance_floor", 12.4, -8.0),
    ("main_bar", -2.0, -13.0),
    ("foyer", 3.4, -15.0),
    ("sunroom_zone", 9.9, -15.2),
    ("dart_room", 0.0, -6.0),
]
# 1.6 m falls on the 1.5 m plane at 0.2 m (smoke run: both k = 8); at 0.1 m the
# face-to-lower-cell rule that put 2.0 m on k = 10 gives distinct planes.
SLICE_HEIGHTS = {0.2: (2.0, 1.5), 0.1: (2.0, 1.6, 1.5)}

# --- burner surfaces (fire_inputs.md 4, A5/A6) -------------------------------
# Each element is a face that burns toward the room, on the lattice:
#   ("vent", XB, outward normal)  a VENT on an existing thick foam face
#   ("slab", XB, outward normal)  a one-cell OBST in front of a thin foam or
#                                 paneling plane, burning on one face
# The source geometry is almost all zero-thickness planes, so most foam and
# paneling surfaces cannot carry a VENT; the slabs stand in for them.
# Groups ignite in NCSTAR's order; START is the time (s) the group joins the
# burning area, in the unshifted time base. RAMP_ON is the time it takes to
# join.
RAMP_ON = 3.0
BURNERS = {
    "G0_alcove_corners": (0.0, [
        ("vent", (17.8, 18.4, -6.2, -6.2, 1.0, 3.6), "-y"),
        ("vent", (17.8, 18.4, -9.0, -9.0, 1.0, 3.6), "+y"),
    ]),
    "G1_alcove": (50.0, [
        ("vent", (18.4, 20.0, -6.2, -6.2, 1.0, 3.6), "-y"),
        ("vent", (18.4, 20.0, -9.0, -9.0, 1.0, 3.6), "+y"),
        ("vent", (20.0, 20.0, -9.0, -6.2, 1.0, 3.6), "-x"),
        ("slab", (18.0, 20.0, -9.0, -6.2, 3.4, 3.6), "-z"),
    ]),
    "G2_platform_wall": (55.0, [
        ("slab", (17.6, 17.8, -11.4, -9.4, 0.6, 3.6), "-x"),
        ("slab", (17.6, 17.8, -6.0, -2.8, 0.6, 3.6), "-x"),
    ]),
    "G3_rear_wall_and_dance_ceiling": (65.0, [
        ("slab", (6.8, 17.6, -3.0, -2.8, 1.0, 3.6), "-y"),
        ("slab", (12.0, 16.0, -9.0, -4.0, 3.4, 3.6), "-z"),
    ]),
    "G4_sunroom": (90.0, [
        ("slab", (5.0, 15.0, -17.0, -13.0, 3.4, 3.6), "-z"),
        ("slab", (4.4, 4.6, -17.0, -12.8, 0.2, 3.6), "+x"),
    ]),
    "G5_main_bar": (100.0, [
        ("slab", (-5.0, 1.0, -16.0, -10.6, 2.4, 2.6), "-z"),
    ]),
}


def snap_z(z: float) -> float:
    """0.2 m lattice: floor above 2.0 m, nearest at or below (FP-guarded)."""
    if z > 2.0 + 1e-9:
        return round(math.floor(z / DZ + 1e-6) * DZ, 6)
    return round(round(z / DZ) * DZ, 6)


def parse_obst(path: Path):
    out = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("&OBST"):
            continue
        v = [float(t) for t in _XB.search(line).group(1).split(",")]
        m = _RGB.search(line)
        rgb = tuple(float(c) for c in m.groups()) if m else None
        name = line.split("/")[-1].strip() or "?"
        out.append((name, v, rgb))
    return out


def parse_obst_extra(path: Path):
    """(SURF_ID, T_REMOVE) per &OBST line, aligned with parse_obst."""
    out = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("&OBST"):
            continue
        s = _SURF.search(line)
        t = _TREM.search(line)
        out.append((s.group(1) if s else None, float(t.group(1)) if t else None))
    return out


# --- door classification, as in scripts/generate_walkable_from_fds.py -----
HORIZONTAL_FINISHES = (
    "A-FLOR", "A-CEIL", "A-STRS-TRED", "A-RISR", "carpet", "A-PLAT-RIM", "A-HRAL",
)


def _is_door(name: str) -> bool:
    return "door" in name.lower()


def _blocks(name: str) -> bool:
    if _is_door(name):
        return False
    return not any(p in name for p in HORIZONTAL_FINISHES)


def _footprint(x0, x1, y0, y1, half_cell=0.05):
    lo_x, hi_x = sorted((x0, x1))
    lo_y, hi_y = sorted((y0, y1))
    if hi_x - lo_x < 1e-9:
        lo_x, hi_x = lo_x - half_cell, hi_x + half_cell
    if hi_y - lo_y < 1e-9:
        lo_y, hi_y = lo_y - half_cell, hi_y + half_cell
    return box(lo_x, lo_y, hi_x, hi_y)


def interior_door_leaves(obst, z_lo=0.1, z_hi=1.8, tol=0.15) -> set[int]:
    """Indices into *obst* of interior door leaves (removed in FDS)."""
    band = [(i, n, v) for i, (n, v, _) in enumerate(obst) if v[5] >= z_lo and v[4] <= z_hi]
    walls = [_footprint(*v[:4]) for _, n, v in band if _blocks(n)]
    doors = [(i, _footprint(*v[:4])) for i, n, v in band if _is_door(n)]
    # FDS 4 domain footprint, as the walkable script uses (&PDIM boxes)
    pdim = re.compile(r"(XBAR0|XBAR|YBAR0|YBAR)\s*=\s*([-\d.eE+]+)")
    meshes = []
    for raw in SOURCE.read_text(errors="replace").splitlines():
        if raw.strip().startswith("&PDIM"):
            g = dict(pdim.findall(raw))
            meshes.append(box(float(g["XBAR0"]), float(g["YBAR0"]), float(g["XBAR"]), float(g["YBAR"])))
    domain = unary_union(meshes)
    sealed = domain.difference(unary_union(walls + [s for _, s in doors]))
    outside = [p for p in getattr(sealed, "geoms", [sealed]) if p.exterior.intersects(domain.boundary)]
    outdoors = unary_union(outside)
    exterior = {i for i, s in doors if s.buffer(tol).intersects(outdoors)}
    return {i for i, _ in doors} - exterior, exterior


ROOF_BUFFER = 0.6
ALCOVE_ROOF = (17.6, 20.4, -9.6, -5.0)  # x0, x1, y0, y1


def roof_strips(walkable_wkt: Path) -> list[tuple[float, float, float, float]]:
    """Thin roof at z = 3.6 m over the building footprint, as row strips.

    Snapping ceilings and wall tops down to 3.6 m opens wall cavities and
    ceiling-edge gaps to the 3.6-3.8 m layer, which is outdoors (OPEN top).
    The source deck closed these with plates at 3.70-3.80 m that snap into
    the same layer. This roof restores the envelope: footprint = walkable
    outline (holes filled) buffered by ROOF_BUFFER, plus the stage alcove.
    """
    from shapely import wkt as _wkt
    from shapely.geometry import Polygon

    walk = _wkt.loads(walkable_wkt.read_text())
    foot = Polygon(walk.exterior).buffer(ROOF_BUFFER, join_style=2).union(box(ALCOVE_ROOF[0], ALCOVE_ROOF[2], ALCOVE_ROOF[1], ALCOVE_ROOF[3]))
    strips = []
    for j in range(115):
        y0 = round(-19.2 + 0.2 * j, 6)
        run = None
        for i in range(167):
            x0 = round(-12.6 + 0.2 * i, 6)
            inside = i < 166 and foot.contains(box(x0, y0, x0 + 0.2, y0 + 0.2).centroid)
            if inside and run is None:
                run = x0
            elif not inside and run is not None:
                strips.append((run, x0, y0, round(y0 + 0.2, 6)))
                run = None
    return strips


def is_dropped_ceiling_plate(name: str, z0: float, z1: float) -> bool:
    """Thin horizontal ceiling plate below the 3.6 m roof (bar and centre)."""
    layer = name.rstrip("0123456789-").strip()
    return layer in ("ceiling", "A-CEIL-MAIN") and abs(z1 - z0) < 1e-6 and 2.3 < z0 < 3.6




def fmt(v) -> str:
    return ",".join(f"{x:.4f}".rstrip("0").rstrip(".") if abs(x) > 0 else "0" for x in v)


# --- lattice model of the snapped geometry ---------------------------------
class Grid:
    """Cell occupancy of the snapped deck at the mesh spacing dx.

    Only thick obstructions fill cells. Zero-thickness ones (most of the
    source deck) are recorded as planes, for the mesh-interface audit.
    """

    def __init__(self, dx: float):
        self.dx = dx
        self.org = (X0, Y0, 0.0)
        self.n = (round((20.6 - X0) / dx), round((3.8 - Y0) / dx), round(Z_TOP / dx))
        self.solid = np.zeros(self.n, bool)
        self.inmesh = np.zeros(self.n, bool)
        for a, b, c, d in STRIPS:
            self.inmesh[self.ix(a, 0):self.ix(b, 0), self.ix(c, 1):self.ix(d, 1), :] = True
        self.thin_y: dict[int, list] = {}
        self.thin_z: dict[int, list] = {}

    def ix(self, v: float, axis: int) -> int:
        return int(math.floor((v - self.org[axis]) / self.dx + 0.5 + 1e-9))

    def snap_box(self, xb) -> list[int]:
        return [self.ix(xb[i], i // 2) for i in range(6)]

    def coord(self, axis: int, idx: int) -> float:
        return round(self.org[axis] + idx * self.dx, 6)

    def add(self, xb) -> None:
        a = self.snap_box(xb)
        lo = [max(a[2 * i], 0) for i in range(3)]
        hi = [min(a[2 * i + 1], self.n[i]) for i in range(3)]
        if a[2] == a[3] and a[0] != a[1] and a[4] != a[5]:
            self.thin_y.setdefault(a[2], []).append((a[0], a[1]))
        if a[4] == a[5] and a[0] != a[1] and a[2] != a[3]:
            self.thin_z.setdefault(a[4], []).append((a[0], a[1], a[2], a[3]))
        if any(hi[i] <= lo[i] for i in range(3)):
            return
        self.solid[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] = True

    def face_mask(self, xb, nrm: str, vent: bool):
        """Boolean array over the two transverse axes: faces of the box that
        burn toward the outward normal *nrm* ('-x', '+z', ...). A VENT must
        lie on a real solid face, so its plane moves by up to two cells to
        the offset with the most valid faces (a wall that snaps differently
        at another dx)."""
        a = self.snap_box(xb)
        ax = "xyz".index(nrm[1])
        neg = nrm[0] == "-"
        tr = [i for i in range(3) if i != ax]
        base = a[2 * ax] if neg or vent else a[2 * ax + 1]
        best = None
        for off in ((0, 1, -1, 2, -2) if vent else (0,)):
            plane = base + off
            outer = plane - 1 if neg else plane
            inner = plane if neg else plane - 1
            if not (0 <= outer < self.n[ax] and 0 <= inner < self.n[ax]):
                continue
            sl_o: list = [None] * 3
            sl_i: list = [None] * 3
            for i in tr:
                sl_o[i] = sl_i[i] = slice(a[2 * i], a[2 * i + 1])
            sl_o[ax], sl_i[ax] = outer, inner
            gas = self.inmesh[tuple(sl_o)] & ~self.solid[tuple(sl_o)]
            if vent:
                gas = gas & self.solid[tuple(sl_i)]
            if best is None or gas.sum() > best[0].sum():
                best = (gas, ax, plane, tr, a)
        return best

    def conflicts_y(self, plane: int, ia: int, ib: int) -> int:
        return sum(1 for i0, i1 in self.thin_y.get(plane, []) if i1 > ia and i0 < ib)

    def conflicts_z(self, plane: int) -> int:
        return len(self.thin_z.get(plane, []))


def rectangles(mask):
    """Greedy cover of a 2D boolean mask by half-open rectangles."""
    m = mask.copy()
    out = []
    for a in range(m.shape[0]):
        b = 0
        while b < m.shape[1]:
            if not m[a, b]:
                b += 1
                continue
            b1 = b
            while b1 < m.shape[1] and m[a, b1]:
                b1 += 1
            a1 = a + 1
            while a1 < m.shape[0] and m[a1, b:b1].all():
                a1 += 1
            m[a:a1, b:b1] = False
            out.append((a, a1, b, b1))
            b = b1
    return out


# --- meshes ------------------------------------------------------------------
def _smooth(n: int) -> bool:
    for p in (2, 3, 5):
        while n % p == 0:
            n //= p
    return n == 1


def split_cells(n: int, parts: int, conflict) -> list[int]:
    """Split n cells into parts of 2-3-5-smooth size (FFT pressure solver),
    near uniform, avoiding interfaces where conflict(cumulative) > 0."""
    if parts == 1:
        return [n]
    avg = n / parts
    cands = [s for s in range(1, n + 1) if _smooth(s) and 0.6 * avg <= s <= 1.4 * avg + 1]
    dp: list[dict] = [dict() for _ in range(parts + 1)]
    dp[0][0] = (0.0, None)
    for p in range(parts):
        for cum, (c, _) in dp[p].items():
            for s in cands:
                nc = cum + s
                if nc > n or (p == parts - 1 and nc != n):
                    continue
                cost = c + (s - avg) ** 2 + (1000 * conflict(nc) if p < parts - 1 else 0)
                if nc not in dp[p + 1] or cost < dp[p + 1][nc][0]:
                    dp[p + 1][nc] = (cost, cum)
    if n not in dp[parts]:
        raise SystemExit(f"no smooth split of {n} cells into {parts} parts")
    sizes, cum = [], n
    for p in range(parts, 0, -1):
        prev = dp[p][cum][1]
        sizes.append(cum - prev)
        cum = prev
    return sizes[::-1]


def mesh_layout(grid: Grid, n_meshes: int):
    """Meshes as (id, xb, ijk). N = 8 strips x ny (y) x nz (z)."""
    if n_meshes % 8:
        raise SystemExit("--meshes must be a multiple of 8")
    nz = 2 if n_meshes >= 128 else 1
    ny = n_meshes // 8 // nz
    dx = grid.dx
    ktot = grid.n[2]
    if nz == 2:
        ks = split_cells(ktot, 2, grid.conflicts_z)
    else:
        ks = [ktot]
    meshes, audit = [], []
    for sx0, sx1, sy0, sy1 in STRIPS:
        ia, ib = grid.ix(sx0, 0), grid.ix(sx1, 0)
        ja, jb = grid.ix(sy0, 1), grid.ix(sy1, 1)
        js = split_cells(jb - ja, ny, lambda cum, ja=ja, ia=ia, ib=ib: grid.conflicts_y(ja + cum, ia, ib))
        for jc in itertools.accumulate(js[:-1]):
            audit.append(grid.conflicts_y(ja + jc, ia, ib))
        j0 = ja
        for jn in js:
            k0 = 0
            for kn in ks:
                xb = (sx0, sx1, grid.coord(1, j0), grid.coord(1, j0 + jn), grid.coord(2, k0), grid.coord(2, k0 + kn))
                meshes.append((f"M{len(meshes) + 1:03d}", xb, (ib - ia, jn, kn)))
                k0 += kn
            j0 += jn
    if nz == 2:
        audit.append(grid.conflicts_z(ks[0]))
    return meshes, sum(audit)


# --- prescribed heat release -------------------------------------------------
def load_curve() -> np.ndarray:
    rows = [ln.split(",") for ln in HRR_CSV.read_text().splitlines() if ln and not ln.startswith(("#", "t_s"))]
    return np.array([[float(a), float(b)] for a, b in rows])


def ramp_tables(curve: np.ndarray, shift: float, areas: dict[str, float]):
    """Per-group RAMP_Q tables of heat release per unit area (kW/m2).

    All groups share one knot set (curve knots, zone start knots), so the
    sum of the group heat releases is the piecewise-linear curve exactly.
    The equal-flux rule: F_k(t) = HRR(t) w_k(t) / sum_j w_j(t) A_j.
    """
    t_all, q_all = curve[:, 0] + shift, curve[:, 1]
    starts = {g: BURNERS[g][0] + (shift if BURNERS[g][0] > 0 else 0.0) for g in BURNERS}
    knots = {0.0} | {float(t) for t in t_all if t >= 0.0}
    for s in starts.values():
        if s > 0:
            knots |= {s, s + RAMP_ON}
    ts = np.array(sorted(knots))
    hrr = np.interp(ts, t_all, q_all)  # holds the end values outside the curve

    def w(g, t):
        s = starts[g]
        return np.ones_like(t) if BURNERS[g][0] == 0 else np.clip((t - s) / RAMP_ON, 0.0, 1.0)

    s_sum = sum(w(g, ts) * areas[g] for g in BURNERS)
    return ts, hrr, {g: hrr * w(g, ts) / s_sum for g in BURNERS}, t_all


def ramp_lines(ts, tables) -> list[str]:
    out = []
    for g, f in tables.items():
        gid = g.split("_")[0]
        for t, v in zip(ts, f):
            out.append(f"&RAMP ID='RQ_{gid}', T={t:.4f}, F={v:.6g} /")
    return out


def check_hrr(lines: list[str], areas, ts, hrr) -> float:
    """Re-read the written RAMPs: sum_k A_k F_k(t_i) against the curve."""
    rx = re.compile(r"&RAMP ID='RQ_(\w+)', T=([-\d.]+), F=([-\d.eE+]+) /")
    tab: dict[str, dict[float, float]] = {}
    for ln in lines:
        m = rx.match(ln)
        tab.setdefault(m.group(1), {})[float(m.group(2))] = float(m.group(3))
    worst = 0.0
    for t, h in zip(ts, hrr):
        tot = sum(areas[g] * tab[g.split("_")[0]][round(float(t), 4)] for g in BURNERS)
        worst = max(worst, abs(tot - h) / h)
    if worst > 0.01:
        raise SystemExit(f"prescribed HRR differs from the curve by {100 * worst:.3f} % (> 1 %)")
    return worst


def overlap(a: list[int], b: list[int]) -> bool:
    """Do two snapped boxes share a face or volume of positive measure?"""
    for ax in range(3):
        lo, hi = max(a[2 * ax], b[2 * ax]), min(a[2 * ax + 1], b[2 * ax + 1])
        if hi < lo:
            return False
        if hi == lo and a[2 * ax] != a[2 * ax + 1] and b[2 * ax] != b[2 * ax + 1]:
            return False
    return True


# --- deck ----------------------------------------------------------------------
def chid_for(mode: str, dx: float, yields: str, shift: float) -> str:
    if mode in ("smoke", "sealed"):
        return f"station_{mode}"
    s = "" if shift == 0 else f"_{'m' if shift < 0 else 'p'}{abs(shift):g}"
    return f"station_dx{round(dx * 100):03d}_{yields}{s}"


def build(mode: str, dx: float, yields: str, n_meshes: int, shift: float) -> tuple[str, dict]:
    obst = parse_obst(SOURCE)
    extra = parse_obst_extra(SOURCE)
    interior, exterior = interior_door_leaves(obst)
    grid = Grid(dx)
    kept, stats = [], Counter()
    zhist: Counter = Counter()
    for i, (name, v, rgb) in enumerate(obst):
        if i in interior:
            stats["interior door leaf removed"] += 1
            continue
        z0, z1 = sorted((v[4], v[5]))
        if z1 <= 0.0:
            stats["dropped (z1 <= 0)"] += 1
            continue
        if z0 < 0.0:
            stats["clipped at z = 0"] += 1
            z0 = 0.0
        z0s, z1s = snap_z(z0), snap_z(z1)
        if is_dropped_ceiling_plate(name, z0, z1):
            # Fill the plenum above a dropped-ceiling plate: after snapping it
            # connects to the rooms through edge gaps (about 100 m3 of extra
            # smoke reservoir). NIST already filled most other plenum bays
            # with solid 2.72-3.70 m blocks; this does the same for the rest.
            z1s = 3.6
            stats["dropped-ceiling plate filled to 3.6 m"] += 1
        zhist[z0s] += 1
        zhist[z1s] += 1
        kept.append([name, (v[0], v[1], v[2], v[3], z0s, z1s), rgb, extra[i][1]])
    stats["exterior door leaves kept"] = len(exterior)

    # Venting times: must be the ones Enrico mapped (fire_inputs.md 5).
    times = {int(k[3]) for k in kept if k[3] is not None}
    door_t = {int(k[3]) for k in kept if k[3] is not None and int(k[3]) in DOOR_TIMES}
    if times != DOOR_TIMES | WINDOW_TIMES:
        raise SystemExit(f"T_REMOVE times {sorted(times)} differ from Table 5-6 mapping")
    for hid, hxb, ht in HOLES:
        hit = [k for k in kept if k[3] == ht and overlap(grid.snap_box(k[1]), grid.snap_box(hxb))]
        if not hit:
            raise SystemExit(f"hole {hid}: no door leaf with T_REMOVE={ht} inside it")

    # Line-1923 hazard: a non-removable thin piece that snaps onto the face of
    # a removable window or door keeps that part shut after the removal time.
    # Pieces of glass, window trim and door frame lying wholly inside the
    # removable face are dropped; one stacked above it is trimmed to start
    # where the removable piece ends. Other overlaps are only reported.
    removable = [grid.snap_box(k[1]) for k in kept if k[3] is not None]
    dropped_glass, trimmed, other_conf = [], [], []
    for k in list(kept):
        if k[3] is not None:
            continue
        sb = grid.snap_box(k[1])
        deg = {ax for ax in range(3) if sb[2 * ax] == sb[2 * ax + 1]}
        hits = [r for r in removable if overlap(sb, r) and deg and deg == {ax for ax in range(3) if r[2 * ax] == r[2 * ax + 1]}]
        if not hits:
            if any(overlap(sb, r) for r in removable):
                other_conf.append((k[0], k[1]))
            continue
        if not k[0].startswith(FACE_NAMES):
            other_conf.append((k[0], k[1]))
            continue
        flat = [ax for ax in range(3) if ax not in deg]
        if any(all(r[2 * ax] <= sb[2 * ax] and r[2 * ax + 1] >= sb[2 * ax + 1] for ax in flat) for r in hits):
            dropped_glass.append((k[0], k[1]))
            kept.remove(k)
            continue
        r = next((r for r in hits if r[4] <= sb[4] < r[5] < sb[5]
                  and all(r[2 * ax] <= sb[2 * ax] and r[2 * ax + 1] >= sb[2 * ax + 1] for ax in flat if ax != 2)), None)
        if r is None:
            other_conf.append((k[0], k[1]))
            continue
        trimmed.append((k[0], k[1]))
        k[1] = (*k[1][:4], grid.coord(2, r[5]), k[1][5])
    stats["fixed pieces dropped (wholly inside a removable face)"] = len(dropped_glass)
    stats["fixed pieces trimmed (stacked above a removable face)"] = len(trimmed)
    stats["other fixed obstructions overlapping a removable one (left)"] = len(other_conf)
    stats["kept"] = len(kept)

    roof = roof_strips(WALKABLE)
    for k in kept:
        grid.add(k[1])
    for r in roof:
        grid.add((r[0], r[1], r[2], r[3], 3.6, 3.6))

    # burner surfaces
    slabs = [(g, e) for g, (_, els) in BURNERS.items() for e in els if e[0] == "slab"]
    for _, e in slabs:
        grid.add(e[1])
    areas = {g: 0.0 for g in BURNERS}
    vents = []  # (group, xb)
    slab_area = {}
    for g, (_, els) in BURNERS.items():
        for kind, xb, nrm in els:
            mask, ax, plane, tr, a = grid.face_mask(xb, nrm, vent=(kind == "vent"))
            n_ok = int(mask.sum())
            areas[g] += n_ok * dx * dx
            slab_area[(g, kind, xb)] = (n_ok, mask.size)
            if kind != "vent":
                continue
            for r in rectangles(mask):
                bb = [0.0] * 6
                bb[2 * ax] = bb[2 * ax + 1] = grid.coord(ax, plane)
                for n_, t_ in enumerate(tr):
                    lo = a[2 * t_] + r[2 * n_]
                    hi = a[2 * t_] + r[2 * n_ + 1]
                    bb[2 * t_], bb[2 * t_ + 1] = grid.coord(t_, lo), grid.coord(t_, hi)
                vents.append((g, tuple(bb)))
    for g, ar in areas.items():
        if ar <= 0:
            raise SystemExit(f"burner group {g} has no burning faces")

    # fuel feasibility
    soot, co, hcn = YIELDS[yields]
    co, hcn = co * YIELD_SCALE, hcn * YIELD_SCALE
    c_used = soot + co * 12.011 / 28.010 + hcn * 12.011 / 27.025
    if c_used > 0.580 or hcn * 14.007 / 27.025 > 0.1074:
        raise SystemExit("yields exceed the fuel's carbon or nitrogen content")

    curve = load_curve()
    ts, hrr, tables, t_all = ramp_tables(curve, shift, areas)
    rlines = ramp_lines(ts, tables)
    worst = check_hrr(rlines, areas, ts, hrr)
    peak_flux = max(float(f.max()) for f in tables.values())

    n_default = {0.2: 32, 0.1: 128}.get(dx, 8)
    meshes, mesh_conf = mesh_layout(grid, n_meshes or (8 if mode in ("smoke", "sealed") else n_default))
    cells = sum(m[2][0] * m[2][1] * m[2][2] for m in meshes)

    chid = chid_for(mode, dx, yields, shift)
    t_end = {"prod": T_END, "smoke": 5.0, "sealed": 1.0}[mode]
    if mode == "prod" and shift < 0:
        # No HRR beyond NIST's data: stop at the last output time (DT_SLCF=1 s)
        # not past the shifted end of the curve.
        t_end = float(math.floor(t_all[-1]))
    L = []
    w = L.append
    w(f"&HEAD CHID='{chid}', TITLE='Station-derived geometry (provenance unverified), prescribed NIST HRR, {dx:g} m' /")
    w("! Generated by make_deck.py from Station210_clean.fds (origin/feat/station-walkable, 2985860). Do not edit by hand.")
    w(f"! yields={yields} yield_scale={YIELD_SCALE:g} dx={dx:g} meshes={len(meshes)} hrr_shift_s={shift:g}")
    if t_end < T_END:
        w(f"! HRR ramp shifted {shift:g} s: the curve ends at {t_all[-1]:.1f} s, so T_END is {t_end:g} s; no HRR is held past the data.")
    if shift > 0:
        w(f"! HRR ramp shifted {shift:g} s: the first point is at {t_all[0]:.1f} s; the HRR is held at its first value (72 kW) from 0 to there (not NIST data).")
    w(f"&TIME T_END={t_end:.1f} /")
    w("&MISC MINIMUM_ZONE_VOLUME=1000. /")
    w("&DUMP DT_SLCF=1.0, DT_DEVC=1.0, DT_HRR=1.0, DT_RESTART=25. /")
    w("")
    for mid, xb, ijk in meshes:
        w(f"&MESH ID='{mid}', XB={fmt(xb)}, IJK={ijk[0]},{ijk[1]},{ijk[2]} /")
    w("")
    w("! Fuel: NIST C6.3H7.1NO2.1 (NCSTAR 2 App. L2.2), dH = 22.6 MJ/kg (fire_inputs.md 2); yields kg/kg (fire_inputs.md 3)")
    w(f"&REAC ID='POLYURETHANE', FUEL='POLYURETHANE', C=6.3, H=7.1, O=2.1, N=1., HEAT_OF_COMBUSTION={HEAT_OF_COMBUSTION:.0f}.,")
    w(f"      SOOT_YIELD={soot:g}, CO_YIELD={co:.6g}, HCN_YIELD={hcn:.6g}, RADIATIVE_FRACTION={RADIATIVE_FRACTION:g} /")
    w("")
    w("&MATL ID='GYPSUM', CONDUCTIVITY=0.48, SPECIFIC_HEAT=0.84, DENSITY=1400. /")
    w("&SURF ID='LINING', MATL_ID='GYPSUM', THICKNESS=0.013, DEFAULT=T /")
    w("")
    w("! Prescribed burner surfaces: HRRPUA=1 x RAMP_Q = kW/m2 of the group's burning faces.")
    w("! Their sum is NIST Fig. 5-42 (nist_fig5_42_hrr.csv); NIST's four ignition vents are NOT included.")
    for g in BURNERS:
        gid = g.split("_")[0]
        w(f"&SURF ID='BURN_{gid}', HRRPUA=1., RAMP_Q='RQ_{gid}', COLOR='RED' /  ! {g}: {areas[g]:.2f} m2, joins at {BURNERS[g][0] + (shift if BURNERS[g][0] > 0 else 0):g} s")
    L.extend(rlines)
    w("")
    w("! Venting (NCSTAR Table 5-6). In FDS 6.10.1 an &OBST with DEVC_ID exists while its device is true, so the")
    w("! timers that carry leaves and windows start TRUE (present at t = 0, removed at the setpoint); the timers")
    w("! that carry the exit &HOLEs start FALSE (shut at t = 0, cut at the setpoint).")
    for t in sorted(times):
        w(f"&DEVC ID='TIMER_{t:03d}', QUANTITY='TIME', XYZ=0,0,1, SETPOINT={t:.1f}, INITIAL_STATE=.TRUE. /")
    for t in sorted({h[2] for h in HOLES}):
        w(f"&DEVC ID='TIMERH_{t:03d}', QUANTITY='TIME', XYZ=0,0,1, SETPOINT={t:.1f}, INITIAL_STATE=.FALSE. /")
    w("")
    w("! Heat detectors (logged only, no suppression)")
    w("&PROP ID='NIST', QUANTITY='LINK TEMPERATURE', RTI=16.,  ACTIVATION_TEMPERATURE=74. /  ! NCSTAR 2 Table 5-2, fitted effective")
    w("&PROP ID='QR',   QUANTITY='LINK TEMPERATURE', RTI=50.,  ACTIVATION_TEMPERATURE=68. /  ! quick-response bound")
    w("&PROP ID='SR',   QUANTITY='LINK TEMPERATURE', RTI=200., ACTIVATION_TEMPERATURE=68. /  ! Schroeder 2017 pp. 82-83")
    for hid, xyz in HEADS:
        for p in HEAD_PROPS:
            w(f"&DEVC ID='HD_{hid}_{p}', PROP_ID='{p}', XYZ={fmt(xyz)} /")
    w("")
    w("! Flow through each exit hole")
    for did, q, xyz in HOLE_PROBES:
        w(f"&DEVC ID='{did}', QUANTITY='{q}', XYZ={fmt(xyz)} /")
    w("")
    w("! K and T device trees, z = 0.2 ... 3.4 m")
    for tid, (x, y) in TREES:
        for k in range(1, 18):
            z = round(0.2 * k, 1)
            w(f"&DEVC ID='K_{tid}_{z:.1f}', QUANTITY='EXTINCTION COEFFICIENT', XYZ={fmt((x, y, z))} /")
            w(f"&DEVC ID='T_{tid}_{z:.1f}', QUANTITY='TEMPERATURE', XYZ={fmt((x, y, z))} /")
    w("")
    w("! V6 zone probes at 1.5 m: gas temperature and O2 volume fraction")
    for zid, x, y in ZONE_PROBES:
        w(f"&DEVC ID='T15_{zid}', QUANTITY='TEMPERATURE', XYZ={fmt((x, y, 1.5))} /")
        w(f"&DEVC ID='O2_15_{zid}', QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN', XYZ={fmt((x, y, 1.5))} /")
    w("")
    w("! Slices: 2.0 m (and 1.6 m at 0.1 m only) for the maps, 1.5 m for T5 and T6")
    for pbz in SLICE_HEIGHTS[dx]:
        w(f"&SLCF PBZ={pbz:.1f}, QUANTITY='EXTINCTION COEFFICIENT' /")
        w(f"&SLCF PBZ={pbz:.1f}, QUANTITY='TEMPERATURE' /")
        for s in ("CARBON MONOXIDE", "CARBON DIOXIDE", "OXYGEN", "HYDROGEN CYANIDE"):
            w(f"&SLCF PBZ={pbz:.1f}, QUANTITY='VOLUME FRACTION', SPEC_ID='{s}' /")
    w("&SLCF PBY=-7.6, QUANTITY='EXTINCTION COEFFICIENT' /")
    w("&SLCF PBY=-7.6, QUANTITY='TEMPERATURE' /")
    w("")
    for xb in OPEN_VENTS:
        w(f"&VENT XB={fmt(xb)}, SURF_ID='OPEN' /")
    w("")
    w("! Geometry: z snapped (above 2.0 m down, else nearest); SURF_ID stripped; T_REMOVE -> DEVC_ID")
    for name, v, rgb, trem in kept:
        col = f", RGB={','.join(str(int(round(c * 255))) for c in rgb)}" if rgb else ""
        dev = f", DEVC_ID='TIMER_{int(trem):03d}'" if trem is not None else ""
        w(f"&OBST XB={fmt(v)}{col}{dev} /  {name}")
    w("")
    w("! Roof closure at z = 3.6 m (see roof_strips); not in the source deck")
    for x0, x1, y0, y1 in roof:
        w(f"&OBST XB={fmt((x0, x1, y0, y1, 3.6, 3.6))} /  roof closure")
    w("")
    w("! Burner slabs (one cell thick, burning on one face; listed after the geometry so they override it)")
    for g, (kind, xb, nrm) in [(g, e) for g, e in slabs]:
        gid = g.split("_")[0]
        idx = {"-x": 0, "+x": 1, "-y": 2, "+y": 3, "-z": 4, "+z": 5}[nrm]
        ids = ["LINING"] * 6
        ids[idx] = f"BURN_{gid}"
        w(f"&OBST XB={fmt(xb)}, SURF_ID6={','.join(repr(s) for s in ids)} /  {g}")
    w("")
    w("! Burner faces on existing thick foam walls")
    for g, xb in vents:
        w(f"&VENT XB={fmt(xb)}, SURF_ID='BURN_{g.split('_')[0]}' /  {g}")
    if mode == "sealed":
        w("")
        w("! Leak test: every interior probe must report a non-zero pressure zone")
        for tid, (x, y) in TREES:
            w(f"&DEVC ID='PZ_{tid}', QUANTITY='PRESSURE ZONE', XYZ={fmt((x, y, 1.0))} /")
        w("&DEVC ID='PZ_outdoors', QUANTITY='PRESSURE ZONE', XYZ=-10.3,-15.1,1.0 /")
    else:
        w("")
        for hid, xb, ht in HOLES:
            w(f"&HOLE XB={fmt(xb)}, DEVC_ID='TIMERH_{ht:03d}' /  exit: {hid}, opens at {ht} s")
    w("")
    w("&TAIL /")

    # zone probes must sit in gas
    bad = []
    for zid, x, y in ZONE_PROBES:
        i, j, k = grid.ix(x, 0), grid.ix(y, 1), grid.ix(1.5, 2)
        if grid.solid[i, j, k]:
            bad.append(zid)
    info = {
        "chid": chid, "stats": stats, "zhist": zhist, "cells": cells, "meshes": len(meshes),
        "mesh_conflicts": mesh_conf, "areas": areas, "peak_flux": peak_flux, "worst": worst,
        "dropped_glass": dropped_glass, "trimmed": trimmed, "other_conf": other_conf, "slab_area": slab_area,
        "bad_probes": bad, "n_ramp_knots": len(ts), "n_vents": len(vents),
        "hrr_end": (t_all[-1], t_end), "t_end": t_end, "kmax": mesh_k(meshes),
    }
    return "\n".join(L) + "\n", info


def mesh_k(meshes):
    return sorted({m[2][2] for m in meshes})


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--smoke", action="store_true", help="T_END=5 s, 8 meshes unless --meshes")
    g.add_argument("--sealed", action="store_true", help="envelope leak test, T_END=1 s")
    g.add_argument("--all", action="store_true", help="the six production decks")
    ap.add_argument("--dx", type=float, default=0.2, choices=(0.2, 0.1))
    ap.add_argument("--yields", default="central", choices=tuple(YIELDS))
    ap.add_argument("--meshes", type=int, default=0, help="multiple of 8; default 32 at 0.2 m, 128 at 0.1 m")
    ap.add_argument("--shift-s", type=float, default=0.0, help="shift the HRR ramp (not the venting) by this many seconds")
    a = ap.parse_args()
    if a.all:
        jobs = [(0.2, "central", 0.0), (0.2, "low", 0.0), (0.2, "high", 0.0), (0.1, "central", 0.0),
                (0.2, "central", -15.0), (0.2, "central", 15.0)]
        jobs = [("prod", *j) for j in jobs]
    else:
        mode = "smoke" if a.smoke else "sealed" if a.sealed else "prod"
        jobs = [(mode, a.dx, a.yields, a.shift_s)]
    for mode, dx, yl, sh in jobs:
        text, info = build(mode, dx, yl, a.meshes, sh)
        out = HERE / info["chid"] / f"{info['chid']}.fds"
        out.parent.mkdir(exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
        print(f"  meshes {info['meshes']} (K per mesh {info['kmax']}), cells {info['cells']}, interface conflicts {info['mesh_conflicts']}")
        print(f"  burner areas m2: " + ", ".join(f"{k.split('_')[0]} {v:.1f}" for k, v in info["areas"].items()))
        print(f"  HRRPUA peak {info['peak_flux']:.0f} kW/m2; HRR check worst deviation {100 * info['worst']:.4f} % over {info['n_ramp_knots']} knots; {info['n_vents']} burner VENTs")
        for k_, v in info["stats"].items():
            print(f"  {k_}: {v}")
        if info["bad_probes"]:
            print("  WARNING zone probes inside solid:", info["bad_probes"])
        for n_, xb in info["dropped_glass"]:
            print(f"  dropped: {n_} {xb}")
        for n_, xb in info["trimmed"]:
            print(f"  trimmed: {n_} {xb}")
        print(f"  T_END {info['t_end']:g} s; ramp ends at {info['hrr_end'][0]:.1f} s")


if __name__ == "__main__":
    main()
