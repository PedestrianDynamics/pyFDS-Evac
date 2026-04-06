"""Helper functions for direct-steering target and speed management."""

import logging
import math
import random
from typing import Any, Dict

from . import simulation_init

_logger = logging.getLogger(__name__)


def simulation_init_module():
    """Return the shared simulation initialization module."""
    return simulation_init


def normalize_speed_factor(value: Any) -> float:
    """Clamp a configured speed factor to a safe runtime range."""
    try:
        speed_factor = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(speed_factor) or speed_factor < 0.0:
        return 1.0
    return min(speed_factor, 3.0)


def random_point_in_polygon(polygon, rng, min_clearance: float = 0.2):
    """Sample a random point inside a polygon with a clearance margin."""
    return simulation_init_module()._random_point_in_polygon(
        polygon,
        rng,
        min_clearance=min_clearance,
    )


def pick_stage_target(wait_state, next_stage_cfg):
    """Pick a random target point inside the next stage polygon.

    Stage completion is handled separately by probabilistic completion
    logic, so no heading-based targeting is needed here.
    """
    polygon = (next_stage_cfg or {}).get("polygon")
    if polygon is None:
        return None

    target_rng = random.Random(
        int(wait_state.get("base_seed", 0)) + int(wait_state.get("step_index", 0))
    )
    target_clearance = max(
        0.05,
        float(wait_state.get("agent_radius", 0.2)) * 0.8,
    )
    return random_point_in_polygon(
        polygon,
        target_rng,
        min_clearance=target_clearance,
    )


def extract_agent_xy(agent):
    """Return the current agent position as an `(x, y)` tuple."""
    pos = getattr(agent, "position", None)
    if pos is not None:
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            return float(pos[0]), float(pos[1])
        if hasattr(pos, "x") and hasattr(pos, "y"):
            return float(pos.x), float(pos.y)
    if hasattr(agent, "x") and hasattr(agent, "y"):
        return float(agent.x), float(agent.y)
    return None, None


def assign_agent_target(agent, target):
    """Assign a new point target to an agent if the runtime supports it."""
    if not target:
        return
    tx, ty = float(target[0]), float(target[1])
    try:
        agent.target = (tx, ty)
        return
    except (AttributeError, TypeError):
        pass
    try:
        agent.target = [tx, ty]
    except Exception as e:
        _logger.warning("Failed to assign target to agent: %s", e)


def is_inside_polygon(x, y, polygon):
    """Return whether a point lies inside or on the boundary of a polygon."""
    if polygon is None:
        return False
    from shapely.geometry import Point

    try:
        point = Point(float(x), float(y))
        return bool(polygon.covers(point))
    except Exception as e:
        _logger.debug("Polygon containment check failed: %s", e)
        return False


def sample_wait_time(stage_cfg, base_seed, step_index):
    """Sample a waiting time from the stage configuration."""
    mean_wait = float(stage_cfg.get("waiting_time", 0.0))
    if stage_cfg.get("waiting_time_distribution") == "gaussian":
        std_wait = float(stage_cfg.get("waiting_time_std", 1.0))
        rng = random.Random(int(base_seed) + int(step_index) * 131 + 17)
        return max(0.1, float(rng.gauss(mean_wait, std_wait)))
    return max(0.0, mean_wait)


_MODEL_SPEED_ATTRS: dict[str, str] = {
    "CollisionFreeSpeedModelState": "v0",
    "CollisionFreeSpeedModelV2State": "v0",
    "SocialForceModelState": "desiredSpeed",
}


def get_agent_desired_speed(agent) -> float | None:
    """Read the agent's desired speed from the documented JuPedSim runtime API."""
    model_obj = getattr(agent, "model", None)
    if model_obj is None:
        return None
    speed_attr = _MODEL_SPEED_ATTRS.get(type(model_obj).__name__)
    if speed_attr is None or not hasattr(model_obj, speed_attr):
        return None
    try:
        return float(getattr(model_obj, speed_attr))
    except Exception:
        return None


def set_agent_desired_speed(agent, speed: float) -> bool:
    """Write the agent's desired speed through the documented JuPedSim runtime API."""
    model_obj = getattr(agent, "model", None)
    if model_obj is None:
        return False
    speed_attr = _MODEL_SPEED_ATTRS.get(type(model_obj).__name__)
    if speed_attr is None or not hasattr(model_obj, speed_attr):
        return False
    try:
        setattr(model_obj, speed_attr, float(speed))
        return True
    except Exception:
        return False


def set_agent_smoke_factor(
    agent_speed_state: Dict[int, Dict[str, Any]],
    agent_id: int,
    agent,
    smoke_factor: float,
) -> None:
    """Cache the smoke multiplier used alongside checkpoint speed modifiers."""
    state = ensure_agent_speed_state(agent_speed_state, agent_id, agent)
    state["smoke_factor"] = normalize_speed_factor(smoke_factor)


def ensure_agent_speed_state(
    agent_speed_state: Dict[int, Dict[str, Any]], agent_id: int, agent
):
    """Create or refresh cached per-agent speed state."""
    state = agent_speed_state.get(agent_id)
    if state is not None:
        return state
    current_speed = get_agent_desired_speed(agent)
    state = {
        "original_speed": current_speed,
        "active_checkpoint": None,
        "smoke_factor": 1.0,
    }
    agent_speed_state[agent_id] = state
    return state


