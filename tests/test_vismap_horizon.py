"""Sign visibility ends where the FDS output ends (#510).

The vismap time grid used to run to the first step at or after T_END, so a
step that does not divide T_END added a point past the last FDS frame:
fdsvismap 0.3.2 answers it with the last frame, fdsvismap#86 rejects it. And
the model raised past its last time point, while the preflight and the slice
samplers accept one FDS output interval more, so a run the preflight allowed
could fail mid-run in sign visibility.

``assets/vis_slice_height/fds`` ends at T_END = 2 s with extinction frames at
0, 1.463 and 2 s, so its output interval is 1.463 s.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import FdsHorizonError, fds_output_horizon
from pyfds_evac.core.visibility import (
    VisibilityModel,
    _build_vismap,
    _load_vismap_cache,
    _make_meta,
)

pytest.importorskip("fdsreader")
pytest.importorskip("fdsvismap")

FDS_DIR = str(
    Path(__file__).resolve().parents[1] / "assets" / "vis_slice_height" / "fds"
)
SIGN = {"s0": {"x": 0.0, "y": 0.0, "c": 3}}


@pytest.mark.parametrize("step", [0.3, 1.0, 1.5, 3.0])
def test_no_vismap_point_past_the_last_fds_frame(step):
    vis = _build_vismap(FDS_DIR, SIGN, time_step_s=step, slice_height_m=1.6)
    t_end = vis.fds_time_points[-1]
    assert vis.vismap_time_points.max() <= t_end
    assert vis.vismap_time_points[-1] == t_end


@pytest.mark.parametrize(
    ("t_end", "step"),
    [(500.0, 30.0), (500.0, 3.0), (500.0, 0.1), (500.0, 1.0), (500.0, 10.0)],
)
def test_time_grid_ends_at_t_end(t_end, step):
    fake = MagicMock()
    fake.fds_time_points = np.array([0.0, t_end / 2, t_end])
    with (
        patch("fdsvismap.VisMap", return_value=fake),
        patch("pyfds_evac.core.visibility._extinction_slice_index", return_value=0),
    ):
        _build_vismap("unused", {}, time_step_s=step, slice_height_m=1.6)
    points = np.asarray(fake.set_time_points.call_args.args[0])
    assert points.max() == t_end
    assert np.all(np.diff(points) > 0)
    assert np.diff(points).max() == pytest.approx(step)


def test_point_within_rounding_of_t_end_is_merged_into_it():
    """A grid point 1e-9 x T_END or closer to T_END is T_END itself.

    It reads the same last frame, so keeping both would only store the map
    twice; ``arange`` rounding lands points there too.
    """
    fake = MagicMock()
    fake.fds_time_points = np.array([0.0, 300.0000001])
    with (
        patch("fdsvismap.VisMap", return_value=fake),
        patch("pyfds_evac.core.visibility._extinction_slice_index", return_value=0),
    ):
        _build_vismap("unused", {}, time_step_s=1.0, slice_height_m=1.6)
    points = fake.set_time_points.call_args.args[0]
    assert points[-2:] == [299.0, 300.0000001]


def test_sign_visibility_follows_the_run_wide_window():
    """Answered up to the preflight's last frame + interval, raises past it."""
    last, interval = fds_output_horizon(FDS_DIR)
    model = VisibilityModel(FDS_DIR, SIGN, time_step_s=1.0, slice_height_m=1.6)
    at_end = model.visibility_to_node(last, 2.0, 0.0, "s0")
    assert model.visibility_to_node(last + interval / 2, 2.0, 0.0, "s0") == at_end
    assert model.visibility_to_node(last + interval, 2.0, 0.0, "s0") == at_end
    with pytest.raises(FdsHorizonError) as excinfo:
        model.node_is_visible(last + 1.01 * interval, 2.0, 0.0, "s0")
    assert f"output interval {interval:.1f} s" in str(excinfo.value)


def test_hold_flag_warns_once_past_the_window(caplog):
    last, interval = fds_output_horizon(FDS_DIR)
    model = VisibilityModel(
        FDS_DIR, SIGN, time_step_s=1.0, slice_height_m=1.6, allow_horizon_hold=True
    )
    with caplog.at_level(logging.WARNING):
        model.node_is_visible(last + 2 * interval, 2.0, 0.0, "s0")
        model.visibility_to_node(last + 3 * interval, 2.0, 0.0, "s0")
    held = [r for r in caplog.records if "past the FDS output" in r.getMessage()]
    assert len(held) == 1


def test_cache_without_output_interval_is_rebuilt(tmp_path):
    meta = _make_meta(FDS_DIR, SIGN, 1.0, 1.6)
    path = tmp_path / "vis.npz"
    np.savez_compressed(
        path,
        time_points=np.array([0.0, 1.0, 2.0]),
        x_coords=np.array([0.0]),
        y_coords=np.array([0.0]),
        vis=np.ones((3, 1, 1, 1), dtype=bool),
        meta=np.array(json.dumps(meta)),
    )
    assert _load_vismap_cache(path, meta) is None


def test_format_5_cache_is_rebuilt_once_then_reused(tmp_path):
    """A cache from before #510 (point past T_END, no interval) is rebuilt."""
    path = tmp_path / "vis.npz"
    old_meta = {**_make_meta(FDS_DIR, SIGN, 1.5, 1.6), "format": 5}
    np.savez_compressed(
        path,
        time_points=np.array([0.0, 1.5, 3.0]),
        x_coords=np.array([0.0]),
        y_coords=np.array([0.0]),
        vis=np.ones((3, 1, 1, 1), dtype=bool),
        metres=np.full((3, 1, 1, 1), 99.0, dtype=np.float16),
        meta=np.array(json.dumps(old_meta)),
    )
    kwargs = {"cache_path": path, "time_step_s": 1.5, "slice_height_m": 1.6}
    rebuilt = VisibilityModel(FDS_DIR, SIGN, **kwargs)
    with np.load(path, allow_pickle=False) as data:
        assert json.loads(str(data["meta"]))["format"] == 6
        assert data["time_points"].tolist() == [0.0, 1.5, 2.0]
        assert float(data["output_interval_s"]) == pytest.approx(1.4633, abs=1e-4)
    with patch("pyfds_evac.core.visibility._build_vismap") as build:
        reused = VisibilityModel(FDS_DIR, SIGN, **kwargs)
    build.assert_not_called()
    assert reused._horizon == rebuilt._horizon
    for t in (0.0, 1.8, 2.5):
        assert reused.visibility_to_node(t, 2.0, 0.0, "s0") == (
            rebuilt.visibility_to_node(t, 2.0, 0.0, "s0")
        )
