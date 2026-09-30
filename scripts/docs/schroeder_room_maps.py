"""ASET, RSET and DIFF maps of the Schröder et al. (2020) room, our own FDS.

Source of the method: B. Schröder, L. Arnold, A. Seyfried, "A map
representation of the ASET-RSET concept", Fire Safety Journal 115 (2020)
103154, doi:10.1016/j.firesaf.2020.103154 (Sect. 2, Eqs. 2-8). This is the
same experiment rerun with our own FDS 6.10.1 deck and pyFDS-Evac; none of the
authors' data is used. pyFDS-Evac does not build these maps itself (#210):
this script does.

``DATA`` is the ``schroeder2020-room`` folder with the finished FDS runs
``hrr060_1door``, ``hrr060_2door`` (0.2 m) and ``hrr060_1door_dx010``
(0.1 m), their ``config_*.json`` and the per-seed two-door configs in
``hrr060_2door/seeds/`` (``build/make_configs.py``, binomial west/east split
per seed). ``RUNS`` is any folder outside the repository; the evacuation runs
go there and a run whose trajectory already exists is not repeated::

    uv run --with "pedpy>=1.5.1" python scripts/docs/schroeder_room_maps.py \\
        --data DATA --runs RUNS

Steps:

* arm U (``--smoke-blind --disable-tenability --smoke-slice-height 2.0``)
  for seeds 1-10 of every version: the exit capped at 0.96 p/s
  (``enable_throughput_throttling``, ``max_throughput`` on each exit, the
  rate read off the paper's Fig. 3) with pre-movement 0, the default
  (constant 10 s), 30 s and 60 s; uncapped CFSM with pre-movement 0; and,
  two doors only, N = 200 capped with pre-movement 0. The one-door versions
  also run on the 0.1 m FDS output, and the trajectories must be identical;
* ASET per criterion on 0.6 m cells at z = 2.0 m (cell rule: any node of the
  cell, the block maximum; slice steps of about 1 s; clock from ignition;
  cells not exceeded by the 600 s FDS end stay censored, "not by 600 s");
* RSET per cell and seed with PedPy ``compute_rset_map`` (``RsetMethod.MAX``,
  the last time an agent is in the cell, Eqs. 4-5) on PedPy's grid, which the
  ASET map shares; pooled over seeds by the maximum (paper, p. 5, n = 10)
  and by the 95th percentile, plus per-seed measures with bootstrap CIs;
* DIFF = ASET - RSET, five cell states, min DIFF, negative area and C;
* the agents-remaining check against the paper's Fig. 3 points.

It prints every number as Markdown tables and writes the figures to
``site/static/images/studies/schroeder2020/``.
"""

import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import gridspec
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.patches import Polygon as PolygonPatch
from shapely import box, wkt

from pyfds_evac.core.fed import (
    DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
    DEFAULT_HEAT_SKIN_TEMPERATURE_C,
    HEAT_ENDPOINTS,
    ISO_RADIANT_THRESHOLD_KW_M2,
    STEFAN_BOLTZMANN_W_M2_K4,
    DefaultFedConfig,
    DefaultFedInputs,
    DefaultHeatFedModel,
    HeatFedInputs,
    default_fed_rate_per_minute,
    default_heat_fed_rate_per_minute,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "studies" / "schroeder2020"

CELL = 0.6  # m, map cell (paper Sect. 2.2.4)
Z = 2.0  # m, slice height (paper Sect. 2.2.4)
T_END = 600.0  # s, FDS T_END: ASET cells not exceeded by then are censored
PAPER_T_END = 120.0  # s, the paper's fill value for unexceeded cells (p. 4)
PAPER_DT = 10.0  # s, the paper's slice step
BIN = 20.0  # s, bin width of the paper's C (Eq. 8)
FPS = 10.0  # trajectory frames per second, frame 0 = ignition
SEEDS = range(1, 11)
CAP = 0.96  # p/s, read off the paper's Fig. 3 [F]
ROOM = (0.0, 0.0, 30.0, 10.0)
BURNER = (0.6, 0.6, 0.6, 0.6)  # x, y, width, depth
DOOR_REGION = (24.0, 6.0)  # x >= 24 m, y >= 6 m (Enrico's grid note)
PAPER_FIG3 = ((0, 100), (40, 61), (80, 23), (120, 0))  # [F] Fig. 3; N = 100 [P] at 0 s
PAPER_FIG5 = (-29.0, 20.0)  # [F] Fig. 5, 60 kW, N = 100: min DIFF s, area m²

FDS_RUNS = {
    "0.2 m, 1 door": "hrr060_1door",
    "0.1 m, 1 door": "hrr060_1door_dx010",
    "0.2 m, 2 doors": "hrr060_2door",
    "0.2 m, 1 door, perturbed": "hrr060_1door_pert",
}
LAYOUT_FDS = {
    "1door": ("hrr060_1door", "hrr060_1door_dx010"),
    "2door": ("hrr060_2door",),
}
PRE_LABEL = {
    "pre0": "pre-movement 0",
    "pre_default": "pre-movement 10 s (default)",
    "pre30": "pre-movement 30 s",
    "pre60": "pre-movement 60 s",
}


@dataclass(frozen=True)
class Version:
    layout: str  # "1door" or "2door"
    name: str
    capped: bool
    pre: str
    n: int = 100

    @property
    def label(self):
        flow = f"capped {CAP} p/s" if self.capped else "uncapped CFSM"
        n = f"N = {self.n}, " if self.n != 100 else ""
        return f"{n}{flow}, {PRE_LABEL[self.pre]}"


VERSIONS = [
    *(Version(lay, f"capped_{p}", True, p) for lay in LAYOUT_FDS for p in PRE_LABEL),
    *(Version(lay, "uncapped_pre0", False, "pre0") for lay in LAYOUT_FDS),
    Version("2door", "N200_capped_pre0", True, "pre0", 200),
]

# Criterion -> (slice quantity or derived field, threshold, label on figures)
CRITERIA = {
    "K 0.23": ("K", 0.23, "K ≥ 0.23 1/m (paper; location screen)"),
    "K 0.3": ("K", 0.3, "K ≥ 0.3 1/m (EA 10 m, C = 3; location screen)"),
    "T 45": ("T", 45.0, "T ≥ 45 °C (vfdb < 30 min; location screen)"),
    "CO 2700": ("CO", 2700.0, "CO ≥ 2,700 ppm (EA fixed limit)"),
    "FED 0.3": ("FED", 0.3, "gas FED ≥ 0.3 (stationary-occupant dose)"),
    "heat FED 0.3": ("HFED", 0.3, "heat FED ≥ 0.3 (stationary, convective)"),
    "CO 100": ("CO", 100.0, "CO ≥ 100 ppm"),
    "CO 500": ("CO", 500.0, "CO ≥ 500 ppm"),
    "CO2 1": ("CO2", 1.0, "CO₂ ≥ 1 %"),
    "CO2 3": ("CO2", 3.0, "CO₂ ≥ 3 %"),
    "RAD 1.7": ("RAD", 1.7, "radiant flux ≥ 1.7 kW/m²"),
    "RAD 2.5": ("RAD", 2.5, "radiant flux ≥ 2.5 kW/m²"),
    "T 50": ("T", 50.0, "T ≥ 50 °C"),
    "T 100": ("T", 100.0, "T ≥ 100 °C"),
    "K 0.46": ("K", 0.46, "K ≥ 0.46 1/m (D_L 0.2, note 4)"),
}
MAP_CRITERIA = ("K 0.23", "K 0.3", "T 45")
# Whole source sets for the criterion screen: vfdb TB 04-01 (2020) Table 8.3,
# EA practice note (2014) Fig. 8 at 2.0 m, and the pyFDS-Evac doses. HCN is
# listed by vfdb and EA but not tracked here (no fuel nitrogen to HCN).
SOURCE_SETS = {
    "vfdb Table 8.3, < 30 min": ("K 0.23", "T 45", "CO 100", "CO2 1", "RAD 1.7"),
    "vfdb Table 8.3, < 5 min": (
        "K 0.23",
        "K 0.46",
        "T 50",
        "CO 500",
        "CO2 3",
        "RAD 2.5",
    ),
    "EA Fig. 8, 2.0 m, up to 10 min": ("K 0.3", "T 100", "RAD 2.5", "CO 2700"),
    "Doses from ignition (pyFDS-Evac)": (
        "FED 0.3",
        "heat FED 0.3",
        "heat FED 0.3, total flux f = 0.25, tolerance",
        "heat FED 0.3, total flux f = 1, tolerance",
    ),
}
T_AMBIENT_C = 20.0  # FDS default ambient, for the radiant proxy
QUANTITIES = {
    "K": "SOOT EXTINCTION COEFFICIENT",
    "T": "TEMPERATURE",
    "CO": "CARBON MONOXIDE VOLUME FRACTION",
    "CO2": "CARBON DIOXIDE VOLUME FRACTION",
    "O2": "OXYGEN VOLUME FRACTION",
    "U": "INTEGRATED INTENSITY",
}
# Sensitivity only: the total-flux heat dose (SFPE Ch. 63, Eq. 63.43) with the
# radiant term f (U - 4 sigma T_s^4) from INTEGRATED INTENSITY. f = 0.25 is a
# small body in an isotropic field; f = 1, the largest f the engine accepts,
# is an upper bound. Below the ISO 13571 2.5 kW/m² the radiant term is zero.
U_FACTORS = (0.25, 1.0)
HEAT_TF_ENDPOINTS = ("tolerance", "fatal")

TEXT = "dimgrey"
NEVER = "#f3e3b5"  # censored cells: not by 600 s (as on "A crowd in a real fire")
UNVISITED = "#e6e6e6"
FIRE = "#bd0c0c"
EXIT = "#33a02c"
CAPPED = "#4575b4"
UNCAPPED = "#d73027"
N200 = "#72a5b4"
PAPER = "black"


# --- Evacuation runs -----------------------------------------------------


def config_source(data, v, seed):
    """The scenario JSON a version and seed start from."""
    if v.layout == "1door":
        return data / "hrr060_1door" / f"config_{v.pre}.json"
    stem = "N200" if v.n == 200 else v.pre
    return data / "hrr060_2door" / "seeds" / f"config_{stem}_seed{seed:02d}.json"


def run_dir(runs, v, fds, seed):
    return runs / v.layout / v.name / fds / f"seed{seed:02d}"


def write_config(data, v, seed, folder):
    """Write the config actually run, with the exit cap applied, next to it."""
    src = config_source(data, v, seed)
    cfg = json.loads(src.read_text())
    for exit_cfg in cfg["exits"].values():
        exit_cfg["enable_throughput_throttling"] = v.capped
        exit_cfg["max_throughput"] = CAP if v.capped else 0
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (folder / "geometry.wkt").write_text((src.parent / "geometry.wkt").read_text())
    (folder / "source.txt").write_text(f"{src}\n")


def evacuated(log_path):
    """(evacuated, total) from a run log, or None."""
    if not log_path.exists():
        return None
    found = re.findall(r"\((\d+)/(\d+) evacuated\)", log_path.read_text())
    return tuple(int(n) for n in found[-1]) if found else None


def run_one(data, runs, v, fds, seed):
    """Run one arm-U simulation unless its trajectory already exists."""
    folder = run_dir(runs, v, fds, seed)
    sqlite = folder / "traj.sqlite"
    if sqlite.exists() and evacuated(folder / "run.log"):
        return folder
    write_config(data, v, seed, folder)
    cmd = [
        sys.executable,
        str(ROOT / "run.py"),
        "--scenario",
        str(folder / "config.json"),
        "--fds-dir",
        str(data / fds),
        "--smoke-blind",
        "--disable-tenability",
        "--smoke-slice-height",
        str(Z),
        "--seed",
        str(seed),
        "--output-sqlite",
        str(sqlite),
        "--output-exit-history",
        str(folder / "exits.csv"),
    ]
    with open(folder / "run.log", "w") as log:
        subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    return folder


def run_all(data, runs, workers):
    jobs = [
        (v, fds, seed)
        for v in VERSIONS
        for fds in LAYOUT_FDS[v.layout]
        for seed in SEEDS
    ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda j: run_one(data, runs, *j), jobs))
    for v, fds, seed in jobs:
        n = evacuated(run_dir(runs, v, fds, seed) / "run.log")
        assert n and n[0] == n[1] == v.n, f"{v.name} {fds} seed {seed}: {n}"


