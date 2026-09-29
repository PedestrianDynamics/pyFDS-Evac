"""The defaults quoted on the Models pages match the code.

Each entry names a page, a literal the page must contain, and a function that
returns the value the code uses. The number in the literal must equal that
value, so the test fails when the page is edited and when the code changes.
"""

import math
import re
from pathlib import Path

import numpy as np
import pytest

import run
from pyfds_evac.core.fed import (
    DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
    DEFAULT_HEAT_EMISSIVITY,
    DEFAULT_HEAT_SKIN_TEMPERATURE_C,
    DefaultFedConfig,
    TenabilityConfig,
    _co_fed_rate_per_minute,
    _heat_fed_rate_per_minute,
    _hyperventilation_factor,
    _o2_hypoxia_rate_per_minute,
)
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.simulation_init import _sample_agent_values
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "site" / "content" / "models"
SMOKE = MODELS / "smoke-speed.md"
FED = MODELS / "fed.md"
HEAT_MODEL = MODELS / "heat.md"
ROUTING = MODELS / "routing.md"
GATE = ROOT / "docs" / "route-cost-gate.md"
WAYFINDING = MODELS / "wayfinding.md"
ROUTING_DOC = ROOT / "docs" / "routing.md"
QUICKSTART = ROOT / "docs" / "quickstart.md"
HOMOGENEOUS = ROOT / "docs" / "testing-homogeneous.md"
HEAT = ROOT / "docs" / "testing-heat.md"
LIMITATIONS = ROOT / "docs" / "limitations.md"

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


def _cli():
    return run._build_parser().parse_args(["--scenario", "unused"])


def _v0():
    """The v0 an agent gets from a spawn area that sets none."""
    return _sample_agent_values({}, 1, np.random.RandomState(0))[1][0]


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
    return math.log(_hyperventilation_factor(2.0) / _hyperventilation_factor(1.0))


def _hv_divisor():
    return math.exp(0.1903 + 2.0004) / _hyperventilation_factor(1.0)


def _heat_exponent(clothing="unclothed"):
    rate = _heat_fed_rate_per_minute
    return math.log2(rate(2.0, clothing) / rate(1.0, clothing))


def _heat_divisor():
    return 1.0 / _heat_fed_rate_per_minute(1.0, "unclothed")


def _clothed_exponent():
    return _heat_exponent("clothed")


def _clothed_mantissa():
    return 1.0 / _heat_fed_rate_per_minute(1.0, "clothed") / 1e8


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
        "| `fridolf_slope` | `0.34` |",
        lambda: SmokeSpeedConfig().fridolf_slope,
    ),
    (
        SMOKE,
        "| `fridolf_visibility_threshold_m` | `3.0` |",
        lambda: SmokeSpeedConfig().fridolf_visibility_threshold_m,
    ),
    (
        SMOKE,
        "| `fridolf_min_speed_m_per_s` | `0.2` |",
        lambda: SmokeSpeedConfig().fridolf_min_speed_m_per_s,
    ),
    (
        SMOKE,
        "| `update_interval_s` | `1.0` |",
        lambda: SmokeSpeedConfig().update_interval_s,
    ),
    (SMOKE, "| `slice_height_m` | `1.6` |", lambda: SmokeSpeedConfig().slice_height_m),
    (SMOKE, "| `slice_height_m` | `1.6` |", lambda: DefaultFedConfig().slice_height_m),
    (SMOKE, "| `slice_height_m` | `1.6` |", lambda: _cli().smoke_slice_height),
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
    (FED, "T^{3.61}", _clothed_exponent),
    (FED, "T^{3.61} / (4.1", _clothed_mantissa),
    (HEAT_MODEL, "T^{3.61}", _clothed_exponent),
    (HEAT_MODEL, "T^{3.61} / (4.1", _clothed_mantissa),
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
    (
        FED,
        "| `o2_threshold_percent` (`DefaultFedConfig`) | `20.0` |",
        lambda: DefaultFedConfig().o2_threshold_percent,
    ),
    (
        FED,
        "| `o2_threshold_percent` (`DefaultFedConfig`) | `20.0` |",
        lambda: _cli().o2_threshold_percent,
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
    (WAYFINDING, "| `--vis-cell-size` | CLI | 0.25", lambda: _cli().vis_cell_size),
    (
        WAYFINDING,
        "| \\(V_{\\max}\\) | `--max-sign-distance` | 30",
        lambda: _cli().max_sign_distance,
    ),
    (LIMITATIONS, "`v0` (1.25 m/s by default)", _v0),
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
    # heat.md: total-flux parameters (#223), defaults are assumptions
    (HEAT_MODEL, "| ε | `0.5` |", lambda: DEFAULT_HEAT_EMISSIVITY),
    (HEAT_MODEL, "| ε | `0.5` |", lambda: _cli().heat_emissivity),
    (
        HEAT_MODEL,
        "| h [W m⁻² K⁻¹] | `5.0` |",
        lambda: DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
    ),
    (
        HEAT_MODEL,
        "| h [W m⁻² K⁻¹] | `5.0` |",
        lambda: _cli().heat_convective_coefficient,
    ),
    (
        HEAT_MODEL,
        "| \\(T_s\\) [°C] | `35.0` |",
        lambda: DEFAULT_HEAT_SKIN_TEMPERATURE_C,
    ),
    (
        HEAT_MODEL,
        "| \\(T_s\\) [°C] | `35.0` |",
        lambda: _cli().heat_skin_temperature,
    ),
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


def test_gas_incapacitation_is_deterministic_by_default():
    """FDS+Evac stops every agent at FED 1; the log-normal draw is opt-in."""
    literal = '| `incapacitation_mode` | `"deterministic"` |'
    assert literal in FED.read_text()
    assert TenabilityConfig().incapacitation_mode == "deterministic"
    assert _cli().incapacitation_mode == "deterministic"


def test_heat_incapacitation_is_deterministic_by_default():
    """No published spread exists for heat, so heat defaults to one threshold."""
    literal = '| `heat_incapacitation_mode` | `"deterministic"` |'
    assert literal in FED.read_text()
    assert TenabilityConfig().heat_incapacitation_mode == "deterministic"
    assert _cli().heat_incapacitation_mode == "deterministic"


def test_heat_fed_method_is_convective_by_default():
    """The total-flux method (#223) is opt-in."""
    literal = '| `heat_fed_method` | `"convective"` |'
    assert literal in HEAT_MODEL.read_text()
    assert _cli().heat_fed_method == "convective"


@pytest.mark.parametrize("page", [FED, HEAT_MODEL])
def test_heat_threshold_defaults_to_the_gas_threshold(page):
    """ISO 13571:2012 §5.4: one threshold; the heat override is unset."""
    literal = "| `heat_fed_threshold` | none, `fed_threshold` |"
    assert literal in page.read_text()
    assert TenabilityConfig().heat_fed_threshold is None
    assert _cli().heat_fed_threshold is None


def test_heat_clothing_is_clothed_by_default():
    """ISO 13571:2012 Eq. (9) is the default convective law (#290)."""
    from pyfds_evac.core.fed import DEFAULT_HEAT_CLOTHING

    literal = '| `heat_clothing` | `"clothed"` |'
    assert literal in HEAT_MODEL.read_text()
    assert DEFAULT_HEAT_CLOTHING == "clothed"
    assert _cli().heat_clothing is None
