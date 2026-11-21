"""Write the FDS 6.7.7 decks for issue #808: C/VM2 Grand Ballroom, scenario CF.

Usage: ``python3 make_decks.py [--out DIR] [--t-end 1200]``

Single source for geometry and parameters; standard library only. Nothing
here has been run with FDS. Values, tags ([P] published, [D] document
inconsistent, [A] assumed) and the arithmetic are in README.md.

Decks written (CHID in brackets):

  cvm2_ballroom_fire.fds        fire part only, NO_EVACUATION [cvm2_ballroom_fire]
  cvm2_ballroom_evac.fds        fire + FDS+Evac part, phase 1 of 3:
                                EVACUATION_INITIALIZATION [cvm2_ballroom]
  cvm2_ballroom_evac_fed.fds    the same, phase 2: EVACUATION_WRITE_FED
  cvm2_ballroom_evac_mc.fds     the same, phase 3: EVACUATION_MC_MODE (every repeat)
  cvm2_ballroom_evac_dx050.fds  phase 1 on the second evacuation grid, 0.5 m
                                [cvm2_ballroom_dx050]

The three phase decks differ only in their &MISC line and share one CHID,
because FDS 6.7.7 (Evac 2.6.1) names the files it passes between the phases
CHID_evac.eff, CHID_evac.xyz and CHID_evac.fed (Source/evac.f90).
"""

import argparse
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

# --- Room: C/VM2 Commentary, Fig. B1 p. 187, Table B1 p. 190 [P] ------------
# Origin at the SW inner corner of the ballroom, x east (20 m), y north (50 m).
# cvm2-function-centre/build/geometry.py has the room at x 20-40, y 20-70.
ROOM_X, ROOM_Y, ROOM_H = 20.0, 50.0, 5.0

# --- Grids [A] --------------------------------------------------------------
DX = 0.25  # fire mesh; every coordinate below lies on the 0.5 m lattice
WALL = 0.5  # east and west walls, two fire cells, outside the 20 m clear width
BUFFER = 2.0  # exterior strip outside each wall, OPEN outer faces
X_CUTS = [-WALL - BUFFER, 5.0, 15.0, ROOM_X + WALL + BUFFER]
Y_CUTS = [0.0, 8.0, 16.0, 22.0, 28.0, 34.0, 44.0, ROOM_Y]
EVAC_DX = 0.25  # FDS+Evac grid; second grid for the mesh-dependence check:
EVAC_DX_2 = 0.5
EVAC_Z = (0.4, 1.6)  # evacuation mesh z range; floor = mid height - 1.0 m

# --- Doors: 4 double doors, 2 x 0.95 m x 2.1 m, pp. 190, 204 [P] ------------
# Centres read off Fig. B2 by the earlier study (y 31.5 and 61.5 there, +-1 m).
# On the grid: 2.0 m wide (published 1.90), 2.0 m high (published 2.10) [A].
DOOR_Y = {"South": 11.5, "North": 41.5}
DOOR_W, DOOR_H = 2.0, 2.0
EXITS = [  # id, wall x, outer face x, IOR, XYZ x
    ("West", 0.0, -WALL, -1, 0.5),
    ("East", ROOM_X, ROOM_X + WALL, +1, ROOM_X - 0.5),
]

# --- Design fire: Table 2.1 p. 56, pp. 199, 202 [P] --------------------------
ALPHA = 0.0469  # kW/s2
Q_PEAK = 2700.0  # kW, held after sprinkler activation (p. 202)
YIELDS = {"soot": 0.07, "co": 0.04, "co2": 1.5, "h2o": 1.0}  # kg/kg
DHC = 20000.0  # kJ/kg
CHI_R = 0.35
BURNER = 2.0  # m, square, room centre [A]; HRRPUA = Q_PEAK / BURNER**2
BURNER_H = 0.5  # m [A]: two cells; the example has 0.4 m (p. 202)

