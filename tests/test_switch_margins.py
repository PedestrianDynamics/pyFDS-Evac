"""The internal view of the switching-resistance margins (#187 R5)."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math

import numpy as np
import pytest

from pyfds_evac.config.rules import routing_issue
from pyfds_evac.core import route_graph as rg
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig

_COST_MARGINS = {
    "tau_return_margin": 0.81,
    "tau_deadband": 0.12,
    "fed_return_margin": 0.87,
    "fallback_switch_margin": 0.23,
    "fallback_return_lockout_s": 7.5,
    "current_exit_discount": 0.83,
    "clean_exit_margin": 0.14,
    "path_switch_anchor": 0.86,
}


def _distinct_config() -> RerouteConfig:
    return RerouteConfig(
        cost_config=RouteCostConfig(**_COST_MARGINS, exit_switch_anchor=0.89),
        exit_switch_anchor=0.91,
    )


def test_view_lists_each_margin_once_in_audit_order():
    names = [m.name for m in rg._SWITCH_MARGINS]
    assert names == [
        "fallback_return_lockout_s",
        "fed_return_margin",
        "path_switch_anchor",
        "fallback_switch_margin",
        "tau_return_margin",
        "tau_deadband",
        "default_exit_anchoring",
        "current_exit_discount",
        "exit_switch_anchor",
        "clean_exit_margin",
    ]


def test_code_defaults_are_unchanged():
    assert rg._switch_margin_values(RerouteConfig()) == {
        "tau_return_margin": 0.8,
        "tau_deadband": 0.1,
        "fed_return_margin": 0.9,
        "path_switch_anchor": 0.9,
        "fallback_switch_margin": 0.2,
        "fallback_return_lockout_s": 10.0,
        "default_exit_anchoring": None,
        "current_exit_discount": 0.9,
        "exit_switch_anchor": 0.9,
        "clean_exit_margin": 0.1,
    }


def test_each_value_is_the_object_its_consumer_reads():
    """Distinct values, so a crossed field cannot hide behind a shared 0.9."""
    config = _distinct_config()
    values = rg._switch_margin_values(config)
    for name, value in _COST_MARGINS.items():
        assert values[name] is getattr(config.cost_config, name)
        assert values[name] == value
    assert values["exit_switch_anchor"] is config.resolved_exit_switch_anchor
    assert values["exit_switch_anchor"] == 0.91
    numbers = [v for v in values.values() if v is not None]
    assert len(set(numbers)) == len(numbers)


def test_exit_switch_anchor_override_takes_precedence():
    """An explicit RerouteConfig value beats the cost model's; None reads it."""
    cost_config = RouteCostConfig.from_routing_params({"exit_switch_anchor": 0.7})
    assert RerouteConfig(cost_config=cost_config).resolved_exit_switch_anchor == 0.7
    assert (
        RerouteConfig(
            cost_config=cost_config, exit_switch_anchor=0.8
        ).resolved_exit_switch_anchor
        == 0.8
    )
    assert RerouteConfig().resolved_exit_switch_anchor == 0.9


def test_without_cost_config_the_code_defaults_apply():
    values = rg._switch_margin_values(RerouteConfig(exit_switch_anchor=0.91))
    assert values["exit_switch_anchor"] == 0.91
    for name in _COST_MARGINS:
        assert values[name] == getattr(RouteCostConfig, name)


@pytest.mark.parametrize("margin", rg._SWITCH_MARGINS, ids=lambda m: m.name)
def test_each_consumer_reads_its_margin(margin):
    """The listed functions are exactly those whose code reads the margin.

    Read from the syntax tree, so a docstring or comment naming the margin
    does not count, and a reader missing from the list fails.
    """
    name = margin.name if margin.owner else "default_exit"
    readers = _functions_reading(_READ_AS.get(name, name))
    if margin.owner:
        assert readers == set(margin.consumers)
    else:
        assert set(margin.consumers) <= readers


# Functions that read a margin without applying it to a switch.
_NOT_CONSUMERS = {
    "RouteCostConfig.__post_init__",
    "RouteCostConfig.from_routing_params",
    "RerouteConfig.__post_init__",
    "_switch_margin_values",
}

