"""Behavioral verification harness for the coupled pyFDS-Evac engine.

Tier-A unit tests (``test_*_verif.py``) pin each model *function* to a closed
form.  This harness exercises the **coupling inside the real run loop**
(``scenario.run_scenario``): does cumulative FED advance every tick, does
crossing the threshold actually pin speed to zero, does a null input stay at
zero, does the control arm stay clean.  (Verifying that the field is sampled at
the agent's *live position* needs a spatially-varying field -- ``ramp_x`` -- and
is left to a dedicated gradient scenario; the uniform-field tests here are
position-blind by construction.)

The unlock is that ``run_scenario`` accepts pre-built ``smoke_speed_model`` and
``fed_model`` objects, and both are duck-typed around a single
``sampler.sample(time_s, x, y) -> float`` call.  A *synthetic* field is thus any
object exposing that method, so the expected agent behaviour is closed-form and
no FDS run is involved.

Design rules baked in (see specs/012-model-verification/SPEC.md):

- **Three arms.** Every scenario compares a *control* (mechanism off) against a
  *treatment* (mechanism on); assertions are on the difference, never the
  absolute.
- **Uniform fields are transpose-blind.**  A uniform K/CO field cannot catch an
  x/y axis-order bug, so the behavioural suite never claims to; that risk stays
  with the standalone asymmetric visibility tests (B3.1).
- **Wiring, not physics.**  The FED/smoke equations are already verified to
  machine precision in Tier A.  Time-of-event is quantised to the FED update
  interval, so assert ``t*`` within one ``update_interval_s`` -- chasing 1e-6
  through JuPedSim only tests its integrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultFedModel,
    DefaultHeatFedModel,
    FdsFedField,
    FdsHeatField,
    TenabilityConfig,
)
from pyfds_evac.core.scenario import Scenario
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

# A field value as a pure function of (time_s, x, y).
FieldFn = Callable[[float, float, float], float]


class SyntheticSampler:
    """Duck-typed stand-in for ``SliceFieldSampler``.

    The real samplers expose exactly one method used by the models --
    ``sample(time_s, x, y) -> float`` -- so a closure is all the coupling
    layer needs.  No FDS, no fdsreader, deterministic to machine precision.
    """

    def __init__(self, field_fn: FieldFn):
        self._fn = field_fn

    def sample(self, time_s: float, x: float, y: float) -> float:
        return float(self._fn(float(time_s), float(x), float(y)))


def uniform(value: float) -> FieldFn:
    """Constant field everywhere -- transpose-invariant by construction."""
    return lambda t, x, y: value


def ramp_x(slope: float, intercept: float = 0.0) -> FieldFn:
    """Linear field along +x: ``value = intercept + slope * x``."""
    return lambda t, x, y: intercept + slope * x


def region_x(value: float, *, x_min: float = -1e30, x_max: float = 1e30) -> FieldFn:
    """``value`` inside the x-band ``[x_min, x_max]``, ``0`` elsewhere.

    Localises smoke to one arm of a junction so only that route's cost rises --
    a spatially-varying field, so it also exercises position sampling.
    """
    return lambda t, x, y: value if x_min <= x <= x_max else 0.0


def make_smoke_model(
    extinction: FieldFn,
    *,
    speed_law: str = "lund",
) -> SmokeSpeedModel:
    """Wrap a synthetic extinction field as a ready-to-inject smoke model."""
    # Duck-typed: ExtinctionField only calls sampler.sample(t, x, y).
    field = ExtinctionField(SyntheticSampler(extinction))  # type: ignore[arg-type]
    config = SmokeSpeedConfig(fds_dir="", speed_law=speed_law)
    return SmokeSpeedModel(field, config)


def make_fed_model(
    *,
    co_volume_fraction: FieldFn,
    co2_volume_fraction: FieldFn,
    o2_volume_fraction: FieldFn,
    update_interval_s: float = 1.0,
    **optional_volume_fractions: FieldFn,
) -> DefaultFedModel:
    """Wrap synthetic gas fields (volume fractions in [0, 1]) as a FED model."""
    optional = {
        key: SyntheticSampler(fn) for key, fn in optional_volume_fractions.items()
    }
    # Duck-typed: FdsFedField only calls each sampler's sample(t, x, y).
    field = FdsFedField(
        SyntheticSampler(co_volume_fraction),  # type: ignore[arg-type]
        SyntheticSampler(co2_volume_fraction),  # type: ignore[arg-type]
        SyntheticSampler(o2_volume_fraction),  # type: ignore[arg-type]
        **optional,  # type: ignore[arg-type]
    )
    config = DefaultFedConfig(fds_dir="", update_interval_s=update_interval_s)
    return DefaultFedModel(field, config)


def deterministic_tenability(fed_threshold: float = 1.0) -> TenabilityConfig:
    """Tenability with every agent collapsing at exactly ``fed_threshold``.

    Deterministic incapacitation neutralises the threshold RNG so a uniform
    field yields one shared ``t*`` -- the assertion the closed form predicts.
    FIC speed reduction is disabled to keep the FED -> incapacitation path
    isolated from the irritant-speed path.
    """
    return TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=True,
        fed_threshold=fed_threshold,
        incapacitation_mode="deterministic",
    )


def make_heat_model(
    temperature_celsius: FieldFn,
    *,
    update_interval_s: float = 1.0,
) -> DefaultHeatFedModel:
    """Wrap a synthetic gas-temperature field (deg C) as a heat FED model."""
    # Duck-typed: FdsHeatField only calls the sampler's sample(t, x, y).
    field = FdsHeatField(SyntheticSampler(temperature_celsius))  # type: ignore[arg-type]
    config = DefaultFedConfig(fds_dir="", update_interval_s=update_interval_s)
    return DefaultHeatFedModel(field, config)


def deterministic_heat_tenability(heat_fed_threshold: float = 1.0) -> TenabilityConfig:
    """Tenability with every agent thermally collapsing at exactly the threshold.

    Mirrors ``deterministic_tenability`` but isolates the *heat* dose track:
    gas incapacitation and FIC speed reduction are disabled so only the heat
    FED -> incapacitation path is under test.
    """
    return TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=False,
        enable_heat_incapacitation=True,
        heat_fed_threshold=heat_fed_threshold,
        heat_incapacitation_mode="deterministic",
    )


def heat_fed_rate_per_min(temperature_celsius: float) -> float:
    """Closed-form heat FED rate (1/min), SFPE Handbook Eq. 63.44.

    Re-derived here (not imported from ``pyfds_evac.core.fed``) so the test
    catches an integration regression independently of the model's own
    coefficients -- mirrors ``co_fed_rate_per_min``.
    """
    return temperature_celsius**3.4 / 5e7


def time_to_heat_incapacitation_s(
    temperature_celsius: float, heat_fed_threshold: float = 1.0
) -> float:
    """Closed-form ``t*``: seconds for cumulative heat FED to reach the threshold."""
    return 60.0 * heat_fed_threshold / heat_fed_rate_per_min(temperature_celsius)


def co_fed_rate_per_min(co_ppm: float) -> float:
    """Closed-form total FED rate (1/min) for a CO-only atmosphere.

    Mirrors the model: CO rate (guide Eq. 13) times the CO2 hyperventilation
    factor at CO2 = 0 (which is >= 1.04 and cannot be omitted).  O2 at ambient
    contributes nothing (hypoxia gated at 19.5 %).
    """
    import math

    co_rate = 2.764e-5 * (co_ppm**1.036)
    hv_co2_at_zero = math.exp(2.0004) / 7.1
    return co_rate * hv_co2_at_zero


def time_to_incapacitation_s(co_ppm: float, fed_threshold: float = 1.0) -> float:
    """Closed-form ``t*``: seconds for cumulative FED to reach the threshold."""
    return 60.0 * fed_threshold / co_fed_rate_per_min(co_ppm)


def lund_speed_factor(
    extinction_per_m: float,
    *,
    alpha: float = 0.706,
    beta: float = -0.057,
    min_speed_factor: float = 0.1,
) -> float:
    """Closed-form Lund factor: clip(1 + beta*K/alpha, min, 1).

    Re-derived here (not imported from the model) so the test catches an
    integration regression independently of the model's own coefficients.
    """
    factor = 1.0 + beta * max(0.0, extinction_per_m) / alpha
    return min(1.0, max(min_speed_factor, factor))


def fridolf_speed_factor(
    extinction_per_m: float,
    *,
    visibility_factor_c: float = 3.0,
) -> float:
    """Closed-form Fridolf factor: V/(V+2) with V = c/K (1 at K=0)."""
    k = max(0.0, extinction_per_m)
    if k == 0.0:
        return 1.0
    v = visibility_factor_c / k
    return v / (v + 2.0)


@dataclass
class CorridorSpec:
    """A straight rectangular corridor with one exit at the far (+x) wall."""

    length_m: float = 40.0
    width_m: float = 4.0
    num_agents: int = 5
    v0: float = 1.0
    seed: int = 42
    max_simulation_time: float = 120.0

    @property
    def free_walk_egress_s(self) -> float:
        """Lower bound on egress time: corridor length at free speed."""
        return self.length_m / self.v0


def corridor_scenario(spec: CorridorSpec) -> Scenario:
    """Build a minimal corridor ``Scenario`` directly (no asset files).

    Agents spawn at the near (-x) end and route to a single exit on the far
    (+x) wall.  Premovement is OFF so the FED clock starts together for every
    agent, which is what makes a uniform field give a single shared ``t*``.
    """
    length = spec.length_m
    width = spec.width_m
    walkable_wkt = f"POLYGON ((0 0, {length} 0, {length} {width}, 0 {width}, 0 0))"

    exit_x0 = length - 1.0
    # Grow the spawn region with the population so distribute_by_number has room
    # (~4 agents/m2 loose packing); a uniform field makes spawn position
    # irrelevant to t*, only that agents stay in-field through it.
    usable_width = max(1.0, width - 1.0)
    spawn_depth = max(2.0, spec.num_agents * 0.3 / usable_width)
    spawn_x1 = min(1.0 + spawn_depth, exit_x0 - 1.0)
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": spec.max_simulation_time,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": spec.seed,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            "exit_far": {
                "type": "polygon",
                "coordinates": [
                    [exit_x0, 0.5],
                    [length, 0.5],
                    [length, width - 0.5],
                    [exit_x0, width - 0.5],
                    [exit_x0, 0.5],
                ],
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
        },
        "distributions": {
            "spawn_near": {
                "type": "polygon",
                "coordinates": [
                    [1.0, 0.5],
                    [spawn_x1, 0.5],
                    [spawn_x1, width - 0.5],
                    [1.0, width - 0.5],
                    [1.0, 0.5],
                ],
                "parameters": {
                    "number": spec.num_agents,
                    "radius": 0.15,
                    "v0": spec.v0,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
    }

    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    sim_params.setdefault("max_simulation_time", spec.max_simulation_time)
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable_wkt,
        model_type="CollisionFreeSpeedModel",
        seed=spec.seed,
        sim_params=sim_params,
        source_path=None,
    )


def first_incapacitation_times(result) -> dict[int, float]:
    """Map agent_id -> earliest time_s at which it was flagged incapacitated."""
    times: dict[int, float] = {}
    for row in result.fed_history or []:
        if not row.get("incapacitated"):
            continue
        agent_id = row["agent_id"]
        t = float(row["time_s"])
        if agent_id not in times or t < times[agent_id]:
            times[agent_id] = t
    return times


def first_incapacitation_causes(result) -> dict[int, str]:
    """Map agent_id -> ``incapacitation_cause`` ('gas'/'heat'/'gas+heat') at collapse.

    Reads the cause recorded at each agent's *earliest* incapacitated row --
    the only way to tell which of the two independent dose tracks (see
    ``fed.py``'s ``TenabilityConfig``) actually tripped it.
    """
    causes: dict[int, str] = {}
    times: dict[int, float] = {}
    for row in result.fed_history or []:
        if not row.get("incapacitated"):
            continue
        agent_id = row["agent_id"]
        t = float(row["time_s"])
        if agent_id not in times or t < times[agent_id]:
            times[agent_id] = t
            causes[agent_id] = row.get("incapacitation_cause", "")
    return causes


# Exit IDs emitted by ``t_junction_scenario`` (referenced by S4 assertions).
EXIT_LEFT = "exit_A_left"
EXIT_RIGHT = "exit_B_right"


@dataclass
class TJunctionSpec:
    """A T-junction: a central stem opening into a left and a right arm.

    The stem is offset toward the right wall so the **right** exit is nearer and
    is the default choice -- smoke placed in the right arm then forces a switch
    to the left.  Geometry follows the proven ``assets/t_junction`` layout.
    """

    width_m: float = 30.0
    stem_center_x: float = 20.0  # offset right of centre -> right arm is shorter
    stem_half_width_m: float = 3.0
    stem_height_m: float = 10.0
    corridor_height_m: float = 3.0
    num_agents: int = 20  # low density: exits stay uncongested, control quiet
    v0: float = 1.3
    seed: int = 42
    max_simulation_time: float = 120.0
    flow_end_time_s: float = 40.0  # rerouting requires flow spawning (see note)

    @property
    def right_arm_x_min(self) -> float:
        """Left edge of the right arm (right of the stem) -- the smoke band."""
        return self.stem_center_x + self.stem_half_width_m


def t_junction_scenario(spec: TJunctionSpec) -> Scenario:
    """Build a two-exit T-junction ``Scenario`` for rerouting tests.

    Agents spawn in the stem and route to the nearer (right) exit; with no
    transitions the engine auto-connects the spawn to both exits, so route cost
    -- not a fixed journey -- decides the exit, which is what rerouting needs.
    """
    w = spec.width_m
    sx0 = spec.stem_center_x - spec.stem_half_width_m
    sx1 = spec.stem_center_x + spec.stem_half_width_m
    stem_h = spec.stem_height_m
    top = stem_h + spec.corridor_height_m

    # T-shape: stem (sx0..sx1, 0..stem_h) opening into a top corridor
    # (0..w, stem_h..top) with an exit at each end.
    walkable_wkt = (
        f"POLYGON (({sx0} 0, {sx1} 0, {sx1} {stem_h}, {w} {stem_h}, "
        f"{w} {top}, 0 {top}, 0 {stem_h}, {sx0} {stem_h}, {sx0} 0))"
    )

    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": spec.max_simulation_time,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": spec.seed,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            EXIT_LEFT: {
                "type": "polygon",
                "coordinates": [
                    [0, stem_h],
                    [1, stem_h],
                    [1, top],
                    [0, top],
                    [0, stem_h],
                ],
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            },
            EXIT_RIGHT: {
                "type": "polygon",
                "coordinates": [
                    [w - 1, stem_h],
                    [w, stem_h],
                    [w, top],
                    [w - 1, top],
                    [w - 1, stem_h],
                ],
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            },
        },
        "distributions": {
            "spawn_stem": {
                "type": "polygon",
                "coordinates": [
                    [sx0 + 1, 1],
                    [sx1 - 1, 1],
                    [sx1 - 1, stem_h - 2],
                    [sx0 + 1, stem_h - 2],
                    [sx0 + 1, 1],
                ],
                "parameters": {
                    "number": spec.num_agents,
                    "radius": 0.15,
                    "v0": spec.v0,
                    # Rerouting engages only on the flow-spawning agent-init path
                    # (by-number placement leaves agents out of route evaluation
                    # -- a verified engine limitation, see project memory). A
                    # short flow window gets the population in quickly.
                    "use_flow_spawning": True,
                    "flow_start_time": 0,
                    "flow_end_time": spec.flow_end_time_s,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "familiarity": "full",
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
    }

    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    sim_params.setdefault("max_simulation_time", spec.max_simulation_time)
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable_wkt,
        model_type="CollisionFreeSpeedModel",
        seed=spec.seed,
        sim_params=sim_params,
        source_path=None,
    )


def route_switch_count(result) -> int:
    """Number of reroutes. Robust to the metric key being absent when zero.

    ``run_scenario`` only writes ``metrics["route_switches"]`` when at least one
    switch occurred, so read the history list directly (it is ``[]``, never
    missing, whenever rerouting is enabled).
    """
    return len(result.route_history or [])


def route_switch_directions(result) -> dict[tuple[str, str], int]:
    """Count ``(old_exit, new_exit)`` reroute pairs from ``route_history``."""
    counts: dict[tuple[str, str], int] = {}
    for switch in result.route_history or []:
        key = (switch["old_exit"], switch["new_exit"])
        counts[key] = counts.get(key, 0) + 1
    return counts
