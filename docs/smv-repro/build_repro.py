"""Build a minimal standalone Smokeview case demonstrating the per-particle
AZIMUTH rotation issue.

Uses a 20-second FDS run (`repro.fds`, no fire, no smoke, just four stub
walls) to produce a well-formed `.smv` with proper mesh/obstacle/time
info, then layers a synthetic agent trajectory on top: three agents
walking concentric circles around the mesh centre so their per-particle
`AZIMUTH` quantity (written into the PRT5) sweeps 0–360° every few
seconds. If per-particle rotation worked, the red marker on the
`agent_arrow` AVATARDEF would orbit around each body. In current
Smokeview (6.10.x) the marker is rigidly offset in world +X for every
agent and every frame regardless of AZIMUTH.

Run from the project root (FDS must be on PATH):

    cd docs/smv-repro/case && fds repro.fds
    cd ../../../
    uv run python docs/smv-repro/build_repro.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from pyfds_evac.core.smv_export import (
    patch_ini_for_avatars,
    patch_smv_file,
    write_agent_prt5,
    write_case_svo,
)

CASE_DIR = Path(__file__).parent / "case"
CHID = "repro"
FRAME_RATE = 10
DURATION_S = 20


def build_trajectory() -> pd.DataFrame:
    """Three agents walking concentric circles around (5, 5), each with
    a different angular speed so their AZIMUTHs sweep at obviously
    different rates."""
    rows = []
    cx, cy = 5.0, 5.0
    cfg = [
        (1, 1.5, 1.0),
        (2, 2.5, 0.6),
        (3, 3.5, 0.4),
    ]
    for frame in range(FRAME_RATE * DURATION_S + 1):
        t = frame / FRAME_RATE
        for agent_id, r, omega in cfg:
            theta = omega * t
            x = cx + r * np.cos(theta)
            y = cy + r * np.sin(theta)
            vx = -np.sin(theta)
            vy = np.cos(theta)
            rows.append((frame, agent_id, x, y, vx, vy))
    return pd.DataFrame(rows, columns=["frame", "id", "x", "y", "ori_x", "ori_y"])


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-azimuth",
        action="store_true",
        help="Write per-particle AZIMUTH (deg) as a PRT5 quantity column. "
        "Off by default — triggers a Smokeview 6.10.x CreatePartBoundFile "
        "bug (`fread_mv` on file-backed streams) that sticks playback on "
        "frame 0. Turn on if you want to reproduce that bug directly.",
    )
    parser.add_argument(
        "--avatar-style",
        default="arrow",
        choices=("arrow", "human", "sphere"),
        help="Which AVATARDEF to emit into repro.svo. `arrow` (default) "
        "makes the rotation question visually obvious — a blue body with "
        "a red marker in local +X that should orbit as the agent turns. "
        "`human` uses the full tan-headed blue-trunked humanoid figure; "
        "`sphere` is a plain body with no facing direction.",
    )
    parser.add_argument(
        "--case-dir",
        default=None,
        help="Output case directory (defaults to docs/smv-repro/case). "
        "If it does not yet contain repro.smv, the FDS-produced support "
        "files are copied from docs/smv-repro/case.",
    )
    args = parser.parse_args()

    case_dir = Path(args.case_dir) if args.case_dir else CASE_DIR
    if case_dir != CASE_DIR and not (case_dir / f"{CHID}.smv").exists():
        import shutil

        case_dir.mkdir(parents=True, exist_ok=True)
        for name in (f"{CHID}.smv", f"{CHID}.fds", f"{CHID}.s3d_dummy"):
            src = CASE_DIR / name
            if src.exists():
                shutil.copy2(src, case_dir / name)

    smv_path = case_dir / f"{CHID}.smv"
    if not smv_path.exists():
        raise SystemExit(
            f"no {smv_path} found — run `cd {CASE_DIR} && fds repro.fds` "
            "first to generate the supporting .smv"
        )

    prt5_path = case_dir / f"{CHID}_agents.prt5"
    svo_path = case_dir / f"{CHID}.svo"
    ini_path = case_dir / f"{CHID}.ini"

    df = build_trajectory()
    # Default `with_azimuth=False` / `n_quantities=0`: the exporter normally
    # writes AZIMUTH as a per-particle quantity, but Smokeview's
    # `CreatePartBoundFile` breaks after frame 0 whenever `numtypes > 0`
    # (`fread_mv` fails on file-backed streams — see README for the trace),
    # which collapses the bounds/size cache to one frame and stops
    # playback. For the shipped repro we drop the quantity so frames
    # play and the rotation question is isolated from that bug. Pass
    # `--with-azimuth` to regenerate with the quantity column (and hit
    # the stuck-at-frame-0 playback).
    write_agent_prt5(
        prt5_path, df, frame_rate=FRAME_RATE, z=0.0, with_azimuth=args.with_azimuth
    )
    n_quantities = 1 if args.with_azimuth else 0
    svo_avatars = write_case_svo(svo_path, avatar_style=args.avatar_style)
    patch_smv_file(
        smv_path,
        prt5_path,
        class_id="Human",
        rgb=(0.1, 0.4, 0.9),
        n_quantities=n_quantities,
        svo_avatars=svo_avatars,
    )
    patch_ini_for_avatars(ini_path, nclasses=1)

    # Fresh PRT5 → stale `.bnd`/`.sz` caches. Delete them so Smokeview
    # rebuilds on first load.
    for ext in (".bnd", ".sz"):
        stale = prt5_path.with_suffix(prt5_path.suffix + ext)
        stale.unlink(missing_ok=True)

    print(
        f"Ready (numtypes={n_quantities}, avatar={args.avatar_style}). Open in Smokeview:"
    )
    print(f"  cd {case_dir}")
    print(f"  smokeview {CHID}.smv")


if __name__ == "__main__":
    main()
