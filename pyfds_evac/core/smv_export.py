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
     human_fixed
     ellipsoid
      1
     D=0.2

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


_DEFAULT_AVATARS = ("human_fixed", "ellipsoid")


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
    prop_block = (
        f"PROP\n {effective_prop_id}\n  {len(svo_avatars)}\n{avatar_lines}  1\n D=0.2\n"
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
    z: float = 1.0,
    class_id: str = "Human",
    rgb: tuple[float, float, float] = (0.1, 0.4, 0.9),
) -> Path:
    """Write `<CHID>_agents.prt5` next to the FDS output and patch `<CHID>.smv`.

    Returns the path of the written `.prt5` file.
    """
    fds_dir = Path(fds_dir)
    smv_path = _find_smv(fds_dir)
    chid = smv_path.stem

    df = result.trajectory_dataframe()
    with_azimuth = {"ori_x", "ori_y"}.issubset(df.columns)
    prt5_path = fds_dir / f"{chid}_agents.prt5"
    write_agent_prt5(
        prt5_path,
        df,
        frame_rate=result.frame_rate,
        z=z,
        with_azimuth=with_azimuth,
    )
    patch_smv_file(
        smv_path,
        prt5_path,
        class_id=class_id,
        rgb=rgb,
        n_quantities=1 if with_azimuth else 0,
    )
    return prt5_path
