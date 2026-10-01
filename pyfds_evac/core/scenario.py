"""Standalone helpers for loading and running JuPedSim web-UI scenario JSON files.

No dependency on the web backend — only JuPedSim, Shapely, and NumPy.

Usage::

    from pyfds_evac.core.scenario import load_scenario, run_scenario

    scenario = load_scenario("scenario.zip")
    print(scenario.summary())

    result = run_scenario(scenario)
    print(result.metrics)

    df = result.trajectory_dataframe()
"""

import hashlib
import json
import logging
import math
import os
import pathlib
import sqlite3
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

try:
    import jupedsim as jps
except ModuleNotFoundError:
    jps = None
import numpy as np
from shapely import wkt
from shapely.geometry import Polygon

from .agent_seed import (
    INITIAL_ORIGIN,
    PURPOSE_FAMILIARITY,
    PURPOSE_INCAP_GAS,
    PURPOSE_INCAP_HEAT,
    PURPOSE_TARGET,
    PURPOSE_VARIANT,
    SEEDING_SCHEME,
    SpawnKey,
    SpawnKeyError,
    agent_rng,
    assign_spawn_key,
    commit_spawn_key,
    lookup_spawn_key,
    pending_spawn_key,
    stagger_index,
    steering_seeds,
)
from .cognitive_map import (
    AgentCognitiveMap,
    expand_from_visibility,
    expand_on_arrival,
    init_cognitive_map,
)
from .direct_steering_runtime import (
    active_steering_zones,
    advance_path_target,
    assign_agent_target,
    ensure_agent_speed_state,
    extract_agent_xy,
    get_agent_desired_speed,
    reached_stage,
    sample_wait_time,
    set_agent_desired_speed,
    set_agent_fic_factor,
    set_agent_smoke_factor,
    update_checkpoint_speed,
)
from .fds_coverage import (
    apply_coverage_policy,
    check_fds_coverage,
    count_outside,
    domain_fields,
    in_fds_domain,
    model_samplers,
)
from .fds_sampling import FdsHorizonError
from .fed import (
    DefaultFedInputs,
    HeatFedInputs,
    default_fed_components,
    default_fic,
    heat_endpoint_row_fields,
    heat_flux_row_fields,
    sample_heat_incapacitation_threshold,
    sample_incapacitation_threshold,
)
from .manifest import fds_dir_from_models, write_manifest
from .route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageGraph,
    compute_eval_offset,
    evaluate_and_reroute,
    rank_routes,
    reroute_agent,
    should_reevaluate,
    stage_closed,
)
from .smoke_speed import ConstantExtinctionField, sample_accepts_free_speed

_logger = logging.getLogger(__name__)
_ZERO_EXTINCTION = ConstantExtinctionField(0.0)


class _FedRateAdapter:
    """Adapt DefaultFedModel to the FedRateSampler protocol."""

    def __init__(self, model):
        self._model = model

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        _, rate = self._model.sample_rate(time_s, x, y)
        return rate


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

_MODEL_BUILDERS = {
    "CollisionFreeSpeedModel": lambda p: jps.CollisionFreeSpeedModel(
        strength_neighbor_repulsion=p.get("strength_neighbor_repulsion", 2.6),
        range_neighbor_repulsion=p.get("range_neighbor_repulsion", 0.1),
    ),
    # V2 carries the repulsion parameters per agent, not on the model, so its
    # constructor takes nothing; create_agent_parameters supplies them.
    "CollisionFreeSpeedModelV2": lambda p: jps.CollisionFreeSpeedModelV2(),
    "AnticipationVelocityModel": lambda p: jps.AnticipationVelocityModel(
        # strength_neighbor_repulsion=p.get("strength_neighbor_repulsion", 2.6),
        # range_neighbor_repulsion=p.get("range_neighbor_repulsion", 0.1),
        # anticipation_time=p.get("anticipation_time", 1.0)
    ),
    "GeneralizedCentrifugalForceModel": lambda p: jps.GeneralizedCentrifugalForceModel(
        strength_neighbor_repulsion=p.get("gcfm_strength_neighbor_repulsion", 0.3),
        strength_geometry_repulsion=p.get("gcfm_strength_geometry_repulsion", 0.2),
        max_neighbor_interaction_distance=p.get(
            "gcfm_max_neighbor_interaction_distance", 2.0
        ),
        max_geometry_interaction_distance=p.get(
            "gcfm_max_geometry_interaction_distance", 2.0
        ),
        max_neighbor_repulsion_force=p.get("gcfm_max_neighbor_repulsion_force", 9.0),
        max_geometry_repulsion_force=p.get("gcfm_max_geometry_repulsion_force", 3.0),
    ),
    "SocialForceModel": lambda p: jps.SocialForceModel(
        bodyForce=p.get("agent_strength", 2000),
        friction=p.get("agent_range", 0.08),
    ),
    "WarpDriverModel": lambda p: jps.WarpDriverModel(
        time_horizon=p.get("time_horizon", 2.0),
        step_size=p.get("step_size", 0.5),
        sigma=p.get("sigma", 0.3),
        time_uncertainty=p.get("time_uncertainty", 0.5),
        velocity_uncertainty_x=p.get("velocity_uncertainty_x", 0.2),
        velocity_uncertainty_y=p.get("velocity_uncertainty_y", 0.2),
    ),
}

_AGENT_PARAM_BUILDERS = {
    "CollisionFreeSpeedModel": lambda **kw: jps.CollisionFreeSpeedModelAgentParameters(
        **kw
    ),
    "CollisionFreeSpeedModelV2": lambda **kw: (
        jps.CollisionFreeSpeedModelV2AgentParameters(**kw)
    ),
    "GeneralizedCentrifugalForceModel": lambda **kw: (
        jps.GeneralizedCentrifugalForceModelAgentParameters(
            desired_speed=kw["desired_speed"],
            a_v=1.0,
            a_min=kw["radius"],
            b_min=kw["radius"],
            b_max=kw["radius"] * 2,
            position=kw["position"],
            journey_id=kw["journey_id"],
            stage_id=kw["stage_id"],
        )
    ),
    "SocialForceModel": lambda **kw: jps.SocialForceModelAgentParameters(**kw),
    "AnticipationVelocityModel": lambda **kw: (
        jps.AnticipationVelocityModelAgentParameters(**kw)
    ),
    "WarpDriverModel": lambda **kw: jps.WarpDriverModelAgentParameters(**kw),
}


def _build_model(model_type: str, sim_params: dict):
    """Construct the configured JuPedSim operational model."""
    _require_jupedsim()
    builder = _MODEL_BUILDERS.get(model_type)
    if builder is None:
        raise ValueError(
            f"Unknown model type: {model_type}. Available: {list(_MODEL_BUILDERS)}"
        )
    return builder(sim_params)


def _build_agent_params(
    model_type: str,
    v0: float,
    radius: float,
    position: tuple[float, float],
    journey_id: int,
    stage_id: int,
):
    """Construct JuPedSim agent parameters for the chosen model type."""
    _require_jupedsim()
    builder = _AGENT_PARAM_BUILDERS.get(model_type)
    if builder is None:
        raise ValueError(f"No agent params builder for model type: {model_type}")
    return builder(
        desired_speed=v0,
        radius=radius,
        position=position,
        journey_id=journey_id,
        stage_id=stage_id,
    )