# The consumers read exit_switch_anchor through its resolver.
_READ_AS = {"exit_switch_anchor": "resolved_exit_switch_anchor"}


def test_only_the_resolver_reads_the_exit_switch_anchor_fields():
    """No consumer reads either field of exit_switch_anchor around the resolver."""
    assert _functions_reading("exit_switch_anchor") == {
        "RerouteConfig.resolved_exit_switch_anchor"
    }


def _reads(node: ast.AST, name: str) -> bool:
    return any(
        (isinstance(n, ast.Attribute) and n.attr == name)
        or (isinstance(n, ast.Name) and n.id == name)
        for n in ast.walk(node)
    )


def _functions_reading(name: str) -> set[str]:
    """Module functions and methods whose code reads *name*."""
    tree = ast.parse(inspect.getsource(rg))
    functions: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            functions.extend(
                (f"{node.name}.{item.name}", item)
                for item in node.body
                if isinstance(item, ast.FunctionDef)
            )
    return {
        qualname
        for qualname, node in functions
        if qualname not in _NOT_CONSUMERS and _reads(node, name)
    }


def _routing_block_sets(name: str) -> bool:
    sentinel = 0.5
    if not hasattr(RouteCostConfig, name):
        return False
    built = RouteCostConfig.from_routing_params({name: sentinel})
    return getattr(built, name) == sentinel


@pytest.mark.parametrize("margin", rg._SWITCH_MARGINS, ids=lambda m: m.name)
def test_routing_key_matches_the_routing_block(margin):
    assert margin.routing_key is _routing_block_sets(margin.name)


def test_only_the_routing_block_margins_are_scenario_keys():
    settable = {m.name for m in rg._SWITCH_MARGINS if m.routing_key}
    assert settable == {
        "tau_return_margin",
        "tau_deadband",
        "fed_return_margin",
        "path_switch_anchor",
        "fallback_switch_margin",
        "fallback_return_lockout_s",
        "current_exit_discount",
        "exit_switch_anchor",
        "clean_exit_margin",
    }


def test_fds_evac_counterparts():
    assert {m.name: m.counterpart for m in rg._SWITCH_MARGINS if m.counterpart} == {
        "current_exit_discount": "FAC_DOOR_OLD2",
        "exit_switch_anchor": "FAC_DOOR_WAIT",
        "clean_exit_margin": "FAC_DOOR_OLD",
    }


# --- the routing-block margin keys and their ranges (#187 Q7, Q-b) ---------

# Whether 0 and 1 are valid values of each key.
_RANGES = {
    "fed_return_margin": (False, True),
    "exit_switch_anchor": (False, True),
    "path_switch_anchor": (False, True),
    "tau_return_margin": (False, True),
    "current_exit_discount": (False, True),
    "clean_exit_margin": (False, True),
    "tau_deadband": (True, True),
    "fallback_switch_margin": (True, False),
}


def test_every_routing_margin_but_the_lockout_has_a_range():
    keys = {m.name for m in rg._SWITCH_MARGINS if m.routing_key}
    assert keys - set(_RANGES) == {"fallback_return_lockout_s"}
    assert rg._MARGIN_RANGES == _RANGES


@pytest.mark.parametrize(
    "key, value",
    [
        ("fed_return_margin", 0.6),
        ("exit_switch_anchor", 0.7),
        ("path_switch_anchor", 0.8),
    ],
)
def test_routing_block_sets_the_q7_keys(key, value):
    built = RouteCostConfig.from_routing_params({key: value})
    assert getattr(built, key) == value
    assert getattr(RouteCostConfig.from_routing_params({}), key) == 0.9


@pytest.mark.parametrize("key", sorted(_RANGES))
@pytest.mark.parametrize(
    "value", [-0.1, 1.0001, 2, math.nan, math.inf, True, False, "0.9", None]
)
def test_out_of_range_margin_is_an_error(key, value):
    with pytest.raises(ValueError, match=rf"^routing\.{key} must be a number in "):
        RouteCostConfig.from_routing_params({key: value})


