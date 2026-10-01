"""Write the FDS decks for the Room 3 design-fire sweep (P0b).

Usage: ``python3 make_decks.py <outdir> [--dx 0.2] [--t-end 480]
[--door-c open|closed] [--only NAME ...]``; writes ``<outdir>/<name>/<name>.fds``.

The fire is the plan's a-priori design fire (annex, Enrico 2026-09-30),
fixed before any routing run. Sweep: alpha in {0.012, 0.047} kW/s^2, fuel
in {PVC, PUR}, ceiling H in {3.0, 4.0} m, plus the central case
(0.047, PVC, 3.5 m). Geometry from geometry.py. Tags: [N] annex, [D]
digitised, [A] assumed here.
"""

import argparse
import math
import pathlib

from geometry import (
    BURNER_XY,
    CORRIDOR,
    DOOR_A,
    DOOR_B,
    DOOR_C,
    DOOR_D,
    EXIT_X,
    HALL,
    ROOM3,
    WALL,
)

# Fuels [N]: soot and CO yields from Schroeder 2017 Tables 4.4-4.5.
# PVC: the FDS User's Guide example that Table 4.5 is based on (section
# "Fuels Not Compatible with Simple Chemistry"): monomer C2H3Cl, all Cl to
# HCl, lumped reaction balanced below, HEAT_OF_COMBUSTION 16400 kJ/kg (SFPE
# Handbook, as in the Guide). PUR: yields and the mean heat of combustion
# 18770 kJ/kg from Schroeder 2017 p. 74 (TRStrab BS); the formula is that of
# the Schroeder et al. 2020 release (NFPA Babrauskas polyurethane) [A]. The
# thesis's HCN yield (0.070) and late-stage soot (0.129 after 600 s) are not
# used: the annex gives soot and CO only, and T_END is 480 s.
FUELS = {
    "pvc": dict(soot=0.172, co=0.063),
    "pur": dict(soot=0.056, co=0.122),
}
HRRPUA = 250.0  # kW/m2 [N]
BURNER = BURNER_XY  # 3 x 2 m, centred in Room 3 [N]
Q_MAX = HRRPUA * (BURNER[1] - BURNER[0]) * (BURNER[3] - BURNER[2])  # 1500 kW


def variants() -> dict:
    out = {"a047_pvc_h35": dict(alpha=0.047, fuel="pvc", h=3.5)}
    for a in (0.012, 0.047):
        for f in ("pvc", "pur"):
            for h in (3.0, 4.0):
                out[f"a{round(a * 1000):03d}_{f}_h{round(h * 10):02d}"] = dict(
                    alpha=a, fuel=f, h=h
                )
    return out


def pvc_reaction(soot: float, co: float) -> str:
    """Lumped C2H3Cl reaction with the given soot and CO mass yields."""
    mw = 2 * 12.011 + 3 * 1.008 + 35.453
    nu_s = soot * mw / 12.011  # soot as pure carbon
    nu_co = co * mw / 28.010
    nu_co2 = 2 - nu_s - nu_co
    nu_h2o = (3 - 1) / 2
    nu_o2 = (2 * nu_co2 + nu_co + nu_h2o) / 2
    nu = [-1.0, -nu_o2, nu_co2, nu_co, nu_s, nu_h2o, 1.0]
    return f"""! PVC as in the FDS User's Guide example (Schroeder 2017 Table 4.5):
! monomer C2H3Cl, lumped, heat of combustion 16400 kJ/kg. Atom balance per mole of fuel: C 2, H 3,
! Cl 1, O {2 * nu_o2:.4f}. Soot yield {soot}, CO yield {co} kg/kg [N]; all Cl to HCl.
&SPEC ID='NITROGEN', BACKGROUND=.TRUE. /
&SPEC ID='OXYGEN', MASS_FRACTION_0=0.232 /
&SPEC ID='WATER VAPOR', MASS_FRACTION_0=0.006 /
&SPEC ID='CARBON DIOXIDE' /
&SPEC ID='CARBON MONOXIDE' /
&SPEC ID='SOOT', FORMULA='C' /
&SPEC ID='HYDROGEN CHLORIDE' /
&SPEC ID='VINYL CHLORIDE', FORMULA='C2H3Cl' /
&REAC FUEL='VINYL CHLORIDE',
      SPEC_ID_NU='VINYL CHLORIDE','OXYGEN','CARBON DIOXIDE','CARBON MONOXIDE','SOOT','WATER VAPOR','HYDROGEN CHLORIDE',
      NU={",".join(f"{v:.4f}" for v in nu)},
      HEAT_OF_COMBUSTION=16400. /"""


