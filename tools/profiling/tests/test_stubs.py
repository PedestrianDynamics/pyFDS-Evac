"""perf_run.py stubs nss and nst (Task 1 of the G3 plan)."""
import dis
import importlib.util
import runpy
import sys
import types
from pathlib import Path

import pytest

WT = Path(__file__).resolve().parents[1]
PERF_RUN = WT / "instrument" / "perf_run.py"
FROZEN_DSR = Path("/Users/chraibi/profiling-stage/wt_8f7d29a2/pyfds_evac/core/direct_steering_runtime.py")


def _fake_app(monkeypatch):
    """A fake pyfds_evac.core with the two patch targets."""
    fds = types.ModuleType("pyfds_evac.core.fds_sampling")
    dsr = types.ModuleType("pyfds_evac.core.direct_steering_runtime")
    scen = types.ModuleType("pyfds_evac.core.scenario")

    class SliceFieldSampler:
        def __init__(self, quantity="EXTINCTION COEFFICIENT"):
            self.quantity = quantity
            self.horizon_calls = []

        def _time_index(self, ts):
            self.horizon_calls.append(ts)
            if ts > 100:
                raise ValueError("horizon")
            return 0

        def sample(self, time_s, x, y):
            return 0.5

    def reached_stage(x, y, target, stage_cfg, agent_radius):
        return "original"

    fds.SliceFieldSampler = SliceFieldSampler
    dsr.reached_stage = reached_stage
    dsr.TARGET_REACH_MARGIN_M = 0.5
    scen.reached_stage = reached_stage
    for name, mod in [("pyfds_evac", types.ModuleType("pyfds_evac")),
                      ("pyfds_evac.core", types.ModuleType("pyfds_evac.core")),
                      ("pyfds_evac.core.fds_sampling", fds),
                      ("pyfds_evac.core.direct_steering_runtime", dsr),
                      ("pyfds_evac.core.scenario", scen)]:
        monkeypatch.setitem(sys.modules, name, mod)
    return fds, dsr, scen


def _load_perf_run(monkeypatch, stub_env):
    """Load perf_run.py as a module without starting run.py."""
    monkeypatch.setenv("PYFDS_PERF_STUB", stub_env)
    monkeypatch.delenv("PYFDS_PERF_COUNTERS_OUT", raising=False)
    monkeypatch.delenv("PYFDS_PERF_RESULT_OUT", raising=False)
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    calls = []
    monkeypatch.setattr(runpy, "run_path", lambda *a, **k: calls.append(a))
    spec = importlib.util.spec_from_file_location("perf_run_under_test", PERF_RUN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert len(calls) == 1          # it would have started run.py
    return mod


def test_nss_returns_neutral_value_after_horizon_check(monkeypatch):
    fds, _, _ = _fake_app(monkeypatch)
    _load_perf_run(monkeypatch, "nss")
    s = fds.SliceFieldSampler()
    assert s.sample(10.0, 1.0, 2.0) == 0.0
    assert s.horizon_calls == [10.0]
    with pytest.raises(ValueError):
        s.sample(200.0, 1.0, 2.0)


@pytest.mark.parametrize("quantity, expected", [
    ("OXYGEN VOLUME FRACTION", 0.209),
    ("CARBON MONOXIDE VOLUME FRACTION", 0.0),
    ("CARBON DIOXIDE VOLUME FRACTION", 0.0),
    ("HYDROGEN CYANIDE VOLUME FRACTION", 0.0),
    ("EXTINCTION COEFFICIENT", 0.0),
    ("TEMPERATURE", 0.0),
])
def test_nss_keeps_oxygen_ambient(monkeypatch, quantity, expected):
    fds, _, _ = _fake_app(monkeypatch)
    _load_perf_run(monkeypatch, "nss")
    s = fds.SliceFieldSampler(quantity)
    assert s.sample(1.0, 0.0, 0.0) == expected
    assert s.sample(2.0, 0.0, 0.0) == expected


def test_nss_oxygen_is_ambient_for_the_frozen_fed_field(monkeypatch):
    """Through the real FED field the stubbed oxygen reads 20.9 %, above the hypoxia threshold."""
    pytest.importorskip("pyfds_evac.core.fed")
    from types import SimpleNamespace

    from pyfds_evac.core.fds_sampling import SliceFieldSampler
    from pyfds_evac.core.fed import FdsFedField

    monkeypatch.setattr(SliceFieldSampler, "sample", SliceFieldSampler.sample)
    monkeypatch.setenv("PYFDS_PERF_STUB", "nss")
    monkeypatch.delenv("PYFDS_PERF_COUNTERS_OUT", raising=False)
    monkeypatch.delenv("PYFDS_PERF_RESULT_OUT", raising=False)
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(runpy, "run_path", lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location("perf_run_real_app", PERF_RUN)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))

    def sampler(quantity):
        s = object.__new__(SliceFieldSampler)
        s._slice = SimpleNamespace(quantity=SimpleNamespace(name=quantity))
        s._time_index = lambda time_s: 0
        return s

    field = FdsFedField(
        sampler("CARBON MONOXIDE VOLUME FRACTION"),
        sampler("CARBON DIOXIDE VOLUME FRACTION"),
        sampler("OXYGEN VOLUME FRACTION"),
    )
    inputs = field.sample_inputs(5.0, 1.0, 2.0)
    assert inputs.o2_volume_fraction_percent == pytest.approx(20.9)
    assert inputs.co_volume_fraction_percent == 0.0
    assert inputs.co2_volume_fraction_percent == 0.0