# --- Detection: Table 3.2 p. 88 [P]; layout [A] ------------------------------
OD_ALARM = 0.097  # 1/m, spot smoke detector
DET_SPACING = 9.8  # m, so that no point is farther than 7 m from a detector
DET_Z = ROOM_H - 0.1

# --- Evacuation: p. 203, Table B1 p. 190 [P]; #808 alignment table -----------
N_PERSONS = 1000
T_DET, T_NOTIFY, T_PRE = 66.0, 30.0, 30.0
V0 = 1.2  # m/s, constant [A]: the C/VM2 cap
DIA = 0.51  # m, constant [A]: mean of the FDS+Evac Adult
SMOKE_HEIGHT = 2.0  # m (C/VM2 tenability height, p. 49)
FED_DOOR_CRIT = -1000.0  # default of evac.f90 at FDS6.7.7, written out

SLICE_Z = (2.0, 1.5)  # 1.5 m is the grid plane nearest 1.6 m
T_END = 1200.0


def f(v: float) -> str:
    """Shortest fixed-point text of a real, always with a decimal point."""
    text = f"{v:.4f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def xb(*v: float) -> str:
    return ",".join(f(x) for x in v)


def fuel_formula() -> tuple[float, float]:
    """H and O atoms per C atom that return the Table 2.1 yields."""
    c = YIELDS["co2"] * 12.011 / 44.01 + YIELDS["co"] * 12.011 / 28.01 + YIELDS["soot"]
    h = YIELDS["h2o"] * 2 * 1.008 / 18.015
    o = 1.0 - c - h
    return (h / 1.008) / (c / 12.011), (o / 15.999) / (c / 12.011)


def fire_meshes() -> tuple[list[str], int]:
    lines, total = [], 0
    for j in range(len(Y_CUTS) - 1):
        for i in range(len(X_CUTS) - 1):
            box = (X_CUTS[i], X_CUTS[i + 1], Y_CUTS[j], Y_CUTS[j + 1], 0.0, ROOM_H)
            ijk = [round((box[2 * k + 1] - box[2 * k]) / DX) for k in range(3)]
            cells = ijk[0] * ijk[1] * ijk[2]
            total += cells
            lines.append(
                f"&MESH ID='F{j + 1}{i + 1}', IJK={ijk[0]},{ijk[1]},{ijk[2]}, "
                f"XB={xb(*box)} /  ! {cells} cells"
            )
    return lines, total


def detector_points() -> list[tuple[float, float]]:
    nx, ny = math.ceil(ROOM_X / DET_SPACING), math.ceil(ROOM_Y / DET_SPACING)
    return [
        (round((i + 0.5) * ROOM_X / nx, 2), round((j + 0.5) * ROOM_Y / ny, 2))
        for i in range(nx)
        for j in range(ny)
    ]


def door_span(name: str) -> tuple[float, float]:
    return DOOR_Y[name] - DOOR_W / 2, DOOR_Y[name] + DOOR_W / 2


