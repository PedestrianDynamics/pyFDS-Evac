"""The route-side FED-rate memo (#243): exact keys, horizon checks, bounds."""

import logging
import math
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core import scenario as scenario_module
from pyfds_evac.core.fds_sampling import FdsHorizonError, SliceFieldSampler
from pyfds_evac.core.scenario import _FedRateAdapter

_REPO = Path(__file__).resolve().parents[1]


class _Extent:
    def __init__(self, xs, ys):
        self.x_start, self.x_end = float(xs[0]), float(xs[-1])
        self.y_start, self.y_end = float(ys[0]), float(ys[-1])


class _SubSlice:
    def __init__(self, xs, ys, n_frames):
        self.mesh = SimpleNamespace(
            coordinates={
                "x": np.asarray(xs, dtype=float),
                "y": np.asarray(ys, dtype=float),
                "z": np.array([0.0, 1.0]),
            }
        )
        self.extent = _Extent(xs, ys)
        self.cell_centered = False
        self.data = np.zeros((n_frames, len(xs), len(ys)))


class _Slice:
    def __init__(self, interval_s, n_frames):
        xs = ys = [0.0, 5.0, 10.0]
        self.subslices = [_SubSlice(xs, ys, n_frames)]
        self.times = np.arange(n_frames) * float(interval_s)
        self.quantity = SimpleNamespace(name="VOLUME FRACTION")

    def get_nearest_timestep(self, time_s):
        return int(np.argmin(np.abs(self.times - time_s)))


class _Model:
    """A FED model whose rate is the number of reads so far, to count them."""

    def __init__(self, *samplers, fail_at=None):
        self.field = SimpleNamespace(samplers=lambda: list(samplers))
        self.reads = 0
        self.fail_at = fail_at

    def sample_rate(self, time_s, x, y):
        for sampler in self.field.samplers():
            sampler._time_index(float(time_s))
        if self.fail_at is not None and (x, y) == self.fail_at:
            raise ValueError("partly covered")
        self.reads += 1
        return None, float(self.reads)


def _sampler(interval_s=1.0, n_frames=11):
    return SliceFieldSampler(_Slice(interval_s, n_frames))


def test_same_frame_and_point_reads_once():
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model)
    first = adapter.sample_fed_rate(3.2, 1.0, 2.0)
    second = adapter.sample_fed_rate(3.2, 1.0, 2.0)
    assert (first, second, model.reads) == (1.0, 1.0, 1)
    assert (adapter.hits, adapter.misses) == (1, 1)


def test_same_frame_different_time_is_a_hit():
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(3.2, 1.0, 2.0)
    assert adapter.sample_fed_rate(3.4, 1.0, 2.0) == 1.0
    assert model.reads == 1


def test_arrival_times_across_a_frame_boundary_read_twice():
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(3.4, 1.0, 2.0)  # frame 3
    adapter.sample_fed_rate(3.6, 1.0, 2.0)  # frame 4
    assert model.reads == 2


def test_different_point_reads_again():
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(3.0, 1.0, 2.0)
    adapter.sample_fed_rate(3.0, 1.0, 2.5)
    assert model.reads == 2


def test_every_sampler_frame_is_in_the_key():
    """Slices at 1 s and 2 s: t = 2.6 and 3.4 share the 2 s frame, not the 1 s one."""
    model = _Model(_sampler(1.0, 11), _sampler(2.0, 6))
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(2.6, 1.0, 2.0)
    adapter.sample_fed_rate(3.4, 1.0, 2.0)
    assert model.reads == 2
    adapter.sample_fed_rate(2.9, 1.0, 2.0)  # frames (3, 1) again
    assert model.reads == 2


def test_past_the_horizon_raises_after_a_cached_last_frame(caplog):
    model = _Model(_sampler(1.0, 11))  # last frame at 10 s, interval 1 s
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(10.0, 1.0, 2.0)
    with pytest.raises(FdsHorizonError):
        adapter.sample_fed_rate(11.5, 1.0, 2.0)
    assert model.reads == 1
    assert adapter.misses == 1


def test_an_exception_stores_nothing():
    model = _Model(_sampler(), fail_at=(1.0, 2.0))
    adapter = _FedRateAdapter(model)
    with pytest.raises(ValueError, match="partly covered"):
        adapter.sample_fed_rate(3.0, 1.0, 2.0)
    with pytest.raises(ValueError, match="partly covered"):
        adapter.sample_fed_rate(3.0, 1.0, 2.0)
    assert (adapter.hits, adapter.misses) == (0, 2)


def test_the_cap_clears_and_the_next_read_misses(monkeypatch):
    monkeypatch.setattr(scenario_module, "_FED_RATE_MEMO_SIZE", 2)
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(3.0, 1.0, 2.0)
    adapter.sample_fed_rate(3.0, 1.0, 3.0)
    adapter.sample_fed_rate(3.0, 1.0, 4.0)  # full: cleared before storing
    assert adapter.clears == 1
    adapter.sample_fed_rate(3.0, 1.0, 2.0)  # gone, read again
    assert model.reads == 4
    assert adapter.sample_fed_rate(3.0, 1.0, 2.0) == 4.0


