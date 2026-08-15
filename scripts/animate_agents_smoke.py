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
from bisect import bisect_left
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


def _read_history(path: Path) -> dict[str, list[tuple[float, float, float, float]]]:
    """Per-agent tracks: agent -> [(time, x, y, speed_factor)], time-ordered.

    Kept per agent rather than per frame so positions can be interpolated
    between samples. The history is written once a second; showing one sample
    per frame plays the run back at twelve times life, and at that rate a
    1.3 m/s walk and a 1.0 m/s crawl look identical -- which defeats the point
    of colouring agents by how much the smoke has slowed them.
    """
    tracks: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            tracks[row.get("agent_id", "0")].append(
                (
                    float(row["time_s"]),
                    float(row["x"]),
                    float(row["y"]),
                    float(row.get("speed_factor") or 1.0),
                )
            )
    for track in tracks.values():
        track.sort()
    return tracks


def _agents_at(tracks, t: float) -> list[tuple[float, float, float]]:
    """Where every agent is at *t*, interpolated between its samples."""
    out = []
    for track in tracks.values():
        if not track or t < track[0][0] or t > track[-1][0]:
            continue
        i = bisect_left([p[0] for p in track], t)
        if i == 0:
            _, x, y, sf = track[0]
        else:
            t0, x0, y0, s0 = track[i - 1]
            t1, x1, y1, s1 = track[min(i, len(track) - 1)]
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            x, y, sf = x0 + f * (x1 - x0), y0 + f * (y1 - y0), s0 + f * (s1 - s0)
        out.append((x, y, sf))
    return out


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
        inward_x = c.x <= 0.5 * (xa + xb)
        dx = 22 if inward_x else -22
        dy = -16 if c.y > 0.5 * (ya + yb) else 16
        ax.annotate(
            name.replace("jps-exits_", "E"),
            (c.x, c.y),
            textcoords="offset points",
            xytext=(dx, dy),
            # Anchored on the side the label runs toward, not centred: an exit
            # on the domain edge with a long name is otherwise half outside the
            # frame however much padding the axes get.
            ha="left" if inward_x else "right",
            va="center",
            fontsize=12,
            fontweight="bold",
            color="white",
            zorder=6,
            clip_on=False,
        )


def _masked_cmap(name: str):
    """The field colormap, with everything outside the building drawn as wall."""
    cmap = matplotlib.colormaps[name].copy()
    cmap.set_bad("0.55")
    return cmap


def _walkable(geometry: Path | None):
    if geometry is None:
        return None
    from shapely import wkt

    return wkt.loads(geometry.read_text(encoding="utf-8").strip())


def _bounds(walkable, tracks) -> tuple[float, float, float, float]:
    if walkable is not None:
        return walkable.bounds
    xs = [x for tr in tracks.values() for _, x, _, _ in tr]
    ys = [y for tr in tracks.values() for _, _, y, _ in tr]
    pad = 2.0
    return (
        float(min(xs)) - pad,
        float(min(ys)) - pad,
        float(max(xs)) + pad,
        float(max(ys)) + pad,
    )


def _field_grid(field, time_s, xs, ys, outside=None):
    grid = np.array([[field.sample_extinction(time_s, x, y) for x in xs] for y in ys])
    if outside is not None:
        grid[outside] = np.nan
    return grid


