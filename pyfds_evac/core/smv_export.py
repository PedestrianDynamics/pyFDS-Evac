"""Export pyFDS-Evac agent trajectories as FDS `.prt5` particle files.

Smokeview renders FDS Lagrangian particle output from `.prt5` files listed
in the case `.smv`. This module writes a minimal, valid `.prt5` stream from
a JuPedSim trajectory dataframe and appends the matching `PRT5` +
`CLASS_OF_PARTICLES` block to the `.smv` so agents show up alongside smoke
in a regular Smokeview session.

Binary layout matches Smokeview's `IOpart.c` reader (FORTRAN-unformatted
records with little-endian 4-byte length markers):

Header (once)
    1:  int32  one              (= 1, endian flag)
    2:  int32  version          (= NINT(version*100))
    3:  int32  n_classes        (= 1 here)
    4:  int32  numtypes[2]      (= 0, 0 for a class with no quantities)
    Per declared quantity (repeated numtypes[0]+numtypes[1] times):
    5a: char[30] label          (30-char label, space-padded)
    5b: char[30] unit           (30-char unit, space-padded)

Per frame
    1:  float32 time_s
    2:  int32   n_points
    3:  float32[3*N]  xyz       (packed as [all X][all Y][all Z])
    4:  int32[N]      tags
    5:  float32[N]    azimuth   (only when written with with_azimuth=True;
                                 numtypes must then be (1, 0))

SMV text block: to get humanoid avatars in Smokeview we bind the particle
class to an AVATARDEF from `objects.svo` via a `PROP` + a `CLASS_OF_PARTICLES`
header of the form ``<name> % % <prop_id>`` (see `docs/smv-avatars.md`):

    PROP
     <prop_id>
      <n_svo_ids>
     human_altered_with_data
     human_fixed
     ellipsoid
      7
     D=0.2
     SX=3.0
     SY=3.0
     SZ=3.0
     R=26
     G=102
     B=230

    CLASS_OF_PARTICLES
     <class_name> % % <prop_id>
      <r> <g> <b>
      <n_quantities>
    PRT5  <mesh_number>
     <relative_prt5_path>
      <n_classes>
      <class_index>
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from .scenario import ScenarioResult

_PRT5_VERSION = 600
_INT32_MAX = 2**31 - 1


def _fortran_record(fh, payload: bytes) -> None:
    """Write a single Fortran-unformatted record: [u32 len][payload][u32 len]."""
    length = struct.pack("<I", len(payload))
    fh.write(length)
    fh.write(payload)
    fh.write(length)


def write_agent_prt5(
    prt5_path: Path,
    df: "pd.DataFrame",
    *,
    frame_rate: float,
    z: float,
    with_azimuth: bool = False,
) -> None:
    """Serialize `df` to an FDS `.prt5` particle file.

    `df` must have columns `frame`, `id`, `x`, `y`. When `with_azimuth`
    is True it must additionally have `ori_x`, `ori_y`; the per-agent
    body angle `atan2(ori_y, ori_x)` is written as a single `AZIMUTH`
    quantity per frame so Smokeview can rotate the avatar to face the
    walking direction. Frames with zero agents are skipped mid-stream
    (would falsely terminate `prt5parser`). A single `n_points=0`
    frame is appended at the end as a clean terminator.
    """
    import numpy as np

    required = {"frame", "id", "x", "y"}
    if with_azimuth:
        required |= {"ori_x", "ori_y"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"trajectory dataframe missing columns: {sorted(missing)}")

    if df["id"].max(skipna=True) is not None and df["id"].max() > _INT32_MAX:
        raise ValueError(
            f"agent id exceeds int32 max ({_INT32_MAX}); .prt5 tags are int32"
        )

    prt5_path = Path(prt5_path)
    prt5_path.parent.mkdir(parents=True, exist_ok=True)

    frames = sorted(df["frame"].unique().tolist())
    last_frame = frames[-1] if frames else 0
    n_quantities = 1 if with_azimuth else 0

    with prt5_path.open("wb") as fh:
        _fortran_record(fh, struct.pack("<i", 1))
        _fortran_record(fh, struct.pack("<i", _PRT5_VERSION))
        _fortran_record(fh, struct.pack("<i", 1))
        _fortran_record(fh, struct.pack("<ii", n_quantities, 0))
        # Per declared quantity, Smokeview's IOpart.c expects a 30-char
        # label record and a 30-char unit record. Missing them makes the
        # reader skip into the first frame body and desynchronise.
        if with_azimuth:
            _fortran_record(fh, b"body angle".ljust(30, b" "))
            _fortran_record(fh, b"deg".ljust(30, b" "))

        grouped = df.groupby("frame", sort=True)
        for frame, rows in grouped:
            n = len(rows)
            if n == 0:
                continue
            t = float(frame) / float(frame_rate)
            _fortran_record(fh, struct.pack("<f", t))
            _fortran_record(fh, struct.pack("<i", n))
            x = rows["x"].to_numpy(dtype=np.float32, copy=False)
            y = rows["y"].to_numpy(dtype=np.float32, copy=False)
            z_arr = np.full(n, z, dtype=np.float32)
            xyz_bytes = x.tobytes() + y.tobytes() + z_arr.tobytes()
            _fortran_record(fh, xyz_bytes)
            tags = rows["id"].to_numpy(dtype=np.int32, copy=False)
            _fortran_record(fh, tags.tobytes())
            if with_azimuth:
                ori_x = rows["ori_x"].to_numpy(dtype=np.float64, copy=False)
                ori_y = rows["ori_y"].to_numpy(dtype=np.float64, copy=False)
                angles = np.mod(np.degrees(np.arctan2(ori_y, ori_x)), 360.0)
                _fortran_record(fh, angles.astype(np.float32).tobytes())

        t_end = float(last_frame) / float(frame_rate)
        _fortran_record(fh, struct.pack("<f", t_end))
        _fortran_record(fh, struct.pack("<i", 0))


_TOP_KEYWORDS = (
    "PROP",
    "CLASS_OF_PARTICLES",
    "CLASS_OF_HUMANS",
    "PRT5",
    "DEVICE",
    "SLCF",
    "DEVICE_ACT",
    "GRID",
    "TRNX",
    "TRNY",
    "TRNZ",
    "MESH",
    "SMOKF3D",
    "BNDF",
    "TITLE",
    "CHID",
    "FDSVERSION",
    "HRRPUVCUT",
    "ENDF",
)


def _block_end(lines: list[str], start: int) -> int:
    """Return exclusive end index of the block starting at `lines[start]`."""
    j = start + 1
    while j < len(lines):
        head = lines[j].split()[0] if lines[j].strip() else ""
        if head in _TOP_KEYWORDS:
            return j
        j += 1
    return j


def _strip_existing_agent_blocks(
    smv_text: str, prt5_basename: str, prop_id: str
) -> str:
    """Remove any prior PROP/CLASS_OF_PARTICLES/PRT5 blocks for this prt5.

    A stale CLASS_OF_PARTICLES with the wrong n_quantities would make
    Smokeview mis-read the .prt5 (treating a quantity record as the
    next frame's XYZ) and crash. Re-running the exporter after the
    on-disk schema changed must therefore overwrite the old blocks.
    Strategy: find each PRT5 line that points at our prt5, then also
    strip the immediately preceding CLASS_OF_PARTICLES (or
    CLASS_OF_HUMANS) and PROP blocks if present — the patcher always
    writes those three together.
    """
    lines = smv_text.splitlines()
    targets: set[int] = set()

    for i, line in enumerate(lines):
        if not line.startswith("PRT5"):
            continue
        if i + 1 >= len(lines) or lines[i + 1].strip() != prt5_basename:
            continue
        targets.update(range(i, _block_end(lines, i)))

        # Walk back through any immediately preceding CLASS_OF_PARTICLES /
        # CLASS_OF_HUMANS / PROP blocks that the patcher paired with this PRT5.
        k = i - 1
        while k >= 0:
            # Skip blank lines between pair members.
            while k >= 0 and not lines[k].strip():
                k -= 1
            if k < 0:
                break
            # Find the start of the block that contains line k.
            start = k
            while start > 0:
                head = lines[start].split()[0] if lines[start].strip() else ""
                if head in _TOP_KEYWORDS:
                    break
                start -= 1
            head = lines[start].split()[0] if lines[start].strip() else ""
            if head not in ("CLASS_OF_PARTICLES", "CLASS_OF_HUMANS", "PROP"):
                break
            targets.update(range(start, _block_end(lines, start)))
            k = start - 1

    # Also strip orphan PROP blocks with matching prop_id.
    for i, line in enumerate(lines):
        if line.strip() != "PROP" or i in targets:
            continue
        if i + 1 < len(lines) and lines[i + 1].strip() == prop_id:
            targets.update(range(i, _block_end(lines, i)))

    if not targets:
        return smv_text
    kept = [line for i, line in enumerate(lines) if i not in targets]
    while kept and kept[-1].strip() == "":
        kept.pop()
    return "\n".join(kept) + "\n"


_DEFAULT_AVATARS = ("human_rotating", "human_altered_with_data", "human_fixed")
_DEFAULT_AVATAR_SCALE = 3.0

# Stock `human_*` AVATARDEFs in objects.svo use a fixed `90.0 rotatez` and
# declare no :AZIMUTH indep variable, so per-particle AZIMUTH has no token to
# substitute into (readobject.c::UpdatePartClassDepend → GetObjectFrameTokenLoc
# returns -1, so IOobjects.c skips the fvars_dep write at L4172). We ship our
# own AVATARDEF that declares `:AZIMUTH=0` and applies `$AZIMUTH rotatez` so
# AZIMUTH = atan2(ori_y, ori_x) rotates the figure to face walking direction
# (at AZIMUTH=0 the avatar faces +X, at 90° faces +Y).
#
# The draw program is modelled on `human_fixed` — vertices are in metres at
# the avatar's local origin (feet on the ground), with a hardcoded `0.3` scale
# that yields a ~1.89 m tall figure. We deliberately do NOT consume `:W :H1`
# from PROP defaults, because the stock `human_altered_with_data` trunk
# collapses to zero when those have no value and relies on `0.579` / `0.3`
# nested scales that interact with FDS's world-coord normalisation in
# IOpart.c (SCALE2SMV applied both at the particle translate and again at
# DrawSmvObject entry) to produce an unintuitive size.
#
# Smokeview loads `<CHID>.svo` from the case directory alongside the global
# `objects.svo` (readobject.c L1498, "last definition wins"), so shipping
# the file next to the .smv is enough — no global install edit.
_HUMAN_ROTATING_AVATARDEF = """\
AVATARDEF
 human_rotating
 :DUM1 :DUM2 :DUM3 :W :D=0.1 :H1 :SX :SY :SZ :R=26 :G=102 :B=230 :HX :HY :HZ :AZIMUTH=0
 $AZIMUTH rotatez
 90.0 rotatez
 "TAN" setcolor
 0.3 0.3 0.3 scalexyz
 push 0.0 0.0 5.2 translate 1.1 drawsphere
   "BLUE" setcolor
   push -0.25 -0.4 0.05 translate 0.2 drawsphere pop
   push  0.25 -0.4 0.05 translate 0.2 drawsphere pop
 pop
 $R $G $B setrgb
 push 0.0 0.0 3.55 translate 0.5 0.3 1.0 scalexyz 2.5 drawsphere pop
 "TAN" setcolor
 push -0.9 0.0 3.5 translate  35.0 rotatey 0.2  0.2  1.0 scalexyz 3.0 drawsphere pop
 push  0.9 0.0 3.5 translate -35.0 rotatey 0.2  0.2  1.0 scalexyz 3.0 drawsphere pop
 39 64 139 setrgb
 push -0.5 0.0 1.3 translate  30.0 rotatey 0.25 0.25 1.0 scalexyz 3.0 drawsphere pop
 push  0.5 0.0 1.3 translate -30.0 rotatey 0.25 0.25 1.0 scalexyz 3.0 drawsphere pop
"""

# A minimal AVATARDEF that draws a single solid sphere at the particle
# position — no rotation required, no compound scales. Useful when the
# humanoid avatar renders at unexpected size and you want a sanity-check
# shape. `scaleauto` applies `SCALE2FDS(x) = x * xyzmaxdiff`, which
# exactly cancels the `SCALE2SMV(1.0)` that Smokeview multiplies in
# at DrawSmvObject entry (IOpart.c L384), so after `1.0 scaleauto`
# subsequent `drawsphere R` draws a sphere of radius R metres in world
# coords, regardless of scene size.
_SPHERE_AVATARDEF = """\
AVATARDEF
 agent_sphere
 :R=26 :G=102 :B=230
 $R $G $B setrgb
 1.0 scaleauto
 0.25 drawsphere
"""

# A directional "lollipop" — a body sphere plus a small red marker
# translated toward the avatar's facing direction. AZIMUTH=0 places
# the red marker at world +X; rotation should visibly swing it around
# the body. `1.0 scaleauto` at the top brings the draw coord system
# back to metres so translates and drawsphere radii are in metres.
_ARROW_AVATARDEF = """\
AVATARDEF
 agent_arrow
 :R=26 :G=102 :B=230 :AZIMUTH=0
 $AZIMUTH rotatez
 1.0 scaleauto
 $R $G $B setrgb
 push 0.0 0.0 0.5 translate 0.25 drawsphere pop
 255 64 64 setrgb
 push 0.5 0.0 0.5 translate 0.1 drawsphere pop
"""

_AVATAR_STYLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "human": (_HUMAN_ROTATING_AVATARDEF, _DEFAULT_AVATARS),
    "sphere": (_SPHERE_AVATARDEF, ("agent_sphere",)),
    "arrow": (_ARROW_AVATARDEF, ("agent_arrow",)),
}


def _resolve_avatar_style(style: str) -> tuple[str, tuple[str, ...]]:
    if style not in _AVATAR_STYLES:
        raise ValueError(
            f"unknown avatar style {style!r}; choose from {sorted(_AVATAR_STYLES)}"
        )
    return _AVATAR_STYLES[style]


def write_case_svo(svo_path: Path, *, avatar_style: str = "human") -> tuple[str, ...]:
    """Write a `<CHID>.svo` containing the AVATARDEF for `avatar_style`.

    Smokeview scans the case directory for `<fdsprefix>.svo` after loading
    the global `objects.svo` and merges in any AVATARDEFs it finds, so this
    file ships the custom avatar without touching the global install.
    Overwrites any existing file of the same name. Returns the ordered
    tuple of SVO avatar names for the PROP block so the caller can pass
    the matching list to `patch_smv_file`.

    `avatar_style` picks which AVATARDEF to emit:
      - ``human``  — detailed humanoid (default; rotates with AZIMUTH)
      - ``arrow``  — sphere + red directional marker (rotation obvious)
      - ``sphere`` — single sphere (position-only sanity check)
    """
    body, svo_avatars = _resolve_avatar_style(avatar_style)
    Path(svo_path).write_text(body, encoding="utf-8")
    return svo_avatars


def patch_smv_file(
    smv_path: Path,
    prt5_path: Path,
    *,
    class_id: str,
    rgb: tuple[float, float, float],
    mesh_number: int = 1,
    n_quantities: int = 0,
    prop_id: str | None = None,
    svo_avatars: tuple[str, ...] = _DEFAULT_AVATARS,
    avatar_scale: float = _DEFAULT_AVATAR_SCALE,
) -> bool:
    """Append PROP + CLASS_OF_PARTICLES + PRT5 blocks to `smv_path`.

    The class is bound to an AVATARDEF from `objects.svo` (see
    `docs/smv-avatars.md`) via a ``<class_id> % % <prop_id>`` header
    parsed by Smokeview's `GetLabels` helper. The PROP block lists
    candidate SVO avatar names; Smokeview draws the first one found.

    If prior export blocks referencing the same `.prt5` or `prop_id`
    are present they are stripped first — a stale `CLASS_OF_PARTICLES`
    with a different `n_quantities` would desynchronise Smokeview's
    frame reader and segfault. Always returns True.
    """
    smv_path = Path(smv_path)
    existing = smv_path.read_text(encoding="utf-8")
    prt5_rel = Path(prt5_path).name

    r, g, b = rgb
    effective_prop_id = prop_id or f"{class_id}_props"
    existing = _strip_existing_agent_blocks(existing, prt5_rel, effective_prop_id)

    avatar_lines = "".join(f" {name}\n" for name in svo_avatars)
    # `human_fixed` ignores :SX :SY :SZ (its draw program hardcodes a 0.3
    # scale, rendering at ~1.89 m regardless). `human_altered_with_data`
    # honours `$SX $SY $SZ scalexyz` — set PROP defaults so avatars render
    # visibly large without per-particle size data. Its trunk sphere also
    # scales by `$W $D $H1 scalexyz`; W and H1 have no AVATARDEF default so
    # without explicit PROP values the trunk collapses to zero size, leaving
    # only a tiny floating head. W/H1 mirror the FDS+Evac body-diameter and
    # height-scale columns (evac.f90 DUMP_EVAC AP(:,2), AP(:,4)).
    # R/G/B map the class colour (0–1) onto the AVATARDEF's 0–255
    # `$R $G $B setrgb` trunk.
    s = float(avatar_scale)
    r255, g255, b255 = (int(round(c * 255)) for c in rgb)
    indep_vars = (
        ("W", 0.5),
        ("D", 0.2),
        ("H1", 1.0),
        ("SX", s),
        ("SY", s),
        ("SZ", s),
        ("R", r255),
        ("G", g255),
        ("B", b255),
    )
    indep_lines = "".join(f" {k}={v}\n" for k, v in indep_vars)
    prop_block = (
        f"PROP\n {effective_prop_id}\n  {len(svo_avatars)}\n{avatar_lines}"
        f"  {len(indep_vars)}\n{indep_lines}"
    )

    # Smokeview's CLASS_OF_PARTICLES parser recognises the AZIMUTH
    # shortlabel (readsmvfile.c GetLabels → col_azimuth) and rotates
    # the bound AVATARDEF by that per-particle value.
    quantity_lines = ""
    if n_quantities >= 1:
        quantity_lines = " body angle\n AZIMUTH\n deg\n"
    class_block = (
        f"CLASS_OF_PARTICLES\n"
        f" {class_id} % % {effective_prop_id}\n"
        f"      {r:.5f}      {g:.5f}      {b:.5f}\n"
        f"  {n_quantities}\n"
        f"{quantity_lines}"
        f"PRT5     {mesh_number}\n"
        f" {prt5_rel}\n"
        f"      1\n"
        f"      1\n"
    )

    suffix = "" if existing.endswith("\n") else "\n"
    smv_path.write_text(existing + suffix + prop_block + class_block, encoding="utf-8")
    return True


_PART_VIS_SMV_DEVICE = 4  # smv/Source/shared/datadefs.h: PART_SMV_DEVICE


def patch_ini_for_avatars(ini_path: Path, *, nclasses: int = 1) -> None:
    """Set `partclassdataVIS=4` so particle classes render as SVO avatars.

    Smokeview's default is `PART_POINTS` (=1). Without this override the
    particles render as point clouds even when the CLASS_OF_PARTICLES is
    bound to a PROP with an AVATARDEF. The value lives in the case
    `.ini` (`<CHID>.ini`) under the `partclassdataVIS` keyword; this
    helper creates or updates that section.
    """
    ini_path = Path(ini_path)
    block = f"partclassdataVIS\n {nclasses}\n" + f" {_PART_VIS_SMV_DEVICE}\n" * nclasses
    if not ini_path.exists():
        ini_path.write_text(block, encoding="utf-8")
        return
    text = ini_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        if lines[i].strip() == "partclassdataVIS" and i + 1 < len(lines):
            try:
                n = int(lines[i + 1].strip())
            except ValueError:
                n = 0
            out.append(lines[i])
            out.append(lines[i + 1])
            for _ in range(n):
                out.append(f" {_PART_VIS_SMV_DEVICE}")
            i += 2 + n
            replaced = True
            continue
        out.append(lines[i])
        i += 1
    if not replaced:
        out.append(block.rstrip("\n"))
    ini_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _find_smv(fds_dir: Path) -> Path:
    """Return the unique `.smv` file under `fds_dir`."""
    candidates = sorted(fds_dir.glob("*.smv"))
    if not candidates:
        raise FileNotFoundError(f"no .smv file found in {fds_dir}")
    if len(candidates) > 1:
        raise ValueError(
            f"multiple .smv files in {fds_dir}: {[c.name for c in candidates]}"
        )
    return candidates[0]


def export_agents_to_smv(
    fds_dir: str | Path,
    result: "ScenarioResult",
    *,
    z: float = 0.0,
    class_id: str = "Human",
    rgb: tuple[float, float, float] = (0.1, 0.4, 0.9),
    avatar_scale: float = _DEFAULT_AVATAR_SCALE,
    avatar_style: str = "human",
    with_azimuth: bool = False,
) -> Path:
    """Write `<CHID>_agents.prt5` next to the FDS output and patch `<CHID>.smv`.

    `avatar_style` picks the SVO avatar shape written to `<CHID>.svo`:
    ``human`` (default) draws the detailed humanoid; ``arrow`` draws a
    body sphere plus a red directional marker (clear visual check that
    per-particle AZIMUTH rotation is working); ``sphere`` draws a single
    plain sphere (position-only sanity check when debugging size issues).

    `with_azimuth` defaults to False for two reasons:

    1. Per-particle avatar rotation is not supported by current
       Smokeview — confirmed upstream on firemodels/smv#2597
       (https://github.com/firemodels/smv/issues/2597). The evac
       visualization code was removed when `&EVAC` left FDS, and
       reviving rotation would require adding AZIMUTH as an FDS
       particle quantity type first.
    2. Writing the quantity column also triggers a separate
       Smokeview bug in `IOpart.c::CreatePartBoundFile` —
       `FORTREAD_mv` -> `fread_mv` on a file-backed stream (the one
       `fopen_b(file, NULL, 0, "rb")` creates) always returns 0
       when the PRT5 has `numtypes > 0`, so the bounds scanner
       quits after frame 0, the derived `.sz` cache collapses
       `parti->ntimes` to 1, and playback sticks on frame 0.

    So the quantity gains a colorbar menu entry at the cost of
    broken playback and no rotation — not a good trade. Set to
    True if you explicitly want the colorbar entry and accept the
    stuck-playback symptom.

    Returns the path of the written `.prt5` file.
    """
    fds_dir = Path(fds_dir)
    smv_path = _find_smv(fds_dir)
    chid = smv_path.stem

    df = result.trajectory_dataframe()
    if with_azimuth and not {"ori_x", "ori_y"}.issubset(df.columns):
        raise ValueError(
            "with_azimuth=True requires ori_x/ori_y columns in the trajectory"
        )
    prt5_path = fds_dir / f"{chid}_agents.prt5"
    write_agent_prt5(
        prt5_path,
        df,
        frame_rate=result.frame_rate,
        z=z,
        with_azimuth=with_azimuth,
    )
    svo_avatars = write_case_svo(fds_dir / f"{chid}.svo", avatar_style=avatar_style)
    patch_smv_file(
        smv_path,
        prt5_path,
        class_id=class_id,
        rgb=rgb,
        n_quantities=1 if with_azimuth else 0,
        avatar_scale=avatar_scale,
        svo_avatars=svo_avatars,
    )
    patch_ini_for_avatars(fds_dir / f"{chid}.ini")
    return prt5_path