def trajectory(folder):
    """DataFrame id/frame/x/y of one run."""
    with sqlite3.connect(folder / "traj.sqlite") as con:
        fps = float(
            con.execute("select value from metadata where key = 'fps'").fetchone()[0]
        )
        df = pd.read_sql(
            "select frame, id, pos_x as x, pos_y as y from trajectory_data "
            "order by frame, id",
            con,
        )
    assert fps == FPS, f"{folder}: {fps} fps"
    return df


def check_identity(runs):
    """Arm U sees no smoke: the 0.2 m and 0.1 m trajectories must be equal."""
    fine, coarse = LAYOUT_FDS["1door"][1], LAYOUT_FDS["1door"][0]
    for v in (v for v in VERSIONS if v.layout == "1door"):
        for seed in SEEDS:
            a = trajectory(run_dir(runs, v, coarse, seed))
            b = trajectory(run_dir(runs, v, fine, seed))
            assert a.equals(b), f"{v.name} seed {seed}: trajectories differ by grid"
    return sum(1 for v in VERSIONS if v.layout == "1door") * len(SEEDS)


# --- Grid ----------------------------------------------------------------


@dataclass
class Grid:
    x_edges: np.ndarray
    y_edges: np.ndarray
    area: np.ndarray  # true cell area inside the walkable area, m²
    near_burner: np.ndarray  # cell centre within 2 m of the burner

    @property
    def shape(self):
        return len(self.y_edges) - 1, len(self.x_edges) - 1

    def centre(self, j, i):
        return (
            0.5 * (self.x_edges[i] + self.x_edges[i + 1]),
            0.5 * (self.y_edges[j] + self.y_edges[j + 1]),
        )


def make_grid(walkable):
    """PedPy's edges (same expression as PedPy), row 0 at y = 0.

    PedPy's arange overshoots the room by one column (PedPy#581); that column
    has zero area here and is never visited.
    """
    min_x, min_y, max_x, max_y = walkable.bounds
    xe = np.arange(min_x, max_x + CELL, CELL)
    ye = np.arange(min_y, max_y + CELL, CELL)
    ny, nx = len(ye) - 1, len(xe) - 1
    area = np.zeros((ny, nx))
    near = np.zeros((ny, nx), dtype=bool)
    burner = box(BURNER[0], BURNER[1], BURNER[0] + BURNER[2], BURNER[1] + BURNER[3])
    for j in range(ny):
        for i in range(nx):
            cell = box(xe[i], ye[j], xe[i + 1], ye[j + 1])
            area[j, i] = cell.intersection(walkable).area
            near[j, i] = cell.centroid.distance(burner) <= 2.0
    return Grid(xe, ye, area, near)


def pedpy_rset(df, walkable, grid):
    """PedPy RSET map (last time in the cell), flipped to row 0 at y = 0."""
    import pedpy

    data = pedpy.TrajectoryData(data=df[["id", "frame", "x", "y"]], frame_rate=FPS)
    rset = pedpy.compute_rset_map(
        traj_data=data,
        walkable_area=pedpy.WalkableArea(walkable),
        grid_size=CELL,
        method=pedpy.RsetMethod.MAX,
    )
    assert rset.shape == grid.shape, f"PedPy grid {rset.shape} != {grid.shape}"
    return np.flipud(rset)


def check_orientation(walkable, grid):
    """Assert PedPy's row 0 is max y, so the flip in pedpy_rset is right."""
    probe = pd.DataFrame({"id": [1], "frame": [70], "x": [2.1], "y": [0.1]})
    rset = pedpy_rset(probe, walkable, grid)
    assert rset[0, 3] == 7.0, "PedPy orientation changed"


# --- Fire fields ---------------------------------------------------------


def read_slices(fds_dir):
    """{name: (t, ny, nx) array}, times, x and y of the z = 2.0 m slices."""
    import fdsreader

    logging.disable(logging.WARNING)
    sim = fdsreader.Simulation(str(fds_dir))
    out = {}
    for key, quantity in QUANTITIES.items():
        sl = next(
            s
            for s in sim.slices
            if s.quantity.name == quantity
            and s.orientation == 3
            and abs((s.extent.z_start + s.extent.z_end) / 2 - Z) < 0.06
        )
        data, coords = sl.to_global(return_coordinates=True)
        out[key] = np.transpose(data, (0, 2, 1)).astype(float)
        times, xs, ys = np.asarray(sl.times), coords["x"], coords["y"]
    logging.disable(logging.NOTSET)
    return out, times, xs, ys


def gas_fed_rate(co, co2, o2):
    """FDS+Evac-form FED rate in 1/min (fed.py), vectorised.

    CO ppm = X_CO 1e6; CO2 and O2 in %. No HCN, NOx or irritants tracked.
    """
    co_ppm = np.maximum(co, 0.0) * 1e6
    rate_co = np.where(co_ppm > 0, 2.764e-5 * co_ppm**1.036, 0.0)
    co2_pct = co2 * 100.0
    hv = np.where(co2_pct > 0, np.exp(0.1903 * co2_pct + 2.0004) / 7.1, 1.0)
    o2_pct = o2 * 100.0
    rate_o2 = np.where(o2_pct < 20.0, np.exp(-(8.13 - 0.54 * (20.9 - o2_pct))), 0.0)
    return rate_co * hv + rate_o2


def heat_fed_rate(temp):
    """ISO 13571 Eq. (9) clothed convective rate in 1/min (fed.py), vectorised."""
    return np.where(temp > 0, np.maximum(temp, 0.0) ** 3.61 / 4.1e8, 0.0)


def total_flux_rate(temp, u, endpoint, factor):
    """Total-flux heat FED rate in 1/min (fed.py, U source), vectorised."""
    t_skin = DEFAULT_HEAT_SKIN_TEMPERATURE_C
    u_skin = 4.0 * STEFAN_BOLTZMANN_W_M2_K4 * (t_skin + 273.15) ** 4 / 1000.0
    radiant = factor * (u - u_skin)
    radiant = np.where(radiant < ISO_RADIANT_THRESHOLD_KW_M2, 0.0, radiant)
    q = radiant + DEFAULT_HEAT_CONVECTIVE_COEFFICIENT * (temp - t_skin) / 1000.0
    dose_r = HEAT_ENDPOINTS[endpoint].radiant_dose
    return np.where(q > 0, np.maximum(q, 0.0) ** 1.33 / dose_r, 0.0)