def _require_jupedsim():
    """Fail with a clear error when JuPedSim is not installed."""
    if jps is None:
        raise ModuleNotFoundError(
            "jupedsim is required to run scenarios. Install project dependencies first."
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_max_capacity(polygon: Polygon, max_radius: float) -> int:
    """Estimate a conservative packing limit for one spawn polygon."""
    effective_radius = max(max_radius, 0.1)
    theoretical = polygon.area / (math.pi * effective_radius * effective_radius)
    return max(1, math.floor(theoretical * 0.5))


def _sample_agent_values(
    params: dict, n_agents: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Sample radii and speeds for *n_agents*."""
    mean_radius = max(0.1, min(1.0, params.get("radius", 0.2)))
    mean_v0 = max(0.1, min(5.0, params.get("desired_speed", params.get("v0", 1.25))))

    if params.get("radius_distribution") == "gaussian" and params.get("radius_std"):
        radii = rng.normal(mean_radius, params["radius_std"], n_agents).clip(0.1, 1.0)
    else:
        radii = np.full(n_agents, mean_radius)

    v0_dist = params.get("desired_speed_distribution", params.get("v0_distribution"))
    v0_std = params.get("desired_speed_std", params.get("v0_std"))
    if v0_dist == "gaussian" and v0_std:
        v0s = rng.normal(mean_v0, v0_std, n_agents).clip(0.1, 5.0)
    else:
        v0s = np.full(n_agents, mean_v0)

    return radii, v0s


def _normalize_flow_schedule_entry(entry: dict) -> dict:
    """Normalize one configured flow schedule entry to canonical keys."""
    start_time = entry.get("flow_start_time", entry.get("start_time_s"))
    end_time = entry.get("flow_end_time", entry.get("end_time_s"))
    number = entry.get("number", entry.get("sim_count"))

    if start_time is None or end_time is None or number is None:
        raise ValueError(
            "Each flow schedule entry must define start/end time and number. "
            "Accepted keys: flow_start_time|start_time_s, flow_end_time|end_time_s, number|sim_count."
        )

    start_time = float(start_time)
    end_time = float(end_time)
    number = int(number)

    if start_time < 0 or end_time <= start_time:
        raise ValueError(
            f"Invalid flow window [{start_time}, {end_time}] - end_time must be greater than start_time."
        )
    if number <= 0:
        raise ValueError(
            f"Flow schedule numbers must be positive integers, got {number!r}"
        )

    return {
        "flow_start_time": start_time,
        "flow_end_time": end_time,
        "number": number,
    }


def _normalized_flow_schedule(params: dict) -> list[dict]:
    """Return the sorted flow schedule for one distribution."""
    raw_schedule = params.get("flow_schedule", [])
    if not raw_schedule:
        return []
    normalized = [_normalize_flow_schedule_entry(entry) for entry in raw_schedule]
    normalized.sort(
        key=lambda entry: (entry["flow_start_time"], entry["flow_end_time"])
    )
    return normalized


def _distribution_agent_budget(dist: dict) -> int:
    """Return the total number of agents implied by one distribution."""
    params = dist.get("parameters", {})
    schedule = _normalized_flow_schedule(params)
    if schedule:
        initial_number = int(params.get("initial_number", 0) or 0)
        return initial_number + sum(entry["number"] for entry in schedule)
    return int(params.get("number", 0) or 0)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    """A loaded scenario ready for inspection and execution."""

    raw: dict[str, Any]
    walkable_area_wkt: str
    model_type: str
    seed: int
    sim_params: dict[str, Any]
    source_path: str | None = None

    _walkable_polygon: Any = field(default=None, repr=False)

    def __post_init__(self):
        self._walkable_polygon = wkt.loads(self.walkable_area_wkt)
        self._sync_runtime_to_raw()

    @property
    def walkable_polygon(self):
        return self._walkable_polygon

    @property
    def max_simulation_time(self) -> float:
        return self.sim_params.get("max_simulation_time", 300)

    @property
    def exits(self) -> dict[str, Any]:
        return self.raw.get("exits", {})

    @property
    def distributions(self) -> dict[str, Any]:
        return self.raw.get("distributions", {})

    @property
    def stages(self) -> dict[str, Any]:
        return self.raw.get("checkpoints", {})

    @property
    def zones(self) -> dict[str, Any]:
        return self.raw.get("zones", {})

    @property
    def journeys(self) -> list[dict[str, Any]]:
        return self.raw.get("journeys", [])

    def _simulation_settings(self) -> dict[str, Any]:
        config = self.raw.setdefault("config", {})
        return config.setdefault("simulation_settings", {})

    def _simulation_params(self) -> dict[str, Any]:
        settings = self._simulation_settings()
        return settings.setdefault("simulationParams", {})

    def _sync_runtime_to_raw(self) -> None:
        settings = self._simulation_settings()
        settings["baseSeed"] = self.seed
        params = self._simulation_params()
        params.update(self.sim_params)
        params["model_type"] = self.model_type

    def summary(self) -> str:
        total_agents = sum(
            _distribution_agent_budget(d) for d in self.distributions.values()
        )
        journey_sequence = []
        journeys = self.raw.get("journeys", [])
        if journeys:
            journey_sequence = list(journeys[0].get("stages", []))
        lines = [
            f"Scenario: {self.source_path or '(in-memory)'}",
            f"  Model:         {self.model_type}",
            f"  Seed:          {self.seed}",
            f"  Max time:      {self.max_simulation_time}s",
            f"  Exits:         {len(self.exits)}",
            f"  Distributions: {len(self.distributions)}",
            f"  Stages:        {len(self.stages)}",
            f"  Zones:         {len(self.zones)}",
            f"  Journeys:      {len(self.journeys)}",
            f"  Agents:        ~{total_agents}",
        ]
        if journey_sequence:
            checkpoint_count = sum(
                stage.startswith("jps-checkpoints_") for stage in journey_sequence
            )
            exit_count = sum(
                stage.startswith("jps-exits_") for stage in journey_sequence
            )
            distribution_count = sum(
                stage.startswith("jps-distributions_") for stage in journey_sequence
            )
            lines.append(f"  Journey elems: {len(journey_sequence)}")
            lines.append(
                "  Route:         "
                f"{distribution_count} distribution, "
                f"{checkpoint_count} checkpoint, "
                f"{exit_count} exit"
            )
            lines.append(f"  Sequence:      {' -> '.join(journey_sequence)}")
        for dist_id, dist in self.distributions.items():
            params = dist.get("parameters", {})
            flow = params.get("use_flow_spawning", False)
            n = params.get("number", "?")
            tag = (
                f" (flow: {params.get('flow_start_time', 0)}-{params.get('flow_end_time', 10)}s)"
                if flow
                else ""
            )
            lines.append(f"    {dist_id}: {n} agents{tag}")
        return "\n".join(lines)

    def plot(self, ax=None):
        """Plot the scenario geometry with labeled distributions, exits, zones, and checkpoints.

        Returns the matplotlib Axes so callers can further customise the figure.
        """
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon

        if ax is None:
            _, ax = plt.subplots(figsize=(12, 7), constrained_layout=True)

        # Walkable area (exterior + interior holes as walls)
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MplPath

        exterior_coords = list(self.walkable_polygon.exterior.coords)
        codes = (
            [MplPath.MOVETO]
            + [MplPath.LINETO] * (len(exterior_coords) - 2)
            + [MplPath.CLOSEPOLY]
        )
        verts = list(exterior_coords)

        for interior in self.walkable_polygon.interiors:
            hole_coords = list(interior.coords)
            codes += (
                [MplPath.MOVETO]
                + [MplPath.LINETO] * (len(hole_coords) - 2)
                + [MplPath.CLOSEPOLY]
            )
            verts += list(hole_coords)

        path = MplPath(verts, codes)
        patch = PathPatch(
            path,
            facecolor="#f0f0ec",
            edgecolor="#3a3a3a",
            linewidth=1.5,
            alpha=0.5,
            zorder=0,
        )
        ax.add_patch(patch)

        # Draw wall outlines explicitly
        wx, wy = self.walkable_polygon.exterior.xy
        ax.plot(wx, wy, color="#3a3a3a", linewidth=1.5, zorder=1)
        for interior in self.walkable_polygon.interiors:
            ix, iy = interior.xy
            ax.plot(ix, iy, color="#3a3a3a", linewidth=1.5, zorder=1)

        palette = {
            "distribution": "#2563EB",
            "exit": "#DC2626",
            "zone": "#059669",
            "checkpoint": "#D97706",
        }

        def _plot_element(coords, color, label, alpha=0.35):
            poly = MplPolygon(
                coords[:-1],
                closed=True,
                facecolor=color,
                edgecolor=color,
                alpha=alpha,
                linewidth=1.5,
                zorder=2,
            )
            ax.add_patch(poly)
            cx = sum(c[0] for c in coords[:-1]) / max(len(coords) - 1, 1)
            cy = sum(c[1] for c in coords[:-1]) / max(len(coords) - 1, 1)
            ax.text(
                cx,
                cy,
                label,
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color=color,
                zorder=3,
            )

        for i, (did, d) in enumerate(self.distributions.items()):
            n = _distribution_agent_budget(d)
            _plot_element(d["coordinates"], palette["distribution"], f"D{i}\n({n} ag)")

        for i, (eid, e) in enumerate(self.exits.items()):
            _plot_element(e["coordinates"], palette["exit"], f"E{i}", alpha=0.5)

        for i, (zid, z) in enumerate(self.zones.items()):
            sf = z.get("speed_factor", 1.0)
            _plot_element(
                z["coordinates"], palette["zone"], f"Z{i}\n(sf={sf})", alpha=0.25
            )

        for i, (sid, s) in enumerate(self.stages.items()):
            wt = s.get("waiting_time", 0.0)
            _plot_element(
                s["coordinates"], palette["checkpoint"], f"C{i}\n(w={wt}s)", alpha=0.3
            )

        # Legend
        from matplotlib.patches import Patch

        handles = []
        if self.distributions:
            handles.append(
                Patch(
                    facecolor=palette["distribution"], alpha=0.35, label="Distribution"
                )
            )
        if self.exits:
            handles.append(Patch(facecolor=palette["exit"], alpha=0.5, label="Exit"))
        if self.zones:
            handles.append(Patch(facecolor=palette["zone"], alpha=0.25, label="Zone"))
        if self.stages:
            handles.append(
                Patch(facecolor=palette["checkpoint"], alpha=0.3, label="Checkpoint")
            )
        if handles:
            ax.legend(handles=handles, loc="best", frameon=False, fontsize=9)

        ax.set_aspect("equal")
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.set_title(f"Scenario: {self.source_path or '(in-memory)'}", pad=10)
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return ax

    # -- resolver helpers (private) -----------------------------------------

    def _resolve_distribution_id(self, id: int | str) -> str:
        """Accept an int index or string key for a distribution."""
        if isinstance(id, int):
            keys = list(self.distributions.keys())
            if id < 0 or id >= len(keys):
                raise IndexError(
                    f"Distribution index {id} out of range. "
                    f"Available indices: 0..{len(keys) - 1}"
                )
            return keys[id]
        if id not in self.distributions:
            raise KeyError(
                f"Distribution '{id}' not found. "
                f"Available: {list(self.distributions.keys())}"
            )
        return id

    def _resolve_zone_id(self, id: int | str) -> str:
        """Accept an int index or string key for a zone."""
        if isinstance(id, int):
            keys = list(self.zones.keys())
            if id < 0 or id >= len(keys):
                raise IndexError(
                    f"Zone index {id} out of range. "
                    f"Available indices: 0..{len(keys) - 1}"
                )
            return keys[id]
        if id not in self.zones:
            raise KeyError(
                f"Zone '{id}' not found. Available: {list(self.zones.keys())}"
            )
        return id

    def _resolve_stage_id(self, id: int | str) -> str:
        """Accept an int index or string key for a stage/checkpoint."""
        if isinstance(id, int):
            keys = list(self.stages.keys())
            if id < 0 or id >= len(keys):
                raise IndexError(
                    f"Stage index {id} out of range. "
                    f"Available indices: 0..{len(keys) - 1}"
                )
            return keys[id]
        if id not in self.stages:
            raise KeyError(
                f"Stage '{id}' not found. Available: {list(self.stages.keys())}"
            )
        return id

    # -- discovery methods ---------------------------------------------------

    def list_distributions(self) -> list[dict]:
        """Return a list of ``{"index", "id", "agents", "flow"}`` dicts."""
        result = []
        for i, (did, d) in enumerate(self.distributions.items()):
            params = d.get("parameters", {})
            result.append(
                {
                    "index": i,
                    "id": did,
                    "agents": _distribution_agent_budget(d),
                    "flow": params.get("use_flow_spawning", False)
                    or bool(params.get("flow_schedule")),
                }
            )
        return result

    def list_zones(self) -> list[dict]:
        """Return a list of ``{"index", "id", "speed_factor"}`` dicts."""
        result = []
        for i, (zid, z) in enumerate(self.zones.items()):
            result.append(
                {
                    "index": i,
                    "id": zid,
                    "speed_factor": z.get("speed_factor", 1.0),
                }
            )
        return result

    def list_stages(self) -> list[dict]:
        """Return a list of ``{"index", "id", "waiting_time"}`` dicts."""
        result = []
        for i, (sid, s) in enumerate(self.stages.items()):
            result.append(
                {
                    "index": i,
                    "id": sid,
                    "waiting_time": s.get("waiting_time", 0.0),
                }
            )
        return result

    # -- copy ----------------------------------------------------------------

    def copy(self, **overrides) -> "Scenario":
        """Return an independent deep copy of this scenario, with optional field overrides."""
        import copy

        clone = copy.deepcopy(self)
        for key, value in overrides.items():
            if not hasattr(clone, key):
                raise AttributeError(f"Scenario has no attribute '{key}'")
            setattr(clone, key, value)
        if "walkable_area_wkt" in overrides:
            clone._walkable_polygon = wkt.loads(clone.walkable_area_wkt)
        clone._sync_runtime_to_raw()
        return clone

    # -- setters -------------------------------------------------------------

    def set_agent_count(self, distribution_id: int | str, count: int):
        distribution_id = self._resolve_distribution_id(distribution_id)
        if not isinstance(count, int) or count <= 0:
            raise ValueError(f"count must be a positive integer, got {count!r}")
        dist = self.distributions[distribution_id]
        dist.setdefault("parameters", {})["number"] = count
        dist["parameters"]["distribution_mode"] = "by_number"

    def set_seed(self, seed: int):
        if not isinstance(seed, int) or seed < 0:
            raise ValueError(f"seed must be a non-negative integer, got {seed!r}")
        self.seed = seed
        self._simulation_settings()["baseSeed"] = seed

    def set_max_time(self, seconds: float):
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            raise ValueError(f"seconds must be a positive number, got {seconds!r}")
        self.sim_params["max_simulation_time"] = seconds
        self._simulation_params()["max_simulation_time"] = seconds

    def set_model_type(self, model_type: str):
        if model_type not in _MODEL_BUILDERS:
            raise ValueError(
                f"Unknown model: {model_type}. Available: {list(_MODEL_BUILDERS)}"
            )
        self.model_type = model_type
        self.sim_params["model_type"] = model_type
        self._simulation_params()["model_type"] = model_type

    def set_model_params(self, **kwargs):
        """Set model-specific parameters (e.g. strength_neighbor_repulsion, range_neighbor_repulsion)."""
        for key, value in kwargs.items():
            if isinstance(value, (int, float)) and value < 0:
                raise ValueError(
                    f"Numeric parameter '{key}' must be non-negative, got {value}"
                )
        self.sim_params.update(kwargs)
        self._simulation_params().update(kwargs)

    def set_agent_params(self, distribution_id: int | str, **kwargs):
        """Set agent parameters for a distribution.

        Supported keys: radius, desired_speed (or v0), radius_distribution,
        radius_std, desired_speed_distribution (or v0_distribution),
        desired_speed_std (or v0_std), use_flow_spawning, flow_start_time,
        flow_end_time, distribution_mode, number.
        """
        distribution_id = self._resolve_distribution_id(distribution_id)
        speed_value = kwargs.get("desired_speed", kwargs.get("v0"))
        speed_std_value = kwargs.get("desired_speed_std", kwargs.get("v0_std"))
        speed_dist_value = kwargs.get(
            "desired_speed_distribution",
            kwargs.get("v0_distribution"),
        )
        if "radius" in kwargs:
            r = kwargs["radius"]
            if not isinstance(r, (int, float)) or r <= 0 or r > 1.0:
                raise ValueError(f"radius must be in (0, 1.0], got {r!r}")
        if speed_value is not None:
            if (
                not isinstance(speed_value, (int, float))
                or speed_value <= 0
                or speed_value > 5.0
            ):
                raise ValueError(
                    f"desired_speed/v0 must be in (0, 5.0], got {speed_value!r}"
                )
        if speed_std_value is not None:
            if not isinstance(speed_std_value, (int, float)) or speed_std_value < 0:
                raise ValueError(
                    f"desired_speed_std/v0_std must be non-negative, got {speed_std_value!r}"
                )
        if speed_dist_value is not None:
            if speed_dist_value not in {"constant", "gaussian"}:
                raise ValueError(
                    f"desired_speed_distribution/v0_distribution must be 'constant' or 'gaussian', got {speed_dist_value!r}"
                )
        if "number" in kwargs:
            n = kwargs["number"]
            if not isinstance(n, int) or n <= 0:
                raise ValueError(f"number must be a positive integer, got {n!r}")
        dist = self.distributions[distribution_id]
        params = dist.setdefault("parameters", {})
        params.update(kwargs)
        if speed_value is not None:
            params["desired_speed"] = speed_value
            params["v0"] = speed_value
        if speed_std_value is not None:
            params["desired_speed_std"] = speed_std_value
            params["v0_std"] = speed_std_value
        if speed_dist_value is not None:
            params["desired_speed_distribution"] = speed_dist_value
            params["v0_distribution"] = speed_dist_value

    def set_flow_schedule(
        self,
        distribution_id: int | str,
        schedule: list[dict],
        *,
        keep_initial_agents: bool = False,
    ):
        """Attach a time-windowed inflow schedule to one source distribution."""
        distribution_id = self._resolve_distribution_id(distribution_id)
        if not isinstance(schedule, list) or not schedule:
            raise ValueError(
                "schedule must be a non-empty list of flow schedule entries"
            )

        normalized_schedule = [
            _normalize_flow_schedule_entry(entry) for entry in schedule
        ]
        normalized_schedule.sort(
            key=lambda entry: (entry["flow_start_time"], entry["flow_end_time"])
        )

        dist = self.distributions[distribution_id]
        params = dist.setdefault("parameters", {})

        if keep_initial_agents:
            params["initial_number"] = int(params.get("number", 0) or 0)
        else:
            params.pop("initial_number", None)

        params["flow_schedule"] = normalized_schedule
        params["use_flow_spawning"] = True
        params["distribution_mode"] = "by_number"
        params["number"] = sum(entry["number"] for entry in normalized_schedule)
        params["flow_start_time"] = normalized_schedule[0]["flow_start_time"]
        params["flow_end_time"] = normalized_schedule[-1]["flow_end_time"]

    def set_zone_speed_factor(self, zone_id: int | str, factor: float):
        """Set the speed factor for a zone."""
        zone_id = self._resolve_zone_id(zone_id)
        if not isinstance(factor, (int, float)) or factor < 0:
            raise ValueError(f"factor must be non-negative, got {factor!r}")
        self.zones[zone_id]["speed_factor"] = factor

    def set_checkpoint_waiting_time(
        self, checkpoint_id: int | str, waiting_time: float
    ):
        """Set the waiting time for a checkpoint/stage."""
        checkpoint_id = self._resolve_stage_id(checkpoint_id)
        if not isinstance(waiting_time, (int, float)) or waiting_time < 0:
            raise ValueError(f"waiting_time must be non-negative, got {waiting_time!r}")
        self.stages[checkpoint_id]["waiting_time"] = waiting_time


@dataclass(frozen=True)
class ProgressEvent:
    """A single progress sample emitted while a scenario runs.

    ``evacuated``/``total`` are agent counts, ``sim_time`` is the simulated
    clock in seconds, ``wall_time`` is real elapsed seconds since the run
    started, and ``pct`` is the integer evacuation percentage.
    """

    evacuated: int
    total: int
    sim_time: float
    wall_time: float
    pct: int


# Called for each progress sample when supplied to ``run_scenario``.
ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class ScenarioResult:
    """Results from running a scenario."""

    metrics: dict[str, Any]
    sqlite_file: str | None = None
    smoke_history: list[dict[str, Any]] | None = None
    fed_history: list[dict[str, Any]] | None = None
    route_history: list[dict[str, Any]] | None = None
    route_cost_history: list[dict[str, Any]] | None = None
    cognitive_map_history: list[dict[str, Any]] | None = None
    manifest_file: str | None = None
    exit_history: list[dict[str, Any]] | None = None

    @property
    def success(self) -> bool:
        return self.metrics.get("success", False)

    @property
    def evacuation_time(self) -> float:
        return self.metrics.get("evacuation_time", 0.0)

    @property
    def total_agents(self) -> int:
        return self.metrics.get("total_agents", 0)

    @property
    def agents_evacuated(self) -> int:
        return self.metrics.get("agents_evacuated", 0)

    @property
    def agents_remaining(self) -> int:
        return self.metrics.get("agents_remaining", 0)

    @property
    def frame_rate(self) -> float:
        """Trajectory frame rate in frames per second (dt=0.01, every_nth_frame=10 → 10 fps)."""
        return self.metrics.get("frame_rate", 10.0)

    @property
    def dt(self) -> float:
        """Simulation timestep in seconds."""
        return self.metrics.get("dt", 0.01)

    @property
    def seed(self) -> int:
        """Random seed used for this run."""
        return self.metrics.get("seed", 0)

    @property
    def walkable_polygon(self):
        """Walkable area as a Shapely Polygon (for pedpy analysis)."""
        return self.metrics.get("walkable_polygon")

    def trajectory_dataframe(self):
        """Load trajectory data into a pandas DataFrame.

        Columns: frame, id, x, y, ori_x, ori_y
        """
        import pandas as pd

        if not self.sqlite_file or not os.path.exists(self.sqlite_file):
            raise FileNotFoundError("No trajectory SQLite file available")

        con = sqlite3.connect(self.sqlite_file)
        try:
            df = pd.read_sql_query(
                "SELECT frame, id, pos_x AS x, pos_y AS y, ori_x, ori_y FROM trajectory_data",
                con,
            )
        finally:
            con.close()
        return df

    def cleanup(self):
        """Delete the temporary SQLite trajectory file and its manifest."""
        if self.sqlite_file and os.path.exists(self.sqlite_file):
            os.unlink(self.sqlite_file)
            self.sqlite_file = None
        if self.manifest_file and os.path.exists(self.manifest_file):
            os.unlink(self.manifest_file)
            self.manifest_file = None


def _extract_terminal_exit(
    wait_info: dict,
    graph_nodes: dict,
) -> str | None:
    """Return the exit stage ID from an agent's wait_info, or None."""
    if wait_info.get("mode") != "path":
        return None
    path_choices = wait_info.get("path_choices", {})
    stage = wait_info.get("current_target_stage")
    visited = set()
    while stage and stage in path_choices and stage not in visited:
        visited.add(stage)
        choices = path_choices[stage]
        if choices:
            stage = (
                choices[0][0] if isinstance(choices[0], (list, tuple)) else choices[0]
            )
        else:
            break
    if stage and stage in graph_nodes:
        node = graph_nodes[stage]
        if node.stage_type == "exit":
            return stage
    fallback = wait_info.get("current_target_stage")
    if (
        fallback
        and fallback in graph_nodes
        and graph_nodes[fallback].stage_type == "exit"
    ):
        return fallback
    return None


def _spawn_position(graph: "StageGraph", node_id: str) -> tuple[float, float] | None:
    """Where an agent standing on *node_id* is, for position-aware costs."""
    node = graph.nodes.get(node_id)
    if node is None:
        return None
    return (node.centroid_x, node.centroid_y)


def _assign_initial_exit(
    agent_id: int,
    wait_info: dict,
    graph: "StageGraph",
    cost_config,
    vis_model,
    time_s: float,
    seed: int,
    cognitive_maps: dict[int, AgentCognitiveMap],
    extinction_sampler,
    fed_rate_sampler=None,
    cached_segments: dict | None = None,
    required_exit: str | None = None,
    *,
    spawn_key: SpawnKey,
    agent_position: tuple[float, float] | None = None,
) -> str | None:
    """Point a freshly spawned agent at the best exit *it knows about*.

    The agent arrives holding a target picked by geometry alone -- the exit
    nearest its spawn point, chosen before it had a cognitive map. That is the
    wrong question: an agent who only knows the front door should walk to the
    front door however far it is. So the map is built first, then the exits are
    ranked on the subgraph the agent actually knows, by the same composite cost
    the reroute pass uses, and the cheapest one wins.

    Distances are measured from *agent_position*, where the agent stands, as
    the reroute pass measures them. Without it they run from the spawn area's
    node, which gives every agent of one spawn area the same exit (#350).

    ``exit_counts`` is deliberately not passed. Ranking against a tally that the
    very same loop is filling would let the queue term punish an exit for the
    agents already assigned to it, scattering a crowd that -- by hypothesis --
    all knows the same door. Congestion is a running condition, so it enters on
    reroute, not at t=0.

    With *required_exit* (exit replay) the agent takes the best ranked route to
    that exit, or the shortest graph path to it when the exit is outside the
    agent's map. Raises ExitReplayError when the exit cannot be reached.

    Returns the exit the agent is now heading for, or None when it knows no
    reachable exit, in which case the geometric assignment is left in place.
    """
    spawn_node = wait_info.get("current_origin") or wait_info.get(
        "current_target_stage"
    )
    if spawn_node is None or spawn_node not in graph.nodes:
        return None

    cmap = cognitive_maps.get(agent_id)
    if cmap is None:
        cmap = init_cognitive_map(
            spawn_node,
            graph,
            wait_info.get("familiarity", "full"),
            vis_model,
            time_s,
            # Same stream as the reroute pass, so an agent that reaches the
            # reroute loop first is given the identical map either way.
            rng=agent_rng(seed, spawn_key, PURPOSE_FAMILIARITY),
            entrance=wait_info.get("entrance"),
        )
        cognitive_maps[agent_id] = cmap

    ranked = rank_routes(
        graph,
        spawn_node,
        time_s,
        0.0,
        extinction_sampler,
        fed_rate_sampler,
        cost_config,
        cached_segments=cached_segments,
        cognitive_map=cmap,
        agent_position=agent_position,
    )
    if required_exit is not None:
        path = _replayed_path(graph, spawn_node, ranked, required_exit)
        if path is None:
            raise ExitReplayError(
                f"Replayed exit {required_exit!r} of agent {agent_id} is not "
                f"reachable from {spawn_node!r}."
            )
        return required_exit if _apply_initial_path(wait_info, path) else None
    ranked = [rc for rc in ranked if not rc.rejected] or ranked
    if not ranked:
        return None

    best = ranked[0]
    return best.exit_id if _apply_initial_path(wait_info, list(best.path)) else None


def _flow_origin(flow_dist: dict, source_id: int) -> str:
    """Return the replay origin of a flow source: its distribution key."""
    return f"flow:{flow_dist.get('dist_key') or source_id}"


def _check_flow_variants(flow_distributions: list, stage_map: dict) -> None:
    """Raise ValueError when a flow journey variant has no valid entry stage.

    A flow spawn draws its variant once, from its spawn key, so a variant that
    cannot be entered would be drawn again at every attempt and stall the
    source for the rest of the run.
    """
    for flow_dist in flow_distributions:
        for variant_info in flow_dist.get("journey_info") or []:
            _check_entry_stage(variant_info["variant_data"], stage_map, flow_dist)


def _check_entry_stage(variant: dict, stage_map: dict, flow_dist: dict) -> None:
    """Raise ValueError when a drawable *variant* has no valid entry stage.

    Zero-weight variants are skipped, although the picker can still return
    one on a draw of exactly 0.0 or through its first-variant fallback; both
    are negligible and rejecting such configs would break valid decks.
    """
    if float(variant.get("percentage", 0.0)) <= 0:
        return
    if any(stage_map.get(stage, -1) != -1 for stage in variant.get("entry_stages", [])):
        return
    name = variant.get("variant_name", variant.get("id"))
    raise ValueError(
        f"Flow distribution {flow_dist.get('dist_key')!r}: journey variant "
        f"{name!r} has no valid entry stage."
    )


class ExitReplayError(ValueError):
    """An agent cannot be given the exit it took in the replayed run."""


def _replayed_path(
    graph: "StageGraph", spawn_node: str, ranked: list, exit_id: str
) -> list[str] | None:
    """Return the route to *exit_id*: the best ranked one, else the shortest."""
    ordered = [rc for rc in ranked if not rc.rejected] + [
        rc for rc in ranked if rc.rejected
    ]
    for rc in ordered:
        if rc.exit_id == exit_id:
            return list(rc.path)
    found = graph.shortest_path_to(spawn_node, exit_id)
    return None if found is None else found[1]


def _apply_initial_path(wait_info: dict, path: list[str]) -> bool:
    """Point *wait_info* along *path*; return whether it was applied."""
    # Clear the geometric target so reroute_agent anchors on the spawn node and
    # writes the whole path, rather than treating the old exit as a waypoint.
    previous_stage = wait_info.get("current_target_stage")
    wait_info["current_target_stage"] = None
    reroute_agent(wait_info, path, wait_info.get("stage_configs", {}))
    if wait_info.get("current_target_stage") is None:
        # Nothing was applied, so ``target`` still points into the geometric
        # exit's polygon; keep that assignment whole rather than half-updating.
        wait_info["current_target_stage"] = previous_stage
        return False
    return True


# INITIAL_ORIGIN, SpawnKey and the key counter live in agent_seed, which
# simulation_init shares; the counter keeps its name here.
_spawn_key = assign_spawn_key


def _replayed_exit(
    replay_exits: Mapping[SpawnKey, str] | None, key: SpawnKey, agent_id: int
) -> str | None:
    """Return the exit the agent spawned at *key* took, or None.

    Raises ExitReplayError when replay is on and the key has no recorded exit.
    """
    if replay_exits is None:
        return None
    exit_id = replay_exits.get(key)
    if exit_id is None:
        raise ExitReplayError(
            f"--replay-exits has no exit for origin {key[0]!r} spawn index "
            f"{key[1]} (agent {agent_id}); replay needs the same scenario and seed."
        )
    return exit_id


def _check_replayed_exit(
    required_exit: str | None, heading: str | None, agent_id: int
) -> None:
    """Raise ExitReplayError when a replayed agent is not heading for its exit."""
    if required_exit is None or heading == required_exit:
        return
    raise ExitReplayError(
        f"Agent {agent_id} could not be sent to its replayed exit "
        f"{required_exit!r}; it is heading for {heading!r}."
    )


def _warn_unused_replay(
    replay_exits: Mapping[SpawnKey, str] | None, spawn_keys: dict[int, SpawnKey]
) -> None:
    """Warn when the replayed run spawned agents this run did not."""
    if replay_exits is None:
        return
    unused = set(replay_exits).difference(spawn_keys.values())
    if unused:
        _logger.warning(
            "--replay-exits: %d agent(s) of the replayed run were never spawned "
            "here (first: origin %r spawn index %d).",
            len(unused),
            *min(unused),
        )


def _replay_digest(replay_exits: Mapping[SpawnKey, str]) -> str:
    """Return a sha256 of the replayed rows, independent of their order."""
    rows = sorted(f"{o}\t{i}\t{e}" for (o, i), e in replay_exits.items())
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _check_run_modes(
    smoke_blind: bool,
    reroute_config,
    tenability_config,
    replay_exits: Mapping[SpawnKey, str] | None,
    stage_graph: "StageGraph | None",
) -> None:
    """Reject a smoke-blind run that would let smoke act, or a bad replay."""
    if smoke_blind and reroute_config is not None:
        raise ValueError("smoke_blind runs take no reroute_config")
    if smoke_blind and tenability_config is not None:
        raise ValueError("smoke_blind runs take no tenability_config")
    if replay_exits is None:
        return
    if stage_graph is None:
        raise ValueError("--replay-exits needs a scenario with exit stages")
    unknown = sorted(set(replay_exits.values()) - set(stage_graph.exit_nodes()))
    if unknown:
        raise ValueError(
            f"--replay-exits names exits this scenario lacks: {', '.join(unknown)}"
        )


def _has_exit_schedule(stage_graph: "StageGraph | None") -> bool:
    """Whether any exit of *stage_graph* opens or closes on a schedule."""
    if stage_graph is None:
        return False
    return any(
        node.open_from_s is not None or node.closed_after_s is not None
        for node in stage_graph.nodes.values()
    )


def _check_exit_schedule(has_schedule: bool, reroute_config, replay_exits) -> None:
    """Reject a scheduled exit in a run where no agent could leave it."""
    if has_schedule and reroute_config is None:
        raise ValueError(
            "Exits with open_from_s or closed_after_s need rerouting: agents "
            "heading for a closed exit are redirected by the reroute pass"
        )
    if has_schedule and replay_exits is not None:
        raise ValueError(
            "--replay-exits cannot be combined with exits that have "
            "open_from_s or closed_after_s: a replayed exit may be closed"
        )


def _check_path_agent(has_schedule: bool, wait_info: dict | None, agent_id) -> None:
    """Reject an agent the closure of an exit cannot hold back."""
    if has_schedule and (wait_info is None or wait_info.get("mode") != "path"):
        raise ValueError(
            f"Agent {agent_id} walks a JuPedSim journey, which leaves through "
            "an exit whether or not it is open; exits with open_from_s or "
            "closed_after_s need every agent on a routed path"
        )


def _heads_for_closed_exit(
    wait_info: dict, stage_graph: "StageGraph", time_s: float
) -> bool:
    """Whether the agent's path ends at an exit closed at *time_s*."""
    exit_id = _extract_terminal_exit(wait_info, stage_graph.nodes)
    return exit_id is not None and not stage_graph.nodes[exit_id].is_open(time_s)


def _migrate_journeys_v2(data: dict[str, Any]) -> None:
    """Backfill legacy ``journeys``/``transitions`` from the editor's ``journeys_v2``.

    The web UI saves routes as ``journeys_v2`` (id/name/color/sequence) with
    per-distribution ``journey_weights``, but the simulation loader only
    understands the legacy ``journeys`` (stages/transitions) shape — without
    this, scenarios saved from the editor have no ``journeys``/``transitions``,
    ``initialize_simulation_from_json`` decides the config needs fallback
    auto-routing, and the drawn route is silently never used.

    Only distributions with exactly one ``journey_weights`` entry are
    migrated: the legacy format has no equivalent for splitting a single
    distribution across multiple whole journeys, so ambiguous cases are left
    alone (existing fallback behaviour applies to those).
    """
    journeys_v2 = data.get("journeys_v2")
    if data.get("journeys") or not journeys_v2:
        return
    if not isinstance(journeys_v2, list):
        return

    sequences = {
        j["id"]: j["sequence"]
        for j in journeys_v2
        if isinstance(j, dict) and j.get("id") and j.get("sequence")
    }
    if not sequences:
        return

    used_ids: set = set()
    legacy_journeys = []
    legacy_transitions = []
    for dist_id, dist in data.get("distributions", {}).items():
        weights = dist.get("journey_weights") or []
        if len(weights) != 1:
            continue
        jid = weights[0].get("journey_id")
        sequence = sequences.get(jid)
        if not sequence:
            continue
        legacy_id = jid if jid not in used_ids else f"{jid}::{dist_id}"
        used_ids.add(legacy_id)
        stages = [dist_id, *sequence]
        transitions = [
            {"from": stages[i], "to": stages[i + 1], "journey_id": legacy_id}
            for i in range(len(stages) - 1)
        ]
        legacy_journeys.append(
            {"id": legacy_id, "stages": stages, "transitions": transitions}
        )
        legacy_transitions.extend(transitions)

    if legacy_journeys:
        data["journeys"] = legacy_journeys
        data["transitions"] = legacy_transitions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_scenario(path: str) -> Scenario:
    """Load a scenario from a directory, ZIP bundle, or JSON file."""
    import zipfile

    resolved = pathlib.Path(path).resolve()

    if resolved.is_dir():
        preferred_json = resolved / "config.json"
        preferred_wkt = resolved / "geometry.wkt"
        json_files = (
            [preferred_json]
            if preferred_json.exists()
            else sorted(resolved.glob("*.json"))
        )
        wkt_files = (
            [preferred_wkt]
            if preferred_wkt.exists()
            else sorted(resolved.glob("*.wkt"))
        )
        if not json_files or not wkt_files:
            raise ValueError(
                f"Scenario directory must contain one JSON and one WKT file: {resolved}"
            )
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        walkable_wkt = wkt_files[0].read_text(encoding="utf-8").strip()
        source_path = str(resolved)
    elif resolved.suffix.lower() == ".json":
        data = json.loads(resolved.read_text(encoding="utf-8"))
        walkable_wkt = data.get("walkable_area_wkt") or data.get("geometry", {}).get(
            "walkable_area_wkt"
        )
        if not walkable_wkt:
            sibling_wkts = sorted(resolved.parent.glob("*.wkt"))
            if sibling_wkts:
                walkable_wkt = sibling_wkts[0].read_text(encoding="utf-8").strip()
        if not walkable_wkt:
            raise ValueError(
                "Scenario JSON must define walkable_area_wkt or live next to a .wkt file."
            )
        source_path = str(resolved)
    else:
        source_path = str(resolved)
        with zipfile.ZipFile(source_path) as zf:
            names = zf.namelist()

            json_name = next((n for n in names if n.endswith(".json")), None)
            if json_name is None:
                raise ValueError(f"ZIP contains no JSON file. Found: {names}")
            data = json.loads(zf.read(json_name))

            wkt_name = next((n for n in names if n.endswith(".wkt")), None)
            if wkt_name is None:
                raise ValueError(f"ZIP contains no WKT file. Found: {names}")
            walkable_wkt = zf.read(wkt_name).decode("utf-8").strip()

    _migrate_journeys_v2(data)

    sim_settings = data.get("config", {}).get("simulation_settings", {})
    sim_params = sim_settings.get("simulationParams", {})
    model_type = sim_params.get("model_type", "CollisionFreeSpeedModel")
    seed = sim_settings.get("baseSeed", 42)

    sim_params.setdefault("max_simulation_time", 300)

    return Scenario(
        raw=data,
        walkable_area_wkt=walkable_wkt,
        model_type=model_type,
        seed=seed,
        sim_params=sim_params,
        source_path=source_path,
    )


def _recorded_free_speed(
    agent_speed_state: dict[int, dict[str, Any]], agent_id: int
) -> float | None:
    """Return the agent's speed recorded before any zone or FIC slowdown.

    A flow agent can be slowed by a zone or by FIC before its first smoke
    update, so its current speed is not its free speed.
    """
    original = agent_speed_state.get(agent_id, {}).get("original_speed")
    if original is None or float(original) <= 0.0:
        return None
    return float(original)


def _report_outside(
    smoke_history, fed_history, smoke_speed_model, fed_model, heat_fed_model
) -> dict[str, Any]:
    """Count the history rows sampled outside the FDS domain; log a summary.

    The smoke history counts when it is recorded, the FED history otherwise;
    each row stands for one update interval of its model.
    """
    rows, model = smoke_history, smoke_speed_model
    if not any("in_fds_domain" in r for r in rows[:1]):
        rows, model = fed_history, fed_model or heat_fed_model
    interval = float(getattr(getattr(model, "config", None), "update_interval_s", 0))
    counts = count_outside(rows, interval)
    if counts["rows"]:
        _logger.warning(
            "Outside the FDS domain: %d agent(s), %d sample(s), about %.1f "
            "agent-seconds read ambient air and clear sight there "
            "(in_fds_domain = False in the smoke and FED histories).",
            counts["agents"],
            counts["rows"],
            counts["agent_seconds"],
        )
    return counts


def run_scenario(
    scenario: Scenario,
    *,
    seed: int | None = None,
    smoke_speed_model=None,
    fed_model=None,
    heat_fed_model=None,
    tenability_config=None,
    reroute_config: RerouteConfig | None = None,
    collect_route_cost_history: bool = False,
    collect_cognitive_map_history: bool = False,
    vis_model=None,
    progress_callback: ProgressCallback | None = None,
    smoke_blind: bool = False,
    replay_exits: Mapping[SpawnKey, str] | None = None,
    require_fds_coverage: bool = False,
) -> ScenarioResult:
    """Run a scenario with the same shared setup/runtime semantics as the web app.

    When ``progress_callback`` is supplied it receives a :class:`ProgressEvent`
    at the same throttled cadence as the stdout progress line. The default
    ``None`` leaves runtime behavior unchanged.

    ``smoke_blind`` samples the smoke and FED models for the histories only:
    agents walk and choose exits as in clear air. It takes no
    ``reroute_config`` and no ``tenability_config``. ``replay_exits`` maps
    ``(origin, spawn_index)`` to the exit the agent spawned there took in an
    earlier run (see ``ScenarioResult.exit_history``); each path agent is sent
    there by the route clear-air costs rank best on its map.

    Before the first step the walkable area, exits, checkpoints, spawn areas,
    signs and route edges are checked against the FDS slice coverage, and
    whatever lies outside is logged (see ``fds_coverage``). With
    ``require_fds_coverage`` it is an error instead; the fields and the
    visibility model must then be built with the same flag so that a sample
    outside also raises. Smoke and FED history rows carry ``in_fds_domain``.
    """
    _require_jupedsim()
    from .simulation_init import (
        _find_nearest_exit,
        _random_point_in_polygon,
        build_agent_path_state,
        create_agent_parameters,
        initialize_simulation_from_json,
    )

    seed = seed if seed is not None else scenario.seed

    model = _build_model(scenario.model_type, scenario.sim_params)

    sqlite_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    output_file = sqlite_tmp.name
    sqlite_tmp.close()

    writer = jps.SqliteTrajectoryWriter(
        output_file=pathlib.Path(output_file),
        every_nth_frame=10,
    )
    simulation = jps.Simulation(
        model=model,
        geometry=scenario.walkable_polygon,
        trajectory_writer=writer,
    )

    config_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    try:
        json.dump(scenario.raw, config_tmp, indent=2)
        config_tmp.close()

        walkable_area = SimpleNamespace(polygon=scenario.walkable_polygon)
        global_parameters = SimpleNamespace(**scenario.sim_params)
        _, _positions, agent_radii, spawning_info = initialize_simulation_from_json(
            config_tmp.name,
            simulation,
            walkable_area,
            seed=seed,
            model_type=scenario.model_type,
            global_parameters=global_parameters,
        )

        initial_agent_count = simulation.agent_count()
        has_flow_spawning = spawning_info.get("has_flow_spawning", False)
        spawning_freqs_and_numbers = spawning_info.get("spawning_freqs_and_numbers", [])
        starting_pos_per_source = spawning_info.get("starting_pos_per_source", [])
        num_agents_per_source = spawning_info.get("num_agents_per_source", [])
        agent_counter_per_source = spawning_info.get("agent_counter_per_source", [])
        flow_distributions = spawning_info.get("flow_distributions", [])
        has_premovement = spawning_info.get("has_premovement", False)
        premovement_times = spawning_info.get("premovement_times", {})
        direct_steering_info = spawning_info.get("direct_steering_info", {})
        agent_wait_info = spawning_info.get("agent_wait_info", {})
        checkpoint_throughput_tracker = {}
        agent_speed_state: dict[int, dict[str, Any]] = {}
        smoke_speed_state: dict[int, float] = {}
        smoke_takes_free_speed = smoke_speed_model is not None and (
            sample_accepts_free_speed(smoke_speed_model.sample)
        )
        smoke_history: list[dict[str, Any]] = []
        fed_state: dict[int, dict[str, float]] = {}
        heat_fed_state: dict[int, dict[str, float]] = {}
        # Set only with --heat-endpoint; default rows keep their columns.
        heat_endpoint = getattr(heat_fed_model, "endpoint", None)
        fed_history: list[dict[str, Any]] = []
        incapacitated_agents: set[int] = set()
        # Which track (gas / heat / both) tripped incapacitation for each
        # agent -- the two doses are independent (see fed.py's
        # TenabilityConfig docstring), so "why" isn't recoverable from
        # fed_cumulative/heat_fed_cumulative alone once both are being
        # tracked.
        incapacitated_cause: dict[int, str] = {}
        # Per-agent incapacitation threshold (population variability). Sampled
        # lazily on first FED evaluation from the agent's own seeded stream, so
        # the draw does not depend on the order agents are first evaluated in;
        # deterministic mode reuses fed_threshold for all.
        incap_thresholds: dict[int, float] = {}
        # Independent stream for the heat track -- not the same dose as gas
        # FED, so its threshold draws must not be correlated with the gas ones.
        incap_heat_thresholds: dict[int, float] = {}

        def _incap_threshold(aid: int) -> float:
            t = incap_thresholds.get(aid)
            if t is None:
                if tenability_config is None:
                    t = float("inf")
                else:
                    rng = agent_rng(
                        seed, lookup_spawn_key(spawn_keys, aid), PURPOSE_INCAP_GAS
                    )
                    t = sample_incapacitation_threshold(tenability_config, rng)
                incap_thresholds[aid] = t
            return t

        def _incap_heat_threshold(aid: int) -> float:
            t = incap_heat_thresholds.get(aid)
            if t is None:
                if tenability_config is None:
                    t = float("inf")
                else:
                    rng = agent_rng(
                        seed, lookup_spawn_key(spawn_keys, aid), PURPOSE_INCAP_HEAT
                    )
                    t = sample_heat_incapacitation_threshold(tenability_config, rng)
                incap_heat_thresholds[aid] = t
            return t

        last_smoke_update_time = None
        last_fed_update_time = None
        last_reroute_check_time: float | None = None
        route_history: list[dict[str, Any]] = []
        # Exit each path agent is heading for, then the one it left through.
        agent_exits: dict[int, str] = {}
        # Run-local spawn order of every agent per origin, assigned where it
        # is added; JuPedSim ids can skip (#198). Per-agent draws are seeded
        # from it, and the JuPedSim id stays the lookup key.
        spawn_keys: dict[int, SpawnKey] = dict(spawning_info.get("spawn_keys", {}))
        origin_counts: dict[str, int] = dict(spawning_info.get("origin_counts", {}))
        route_cost_history: list[dict[str, Any]] = []
        agent_route_state: dict[int, AgentRouteState] = {}
        cognitive_maps: dict[int, AgentCognitiveMap] = {}
        cognitive_map_history: list[dict[str, Any]] = []
        # Size of each agent's map when it was last recorded, so a later frame
        # can be compared against the previous one and only changes recorded.
        _cmap_seen: dict[int, tuple[int, int]] = {}
        route_segment_cache: dict[tuple[str, str], Any] | None = None
        stage_graph: StageGraph | None = None
        distribution_stage_configs: dict[str, dict[str, Any]] = {}
        reroute_debug_printed = False
        reroute_debug_samples = 0
        _fed_rate_adapter = None
        # The graph is built whenever there are stages to walk between, not only
        # when rerouting is on: the initial exit choice is ranked on it too, and
        # that choice is made in every run.
        if direct_steering_info:
            stage_graph = StageGraph.from_scenario(
                direct_steering_info,
                scenario.raw.get("transitions", []),
                distributions=scenario.raw.get("distributions"),
                walkable_polygon=scenario.walkable_polygon,
            )
            route_segment_cache = {}
            # Spawn areas as steerable patrol stops. Stage configs are built
            # from direct_steering_info, which holds crossings and exits only,
            # so a wandering agent could never be routed back to its own
            # spawn area -- and an agent that knows nothing but its spawn and
            # the checkpoint it stands on would have no patrol at all.
            for _dist_id, _dist in (scenario.raw.get("distributions") or {}).items():
                _coords = _dist.get("coordinates")
                if _dist_id in stage_graph.nodes and _coords and len(_coords) >= 3:
                    distribution_stage_configs[_dist_id] = {
                        "polygon": Polygon(_coords),
                        "stage_type": "distribution",
                        "waiting_time": 0.0,
                        "waiting_time_distribution": "constant",
                        "waiting_time_std": 1.0,
                        "enable_throughput_throttling": False,
                        "max_throughput": 1.0,
                        "speed_factor": 1.0,
                    }
            # Not every FED model can be sampled ahead of the agent -- the
            # constant-input ones only know the dose here and now -- and route
            # costs are the one caller that needs the spatial rate.
            _fed_rate_adapter = (
                _FedRateAdapter(fed_model)
                if hasattr(fed_model, "sample_rate")
                else None
            )
            if reroute_config is not None:
                print(
                    "Reroute debug: "
                    f"nodes={len(stage_graph.nodes)} "
                    f"edges={sum(len(edges) for edges in stage_graph.edges.values())} "
                    f"direct_steering={len(direct_steering_info)} "
                    f"wait_info={len(agent_wait_info)}"
                )
        _check_run_modes(
            smoke_blind, reroute_config, tenability_config, replay_exits, stage_graph
        )
        has_exit_schedule = _has_exit_schedule(stage_graph)
        _check_exit_schedule(has_exit_schedule, reroute_config, replay_exits)
        # Pre-compute familiarity per distribution index. The value may be
        # "full", "discovery", or a probability in [0, 1] that each exit is
        # already known -- a real crowd is a gradient, not two camps.
        dist_familiarity: list = [
            d.get("parameters", {}).get("familiarity", "full")
            for d in scenario.raw.get("distributions", {}).values()
        ]
        # The exit each spawn area's occupants walked in through, which they
        # know whatever their familiarity.
        dist_entrance: list = [
            d.get("parameters", {}).get("entrance")
            for d in scenario.raw.get("distributions", {}).values()
        ]
        # Weights for the opening choice. With rerouting on these are the same
        # weights the reroute pass uses, so turning rerouting off changes when
        # routes are re-ranked, not how they are scored.
        initial_cost_config = (
            reroute_config.cost_config
            if reroute_config is not None
            else RouteCostConfig.from_routing_params(scenario.raw.get("routing"))
        )

        def _initial_exit_choice(
            agent_id: int,
            wait_info: dict,
            cached_segments: dict | None = None,
            origin: str = INITIAL_ORIGIN,
        ) -> str | None:
            """Re-target one just-spawned agent onto the best exit it knows.

            *cached_segments* is only safe to share between agents ranked at the
            same instant, since segment costs depend on the smoke field at that
            time; flow-spawned agents therefore pass nothing, and their
            *origin*.
            """
            if stage_graph is None or wait_info.get("mode") != "path":
                return None
            key = lookup_spawn_key(spawn_keys, agent_id, origin)
            required_exit = _replayed_exit(replay_exits, key, agent_id)
            # A replayed or smoke-blind choice is made as in clear air.
            clear_air = smoke_blind or required_exit is not None
            spawn_time = simulation.elapsed_time()
            chosen = _assign_initial_exit(
                agent_id,
                wait_info,
                stage_graph,
                initial_cost_config,
                vis_model,
                spawn_time,
                seed,
                cognitive_maps,
                extinction_sampler=(
                    smoke_speed_model.field
                    if smoke_speed_model is not None and not clear_air
                    else _ZERO_EXTINCTION
                ),
                fed_rate_sampler=None if clear_air else _fed_rate_adapter,
                cached_segments=cached_segments,
                required_exit=required_exit,
                spawn_key=key,
                agent_position=extract_agent_xy(simulation.agent(agent_id)),
            )
            terminal_exit = _extract_terminal_exit(wait_info, stage_graph.nodes)
            _check_replayed_exit(required_exit, terminal_exit, agent_id)
            if terminal_exit is not None:
                agent_exits[agent_id] = terminal_exit
            if chosen is not None and reroute_config is not None:
                # This *was* the agent's first route evaluation, so record it as
                # one. Otherwise the reroute pass fires its own first evaluation
                # in the same timestep, differing only in that it now sees an
                # exit_counts tally built from these very assignments -- and the
                # queue term promptly scatters a crowd that, by hypothesis, all
                # knows the same door. Congestion should redirect people once it
                # exists, not before anyone has taken a step.
                agent_route_state[agent_id] = AgentRouteState(
                    current_exit=chosen,
                    last_eval_time_s=spawn_time,
                    eval_offset_s=compute_eval_offset(
                        stagger_index(key), reroute_config.reevaluation_interval_s
                    ),
                )
            return chosen

        smoke_domain_fields = domain_fields(smoke_speed_model)
        fed_domain_fields = domain_fields(fed_model, heat_fed_model)
        fds_coverage = check_fds_coverage(
            walkable=scenario.walkable_polygon,
            raw=scenario.raw,
            samplers=model_samplers(smoke_speed_model, fed_model, heat_fed_model),
            stage_graph=stage_graph,
            vis_model=vis_model,
        )
        apply_coverage_policy(fds_coverage, require_fds_coverage=require_fds_coverage)

        # Every agent placed at t=0 arrived holding a geometrically nearest exit.
        # Re-decide it now that the graph exists, before exit_counts is seeded
        # from those assignments -- seeding first would tally the exits nobody
        # actually chose.
        _initial_segment_cache: dict = {}
        for _agent_id_init, _wi in agent_wait_info.items():
            _initial_exit_choice(_agent_id_init, _wi, _initial_segment_cache)

        for _agent in simulation.agents():
            _agent_id = int(_agent.id)
            _check_path_agent(
                has_exit_schedule, agent_wait_info.get(_agent_id), _agent_id
            )

        exit_counts: dict[str, int] = {}
        if reroute_config is not None and stage_graph is not None:
            # Initialise all exits to zero.
            for node_id, node in stage_graph.nodes.items():
                if node.stage_type == "exit":
                    exit_counts[node_id] = 0
            # Seed from initial agent assignments.
            for agent_id_init, wi in agent_wait_info.items():
                exit_id = _extract_terminal_exit(wi, stage_graph.nodes)
                if exit_id is not None:
                    exit_counts[exit_id] = exit_counts.get(exit_id, 0) + 1
                    if agent_id_init not in agent_route_state:
                        agent_route_state[agent_id_init] = AgentRouteState(
                            current_exit=exit_id,
                            eval_offset_s=compute_eval_offset(
                                stagger_index(
                                    lookup_spawn_key(spawn_keys, agent_id_init)
                                ),
                                reroute_config.reevaluation_interval_s,
                            ),
                        )
                    else:
                        agent_route_state[agent_id_init].current_exit = exit_id
        # Precompute whether any zone/checkpoint has a non-trivial speed factor.
        # When none do, skip the expensive per-agent update_checkpoint_speed loop.
        _has_speed_zones = (
            any(
                math.fabs(float(info.get("speed_factor", 1.0)) - 1.0) > 1e-9
                for info in direct_steering_info.values()
            )
            if direct_steering_info
            else False
        )
        _active_speed_zones = active_steering_zones(direct_steering_info)
        _check_flow_variants(flow_distributions, spawning_info.get("stage_map", {}))
        total_progress_agents = initial_agent_count + sum(num_agents_per_source)
        import time as _time

        _wall_start = _time.monotonic()
        last_progress_time = -1.0
        last_progress_agents = simulation.agent_count()

        while simulation.elapsed_time() < scenario.max_simulation_time:
            current_time = simulation.elapsed_time()
            current_agents = simulation.agent_count()
            all_spawned = not has_flow_spawning or sum(agent_counter_per_source) >= sum(
                num_agents_per_source
            )
            if current_agents == 0 and all_spawned:
                break
            spawned_agents = initial_agent_count + sum(agent_counter_per_source)
            evacuated_agents = max(0, spawned_agents - current_agents)
            if (
                current_time - last_progress_time >= 0.5
                or current_agents != last_progress_agents
            ):
                wall_elapsed = _time.monotonic() - _wall_start
                wall_m, wall_s = divmod(int(wall_elapsed), 60)
                pct = (
                    int(100 * evacuated_agents / total_progress_agents)
                    if total_progress_agents
                    else 0
                )
                print(
                    f"\rEvacuated {evacuated_agents}/{total_progress_agents}"
                    f"  sim={current_time:.1f}s"
                    f"  wall={wall_m}m{wall_s:02d}s"
                    f"  {pct}%   ",
                    end="",
                    flush=True,
                )
                if progress_callback is not None:
                    progress_callback(
                        ProgressEvent(
                            evacuated=evacuated_agents,
                            total=total_progress_agents,
                            sim_time=current_time,
                            wall_time=wall_elapsed,
                            pct=pct,
                        )
                    )
                last_progress_time = current_time
                last_progress_agents = current_agents
            if has_flow_spawning:
                current_time = simulation.elapsed_time()

                for source_id in range(len(spawning_freqs_and_numbers)):
                    if source_id >= len(flow_distributions):
                        continue

                    flow_dist = flow_distributions[source_id]
                    spawn_frequency = spawning_freqs_and_numbers[source_id][0]
                    next_spawn_time = flow_dist["start_time"] + (
                        agent_counter_per_source[source_id] * spawn_frequency
                    )

                    if (
                        agent_counter_per_source[source_id]
                        >= num_agents_per_source[source_id]
                    ):
                        continue
                    if (
                        current_time < flow_dist["start_time"]
                        or current_time > flow_dist["end_time"]
                    ):
                        continue
                    if current_time < next_spawn_time:
                        continue

                    flow_origin = _flow_origin(flow_dist, source_id)
                    for _ in range(spawning_freqs_and_numbers[source_id][1]):
                        spawned_this_attempt = False
                        selected_variant = None
                        selected_variant_info = None
                        fallback_exit_id = None

                        for j in range(len(starting_pos_per_source[source_id])):
                            pos_index = (agent_counter_per_source[source_id] + j) % len(
                                starting_pos_per_source[source_id]
                            )
                            position = starting_pos_per_source[source_id][pos_index]
                            flow_params = flow_dist["params"]
                            # Draws are keyed by the spawn this attempt would
                            # be, so a refused position does not shift them.
                            pending = pending_spawn_key(origin_counts, flow_origin)
                            added = False

                            try:
                                assigned_journey_id = None
                                assigned_stage_id = None

                                if flow_dist.get("journey_info"):
                                    distribution_journeys = flow_dist["journey_info"]
                                    total_weight = sum(
                                        variant_info["variant_data"]["percentage"]
                                        for variant_info in distribution_journeys
                                    )
                                    rand_val = (
                                        agent_rng(
                                            seed, pending, PURPOSE_VARIANT
                                        ).random()
                                        * total_weight
                                    )
                                    cumulative_weight = 0.0
                                    for variant_info in distribution_journeys:
                                        cumulative_weight += variant_info[
                                            "variant_data"
                                        ]["percentage"]
                                        if rand_val <= cumulative_weight:
                                            selected_variant_info = variant_info
                                            break
                                    if selected_variant_info is None:
                                        selected_variant_info = distribution_journeys[0]

                                    selected_variant = selected_variant_info[
                                        "variant_data"
                                    ]
                                    assigned_journey_id = selected_variant["id"]

                                    selected_stage_id = None
                                    for stage in selected_variant.get(
                                        "entry_stages", []
                                    ):
                                        if (
                                            stage in spawning_info["stage_map"]
                                            and spawning_info["stage_map"][stage] != -1
                                        ):
                                            selected_stage_id = spawning_info[
                                                "stage_map"
                                            ][stage]
                                            break
                                    if selected_stage_id is None:
                                        raise ValueError(
                                            f"No valid entry stage for variant {selected_variant.get('variant_name', selected_variant.get('id'))}"
                                        )
                                    assigned_stage_id = selected_stage_id
                                    uses_direct_steering = any(
                                        stage in direct_steering_info
                                        for stage in selected_variant.get(
                                            "actual_stages", []
                                        )
                                    )
                                    global_ds_journey_id = spawning_info.get(
                                        "global_ds_journey_id"
                                    )
                                    global_ds_stage_id = spawning_info.get(
                                        "global_ds_stage_id"
                                    )
                                    if (
                                        uses_direct_steering
                                        and global_ds_journey_id is not None
                                        and global_ds_stage_id is not None
                                    ):
                                        assigned_journey_id = global_ds_journey_id
                                        assigned_stage_id = global_ds_stage_id
                                else:
                                    nearest_exit_stage_id = _find_nearest_exit(
                                        position,
                                        stage_map=spawning_info.get("stage_map"),
                                        exits=spawning_info.get("exits"),
                                        exit_geometries=spawning_info.get(
                                            "exit_geometries"
                                        ),
                                    )
                                    # _find_nearest_exit returns the exit key
                                    # (e.g. "jps-exits_0") when exit_geometries
                                    # is provided, or an integer stage id
                                    # otherwise.  Resolve to the exit key for
                                    # direct_steering_info lookup.
                                    stage_map = spawning_info.get("stage_map", {})
                                    if nearest_exit_stage_id in stage_map:
                                        # Already an exit key string
                                        fallback_exit_id = nearest_exit_stage_id
                                    else:
                                        # Integer stage id – reverse-lookup
                                        stage_id_to_exit = {
                                            v: k for k, v in stage_map.items()
                                        }
                                        fallback_exit_id = stage_id_to_exit.get(
                                            nearest_exit_stage_id
                                        )
                                    nearest_journey_id = spawning_info.get(
                                        "exit_to_journey", {}
                                    ).get(nearest_exit_stage_id)
                                    if nearest_journey_id is not None:
                                        assigned_journey_id = nearest_journey_id
                                        assigned_stage_id = nearest_exit_stage_id
                                    else:
                                        global_ds_journey_id = spawning_info.get(
                                            "global_ds_journey_id"
                                        )
                                        global_ds_stage_id = spawning_info.get(
                                            "global_ds_stage_id"
                                        )
                                        if (
                                            global_ds_journey_id is None
                                            or global_ds_stage_id is None
                                        ):
                                            raise ValueError(
                                                "Missing exit journey mapping and no fallback direct-steering journey is available"
                                            )
                                        assigned_journey_id = global_ds_journey_id
                                        assigned_stage_id = global_ds_stage_id

                                agent_parameters = create_agent_parameters(
                                    model_type=spawning_info["model_type"],
                                    position=position,
                                    params=flow_params,
                                    global_params=spawning_info["global_parameters"],
                                    journey_id=assigned_journey_id,
                                    stage_id=assigned_stage_id,
                                )

                                agent_id = simulation.add_agent(agent_parameters)
                                # From here on the agent exists, so a failure
                                # is raised rather than retried elsewhere.
                                added = True
                                key = commit_spawn_key(
                                    spawn_keys, origin_counts, agent_id, pending
                                )
                                agent_radii[agent_id] = flow_params.get("radius", 0.2)
                                # print(
                                #     "Spawned flow agent "
                                #     f"{agent_id} from source {source_id} at t={current_time:.2f}s "
                                #     f"pos=({float(position[0]):.3f}, {float(position[1]):.3f}) "
                                #     f"journey={getattr(agent_parameters, 'journey_id', None)} "
                                #     f"stage={getattr(agent_parameters, 'stage_id', None)}"

                                if (
                                    selected_variant
                                    and agent_wait_info is not None
                                    and direct_steering_info
                                ):
                                    path_state = build_agent_path_state(
                                        variant_data=selected_variant,
                                        journey_key=(
                                            selected_variant_info.get(
                                                "original_journey_id"
                                            )
                                            if selected_variant_info
                                            else None
                                        ),
                                        transitions=spawning_info.get(
                                            "transitions", []
                                        ),
                                        direct_steering_info=direct_steering_info,
                                        waypoint_routing=spawning_info.get(
                                            "waypoint_routing", {}
                                        ),
                                        seed=seed,
                                        agent_id=agent_id,
                                        initial_position=(
                                            float(position[0]),
                                            float(position[1]),
                                        ),
                                        agent_radius=float(
                                            flow_params.get("radius", 0.2)
                                        ),
                                        spawn_origin=flow_dist.get("dist_key"),
                                        spawn_key=key,
                                    )
                                    if path_state:
                                        agent_wait_info[agent_id] = path_state
                                        _dist_idx = flow_dist.get(
                                            "dist_index", source_id
                                        )
                                        _fam = (
                                            dist_familiarity[_dist_idx]
                                            if _dist_idx < len(dist_familiarity)
                                            else "full"
                                        )
                                        path_state["familiarity"] = _fam
                                        path_state["entrance"] = (
                                            dist_entrance[_dist_idx]
                                            if _dist_idx < len(dist_entrance)
                                            else None
                                        )
                                        _initial_exit_choice(
                                            agent_id,
                                            path_state,
                                            origin=_flow_origin(flow_dist, source_id),
                                        )
                                        if path_state and stage_graph is not None:
                                            _spawn_exit = _extract_terminal_exit(
                                                path_state, stage_graph.nodes
                                            )
                                            if _spawn_exit is not None:
                                                exit_counts[_spawn_exit] = (
                                                    exit_counts.get(_spawn_exit, 0) + 1
                                                )
                                                if (
                                                    reroute_config is not None
                                                    and agent_id
                                                    not in agent_route_state
                                                ):
                                                    agent_route_state[agent_id] = (
                                                        AgentRouteState(
                                                            eval_offset_s=compute_eval_offset(
                                                                stagger_index(key),
                                                                reroute_config.reevaluation_interval_s,
                                                            ),
                                                            current_exit=_spawn_exit,
                                                        )
                                                    )
                                elif (
                                    not selected_variant
                                    and agent_wait_info is not None
                                    and direct_steering_info
                                ):
                                    exit_id = fallback_exit_id
                                    if exit_id and exit_id in direct_steering_info:
                                        exit_info = direct_steering_info[exit_id]
                                        target_rng = agent_rng(
                                            seed, key, PURPOSE_TARGET
                                        )
                                        target = _random_point_in_polygon(
                                            exit_info["polygon"],
                                            target_rng,
                                        )
                                        stage_configs = {}
                                        for sk, info in direct_steering_info.items():
                                            stage_configs[sk] = {
                                                "polygon": info.get("polygon"),
                                                "stage_type": info.get(
                                                    "stage_type", "exit"
                                                ),
                                                "waiting_time": float(
                                                    info.get("waiting_time", 0.0)
                                                ),
                                                "waiting_time_distribution": info.get(
                                                    "waiting_time_distribution",
                                                    "constant",
                                                ),
                                                "waiting_time_std": float(
                                                    info.get("waiting_time_std", 1.0)
                                                ),
                                                "enable_throughput_throttling": bool(
                                                    info.get(
                                                        "enable_throughput_throttling",
                                                        False,
                                                    )
                                                ),
                                                "max_throughput": float(
                                                    info.get("max_throughput", 1.0)
                                                ),
                                                "speed_factor": float(
                                                    info.get("speed_factor", 1.0)
                                                ),
                                            }
                                        agent_wait_info[agent_id] = {
                                            "mode": "path",
                                            "path_choices": {},
                                            "stage_configs": stage_configs,
                                            "current_origin": flow_dist.get(
                                                "dist_key", exit_id
                                            ),
                                            "current_target_stage": exit_id,
                                            "target": target,
                                            "target_assigned": False,
                                            "state": "to_target",
                                            "wait_until": None,
                                            "inside_since": None,
                                            "reach_penetration": 0.25,
                                            "reach_dwell_seconds": 0.2,
                                            "step_index": 0,
                                            **steering_seeds(seed, key),
                                            "familiarity": dist_familiarity[
                                                flow_dist.get("dist_index", source_id)
                                            ]
                                            if flow_dist.get("dist_index", source_id)
                                            < len(dist_familiarity)
                                            else "full",
                                            "entrance": dist_entrance[
                                                flow_dist.get("dist_index", source_id)
                                            ]
                                            if flow_dist.get("dist_index", source_id)
                                            < len(dist_entrance)
                                            else None,
                                        }
                                        _initial_exit_choice(
                                            agent_id,
                                            agent_wait_info[agent_id],
                                            origin=_flow_origin(flow_dist, source_id),
                                        )
                                        if stage_graph is not None:
                                            _spawn_exit = _extract_terminal_exit(
                                                agent_wait_info[agent_id],
                                                stage_graph.nodes,
                                            )
                                            if _spawn_exit is not None:
                                                exit_counts[_spawn_exit] = (
                                                    exit_counts.get(_spawn_exit, 0) + 1
                                                )
                                                if (
                                                    reroute_config is not None
                                                    and agent_id
                                                    not in agent_route_state
                                                ):
                                                    agent_route_state[agent_id] = (
                                                        AgentRouteState(
                                                            eval_offset_s=compute_eval_offset(
                                                                stagger_index(key),
                                                                reroute_config.reevaluation_interval_s,
                                                            ),
                                                            current_exit=_spawn_exit,
                                                        )
                                                    )

                                spawned_this_attempt = True
                                break
                            except (FdsHorizonError, ExitReplayError, SpawnKeyError):
                                raise
                            except Exception:
                                if added:
                                    raise
                                continue

                        if not spawned_this_attempt:
                            print(
                                "Flow spawn attempt failed "
                                f"for source {source_id} at t={current_time:.2f}s "
                                f"after trying {len(starting_pos_per_source[source_id])} candidate positions"
                            )
                            break
                        agent_counter_per_source[source_id] += 1

            if has_premovement:
                current_time = simulation.elapsed_time()
                for agent in simulation.agents():
                    agent_id = agent.id
                    if (
                        agent_id in premovement_times
                        and not premovement_times[agent_id]["activated"]
                    ):
                        if (
                            current_time
                            >= premovement_times[agent_id]["premovement_time"]
                        ):
                            desired_speed = premovement_times[agent_id]["desired_speed"]
                            set_agent_desired_speed(agent, desired_speed)
                            speed_state = ensure_agent_speed_state(
                                agent_speed_state, agent_id, agent
                            )
                            speed_state["original_speed"] = float(desired_speed)
                            speed_state["active_checkpoint"] = None
                            premovement_times[agent_id]["activated"] = True

            if smoke_speed_model is not None:
                current_time = simulation.elapsed_time()
                if (
                    last_smoke_update_time is None
                    or current_time - last_smoke_update_time
                    >= smoke_speed_model.config.update_interval_s
                ):
                    for agent in simulation.agents():
                        agent_id = int(agent.id)
                        if agent_id in incapacitated_agents:
                            continue
                        premovement_active = (
                            agent_id in premovement_times
                            and not premovement_times[agent_id]["activated"]
                        )
                        base_speed = smoke_speed_state.get(agent_id)
                        if base_speed is None:
                            base_speed = _recorded_free_speed(
                                agent_speed_state, agent_id
                            )
                        current_speed = get_agent_desired_speed(agent)
                        if base_speed is None and current_speed is not None:
                            if current_speed > 0:
                                base_speed = float(current_speed)
                            elif agent_id in premovement_times:
                                base_speed = float(
                                    premovement_times[agent_id]["desired_speed"]
                                )
                            else:
                                base_speed = float(current_speed)
                        if base_speed is not None:
                            smoke_speed_state[agent_id] = base_speed
                        if base_speed is None:
                            raise RuntimeError(
                                "Smoke-speed updates require a documented JuPedSim runtime "
                                "speed attribute; could not read one for agent "
                                f"{agent_id} in model {type(getattr(agent, 'model', None)).__name__}."
                            )
                        x, y = extract_agent_xy(agent)
                        if x is None or y is None:
                            continue
                        sample_kwargs = (
                            {"free_speed_m_per_s": base_speed}
                            if smoke_takes_free_speed
                            else {}
                        )
                        extinction, speed_factor = smoke_speed_model.sample(
                            current_time, x, y, **sample_kwargs
                        )
                        desired_speed = base_speed * speed_factor
                        if smoke_blind:
                            # Record K only; the agent walks as in clear air.
                            speed_factor, desired_speed = 1.0, base_speed
                        elif direct_steering_info:
                            set_agent_smoke_factor(
                                agent_speed_state,
                                agent_id,
                                agent,
                                speed_factor,
                            )
                        elif not premovement_active:
                            set_agent_desired_speed(agent, desired_speed)
                        smoke_history.append(
                            {
                                "time_s": round(float(current_time), 6),
                                "agent_id": agent_id,
                                "x": float(x),
                                "y": float(y),
                                "base_speed": float(base_speed),
                                "desired_speed": float(desired_speed),
                                "speed_factor": float(speed_factor),
                                "extinction_per_m": float(extinction),
                            }
                        )
                        if smoke_domain_fields:
                            smoke_history[-1]["in_fds_domain"] = in_fds_domain(
                                smoke_domain_fields, x, y
                            )
                    last_smoke_update_time = current_time

            if fed_model is not None or heat_fed_model is not None:
                current_time = simulation.elapsed_time()
                _interval_source = (
                    fed_model if fed_model is not None else heat_fed_model
                )
                fed_update_interval_s = max(
                    0.0,
                    float(
                        getattr(
                            getattr(_interval_source, "config", None),
                            "update_interval_s",
                            0.0,
                        )
                    ),
                )
                if (
                    last_fed_update_time is None
                    or current_time - last_fed_update_time >= fed_update_interval_s
                ):
                    for agent in simulation.agents():
                        agent_id = int(agent.id)
                        x, y = extract_agent_xy(agent)
                        if x is None or y is None:
                            continue

                        cumulative = None
                        if fed_model is not None:
                            state = fed_state.setdefault(
                                agent_id,
                                {
                                    "cumulative": 0.0,
                                    "last_update_s": float(current_time),
                                },
                            )
                            dt_s = max(
                                0.0,
                                float(current_time) - float(state["last_update_s"]),
                            )
                            advance_with_components = getattr(
                                fed_model, "advance_with_components", None
                            )
                            if advance_with_components is not None:
                                inputs, components, cumulative = (
                                    advance_with_components(
                                        current_time,
                                        x,
                                        y,
                                        dt_s=dt_s,
                                        current_fed=state["cumulative"],
                                    )
                                )
                            else:
                                inputs, _rate_per_min, cumulative = fed_model.advance(
                                    current_time,
                                    x,
                                    y,
                                    dt_s=dt_s,
                                    current_fed=state["cumulative"],
                                )
                                components = default_fed_components(inputs)
                            state["cumulative"] = float(cumulative)
                            state["last_update_s"] = float(current_time)
                        else:
                            inputs = DefaultFedInputs()
                            components = default_fed_components(inputs)

                        heat_cumulative = None
                        if heat_fed_model is not None:
                            heat_state = heat_fed_state.setdefault(
                                agent_id,
                                {
                                    "cumulative": 0.0,
                                    "last_update_s": float(current_time),
                                },
                            )
                            heat_dt_s = max(
                                0.0,
                                float(current_time)
                                - float(heat_state["last_update_s"]),
                            )
                            (
                                heat_inputs,
                                heat_rate_per_min,
                                heat_cumulative,
                            ) = heat_fed_model.advance(
                                current_time,
                                x,
                                y,
                                dt_s=heat_dt_s,
                                current_fed=heat_state["cumulative"],
                            )
                            heat_state["cumulative"] = float(heat_cumulative)
                            heat_state["last_update_s"] = float(current_time)
                        else:
                            heat_inputs = HeatFedInputs()
                            heat_rate_per_min = 0.0

                        fic_value = default_fic(inputs)
                        incapacitated_now = agent_id in incapacitated_agents
                        fic_speed_factor = 1.0
                        if tenability_config is not None and not incapacitated_now:
                            gas_crossed = (
                                fed_model is not None
                                and tenability_config.enable_incapacitation
                                and cumulative is not None
                                and cumulative >= _incap_threshold(agent_id)
                            )
                            heat_crossed = (
                                heat_fed_model is not None
                                and tenability_config.enable_heat_incapacitation
                                and heat_cumulative is not None
                                and heat_cumulative >= _incap_heat_threshold(agent_id)
                            )
                            if gas_crossed or heat_crossed:
                                incapacitated_agents.add(agent_id)
                                incapacitated_cause[agent_id] = (
                                    "gas+heat"
                                    if (gas_crossed and heat_crossed)
                                    else ("gas" if gas_crossed else "heat")
                                )
                                set_agent_desired_speed(agent, 0.0)
                                incapacitated_now = True
                                # Pin the baseline too so downstream speed
                                # restorations (checkpoint / direct-steering
                                # update_checkpoint_speed, Frantzich smoke
                                # reapplication) can't un-incapacitate the
                                # agent by resetting to the pre-collapse v0.
                                speed_state = agent_speed_state.get(agent_id)
                                if speed_state is not None:
                                    speed_state["original_speed"] = 0.0
                                    speed_state["smoke_factor"] = 1.0
                                    speed_state["fic_factor"] = 1.0
                                    speed_state["active_checkpoint"] = None
                                smoke_speed_state[agent_id] = 0.0
                            elif (
                                fed_model is not None
                                and tenability_config.enable_fic_speed
                                and fic_value > 0.0
                            ):
                                fic_speed_factor = max(
                                    float(tenability_config.fic_min_factor),
                                    1.0
                                    - float(tenability_config.fic_alpha) * fic_value,
                                )
                                set_agent_fic_factor(
                                    agent_speed_state,
                                    agent_id,
                                    agent,
                                    fic_speed_factor,
                                )

                        desired_speed_now = get_agent_desired_speed(agent)
                        base_speed_logged = smoke_speed_state.get(agent_id)
                        if base_speed_logged is None and desired_speed_now is not None:
                            base_speed_logged = float(desired_speed_now)
                        effective_factor = 0.0
                        if (
                            base_speed_logged is not None
                            and base_speed_logged > 0.0
                            and desired_speed_now is not None
                        ):
                            effective_factor = float(desired_speed_now) / float(
                                base_speed_logged
                            )
                        fed_history.append(
                            {
                                "time_s": round(float(current_time), 6),
                                "agent_id": agent_id,
                                "x": float(x),
                                "y": float(y),
                                "co_percent": float(inputs.co_volume_fraction_percent),
                                "co2_percent": float(
                                    inputs.co2_volume_fraction_percent
                                ),
                                "o2_percent": float(inputs.o2_volume_fraction_percent),
                                "hcn_ppm": float(inputs.hcn_ppm),
                                "no_ppm": float(inputs.no_ppm),
                                "no2_ppm": float(inputs.no2_ppm),
                                "co_rate_per_min": float(components.co_rate_per_min),
                                "cn_rate_per_min": float(components.cn_rate_per_min),
                                "nox_rate_per_min": float(components.nox_rate_per_min),
                                "fld_rate_per_min": float(components.fld_rate_per_min),
                                "hv_co2": float(components.hv_co2),
                                "o2_rate_per_min": float(components.o2_rate_per_min),
                                "fed_rate_per_min": float(
                                    components.total_rate_per_min
                                ),
                                "fed_cumulative": float(cumulative)
                                if cumulative is not None
                                else 0.0,
                                "temperature_celsius": float(
                                    heat_inputs.temperature_celsius
                                ),
                                "heat_fed_rate_per_min": float(heat_rate_per_min),
                                "heat_fed_cumulative": float(heat_cumulative)
                                if heat_cumulative is not None
                                else 0.0,
                                "incapacitation_cause": incapacitated_cause.get(
                                    agent_id, ""
                                ),
                                "fic": float(fic_value),
                                "fic_speed_factor": float(fic_speed_factor),
                                "incapacitated": bool(incapacitated_now),
                                "base_speed": float(base_speed_logged)
                                if base_speed_logged is not None
                                else 0.0,
                                "desired_speed": float(desired_speed_now)
                                if desired_speed_now is not None
                                else 0.0,
                                "speed_factor": float(effective_factor),
                            }
                        )
                        fed_history[-1].update(
                            heat_endpoint_row_fields(
                                heat_endpoint, float(heat_inputs.temperature_celsius)
                            )
                        )
                        fed_history[-1].update(
                            heat_flux_row_fields(
                                heat_fed_model,
                                float(heat_inputs.temperature_celsius),
                                heat_inputs.layer_temperature_celsius,
                                integrated_intensity_kw_m2=heat_inputs.integrated_intensity_kw_m2,
                            )
                        )
                        if fed_domain_fields:
                            fed_history[-1]["in_fds_domain"] = in_fds_domain(
                                fed_domain_fields, x, y
                            )
                    last_fed_update_time = current_time

            if (
                reroute_config is not None
                and stage_graph is not None
                and agent_wait_info
                and (
                    last_reroute_check_time is None
                    or simulation.elapsed_time() - last_reroute_check_time >= 1.0
                )
            ):
                current_time = simulation.elapsed_time()
                extinction_sampler = (
                    smoke_speed_model.field
                    if smoke_speed_model is not None
                    else _ZERO_EXTINCTION
                )
                # Scope the route segment cache to a single reroute-check pass.
                # Segment costs depend on current_time and the time-varying smoke field,
                # so we clear any previously cached values computed at different times.
                route_segment_cache = {}
                last_reroute_check_time = current_time
                reroute_loop_agents = 0
                for agent in simulation.agents():
                    agent_id = int(agent.id)
                    wait_info = agent_wait_info.get(agent_id)
                    # Agents placed at t=0 are checked at setup; this catches
                    # flow-spawned ones at the first check after they enter.
                    _check_path_agent(has_exit_schedule, wait_info, agent_id)
                    if wait_info is None or wait_info.get("mode") != "path":
                        continue
                    reroute_loop_agents += 1
                    if wait_info.get("state") == "done":
                        continue
                    # Spawn areas become steerable patrol stops for wander.
                    for _dist_id, _cfg in distribution_stage_configs.items():
                        wait_info["stage_configs"].setdefault(_dist_id, _cfg)
                    # Initialize route state on first encounter.
                    if agent_id not in agent_route_state:
                        agent_route_state[agent_id] = AgentRouteState(
                            eval_offset_s=compute_eval_offset(
                                stagger_index(lookup_spawn_key(spawn_keys, agent_id)),
                                reroute_config.reevaluation_interval_s,
                            ),
                        )
                    # Initialize cognitive map on first encounter.
                    if agent_id not in cognitive_maps and stage_graph is not None:
                        spawn_node = wait_info.get("current_origin") or wait_info.get(
                            "current_target_stage"
                        )
                        if spawn_node is not None:
                            familiarity = wait_info.get("familiarity", "full")
                            cognitive_maps[agent_id] = init_cognitive_map(
                                spawn_node,
                                stage_graph,
                                familiarity,
                                vis_model,
                                current_time,
                                # Seeded per agent so a probabilistic draw is
                                # reproducible under a fixed run seed.
                                rng=agent_rng(
                                    seed,
                                    lookup_spawn_key(spawn_keys, agent_id),
                                    PURPOSE_FAMILIARITY,
                                ),
                                entrance=wait_info.get("entrance"),
                            )
                    rs = agent_route_state[agent_id]
                    # Force the very first evaluation to happen immediately (at
                    # spawn), regardless of the staggering offset, so agents that
                    # know a better route than their scripted spawn journey — e.g.
                    # a 'full' agent that can head straight for the exit — commit
                    # to it before drifting along the default path. Later
                    # evaluations keep the staggered cadence.
                    first_eval = rs.last_eval_time_s == -math.inf
                    # An agent heading for a closed exit re-decides now.
                    first_eval = first_eval or (
                        has_exit_schedule
                        and _heads_for_closed_exit(wait_info, stage_graph, current_time)
                    )
                    if not first_eval and not should_reevaluate(
                        current_time, rs, reroute_config.reevaluation_interval_s
                    ):
                        continue
                    current_fed = fed_state.get(agent_id, {}).get("cumulative", 0.0)
                    if reroute_debug_samples < 5:
                        source = wait_info.get("current_origin") or wait_info.get(
                            "current_target_stage"
                        )
                        print(
                            "Reroute debug agent: "
                            f"time={current_time:.2f} "
                            f"agent={agent_id} "
                            f"origin={wait_info.get('current_origin')} "
                            f"target={wait_info.get('current_target_stage')} "
                            f"source={source} "
                            f"state={wait_info.get('state')} "
                            f"in_graph={source in stage_graph.nodes if source is not None else False}"
                        )
                        reroute_debug_samples += 1
                    # Expand cognitive map from current position before reevaluation.
                    _cmap = cognitive_maps.get(agent_id)
                    _pos = wait_info.get("current_position")
                    if _cmap is not None and stage_graph is not None:
                        _cur_node = wait_info.get("current_origin") or wait_info.get(
                            "current_target_stage"
                        )
                        if _cur_node is not None and _pos is not None:
                            expand_from_visibility(
                                _cmap,
                                _cur_node,
                                stage_graph,
                                vis_model,
                                current_time,
                                _pos[0],
                                _pos[1],
                            )
                    if collect_route_cost_history:
                        source = wait_info.get("current_origin") or wait_info.get(
                            "current_target_stage"
                        )
                        if source is not None and source in stage_graph.nodes:
                            ranked = rank_routes(
                                stage_graph,
                                source,
                                current_time,
                                current_fed,
                                extinction_sampler,
                                _fed_rate_adapter,
                                reroute_config.cost_config,
                                cached_segments=route_segment_cache,
                                exit_counts=exit_counts,
                                cognitive_map=_cmap,
                                agent_position=tuple(_pos)
                                if _pos is not None
                                else None,
                                current_exit=rs.current_exit or None,
                                current_target=wait_info.get("current_target_stage"),
                            )
                            for route_rank, rc in enumerate(ranked, start=1):
                                _exit_node = stage_graph.nodes.get(rc.exit_id)
                                _exit_cap = (
                                    _exit_node.capacity_agents_per_s
                                    if _exit_node is not None
                                    and _exit_node.capacity_agents_per_s is not None
                                    else reroute_config.cost_config.default_exit_capacity
                                )
                                route_cost_history.append(
                                    {
                                        "time_s": round(float(current_time), 6),
                                        "agent_id": agent_id,
                                        "source": source,
                                        "current_exit": rs.current_exit or "",
                                        "current_fed": float(current_fed),
                                        "route_rank": route_rank,
                                        "exit_id": rc.exit_id,
                                        "path": " > ".join(rc.path),
                                        "path_length_m": float(rc.path_length_m),
                                        "k_ave_route": float(rc.k_ave_route),
                                        "travel_time_s": float(rc.travel_time_s),
                                        "fed_max_route": float(rc.fed_max_route),
                                        "composite_cost": float(rc.composite_cost),
                                        # The gate's own diagnostics. Without
                                        # them its decisions cannot be audited
                                        # from its output: composite_cost does
                                        # not rank under the gate, and the sight
                                        # that decides feasibility is invisible.
                                        "rank_cost": float(rc.rank_cost),
                                        "k_max_route": float(rc.k_max_route),
                                        "tau_route": float(rc.tau_route),
                                        "k_leg_max": float(rc.k_leg_max),
                                        "clean": bool(rc.clean),
                                        "feasible": bool(rc.feasible),
                                        "rejected": bool(rc.rejected),
                                        "rejection_reason": rc.rejection_reason or "",
                                        "queue_time_s": float(rc.queue_time_s),
                                        "exit_count": exit_counts.get(rc.exit_id, 0),
                                        "exit_capacity": float(_exit_cap),
                                    }
                                )
                    switch = evaluate_and_reroute(
                        agent_id=agent_id,
                        wait_info=wait_info,
                        route_state=rs,
                        graph=stage_graph,
                        current_time_s=current_time,
                        current_fed=current_fed,
                        extinction_sampler=extinction_sampler,
                        fed_rate_sampler=_fed_rate_adapter,
                        config=reroute_config,
                        cached_segments=route_segment_cache,
                        exit_counts=exit_counts,
                        cognitive_map=_cmap,
                        agent_position=tuple(_pos) if _pos is not None else None,
                    )
                    if switch is not None:
                        # Update exit_counts: decrement old, increment new.
                        if switch.old_exit and switch.old_exit in exit_counts:
                            exit_counts[switch.old_exit] = max(
                                0, exit_counts[switch.old_exit] - 1
                            )
                        if switch.new_exit in exit_counts:
                            exit_counts[switch.new_exit] = (
                                exit_counts.get(switch.new_exit, 0) + 1
                            )
                        agent_exits[switch.agent_id] = switch.new_exit
                        route_history.append(
                            {
                                "time_s": round(float(switch.time_s), 6),
                                "agent_id": switch.agent_id,
                                "old_exit": switch.old_exit or "",
                                "new_exit": switch.new_exit,
                                "old_cost": round(float(switch.old_cost), 4)
                                if switch.old_cost is not None
                                else "",
                                "new_cost": round(float(switch.new_cost), 4),
                                "reason": switch.reason,
                            }
                        )
                if not reroute_debug_printed:
                    print(
                        "Reroute debug pass: "
                        f"time={current_time:.2f} "
                        f"path_agents={reroute_loop_agents} "
                        f"route_cost_rows={len(route_cost_history)} "
                        f"switches={len(route_history)}"
                    )
                    reroute_debug_printed = True

            if direct_steering_info:
                current_time = simulation.elapsed_time()
                agents_by_id = {}
                live_agent_ids = set()
                _need_speed_update = _has_speed_zones or (
                    smoke_speed_model is not None and not smoke_blind
                )
                for agent in simulation.agents():
                    agent_id = int(agent.id)
                    live_agent_ids.add(agent_id)
                    if agent_wait_info:
                        agents_by_id[agent_id] = agent
                    if _need_speed_update:
                        x, y = extract_agent_xy(agent)
                        if x is None or y is None:
                            continue
                        update_checkpoint_speed(
                            agent_speed_state,
                            direct_steering_info,
                            agent_id,
                            agent,
                            None,
                            None,
                            x,
                            y,
                            active_zones=_active_speed_zones,
                        )
                if agent_speed_state:
                    for tracked_agent_id in list(agent_speed_state.keys()):
                        if tracked_agent_id not in live_agent_ids:
                            agent_speed_state.pop(tracked_agent_id, None)
                if agent_route_state:
                    for tracked_agent_id in list(agent_route_state.keys()):
                        if tracked_agent_id not in live_agent_ids:
                            removed_state = agent_route_state.pop(
                                tracked_agent_id, None
                            )
                            cognitive_maps.pop(tracked_agent_id, None)
                            if (
                                removed_state is not None
                                and removed_state.current_exit
                                and removed_state.current_exit in exit_counts
                            ):
                                exit_counts[removed_state.current_exit] = max(
                                    0,
                                    exit_counts[removed_state.current_exit] - 1,
                                )

            if direct_steering_info and agent_wait_info:
                for agent_id, wait_info in list(agent_wait_info.items()):
                    if wait_info.get("mode") != "path":
                        continue
                    agent = agents_by_id.get(agent_id)
                    if agent is None:
                        continue

                    state = wait_info.get("state", "to_target")
                    x, y = extract_agent_xy(agent)
                    if x is None or y is None:
                        continue
                    wait_info["current_position"] = (x, y)

                    if state == "done":
                        update_checkpoint_speed(
                            agent_speed_state,
                            direct_steering_info,
                            agent_id,
                            agent,
                            None,
                            None,
                            x,
                            y,
                            active_zones=_active_speed_zones,
                        )
                        continue

                    current_target_stage = wait_info.get("current_target_stage")
                    stage_cfg = wait_info.get("stage_configs", {}).get(
                        current_target_stage, {}
                    )
                    target = wait_info.get("target")

                    if state == "to_target":
                        update_checkpoint_speed(
                            agent_speed_state,
                            direct_steering_info,
                            agent_id,
                            agent,
                            current_target_stage,
                            stage_cfg,
                            x,
                            y,
                            active_zones=_active_speed_zones,
                        )
                        if not wait_info.get("target_assigned", False):
                            assign_agent_target(agent, target)
                            wait_info["target_assigned"] = True

                        stage_type = stage_cfg.get("stage_type")
                        reached_target = reached_stage(
                            x,
                            y,
                            target,
                            stage_cfg,
                            wait_info.get("agent_radius", 0.2),
                        )

                        if reached_target and stage_closed(
                            stage_graph, current_target_stage, current_time
                        ):
                            # A closed exit accepts no one; the reroute pass
                            # sends the agent elsewhere.
                            continue

                        if reached_target:
                            enable_throttling = stage_cfg.get(
                                "enable_throughput_throttling", False
                            )
                            max_throughput = float(stage_cfg.get("max_throughput", 1.0))
                            wp_key = current_target_stage
                            if enable_throttling and wp_key and max_throughput > 0:
                                min_interval = 1.0 / max_throughput
                                tracker = checkpoint_throughput_tracker.get(
                                    wp_key,
                                    {"last_exit_time": -9999},
                                )
                                if (
                                    current_time - tracker.get("last_exit_time", -9999)
                                    < min_interval
                                ):
                                    continue
                                checkpoint_throughput_tracker[wp_key] = {
                                    "last_exit_time": current_time
                                }

                            if stage_type == "exit":
                                agent_exits[agent_id] = current_target_stage
                                try:
                                    simulation.mark_agent_for_removal(agent_id)
                                except Exception as e:
                                    _logger.warning(
                                        "Failed to remove agent %s: %s", agent_id, e
                                    )
                                wait_info["state"] = "done"
                                continue

                            wait_time = sample_wait_time(
                                stage_cfg,
                                wait_info.get(
                                    "wait_seed", wait_info.get("base_seed", 0)
                                ),
                                wait_info.get("step_index", 0),
                            )
                            if wait_time > 0:
                                wait_info["state"] = "waiting"
                                wait_info["wait_until"] = current_time + wait_time
                            else:
                                advance_path_target(wait_info)
                                _acmap = cognitive_maps.get(agent_id)
                                if _acmap is not None and stage_graph is not None:
                                    _arrived = wait_info.get("current_origin")
                                    if _arrived and _arrived in stage_graph.nodes:
                                        expand_on_arrival(
                                            _acmap,
                                            _arrived,
                                            stage_graph,
                                            vis_model=vis_model,
                                            time_s=current_time,
                                            ax=x,
                                            ay=y,
                                        )
                        continue

                    if state == "waiting":
                        update_checkpoint_speed(
                            agent_speed_state,
                            direct_steering_info,
                            agent_id,
                            agent,
                            current_target_stage,
                            stage_cfg,
                            x,
                            y,
                            active_zones=_active_speed_zones,
                        )
                        if current_time >= float(
                            wait_info.get("wait_until", current_time)
                        ):
                            advance_path_target(wait_info)
                            _acmap = cognitive_maps.get(agent_id)
                            if _acmap is not None and stage_graph is not None:
                                _arrived = wait_info.get("current_origin")
                                if _arrived and _arrived in stage_graph.nodes:
                                    expand_on_arrival(
                                        _acmap,
                                        _arrived,
                                        stage_graph,
                                        vis_model=vis_model,
                                        time_s=current_time,
                                        ax=x,
                                        ay=y,
                                    )
                        continue

            if collect_cognitive_map_history:
                # Cognitive maps only ever grow, so the pair of sizes is a
                # faithful change detector and lets a long run record one row
                # per learning event instead of one per agent per timestep.
                for _aid, _map in cognitive_maps.items():
                    _size = (len(_map.known_nodes), len(_map.known_edges))
                    if _cmap_seen.get(_aid) == _size:
                        continue
                    _cmap_seen[_aid] = _size
                    cognitive_map_history.append(
                        {
                            "time_s": current_time,
                            "agent_id": _aid,
                            "familiarity": _map.familiarity,
                            "known_nodes": sorted(_map.known_nodes),
                            "known_edges": sorted(_map.known_edges),
                        }
                    )

            simulation.iterate()

        final_total_agents = initial_agent_count
        if has_flow_spawning:
            final_total_agents += sum(agent_counter_per_source)
        final_evacuated = max(0, final_total_agents - simulation.agent_count())
        wall_elapsed = _time.monotonic() - _wall_start
        wall_m, wall_s = divmod(int(wall_elapsed), 60)
        print(
            f"\rEvacuated {final_evacuated}/{total_progress_agents}"
            f"  sim={simulation.elapsed_time():.1f}s"
            f"  wall={wall_m}m{wall_s:02d}s"
            f"  done   "
        )

        evacuation_time = simulation.elapsed_time()
        remaining = simulation.agent_count()
        total_agents = initial_agent_count
        if has_flow_spawning:
            total_agents += sum(agent_counter_per_source)

        metrics = {
            "success": remaining == 0
            or evacuation_time >= scenario.max_simulation_time,
            "evacuation_time": round(evacuation_time, 2),
            "total_agents": total_agents,
            "agents_evacuated": total_agents - remaining,
            "agents_remaining": remaining,
            "all_evacuated": remaining == 0,
            "frame_rate": 10.0,
            "dt": 0.01,
            "seed": seed,
            "walkable_polygon": scenario.walkable_polygon,
        }
        # Only agents that were given an exit can have taken a replayed one.
        _warn_unused_replay(replay_exits, {aid: spawn_keys[aid] for aid in agent_exits})
        if smoke_speed_model is not None:
            metrics["smoke_history_samples"] = len(smoke_history)
        if fed_model is not None:
            metrics["fed_history_samples"] = len(fed_history)
            metrics["fed_max"] = max(
                (row["fed_cumulative"] for row in fed_history),
                default=0.0,
            )
        if heat_fed_model is not None:
            metrics["heat_fed_history_samples"] = len(fed_history)
            metrics["heat_fed_max"] = max(
                (row["heat_fed_cumulative"] for row in fed_history),
                default=0.0,
            )

        if fds_coverage is not None:
            metrics["fds_coverage"] = fds_coverage.to_dict()
            metrics["fds_outside"] = _report_outside(
                smoke_history, fed_history, smoke_speed_model, fed_model, heat_fed_model
            )

        if reroute_config is not None and route_history:
            metrics["route_switches"] = len(route_history)
        if reroute_config is not None and collect_route_cost_history:
            metrics["route_cost_samples"] = len(route_cost_history)
        if collect_cognitive_map_history:
            metrics["cognitive_map_events"] = len(cognitive_map_history)

        try:
            manifest_file = write_manifest(
                output_file,
                seed=seed,
                agent_seeding=SEEDING_SCHEME,
                scenario_path=scenario.source_path,
                fds_dir=fds_dir_from_models(
                    smoke_speed_model, fed_model, heat_fed_model
                ),
                heat_endpoint=heat_endpoint,
                heat_fed_method=getattr(heat_fed_model, "method", None),
                heat_flux_parameters=(
                    heat_fed_model.heat_flux_parameters()
                    if getattr(heat_fed_model, "method", None) == "total-flux"
                    else None
                ),
                heat_clothing=(
                    heat_fed_model.convective_clothing()
                    if hasattr(heat_fed_model, "convective_clothing")
                    else None
                ),
                heat_fed_threshold_override=(
                    tenability_config.heat_fed_threshold
                    if heat_fed_model is not None and tenability_config is not None
                    else None
                ),
                smoke_blind=smoke_blind,
                fds_coverage=metrics.get("fds_coverage"),
                replay_exits=(
                    None
                    if replay_exits is None
                    else {
                        "agents": len(replay_exits),
                        "sha256": _replay_digest(replay_exits),
                    }
                ),
            )
        except (OSError, ValueError) as exc:
            _logger.warning("Could not write the run manifest: %s", exc)
            manifest_file = None

        return ScenarioResult(
            metrics=metrics,
            sqlite_file=output_file,
            manifest_file=manifest_file,
            smoke_history=smoke_history if smoke_speed_model is not None else None,
            fed_history=fed_history
            if (fed_model is not None or heat_fed_model is not None)
            else None,
            route_history=route_history if reroute_config is not None else None,
            route_cost_history=(
                route_cost_history
                if reroute_config is not None and collect_route_cost_history
                else None
            ),
            cognitive_map_history=(
                cognitive_map_history if collect_cognitive_map_history else None
            ),
            exit_history=[
                {
                    "agent_id": agent_id,
                    "origin": origin,
                    "spawn_index": index,
                    "exit_id": agent_exits[agent_id],
                }
                for agent_id, (origin, index) in spawn_keys.items()
                if agent_id in agent_exits
            ],
        )
    finally:
        try:
            writer.close()
        except Exception:
            pass
        try:
            os.unlink(config_tmp.name)
        except Exception:
            pass
