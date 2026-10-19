"""perf_counters detail group: route-path timers and memo-key counts (Task 1 of the G4 plan)."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

WT = Path(__file__).resolve().parents[1]
PERF_COUNTERS = WT / "instrument" / "perf_counters.py"


class _Quantity:
    name = "EXTINCTION COEFFICIENT"


class _Slice:
    quantity = _Quantity()


def _sampler_class():
    """A fresh class per test: _wrap marks wrapped methods on the class itself."""

    class SliceFieldSampler:
        _LINE_CACHE_SIZE = 8

        def __init__(self):
            self._slice = _Slice()
            self._t_index_cache = {}
            self._line_cache = {}

        def sample(self, time_s, x, y):
            return 0.5

        def read_cells(self, part, times):
            return np.zeros(len(times))

        def line_parts(self, x0, y0, x1, y1):
            return []

        def _time_index(self, ts):
            return int(ts)

        def _frames(self, times):
            if np.all(times == times[0]):
                return int(times[0])
            return times.astype(int)

    return SliceFieldSampler


class _Part:
    def __init__(self):
        self.subslice = object()
        self.cells = (np.array([1, 2]), np.array([3, 4]))


def _module(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _fake_app(monkeypatch):
    """Fake pyfds_evac.core modules with every patch target of _hook_detail."""
    SliceFieldSampler = _sampler_class()
    samplers = [SliceFieldSampler(), SliceFieldSampler()]

    class _FedRateAdapter:
        def __init__(self, model):
            self._model = model

        def sample_fed_rate(self, time_s, x, y):
            for sampler in samplers:
                sampler.sample(time_s, x, y)
            return 0.0

    def _cell_los_stats(sampler, part, times):
        sampler.read_cells(part, times)
        return 0.0

    rg = _module(
        "pyfds_evac.core.route_graph",
        evaluate_segment=lambda *a, **k: 1.0,
        _first_leg=lambda *a, **k: 2.0,
        _first_leg_dose=lambda *a, **k: 0.0,
        _cell_los_stats=_cell_los_stats,
        _step_los_stats=lambda *a, **k: 3.0,
        _polyline_stats=lambda *a, **k: 4.0,
        _generate_candidates=lambda graph, *a, **k: [],
    )
    fs = _module("pyfds_evac.core.fds_sampling", SliceFieldSampler=SliceFieldSampler,
                 _LINE_CACHE_SIZE=8)
    scen = _module("pyfds_evac.core.scenario", _FedRateAdapter=_FedRateAdapter,
                   _defer_flow_spawn=lambda deferred, source_id, time_s: None)
    cov = _module("pyfds_evac.core.fds_coverage", model_samplers=lambda *models: samplers)
    dsr = _module("pyfds_evac.core.direct_steering_runtime",
                  reached_stage=lambda x, y, target, stage_cfg, agent_radius: False,
                  distance_to_polygon=lambda x, y, polygon: 0.0)
    si = _module("pyfds_evac.core.simulation_init",
                 _refuses_position=lambda error: False,
                 _occupied=lambda *a, **k: ([], []),
                 _crowds_agents=lambda *a, **k: False)
    cognitive_map = _module("pyfds_evac.core.cognitive_map")
    visibility = _module("pyfds_evac.core.visibility")
    core = _module("pyfds_evac.core", route_graph=rg, fds_sampling=fs, scenario=scen,
                   fds_coverage=cov, direct_steering_runtime=dsr, simulation_init=si,
                   cognitive_map=cognitive_map, visibility=visibility)
    fdsreader_simulation = _module("fdsreader.simulation")
    jupedsim_simulation = _module("jupedsim.simulation")
    for name, mod in [("fdsreader", _module("fdsreader", simulation=fdsreader_simulation)),
                      ("fdsreader.simulation", fdsreader_simulation),
                      ("jupedsim", _module("jupedsim", simulation=jupedsim_simulation)),
                      ("jupedsim.simulation", jupedsim_simulation),
                      ("pyfds_evac.core.cognitive_map", cognitive_map),
                      ("pyfds_evac.core.visibility", visibility),
                      ("pyfds_evac", _module("pyfds_evac", core=core)),
                      ("pyfds_evac.core", core),
                      ("pyfds_evac.core.route_graph", rg),
                      ("pyfds_evac.core.fds_sampling", fs),
                      ("pyfds_evac.core.scenario", scen),
                      ("pyfds_evac.core.fds_coverage", cov),
                      ("pyfds_evac.core.direct_steering_runtime", dsr),
                      ("pyfds_evac.core.simulation_init", si)]:
        monkeypatch.setitem(sys.modules, name, mod)
    return rg, scen, samplers


def _load_perf_counters():
    """A fresh perf_counters module, so counter state never leaks between tests."""
    spec = importlib.util.spec_from_file_location("perf_counters_under_test", PERF_COUNTERS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dump(pc, tmp_path):
    out = tmp_path / "counters.json"
    pc.dump(str(out))
    return json.loads(out.read_text())


def test_route_paths_time_and_key_the_driven_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("PYFDS_PERF_DETAIL", "1")
    rg, scen, samplers = _fake_app(monkeypatch)
    pc = _load_perf_counters()
    pc._hook_detail(rg, scen)

    rg.evaluate_segment()
    rg.evaluate_segment()
    part = _Part()
    times = np.array([3.0, 3.0])
    for _ in range(3):
        rg._cell_los_stats(samplers[0], part, times=times)
    twin = _Part()
    twin.subslice = part.subslice
    rg._cell_los_stats(samplers[0], twin, times=times)    # same cells by value, other arrays

    def evaluate_segment():
        samplers[0].sample(4.0, 1.0, 2.0)
        samplers[0].sample(4.0, 1.0, 2.0)

    evaluate_segment()                                    # route side: a frame in the chain
    samplers[0].sample(4.0, 1.0, 2.0)                     # not route side
    adapter = scen._FedRateAdapter(object())
    adapter.sample_fed_rate(5.0, 1.0, 2.0)
    adapter.sample_fed_rate(5.0, 1.0, 2.0)
    adapter.sample_fed_rate(5.0, 1.0, 2.5)

    detail = _dump(pc, tmp_path)["detail"]
    assert detail["route_paths_overhead"]["noop_wrapper_calls"] == 1_000_000
    paths = detail["route_paths"]
    assert paths["evaluate_segment"]["calls"] == 2
    assert paths["cell_los_stats"]["calls"] == 4
    assert paths["read_cells"]["total"] == 4
    assert paths["read_cells"]["distinct"] == 1
    assert paths["sample_fed_rate"]["total"] == 3
    assert paths["sample_fed_rate"]["distinct"] == 2
    sample_route = paths["sample_route"]
    assert (sample_route["calls"], sample_route["total"], sample_route["distinct"]) == (2, 2, 1)
    assert pc.route_key_frames(3) == (3,)
    assert pc.route_key_frames(np.int64(3)) == (3,)
    assert pc.route_key_frames(np.array([3, 3])) == (3, 3)
    for stats in paths.values():
        assert stats["seconds"] >= 0.0
    for name in ("read_cells", "sample_fed_rate", "sample_route"):
        assert paths[name]["capped"] is False


def test_no_detail_run_writes_no_route_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("PYFDS_PERF_DETAIL", raising=False)
    pc = _load_perf_counters()

    detail = _dump(pc, tmp_path)["detail"]
    assert detail["enabled"] is False
    assert "route_paths" not in detail
    assert "route_paths_overhead" not in detail


def _hooked(monkeypatch, calibration_calls=10):
    """Fake app with the detail group installed; a short calibration loop keeps tests fast."""
    monkeypatch.setenv("PYFDS_PERF_DETAIL", "1")
    rg, scen, samplers = _fake_app(monkeypatch)
    pc = _load_perf_counters()
    monkeypatch.setattr(pc, "NOOP_CALIBRATION_CALLS", calibration_calls)
    return pc, rg, scen, samplers


def _paths(pc, tmp_path):
    return _dump(pc, tmp_path)["detail"]["route_paths"]


def test_samplers_at_one_point_are_distinct_route_keys(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)

    def evaluate_segment():
        for sampler in samplers:
            sampler.sample(4.0, 1.0, 2.0)
        samplers[0].sample(4.0, 1.0, 2.0)

    evaluate_segment()

    sample_route = _paths(pc, tmp_path)["sample_route"]
    assert (sample_route["total"], sample_route["distinct"]) == (3, 2)


def test_fed_species_reads_are_not_route_scalar_samples(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)

    scen._FedRateAdapter(object()).sample_fed_rate(5.0, 1.0, 2.0)

    paths = _paths(pc, tmp_path)
    assert paths["sample_fed_rate"]["total"] == 1
    assert paths["sample_route"]["calls"] == 0
    assert paths["sample_route"]["total"] == 0


def test_all_paths_are_listed_without_calls(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)

    paths = _paths(pc, tmp_path)
    assert sorted(paths) == sorted(
        ["evaluate_segment", "first_leg", "cell_los_stats", "step_los_stats", "read_cells",
         "line_parts", "sample_fed_rate", "sample_route",
         "first_leg_dose", "segment", "first_leg_r01"])
    for name in ("read_cells", "sample_fed_rate", "sample_route"):
        assert (paths[name]["total"], paths[name]["distinct"]) == (0, 0)
        assert paths[name]["capped"] is False
    assert paths["evaluate_segment"]["calls"] == 0


def test_capped_key_set_keeps_counting_and_reports_the_cap(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    monkeypatch.setattr(pc, "_KEYS_CAP", 2)
    pc._hook_detail(rg, scen)

    adapter = scen._FedRateAdapter(object())
    for y in (1.0, 2.0, 3.0, 4.0):
        adapter.sample_fed_rate(5.0, 1.0, y)

    fed = _paths(pc, tmp_path)["sample_fed_rate"]
    assert (fed["total"], fed["distinct"], fed["capped"]) == (4, 2, True)


def test_equal_frames_key_alike_as_int_and_array(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)
    sampler, part, times = samplers[0], _Part(), np.array([3.0, 3.0])

    sampler.read_cells(part, times)
    sampler._frames = lambda t: np.array([3, 3])
    sampler.read_cells(part, times)

    read_cells = _paths(pc, tmp_path)["read_cells"]
    assert (read_cells["total"], read_cells["distinct"]) == (2, 1)


def test_hook_time_is_left_out_of_enclosing_timers(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    clock = [0.0]

    def advance(dt):
        clock[0] += dt

    monkeypatch.setattr(pc, "time", types.SimpleNamespace(perf_counter=lambda: clock[0]))
    monkeypatch.setattr(pc, "_callers", lambda depth=2, skip=2: advance(10.0) or
                        "route_graph.evaluate_segment")
    type(samplers[0]).sample = lambda self, time_s, x, y: advance(1.0)

    def evaluate_segment():
        advance(1.0)
        samplers[0].sample(4.0, 1.0, 2.0)
        advance(1.0)

    rg.evaluate_segment = evaluate_segment
    pc._hook_detail(rg, scen)

    rg.evaluate_segment()

    paths = _paths(pc, tmp_path)
    assert paths["evaluate_segment"]["seconds"] == pytest.approx(3.0)
    assert paths["evaluate_segment"]["hook_seconds"] == pytest.approx(10.0)
    assert paths["evaluate_segment"]["self_seconds"] == pytest.approx(2.0)
    assert paths["sample_route"]["seconds"] == pytest.approx(1.0)
    assert paths["sample_route"]["by_parent"] == {"evaluate_segment": pytest.approx(1.0)}
    assert paths["evaluate_segment"]["by_parent"] == {"root": pytest.approx(3.0)}


def test_paths_record_time_per_innermost_enclosing_path(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    clock = [0.0]

    def advance(dt):
        clock[0] += dt

    monkeypatch.setattr(pc, "time", types.SimpleNamespace(perf_counter=lambda: clock[0]))
    adapter = scen._FedRateAdapter(object())
    scen._FedRateAdapter.sample_fed_rate = lambda self, time_s, x, y: advance(5.0)
    rg._step_los_stats = lambda *a, **k: advance(3.0)

    def cell_los_stats():
        advance(1.0)
        rg._step_los_stats()

    def evaluate_segment():
        advance(2.0)
        rg._cell_los_stats()
        adapter.sample_fed_rate(5.0, 1.0, 2.0)

    def first_leg():
        advance(1.0)
        rg._step_los_stats()
        rg._step_los_stats()
        adapter.sample_fed_rate(5.0, 1.0, 2.0)

    rg._cell_los_stats, rg.evaluate_segment, rg._first_leg = (
        cell_los_stats, evaluate_segment, first_leg)
    pc._hook_detail(rg, scen)

    rg.evaluate_segment()
    rg._first_leg()

    paths = _paths(pc, tmp_path)
    assert paths["evaluate_segment"]["seconds"] == pytest.approx(11.0)
    assert paths["evaluate_segment"]["self_seconds"] == pytest.approx(2.0)
    assert paths["cell_los_stats"]["seconds"] == pytest.approx(4.0)
    assert paths["cell_los_stats"]["self_seconds"] == pytest.approx(1.0)
    assert paths["step_los_stats"]["seconds"] == pytest.approx(9.0)
    assert paths["step_los_stats"]["by_parent"] == {
        "cell_los_stats": pytest.approx(3.0), "first_leg": pytest.approx(6.0)}
    assert paths["sample_fed_rate"]["by_parent"] == {
        "evaluate_segment": pytest.approx(5.0), "first_leg": pytest.approx(5.0)}
    assert paths["first_leg"]["self_seconds"] == pytest.approx(1.0)


def test_key_building_leaves_existing_detail_counters_alone(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)

    def first_leg():
        samplers[0].sample(4.0, 1.0, 2.0)

    rg._first_leg = first_leg
    pc._hook_detail(rg, scen)

    rg._first_leg()
    samplers[0].read_cells(_Part(), np.array([3.0, 3.0]))

    data = _dump(pc, tmp_path)
    assert "time_index_hits" not in data["counters"]
    assert "time_index_misses" not in data["counters"]
    sample_calls = [k for k in data["counters"] if k.startswith("sampler_sample_calls[")]
    assert sample_calls
    assert not any("perf_counters." in k for k in sample_calls)


@pytest.mark.parametrize("detail", [False, True])
def test_install_hooks_the_detail_group_only_when_asked(monkeypatch, detail):
    if detail:
        monkeypatch.setenv("PYFDS_PERF_DETAIL", "1")
    else:
        monkeypatch.delenv("PYFDS_PERF_DETAIL", raising=False)
    _fake_app(monkeypatch)
    pc = _load_perf_counters()
    hooked = []
    for name in ("_hook_fdsreader", "_hook_visibility", "_hook_cognitive_map", "_hook_routing",
                 "_hook_jupedsim", "_hook_run_scenario"):
        monkeypatch.setattr(pc, name, lambda *a, **k: None)
    monkeypatch.setattr(pc, "_hook_detail", lambda *a, **k: hooked.append(a))
    monkeypatch.setattr(pc.atexit, "register", lambda *a, **k: None)

    pc.install("unused.json")

    assert bool(hooked) is detail


def _extinction(samplers):
    return types.SimpleNamespace(samplers=lambda: [samplers[0]])


def _clock(t0=10.0, horizon_end_s=40.0, decision_time_s=10.0, end_s=100.0):
    return types.SimpleNamespace(t0=t0, horizon_end_s=horizon_end_s,
                                 decision_time_s=decision_time_s, end_s=end_s)


def _leg(rg, ext, position=(1.0, 2.0), node="n1", time_s=3.0, walks=None, clock=None):
    rg._first_leg(None, position, node, time_s, ext, None, walks, clock=clock)


def test_first_leg_keys_count_computed_calls_only(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)
    ext = _extinction(samplers)

    for _ in range(3):
        _leg(rg, ext)
    walks = {"n1": types.SimpleNamespace(time_s=3.0)}
    _leg(rg, ext, walks=walks)                            # served from walks: computes nothing
    _leg(rg, ext, walks={"n1": types.SimpleNamespace(time_s=2.0)})    # stale walk: computed
    foreseen = {("n1", "foreseen"): types.SimpleNamespace(time_s=3.0)}
    _leg(rg, ext, walks=foreseen, clock=_clock())         # foreseen key served
    _leg(rg, ext, walks=foreseen)                         # plain key is another walk: computed
    _leg(rg, ext, time_s=3.4)                             # same frame
    _leg(rg, ext, position=(1.0, 2.5))
    _leg(rg, ext, node="n2")
    _leg(rg, ext, time_s=4.0)                             # other frame
    _leg(rg, ext, clock=_clock())
    _leg(rg, ext, clock=_clock(t0=11.0))
    _leg(rg, ext, clock=_clock(horizon_end_s=50.0))       # limit min(50, 100) differs
    _leg(rg, ext, clock=_clock(horizon_end_s=200.0, end_s=40.0))    # limit 40, as the first clock
    _leg(rg, ext, clock=_clock())                         # equal descriptor

    data = _dump(pc, tmp_path)
    first_leg = data["detail"]["route_paths"]["first_leg"]
    assert first_leg["calls"] == 16
    assert (first_leg["total"], first_leg["distinct"]) == (14, 7)
    assert data["counters"]["first_leg_walks_hits"] == 2


def test_first_leg_r01_merges_nearby_positions(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)
    ext = _extinction(samplers)

    _leg(rg, ext, position=(1.00, 2.00))
    _leg(rg, ext, position=(1.01, 2.00))
    _leg(rg, ext, position=(1.00, 2.20))

    paths = _paths(pc, tmp_path)
    assert (paths["first_leg"]["total"], paths["first_leg"]["distinct"]) == (3, 3)
    assert (paths["first_leg_r01"]["total"], paths["first_leg_r01"]["distinct"]) == (3, 2)
    assert paths["first_leg_r01"]["calls"] == 0


def _segment(rg, ext, fed, source="a", target="b", time_s=3.0, arrival_time_s=None, clock=None):
    rg.evaluate_segment(None, source, target, time_s, ext, fed, None, arrival_time_s, clock)


def _dose_calls(rg, scen):
    fed = scen._FedRateAdapter(object())

    def seg(**changes):
        fields = dict(source="a", target="b", length_m=5.0, fed_growth=0.1)
        return types.SimpleNamespace(**{**fields, **changes})

    def dose(waypoints=((0.0, 0.0), (3.0, 4.0)), length_m=5.0, walk_time_s=6.0, time_s=3.0,
             first=None):
        leg = types.SimpleNamespace(waypoints=list(waypoints), length_m=length_m)
        rg._first_leg_dose(leg, walk_time_s, first or seg(), time_s, fed, None)

    dose()
    dose(time_s=3.4)                                      # same FED frame
    dose(walk_time_s=7.0)
    dose(waypoints=((0.0, 0.0), (3.0, 4.5)))
    dose(length_m=5.5)
    dose(time_s=4.0)                                      # other FED frame
    dose(first=seg(fed_growth=0.2))
    dose(first=seg(length_m=4.0))


def test_segment_and_dose_keys(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)
    ext, fed = _extinction(samplers), scen._FedRateAdapter(object())

    _segment(rg, ext, fed, time_s=3.0)
    _segment(rg, ext, fed, time_s=3.4)                    # same frame
    _segment(rg, ext, fed, time_s=9.0, arrival_time_s=3.2)    # keyed on the arrival time
    _segment(rg, ext, fed, time_s=4.0)                    # other frame
    _segment(rg, ext, fed, target="c")
    _segment(rg, ext, fed, clock=_clock())

    segment = _paths(pc, tmp_path)["segment"]
    assert (segment["calls"], segment["total"], segment["distinct"]) == (0, 6, 4)
    assert segment["capped"] is False

    _dose_calls(rg, scen)

    dose = _paths(pc, tmp_path)["first_leg_dose"]
    assert (dose["calls"], dose["total"], dose["distinct"]) == (0, 8, 7)


def test_old_paths_are_unchanged(monkeypatch, tmp_path):
    pc, rg, scen, samplers = _hooked(monkeypatch)
    pc._hook_detail(rg, scen)

    rg.evaluate_segment()
    rg.evaluate_segment()
    part, times = _Part(), np.array([3.0, 3.0])
    for _ in range(3):
        rg._cell_los_stats(samplers[0], part, times=times)
    adapter = scen._FedRateAdapter(object())
    adapter.sample_fed_rate(5.0, 1.0, 2.0)
    adapter.sample_fed_rate(5.0, 1.0, 2.5)

    paths = _paths(pc, tmp_path)
    assert paths["evaluate_segment"]["calls"] == 2
    assert paths["cell_los_stats"]["calls"] == 3
    assert (paths["read_cells"]["total"], paths["read_cells"]["distinct"]) == (3, 1)
    assert (paths["sample_fed_rate"]["total"], paths["sample_fed_rate"]["distinct"]) == (2, 2)
    for name in ("first_leg_dose", "first_leg_r01"):
        assert paths[name]["calls"] == 0
    assert paths["segment"]["calls"] == 0
    assert paths["segment"]["total"] == 2
