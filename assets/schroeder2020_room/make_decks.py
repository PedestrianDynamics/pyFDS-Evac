"""Write the FDS decks for the Schroeder et al. (2020) room variants.

The hrr060_* family: the room rebuilt from the paper alone. From the
repository root:
``python assets/schroeder2020_room/make_decks.py <outdir> [T_END]``.
"""

import pathlib
import sys

OUT = pathlib.Path(sys.argv[1])
T_END = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0

VARIANTS = {
    "hrr060_1door": dict(dx=0.2, doors=("D1",), title="1 door, 60 kW, dx 0.2 m"),
    "hrr060_2door": dict(dx=0.2, doors=("D1", "D2"), title="2 doors, 60 kW, dx 0.2 m"),
    "hrr060_1door_dx010": dict(dx=0.1, doors=("D1",), title="1 door, 60 kW, dx 0.1 m"),
}

DOORS = {
    "D1": "&VENT XB=30.0,30.0,8.2,9.4,0.0,2.0, SURF_ID='OPEN' /  ! exit, east wall, 1.2 m x 2.0 m",
    "D2": "&VENT XB=0.0,0.0,8.2,9.4,0.0,2.0, SURF_ID='OPEN' /  ! second exit, D1 mirrored about x = 15",
}

HRR_KW = 60.0
BURNER_AREA = 0.36


def meshes(dx: float) -> str:
    """Six meshes along x, 5 m each, one MPI rank per mesh."""
    i, j, k = round(5 / dx), round(10 / dx), round(3 / dx)
    lines = []
    for m in range(6):
        x0, x1 = 5 * m, 5 * (m + 1)
        lines.append(
            f"&MESH ID='M{m + 1}', IJK={i},{j},{k}, XB={x0:.1f},{x1:.1f},0.0,10.0,0.0,3.0 /"
        )
    return "\n".join(lines)


def deck(chid: str, v: dict) -> str:
    hrrpua = HRR_KW / BURNER_AREA
    doors = "\n".join(DOORS[d] for d in v["doors"])
    slices = []
    for z in (1.0, 1.6, 2.0):
        slices += [
            f"&SLCF PBZ={z:.1f}, QUANTITY='EXTINCTION COEFFICIENT' /",
            f"&SLCF PBZ={z:.1f}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /",
            f"&SLCF PBZ={z:.1f}, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /",
            f"&SLCF PBZ={z:.1f}, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
            f"&SLCF PBZ={z:.1f}, QUANTITY='TEMPERATURE' /",
        ]
    for z in (1.6, 2.0):
        slices.append(f"&SLCF PBZ={z:.1f}, QUANTITY='INTEGRATED INTENSITY' /")
    slices += [
        "&SLCF PBZ=2.0, QUANTITY='VISIBILITY' /  ! Smokeview only",
        "&SLCF PBY=8.8, QUANTITY='EXTINCTION COEFFICIENT' /  ! Smokeview only: door axis",
        "&SLCF PBY=8.8, QUANTITY='TEMPERATURE' /  ! Smokeview only: door axis",
    ]
    devc = []
    for tag, (x, y) in {
        "W": (5.1, 5.1),
        "C": (15.1, 5.1),
        "E": (25.1, 8.9),
    }.items():  # cell centres
        for q, p in (("TEMPERATURE", "T"), ("EXTINCTION COEFFICIENT", "K")):
            devc.append(
                f"&DEVC ID='{p}_tree_{tag}', QUANTITY='{q}', "
                f"XBP={x},{x},{y},{y},0.2,2.8, POINTS=14, TIME_HISTORY=T /"
            )
    return f"""&HEAD CHID='{chid}', TITLE='Schroeder et al. 2020 demonstration room: {v["title"]}' /

! Room after B. Schroeder, L. Arnold, A. Seyfried, Fire Saf. J. 115 (2020)
! 103154, doi:10.1016/j.firesaf.2020.103154. Built from the paper text and
! figures only; see README.md for the source of every value ([P] paper,
! [F] read off a paper figure, [A] assumed).

! --- Domain: 30 x 10 x 3 m [P, pre-proof p. 5], dx = {v["dx"]} m ---
! Six meshes along x, 5 m each, one MPI rank per mesh.
{meshes(v["dx"])}

&TIME T_END={T_END:g} /
&DUMP DT_SLCF=1.0, DT_DEVC=1.0, DT_RESTART=60.0 /

! --- Fuel: flexible polyurethane foam GM21 [A] ---
! SFPE Handbook 5th ed., App. 3, Table A.38 (formula) and Table A.39.
! HEAT_OF_COMBUSTION is the chemical heat of combustion (not 26.2 MJ/kg
! total); RADIATIVE_FRACTION = dH_rad/dH_ch = 9.2/17.8 from the same row.
! No HCN_YIELD: the fuel nitrogen leaves as N2. No irritant is tracked.
! Mass extinction coefficient: FDS default, 8700 m2/kg.
&REAC FUEL='PU_GM21', C=1.0, H=1.8, O=0.30, N=0.05,
      SOOT_YIELD=0.131, CO_YIELD=0.010, HEAT_OF_COMBUSTION=17800.,
      RADIATIVE_FRACTION=0.52 /

! --- Fire: {HRR_KW:g} kW constant, 0.6 x 0.6 m floor burner [A] ---
! "opposite corner to the exit" [P, p. 5]; south-west corner [P, Fig. 2].
! HRRPUA = {HRR_KW:g} kW / {BURNER_AREA} m2. No RAMP_Q: FDS default onset
! (tanh, TAU_Q = 1 s).
&SURF ID='FIRE', HRRPUA={hrrpua:.1f}, COLOR='RED' /
&VENT XB=0.6,1.2,0.6,1.2,0.0,0.0, SURF_ID='FIRE' /

! --- Doors: open for the whole run, 2.0 m high [A], vented to ambient ---
! Width 1.2 m and position 0.6 m below the north wall read off Fig. 2 [F].
{doors}

! --- Walls, floor, ceiling: the default INERT mesh boundary [A] ---

! --- Slices read by pyFDS-Evac (1.6 m default) and the paper (2.0 m) ---
{chr(10).join(slices)}

! --- Device trees for the layer height, z = 0.2 .. 2.8 m every 0.2 m ---
{chr(10).join(devc)}

&TAIL /
"""


for name, v in VARIANTS.items():
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.fds").write_text(deck(name, v))
    print(d / f"{name}.fds")
