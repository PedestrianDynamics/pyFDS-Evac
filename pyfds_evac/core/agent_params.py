"""Agent parameter keys of a scenario JSON, checked without the simulation stack.

``desired_speed``, ``desired_speed_distribution`` and ``desired_speed_std``
are aliases of ``v0``, ``v0_distribution`` and ``v0_std`` (#143). An alias
set alone is used as its ``v0*`` key; an alias and its ``v0*`` key with the
same value are accepted; with different values the deck is rejected.

The run normalises the aliases in place
(:func:`normalize_distribution_speed_aliases`); the configuration check
calls :func:`check_speed_aliases`, which raises the same error and leaves
the scenario untouched. Imports stay light: no JuPedSim, pedpy or shapely,
so ``--show-config``, the TUI and the GUI can call it (#612).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

SPEED_KEY_ALIASES = (
    ("desired_speed", "v0"),
    ("desired_speed_distribution", "v0_distribution"),
    ("desired_speed_std", "v0_std"),
)


def _check_speed_pairs(params: dict[str, Any], dist_id: str) -> None:
    """Raise ValueError for the first alias whose ``v0*`` key differs."""
    for alias, canonical in SPEED_KEY_ALIASES:
        if alias not in params or canonical not in params:
            continue
        if params[canonical] != params[alias]:
            raise ValueError(
                f"Distribution {dist_id!r} sets {alias}={params[alias]!r} and "
                f"{canonical}={params[canonical]!r}; {alias} is an alias of "
                f"{canonical}, set one of them"
            )


def _normalize_speed_aliases(params: dict[str, Any], dist_id: str) -> None:
    """Copy each ``desired_speed*`` alias to its ``v0*`` key in place.

    ``Scenario.set_agent_params`` writes both key families with equal
    values; a pair with different values is ambiguous and is rejected.
    """
    _check_speed_pairs(params, dist_id)
    for alias, canonical in SPEED_KEY_ALIASES:
        if alias in params and canonical not in params:
            params[canonical] = params[alias]


def _parameters_as_dict(params: Any) -> dict[str, Any] | None:
    """Return distribution ``parameters`` as a dict, or None if not one."""
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError:
            return None
    return params if isinstance(params, dict) else None


def _alias_parameters(data: Any) -> Iterator[tuple[str, dict, dict[str, Any]]]:
    """Yield ``(dist_id, dist_data, params)`` of each distribution with an alias.

    ``params`` is the parsed dict of string-encoded ``parameters`` (a new
    object) or the ``parameters`` dict itself. Anything that is not a dict
    is left for the loaders.
    """
    if not isinstance(data, dict):
        return
    distributions = data.get("distributions")
    if not isinstance(distributions, dict):
        return
    for dist_id, dist_data in distributions.items():
        if not isinstance(dist_data, dict):
            continue
        params = _parameters_as_dict(dist_data.get("parameters"))
        if params is None:
            continue
        if not any(alias in params for alias, _ in SPEED_KEY_ALIASES):
            continue
        yield dist_id, dist_data, params


def check_speed_aliases(raw: Any) -> None:
    """Raise the run's ValueError if a distribution sets a conflicting pair.

    Checks the distributions in order and stops at the first conflict, as
    the run does. ``raw`` is not modified.
    """
    for dist_id, _, params in _alias_parameters(raw):
        _check_speed_pairs(params, dist_id)


def normalize_distribution_speed_aliases(data: Any) -> None:
    """Apply ``_normalize_speed_aliases`` to every distribution of ``data``.

    String-encoded ``parameters`` are replaced by the parsed dict only when
    they contain an alias; anything else is left for the loaders.
    """
    for dist_id, dist_data, params in _alias_parameters(data):
        _normalize_speed_aliases(params, dist_id)
        dist_data["parameters"] = params