@pytest.mark.parametrize("key", sorted(_RANGES))
def test_margin_bounds(key):
    closed_low, closed_high = _RANGES[key]
    for bound, closed in ((0.0, closed_low), (0, closed_low), (1.0, closed_high)):
        if closed:
            assert getattr(RouteCostConfig(**{key: bound}), key) == bound
            continue
        with pytest.raises(ValueError, match=rf"routing\.{key}"):
            RouteCostConfig(**{key: bound})


@pytest.mark.parametrize("key", sorted(_RANGES))
def test_off_value_is_valid(key):
    """Each margin can be switched off from the routing block."""
    off = 0.0 if key in ("tau_deadband", "fallback_switch_margin") else 1
    assert getattr(RouteCostConfig.from_routing_params({key: off}), key) == off


@pytest.mark.parametrize("value", [0.0, 1.5, math.nan, True, "0.9"])
def test_out_of_range_override_is_an_error(value):
    with pytest.raises(
        ValueError, match=r"^RerouteConfig\.exit_switch_anchor must be a number in "
    ):
        RerouteConfig(exit_switch_anchor=value)


# The fields of RouteCostConfig in order before the Q7 keys (fb06761f).
_POSITIONAL_FIELDS = (
    "w_smoke",
    "w_fed",
    "w_queue",
    "fed_rejection_threshold",
    "fed_return_margin",
    "visibility_extinction_threshold",
    "impassable_extinction_threshold",
    "sampling_step_m",
    "base_speed_m_per_s",
    "alpha",
    "beta",
    "min_speed_factor",
    "default_exit_capacity",
    "cost_model",
    "clean_extinction_threshold",
    "clean_exit_margin",
    "tau_max",
    "tau_deadband",
    "current_exit_discount",
    "tau_return_margin",
    "anticipate",
    "foresight_horizon_s",
    "fallback_switch_margin",
    "fallback_return_lockout_s",
    "fallback_rule",
)


def test_positional_slots_are_unchanged():
    """The Q7 fields come last; every earlier positional argument keeps its slot."""
    names = [f.name for f in dataclasses.fields(RouteCostConfig)]
    assert tuple(names[: len(_POSITIONAL_FIELDS)]) == _POSITIONAL_FIELDS
    values = [getattr(RouteCostConfig(), name) for name in _POSITIONAL_FIELDS]
    values[-1] = "hold"
    built = RouteCostConfig(*values)
    assert built.fallback_rule == "hold"
    assert (built.exit_switch_anchor, built.path_switch_anchor) == (0.9, 0.9)
    assert [f.name for f in dataclasses.fields(RerouteConfig)] == [
        "reevaluation_interval_s",
        "cost_config",
        "exit_switch_anchor",
    ]


@pytest.mark.parametrize("key", sorted(_RANGES))
def test_huge_int_is_a_range_error_not_an_overflow(key):
    with pytest.raises(ValueError, match=rf"^routing\.{key} must be a number in "):
        RouteCostConfig.from_routing_params({key: 10**400})


def test_huge_int_is_a_configuration_issue():
    issue = routing_issue({"routing": {"fed_return_margin": 10**400}})
    assert issue is not None
    assert issue.message.startswith("routing.fed_return_margin must be a number in ")


@pytest.mark.parametrize(
    "value", [np.int64(1), np.float32(0.9), np.float64(0.5), np.int32(1)]
)
def test_numpy_scalars_in_range_are_accepted(value):
    built = RouteCostConfig(exit_switch_anchor=value, path_switch_anchor=value)
    assert built.exit_switch_anchor == value
    assert RerouteConfig(exit_switch_anchor=value).resolved_exit_switch_anchor == value


@pytest.mark.parametrize("value", [np.float64(1.5), np.int64(0), np.bool_(True)])
def test_numpy_scalars_out_of_range_are_refused(value):
    with pytest.raises(ValueError, match=r"routing\.exit_switch_anchor"):
        RouteCostConfig(exit_switch_anchor=value)
