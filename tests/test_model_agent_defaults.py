"""Per-model agent defaults of ``create_agent_parameters`` (#836).

A spawn area that sets no ``v0`` or ``radius``, and a deck without global
model parameters, take these values. The expected numbers are literals
taken from their sources, not read from the code:

- ``v0`` 1.25 m/s and ``radius`` 0.2 m: docs/scenario-json.md, the
  ``simulationParams.number``, ``.radius``, ``.v0`` row ("10, 0.2 m,
  1.25 m/s"); 1.25 m/s is FDS+Evac's ``VEL_MEAN``
  (docs/coming-from-fds-evac.md).
- GCFM ``tau`` 0.5 s, ``a_v`` 1, ``a_min`` 0.2, ``b_min`` 0.2, ``b_max`` 0.4:
  the ``GeneralizedCentrifugalForceModelAgentParameters`` defaults of
  JuPedSim 1.4.2.
- AVM ``time_gap`` 1.06 s, ``anticipation_time`` 1.0 s, ``reaction_time``
  0.3 s: the ``AnticipationVelocityModelAgentParameters`` defaults of
  JuPedSim 1.4.2.

The GCFM ``mass`` default (80 kg; JuPedSim's own default is 1) has no cited
source and is not pinned. A JuPedSim upgrade that changes a default above
fails here on purpose: decide whether the deck default follows it.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core.simulation_init import (
    _AGENT_MODEL_TYPES,
    _sample_agent_values,
    create_agent_parameters,
)

DEFAULT_V0_MPS = 1.25
DEFAULT_RADIUS_M = 0.2
GCFM = "GeneralizedCentrifugalForceModel"
AVM = "AnticipationVelocityModel"


def _defaults(model, global_params=None):
    return create_agent_parameters(model, (0.0, 0.0), {}, global_params=global_params)


@pytest.mark.parametrize("model", _AGENT_MODEL_TYPES)
def test_v0_default(model):
    assert _defaults(model).desired_speed == DEFAULT_V0_MPS


@pytest.mark.parametrize("model", [m for m in _AGENT_MODEL_TYPES if m != GCFM])
def test_radius_default(model):
    # The GCFM parameter set carries no radius; its shape comes from
    # a_min, b_min and b_max.
    assert _defaults(model).radius == DEFAULT_RADIUS_M


@pytest.mark.parametrize("global_params", [None, SimpleNamespace()])
def test_gcfm_defaults_without_global_parameters(global_params):
    agent = _defaults(GCFM, global_params)
    assert agent.tau == 0.5
    assert agent.a_v == 1.0
    assert agent.a_min == 0.2
    assert agent.b_min == 0.2
    assert agent.b_max == 0.4


@pytest.mark.parametrize("global_params", [None, SimpleNamespace()])
def test_avm_defaults_without_global_parameters(global_params):
    agent = _defaults(AVM, global_params)
    assert agent.time_gap == 1.06
    assert agent.anticipation_time == 1.0
    assert agent.reaction_time == 0.3


class _FixedDraws:
    """An rng whose ``normal`` returns the given draws."""

    def __init__(self, draws):
        self.draws = np.asarray(draws, dtype=float)

    def normal(self, mean, std, n):
        return self.draws.copy()


def test_gaussian_v0_is_clipped_to_the_documented_range():
    # docs/coming-from-fds-evac.md: "Gaussian draws are clipped to 0.1-5.0 m/s".
    params = {"v0": 1.25, "v0_distribution": "gaussian", "v0_std": 0.3}
    draws = [0.0, 0.1, 0.5, 5.0, 7.0]
    _, v0s = _sample_agent_values(params, len(draws), _FixedDraws(draws))
    assert v0s.tolist() == [0.1, 0.1, 0.5, 5.0, 5.0]
