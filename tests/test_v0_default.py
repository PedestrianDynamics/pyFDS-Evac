"""An agent whose spawn area sets no v0 walks at FDS+Evac's VEL_MEAN, 1.25 m/s."""

import numpy as np

from pyfds_evac.core import scenario, simulation_init


def test_immediate_spawn_default_v0():
    _, v0s = simulation_init._sample_agent_values({}, 3, np.random.RandomState(0))
    assert np.all(v0s == 1.25)


def test_flow_spawn_default_v0():
    _, v0s = scenario._sample_agent_values({}, 3, np.random.default_rng(0))
    assert np.all(v0s == 1.25)


def test_v0_stays_overridable():
    _, v0s = simulation_init._sample_agent_values(
        {"v0": 1.2}, 3, np.random.RandomState(0)
    )
    assert np.all(v0s == 1.2)