def check_total_flux(fields, n=3000):
    """The vectorised total-flux rate must equal DefaultHeatFedModel's."""
    rng = np.random.default_rng(1)
    flat_t, flat_u = fields["T"].reshape(-1), fields["U"].reshape(-1)
    hot = np.flatnonzero(flat_u >= ISO_RADIANT_THRESHOLD_KW_M2)
    picks = np.concatenate([rng.integers(0, flat_t.size, n), hot[:n]])
    for endpoint, factor in ((e, f) for e in HEAT_TF_ENDPOINTS for f in U_FACTORS):
        model = DefaultHeatFedModel(
            None,
            DefaultFedConfig(),
            endpoint=endpoint,
            method="total-flux",
            radiant_source="integrated-intensity",
            u_factor=factor,
        )
        for idx in picks:
            t, u = float(flat_t[idx]), float(flat_u[idx])
            ref = model._total_flux_rate(
                HeatFedInputs(temperature_celsius=t, integrated_intensity_kw_m2=u)
            )
            assert np.isclose(total_flux_rate(t, u, endpoint, factor), ref, rtol=1e-9)


def check_fed_formulas(fields, n=3000):
    """The vectorised rates must equal fed.py's scalar functions."""
    rng = np.random.default_rng(0)
    flat = {k: fields[k].reshape(-1) for k in ("CO", "CO2", "O2", "T")}
    for idx in rng.integers(0, flat["CO"].size, n):
        co, co2, o2, t = (flat[k][idx] for k in ("CO", "CO2", "O2", "T"))
        gas = DefaultFedInputs(
            co_volume_fraction_percent=100 * co,
            co2_volume_fraction_percent=100 * co2,
            o2_volume_fraction_percent=100 * o2,
        )
        ref = default_fed_rate_per_minute(gas)
        co, co2, o2, t = float(co), float(co2), float(o2), float(t)
        assert np.isclose(gas_fed_rate(co, co2, o2), ref, rtol=1e-9, atol=1e-15)
        ref = default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=t))
        assert np.isclose(heat_fed_rate(t), ref, rtol=1e-9, atol=1e-15)


def radiant_proxy(u):
    """Net radiant flux on a small body, 0.25 (U - 4 sigma T_amb^4), kW/m².

    INTEGRATED INTENSITY U is the integral of the intensity over all
    directions; a small body in an isotropic field receives about U / 4.
    """
    t_amb = T_AMBIENT_C + 273.15
    return 0.25 * (u - 4.0 * STEFAN_BOLTZMANN_W_M2_K4 * t_amb**4 / 1000.0)


def dose(rate, times):
    """Dose accumulated from ignition by someone standing still (left sum)."""
    dt_min = np.diff(times)[:, None, None] / 60.0
    acc = np.cumsum(rate[:-1] * dt_min, axis=0)
    return np.concatenate([np.zeros_like(rate[:1]), acc])


def first_time(over, times):
    """First time each node's criterion holds; inf when never."""
    hit = over.any(axis=0)
    return np.where(hit, times[over.argmax(axis=0)], np.inf)


def paper_steps(times):
    """Indices of the slices nearest 0, 10, 20, ... s (the paper's Δt)."""
    targets = np.arange(0.0, times[-1] + 0.5, PAPER_DT)
    return np.unique(np.abs(times[None, :] - targets[:, None]).argmin(axis=1))


@dataclass
class Fire:
    name: str
    times: np.ndarray
    xs: np.ndarray
    ys: np.ndarray
    node: dict = field(default_factory=dict)  # criterion -> node first times
    screen: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)  # criterion -> (t, ny, nx) bool


def fire_fields(fds_dir, cache):
    """Node first-crossing times per criterion and the screen values, cached."""
    path = cache / f"{fds_dir.name}.npz"
    if path.exists():
        z = np.load(path, allow_pickle=True)
        fire = Fire(fds_dir.name, z["times"], z["xs"], z["ys"])
        fire.node = z["node"].item()
        fire.screen = z["screen"].item()
        shape = tuple(z["raw_shape"])
        fire.raw["K 0.23"] = np.unpackbits(z["raw_k"])[: np.prod(shape)].reshape(shape)
        fire.raw["K 0.23"] = fire.raw["K 0.23"].astype(bool)
        missing = set(CRITERIA) - set(fire.node)
        assert not missing, f"stale cache {path}: {missing}; delete it"
        return fire
    f, times, xs, ys = read_slices(fds_dir)
    check_fed_formulas(f)
    check_total_flux(f)
    derived = {
        "K": f["K"],
        "T": f["T"],
        "CO": f["CO"] * 1e6,
        "FED": dose(gas_fed_rate(f["CO"], f["CO2"], f["O2"]), times),
        "HFED": dose(heat_fed_rate(f["T"]), times),
        "CO2": f["CO2"] * 100.0,
        "RAD": radiant_proxy(f["U"]),
    }
    fire = Fire(fds_dir.name, times, xs, ys)
    for name, (key, limit, _) in CRITERIA.items():
        fire.node[name] = first_time(derived[key] >= limit, times)
    for endpoint in HEAT_TF_ENDPOINTS:
        for factor in U_FACTORS:
            tf = dose(total_flux_rate(f["T"], f["U"], endpoint, factor), times)
            tag = f"total flux f = {factor:g}, {endpoint}"
            fire.node[f"heat FED 0.3, {tag}"] = first_time(tf >= 0.3, times)
            fire.screen[f"heat FED max, {tag}"] = float(tf[-1].max())
    # The ∀ rule needs the raw exceedance, not the node first times.
    fire.raw["K 0.23"] = f["K"] >= CRITERIA["K 0.23"][1]
    steps = paper_steps(times)
    for name in ("K 0.23", "T 45"):
        key, limit, _ = CRITERIA[name]
        fire.node[f"{name} @10 s"] = first_time(
            derived[key][steps] >= limit, times[steps]
        )
    fire.screen |= {
        "K max 1/m": float(f["K"].max()),
        "T max °C": float(f["T"].max()),
        "CO max ppm": float(derived["CO"].max()),
        "CO2 max %": float(100 * f["CO2"].max()),
        "O2 min %": float(100 * f["O2"].min()),
        "U max kW/m²": float(f["U"].max()),
        "radiant proxy max kW/m²": float(derived["RAD"].max()),
        "gas FED max": float(derived["FED"][-1].max()),
        "heat FED max": float(derived["HFED"][-1].max()),
        "T ≥ 45 °C node share": float((fire.node["T 45"] < np.inf).mean()),
        "U ≥ 2.5 kW/m² node share": float(
            (f["U"] >= ISO_RADIANT_THRESHOLD_KW_M2).any(axis=0).mean()
        ),
        "U ≥ 2.5 kW/m² farthest node from origin, m": _farthest_hot(f["U"], xs, ys),
        "t_last": float(times[-1]),
    }
    cache.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        times=times,
        xs=xs,
        ys=ys,
        node=np.array(fire.node, dtype=object),
        screen=np.array(fire.screen, dtype=object),
        raw_k=np.packbits(fire.raw["K 0.23"]),
        raw_shape=np.array(fire.raw["K 0.23"].shape),
    )
    return fire


def _farthest_hot(u, xs, ys):
    hot = (u >= ISO_RADIANT_THRESHOLD_KW_M2).any(axis=0)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    return float(np.hypot(gx[hot], gy[hot]).max()) if hot.any() else 0.0


def members(coords, edges, n_cells):
    """Node indices per cell; a node on a cell edge belongs to both cells.

    fdsreader coordinates are float32 (29.800001), so the edge tolerance is
    1 mm, well below the 0.1 m node spacing. Every cell inside the room must
    hold CELL / dx + 1 nodes per axis (asserted).
    """
    eps = 1e-3
    out = [
        np.flatnonzero((coords >= edges[i] - eps) & (coords <= edges[i + 1] + eps))
        for i in range(n_cells)
    ]
    full = round(CELL / float(np.diff(coords).mean())) + 1
    inside = [c for i, c in enumerate(out) if edges[i + 1] <= coords.max() + eps]
    assert all(c.size == full for c in inside), "a map cell lost an edge node"
    return out


def nearest_index(coords, n_room, n_cells):
    """One node per cell: the nearest-sample (resize) index."""
    idx = np.floor((np.arange(n_cells) + 0.5) * len(coords) / n_room).astype(int)
    return np.minimum(idx, len(coords) - 1)


def cell_aset(node_first, fire, grid, rule="exists"):
    """ASET per map cell (row 0 at y = 0); inf = not by the end; NaN = no floor."""
    ny, nx = grid.shape
    if rule == "nearest":
        n_room_x = round((ROOM[2] - ROOM[0]) / CELL)
        n_room_y = int(np.ceil((ROOM[3] - ROOM[1]) / CELL - 1e-9))
        ix = nearest_index(fire.xs, n_room_x, nx)
        iy = nearest_index(fire.ys, n_room_y, ny)
        out = node_first[np.ix_(iy, ix)].astype(float)
    else:
        cols = members(fire.xs, grid.x_edges, nx)
        rows = members(fire.ys, grid.y_edges, ny)
        out = np.full((ny, nx), np.nan)
        for j, r in enumerate(rows):
            out[j] = [
                node_first[np.ix_(r, c)].min() if c.size else np.nan for c in cols
            ]
    return np.where(grid.area > 0, out, np.nan)


def cell_aset_forall(over, fire, grid):
    """ASET per map cell under Eq. 2 as printed: every node of the cell at once."""
    ny, nx = grid.shape
    cols = members(fire.xs, grid.x_edges, nx)
    rows = members(fire.ys, grid.y_edges, ny)
    out = np.full((ny, nx), np.nan)
    for j, r in enumerate(rows):
        for i, c in enumerate(cols):
            if not c.size:
                continue
            every = over[:, r][:, :, c].all(axis=(1, 2))
            out[j, i] = fire.times[every.argmax()] if every.any() else np.inf
    return np.where(grid.area > 0, out, np.nan)


def combined(fire, names, suffix=""):
    return np.minimum.reduce([fire.node[n + suffix] for n in names])


# --- RSET, DIFF and measures ---------------------------------------------


