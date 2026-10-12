"""The internal view of the switching-resistance margins (#187 R5)."""

from __future__ import annotations

import ast
import inspect

import pytest

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
}


def _distinct_config() -> RerouteConfig:
    return RerouteConfig(
        cost_config=RouteCostConfig(**_COST_MARGINS), exit_switch_anchor=0.91
    )


def test_view_lists_each_margin_once_in_audit_order():
    names = [m.name for m in rg._SWITCH_MARGINS]
    assert names == [
        "tau_return_margin",
        "tau_deadband",
        "fed_return_margin",
        "_PATH_IMPROVEMENT_THRESHOLD",
        "fallback_switch_margin",
        "fallback_return_lockout_s",
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
        "_PATH_IMPROVEMENT_THRESHOLD": 0.9,
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
    assert values["exit_switch_anchor"] is config.exit_switch_anchor
    assert values["_PATH_IMPROVEMENT_THRESHOLD"] is rg._PATH_IMPROVEMENT_THRESHOLD
    numbers = [v for v in values.values() if v is not None]
    assert len(set(numbers)) == len(numbers)


def test_module_constant_is_read_at_call_time(monkeypatch):
    monkeypatch.setattr(rg, "_PATH_IMPROVEMENT_THRESHOLD", 0.77)
    assert rg._switch_margin_values(RerouteConfig())["_PATH_IMPROVEMENT_THRESHOLD"] == (
        0.77
    )


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
    readers = _functions_reading(name)
    if margin.owner:
        assert readers == set(margin.consumers)
    else:
        assert set(margin.consumers) <= readers


# Functions that read a margin without applying it to a switch.
_NOT_CONSUMERS = {
    "RouteCostConfig.__post_init__",
    "RouteCostConfig.from_routing_params",
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
        "fallback_switch_margin",
        "fallback_return_lockout_s",
        "current_exit_discount",
        "clean_exit_margin",
    }


def test_fds_evac_counterparts():
    assert {m.name: m.counterpart for m in rg._SWITCH_MARGINS if m.counterpart} == {
        "current_exit_discount": "FAC_DOOR_OLD2",
        "exit_switch_anchor": "FAC_DOOR_WAIT",
        "clean_exit_margin": "FAC_DOOR_OLD",
    }
