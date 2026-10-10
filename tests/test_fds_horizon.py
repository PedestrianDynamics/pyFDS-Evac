"""Sampling past the end of the FDS output (#340).

Past the last slice frame there is no smoke data. Nearest-timestep lookup used
to hold the last frame silently, so agents walked through frozen smoke and kept
accumulating dose at the final concentrations. Now a sample more than one
output interval past the end raises ``FdsHorizonError``; the hold is opt-in
through ``--allow-fds-horizon-hold`` and logged once.
"""

import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import (
    FdsHorizonError,
    SliceFieldSampler,
    fds_output_horizon,
)
from pyfds_evac.core.fed import FdsFedField, FdsHeatField
from pyfds_evac.core.run_config import _check_fds_horizon
from pyfds_evac.core.smoke_speed import ExtinctionField
from pyfds_evac.core.visibility import VisibilityModel, _VisMapCache

_REPO = Path(__file__).resolve().parents[1]
_FDS_DIR = str(_REPO / "assets" / "fed_slice_height" / "fds")  # T_END = 2 s


class _Slice:
    """One-cell slice with frames at 0..10 s whose value is the frame index."""

    def __init__(self, name="SOOT EXTINCTION COEFFICIENT", times=None):
        self.times = np.arange(0.0, 11.0) if times is None else np.asarray(times)
        self.quantity = SimpleNamespace(name=name)
        extent = SimpleNamespace(x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0)
        mesh = SimpleNamespace(coordinates={"x": np.array([0.0]), "y": [0.0]})
        n = len(self.times)
        data = np.arange(float(n)).reshape(n, 1, 1)
        self.subslices = [
            SimpleNamespace(extent=extent, mesh=mesh, cell_centered=False, data=data)
        ]

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


def _horizon_warnings(caplog):
    return [r for r in caplog.records if "past the FDS output" in r.getMessage()]


def test_within_one_output_interval_passes():
    assert SliceFieldSampler(_Slice()).sample(10.5, 0.5, 0.5) == 10.0


def test_beyond_one_output_interval_raises_naming_quantity_and_times():
    with pytest.raises(FdsHorizonError) as excinfo:
        SliceFieldSampler(_Slice()).sample(30.0, 0.5, 0.5)
    message = str(excinfo.value)
    assert "SOOT EXTINCTION COEFFICIENT" in message
    assert "t=30.0 s" in message
    assert "t=10.0 s" in message
    assert isinstance(excinfo.value, ValueError)


def test_clipped_final_frame_keeps_the_output_interval():
    """FDS clips the last frame at T_END; the tolerance is still one interval."""
    times = [0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0, 10.0]
    sampler = SliceFieldSampler(_Slice(times=times))
    assert sampler.output_interval_s == pytest.approx(1.5)
    assert sampler.sample(11.4, 0.5, 0.5) == 7.0
    with pytest.raises(FdsHorizonError):
        sampler.sample(11.6, 0.5, 0.5)


def test_horizon_is_checked_before_the_domain():
    """A point outside the slice past T_END reports the horizon, not the domain."""
    with pytest.raises(FdsHorizonError):
        SliceFieldSampler(_Slice()).sample(30.0, 5.0, 5.0)


def test_flag_holds_the_last_frame_and_warns_once(caplog):
    sampler = SliceFieldSampler(_Slice(), allow_horizon_hold=True)
    with caplog.at_level(logging.WARNING):
        assert sampler.sample(30.0, 0.5, 0.5) == 10.0
        assert sampler.sample(40.0, 0.5, 0.5) == 10.0
    assert len(_horizon_warnings(caplog)) == 1


def test_extinction_field_does_not_turn_the_horizon_into_clear_air():
    field = ExtinctionField(SliceFieldSampler(_Slice()))
    assert field.sample_extinction(5.0, 5.0, 5.0) == 0.0  # out of domain
    with pytest.raises(FdsHorizonError):
        field.sample_extinction(30.0, 0.5, 0.5)


def test_fed_field_does_not_turn_the_horizon_into_zero_dose():
    def sampler(name):
        return SliceFieldSampler(_Slice(name))

    field = FdsFedField(sampler("CO"), sampler("CO2"), sampler("O2"))
    with pytest.raises(FdsHorizonError):
        field.sample_inputs(30.0, 0.5, 0.5)
    field = FdsFedField(
        SliceFieldSampler(_Slice("CO"), allow_horizon_hold=True),
        SliceFieldSampler(_Slice("CO2"), allow_horizon_hold=True),
        SliceFieldSampler(_Slice("O2"), allow_horizon_hold=True),
        hcn=sampler("HCN"),
    )
    with pytest.raises(FdsHorizonError):
        field.sample_inputs(30.0, 0.5, 0.5)