def pur_reaction(soot: float, co: float) -> str:
    return f"""! PUR, simple chemistry, formula of the Schroeder et al. 2020 release (NFPA
! Babrauskas polyurethane) [A]. Soot yield {soot}, CO yield {co} kg/kg and
! heat of combustion 18770 kJ/kg: Schroeder 2017 Table 4.4 and p. 74 [N].
&REAC FUEL='REAC_FUEL', FYI='NFPA Babrauskas polyurethane',
      C=6.3, H=7.1, O=2.1, N=1.0, SOOT_YIELD={soot}, CO_YIELD={co},
      HEAT_OF_COMBUSTION=18770. /"""


def meshes(dx: float, h: float) -> tuple[list[str], float]:
    """Six meshes over the floor footprint only: 2 corridor, 4 hall/Room 3."""
    nz = max(1, round(h / dx))
    cx0, cy0, cx1, cy1 = CORRIDOR
    blocks = [(cx0, cx1, cy0, 12.4), (cx0, cx1, 12.4, cy1)]
    ys = (0.0, 7.8, 15.6, 23.4, ROOM3[3])
    blocks += [(0.0, HALL[2], ys[k], ys[k + 1]) for k in range(4)]
    lines = []
    for m, (x0, x1, y0, y1) in enumerate(blocks, 1):
        i, j = round((x1 - x0) / dx), round((y1 - y0) / dx)
        lines.append(
            f"&MESH ID='M{m}', IJK={i},{j},{nz}, XB={x0:.1f},{x1:.1f},{y0:.1f},{y1:.1f},0.0,{h:.2f} /"
        )
    return lines, h / nz


def walls(h: float, door_c: str) -> list[str]:
    """Hall/corridor wall with A, B; Room 3 walls with C, D (holes)."""
    x0, x1 = 0.0, WALL
    r3y0 = ROOM3[1] - WALL
    out = [
        f"&OBST XB={x0:.1f},{x1:.1f},0.0,{ROOM3[3]:.1f},0.0,{h:.2f}, COLOR='GRAY 60' /  ! wall x 0-0.2 [A]",
        f"&OBST XB={x0:.1f},{HALL[2]:.1f},{r3y0:.1f},{ROOM3[1]:.1f},0.0,{h:.2f}, COLOR='GRAY 60' /  ! wall hall/Room 3 [A]",
    ]
    doors = [("A", DOOR_A), ("B", DOOR_B), ("D", DOOR_D)]
    for name, (ya, yb) in doors:
        out.append(
            f"&HOLE XB=-0.1,0.3,{ya:.1f},{yb:.1f},0.0,2.0 /  ! door {name}, 2 m wide, 2 m high"
        )
    if door_c == "open":
        xa, xb = DOOR_C
        out.append(
            f"&HOLE XB={xa:.1f},{xb:.1f},{r3y0 - 0.1:.1f},{ROOM3[1] + 0.1:.1f},0.0,2.0 /  ! door C, open"
        )
    else:
        out.append("! door C closed")
    return out


def trees(dx: float, dz: float, nz: int) -> list[str]:
    """Temperature and extinction trees at cell centres, floor to ceiling."""

    def cc(v: float, origin: float) -> float:
        return round(origin + (math.floor((v - origin) / dx) + 0.5) * dx, 4)

    points = {
        "corrE": (-2.5, -8.0),
        "doorA_c": (-1.0, 1.6),
        "corr_mid": (-2.5, 12.0),
        "doorB_c": (-1.0, 21.6),
        "doorD_c": (-1.0, 27.6),
        "corrF": (-2.5, 33.0),
        "hall_lo": (5.4, 6.0),
        "hall_mid": (5.4, 12.0),
        "hall_hi": (5.4, 18.0),
        "doorA_h": (1.0, 1.6),
        "doorB_h": (1.0, 21.6),
        "room3": (9.0, 29.5),
    }
    z0, z1 = dz / 2, (nz - 0.5) * dz
    out = []
    for tag, (x, y) in points.items():
        xo = CORRIDOR[0] if x < 0 else 0.0
        yo = CORRIDOR[1] if x < 0 else 0.0
        xc, yc = cc(x, xo), cc(y, yo)
        for q, p in (("TEMPERATURE", "T"), ("EXTINCTION COEFFICIENT", "K")):
            out.append(
                f"&DEVC ID='{p}_{tag}', QUANTITY='{q}', XBP={xc},{xc},{yc},{yc},{z0:.4f},{z1:.4f}, "
                f"POINTS={nz}, TIME_HISTORY=T /"
            )
    return out


