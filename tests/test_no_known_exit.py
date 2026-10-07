"""An agent that knows no exit (#610): the no_known_exit setting.

no_known_exit is set per distribution: default_route (default),
explore, return or stay. The opt-in modes act at each
re-evaluation, so a run without a reroute pass rejects them (D33).
"""

from __future__ import annotations

import pytest

from pyfds_evac.config import rules
from pyfds_evac.core.cognitive_map import distribution_no_known_exit
from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.scenario import _check_run_modes

CONFIG = RerouteConfig()


class TestRunModes:
    """C5 / D33: an opt-in mode needs a reroute pass."""

    MODES = {"d0": "explore"}

    def test_smoke_blind_is_rejected_with_the_control_named(self):
        with pytest.raises(ValueError) as excinfo:
            _check_run_modes(True, None, None, None, None, self.MODES)
        message = str(excinfo.value)
        assert "'d0'" in message and "'explore'" in message
        assert "clear-air run (no --fds-dir)" in message

    def test_rerouting_off_is_rejected(self):
        with pytest.raises(ValueError, match="needs rerouting"):
            _check_run_modes(False, None, None, None, None, self.MODES)

    def test_the_default_stays_allowed(self):
        _check_run_modes(True, None, None, None, None, {"d0": "default_route"})
        _check_run_modes(False, CONFIG, None, None, None, self.MODES)

    @staticmethod
    def _raw(mode):
        return {"distributions": {"d0": {"parameters": {"no_known_exit": mode}}}}

    def test_the_front_ends_refuse_before_a_run(self):
        class Opts:
            smoke_blind = True
            enable_rerouting = True

        issue = rules.no_known_exit_issue(Opts(), self._raw("stay"))
        assert issue is not None and issue.rule == "D33"
        assert "clear-air run" in issue.message
        assert rules.no_known_exit_issue(Opts(), self._raw(None)) is None

    def test_an_unknown_mode_names_its_distribution(self):
        with pytest.raises(ValueError, match="distribution 'd0'.*'wait'"):
            distribution_no_known_exit(self._raw("wait"))
        assert rules.scenario_issue(self._raw("wait")) is not None
