"""Plan-view events of a run: the plan once, then throttled frames (#485).

:func:`plan_event` describes the geometry and how the run models smoke, from
the scenario and the models the run was given. :class:`FrameRecorder` is
handed to ``run_scenario``, which calls it after every step; it sends a
:class:`~pyfds_evac.config.events.FrameEvent` at most ``max_hz`` times per
wall second and once more at the end.

Both only read: positions, stage ids and removed agents from JuPedSim, and
the extinction slice through :class:`~pyfds_evac.core.fds_sampling.SliceGrid`,
which does not touch the run's sampler. A run gives the same results with or
without a recorder.

Provisional public API (0.3.0): names may change in 0.3.x.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import numpy as np
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import linemerge

from pyfds_evac.config import events

# Simplification tolerance of the walkable outline [m].
PLAN_TOLERANCE_M = 0.05
# Largest smoke grid sent, in cells (x, y).
SMOKE_GRID_MAX = (200, 120)
DEFAULT_MAX_HZ = 5.0
DEFAULT_SMOKE_HZ = 1.0


def _ring(coords: Iterable[Any]) -> events.Ring:
    return tuple((float(x), float(y)) for x, y, *_ in coords)


def _polygons(geometry: Any) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    return [g for g in getattr(geometry, "geoms", ()) if isinstance(g, Polygon)]


def _segments(geometry: Any) -> Iterable[tuple]:
    """The straight segments of the lines in *geometry*."""
    for line in getattr(geometry, "geoms", [geometry]):
        if not isinstance(line, LineString):
            continue
        coords = list(line.simplify(0).coords)
        yield from zip(coords, coords[1:], strict=False)


def _opening(walkable: Any, exit_polygon: Polygon) -> tuple | None:
    """Longest straight piece of the walkable boundary inside *exit_polygon*.

    For an exit drawn over a gap in the wall this is the door; the wall
    stubs at its sides are shorter.
    """
    boundary = walkable.boundary
    if boundary is None:  # a geometry collection has none
        return None
    piece = _linemerge(boundary.intersection(exit_polygon))
    best = max(
        _segments(piece),
        key=lambda s: math.dist(s[0], s[1]),
        default=None,
    )
    if best is None or math.dist(best[0], best[1]) <= 0:
        return None
    (x0, y0), (x1, y1) = best[0][:2], best[1][:2]
    return ((float(x0), float(y0)), (float(x1), float(y1)))


def _linemerge(geometry: Any) -> Any:
    """Join touching lines, so a segment cut at a vertex counts whole."""
    lines = [
        g for g in getattr(geometry, "geoms", [geometry]) if isinstance(g, LineString)
    ]
    if len(lines) < 2:
        return geometry
    return linemerge(MultiLineString(lines))


def _polygon_entries(section: Mapping[str, Any]) -> dict[str, Polygon]:
    found = {}
    for key, data in section.items():
        coords = (data or {}).get("coordinates")
        if coords and len(coords) >= 3:
            found[str(key)] = Polygon(coords)
    return found


def _authored_signs(raw: Mapping[str, Any]) -> tuple:
    signs = []
    for section in ("exits", "checkpoints", "waypoints"):
        for node_id, data in (raw.get(section) or {}).items():
            sign = (data or {}).get("sign")
            if not sign:
                continue
            alpha = sign.get("alpha")
            signs.append(
                (
                    str(node_id),
                    float(sign["x"]),
                    float(sign["y"]),
                    None if alpha is None else float(alpha),
                )
            )
    return tuple(signs)


def _extinction_sampler(smoke_speed_model: Any) -> Any:
    """The FDS extinction slice sampler of the smoke model, or None."""
    field: Any = getattr(smoke_speed_model, "field", None)
    samplers = field.samplers() if hasattr(field, "samplers") else []
    return samplers[0] if samplers else None


def smoke_mode(smoke_speed_model: Any, smoke_blind: bool) -> tuple[str, float | None]:
    """The plan view's smoke mode and the constant K, from the built model."""
    if smoke_speed_model is None:
        return events.SMOKE_NONE, None
    k = getattr(smoke_speed_model.field, "extinction_per_m", None)
    k = None if k is None else float(k)
    if smoke_blind:
        return events.SMOKE_BLIND, k
    return (events.SMOKE_CONSTANT if k is not None else events.SMOKE_FDS), k


