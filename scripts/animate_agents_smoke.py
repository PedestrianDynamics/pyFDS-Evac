"""Animate agents walking through the smoke field they are actually reading.

    uv run python scripts/animate_agents_smoke.py \
        --smoke-history run_smoke.csv \
        --fds-dir "$SCIEBO/fds-evac-data/world100/fire_4p5MW" \
        --geometry assets/world_100/geometry.wkt \
        --out agents_smoke.mp4

The background is the extinction slice the run itself sampled -- same
``ExtinctionField``, same slice height -- so what you see is what the agents
saw, not a separate rendering of the FDS output. Agents come from the smoke
history CSV (``run.py --output-smoke-history``), which already carries per
sample ``(time_s, agent_id, x, y, speed_factor, extinction_per_m)``, so no
trajectory join is needed and the two layers cannot fall out of step.

Agents are coloured by ``speed_factor``: pale where smoke has slowed them,
saturated where they are walking freely. That is the coupling the picture is
meant to show -- the field on the left of the colourbar, its effect on the
people.

Sampling the field past the end of the FDS data clamps to the last frame, so
the animation stops at the last FDS time point by default rather than showing a
frozen field under moving agents. ``--past-fds-end`` overrides that.
"""

from __future__ import annotations

import argparse
import csv
import logging
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import animation  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

from pyfds_evac.core.smoke_speed import ExtinctionField  # noqa: E402

_logger = logging.getLogger(__name__)