def test_heat_field_does_not_turn_the_horizon_into_no_heat():
    field = FdsHeatField(SliceFieldSampler(_Slice("TEMPERATURE")))
    with pytest.raises(FdsHorizonError):
        field.sample_inputs(30.0, 0.5, 0.5)


def _vis_model(**kwargs):
    cache = _VisMapCache(
        time_points=np.array([0.0, 10.0]),
        x_coords=np.array([0.0, 1.0]),
        y_coords=np.array([0.0]),
        vis=np.ones((2, 1, 1, 2), dtype=bool),
        metres=np.full((2, 1, 1, 2), 12.0),
        output_interval_s=5.0,
    )
    signs = {"e0": {"x": 0.0, "y": 0.0}}
    with patch("pyfds_evac.core.visibility._resolve_vis", return_value=cache):
        return VisibilityModel("unused", signs, **kwargs)


def test_visibility_raises_past_one_fds_output_interval():
    """The run-wide window (#510): last frame plus one FDS output interval.

    The interval is the extinction slice's (5 s here), not the vismap step.
    """
    model = _vis_model()
    assert model.node_is_visible(15.0, 0.0, 0.0, "e0") is True
    assert model.visibility_to_node(15.0, 0.0, 0.0, "e0") == 12.0
    with pytest.raises(FdsHorizonError):
        model.node_is_visible(15.1, 0.0, 0.0, "e0")
    with pytest.raises(FdsHorizonError):
        model.visibility_to_node(15.1, 0.0, 0.0, "e0")


def test_visibility_flag_holds_and_warns_once(caplog):
    model = _vis_model(allow_horizon_hold=True)
    with caplog.at_level(logging.WARNING):
        assert model.node_is_visible(30.0, 0.0, 0.0, "e0") is True
        assert model.visibility_to_node(40.0, 0.0, 0.0, "e0") == 12.0
    assert len(_horizon_warnings(caplog)) == 1


def test_committed_case_horizon():
    last, interval = fds_output_horizon(_FDS_DIR)
    assert last == pytest.approx(2.0)
    assert interval == pytest.approx(1.383, abs=1e-3)  # not the clipped 0.617


def _opts(**overrides):
    return SimpleNamespace(**{"fds_dir": _FDS_DIR, **overrides})


def test_run_past_the_fds_output_fails_at_setup():
    with pytest.raises(ValueError) as excinfo:
        _check_fds_horizon(SimpleNamespace(max_simulation_time=300.0), _opts())
    message = str(excinfo.value)
    assert "max_simulation_time=300.0 s" in message
    assert "t=2.0 s" in message
    assert "--allow-fds-horizon-hold" in message


def test_run_within_the_fds_output_passes_setup():
    _check_fds_horizon(SimpleNamespace(max_simulation_time=2.0), _opts())


def test_flag_turns_the_setup_check_into_a_warning():
    messages = []
    _check_fds_horizon(
        SimpleNamespace(max_simulation_time=300.0),
        _opts(allow_fds_horizon_hold=True),
        messages.append,
    )
    assert len(messages) == 1
    assert messages[0].startswith("Warning: max_simulation_time=300.0 s")


def test_cli_exposes_the_flag():
    from run import _build_parser

    parser = _build_parser()
    assert parser.parse_args(["--scenario", "x"]).allow_fds_horizon_hold is False
    args = parser.parse_args(["--scenario", "x", "--allow-fds-horizon-hold"])
    assert args.allow_fds_horizon_hold is True


class _HorizonAfterOneSecond:
    """Extinction field whose FDS output ends at t = 1 s."""

    def sample_extinction(self, time_s, x, y):
        if time_s > 1.0:
            raise FdsHorizonError(f"past the FDS output at t={time_s}")
        return 0.0