def test_nst_point_distance_only_on_both_bindings(monkeypatch):
    _, dsr, scen = _fake_app(monkeypatch)
    _load_perf_run(monkeypatch, "nst")
    assert dsr.reached_stage is scen.reached_stage
    assert scen.reached_stage(0.0, 0.0, (0.6, 0.0), {"stage_type": "exit"}, 0.2) is True
    assert scen.reached_stage(0.0, 0.0, (0.8, 0.0), {"stage_type": "exit"}, 0.2) is False
    assert scen.reached_stage(0.0, 0.0, None, {"stage_type": "checkpoint"}, 0.2) is False


def test_no_stub_leaves_app_untouched(monkeypatch):
    fds, _, scen = _fake_app(monkeypatch)
    _load_perf_run(monkeypatch, "")
    assert fds.SliceFieldSampler().sample(1.0, 0.0, 0.0) == 0.5
    assert scen.reached_stage(0, 0, None, {}, 0.2) == "original"


def test_unknown_stub_is_refused(monkeypatch):
    _fake_app(monkeypatch)
    with pytest.raises(SystemExit, match="unknown stub"):
        _load_perf_run(monkeypatch, "bogus")


@pytest.mark.skipif(not FROZEN_DSR.exists(), reason="frozen worktree not on this machine")
def test_margin_matches_frozen_source():
    assert "TARGET_REACH_MARGIN_M = 0.5" in FROZEN_DSR.read_text()


def test_memo_log_handler_writes_the_debug_line(monkeypatch, tmp_path):
    import logging
    _fake_app(monkeypatch)
    path = tmp_path / "memo.log"
    logger = logging.getLogger("pyfds_evac.core.scenario")
    monkeypatch.setattr(logger, "level", logger.level)
    monkeypatch.setattr(logger, "handlers", list(logger.handlers))
    monkeypatch.setenv("PYFDS_PERF_MEMO_LOG", str(path))
    _load_perf_run(monkeypatch, "")
    logger.debug("Reroute debug: nodes=%d", 5)
    logger.debug("FED-rate memo: %d hits, %d misses, %d clears", 3, 2, 0)
    assert path.read_text() == "FED-rate memo: 3 hits, 2 misses, 0 clears\n"
    assert logger.level == logging.DEBUG
    logger.handlers[-1].close()