def _outside_mask(walkable, xs, ys):
    """Cells that are not part of the building at all.

    Without this the ground outside the walkable polygon samples as K = 0 and
    renders as the clearest air in the frame -- so an L-shaped corridor reads
    as a small dark building floating in a large safe room, which is the
    opposite of the truth. Obstacles inside the polygon are filled separately;
    this is everything beyond its outer boundary.
    """
    if walkable is None:
        return None
    from matplotlib.path import Path as MplPath

    gx, gy = np.meshgrid(xs, ys)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    inside = np.zeros(len(pts), dtype=bool)
    for geom in getattr(walkable, "geoms", [walkable]):
        inside |= MplPath(np.asarray(geom.exterior.coords)).contains_points(pts)
    return ~inside.reshape(gx.shape)


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
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument(
        "--playback",
        type=float,
        default=1.0,
        help="seconds of simulation per second of video (1 = real time)",
    )
    ap.add_argument("--kmax", type=float, help="colour ceiling for K [1/m]")
    ap.add_argument(
        "--speed-min",
        type=float,
        help="lower end of the agent colour scale (default: the run's own minimum)",
    )
    ap.add_argument(
        "--past-fds-end",
        action="store_true",
        help="keep animating after the FDS data ends (the field then freezes)",
    )
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    tracks = _read_history(args.smoke_history)
    if not tracks:
        raise SystemExit(f"no rows in {args.smoke_history}")
    field = ExtinctionField.from_fds(args.fds_dir, slice_height_m=args.slice_height)

    sample_times = sorted({t for tr in tracks.values() for t, _, _, _ in tr})
    end = _last_fds_time(field)
    if end is not None and not args.past_fds_end:
        kept = [t for t in sample_times if t <= end]
        if len(kept) < len(sample_times):
            _logger.info(
                "FDS data ends at %.1f s; stopping there (%d of %d frames). "
                "--past-fds-end to continue with a frozen field.",
                end,
                len(kept),
                len(sample_times),
            )
        sample_times = kept or sample_times
    # Frame times are chosen from the wall clock, not from the samples, so the
    # video runs at a stated rate rather than at whatever the logging interval
    # happens to be.
    step = args.playback / max(args.fps, 1)
    n_frames = max(2, int((sample_times[-1] - sample_times[0]) / step) + 1)
    times = [sample_times[0] + k * step for k in range(n_frames)]
    _logger.info(
        "%d frames at %d fps: %.3g s of simulation per second of video",
        len(times),
        args.fps,
        args.playback,
    )

    walkable = _walkable(args.geometry)
    x0, y0, x1, y1 = _bounds(walkable, tracks)
    # Exits sit on the domain boundary and their labels are drawn outside it,
    # so the axes need room or the text is cut off at the frame edge.
    pad = 0.06 * max(x1 - x0, y1 - y0)
    xs = np.arange(x0, x1 + args.cell_size, args.cell_size)
    ys = np.arange(y0, y1 + args.cell_size, args.cell_size)

    outside = _outside_mask(walkable, xs, ys)

    kmax = args.kmax
    if kmax is None:
        # A percentile, not the maximum: the burner cell is one or two orders
        # above everything else, and scaling to it renders the whole hall as a
        # single flat colour with no gradient to read.
        probe = times[len(times) // 2 :: max(1, len(times) // 5)] or times[-1:]
        pooled = np.concatenate(
            [_field_grid(field, t, xs, ys, outside).ravel() for t in probe]
        )
        kmax = max(float(np.nanpercentile(pooled, 99.0)), 0.1)
        _logger.info(
            "colour ceiling K = %.2f /m (99th percentile; field peaks at %.1f)",
            kmax,
            float(np.nanmax(pooled)),
        )

    fig, ax = plt.subplots(
        figsize=(11, 10 * (y1 - y0) / max(x1 - x0, 1e-9)), layout="constrained"
    )
    ax.set_aspect("equal")
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")

    im = ax.imshow(
        _field_grid(field, times[0], xs, ys, outside),
        origin="lower",
        extent=(x0, x1, y0, y1),
        cmap=_masked_cmap("inferno_r"),
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

    # Scaled to the spread that actually occurs, not to [0, 1]. Routing steers
    # agents around the heaviest smoke, so speed factors sit in a narrow band
    # near 1 -- measured 0.83-1.00 on l_corridor and 0.87-1.00 on world100 --
    # and a fixed 0-1 norm renders every agent the same colour, which reads as
    # "smoke had no effect" when the truth is "the model avoided the worst of
    # it". The floor is padded so a run with no variation does not divide by
    # zero and does not exaggerate noise.
    sf_all = [sf for tr in tracks.values() for _, _, _, sf in tr]
    sf_lo = args.speed_min if args.speed_min is not None else min(sf_all, default=0.0)
    if 1.0 - sf_lo < 0.02:
        sf_lo = 0.98
    scat = ax.scatter(
        [],
        [],
        s=42,
        c=[],
        cmap="winter",
        norm=Normalize(sf_lo, 1.0),
        edgecolors="white",
        linewidths=0.6,
        zorder=3,
    )
    cb2 = fig.colorbar(scat, ax=ax, fraction=0.035, pad=0.02)
    cb2.set_label(f"agent speed factor ({sf_lo:.2f} = slowest here, 1 = unimpeded)")
    title = ax.set_title("")

    # The field is only written once per history sample, so grids are computed
    # per sample and reused across the frames that interpolate between them --
    # otherwise real-time playback would resample the whole grid 24 times a
    # second for a field that changes once.
    grid_cache: dict[float, np.ndarray] = {}

    def _grid_for(t):
        key = min(sample_times, key=lambda s: abs(s - t))
        if key not in grid_cache:
            grid_cache[key] = _field_grid(field, key, xs, ys, outside)
        return grid_cache[key]

    def update(t):
        im.set_data(_grid_for(t))
        pts = _agents_at(tracks, t)
        scat.set_offsets(
            np.array([[x, y] for x, y, _ in pts]) if pts else np.empty((0, 2))
        )
        scat.set_array(np.array([sf for _, _, sf in pts]))
        rate = "real time" if args.playback == 1 else f"{args.playback:g}x real time"
        title.set_text(f"t = {t:6.1f} s     {len(pts)} agents inside     ({rate})")
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
