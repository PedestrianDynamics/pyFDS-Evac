"""A run says whether it computed a gas FED (#137).

A disabled FED is absent from the result, not zero: ``fed_history`` is
``None`` and ``metrics`` has no ``fed_max``. ``metrics["fed_enabled"]``
states it on every run, so a caller need not infer it from a missing key.
"""

from __future__ import annotations

from harness import CorridorSpec, corridor_scenario, make_fed_model, uniform

from pyfds_evac.config.messages import fed_without_gases
from pyfds_evac.core.scenario import run_scenario


def _run(fed_model=None):
    spec = CorridorSpec(
        length_m=10.0,
        width_m=4.0,
        num_agents=2,
        v0=1.2,
        seed=3,
        max_simulation_time=20.0,
    )
    return run_scenario(corridor_scenario(spec), seed=spec.seed, fed_model=fed_model)


def test_a_run_without_fed_says_so():
    result = _run()
    try:
        assert result.metrics["fed_enabled"] is False
        assert "fed_max" not in result.metrics
        assert result.fed_history is None
    finally:
        result.cleanup()


def test_a_run_with_fed_says_so():
    fed = make_fed_model(
        co_volume_fraction=uniform(0.0),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
    )
    result = _run(fed)
    try:
        assert result.metrics["fed_enabled"] is True
        assert "fed_max" in result.metrics
    finally:
        result.cleanup()


def test_the_warning_promises_no_zeros():
    text = fed_without_gases("d", ["co"])
    assert "zero dose" not in text
    assert "no gas FED" in text
