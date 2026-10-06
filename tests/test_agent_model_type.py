"""``create_agent_parameters`` rejects an unknown model type (#570).

It used to fall back to collision-free speed model parameters, so a
misspelled ``model_type`` silently ran a different model.
"""

from __future__ import annotations

import pytest

from pyfds_evac.core.scenario import _MODEL_BUILDERS
from pyfds_evac.core.simulation_init import create_agent_parameters


def test_unknown_model_type_raises_naming_value_and_accepted_names():
    with pytest.raises(ValueError) as excinfo:
        create_agent_parameters("NoSuchModel", (0.0, 0.0), {})
    message = str(excinfo.value)
    assert "NoSuchModel" in message
    for name in _MODEL_BUILDERS:
        assert name in message


def test_accepted_model_types_match_model_builders():
    from pyfds_evac.core.simulation_init import _AGENT_MODEL_TYPES

    assert set(_AGENT_MODEL_TYPES) == set(_MODEL_BUILDERS)
