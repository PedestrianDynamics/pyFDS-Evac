"""The defaults quoted on the Models pages match the code.

Each entry names a page, a literal the page must contain, and a function that
returns the value the code uses. The number in the literal must equal that
value, so the test fails when the page is edited and when the code changes.
"""

import math
import re
from pathlib import Path

import pytest

import run
from pyfds_evac.core.fed import (
    TenabilityConfig,
    _co_fed_rate_per_minute,
    _heat_fed_rate_per_minute,
    _hyperventilation_factor,
    _o2_hypoxia_rate_per_minute,
)
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "site" / "content" / "models"
SMOKE = MODELS / "smoke-speed.md"
FED = MODELS / "fed.md"
ROUTING = MODELS / "routing.md"
GATE = ROOT / "docs" / "route-cost-gate.md"
VISIBILITY = MODELS / "visibility.md"
ROUTING_DOC = ROOT / "docs" / "routing.md"
QUICKSTART = ROOT / "docs" / "quickstart.md"
HOMOGENEOUS = ROOT / "docs" / "testing-homogeneous.md"
HEAT = ROOT / "docs" / "testing-heat.md"

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


def _cli():
    return run._build_parser().parse_args(["--scenario", "unused"])


def _routing():
    return RouteCostConfig.from_routing_params({})


def _co_exponent():
    return math.log(_co_fed_rate_per_minute(math.e) / _co_fed_rate_per_minute(1.0))


def _o2_slope():
    rates = [_o2_hypoxia_rate_per_minute(c) for c in (10.0, 15.0)]
    return math.log(rates[0] / rates[1]) / 5.0


def _o2_intercept():
    """ln t_incap extrapolated to 20.9 % O2, above the code's zero-rate guard."""
    return -math.log(_o2_hypoxia_rate_per_minute(15.0)) + _o2_slope() * 5.9


def _hv_slope():
    return math.log(_hyperventilation_factor(1.0) / _hyperventilation_factor(0.0))


def _hv_divisor():
    return math.exp(2.0004) / _hyperventilation_factor(0.0)


def _heat_exponent():
    return math.log2(_heat_fed_rate_per_minute(2.0) / _heat_fed_rate_per_minute(1.0))


def _heat_divisor():
    return 1.0 / _heat_fed_rate_per_minute(1.0)


