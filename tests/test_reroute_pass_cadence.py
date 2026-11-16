"""The reroute pass follows the configured interval (issue #660).

The pass used to run at most once per simulated second, so an interval below
1 s acted as 1 s. The scenario is the 10 x 6 m two-door room of
``test_run_log``; the pass times are read from the calls the run makes to
``should_reevaluate``, one per agent at every pass after the first.
"""

from __future__ import annotations

import pytest
from test_run_log import _scenario

from pyfds_evac.core import scenario as scenario_module
from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.scenario import run_scenario


def _pass_times(monkeypatch, interval_s: float) -> list[float]:
    times: set[float] = set()
    real = scenario_module.should_reevaluate

    def recording(current_time_s, state, interval):
        times.add(round(current_time_s, 6))
        return real(current_time_s, state, interval)

    monkeypatch.setattr(scenario_module, "should_reevaluate", recording)
    run_scenario(
        _scenario(), reroute_config=RerouteConfig(reevaluation_interval_s=interval_s)
    )
    return sorted(times)


def test_half_second_interval_runs_the_pass_every_half_second(monkeypatch):
    times = _pass_times(monkeypatch, 0.5)
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert len(times) >= 3
    assert max(gaps) == pytest.approx(0.5, abs=0.05)


def test_one_second_interval_keeps_the_one_second_pass(monkeypatch):
    times = _pass_times(monkeypatch, 1.0)
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert len(times) >= 2
    assert min(gaps) == pytest.approx(1.0, abs=0.05)


@pytest.mark.parametrize("interval_s", [0.0, -1.0, float("nan")])
def test_non_positive_interval_is_rejected(interval_s):
    with pytest.raises(ValueError, match="reevaluation_interval_s must be > 0"):
        RerouteConfig(reevaluation_interval_s=interval_s)