def fire_part(n_meshes: int, cells: int, mesh_lines: list[str], t_end: float) -> str:
    nh, no = fuel_formula()
    t_peak = math.sqrt(Q_PEAK / ALPHA)
    hrrpua = Q_PEAK / BURNER**2
    cx, cy, s = ROOM_X / 2, ROOM_Y / 2, BURNER / 2
    x0, x1 = X_CUTS[0], X_CUTS[-1]
    w0, e1 = -WALL, ROOM_X + WALL
    out = [
        f"! --- Fire meshes: {n_meshes} meshes, {cells} cells, dx {f(DX)} m [A] ---",
        *mesh_lines,
        "",
        f"&TIME T_END={f(t_end)} /",
        "&DUMP DT_SLCF=1.0, DT_DEVC=1.0, DT_HRR=1.0 /",
        "",
        "! --- Reaction: C/VM2 Table 2.1 (Commentary p. 56) [P]; formula [A] ---",
        f"! CH{nh:.3f}O{no:.3f}: C from the CO2, CO and soot yields, H from the H2O",
        "! yield, O the rest, so that FDS returns CO2 1.5 and H2O 1.0 kg/kg.",
        f"&REAC FUEL='CVM2_FUEL', C=1.0, H={nh:.4f}, O={no:.4f},",
        f"      SOOT_YIELD={YIELDS['soot']}, CO_YIELD={YIELDS['co']},",
        f"      HEAT_OF_COMBUSTION={f(DHC)}, RADIATIVE_FRACTION={CHI_R} /",
        "",
        f"! --- Fire: {ALPHA} t2 kW to {f(Q_PEAK)} kW at {t_peak:.1f} s, then held [P] ---",
        f"! Burner {f(BURNER)} x {f(BURNER)} m in the room centre, top at "
        f"{f(BURNER_H)} m [A]; HRRPUA = {f(Q_PEAK)} / {f(BURNER**2)}.",
        f"&SURF ID='FIRE', HRRPUA={f(hrrpua)}, TAU_Q=-{t_peak:.1f}, COLOR='RED' /",
        f"&OBST XB={xb(cx - s, cx + s, cy - s, cy + s, 0, BURNER_H)}, "
        "SURF_IDS='FIRE','INERT','INERT' /  ! burner",
        "",
        "! --- Walls and doors. North and south walls, floor and ceiling are",
        "! the mesh boundary (INERT) [A]. Doors open throughout [A]. ---",
        f"&OBST XB={xb(w0, 0, 0, ROOM_Y, 0, ROOM_H)} /  ! west wall",
        f"&OBST XB={xb(ROOM_X, e1, 0, ROOM_Y, 0, ROOM_H)} /  ! east wall",
    ]
    for side, wall_x, _, _, _ in EXITS:
        a, b = (w0, 0.0) if side == "West" else (ROOM_X, e1)
        for name in DOOR_Y:
            p, q = door_span(name)
            out.append(
                f"&HOLE XB={xb(a - 0.01, b + 0.01, p, q, 0, DOOR_H)}, "
                f"EVACUATION=.FALSE. /  ! door {side}{name}, fire meshes"
            )
    out += [
        "",
        "! --- Exterior strips: OPEN outer faces, ends and tops [A] ---",
        f"&VENT XB={xb(x0, x0, 0, ROOM_Y, 0, ROOM_H)}, SURF_ID='OPEN' /",
        f"&VENT XB={xb(x1, x1, 0, ROOM_Y, 0, ROOM_H)}, SURF_ID='OPEN' /",
    ]
    for a, b in ((x0, w0), (e1, x1)):
        out += [
            f"&VENT XB={xb(a, b, 0, 0, 0, ROOM_H)}, SURF_ID='OPEN' /",
            f"&VENT XB={xb(a, b, ROOM_Y, ROOM_Y, 0, ROOM_H)}, SURF_ID='OPEN' /",
            f"&VENT XB={xb(a, b, 0, ROOM_Y, ROOM_H, ROOM_H)}, SURF_ID='OPEN' /",
        ]
    out += [
        "",
        "! --- Detection: C/VM2 Table 3.2 (p. 88) [P], layout [A] ---",
        f"! OD_*: optical density at the detector; t_d = first time above {OD_ALARM} 1/m.",
        "! SD_*: Heskestad spot detector at the same obscuration, 20.0 %/m, with",
        "! the FDS default entry lag; for comparison only.",
        "&PROP ID='SD', QUANTITY='CHAMBER OBSCURATION', ACTIVATION_OBSCURATION=20.0 /",
    ]
    for k, (x, y) in enumerate(detector_points(), 1):
        p = xb(x, y, DET_Z)
        out.append(
            f"&DEVC ID='OD_{k:02d}', QUANTITY='OPTICAL DENSITY', XYZ={p}, "
            f"SETPOINT={OD_ALARM} /"
        )
        out.append(f"&DEVC ID='SD_{k:02d}', PROP_ID='SD', XYZ={p} /")
    out += ["", "! --- Slices: docs/fds-case-requirements.md, at 2.0 m and 1.5 m ---"]
    for z in SLICE_Z:
        out += [
            f"&SLCF PBZ={f(z)}, QUANTITY='EXTINCTION COEFFICIENT' /",
            f"&SLCF PBZ={f(z)}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /",
            f"&SLCF PBZ={f(z)}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /",
            f"&SLCF PBZ={f(z)}, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
            f"&SLCF PBZ={f(z)}, QUANTITY='TEMPERATURE' /",
        ]
    return "\n".join(out)