def plan_event(
    scenario: Any,
    *,
    smoke_speed_model: Any = None,
    smoke_blind: bool = False,
    total_agents: int | None = None,
    tolerance_m: float = PLAN_TOLERANCE_M,
) -> events.PlanEvent:
    """The :class:`~pyfds_evac.config.events.PlanEvent` of *scenario*.

    *smoke_speed_model* and *smoke_blind* are the values ``run_scenario``
    gets (``build_run_kwargs``), so the smoke mode and slice height are the
    ones the run uses.
    """
    walkable = scenario.walkable_polygon
    raw = scenario.raw
    simplified = walkable.simplify(tolerance_m, preserve_topology=True)
    exits = _polygon_entries(raw.get("exits") or {})
    openings = {}
    for exit_id, polygon in exits.items():
        opening = _opening(walkable, polygon)
        if opening is not None:
            openings[exit_id] = opening
    mode, k = smoke_mode(smoke_speed_model, smoke_blind)
    sampler = _extinction_sampler(smoke_speed_model)
    xmin, ymin, xmax, ymax = (float(v) for v in walkable.bounds)
    return events.PlanEvent(
        extent=(xmin, ymin, xmax, ymax),
        walkable=tuple(
            (
                _ring(p.exterior.coords),
                tuple(_ring(hole.coords) for hole in p.interiors),
            )
            for p in _polygons(simplified)
        ),
        exits={key: _ring(p.exterior.coords) for key, p in exits.items()},
        exit_openings=openings,
        signs=_authored_signs(raw),
        spawn_areas={
            key: _ring(p.exterior.coords)
            for key, p in _polygon_entries(raw.get("distributions") or {}).items()
        },
        smoke_mode=mode,
        smoke_k=k,
        smoke_z_m=None if sampler is None else float(sampler.z_m),
        max_time_s=float(scenario.max_simulation_time),
        total_agents=total_agents,
        tolerance_m=float(tolerance_m),
    )


def _le(values: np.ndarray, dtype: str) -> bytes:
    return np.ascontiguousarray(
        values, dtype=np.dtype(dtype).newbyteorder("<")
    ).tobytes()


class _SmokeReader:
    """The extinction slice on a coarse grid over the walkable extent."""

    def __init__(self, sampler: Any, extent: tuple[float, float, float, float]):
        xmin, ymin, xmax, ymax = extent
        nx_max, ny_max = SMOKE_GRID_MAX
        cell = max((xmax - xmin) / nx_max, (ymax - ymin) / ny_max, 1e-6)
        self.nx = max(1, int(np.ceil((xmax - xmin) / cell)))
        self.ny = max(1, int(np.ceil((ymax - ymin) / cell)))
        self.x0, self.y0, self.cell = xmin, ymin, cell
        xs = xmin + (np.arange(self.nx) + 0.5) * cell
        ys = ymin + (np.arange(self.ny) + 0.5) * cell
        self._grid = sampler.grid(xs, ys)
        self._z = float(sampler.z_m)
        self._quantity = sampler.quantity
        self.last_index: int | None = None

    def read(self, sim_time: float) -> events.SmokeGrid | None:
        """The grid at *sim_time*, or None if its FDS frame was sent last."""
        index = self._grid.time_index(sim_time)
        if index == self.last_index:
            return None
        self.last_index = index
        values = self._grid.values(index)
        return events.SmokeGrid(
            x0=float(self.x0),
            y0=float(self.y0),
            cell_m=float(self.cell),
            nx=self.nx,
            ny=self.ny,
            values=_le(values.astype(np.float16), "f2"),
            fds_time_s=self._grid.frame_time_s(index),
            z_m=self._z,
            quantity=self._quantity,
        )