def pool(maps, how):
    """Pool seeds per cell over the seeds that visit it; NaN if none does."""
    stack = np.dstack(maps)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells
        if how == "max":
            return np.nanmax(stack, axis=2)
        return np.nanpercentile(stack, 95, axis=2)


def measures(aset, rset, grid):
    """min DIFF, negative area, C and the five states on visited cells.

    Every run empties the room before T_END (asserted in run_all), so no
    RSET is censored and the "<= bound" and "undetermined" states are empty.
    """
    visited = np.isfinite(rset) & (grid.area > 0)
    exact = visited & np.isfinite(aset)
    diff = np.where(exact, aset - rset, np.nan)
    fail = exact & (diff < 0)
    j, i = np.unravel_index(np.nanargmin(diff), diff.shape)
    far = np.where(grid.near_burner, np.nan, diff)
    neg = diff[fail]
    centres = (np.floor(neg / BIN) + 0.5) * BIN
    return {
        "min": float(np.nanmin(diff)),
        "min_at": grid.centre(j, i),
        "min_far": float(np.nanmin(far)),
        "area": float(grid.area[fail].sum()),
        "c_free": float((neg * grid.area[fail]).sum()),
        "c_binned": float((centres * grid.area[fail]).sum()),
        "pass": int((exact & (diff >= 0)).sum()),
        "fail": int(fail.sum()),
        ">= bound": int((visited & np.isinf(aset)).sum()),
        "<= bound": 0,
        "undetermined": 0,
        "diff": diff,
        "censored": visited & np.isinf(aset),
    }


def bootstrap(values, n=4000):
    """Mean and 95 % bootstrap CI of per-seed values."""
    rng = np.random.default_rng(0)
    values = np.asarray(values, dtype=float)
    means = rng.choice(values, (n, values.size)).mean(axis=1)
    return values.mean(), *np.percentile(means, [2.5, 97.5])


@dataclass
class Result:
    version: Version
    rset_seeds: list
    rset_max: np.ndarray
    rset_p95: np.ndarray
    remaining: pd.DataFrame  # time x seed


def remaining_curve(df, n):
    """Agents in the room at every whole second, 0 once the room is empty."""
    counts = df.groupby("frame").id.nunique()
    t = np.arange(0, 301)
    frames = (t * FPS).astype(int)
    out = counts.reindex(frames).fillna(0).to_numpy()
    assert out[0] == n, f"{out[0]} agents at t = 0, expected {n}"
    return out


def rset_results(runs, walkable, grid):
    results = {}
    for v in VERSIONS:
        fds = LAYOUT_FDS[v.layout][0]
        maps, curves = [], {}
        for seed in SEEDS:
            df = trajectory(run_dir(runs, v, fds, seed))
            maps.append(pedpy_rset(df, walkable[v.layout], grid))
            curves[seed] = remaining_curve(df, v.n)
        results[(v.layout, v.name)] = Result(
            v,
            maps,
            pool(maps, "max"),
            pool(maps, "p95"),
            pd.DataFrame(curves),
        )
    return results


# --- Report --------------------------------------------------------------


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    print("\n".join(lines) + "\n")


def fmt_time(t):
    return "not by 600 s" if not np.isfinite(t) else f"{t:.0f} s"


def report_split(data):
    rows = []
    for seed in SEEDS:
        row = [seed]
        for stem in ("pre0", "N200"):
            path = (
                data / "hrr060_2door" / "seeds" / f"config_{stem}_seed{seed:02d}.json"
            )
            dists = json.loads(path.read_text())["distributions"]
            row += [f"{d['parameters']['number']}" for d in dists.values()]
        rows.append(row)
    print("## E1: two-door spawn counts per seed (west / east)\n")
    md_table(["seed", "N=100 west", "N=100 east", "N=200 west", "N=200 east"], rows)


FIGURE_NUMBERS = []  # (figure, item, value): every number a figure shows


def _note(figure, item, value):
    FIGURE_NUMBERS.append((figure, item, value))


def grid_for(fire_name, grids):
    return grids["2door"] if "2 doors" in fire_name else grids["1door"]


SCREEN_LABELS = {c: spec[2] for c, spec in CRITERIA.items()} | {
    f"heat FED 0.3, total flux f = {f:g}, {e}": f"heat FED ≥ 0.3, total flux, f = {f:g}, "
    f"{e} dose (SFPE Eq. 63.43; sensitivity)"
    for e in HEAT_TF_ENDPOINTS
    for f in U_FACTORS
}
SCREEN_RUNS = ("0.2 m, 1 door", "0.1 m, 1 door", "0.2 m, 2 doors")


def burner_distance(grid, mask):
    """Largest distance of a masked cell centre from the burner, m."""
    x0, y0, w, d = BURNER
    jj, ii = np.nonzero(mask)
    cx = 0.5 * (grid.x_edges[ii] + grid.x_edges[ii + 1])
    cy = 0.5 * (grid.y_edges[jj] + grid.y_edges[jj + 1])
    dx = np.clip(cx, x0, x0 + w) - cx
    dy = np.clip(cy, y0, y0 + d) - cy
    return float(np.hypot(dx, dy).max())


def screen_cell(fire, crit, grid):
    """(cells exceeded, cells on the floor, first, median, farthest from burner)."""
    aset = cell_aset(fire.node[crit], fire, grid)
    hit = np.isfinite(aset)
    n_floor = int((grid.area > 0).sum())
    if not hit.any():
        return 0, n_floor, np.inf, np.inf, np.nan
    return (
        int(hit.sum()),
        n_floor,
        float(aset[hit].min()),
        float(np.median(aset[hit])),
        burner_distance(grid, hit),
    )


def report_screen(fires, grids):
    print("## Fire quantities at z = 2.0 m, 0-600 s\n")
    names = [n for n in FDS_RUNS if n in fires]
    keys = list(next(iter(fires.values())).screen)
    rows = [[k] + [f"{fires[n].screen[k]:.3g}" for n in names] for k in keys]
    md_table(["quantity"] + names, rows)
    print(
        "## Criterion screen by source set: map cells exceeded by 600 s (∃ rule), "
        "first / median time, farthest cell centre from the burner\n"
    )
    runs = [n for n in SCREEN_RUNS if n in fires]
    rows = []
    for source, crits in SOURCE_SETS.items():
        for crit in crits:
            row = [source, SCREEN_LABELS[crit]]
            for n in runs:
                hit, total, first, med, dist = screen_cell(
                    fires[n], crit, grid_for(n, grids)
                )
                row.append(
                    f"{hit}/{total}, {fmt_time(first)} / {fmt_time(med)}, ≤ {dist:.1f} m"
                    if hit
                    else f"0/{total}, not by 600 s"
                )
            rows.append(row)
        if source.startswith(("vfdb", "EA")):
            rows.append([source, "HCN"] + ["not applicable: not tracked"] * len(runs))
    md_table(["source set", "criterion"] + runs, rows)
    t_skin = DEFAULT_HEAT_SKIN_TEMPERATURE_C + 273.15
    u_skin = 4.0 * STEFAN_BOLTZMANN_W_M2_K4 * t_skin**4 / 1000.0
    for n in names:
        u = fires[n].screen["U max kW/m²"]
        for f in U_FACTORS:
            q = f * (u - u_skin)
            print(
                f"- {n}: max f·(U − 4σT_skin⁴) at f = {f:g} is {q:.2f} kW/m²; "
                f"ISO 13571 counts it from {ISO_RADIANT_THRESHOLD_KW_M2} kW/m²: "
                f"{'reached' if q >= ISO_RADIANT_THRESHOLD_KW_M2 else 'not reached'}"
            )
    print()


def report_first_criterion(fires, grids):
    print("## Which criterion is first (cells exceeded, ∃ rule)\n")
    rows = []
    for n, fire in fires.items():
        grid = grid_for(n, grids)
        k = cell_aset(fire.node["K 0.23"], fire, grid)
        t = cell_aset(fire.node["T 45"], fire, grid)
        both = np.isfinite(k) | np.isfinite(t)
        rows.append(
            [
                n,
                int((both & (k < t)).sum()),
                int((both & (k == t)).sum()),
                int((both & (t < k)).sum()),
            ]
        )
    md_table(["run", "K 0.23 first", "tie", "T 45 first"], rows)


def report_queue(results):
    """Cells occupied at or after 60, 75 and 90 s: the footprint of the queue."""
    print("## Queue footprint, one door, capped, pre-movement 0 (n = 10)\n")
    r = results[("1door", "capped_pre0")]
    rows = [
        [how] + [int(np.sum(np.nan_to_num(m, nan=-1.0) >= t)) for t in (60, 75, 90)]
        for how, m in (("maximum", r.rset_max), ("95th percentile", r.rset_p95))
    ]
    md_table(["pooling", "cells RSET >= 60 s", ">= 75 s", ">= 90 s"], rows)