def test_flow_spawn_does_not_swallow_the_horizon():
    """A flow spawn past T_END ranks routes on smoke; it must not just skip."""
    import copy
    import json

    from pyfds_evac.core.scenario import Scenario, run_scenario
    from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

    asset = _REPO / "assets" / "t_junction"
    raw = json.loads((asset / "config_full.json").read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    sim_params["max_simulation_time"] = 5.0
    raw["distributions"]["jps-distributions_0"]["parameters"].update(
        {
            "number": 4,
            "use_flow_spawning": True,
            "flow_start_time": 0,
            "flow_end_time": 3,
        }
    )
    scenario = Scenario(
        raw=raw,
        walkable_area_wkt=(asset / "geometry.wkt").read_text(encoding="utf-8").strip(),
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params=sim_params,
        source_path=None,
    )
    # A long smoke update interval keeps the per-step speed update at t = 0,
    # and without rerouting only the spawn-time route ranking samples past
    # the horizon.
    smoke = SmokeSpeedModel(
        _HorizonAfterOneSecond(), SmokeSpeedConfig(update_interval_s=100.0)
    )
    with pytest.raises(FdsHorizonError):
        run_scenario(scenario, seed=42, smoke_speed_model=smoke)


# --- #666: route foresight stops at the last FDS frame -------------------------


class _CorridorSlice(_Slice):
    """Slice over x 0..20 m, y -1..1 m, frames 0..10 s; K = 0.01 x frame index.

    Nodes every 2 m in x, so route smoke, read once per grid cell (#653),
    is read at x = 0, 2, ..., 20 along the corridor.
    """

    def __init__(self):
        super().__init__()
        extent = SimpleNamespace(x_start=0.0, x_end=20.0, y_start=-1.0, y_end=1.0)
        mesh = SimpleNamespace(
            coordinates={
                "x": np.arange(0.0, 21.0, 2.0),
                "y": np.array([-1.0, 1.0]),
            }
        )
        data = 0.01 * np.arange(11.0)[:, None, None] * np.ones((1, 11, 2))
        self.subslices = [
            SimpleNamespace(extent=extent, mesh=mesh, cell_centered=False, data=data)
        ]


def _corridor_route(time_s, *, hold=False):
    """D0 (0, 0) -> C0 (10, 0) -> E0 (20, 0) through the corridor slice at *time_s*."""
    from shapely.geometry import box

    from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, evaluate_route

    stages = {
        "C0": {"polygon": box(9, -1, 11, 1), "stage_type": "checkpoint"},
        "E0": {"polygon": box(19, -1, 21, 1), "stage_type": "exit"},
    }
    dists = {"D0": {"coordinates": list(box(-1, -1, 1, 1).exterior.coords)}}
    graph = StageGraph.from_scenario(
        stages, [{"from": "D0", "to": "C0"}, {"from": "C0", "to": "E0"}], dists
    )
    field = ExtinctionField(
        SliceFieldSampler(_CorridorSlice(), allow_horizon_hold=hold)
    )
    return evaluate_route(
        graph, ["D0", "C0", "E0"], time_s, 0.0, field, None, RouteCostConfig()
    )


def _foresight_warnings(caplog):
    return [r for r in caplog.records if "Route foresight" in r.getMessage()]


def test_foresight_past_the_last_frame_reads_the_last_frame(caplog):
    """Decided at 9 s, the second leg is reached at 9 + 10/1.3 = 16.7 s.

    That is past the output (last frame 10 s, interval 1 s) and raised
    ``FdsHorizonError`` without --allow-fds-horizon-hold, mid-run (#666).
    The leg now reads the last frame. The first leg starts at the decision
    time; its samples 2 m on and beyond are reached after 10.5 s and read
    the last frame too (#650).
    """
    with caplog.at_level(logging.WARNING):
        rc = _corridor_route(9.0)
    first, second = rc.segments
    assert first.arrival_time_s == 9.0
    assert first.k_avg == pytest.approx((0.09 + 5 * 0.10) / 6, rel=1e-12)
    assert first.k_max == pytest.approx(0.10, rel=1e-12)
    assert second.arrival_time_s == 10.0
    assert second.k_max == pytest.approx(0.10, rel=1e-12)
    assert len(_foresight_warnings(caplog)) == 1
    assert _horizon_warnings(caplog) == []


def test_foresight_cap_reads_what_the_hold_flag_reads():
    """With --allow-fds-horizon-hold the route is priced as before #666."""
    capped = _corridor_route(9.0)
    held = _corridor_route(9.0, hold=True)
    assert [s.k_max for s in capped.segments] == [s.k_max for s in held.segments]
    assert capped.tau_route == held.tau_route


def test_foresight_cap_logs_once_per_field(caplog):
    from pyfds_evac.core.route_graph import _cap_at_fds_end

    field = ExtinctionField(SliceFieldSampler(_CorridorSlice()))
    with caplog.at_level(logging.WARNING):
        for t in (12.0, 14.0):
            assert _cap_at_fds_end(9.0, t, field.end_time_s, field) == 10.0
    assert len(_foresight_warnings(caplog)) == 1


def test_decision_past_the_output_still_raises():
    """The cap is on foresight only; the decision-time sample keeps its check."""
    with pytest.raises(FdsHorizonError):
        _corridor_route(30.0)


class _HalfSecondSlice(_Slice):
    """Frames every 0.5 s up to 10 s over x 0..30 m; K = 0.01 x frame index."""

    def __init__(self):
        super().__init__(times=np.arange(0.0, 10.01, 0.5))
        extent = SimpleNamespace(x_start=0.0, x_end=30.0, y_start=-1.0, y_end=10.0)
        mesh = SimpleNamespace(
            coordinates={"x": np.array([0.0, 30.0]), "y": np.array([-1.0, 10.0])}
        )
        data = 0.01 * np.arange(float(len(self.times)))[:, None, None]
        self.subslices = [
            SimpleNamespace(
                extent=extent,
                mesh=mesh,
                cell_centered=False,
                data=data * np.ones((1, 2, 2)),
            )
        ]


@pytest.mark.parametrize("order", [("DA", "DB"), ("DB", "DA")])
def test_held_foresight_does_not_share_a_cache_bucket(order):
    """A held time keeps its own segment-cache bucket (QA B1, #666).

    Decided at 8 s, A reaches C0 -> E0 at 9.6 s (frame 9.5 s), B at 13 s,
    past the 10 s end. Holding B at 10 s put it in A's bucket, so the agent
    evaluated second read the other's frame. With the hold flag both read
    what they read before #666, in either order. Each sample is read when
    the agent reaches it (#650), so A's samples past 10.5 s read the last
    frame too: A k_max 0.20 (0.19 before #650), B 0.20.
    """
    from shapely.geometry import box

    from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, evaluate_route

    field = ExtinctionField(
        SliceFieldSampler(_HalfSecondSlice(), allow_horizon_hold=True)
    )
    stages = {
        "C0": {"polygon": box(9, -1, 11, 1), "stage_type": "checkpoint"},
        "E0": {"polygon": box(19, -1, 21, 1), "stage_type": "exit"},
    }
    dists = {
        "DA": {"coordinates": list(box(7.42, -0.5, 8.42, 0.5).exterior.coords)},
        "DB": {"coordinates": list(box(9.5, 6.0, 10.5, 7.0).exterior.coords)},
    }
    graph = StageGraph.from_scenario(
        stages,
        [
            {"from": "DA", "to": "C0"},
            {"from": "DB", "to": "C0"},
            {"from": "C0", "to": "E0"},
        ],
        dists,
    )

    def route(src, cache):
        return evaluate_route(
            graph,
            [src, "C0", "E0"],
            8.0,
            0.0,
            field,
            None,
            RouteCostConfig(),
            cached_segments=cache,
        )

    expected_k_max = {"DA": 0.20, "DB": 0.20}
    shared: dict = {}
    for src in order:
        cached = route(src, shared)
        fresh = route(src, {})
        assert cached.segments[1].k_max == pytest.approx(expected_k_max[src])
        assert cached.tau_route == fresh.tau_route


_T_JUNCTION_FDS = Path(
    os.environ.get(
        "T_JUNCTION_FDS",
        Path.home()
        / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
        / "fds-evac-data"
        / "t_junction"
        / "fire_2MW_PVC",
    )
)


@pytest.mark.slow
@pytest.mark.external_data
@pytest.mark.skipif(
    not (_T_JUNCTION_FDS / "t_junction.smv").is_file(),
    reason="t_junction FDS output absent",
)
def test_t_junction_runs_to_t_end_without_the_hold_flag(
    tmp_path, caplog, fds_read_only
):
    """t_junction with fire_2MW_PVC: 300 s of FDS output, a 300 s run.

    The setup check passes, yet before #666 the run stopped at about 295.6 s
    with ``FdsHorizonError``: route foresight sampled smoke at 301.5 s.
    """
    import shutil

    from pyfds_evac.core import load_scenario, run_scenario
    from pyfds_evac.core.run_config import build_run_kwargs
    from run import _build_parser

    asset = _REPO / "assets" / "t_junction"
    shutil.copy(asset / "config_full.json", tmp_path / "config.json")
    shutil.copy(asset / "geometry.wkt", tmp_path / "geometry.wkt")
    scenario = load_scenario(str(tmp_path))
    opts = _build_parser().parse_args(
        [
            "--scenario",
            str(tmp_path),
            "--fds-dir",
            str(fds_read_only(_T_JUNCTION_FDS)),
        ]
    )
    with caplog.at_level(logging.WARNING):
        result = run_scenario(scenario, **build_run_kwargs(scenario, opts))
    try:
        assert result.evacuation_time == pytest.approx(300.0, abs=0.1)
        assert len(_foresight_warnings(caplog)) == 1
        assert _horizon_warnings(caplog) == []
    finally:
        result.cleanup()