def deck(name: str, v: dict, dx: float, t_end: float, door_c: str) -> str:
    mesh_lines, dz = meshes(dx, v["h"])
    nz = round(v["h"] / dz)
    tau = math.sqrt(Q_MAX / v["alpha"])
    fuel = FUELS[v["fuel"]]
    reac = pvc_reaction(**fuel) if v["fuel"] == "pvc" else pur_reaction(**fuel)
    slices = [
        f"&SLCF PBZ={z}, QUANTITY='EXTINCTION COEFFICIENT' /" for z in (1.6, 2.0, 2.8)
    ]
    slices += [
        "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /",
        "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /",
        "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
        "&SLCF PBZ=1.6, QUANTITY='TEMPERATURE' /",
        "&SLCF PBX=-2.5, QUANTITY='EXTINCTION COEFFICIENT' /  ! corridor axis, Smokeview",
    ]
    ex0, ex1 = EXIT_X
    bx0, bx1, by0, by1 = BURNER
    return f"""&HEAD CHID='{name}', TITLE='Route choice after Schroeder et al. 2015: Room 3 fire, alpha {v["alpha"]}, {v["fuel"].upper()}, H {v["h"]} m, dx {dx} m' /

! Geometry after Schroeder et al. 2015 Fig. 6 / Schroeder 2017 Fig. 3.9
! (digitised, +-0.5-1 m, snapped to 0.2 m); see build/geometry.py. Design
! fire from the plan's annex, fixed a priori. Tags: [N] annex, [D]
! digitised, [A] assumed. See ../README.md.

! --- Domain: corridor x -5..0, y -10..35; hall + Room 3 x 0..10.6, y 0..31 ---
! Meshes cover the floor footprint only; H = {v["h"]} m, dz = {dz:.4f} m.
{chr(10).join(mesh_lines)}

&TIME T_END={t_end:g} /
&DUMP DT_SLCF=1.0, DT_DEVC=1.0, DT_RESTART=60.0 /

! --- Reaction [N] ---
{reac}

! --- Fire: t^2, alpha = {v["alpha"]} kW/s^2, to {Q_MAX:.0f} kW at {tau:.1f} s [N] ---
! HRRPUA {HRRPUA:g} kW/m2 on a 3 x 2 m floor burner centred in Room 3.
&SURF ID='FIRE', HRRPUA={HRRPUA:g}, TAU_Q=-{tau:.1f}, COLOR='RED' /
&VENT XB={bx0:.1f},{bx1:.1f},{by0:.1f},{by1:.1f},0.0,0.0, SURF_ID='FIRE' /

! --- Internal walls and doors (all 2 m wide [D], 2 m high [A]) ---
{chr(10).join(walls(v["h"], door_c))}

! --- Exits E, F: open to ambient on the corridor end walls, 2 m high [A] ---
&VENT XB={ex0:.1f},{ex1:.1f},{CORRIDOR[1]:.1f},{CORRIDOR[1]:.1f},0.0,2.0, SURF_ID='OPEN' /  ! exit E
&VENT XB={ex0:.1f},{ex1:.1f},{CORRIDOR[3]:.1f},{CORRIDOR[3]:.1f},0.0,2.0, SURF_ID='OPEN' /  ! exit F

! --- Walls, floor, ceiling: the default INERT boundary [A] ---

! --- Slices: soot extinction at 1.6, 2.0, 2.8 m; CO, CO2, O2, T at 1.6 m ---
{chr(10).join(slices)}

! --- Device trees at cell centres ---
{chr(10).join(trees(dx, dz, nz))}

&TAIL /
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--dx", type=float, default=0.2)
    ap.add_argument("--t-end", type=float, default=480.0)
    ap.add_argument("--door-c", choices=("open", "closed"), default="open")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    suffix = "" if a.dx == 0.2 else f"_dx{round(a.dx * 100):03d}"
    suffix += "" if a.door_c == "open" else "_Cclosed"
    for name, v in variants().items():
        if a.only and name not in a.only:
            continue
        chid = name + suffix
        d = a.outdir / chid
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{chid}.fds").write_text(deck(chid, v, a.dx, a.t_end, a.door_c))
        print(d / f"{chid}.fds")


if __name__ == "__main__":
    main()