def report_gate(results):
    print("## Agents remaining (pre-movement 0, 10 seeds, mean ± sd)\n")
    rows = []
    for key in [k for k, r in results.items() if r.version.pre == "pre0"]:
        rem = results[key].remaining
        last = [np.flatnonzero(rem[s].to_numpy() > 0).max() + 1 for s in rem]
        rows.append(
            [
                f"{key[0]} {v_label(key)}",
                f"{rem.loc[40].mean():.1f} ± {rem.loc[40].std():.1f}",
                f"{rem.loc[80].mean():.1f} ± {rem.loc[80].std():.1f}",
                f"{min(last)}-{max(last)} s",
            ]
        )
    md_table(["version", "remaining at 40 s", "at 80 s", "last out (whole s)"], rows)
    rem = results[("1door", "capped_pre0")].remaining
    ok = (
        abs(rem.loc[40].mean() - 61) <= 5
        and abs(rem.loc[80].mean() - 23) <= 5
        and 100 <= np.median([np.flatnonzero(rem[s] > 0).max() + 1 for s in rem]) <= 110
    )
    print(
        f"Gate (b), 61 ± 5 / 23 ± 5 / last out 100-110 s: {'PASS' if ok else 'FAIL'}\n"
    )
    print("## RSET map, latest cell per version (n = 10)\n")
    rows = [
        [
            f"{k[0]} {v_label(k)}",
            f"{np.nanmax(r.rset_max):.1f}",
            f"{np.nanmax(r.rset_p95):.1f}",
            int(np.isfinite(r.rset_max).sum()),
        ]
        for k, r in results.items()
    ]
    md_table(["version", "max pooling s", "p95 pooling s", "visited cells"], rows)
    return ok


def measure_row(label, m):
    x, y = m["min_at"]
    return [
        label,
        f"{m['min']:.0f} at ({x:.1f}, {y:.1f})",
        f"{m['min_far']:.0f}",
        f"{m['area']:.1f}",
        f"{m['c_free']:.0f}",
        f"{m['c_binned']:.0f}",
        f"{m['pass']}/{m['fail']}/{m['>= bound']}",
    ]


MEASURE_HEADER = [
    "version",
    "min DIFF s (cell centre)",
    "min DIFF > 2 m from burner",
    "area DIFF<0 m²",
    "C m²s",
    "C 20 s bins",
    "pass/fail/≥ bound",
]


# --- Figures -------------------------------------------------------------


def _style(ax):
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    ax.set_xticks([])
    ax.set_yticks([])
    sns.despine(ax=ax, left=True, bottom=True)


def _legend(target, **kwargs):
    return target.legend(
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        **kwargs,
    )


def _save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {(OUT / name).relative_to(ROOT)}")


def _plan(ax, walkable, exits):
    for ring in [walkable.exterior, *walkable.interiors]:
        ax.add_patch(
            PolygonPatch(np.asarray(ring.coords), fc="none", ec=TEXT, lw=0.9, zorder=4)
        )
    for xy in exits:
        ax.add_patch(PolygonPatch(np.asarray(xy), fc=EXIT, ec="none", zorder=5))
    ax.add_patch(Rectangle(BURNER[:2], *BURNER[2:], fc=FIRE, ec=FIRE, zorder=5))
    ax.set_aspect("equal")
    ax.set_xlim(-0.3, 30.3)
    ax.set_ylim(-0.3, 10.3)
    _style(ax)


def _mesh(ax, grid, values, **kwargs):
    xe = np.minimum(grid.x_edges, ROOM[2])
    ye = np.minimum(grid.y_edges, ROOM[3])
    return ax.pcolormesh(xe, ye, values, shading="flat", **kwargs)


def _hatch(ax, grid, mask, hatch):
    xe = np.minimum(grid.x_edges, ROOM[2])
    ye = np.minimum(grid.y_edges, ROOM[3])
    for j, i in zip(*np.nonzero(mask)):
        ax.add_patch(
            Rectangle(
                (xe[i], ye[j]),
                xe[i + 1] - xe[i],
                ye[j + 1] - ye[j],
                fc="none",
                ec="black",
                lw=0,
                hatch=hatch,
                alpha=0.6,
                zorder=3,
            )
        )


def _title(ax, letter, text):
    ax.set_title(
        r"$\bf{(" + letter + r")}$" + f" {text}",
        loc="left",
        fontsize=10,
        color=TEXT,
        pad=5,
    )


def _stamp(fig, text):
    if fig.get_layout_engine() is not None:
        fig.supxlabel(text, x=0.01, ha="left", fontsize=8, color=TEXT)
        return
    fig.text(0.01, 0.005, text, fontsize=8, color=TEXT, ha="left", va="bottom")


def _aset_cmap():
    bounds = [0, 10, 20, 30, 40, 50, 60, 80, 100, 150, 600, 601]
    colours = sns.cubehelix_palette(len(bounds) - 2, rot=-0.25, light=0.92, dark=0.15)
    return (
        ListedColormap(list(colours[::-1]) + [NEVER]),
        BoundaryNorm(bounds, len(bounds) - 1),
        bounds,
    )


def _aset_colorbar(fig, im, axes, bounds):
    cb = fig.colorbar(im, ax=axes, location="bottom", shrink=0.7, aspect=60)
    cb.set_ticks(
        [*bounds[:-2], 600.5], labels=[str(b) for b in bounds[:-2]] + ["not by 600"]
    )
    cb.set_label("ASET, first time the criterion holds [s after ignition]", color=TEXT)
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)


def _panel_grid(n_rows, figsize):
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(n_rows, 2, figsize=figsize, layout="constrained")
    fig.get_layout_engine().set(w_pad=0.03, h_pad=0.03, wspace=0.03, hspace=0.04)
    return fig, list(axes.flat)


def _suptitle(fig, text):
    fig.suptitle(text, x=0.01, ha="left", fontsize=12, color=TEXT)


def fig_aset_criteria(fire, grid, walkable, exits, name, title):
    """ASET per criterion (a-c) and which criterion comes first (d)."""
    cmap, norm, bounds = _aset_cmap()
    fig, axes = _panel_grid(2, (13, 6.8))
    im = None
    for ax, letter, crit in zip(axes, "abc", MAP_CRITERIA):
        aset = cell_aset(fire.node[crit], fire, grid)
        im = _mesh(
            ax, grid, np.where(np.isinf(aset), 600.5, aset), cmap=cmap, norm=norm
        )
        _hatch(ax, grid, np.isinf(aset), "..")
        _plan(ax, walkable, exits)
        shown = aset[np.isfinite(aset)]
        note = (
            f"median {np.median(shown):.0f} s, latest {shown.max():.0f} s"
            if shown.size > 10
            else f"{shown.size} cells, all at the plume"
        )
        _title(ax, letter, f"{CRITERIA[crit][2]}; {note}")
        if crit.startswith("T "):
            ax.text(
                15,
                5.2,
                "vfdb Table 8.3, note (2): gas temperature is not to be assessed\n"
                "in isolation from smoke density. 45 °C is the < 30 min column;\n"
                "for < 5 min, vfdb gives 50 °C.",
                ha="center",
                va="center",
                fontsize=8.5,
                color=TEXT,
                zorder=6,
                bbox={"fc": "white", "ec": "lightgrey", "alpha": 0.9},
            )
        _note(
            name,
            crit,
            f"median {np.median(shown):.0f} s, 90th pct {np.percentile(shown, 90):.0f} s,"
            f" latest {shown.max():.0f} s, {shown.size} cells exceeded",
        )
    k = cell_aset(fire.node["K 0.23"], fire, grid)
    t = cell_aset(fire.node["T 45"], fire, grid)
    cats = np.full(k.shape, np.nan)
    cats[k < t] = 0
    cats[(k == t) & np.isfinite(k)] = 1
    cats[np.isinf(k) & np.isinf(t)] = 2
    cat_cmap = ListedColormap(["#c6dbef", FIRE, NEVER])
    _mesh(axes[3], grid, cats, cmap=cat_cmap, vmin=-0.5, vmax=2.5)
    _hatch(axes[3], grid, cats == 1, "xxx")
    _plan(axes[3], walkable, exits)
    n_tie, n_t = int((cats == 1).sum()), int((t < k).sum())
    _title(
        axes[3],
        "d",
        f"first criterion: K first, T first in {n_t} cells, tie in {n_tie}",
    )
    _note(name, "T 45 first / tie with K 0.23", f"{n_t} / {n_tie} cells")
    _legend(
        axes[3],
        handles=[
            Patch(fc="#c6dbef", label="K ≥ 0.23 first"),
            Patch(fc=FIRE, hatch="xxx", label="tie with T ≥ 45 °C"),
            Patch(fc=NEVER, label="neither by 600 s"),
        ],
        loc="lower right",
        fontsize=8,
    )
    _aset_colorbar(fig, im, axes, bounds)
    _suptitle(fig, title)
    _stamp(
        fig,
        "∃ rule (any FDS node of the 0.6 m cell), z = 2.0 m, slices every ~1 s, "
        "clock from ignition; dotted: not by 600 s (censored, not filled). "
        "T ≥ 45 °C only at the plume: not grid-converged. Burner red, exit green.",
    )
    _save(fig, name)