def _fake_numpy_lookup_app(monkeypatch):
    """A fake sampler with the parts the nlk stub uses; its own `sample` must not run."""
    import numpy as np

    fds, _, _ = _fake_app(monkeypatch)

    class SliceFieldSampler:
        def __init__(self):
            self._cached_time_s = None
            self._cached_t_index = 0
            self.horizon_calls = []
            self.numpy_calls = []
            self.subslice = types.SimpleNamespace(
                data=np.array([[[1.0, 2.0], [3.0, 4.0]], [[5.0, 6.0], [7.0, 8.0]]])
            )

        def _time_index(self, ts):
            self.horizon_calls.append(ts)
            if ts > 100:
                raise ValueError("horizon")
            return 1 if ts >= 5.0 else 0

        def _find_subslice(self, x, y):
            return self.subslice if 0.0 <= x <= 2.0 and 0.0 <= y <= 2.0 else None

        def _axes(self, subslice):
            return [0.0, 2.0], [0.0, 2.0]

        def _nearest_index(self, coords, value):
            self.numpy_calls.append((tuple(coords), value))
            return 0 if value < 1.0 else 1

        def sample(self, time_s, x, y):
            raise AssertionError("the shared lookup ran")

    fds.SliceFieldSampler = SliceFieldSampler
    return fds


def test_nlk_restores_the_numpy_lookup(monkeypatch):
    fds = _fake_numpy_lookup_app(monkeypatch)
    _load_perf_run(monkeypatch, "nlk")
    s = fds.SliceFieldSampler()
    assert s.sample(5.0, 1.5, 0.5) == 7.0          # frame 1, i = 1, j = 0
    assert [v for _, v in s.numpy_calls] == [1.5, 0.5]
    assert s.sample(5.0, 0.5, 1.5) == 6.0          # frame 1, i = 0, j = 1
    assert s.horizon_calls == [5.0]                # the time index is cached per time, as before


def test_nlk_keeps_the_horizon_and_outside_point_errors(monkeypatch):
    fds = _fake_numpy_lookup_app(monkeypatch)
    _load_perf_run(monkeypatch, "nlk")
    s = fds.SliceFieldSampler()
    with pytest.raises(ValueError, match="horizon"):
        s.sample(200.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="outside the sampled FDS slice domain"):
        s.sample(1.0, 9.0, 1.0)


def test_nrp_restores_the_exact_exit_distance(monkeypatch):
    _, dsr, scen = _fake_app(monkeypatch)
    calls = []
    dsr.EXIT_REACH_TOLERANCE_M = 0.03
    dsr.distance_to_polygon = lambda x, y, polygon: calls.append((x, y)) or (0.0 if polygon == "near" else 9.0)
    dsr.is_inside_polygon = lambda x, y, polygon: polygon == "inside"
    _load_perf_run(monkeypatch, "nrp")
    assert dsr.reached_stage is scen.reached_stage
    assert scen.reached_stage(50.0, 50.0, None, {"stage_type": "exit", "polygon": "near"}, 0.2) is True
    assert scen.reached_stage(50.0, 50.0, None, {"stage_type": "exit", "polygon": "far"}, 0.2) is False
    assert calls == [(50.0, 50.0), (50.0, 50.0)]           # the exact distance for every exit test
    assert scen.reached_stage(0.0, 0.0, (0.6, 0.0), {"stage_type": "zone"}, 0.2) is True     # 0.2 + 0.5 margin
    assert scen.reached_stage(0.0, 0.0, (0.8, 0.0), {"stage_type": "zone"}, 0.2) is False
    assert scen.reached_stage(0.5, 0.5, None, {"stage_type": "checkpoint", "polygon": "inside"}, 0.2) is True
    assert scen.reached_stage(0.5, 0.5, None, {"stage_type": "exit"}, 0.2) is False           # exit without polygon


def test_nrp_binds_its_imports_at_install_time(monkeypatch):
    _, dsr, _ = _fake_app(monkeypatch)
    _load_perf_run(monkeypatch, "nrp")
    ops = {i.opname for i in dis.get_instructions(dsr.reached_stage)}
    assert "IMPORT_NAME" not in ops            # a per-call import would add cost to the nrp arm only
