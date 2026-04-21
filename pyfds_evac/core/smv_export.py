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
) -> None:
    """Serialize `df` to an FDS `.prt5` particle file.

    `df` must have columns `frame`, `id`, `x`, `y`. Frames with zero agents
    are skipped mid-stream (would falsely terminate `prt5parser`). A single
    `n_points=0` frame is appended at the end as a clean terminator.
    """
    import numpy as np

    required = {"frame", "id", "x", "y"}
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

    with prt5_path.open("wb") as fh:
        _fortran_record(fh, struct.pack("<i", 1))
        _fortran_record(fh, struct.pack("<i", _PRT5_VERSION))
        _fortran_record(fh, struct.pack("<i", 1))
        _fortran_record(fh, struct.pack("<ii", 0, 0))

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

        t_end = float(last_frame) / float(frame_rate)
        _fortran_record(fh, struct.pack("<f", t_end))
        _fortran_record(fh, struct.pack("<i", 0))


def _prt5_block_present(smv_text: str, prt5_basename: str) -> bool:
    """Return True if the smv already references `prt5_basename` under a PRT5 line."""
    lines = smv_text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("PRT5"):
            continue
        if i + 1 < len(lines) and lines[i + 1].strip() == prt5_basename:
            return True
    return False


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

    Idempotent: returns False if a PRT5 entry for this `.prt5` file
    already exists, True if a new block was appended.
    """
    smv_path = Path(smv_path)
    existing = smv_path.read_text(encoding="utf-8")
    prt5_rel = Path(prt5_path).name

    if _prt5_block_present(existing, prt5_rel):
        return False

    r, g, b = rgb
    effective_prop_id = prop_id or f"{class_id}_props"

    avatar_lines = "".join(f" {name}\n" for name in svo_avatars)
    prop_block = (
        f"PROP\n {effective_prop_id}\n  {len(svo_avatars)}\n{avatar_lines}  1\n D=0.2\n"
    )

    class_block = (
        f"CLASS_OF_PARTICLES\n"
        f" {class_id} % % {effective_prop_id}\n"
        f"      {r:.5f}      {g:.5f}      {b:.5f}\n"
        f"  {n_quantities}\n"
        f"PRT5     {mesh_number}\n"
        f" {prt5_rel}\n"
        f"      1\n"
        f"      1\n"
    )

    suffix = "" if existing.endswith("\n") else "\n"
    with smv_path.open("a", encoding="utf-8") as fh:
        fh.write(suffix + prop_block + class_block)
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
    prt5_path = fds_dir / f"{chid}_agents.prt5"
    write_agent_prt5(
        prt5_path,
        df,
        frame_rate=result.frame_rate,
        z=z,
    )
    patch_smv_file(
        smv_path,
        prt5_path,
        class_id=class_id,
        rgb=rgb,
    )
    return prt5_path
