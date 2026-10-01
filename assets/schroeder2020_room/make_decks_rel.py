"""Write the FDS decks for the rel_* variants of the Schroeder et al. (2020) room.

The fire, the reaction and door D1 are those of the authors' release,
doi:10.5281/zenodo.3875550, file 0_ASET/HRR_60kW/ASET_animation.fds.
From the repository root:
``python assets/schroeder2020_room/make_decks_rel.py <outdir> [T_END]``.
"""

import pathlib
import sys

OUT = pathlib.Path(sys.argv[1])
T_END = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0

VARIANTS = {
    "rel_1door": dict(dx=0.2, doors=("D1",), title="1 door, release fire, dx 0.2 m"),
    "rel_2door": dict(
        dx=0.2, doors=("D1", "D2"), title="2 doors, release fire, dx 0.2 m"
    ),
    "rel_1door_dx010": dict(
        dx=0.1, doors=("D1",), title="1 door, release fire, dx 0.1 m"
    ),
}

DOORS = {
    "D1": "&VENT XB=30.0,30.0,8.0,9.0,0.0,2.0, SURF_ID='OPEN' /  ! D1, east wall, 1.0 m x 2.0 m [R]",
    "D2": "&VENT XB=0.0,0.0,8.0,9.0,0.0,2.0, SURF_ID='OPEN' /  ! D2, D1 mirrored about x = 15 [A]",
}

# Device trees at cell centres: (x, y) per tree, and the z range and count.
TREES = {
    0.2: ({"W": (5.1, 5.1), "C": (15.1, 5.1), "E": (25.1, 8.5)}, (0.1, 2.9), 15),
    0.1: (
        {"W": (5.05, 5.05), "C": (15.05, 5.05), "E": (25.05, 8.55)},
        (0.05, 2.95),
        30,
    ),
}


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


def trees(dx: float) -> list[str]:
    points, (z0, z1), n = TREES[dx]
    devc = []
    for tag, (x, y) in points.items():
        for q, p in (("TEMPERATURE", "T"), ("EXTINCTION COEFFICIENT", "K")):
            devc.append(
                f"&DEVC ID='{p}_tree_{tag}', QUANTITY='{q}', "
                f"XBP={x},{x},{y},{y},{z0},{z1}, POINTS={n}, TIME_HISTORY=T /"
            )
    return devc


def deck(chid: str, v: dict) -> str:
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
        "&SLCF PBY=8.5, QUANTITY='EXTINCTION COEFFICIENT' /  ! Smokeview only: door axis",
        "&SLCF PBY=8.5, QUANTITY='TEMPERATURE' /  ! Smokeview only: door axis",
    ]
    z0, z1 = TREES[v["dx"]][1]
    return f"""&HEAD CHID='{chid}', TITLE='Schroeder et al. 2020 room, release conditions: {v["title"]}' /

! Room after B. Schroeder, L. Arnold, A. Seyfried, Fire Saf. J. 115 (2020)
! 103154, doi:10.1016/j.firesaf.2020.103154. Fire, reaction and door D1
! copied from the authors' release, doi:10.5281/zenodo.3875550, file
! 0_ASET/HRR_60kW/ASET_animation.fds (FDS 6.5.3). Tags: [R] release deck,
! [P] paper, [A] assumed. See README.md.

! --- Domain: 30 x 10 x 3 m [R], dx = {v["dx"]} m ---
! The release uses one mesh IJK=150,50,15 (0.2 m cells). Here: six meshes
! along x, 5 m each, one MPI rank per mesh; the burner and the doors do
! not cross a mesh interface.
{meshes(v["dx"])}

&TIME T_END={T_END:g} /
&DUMP DT_SLCF=1.0, DT_DEVC=1.0, DT_RESTART=60.0 /

! --- Reaction: as in the release [R] ---
! HEAT_OF_COMBUSTION, CO_YIELD and RADIATIVE_FRACTION are not set, so the
! FDS defaults apply, exactly as in the release.
&REAC FUEL='REAC_FUEL', FYI='NFPA Babrauskas polyurethane, as Schroeder et al. 2020 release',
      C=6.3, H=7.1, O=2.1, N=1.0, SOOT_YIELD=0.129 /

! --- Fire: 60 kW/m2 on a 1 x 1 m floor vent at x, y = 1-2 m [R] ---
! No RAMP_Q or TAU_Q, as in the release.
&SURF ID='FIRE', HRRPUA=60., COLOR='RED' /
&VENT XB=1.0,2.0,1.0,2.0,0.0,0.0, SURF_ID='FIRE' /

! --- Doors: open for the whole run, vented to ambient ---
{doors}

! --- Walls, floor, ceiling: the default INERT mesh boundary [R] ---

! --- Slices: 2.0 m as in the release, plus 1.0 and 1.6 m ---
{chr(10).join(slices)}

! --- Device trees at cell centres, z = {z0} .. {z1} m ---
{chr(10).join(trees(v["dx"]))}

&TAIL /
"""


for name, v in VARIANTS.items():
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.fds").write_text(deck(name, v))
    print(d / f"{name}.fds")
