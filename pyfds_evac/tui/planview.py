"""The live plan view: walls, exits, signs, agents and smoke in the terminal.

Draws only what the runner sent: the :class:`~pyfds_evac.config.events.PlanEvent`
(geometry, exits, signs, how smoke is modelled) and the latest
:class:`~pyfds_evac.config.events.FrameEvent` (agents, per-exit counts, the
coarse extinction grid). Design: ``studies/tui_visual_design.md`` §5.

numpy and shapely load when the first plan arrives, never at start-up.
"""

from __future__ import annotations

import math
import os
from typing import Any

from rich.style import Style
from rich.text import Text
from textual.widget import Widget

from pyfds_evac.config import events

from .theme import K_EDGES, RAMP_DARK, RAMP_LIGHT, SHADES, agent_colour, no_color

HEAVY = {  # (up, down, left, right) -> heavy box glyph
    (0, 0, 1, 1): "━",
    (1, 1, 0, 0): "┃",
    (0, 1, 0, 1): "┏",
    (0, 1, 1, 0): "┓",
    (1, 0, 0, 1): "┗",
    (1, 0, 1, 0): "┛",
    (1, 1, 0, 1): "┣",
    (1, 1, 1, 0): "┫",
    (0, 1, 1, 1): "┳",
    (1, 0, 1, 1): "┻",
    (1, 1, 1, 1): "╋",
    (0, 0, 1, 0): "╸",
    (0, 0, 0, 1): "╺",
    (1, 0, 0, 0): "╹",
    (0, 1, 0, 0): "╻",
    (0, 0, 0, 0): "■",
}
NOT_AVAILABLE = "plan not available"


def exit_label(exit_id: str) -> str:
    return exit_id.removeprefix("exit_")


def legend_text(plan: events.PlanEvent | None) -> str:
    """The smoke part of the legend in words (spec §10 honesty rules)."""
    if plan is None:
        return NOT_AVAILABLE
    if plan.smoke_mode == events.SMOKE_NONE:
        return "no fire input"
    if plan.smoke_mode == events.SMOKE_CONSTANT:
        return f"uniform K = {plan.smoke_k:g} 1/m (constant)"
    where = (
        f"FDS slice z = {plan.smoke_z_m:.1f} m"
        if plan.smoke_z_m is not None
        else "FDS slice"
    )
    if plan.smoke_mode == events.SMOKE_BLIND:
        return f"{where}; smoke not felt by agents (smoke-blind)"
    return where