def test_memo_off_reads_every_time():
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model, memo=False)
    adapter.sample_fed_rate(3.0, 1.0, 2.0)
    adapter.sample_fed_rate(3.0, 1.0, 2.0)
    assert model.reads == 2
    assert (adapter.hits, adapter.misses, adapter.clears) == (0, 0, 0)


def test_a_model_without_slices_is_not_memoised():
    model = _Model()
    adapter = _FedRateAdapter(model)
    adapter.sample_fed_rate(3.0, 1.0, 2.0)
    adapter.sample_fed_rate(3.0, 1.0, 2.0)
    assert model.reads == 2
    assert adapter.memo is False


@pytest.mark.parametrize("value", [1, "true", None])
def test_the_flag_must_be_a_bool(value):
    from pyfds_evac.core.scenario import _fed_rate_memo_flag

    with pytest.raises(ValueError, match="routing.fed_rate_memo"):
        _fed_rate_memo_flag({"fed_rate_memo": value})


def test_the_flag_defaults_on():
    from pyfds_evac.core.scenario import _fed_rate_memo_flag

    assert _fed_rate_memo_flag(None) is True
    assert _fed_rate_memo_flag({}) is True
    assert _fed_rate_memo_flag({"fed_rate_memo": False}) is False


def test_a_run_without_fds_rejects_a_bad_flag(tmp_path):
    import json

    from pyfds_evac.core import load_scenario, run_scenario
    from pyfds_evac.core.run_config import build_run_kwargs
    from run import _build_parser

    asset = _REPO / "assets" / "t_junction"
    raw = json.loads((asset / "config_full.json").read_text())
    raw.setdefault("routing", {})["fed_rate_memo"] = "false"
    (tmp_path / "config.json").write_text(json.dumps(raw))
    shutil.copy(asset / "geometry.wkt", tmp_path / "geometry.wkt")
    scenario = load_scenario(str(tmp_path))
    opts = _build_parser().parse_args(["--scenario", str(tmp_path), "--seed", "1"])
    with pytest.raises(ValueError, match="routing.fed_rate_memo"):
        run_scenario(scenario, **build_run_kwargs(scenario, opts))


@pytest.mark.parametrize("axis", [0, 1])
def test_the_key_is_not_rounded(axis):
    model = _Model(_sampler())
    adapter = _FedRateAdapter(model)
    point = [1.0, 2.0]
    adapter.sample_fed_rate(3.0, *point)
    point[axis] = math.nextafter(point[axis], math.inf)
    adapter.sample_fed_rate(3.0, *point)
    assert model.reads == 2


# --- equality on an FDS-backed deck ------------------------------------------

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


def _memo_line(caplog):
    return [
        r.getMessage() for r in caplog.records if "FED-rate memo:" in r.getMessage()
    ]


def _run_t_junction(tmp_path, fds_dir, memo, caplog):
    import json

    from pyfds_evac.core import load_scenario, run_scenario
    from pyfds_evac.core.run_config import build_run_kwargs
    from run import _build_parser

    asset = _REPO / "assets" / "t_junction"
    deck = tmp_path / ("memo_on" if memo else "memo_off")
    deck.mkdir()
    raw = json.loads((asset / "config_full.json").read_text())
    raw.setdefault("routing", {})["fed_rate_memo"] = memo
    (deck / "config.json").write_text(json.dumps(raw))
    shutil.copy(asset / "geometry.wkt", deck / "geometry.wkt")
    scenario = load_scenario(str(deck))
    opts = _build_parser().parse_args(
        ["--scenario", str(deck), "--fds-dir", str(fds_dir), "--seed", "1"]
    )
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="pyfds_evac.core.scenario"):
        result = run_scenario(scenario, **build_run_kwargs(scenario, opts))
    try:
        # JuPedSim numbers agents across runs in one process; rebase the ids
        # to the first agent of each run so the histories are comparable.
        first = min(row["agent_id"] for row in result.exit_history)
        return (
            [{**r, "agent_id": r["agent_id"] - first} for r in result.route_history],
            [{**r, "agent_id": r["agent_id"] - first} for r in result.exit_history],
            result.metrics["evacuation_time"],
            _memo_line(caplog),
        )
    finally:
        result.cleanup()


@pytest.mark.slow
@pytest.mark.external_data
@pytest.mark.skipif(
    not (_T_JUNCTION_FDS / "t_junction.smv").is_file(),
    reason="t_junction FDS output absent",
)
def test_memo_on_and_off_make_the_same_decisions(tmp_path, caplog, fds_read_only):
    fds_dir = fds_read_only(_T_JUNCTION_FDS)
    on = _run_t_junction(tmp_path, fds_dir, True, caplog)
    off = _run_t_junction(tmp_path, fds_dir, False, caplog)
    assert on[:3] == off[:3]
    assert len(on[3]) == 1 and not on[3][0].startswith("FED-rate memo: 0 hits")
    assert off[3] == ["FED-rate memo: 0 hits, 0 misses, 0 clears"]