def restore_agent_speed(
    agent_speed_state: Dict[int, Dict[str, Any]], agent_id: int, agent
) -> None:
    """Restore the effective desired speed outside checkpoint and zone slowdowns."""
    state = ensure_agent_speed_state(agent_speed_state, agent_id, agent)
    original_speed = state.get("original_speed")
    if original_speed is None:
        return
    smoke_factor = state.get("smoke_factor", 1.0)
    # Skip redundant write when already at restored speed and no smoke modification
    if state.get("active_checkpoint") is None and smoke_factor == 1.0:
        return
    smoke_factor = normalize_speed_factor(smoke_factor)
    if set_agent_desired_speed(agent, float(original_speed) * smoke_factor):
        state["active_checkpoint"] = None


def _find_checkpoint_zone(
    checkpoint_key: str,
    stage_cfg: Dict[str, Any],
    x: float,
    y: float,
) -> tuple[str, float] | None:
    """Return (zone_key, speed_factor) if the checkpoint has an active speed modifier."""
    factor = normalize_speed_factor(stage_cfg.get("speed_factor", 1.0))
    if math.fabs(factor - 1.0) <= 1e-9:
        return None
    if not is_inside_polygon(x, y, stage_cfg.get("polygon")):
        return None
    return checkpoint_key, factor


def _find_steering_zone(
    direct_steering_info: Dict[str, Dict[str, Any]] | None,
    x: float,
    y: float,
) -> tuple[str, float] | None:
    """Return (zone_key, speed_factor) for the strongest active steering zone."""
    best_key: str | None = None
    best_factor = 1.0
    for zone_key, zone_cfg in (direct_steering_info or {}).items():
        factor = normalize_speed_factor(zone_cfg.get("speed_factor", 1.0))
        if math.fabs(factor - 1.0) <= 1e-9:
            continue
        if not is_inside_polygon(x, y, zone_cfg.get("polygon")):
            continue
        if best_key is None or math.fabs(factor - 1.0) > math.fabs(best_factor - 1.0):
            best_key = zone_key
            best_factor = factor
    return (best_key, best_factor) if best_key is not None else None


def update_checkpoint_speed(
    agent_speed_state: Dict[int, Dict[str, Any]],
    direct_steering_info: Dict[str, Dict[str, Any]] | None,
    agent_id: int,
    agent,
    checkpoint_key: str | None,
    stage_cfg: Dict[str, Any] | None,
    x: float,
    y: float,
) -> None:
    """Apply or clear speed modifiers from checkpoint and steering zones."""
    state = ensure_agent_speed_state(agent_speed_state, agent_id, agent)

    zone = None
    if checkpoint_key and stage_cfg:
        zone = _find_checkpoint_zone(checkpoint_key, stage_cfg, x, y)
    if zone is None:
        zone = _find_steering_zone(direct_steering_info, x, y)

    if zone is None:
        restore_agent_speed(agent_speed_state, agent_id, agent)
        return

    active_zone_key, active_speed_factor = zone
    original_speed = state.get("original_speed")
    if original_speed is None:
        return
    smoke_factor = normalize_speed_factor(state.get("smoke_factor", 1.0))
    slowed_speed = max(0.0, float(original_speed) * active_speed_factor * smoke_factor)
    if set_agent_desired_speed(agent, slowed_speed):
        state["active_checkpoint"] = active_zone_key


def _weighted_choice(candidates: list, rng: random.Random) -> str:
    """Pick a stage key from (stage_key, weight) candidates by weighted random."""
    total = sum(max(0.0, float(w)) for _, w in candidates)
    if total <= 0:
        return candidates[0][0]
    pick = rng.random() * total
    running = 0.0
    for stage_key, weight in candidates:
        running += max(0.0, float(weight))
        if pick <= running:
            return stage_key
    return candidates[-1][0]


def advance_path_target(wait_info):
    """Advance direct-steering state to the next stage target if available."""
    path_choices = wait_info.get("path_choices", {})
    stage_configs = wait_info.get("stage_configs", {})
    current_stage = wait_info.get("current_target_stage")
    next_candidates = path_choices.get(current_stage, [])
    if not next_candidates:
        wait_info["state"] = "done"
        return

    choose_rng = random.Random(
        int(wait_info.get("base_seed", 0))
        + int(wait_info.get("step_index", 0)) * 131
        + 53
    )
    next_stage = _weighted_choice(next_candidates, choose_rng)

    if next_stage not in stage_configs:
        wait_info["state"] = "done"
        return

    wait_info["current_origin"] = current_stage
    wait_info["current_target_stage"] = next_stage
    wait_info["step_index"] = int(wait_info.get("step_index", 0)) + 1
    wait_info["target_assigned"] = False
    wait_info["wait_until"] = None
    wait_info["state"] = "to_target"
    wait_info["inside_since"] = None
    wait_info["target"] = pick_stage_target(wait_info, stage_configs[next_stage])