DEFAULTS = [
    # smoke-speed: SmokeSpeedConfig fields
    (SMOKE, "| `alpha` | `0.706` |", lambda: SmokeSpeedConfig().alpha),
    (SMOKE, "| `beta` | `-0.057` |", lambda: SmokeSpeedConfig().beta),
    (
        SMOKE,
        "| `min_speed_factor` | `0.1` |",
        lambda: SmokeSpeedConfig().min_speed_factor,
    ),
    (
        SMOKE,
        "| `visibility_factor_c` | `3.0` |",
        lambda: SmokeSpeedConfig().visibility_factor_c,
    ),
    (
        SMOKE,
        "| `update_interval_s` | `1.0` |",
        lambda: SmokeSpeedConfig().update_interval_s,
    ),
    (SMOKE, "| `slice_height_m` | `2.0` |", lambda: SmokeSpeedConfig().slice_height_m),
    # fed: TenabilityConfig fields and the run.py flags that set them
    (FED, "| `fic_alpha` | `0.7` |", lambda: TenabilityConfig().fic_alpha),
    (FED, "| `fic_alpha` | `0.7` |", lambda: _cli().fic_alpha),
    (FED, "| `fic_min_factor` | `0.3` |", lambda: TenabilityConfig().fic_min_factor),
    (FED, "| `fic_min_factor` | `0.3` |", lambda: _cli().fic_min_factor),
    (FED, "| `fed_threshold` | `1.0` |", lambda: TenabilityConfig().fed_threshold),
    (FED, "| `fed_threshold` | `1.0` |", lambda: _cli().fed_threshold),
    (
        FED,
        "| `susceptibility_sigma` | `0.94` |",
        lambda: TenabilityConfig().susceptibility_sigma,
    ),
    (FED, "| `susceptibility_sigma` | `0.94` |", lambda: _cli().susceptibility_sigma),
    (
        FED,
        "| `heat_fed_threshold` | `1.0` |",
        lambda: TenabilityConfig().heat_fed_threshold,
    ),
    (FED, "| `heat_fed_threshold` | `1.0` |", lambda: _cli().heat_fed_threshold),
    (
        FED,
        "| `heat_susceptibility_sigma` | `0.94` |",
        lambda: TenabilityConfig().heat_susceptibility_sigma,
    ),
    (
        FED,
        "| `heat_susceptibility_sigma` | `0.94` |",
        lambda: _cli().heat_susceptibility_sigma,
    ),
    # routing: the scenario `routing` block, and the reevaluation interval
    (ROUTING, "| `tau_max` | `6.0` |", lambda: _routing().tau_max),
    (ROUTING, "| `tau_return_margin` | `0.8` |", lambda: _routing().tau_return_margin),
    (
        ROUTING,
        "| `current_exit_discount` | `0.9` |",
        lambda: _routing().current_exit_discount,
    ),
    (ROUTING, "| `tau_deadband` | `0.1` |", lambda: _routing().tau_deadband),
    (
        ROUTING,
        "| `fed_rejection_threshold` | `1.0` |",
        lambda: _routing().fed_rejection_threshold,
    ),
    (ROUTING, "| `sampling_step_m` | `2.0` |", lambda: _routing().sampling_step_m),
    (
        ROUTING,
        "| `base_speed_m_per_s` | `1.3` |",
        lambda: _routing().base_speed_m_per_s,
    ),
    (ROUTING, "| `alpha` | `0.706` |", lambda: _routing().alpha),
    (ROUTING, "| `beta` | `-0.057` |", lambda: _routing().beta),
    (ROUTING, "| `min_speed_factor` | `0.1` |", lambda: _routing().min_speed_factor),
    (
        ROUTING,
        "| `RerouteConfig()` built in Python | `10.0` s |",
        lambda: RerouteConfig().reevaluation_interval_s,
    ),
    (
        ROUTING,
        "| `run.py --reroute-interval` | `1.0` s |",
        lambda: _cli().reroute_interval,
    ),
    # prose defaults
    (
        ROUTING_DOC,
        "`fed_rejection_threshold` (default 1.0)",
        lambda: _routing().fed_rejection_threshold,
    ),
    (
        ROUTING_DOC,
        "`current_exit_discount` (0.9)",
        lambda: _routing().current_exit_discount,
    ),
    (
        ROUTING_DOC,
        "`fed_return_margin` (0.9)",
        lambda: RouteCostConfig().fed_return_margin,
    ),
    (
        ROUTING_DOC,
        "`impassable_extinction_threshold` (3.0)",
        lambda: RouteCostConfig().impassable_extinction_threshold,
    ),
    (
        ROUTING_DOC,
        "`capacity_agents_per_s` (default 1.3)",
        lambda: _routing().default_exit_capacity,
    ),
    (
        ROUTING_DOC,
        "`RouteCostConfig.default_exit_capacity` (1.3 agents/s)",
        lambda: RouteCostConfig().default_exit_capacity,
    ),
    (VISIBILITY, "(default 0.25 m)", lambda: _cli().vis_cell_size),
    # hand calculations on the tutorial and testing pages
    (QUICKSTART, "`1 + (-0.057", lambda: SmokeSpeedConfig().beta),
    (QUICKSTART, "× 3.0) / 0.706", lambda: SmokeSpeedConfig().alpha),
    (HOMOGENEOUS, "FED_CO = 2.764e-5", lambda: _co_fed_rate_per_minute(1.0)),
    (HOMOGENEOUS, "(C_CO)^1.036", _co_exponent),
    (HOMOGENEOUS, "exp[8.13", _o2_intercept),
    (HOMOGENEOUS, "exp[8.13 - 0.54", _o2_slope),
    (HOMOGENEOUS, "exp(0.1903", _hv_slope),
    (HOMOGENEOUS, "+ 2.0004) / 7.1", _hv_divisor),
    (HEAT, "[ T^3.4", _heat_exponent),
    (HEAT, "[ T^3.4 / 5e7", _heat_divisor),
    (HEAT, "(T^3.4", _heat_exponent),
    (HEAT, "(T^3.4 / 5e7", _heat_divisor),
    # route-cost-gate: the full `routing` key table
    (GATE, "| `tau_max` | `6.0` |", lambda: _routing().tau_max),
    (GATE, "| `tau_return_margin` | `0.8` |", lambda: _routing().tau_return_margin),
    (
        GATE,
        "| `current_exit_discount` | `0.9` |",
        lambda: _routing().current_exit_discount,
    ),
    (GATE, "| `sampling_step_m` | `2.0` |", lambda: _routing().sampling_step_m),
    (GATE, "| `base_speed_m_per_s` | `1.3` |", lambda: _routing().base_speed_m_per_s),
    (GATE, "| `alpha` | `0.706` |", lambda: _routing().alpha),
    (GATE, "| `beta` | `-0.057` |", lambda: _routing().beta),
    (GATE, "| `min_speed_factor` | `0.1` |", lambda: _routing().min_speed_factor),
]


@pytest.mark.parametrize(
    "page, literal, code_value",
    DEFAULTS,
    ids=[f"{page.name}:{literal}" for page, literal, _ in DEFAULTS],
)
def test_page_quotes_code_default(page, literal, code_value):
    assert literal in page.read_text(), f"{page.name} no longer contains {literal!r}"
    quoted = float(_NUMBER.findall(literal)[-1])
    assert quoted == pytest.approx(float(code_value())), (
        f"{page.name} quotes {quoted} in {literal!r}, the code has {code_value()}"
    )
