"""Plot agent trajectories coloured by desired walking speed.

Reads the extended FED history CSV (``run.py --output-fed-history``)
which carries per-sample ``(time_s, agent_id, x, y, desired_speed)``.
Each agent is rendered as a polyline with per-segment colour from the
``RdBu`` colormap: red = slow, blue = fast.  Optionally overlays the
walkable geometry polygon loaded from a JuPedSim SQLite trajectory
file via pedpy.

Examples::

    uv run python scripts/plot_trajectories_by_speed.py fed.csv \\
        --sqlite demo3.sqlite --output trajectories.png

    uv run python scripts/plot_trajectories_by_speed.py fed.csv \\
        --sqlite demo3.sqlite --agents 7,8,43 --output trajs_select.png
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath


def _read_trajectories(csv_path: Path) -> dict[int, dict[str, list[float]]]:
    """Group (x, y, desired_speed) by agent id in sample order."""
    by_agent: dict[int, dict[str, list[float]]] = {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if "desired_speed" not in fieldnames:
            raise SystemExit(
                f"{csv_path} has no 'desired_speed' column; re-run with the "
                "updated pyfds_evac to produce speed columns."
            )
        for row in reader:
            agent_id = int(row["agent_id"])
            series = by_agent.setdefault(agent_id, {"t": [], "x": [], "y": [], "v": []})
            series["t"].append(float(row["time_s"]))
            series["x"].append(float(row["x"]))
            series["y"].append(float(row["y"]))
            series["v"].append(float(row["desired_speed"]))
    return by_agent


def _walkable_patch_from_sqlite(sqlite_path: Path) -> PathPatch | None:
    """Build a filled-with-holes patch for the walkable area from a JPS sqlite.

    Uses pedpy's ``load_walkable_area_from_jupedsim_sqlite`` so version 1
    and 2 trajectory files are both handled.  Returns ``None`` if pedpy
    is not installed.
    """
    try:
        from pedpy.io.trajectory_loader import load_walkable_area_from_jupedsim_sqlite
    except ModuleNotFoundError:
        print(
            f"Warning: pedpy not installed, skipping walkable-area overlay "
            f"for {sqlite_path}"
        )
        return None

    walkable = load_walkable_area_from_jupedsim_sqlite(sqlite_path)
    polygon = walkable.polygon
    vertices: list[tuple[float, float]] = []
    codes: list[int] = []

    def _add_ring(ring_coords: list[tuple[float, float]]) -> None:
        vertices.append(ring_coords[0])
        codes.append(int(MPath.MOVETO))
        for xy in ring_coords[1:]:
            vertices.append(xy)
            codes.append(int(MPath.LINETO))
        vertices.append(ring_coords[0])
        codes.append(int(MPath.CLOSEPOLY))

    _add_ring(list(polygon.exterior.coords))
    for interior in polygon.interiors:
        _add_ring(list(interior.coords))

    path = MPath(vertices, codes)
    return PathPatch(
        path, facecolor="#f5f5f5", edgecolor="#555", linewidth=0.9, zorder=0
    )


def _parse_agents(raw: str | None) -> set[int] | None:
    """Parse a comma-separated agent-id list, or ``None`` for all agents."""
    if raw is None:
        return None
    return {int(token) for token in raw.split(",") if token.strip()}


def _build_figure(
    by_agent: dict[int, dict[str, list[float]]],
    *,
    agents_filter: set[int] | None,
    walkable_patch: PathPatch | None,
    vmax: float | None,
    title: str,
    linewidth: float,
    alpha: float,
) -> Figure:
    """Draw per-agent polylines coloured by desired speed."""
    if agents_filter is not None:
        by_agent = {aid: v for aid, v in by_agent.items() if aid in agents_filter}
    if not by_agent:
        raise SystemExit("No trajectories to plot after filtering.")

    all_v = np.concatenate([np.asarray(s["v"], dtype=float) for s in by_agent.values()])
    effective_vmax = float(vmax) if vmax is not None else float(np.nanmax(all_v))
    if effective_vmax <= 0.0:
        effective_vmax = 1.0  # avoid zero-range cmap

    fig, ax = plt.subplots(figsize=(9, 6), constrained_layout=True)

    if walkable_patch is not None:
        ax.add_patch(walkable_patch)

    # Red = slow, blue = fast.  RdBu goes red -> white -> blue.
    cmap = plt.get_cmap("RdBu")

    for agent_id in sorted(by_agent):
        series = by_agent[agent_id]
        xs = np.asarray(series["x"])
        ys = np.asarray(series["y"])
        vs = np.asarray(series["v"])
        if xs.size < 2:
            ax.scatter(
                xs, ys, c=vs, cmap=cmap, vmin=0.0, vmax=effective_vmax, s=8, alpha=alpha
            )
            continue
        segments = np.stack(
            [
                np.column_stack((xs[:-1], ys[:-1])),
                np.column_stack((xs[1:], ys[1:])),
            ],
            axis=1,
        )
        seg_v = 0.5 * (vs[:-1] + vs[1:])  # colour each segment by mean speed
        lc = LineCollection(
            list(segments),
            cmap=cmap,
            norm=Normalize(0.0, effective_vmax),
            linewidth=linewidth,
            alpha=alpha,
        )
        lc.set_array(seg_v)
        ax.add_collection(lc)

        # Mark start/end for small agent sets
        if agents_filter is not None and len(agents_filter) <= 12:
            ax.plot(xs[0], ys[0], "o", color="white", mec="black", ms=5, zorder=3)
            ax.plot(xs[-1], ys[-1], "s", color="black", mec="white", ms=5, zorder=3)
            ax.text(xs[-1], ys[-1], f" {agent_id}", fontsize=7, zorder=4)

    # Add a colorbar using a dummy mappable (so it works even when every
    # agent was rendered via LineCollection rather than scatter).
    dummy = plt.cm.ScalarMappable(cmap=cmap, norm=Normalize(0.0, effective_vmax))
    dummy.set_array([])
    cbar = fig.colorbar(dummy, ax=ax)
    cbar.set_label("desired speed (m/s)")

    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(title)
    ax.autoscale_view()
    return fig


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="FED history CSV from run.py")
    parser.add_argument(
        "--sqlite",
        type=Path,
        help="JuPedSim SQLite trajectory file; its walkable area is drawn as "
        "backdrop via pedpy.load_walkable_area_from_jupedsim_sqlite",
    )
    parser.add_argument(
        "--agents",
        help="Comma-separated agent ids to include (default: all).",
    )
    parser.add_argument(
        "--vmax",
        type=float,
        help="Upper bound for the colormap (default: max desired_speed in data)",
    )
    parser.add_argument(
        "--title",
        default="Trajectories coloured by desired speed",
    )
    parser.add_argument(
        "--linewidth",
        type=float,
        default=0.5,
        help="Line width for trajectory polylines (default: 0.5)",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.4,
        help="Alpha transparency for trajectories (default: 0.4)",
    )
    parser.add_argument("--output", type=Path, help="Write PNG here instead of showing")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    by_agent = _read_trajectories(args.csv)
    walkable_patch = (
        _walkable_patch_from_sqlite(args.sqlite) if args.sqlite is not None else None
    )
    fig = _build_figure(
        by_agent,
        agents_filter=_parse_agents(args.agents),
        walkable_patch=walkable_patch,
        vmax=args.vmax,
        title=args.title,
        linewidth=args.linewidth,
        alpha=args.alpha,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=150, bbox_inches="tight")
        print(f"Wrote {args.output}")
    else:
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