def fig_screen(fires, grids):
    """Map cells exceeded by 600 s per criterion, grouped by source set."""
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    runs = [n for n in SCREEN_RUNS if n in fires]
    marks = dict(zip(runs, (("o", CAPPED), ("D", UNCAPPED), ("s", N200))))
    offsets = dict(zip(runs, (-0.22, 0.0, 0.22)))
    labels, y, ticks, groups = [], 0, [], []
    fig, ax = plt.subplots(figsize=(10, 7.4), layout="constrained")
    for source, crits in SOURCE_SETS.items():
        groups.append((y - 0.6, source))
        for crit in crits:
            for n in runs:
                hit, *_ = screen_cell(fires[n], crit, grid_for(n, grids))
                marker, colour = marks[n]
                ax.scatter(
                    hit,
                    y + offsets[n],
                    marker=marker,
                    s=36,
                    fc=colour if hit else "white",
                    ec=colour,
                    lw=1.3,
                    zorder=3,
                )
                _note("criteria_screen.png", f"{crit}, {n}", f"{hit} cells")
            label = SCREEN_LABELS[crit]
            labels.append(
                label.split(" (SFPE")[0].replace(" (stationary-occupant dose)", "")
            )
            ticks.append(y)
            y += 1
        y += 0.9
    for y0, source in groups:
        ax.text(
            -0.5,
            y0,
            source,
            fontsize=9.5,
            fontweight="bold",
            color=TEXT,
            va="center",
            ha="left",
            transform=ax.get_yaxis_transform(),
        )
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlim(-0.3, 1500)
    ax.set_xticks([0, 1, 10, 100, 848], labels=["0", "1", "10", "100", "848 (all)"])
    ax.set_yticks(ticks, labels=labels)
    ax.set_ylim(y - 0.5, -1.2)
    ax.set_xlabel("map cells exceeded by 600 s at z = 2.0 m (∃ rule, 0.6 m cells)")
    ax.tick_params(length=0, labelcolor=TEXT)
    ax.xaxis.label.set_color(TEXT)
    ax.grid(axis="y", visible=False)
    sns.despine(ax=ax, left=True)
    _legend(
        ax,
        handles=[
            Line2D([], [], marker=m, ls="", mfc=c, mec=c, label=n)
            for n, (m, c) in marks.items()
        ]
        + [
            Line2D(
                [], [], marker="o", ls="", mfc="white", mec="grey", label="open: none"
            )
        ],
        loc="lower right",
        fontsize=8.5,
    )
    _suptitle(
        fig, "Which fire quantities are exceeded at 2.0 m by 600 s, per source set"
    )
    _stamp(
        fig,
        "Radiant flux: 0.25·(U − 4σT_amb⁴) from INTEGRATED INTENSITY, T_amb = 20 °C [A]. "
        "HCN not tracked: not applicable. Not reached by 600 s is a result for this "
        "fire, not a pass.",
    )
    _save(fig, "criteria_screen.png")


def fig_grid_pair(coarse, fine, grid, walkable, exits):
    """K ≥ 0.23 on the 0.2 m and 0.1 m FDS grids, their difference and scatter."""
    cmap, norm, bounds = _aset_cmap()
    a = cell_aset(coarse.node["K 0.23"], coarse, grid)
    b = cell_aset(fine.node["K 0.23"], fine, grid)
    fig, axes = _panel_grid(2, (13, 6.6))
    for ax, letter, aset, label in (
        (axes[0], "a", a, "0.2 m"),
        (axes[1], "b", b, "0.1 m"),
    ):
        im = _mesh(
            ax, grid, np.where(np.isinf(aset), 600.5, aset), cmap=cmap, norm=norm
        )
        _hatch(ax, grid, np.isinf(aset), "..")
        _plan(ax, walkable, exits)
        shown = aset[np.isfinite(aset)]
        _note(
            "aset_grid_pair.png",
            f"K 0.23, FDS grid {label}",
            f"median {np.median(shown):.0f} s, 90th pct "
            f"{np.percentile(shown, 90):.0f} s, latest {shown.max():.0f} s",
        )
        _title(
            ax,
            letter,
            f"FDS grid {label}: median {np.median(shown):.0f} s, "
            f"90th pct {np.percentile(shown, 90):.0f} s, latest {shown.max():.0f} s",
        )
    d = b - a
    lim = 60
    im_d = _mesh(axes[2], grid, np.clip(d, -lim, lim), cmap="RdBu", vmin=-lim, vmax=lim)
    _hatch(axes[2], grid, np.abs(d) > 30, "///")
    _plan(axes[2], walkable, exits)
    big = np.nanmean(np.abs(d[np.isfinite(d)]) > 30)
    _title(axes[2], "c", f"0.1 m minus 0.2 m; hatched: |Δ| > 30 s ({big:.0%} of cells)")
    _note("aset_grid_pair.png", "cells with |Δ| > 30 s", f"{big:.1%}")
    _note(
        "aset_grid_pair.png",
        "all cells, |Δ|",
        f"mean {np.nanmean(np.abs(d)):.1f} s, max {np.nanmax(np.abs(d)):.0f} s",
    )
    cb = fig.colorbar(im_d, ax=axes[2], location="left", shrink=0.8, aspect=15)
    cb.set_label("Δ ASET [s]", color=TEXT)
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)
    ax = axes[3]
    xc = 0.5 * (grid.x_edges[:-1] + grid.x_edges[1:])
    yc = 0.5 * (grid.y_edges[:-1] + grid.y_edges[1:])
    door = (xc[None, :] >= DOOR_REGION[0]) & (yc[:, None] >= DOOR_REGION[1])
    ok = np.isfinite(a) & np.isfinite(b)
    ax.scatter(
        a[ok & ~door], b[ok & ~door], s=10, c="grey", alpha=0.4, lw=0, label="room"
    )
    ax.scatter(
        a[ok & door],
        b[ok & door],
        s=22,
        marker="D",
        c=CAPPED,
        lw=0,
        label="door region (x ≥ 24 m, y ≥ 6 m)",
    )
    top = max(np.nanmax(a[ok]), np.nanmax(b[ok])) + 10
    ax.plot([0, top], [0, top], color="lightgrey", lw=1, zorder=0)
    ax.set_xlim(0, np.nanmax(a[ok]) + 10)
    ax.set_ylim(0, top)
    ax.set_xlabel("ASET, 0.2 m grid [s]", color=TEXT, fontsize=9)
    ax.set_ylabel("ASET, 0.1 m grid [s]", color=TEXT, fontsize=9)
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT, labelsize=8)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)
    sns.despine(ax=ax, left=True, bottom=True)
    dd = np.abs(d[ok & door])
    _note(
        "aset_grid_pair.png",
        "door region |Δ| (x ≥ 24 m, y ≥ 6 m)",
        f"max {dd.max():.0f} s, 95th pct {np.percentile(dd, 95):.0f} s, {dd.size} cells",
    )
    _title(
        ax,
        "d",
        f"door region: |Δ| ≤ {dd.max():.0f} s, 95th pct {np.percentile(dd, 95):.0f} s",
    )
    _legend(ax, loc="upper left", fontsize=8)
    _aset_colorbar(fig, im, axes[:2], bounds)
    _suptitle(
        fig,
        "K ≥ 0.23 1/m at 2.0 m, one door: not shown grid-converged; "
        "the 2.0 m criterion sits in the layer interface",
    )
    _stamp(
        fig, "∃ rule, 0.6 m cells, z = 2.0 m, slices every ~1 s; dotted: not by 600 s."
    )
    _save(fig, "aset_grid_pair.png")


def fig_rset(results, grids, walkable, exits):
    keys = [
        ("1door", "capped_pre0"),
        ("1door", "uncapped_pre0"),
        ("2door", "capped_pre0"),
        ("2door", "N200_capped_pre0"),
    ]
    vmax = 10 * np.ceil(max(np.nanmax(results[k].rset_max) for k in keys) / 10)
    fig, axes = _panel_grid(2, (13, 6.8))
    cmap = sns.color_palette("Blues", as_cmap=True)
    im = None
    for ax, letter, key in zip(axes, "abcd", keys):
        r = results[key]
        grid = grids[key[0]]
        shown = np.where(np.isfinite(r.rset_max), np.nan, 0.0)
        _mesh(
            ax,
            grid,
            np.where(grid.area > 0, shown, np.nan),
            cmap=ListedColormap([UNVISITED]),
        )
        im = _mesh(ax, grid, r.rset_max, cmap=cmap, vmin=0, vmax=vmax)
        _plan(ax, walkable[key[0]], exits[key[0]])
        doors = "1 door" if key[0] == "1door" else "2 doors"
        _title(
            ax,
            letter,
            f"{doors}, {r.version.label}: latest {np.nanmax(r.rset_max):.0f} s",
        )
    cb = fig.colorbar(im, ax=axes, location="bottom", shrink=0.7, aspect=60)
    cb.set_label(
        "RSET, last time any agent is in the cell [s after ignition]", color=TEXT
    )
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)
    _suptitle(
        fig,
        "RSET maps, arm U (smoke-blind): the capped exit sets the time the last "
        "person leaves the door corner",
    )
    _stamp(
        fig,
        "PedPy compute_rset_map (RsetMethod.MAX), 0.6 m cells, 10 fps, frame 0 = ignition; "
        "maximum over n = 10 seeds (paper p. 5). Grey: not visited. Burner red, exit green.",
    )
    _save(fig, "rset_maps.png")


def _diff_panel(ax, m, grid, walkable, exits):
    lim = 60
    diff = m["diff"]
    unvisited = np.isnan(diff) & ~m["censored"] & (grid.area > 0)
    _mesh(ax, grid, np.where(unvisited, 0.0, np.nan), cmap=ListedColormap([UNVISITED]))
    im = _mesh(ax, grid, np.clip(diff, -lim, lim), cmap="RdBu", vmin=-lim, vmax=lim)
    _mesh(ax, grid, np.where(m["censored"], 0.0, np.nan), cmap=ListedColormap([NEVER]))
    _hatch(ax, grid, m["censored"], "..")
    _hatch(ax, grid, diff < 0, "////")
    _plan(ax, walkable, exits)
    return im