def evac_part(evac_dx: float) -> str:
    w0, e1 = -WALL, ROOM_X + WALL
    ni, nj = round((e1 - w0) / evac_dx), round(ROOM_Y / evac_dx)
    z0, z1 = EVAC_Z
    zm = (z0 + z1) / 2
    cx, cy, s = ROOM_X / 2, ROOM_Y / 2, BURNER / 2
    ids = [f"{side}{name}" for side, *_ in EXITS for name in DOOR_Y]
    out = [
        f"! --- FDS+Evac: evacuation mesh, dx {f(evac_dx)} m, floor at z 0 [A] ---",
        f"&MESH ID='Ballroom', IJK={ni},{nj},1, XB={xb(w0, e1, 0, ROOM_Y, z0, z1)},",
        "      EVACUATION=.TRUE., EVAC_HUMANS=.TRUE., EVAC_Z_OFFSET=1.0 /",
        "&SURF ID='EVAC_WALL', RGB=200,0,200, EVAC_DEFAULT=.TRUE. /",
        "",
        "! Doorways in the evacuation meshes, full height: the automatic",
        f"! visibility mesh is centred on HUMAN_SMOKE_HEIGHT {f(SMOKE_HEIGHT)} m, where the",
        "! fire-mesh door ends [A].",
    ]
    for side, wall_x, _, _, _ in EXITS:
        a, b = (w0, 0.0) if side == "West" else (ROOM_X, e1)
        for name in DOOR_Y:
            p, q = door_span(name)
            out.append(
                f"&HOLE XB={xb(a - 0.01, b + 0.01, p, q, 0, ROOM_H)}, "
                f"EVACUATION=.TRUE. /  ! door {side}{name}"
            )
    out += ["", "! Exits on the outer wall face; all four lead to safety [A]."]
    for side, _, face_x, ior, xyz_x in EXITS:
        for name in DOOR_Y:
            p, q = door_span(name)
            out.append(
                f"&EXIT ID='{side}{name}', IOR={ior:+d}, "
                f"XB={xb(face_x, face_x, p, q, z0, z1)}, "
                f"XYZ={xb(xyz_x, DOOR_Y[name], zm)} /"
            )
    names = ",".join(f"'{i}'" for i in ids)
    probs = ",".join("1.0" for _ in ids)
    out += [
        "",
        "! Agents: constant speed, body size, detection and reaction time [A]/[P].",
        "&PERS ID='Occupant', DEFAULT_PROPERTIES='Adult',",
        f"      VELOCITY_DIST=0, VEL_MEAN={V0},",
        f"      DIAMETER_DIST=0, DIA_MEAN={DIA},",
        f"      DET_EVAC_DIST=0, DET_MEAN={f(T_DET + T_NOTIFY)},",
        f"      PRE_EVAC_DIST=0, PRE_MEAN={f(T_PRE)},",
        f"      HUMAN_SMOKE_HEIGHT={f(SMOKE_HEIGHT)}, FED_DOOR_CRIT={f(FED_DOOR_CRIT)},",
        "      OUTPUT_FED=.TRUE., OUTPUT_SPEED=.TRUE., COLOR_METHOD=4 /",
        "",
        f"&EVAC ID='BallroomOccupants', NUMBER_INITIAL_PERSONS={N_PERSONS},",
        f"      XB={xb(0, ROOM_X, 0, ROOM_Y, z0, z1)}, PERS_ID='Occupant',",
        f"      KNOWN_DOOR_NAMES={names},",
        f"      KNOWN_DOOR_PROBS={probs} /",
        f"&EVHO ID='Burner', XB={xb(cx - s, cx + s, cy - s, cy + s, z0, z1)} /",
        "",
        "! Guiding flow fields, to check in Smokeview (guide, MESH section).",
        f"&SLCF PBZ={f(zm)}, QUANTITY='VELOCITY', VECTOR=.TRUE., EVACUATION=.TRUE. /",
    ]
    return "\n".join(out)