class _Raster:
    """The plan rasterised for one widget size (cells: rows x columns)."""

    def __init__(self, plan: events.PlanEvent, width: int, height: int) -> None:
        import numpy as np
        import shapely
        from shapely.geometry import MultiPolygon, Polygon

        polys = [Polygon(ext, list(holes)) for ext, holes in plan.walkable]
        geom = MultiPolygon(polys) if len(polys) > 1 else polys[0]
        x0, y0, x1, y1 = plan.extent
        s = max((x1 - x0) / max(width - 2, 1), (y1 - y0) / max(2 * (height - 2), 1))
        s = s if s > 0 else 1.0
        nc = min(width, int(math.ceil((x1 - x0) / s)) + 2)
        nr = min(height, int(math.ceil((y1 - y0) / (2 * s))) + 2)
        self.s, self.x0, self.y1, self.nc, self.nr = s, x0, y1, nc, nr
        self.ox = max(0, (width - nc) // 2)
        cx = x0 + (np.arange(nc) - 1 + 0.5) * s
        cy = y1 - (np.arange(nr) - 1 + 0.5) * 2 * s
        self.cx, self.cy = cx, cy
        gx, gy = np.meshgrid(cx, cy)
        inside = shapely.contains_xy(geom, gx, gy)
        pad = np.pad(inside, 1)
        near = np.zeros_like(inside)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                near |= pad[1 + dr : 1 + dr + nr, 1 + dc : 1 + dc + nc]
        self.inside = inside
        self.wall = near & ~inside
        self.exit_wall = np.zeros_like(inside)
        points = shapely.points(gx, gy)
        for exit_id, ring in plan.exits.items():
            opening = plan.exit_openings.get(exit_id)
            if opening is not None:
                segment = shapely.LineString(opening)
            else:
                segment = _boundary_piece(geom, Polygon(ring))
            if segment is None:
                continue
            self.exit_wall |= self.wall & (shapely.distance(segment, points) < 0.75 * s)
        self.free = ~(inside | self.wall)
        self.exit_centres = {
            k: tuple(np.asarray(ring[:-1] or ring).mean(axis=0))
            for k, ring in plan.exits.items()
        }
        self.signs = {}
        for sign_id, sx, sy, _alpha in plan.signs:
            c, r = self.cell(sx, sy)
            self.signs[(r, c)] = sign_id

    def cell(self, x: float, y: float) -> tuple[int, int]:
        """``(column, row)`` of the point (x, y)."""
        return int((x - self.x0) / self.s + 1), int((self.y1 - y) / (2 * self.s) + 1)


def _boundary_piece(geom: Any, exit_polygon: Any) -> Any:
    """Longest piece of the walkable boundary inside the exit (design §5.1)."""
    on = exit_polygon.boundary.intersection(geom.boundary)
    parts = [p for p in getattr(on, "geoms", [on]) if p.length > 0]
    if not parts:
        on = exit_polygon.intersection(geom.boundary)
        parts = [p for p in getattr(on, "geoms", [on]) if p.length > 0]
    return max(parts, key=lambda p: p.length) if parts else None


class PlanView(Widget):
    """The plan of the run, with the agents of one frame."""

    DEFAULT_CSS = "PlanView { height: 1fr; min-height: 6; }"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.plan: events.PlanEvent | None = None
        self.frame: events.FrameEvent | None = None
        self.smoke: events.SmokeGrid | None = None
        self._raster: _Raster | None = None
        self._raster_key: tuple[int, int] | None = None
        self._k: Any = None
        self._k_grid: events.SmokeGrid | None = None

    def show(
        self,
        plan: events.PlanEvent | None,
        frame: events.FrameEvent | None,
        smoke: events.SmokeGrid | None,
    ) -> None:
        if plan is not self.plan:
            self._raster = None
        self.plan, self.frame, self.smoke = plan, frame, smoke
        self.refresh()

    # --- data ------------------------------------------------------------------

    def _bins(self, raster: _Raster) -> tuple[Any, Any]:
        """Smoke bins (0 clear, 1-5) of the upper and lower half of each cell."""
        import numpy as np

        shape = raster.inside.shape
        grid = self.smoke
        if (
            grid is None
            or self.plan is None
            or self.plan.smoke_mode
            in (
                events.SMOKE_NONE,
                events.SMOKE_CONSTANT,
            )
        ):
            zero = np.zeros(shape, dtype=int)
            return zero, zero
        if grid is not self._k_grid:
            values = np.frombuffer(grid.values, dtype="<f2").astype(float)
            self._k = np.nan_to_num(values.reshape(grid.ny, grid.nx), nan=0.0)
            self._k_grid = grid
        k = self._k
        i = np.clip(((raster.cx - grid.x0) / grid.cell_m).astype(int), 0, grid.nx - 1)

        def at(dy: float) -> Any:
            rows = ((raster.cy + dy - grid.y0) / grid.cell_m).astype(int)
            j = np.clip(rows, 0, grid.ny - 1)
            b = np.searchsorted(K_EDGES, k[np.ix_(j, i)], side="right")
            b[~raster.inside] = 0
            return b

        return at(raster.s / 2), at(-raster.s / 2)

    def _agents(self, raster: _Raster) -> tuple[dict, dict]:
        """Walking agents and incapacitated agents per cell."""
        import numpy as np

        walking: dict[tuple[int, int], int] = {}
        down: dict[tuple[int, int], int] = {}
        frame = self.frame
        if frame is None or not frame.x:
            return walking, down
        xs = np.frombuffer(frame.x, dtype="<f4")
        ys = np.frombuffer(frame.y, dtype="<f4")
        states = np.frombuffer(frame.states, dtype=np.uint8)
        for x, y, state in zip(xs, ys, states, strict=True):
            c, r = raster.cell(float(x), float(y))
            target = down if state == events.AGENT_INCAPACITATED else walking
            target[(r, c)] = target.get((r, c), 0) + 1
        return walking, down

    def _labels(self, raster: _Raster) -> dict[tuple[int, int], str]:
        """Exit labels on free cells near each exit; the rest in ``unplaced``."""
        counts = {} if self.frame is None else self.frame.exit_counts
        out: dict[tuple[int, int], str] = {}
        self.unplaced: list[str] = []
        for exit_id, (ex, ey) in raster.exit_centres.items():
            text = f"{exit_label(exit_id)} {counts.get(exit_id, 0)}"
            fc, fr = raster.cell(ex, ey)
            best, best_d = None, math.inf
            for r in range(raster.nr):
                for c in range(raster.nc - len(text) + 1):
                    if not raster.free[r, c : c + len(text)].all():
                        continue
                    if any((r, c + k) in out for k in range(-1, len(text) + 1)):
                        continue
                    d = abs(c + len(text) / 2 - fc) + 2 * abs(r - fr)
                    if d < best_d:
                        best, best_d = (r, c), d
            if best is None:
                self.unplaced.append(text)
                continue
            for k, ch in enumerate(text):
                out[(best[0], best[1] + k)] = ch
        return out

    def _scale_bar(self, raster: _Raster, taken: dict) -> dict[tuple[int, int], str]:
        metres = 5 if raster.s * raster.nc < 200 else 20
        n = max(2, int(round(metres / raster.s)))
        bar = "├" + "─" * (n - 1) + f"┤ {metres} m   y↑ x→"
        for r in range(raster.nr - 1, -1, -1):
            for c in range(0, raster.nc - len(bar)):
                if raster.free[r, c : c + len(bar)].all() and not any(
                    (r, c + k) in taken for k in range(len(bar))
                ):
                    return {(r, c + k): ch for k, ch in enumerate(bar)}
        return {}

    # --- rendering -------------------------------------------------------------

    def render(self) -> Text:
        w, h = self.size.width, self.size.height
        if self.plan is None or w < 20 or h < 4 or os.environ.get("TERM") == "dumb":
            return Text(NOT_AVAILABLE, style="dim")
        if self._raster is None or self._raster_key != (w, h):
            self._raster = _Raster(self.plan, w, h - 1)  # a row for exit labels
            self._raster_key = (w, h)
        return self._draw(self._raster, h)

    def _draw(self, raster: _Raster, height: int) -> Text:
        theme = self.app.current_theme
        dark = bool(theme.dark)
        mono = no_color()
        ramp = RAMP_DARK if dark else RAMP_LIGHT
        background = str(theme.background)
        exit_style = Style(color=str(theme.success), bold=True)
        wall_style = Style(color=str(theme.foreground))
        upper, lower = self._bins(raster)
        walking, down = self._agents(raster)
        labels = self._labels(raster)
        marks = self._scale_bar(raster, labels)
        text = Text(no_wrap=True, overflow="crop")
        pad = " " * raster.ox
        for r in range(min(raster.nr, height)):
            text.append(pad)
            for c in range(raster.nc):
                b_up, b_lo = int(upper[r, c]), int(lower[r, c])
                b = max(b_up, b_lo)
                bg = None if (mono or not b) else ramp[b - 1]
                key = (r, c)
                if key in down or key in walking:
                    glyph = "x" if key in down else ("•" if walking[key] == 1 else "●")
                    colour = None if mono else agent_colour(b, dark)
                    text.append(glyph, Style(color=colour, bgcolor=bg, bold=True))
                elif key in raster.signs:
                    text.append("◆", exit_style + Style(bgcolor=bg))
                elif raster.wall[r, c]:
                    if raster.exit_wall[r, c]:
                        text.append("▒" if mono else "█", exit_style)
                    else:
                        text.append(self._wall(raster, r, c), wall_style)
                elif key in labels:
                    text.append(labels[key], exit_style)
                elif key in marks:
                    text.append(marks[key], Style(dim=True))
                elif b and mono:
                    text.append(SHADES[b - 1], Style(dim=True))
                elif b:
                    top = ramp[b_up - 1] if b_up else background
                    bottom = ramp[b_lo - 1] if b_lo else background
                    text.append("▀", Style(color=top, bgcolor=bottom))
                else:
                    text.append(" ")
            text.append("\n")
        if self.unplaced:
            text.append(pad + "exits  " + "   ".join(self.unplaced), exit_style)
        text.rstrip()
        return text

    @staticmethod
    def _wall(raster: _Raster, r: int, c: int) -> str:
        def wall(rr: int, cc: int) -> int:
            if 0 <= rr < raster.nr and 0 <= cc < raster.nc:
                return int(raster.wall[rr, cc])
            return 0

        key = (wall(r - 1, c), wall(r + 1, c), wall(r, c - 1), wall(r, c + 1))
        return HEAVY[key]


def scrubber(
    t: float, limit: float, ticks: list[float], width: int, theme: Any
) -> Text:
    """``plan at 120.0 s ━━╋┊── 300 s limit``: the time of the frame drawn.

    Frames come by wall time and at least once per simulated second, so
    the plan can lag the status line by up to about a second.
    """
    lead = f" plan at {t:5.1f} s "
    tail = f" {limit:g} s limit"
    n = max(10, width - len(lead) - len(tail) - 1)
    limit = limit if limit > 0 else 1.0
    pos = min(n - 1, int(round(t / limit * (n - 1))))
    tick_cells = {min(n - 1, int(round(x / limit * (n - 1)))) for x in ticks}
    bar = Text(lead, Style(bold=True), no_wrap=True, overflow="crop")
    primary, secondary = str(theme.primary), str(theme.secondary)
    for i in range(n):
        if i < pos:
            bar.append("━", Style(color=primary))
        elif i == pos:
            bar.append("╋", Style(color=primary, bold=True))
        elif i in tick_cells:
            bar.append("┊", Style(color=str(theme.warning)))
        else:
            bar.append("─", Style(color=secondary, dim=True))
    bar.append(tail, Style(dim=True))
    return bar


def legend(
    plan: events.PlanEvent | None, theme: Any, smoke: events.SmokeGrid | None = None
) -> Text:
    """Two lines: the smoke scale (or its absence) and the glyph key."""
    mono = no_color()
    dark = bool(theme.dark)
    ramp = RAMP_DARK if dark else RAMP_LIGHT
    line = Text(no_wrap=True, overflow="ellipsis")
    mode = None if plan is None else plan.smoke_mode
    if mode in (events.SMOKE_FDS, events.SMOKE_BLIND):
        line.append(" smoke K [1/m] ", Style(bold=True))
        for i, edge in enumerate(K_EDGES):
            if mono:
                line.append(f"{SHADES[i]}{edge:g} ")
            else:
                colour = agent_colour(i + 1, dark)
                line.append(f" {edge:g} ", Style(bgcolor=ramp[i], color=colour))
        line.append(f"  {legend_text(plan)}", Style(dim=True))
        if smoke is not None:
            line.append(f", frame t = {smoke.fds_time_s:.0f} s", Style(dim=True))
    else:
        line.append(" smoke ", Style(bold=True))
        line.append(legend_text(plan), Style(dim=True))
    key = Text(no_wrap=True, overflow="ellipsis")
    exit_style = Style(color=str(theme.success), bold=True)
    for glyph, name, style in (
        ("•", "agent", Style(bold=True)),
        ("●", "2+ agents", Style(bold=True)),
        ("x", "incapacitated", Style(bold=True)),
        ("◆", "sign", exit_style),
        ("▒" if mono else "█", "exit + evacuated", exit_style),
    ):
        key.append(f" {glyph}", style)
        key.append(f" {name}  ")
    return Text("\n", no_wrap=True).join([line, key])