def fig_diff(panels, grid, walkable, exits, name, title):
    fig, axes = _panel_grid(3, (13, 9.6))
    im = None
    for ax, letter, (label, m) in zip(axes, "abcdef", panels):
        im = _diff_panel(ax, m, grid, walkable, exits)
        _title(
            ax,
            letter,
            f"{label}\nmin DIFF {m['min']:.0f} s, area DIFF < 0 {m['area']:.1f} m², "
            f"C {m['c_free']:.0f} m²s",
        )
    cb = fig.colorbar(
        im, ax=axes, location="bottom", shrink=0.6, aspect=60, extend="both"
    )
    cb.set_label("DIFF = ASET − RSET [s]; hatched: DIFF < 0", color=TEXT)
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)
    _legend(
        fig,
        handles=[
            Patch(fc="#b2182b", hatch="////", label="DIFF < 0 (fail)"),
            Patch(fc="#2166ac", label="DIFF ≥ 0 (pass)"),
            Patch(fc=UNVISITED, label="not visited"),
        ],
        loc="outside upper right",
        fontsize=8,
        ncols=3,
    )
    _suptitle(fig, title)
    _stamp(
        fig,
        "ASET: K ≥ 0.23 1/m, ∃ rule, z = 2.0 m, ~1 s slices. RSET: maximum over n = 10 "
        "seeds, arm U. No visited cell is censored (ASET all by 600 s). C = Σ DIFF·A over DIFF < 0 (no direct physical interpretation yet, paper p. 7).",
    )
    _save(fig, name)


def fig_measures(rows):
    """min DIFF and negative area per version, maximum pooling (n = 10)."""
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(12, 6.2))
    gs = gridspec.GridSpec(1, 2, figure=fig)
    gs.update(wspace=0.06, left=0.3, right=0.99, top=0.9, bottom=0.15)
    ax_min, ax_area = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    y = np.arange(len(rows))[::-1]
    for yy, (label, coarse, fine) in zip(y, rows):
        colour, marker = (UNCAPPED, "s") if "uncapped" in label else (CAPPED, "o")
        for ax, key in ((ax_min, "min"), (ax_area, "area")):
            if fine is not None:
                ax.plot(
                    [coarse[key], fine[key]],
                    [yy, yy],
                    color="lightgrey",
                    lw=4,
                    zorder=1,
                )
                ax.scatter(
                    fine[key],
                    yy,
                    marker="D",
                    s=45,
                    fc="white",
                    ec=colour,
                    lw=1.5,
                    zorder=3,
                )
            ax.scatter(coarse[key], yy, marker=marker, s=50, c=colour, zorder=4)
            ax.annotate(
                f"{coarse[key]:.0f}" if key == "min" else f"{coarse[key]:.1f}",
                (coarse[key], yy),
                xytext=(0, 7),
                textcoords="offset points",
                ha="center",
                fontsize=7,
                color=TEXT,
            )
    y_paper = y[0]
    ax_min.scatter(PAPER_FIG5[0], y_paper, marker="*", s=140, c=PAPER, zorder=5)
    ax_area.scatter(PAPER_FIG5[1], y_paper, marker="*", s=140, c=PAPER, zorder=5)
    ax_min.axvline(0, color="lightgrey", lw=0.8, zorder=0)
    ax_min.set_yticks(y, [r[0] for r in rows], fontsize=9)
    ax_area.set_yticks(y, [])
    ax_min.set_xlabel("min DIFF [s]", color=TEXT)
    ax_area.set_xlabel("area with DIFF < 0 [m²]", color=TEXT)
    for ax in (ax_min, ax_area):
        ax.grid(alpha=0.7, linewidth=1, axis="x")
        ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    sns.despine(left=True, bottom=True)
    _legend(
        ax_area,
        handles=[
            Line2D(
                [], [], marker="o", ls="", color=CAPPED, label="capped, 0.2 m FDS grid"
            ),
            Line2D(
                [],
                [],
                marker="s",
                ls="",
                color=UNCAPPED,
                label="uncapped CFSM, 0.2 m FDS grid",
            ),
            Line2D(
                [],
                [],
                marker="D",
                ls="",
                mfc="white",
                mec="dimgrey",
                label="0.1 m FDS grid (one door; open marker)",
            ),
            Line2D([], [], color="lightgrey", lw=4, label="grid band"),
            Line2D(
                [],
                [],
                marker="*",
                ls="",
                color=PAPER,
                ms=11,
                label="paper Fig. 5, 60 kW, N = 100 [F]",
            ),
        ],
        loc="lower right",
        fontsize=8,
    )
    fig.suptitle(
        "DIFF measures per version: pre-movement moves min DIFF second for second; "
        "the door-flow model decides the sign",
        x=0.01,
        ha="left",
        fontsize=12,
        color=TEXT,
    )
    _stamp(
        fig,
        "Maximum pooling over n = 10 seeds (paper p. 5); K ≥ 0.23 1/m, ∃ rule, z = 2.0 m, "
        "~1 s slices, 600 s censoring. Two doors: no grid band (no 0.1 m run).",
    )
    _save(fig, "diff_measures.png")


def _remaining_band(ax, rem, colour, ls, label):
    t = rem.index.to_numpy()
    ax.fill_between(t, rem.min(axis=1), rem.max(axis=1), color=colour, alpha=0.25, lw=0)
    ax.plot(t, rem.median(axis=1), color=colour, ls=ls, lw=2, label=label)


def fig_remaining(results):
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(12, 4.6))
    gs = gridspec.GridSpec(1, 2, figure=fig)
    gs.update(wspace=0.08, left=0.07, right=0.99, top=0.85, bottom=0.2)
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
    one, two = axes
    _remaining_band(
        one,
        results[("1door", "capped_pre0")].remaining,
        CAPPED,
        "-",
        f"capped {CAP} p/s",
    )
    _remaining_band(
        one,
        results[("1door", "uncapped_pre0")].remaining,
        UNCAPPED,
        "--",
        "uncapped CFSM",
    )
    px, py = zip(*PAPER_FIG3)
    one.scatter(
        px, py, marker="s", s=45, c=PAPER, zorder=5, label="paper Fig. 3, read off [F]"
    )
    one.plot(
        [80, 80 + 23 / CAP],
        [23, 0],
        color=PAPER,
        ls=(0, (5, 2)),
        lw=1.5,
        label="our linear extrapolation at 0.96 p/s (not data)",
    )
    _remaining_band(
        two,
        results[("2door", "capped_pre0")].remaining,
        CAPPED,
        "-",
        "N = 100, capped per exit",
    )
    _remaining_band(
        two,
        results[("2door", "uncapped_pre0")].remaining,
        UNCAPPED,
        "--",
        "N = 100, uncapped CFSM",
    )
    _remaining_band(
        two,
        results[("2door", "N200_capped_pre0")].remaining,
        N200,
        "-.",
        "N = 200, capped per exit",
    )
    rem = results[("1door", "capped_pre0")].remaining
    one.annotate(
        f"capped: {rem.loc[40].mean():.0f} and {rem.loc[80].mean():.0f} left at 40 and 80 s\n"
        "(paper 61 and 23): the cap sets the rate",
        (80, rem.loc[80].mean()),
        xytext=(38, 4),
        fontsize=8,
        color=TEXT,
        arrowprops={"arrowstyle": "-", "color": TEXT, "lw": 0.8},
    )
    for ax, letter, text in (
        (one, "a", "one door, pre-movement 0"),
        (two, "b", "two doors, pre-movement 0 (binomial split per seed)"),
    ):
        ax.set_xlim(0, 130)
        ax.set_ylim(0, None)
        ax.set_xlabel("time since ignition [s]", color=TEXT)
        ax.grid(alpha=0.7, linewidth=1, axis="y")
        ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
        _title(ax, letter, text)
        _legend(ax, loc="upper right", fontsize=8)
    one.set_ylabel("agents in the room", color=TEXT)
    sns.despine(left=True, bottom=True)
    fig.suptitle(
        "Agents remaining against time: the uncapped CFSM empties the room about 3× faster than the paper",
        x=0.01,
        ha="left",
        fontsize=12,
        color=TEXT,
    )
    _stamp(fig, "Arm U, n = 10 seeds each: line = median, band = min-max over seeds.")
    _save(fig, "agents_remaining.png")


# --- Main ----------------------------------------------------------------


def load_layouts(data):
    walkable, exits = {}, {}
    for layout, (fds, *_) in LAYOUT_FDS.items():
        walkable[layout] = wkt.loads((data / fds / "geometry.wkt").read_text())
        cfg = json.loads((data / fds / "config.json").read_text())
        exits[layout] = [e["coordinates"] for e in cfg["exits"].values()]
    return walkable, exits


def load_fires(data, cache):
    fires = {}
    for label, fds in FDS_RUNS.items():
        if not (data / fds).exists():
            continue
        fire = fire_fields(data / fds, cache)
        if fire.times[-1] < T_END - 1.0:
            print(f"- {label}: FDS output ends at {fire.times[-1]:.0f} s, not used\n")
            continue
        fires[label] = fire
    return fires


def version_measures(results, fires, grid):
    """Measures of the headline map (K ≥ 0.23, ∃, ~1 s) per version and pooling."""
    table = {}
    for key, r in results.items():
        fire_names = (
            ["0.2 m, 1 door", "0.1 m, 1 door"]
            if key[0] == "1door"
            else ["0.2 m, 2 doors"]
        )
        if key[0] == "1door" and "0.2 m, 1 door, perturbed" in fires:
            fire_names.append("0.2 m, 1 door, perturbed")
        for fname in fire_names:
            aset = cell_aset(fires[fname].node["K 0.23"], fires[fname], grid)
            seeds = [measures(aset, rs, grid) for rs in r.rset_seeds]
            table[(key, fname)] = {
                "max": measures(aset, r.rset_max, grid),
                "p95": measures(aset, r.rset_p95, grid),
                "seeds": seeds,
            }
    return table