HEADER = """&HEAD CHID='{chid}', TITLE='{title}' /

! Issue #808. After MBIE (2012), Commentary for Verification Method C/VM2,
! Appendix B, design scenario CF in the Grand Ballroom. Written for
! FDS 6.7.7 (Evac 2.6.1). NOT RUN: no FDS was available when this was written.
! Tags: [P] published, [D] document inconsistent, [A] assumed; see README.md.
! Generated by make_decks.py; do not edit by hand.
! {mode}
&MISC {misc} /
"""

DECKS = [  # file stem, CHID, &MISC, evacuation grid or None, what the run does
    (
        "cvm2_ballroom_fire",
        "cvm2_ballroom_fire",
        "NO_EVACUATION=.TRUE.",
        None,
        "Fire part only: the stand-alone fire test.",
    ),
    (
        "cvm2_ballroom_evac",
        "cvm2_ballroom",
        "EVACUATION_INITIALIZATION=.TRUE.",
        EVAC_DX,
        "Phase 1 of 3: evacuation meshes only (a drill); writes "
        "CHID_evac.eff and CHID_evac.xyz.",
    ),
    (
        "cvm2_ballroom_evac_fed",
        "cvm2_ballroom",
        "EVACUATION_WRITE_FED=.TRUE.",
        EVAC_DX,
        "Phase 2 of 3: fire meshes only; reads CHID_evac.xyz, writes the "
        "slices and CHID_evac.fed.",
    ),
    (
        "cvm2_ballroom_evac_mc",
        "cvm2_ballroom",
        "EVACUATION_MC_MODE=.TRUE.",
        EVAC_DX,
        "Phase 3 of 3, every repeat: evacuation meshes only; reads "
        "CHID_evac.eff and CHID_evac.fed.",
    ),
    (
        "cvm2_ballroom_evac_dx050",
        "cvm2_ballroom_dx050",
        "EVACUATION_INITIALIZATION=.TRUE.",
        EVAC_DX_2,
        "Phase 1 (drill) on the second evacuation grid: mesh-dependence check.",
    ),
]


def deck(chid: str, misc: str, evac_dx: float | None, mode: str, t_end: float) -> str:
    mesh_lines, cells = fire_meshes()
    title = "CVM2 Grand Ballroom, scenario CF, fast t2 fire to 2700 kW"
    parts = [
        HEADER.format(chid=chid, title=title, mode=mode, misc=misc),
        fire_part(len(mesh_lines), cells, mesh_lines, t_end),
    ]
    if evac_dx is not None:
        parts += ["", evac_part(evac_dx)]
    return "\n".join(parts) + "\n\n&TAIL /\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=pathlib.Path, default=HERE)
    ap.add_argument("--t-end", type=float, default=T_END)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    mesh_lines, cells = fire_meshes()
    for stem, chid, misc, evac_dx, mode in DECKS:
        path = a.out / f"{stem}.fds"
        path.write_text(deck(chid, misc, evac_dx, mode, a.t_end))
        print(path.name, f"CHID {chid}, {len(mesh_lines)} fire meshes, {cells} cells")


if __name__ == "__main__":
    main()