class FrameRecorder:
    """Send :class:`~pyfds_evac.config.events.FrameEvent`\\ s from a run.

    *emit* receives each event. A frame goes out when at least
    ``1 / max_hz`` wall seconds have passed since the last one, and the
    smoke grid with it when ``1 / smoke_hz`` have passed since the last
    grid and the FDS frame has changed. *clock* returns wall seconds.

    ``run_scenario`` calls :meth:`start` once before the first step,
    :meth:`leaves` when it removes an agent at an exit, :meth:`after_step`
    after every step and :meth:`finish` after the last.

    An agent counts as evacuated in the step JuPedSim removes it, so the
    counts agree with ``agents_evacuated`` of the run. JuPedSim 1.4.2 lists
    an agent that reaches an exit stage in ``removed_agents()`` after the
    step and removes it at the start of the next one; until then it can
    still be read, and its stage names the exit. Agents removed by
    ``mark_agent_for_removal`` (direct steering) are not listed there;
    ``run_scenario`` reports them through :meth:`leaves`.
    """

    def __init__(
        self,
        emit: Callable[[events.FrameEvent], None],
        *,
        max_hz: float = DEFAULT_MAX_HZ,
        smoke_hz: float = DEFAULT_SMOKE_HZ,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not max_hz > 0 or not smoke_hz >= 0:
            raise ValueError(
                "frame rates must be positive (smoke_hz may be 0 for no grid), "
                f"got max_hz={max_hz}, smoke_hz={smoke_hz}"
            )
        self._emit = emit
        self._period = 1.0 / max_hz
        self._smoke_period = None if smoke_hz == 0 else 1.0 / smoke_hz
        self._clock = clock
        self._start = 0.0
        self._last: float | None = None
        self._last_smoke: float | None = None
        self._exit_by_stage: dict[int, str] = {}
        # Exit of each agent that leaves at the next step.
        self._leaving: dict[int, str | None] = {}
        self._smoke: _SmokeReader | None = None
        self.exit_counts: dict[str, int] = {}
        self.unattributed = 0
        self.frames = 0

    def start(
        self,
        stage_map: Mapping[str, int],
        exit_ids: Iterable[str],
        smoke_speed_model: Any,
        extent: tuple[float, float, float, float],
    ) -> None:
        """Set up before the first step.

        *stage_map* maps a stage id of the scenario to its JuPedSim stage;
        *exit_ids* are the exits, counted from zero.
        """
        self._start = self._clock()
        exits = [str(e) for e in exit_ids]
        self.exit_counts = dict.fromkeys(exits, 0)
        self._exit_by_stage = {
            int(stage_map[e]): e for e in exits if stage_map.get(e, -1) != -1
        }
        sampler = _extinction_sampler(smoke_speed_model)
        if sampler is not None and self._smoke_period is not None:
            self._smoke = _SmokeReader(sampler, extent)

    def leaves(self, agent_id: int, exit_id: str | None) -> None:
        """*agent_id* is marked for removal at *exit_id* before the next step."""
        self._leaving[int(agent_id)] = exit_id

    def _exit_of(self, simulation: Any, agent_id: int) -> str | None:
        try:
            stage = int(simulation.agent(agent_id).stage_id)
        except Exception:  # not readable: counted as unattributed
            return None
        return self._exit_by_stage.get(stage)

    def _count_left(self, simulation: Any) -> None:
        """Count the agents this step removed; note those the next removes."""
        for exit_id in self._leaving.values():
            if exit_id is None:
                self.unattributed += 1
            else:
                self.exit_counts[exit_id] = self.exit_counts.get(exit_id, 0) + 1
        self._leaving = {
            int(a): self._exit_of(simulation, int(a))
            for a in simulation.removed_agents()
        }

    def after_step(
        self,
        simulation: Any,
        *,
        incapacitated: set[int],
        not_spawned: int,
    ) -> None:
        """Count the agents that left in this step; send a frame when due."""
        self._count_left(simulation)
        now = self._clock()
        if self._last is not None and now - self._last < self._period:
            return
        self._send(simulation, now, incapacitated, not_spawned, final=False)

    def finish(
        self, simulation: Any, *, incapacitated: set[int], not_spawned: int
    ) -> None:
        """Send the last frame of the run."""
        self._send(simulation, self._clock(), incapacitated, not_spawned, final=True)

    def _send(
        self,
        simulation: Any,
        now: float,
        incapacitated: set[int],
        not_spawned: int,
        *,
        final: bool,
    ) -> None:
        self._last = now
        sim_time = float(simulation.elapsed_time())
        agents = list(simulation.agents())
        ids = np.fromiter((a.id for a in agents), dtype=np.int64, count=len(agents))
        xy = np.array([a.position for a in agents], dtype=float).reshape(-1, 2)
        states = np.array(
            [
                events.AGENT_INCAPACITATED
                if int(i) in incapacitated
                else events.AGENT_WALKING
                for i in ids
            ],
            dtype=np.uint8,
        )
        evacuated = sum(self.exit_counts.values()) + self.unattributed
        self.frames += 1
        self._emit(
            events.FrameEvent(
                sim_time=sim_time,
                wall_time=now - self._start,
                ids=_le(ids, "i4"),
                x=_le(xy[:, 0], "f4"),
                y=_le(xy[:, 1], "f4"),
                states=states.tobytes(),
                evacuated=evacuated,
                exit_counts=dict(self.exit_counts),
                unattributed=self.unattributed,
                incapacitated=len(incapacitated),
                not_spawned=not_spawned,
                smoke=self._read_smoke(sim_time, now, final),
                final=final,
            )
        )

    def _read_smoke(
        self, sim_time: float, now: float, final: bool
    ) -> events.SmokeGrid | None:
        if self._smoke is None or self._smoke_period is None:
            return None
        due = self._last_smoke is None or now - self._last_smoke >= self._smoke_period
        if not (due or final):
            return None
        grid = self._smoke.read(sim_time)
        if grid is not None:
            self._last_smoke = now
        return grid