def report_measures(table):
    for pooling, title in (
        ("max", "maximum over n = 10 seeds (paper p. 5)"),
        ("p95", "95th percentile over the seeds visiting each cell"),
    ):
        print(f"## DIFF measures, K ≥ 0.23, ∃ rule, ~1 s, pooling: {title}\n")
        rows = [
            measure_row(f"{key[0]} {v_label(key)}, {fname}", t[pooling])
            for (key, fname), t in table.items()
        ]
        md_table(MEASURE_HEADER, rows)
    print("## Per-seed measures: mean and 95 % bootstrap CI over 10 seeds\n")
    rows = []
    for (key, fname), t in table.items():
        cells = [f"{key[0]} {v_label(key)}, {fname}"]
        for m in ("min", "area", "c_free"):
            mean, lo, hi = bootstrap([s[m] for s in t["seeds"]])
            cells.append(f"{mean:.1f} [{lo:.1f}, {hi:.1f}]")
        rows.append(cells)
    md_table(["version", "min DIFF s", "area DIFF<0 m²", "C m²s"], rows)


def report_bands(table):
    """Grid band (0.2 / 0.1 m) and same-grid spread (0.2 m / perturbed), apart."""
    print("## One door, maximum pooling: grid band and same-grid spread\n")
    rows = []
    for (key, fname), t in table.items():
        if fname != "0.2 m, 1 door":
            continue
        base = t["max"]
        row = [v_label(key)]
        for other in ("0.1 m, 1 door", "0.2 m, 1 door, perturbed"):
            m = table.get((key, other), {}).get("max")
            row += (
                [f"{base[k]:.1f} / {m[k]:.1f}" for k in ("min", "area")]
                if m
                else ["not available"] * 2
            )
        rows.append(row)
    md_table(
        [
            "version",
            "grid band min DIFF s (0.2 / 0.1 m)",
            "grid band area m²",
            "same-grid spread min DIFF s (0.2 m / perturbed)",
            "same-grid spread area m²",
        ],
        rows,
    )


def v_label(key):
    return next(v.label for v in VERSIONS if (v.layout, v.name) == key)


def sensitivity(results, fires, grid):
    """One door, capped, pre-movement 0, maximum pooling: rule, Δt, criterion."""
    fire = fires["0.2 m, 1 door"]
    rset = results[("1door", "capped_pre0")].rset_max
    paper_node = np.minimum(fire.node["K 0.23 @10 s"], fire.node["T 45 @10 s"])
    paper_node = np.where(paper_node > PAPER_T_END, PAPER_T_END, paper_node)
    rows = {
        "headline: K ≥ 0.23, ∃, ~1 s": cell_aset(fire.node["K 0.23"], fire, grid),
        "K ≥ 0.23 or T ≥ 45 °C, ∃, ~1 s": cell_aset(
            combined(fire, ("K 0.23", "T 45")), fire, grid
        ),
        "K ≥ 0.3, ∃, ~1 s": cell_aset(fire.node["K 0.3"], fire, grid),
        "K ≥ 0.23, nearest node, ~1 s": cell_aset(
            fire.node["K 0.23"], fire, grid, "nearest"
        ),
        "K ≥ 0.23, ∀ (Eq. 2 as printed), ~1 s": cell_aset_forall(
            fire.raw["K 0.23"], fire, grid
        ),
        "K ≥ 0.23, ∀ (Eq. 2 as printed), ~1 s, 0.1 m FDS grid": cell_aset_forall(
            fires["0.1 m, 1 door"].raw["K 0.23"], fires["0.1 m, 1 door"], grid
        ),
        "K ≥ 0.23, ∃, 10 s": cell_aset(fire.node["K 0.23 @10 s"], fire, grid),
        "paper's demonstration settings: K ≥ 0.23 or T ≥ 45, nearest, 10 s, "
        "120 s fill": cell_aset(paper_node, fire, grid, "nearest"),
    }
    print("## Sensitivity: one door, capped, pre-movement 0, maximum over n = 10\n")
    md_table(
        MEASURE_HEADER,
        [measure_row(k, measures(a, rset, grid)) for k, a in rows.items()],
    )
    fill_check(results, fires, grid)


def fill_check(results, fires, grid):
    """0.1 m grid: do cells exceeded only after 120 s enter DIFF with a fill?"""
    fire = fires["0.1 m, 1 door"]
    aset = cell_aset(fire.node["K 0.23"], fire, grid)
    late = np.isfinite(aset) & (aset > PAPER_T_END)
    filled = np.where(late | np.isinf(aset), PAPER_T_END, aset)
    print(
        f"## 120 s fill against 600 s censoring, 0.1 m FDS grid, one door\n\n"
        f"- cells first exceeded after {PAPER_T_END:.0f} s: {int(late.sum())}\n"
    )
    rows = []
    for name in ("capped_pre0", "capped_pre_default", "capped_pre30", "capped_pre60"):
        rset = results[("1door", name)].rset_max
        both = late & np.isfinite(rset) & (rset > PAPER_T_END)
        rows.append(
            measure_row(
                f"{v_label(('1door', name))}, censored", measures(aset, rset, grid)
            )
        )
        rows.append(
            measure_row(
                f"{v_label(('1door', name))}, 120 s fill ({int(both.sum())} late "
                "cells with RSET > 120 s)",
                measures(filled, rset, grid),
            )
        )
    md_table(MEASURE_HEADER, rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--data", type=Path, required=True, help="schroeder2020-room folder"
    )
    parser.add_argument(
        "--runs", type=Path, required=True, help="folder for the evacuation runs"
    )
    parser.add_argument(
        "--workers", type=int, default=6, help="parallel runs (default 6)"
    )
    opts = parser.parse_args()
    data, runs = opts.data.resolve(), opts.runs.resolve()
    assert not runs.is_relative_to(ROOT), "keep the runs outside the repository"

    run_all(data, runs, opts.workers)
    n_identical = check_identity(runs)
    print(
        f"# Schröder room, our own FDS\n\n- {n_identical} one-door runs: identical trajectories on the 0.2 m and 0.1 m FDS output\n"
    )

    walkable, exits = load_layouts(data)
    grids = {k: make_grid(w) for k, w in walkable.items()}
    for k in ("x_edges", "y_edges"):
        assert np.array_equal(getattr(grids["1door"], k), getattr(grids["2door"], k))
    grid = grids["1door"]
    # Cell areas differ by layout (jambs); use each layout's own floor.
    check_orientation(walkable["1door"], grid)
    print(
        f"- grid {grid.shape[0]} × {grid.shape[1]} cells of {CELL} m (PedPy edges); "
        f"top row {ROOM[3] - grid.y_edges[-2]:.1f} m; last column past x = 30 has area 0\n"
    )
    report_split(data)

    fires = load_fires(data, runs / "cache")
    report_screen(fires, grids)
    report_first_criterion(fires, grids)

    results = rset_results(runs, walkable, grid)
    gate = report_gate(results)
    report_queue(results)
    table_1 = version_measures(
        {k: r for k, r in results.items() if k[0] == "1door"}, fires, grids["1door"]
    )
    table_2 = version_measures(
        {k: r for k, r in results.items() if k[0] == "2door"}, fires, grids["2door"]
    )
    report_measures({**table_1, **table_2})
    report_bands(table_1)
    sensitivity(results, fires, grids["1door"])

    fig_remaining(results)
    fig_aset_criteria(
        fires["0.2 m, 1 door"],
        grid,
        walkable["1door"],
        exits["1door"],
        "aset_criteria_1door.png",
        "ASET per criterion at 2.0 m, one door, 0.2 m FDS grid",
    )
    fig_aset_criteria(
        fires["0.2 m, 2 doors"],
        grids["2door"],
        walkable["2door"],
        exits["2door"],
        "aset_criteria_2door.png",
        "ASET per criterion at 2.0 m, two doors, 0.2 m FDS grid",
    )
    fig_screen(fires, grids)
    fig_grid_pair(
        fires["0.2 m, 1 door"],
        fires["0.1 m, 1 door"],
        grid,
        walkable["1door"],
        exits["1door"],
    )
    fig_rset(results, grids, walkable, exits)
    if not gate:
        print("Gate (b) failed: the capped DIFF figures are not written.")
        return
    order = [
        "capped_pre0",
        "capped_pre_default",
        "capped_pre30",
        "capped_pre60",
        "uncapped_pre0",
    ]
    panels_1 = [
        (
            f"{v_label(('1door', n))}, 0.2 m",
            table_1[(("1door", n), "0.2 m, 1 door")]["max"],
        )
        for n in order
    ]
    panels_1.insert(
        1,
        (
            f"{v_label(('1door', 'capped_pre0'))}, 0.1 m",
            table_1[(("1door", "capped_pre0"), "0.1 m, 1 door")]["max"],
        ),
    )
    fig_diff(
        panels_1,
        grids["1door"],
        walkable["1door"],
        exits["1door"],
        "diff_1door.png",
        "DIFF maps, one door",
    )
    order_2 = [*order, "N200_capped_pre0"]
    panels_2 = [
        (v_label(("2door", n)), table_2[(("2door", n), "0.2 m, 2 doors")]["max"])
        for n in order_2
    ]
    fig_diff(
        panels_2,
        grids["2door"],
        walkable["2door"],
        exits["2door"],
        "diff_2door.png",
        "DIFF maps, two doors, 0.2 m grid (no grid band)",
    )
    rows = []
    for layout, table, fname in (
        ("1door", table_1, "0.2 m, 1 door"),
        ("2door", table_2, "0.2 m, 2 doors"),
    ):
        for n in order_2 if layout == "2door" else order:
            key = (layout, n)
            fine = table.get((key, "0.1 m, 1 door"), {}).get("max")
            doors = "1 door" if layout == "1door" else "2 doors"
            rows.append((f"{doors}: {v_label(key)}", table[(key, fname)]["max"], fine))
    fig_measures(rows)
    print("\n## Numbers shown in the figures\n")
    md_table(["figure", "item", "value"], FIGURE_NUMBERS)


if __name__ == "__main__":
    main()