def _read_history(path: Path) -> dict[float, list[tuple[float, float, float]]]:
    """Group the smoke history into frames: time -> [(x, y, speed_factor)]."""
    frames: dict[float, list[tuple[float, float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            frames[float(row["time_s"])].append(
                (
                    float(row["x"]),
                    float(row["y"]),
                    float(row.get("speed_factor") or 1.0),
                )
            )
    return frames


def _draw_deck(ax, config: Path | None) -> None:
    """Outline where agents come from and where they are trying to get to.

    Without these the animation shows dots on a smoke field and leaves the
    reader to guess which blob is a door -- and the whole question the picture
    answers is which exit the crowd chose.
    """
    if config is None:
        return
    import json

    from shapely.geometry import Polygon

    raw = json.loads(config.read_text(encoding="utf-8"))
    for name, spec in (raw.get("distributions") or {}).items():
        coords = spec.get("coordinates")
        if not coords:
            continue
        poly = Polygon(coords)
        ax.fill(
            *poly.exterior.xy,
            facecolor="none",
            edgecolor="deepskyblue",
            lw=1.8,
            ls="--",
            zorder=4,
        )
        ax.annotate(
            "spawn",
            (poly.centroid.x, poly.centroid.y),
            color="deepskyblue",
            fontsize=9,
            ha="center",
            va="center",
            zorder=5,
        )
        del name
    for name, spec in (raw.get("exits") or {}).items():
        coords = spec.get("coordinates")
        if not coords:
            continue
        c = Polygon(coords).centroid
        ax.plot(
            [c.x],
            [c.y],
            marker="s",
            ms=10,
            mfc="white",
            mec="black",
            mew=1.4,
            zorder=6,
            clip_on=False,
        )
        # Exits sit on the domain boundary, so the label is offset *inward*: a
        # fixed offset leaves half of them outside the axes and clipped away.
        xa, xb = ax.get_xlim()
        ya, yb = ax.get_ylim()
        dx = -22 if c.x > 0.5 * (xa + xb) else 22
        dy = -16 if c.y > 0.5 * (ya + yb) else 16
        ax.annotate(
            name.replace("jps-exits_", "E"),
            (c.x, c.y),
            textcoords="offset points",
            xytext=(dx, dy),
            ha="center",
            va="center",
            fontsize=12,
            fontweight="bold",
            color="white",
            zorder=6,
            clip_on=False,
        )


def _walkable(geometry: Path | None):
    if geometry is None:
        return None
    from shapely import wkt

    return wkt.loads(geometry.read_text(encoding="utf-8").strip())


def _bounds(walkable, frames) -> tuple[float, float, float, float]:
    if walkable is not None:
        return walkable.bounds
    xs = [x for f in frames.values() for x, _, _ in f]
    ys = [y for f in frames.values() for _, y, _ in f]
    pad = 2.0
    return (
        float(min(xs)) - pad,
        float(min(ys)) - pad,
        float(max(xs)) + pad,
        float(max(ys)) + pad,
    )


def _field_grid(field, time_s, xs, ys):
    return np.array([[field.sample_extinction(time_s, x, y) for x in xs] for y in ys])


def _last_fds_time(field) -> float | None:
    """When the FDS data runs out. Past it the sampler clamps to the last frame."""
    sampler = getattr(field, "_sampler", None)
    times = getattr(getattr(sampler, "_slice", None), "times", None)
    if times is None or len(times) == 0:
        return None
    return float(np.asarray(times)[-1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke-history", type=Path, required=True)
    ap.add_argument("--fds-dir", required=True)
    ap.add_argument(
        "--geometry", type=Path, help="walkable-area WKT, drawn as backdrop"
    )
    ap.add_argument(
        "--config",
        type=Path,
        help="deck config.json; draws the spawn areas and labels the exits",
    )
    ap.add_argument("--out", "-o", type=Path, default=Path("agents_smoke.mp4"))
    ap.add_argument("--slice-height", type=float, default=2.0)
    ap.add_argument("--cell-size", type=float, default=0.5, help="field raster [m]")
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--stride", type=int, default=1, help="use every Nth frame")
    ap.add_argument("--kmax", type=float, help="colour ceiling for K [1/m]")
    ap.add_argument(
        "--past-fds-end",
        action="store_true",
        help="keep animating after the FDS data ends (the field then freezes)",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    frames = _read_history(args.smoke_history)
    if not frames:
        raise SystemExit(f"no rows in {args.smoke_history}")
    field = ExtinctionField.from_fds(args.fds_dir, slice_height_m=args.slice_height)

    times = sorted(frames)
    end = _last_fds_time(field)
    if end is not None and not args.past_fds_end:
        kept = [t for t in times if t <= end]
        if len(kept) < len(times):
            _logger.info(
                "FDS data ends at %.1f s; stopping there (%d of %d frames). "
                "--past-fds-end to continue with a frozen field.",
                end,
                len(kept),
                len(times),
            )
        times = kept or times
    times = times[:: max(1, args.stride)]

    walkable = _walkable(args.geometry)
    x0, y0, x1, y1 = _bounds(walkable, frames)
    xs = np.arange(x0, x1 + args.cell_size, args.cell_size)
    ys = np.arange(y0, y1 + args.cell_size, args.cell_size)

    kmax = args.kmax
    if kmax is None:
        # A percentile, not the maximum: the burner cell is one or two orders
        # above everything else, and scaling to it renders the whole hall as a
        # single flat colour with no gradient to read.
        probe = times[len(times) // 2 :: max(1, len(times) // 5)] or times[-1:]
        pooled = np.concatenate([_field_grid(field, t, xs, ys).ravel() for t in probe])
        kmax = max(float(np.percentile(pooled, 99.0)), 0.1)
        _logger.info(
            "colour ceiling K = %.2f /m (99th percentile; field peaks at %.1f)",
            kmax,
            float(pooled.max()),
        )

    fig, ax = plt.subplots(
        figsize=(11, 10 * (y1 - y0) / max(x1 - x0, 1e-9)), layout="constrained"
    )
    ax.set_aspect("equal")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")

    im = ax.imshow(
        _field_grid(field, times[0], xs, ys),
        origin="lower",
        extent=(x0, x1, y0, y1),
        cmap="inferno_r",
        norm=Normalize(0.0, kmax),
        interpolation="bilinear",
        zorder=0,
    )
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("extinction K [1/m]   (Jin sight S = 3/K)")

    if walkable is not None:
        # Obstacles are filled, not outlined. The extinction field is zero
        # inside them, so an unfilled obstacle reads as the clearest air in the
        # room -- the exact opposite of what it is.
        for geom in getattr(walkable, "geoms", [walkable]):
            ax.plot(*geom.exterior.xy, color="0.15", lw=1.2, zorder=2)
            for hole in geom.interiors:
                ax.fill(*hole.xy, color="0.55", zorder=2, lw=0)
                ax.plot(*hole.xy, color="0.15", lw=0.6, zorder=2)

    _draw_deck(ax, args.config)

    scat = ax.scatter(
        [],
        [],
        s=42,
        c=[],
        cmap="winter",
        norm=Normalize(0.0, 1.0),
        edgecolors="white",
        linewidths=0.6,
        zorder=3,
    )
    cb2 = fig.colorbar(scat, ax=ax, fraction=0.035, pad=0.02)
    cb2.set_label("agent speed factor (1 = unimpeded)")
    title = ax.set_title("")

    def update(t):
        im.set_data(_field_grid(field, t, xs, ys))
        pts = frames[t]
        scat.set_offsets(
            np.array([[x, y] for x, y, _ in pts]) if pts else np.empty((0, 2))
        )
        scat.set_array(np.array([sf for _, _, sf in pts]))
        title.set_text(f"t = {t:6.1f} s     {len(pts)} agents inside")
        return im, scat, title

    anim = animation.FuncAnimation(fig, update, frames=times, blit=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = (
        animation.FFMpegWriter(fps=args.fps)
        if args.out.suffix == ".mp4"
        else animation.PillowWriter(fps=args.fps)
    )
    anim.save(str(args.out), writer=writer, dpi=110)
    _logger.info("wrote %s (%d frames)", args.out, len(times))


if __name__ == "__main__":
    main()
