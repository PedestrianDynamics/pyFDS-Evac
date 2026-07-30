"""Tests for the trajectory viewer's FDS smoke overlay payload.

``_smoke_payload`` samples an FDS extinction slice into a compact base64 grid
shipped to the browser. fdsreader is not required here: the tests inject a fake
``Simulation`` so the packing/geometry logic is exercised without an FDS deck.
"""

import base64

import numpy as np
import pytest

pytest.importorskip("fasthtml")

from pyfds_evac.webapp.trajviz import _smoke_payload  # noqa: E402


class _FakeExtent:
    def __init__(self, z_start, z_end):
        self.z_start = z_start
        self.z_end = z_end


class _FakeSlice:
    def __init__(self, grid, xs, ys, times, z_start=1.9, z_end=2.1):
        self._grid = np.asarray(grid, dtype=float)  # (T, X, Y)
        self._xs = np.asarray(xs, dtype=float)
        self._ys = np.asarray(ys, dtype=float)
        self.times = np.asarray(times, dtype=float)
        self.extent = _FakeExtent(z_start, z_end)

    def to_global(self, masked=True, return_coordinates=True):
        return self._grid, {"x": self._xs, "y": self._ys}


class _FakeSlices:
    def __init__(self, by_quantity):
        self._by_quantity = by_quantity

    def filter_by_quantity(self, name):
        return self._by_quantity.get(name, [])


class _FakeSim:
    def __init__(self, by_quantity):
        self.slices = _FakeSlices(by_quantity)


def _sim_with_slice(slice_obj, quantity="SOOT EXTINCTION COEFFICIENT"):
    return _FakeSim({quantity: [slice_obj]})


def test_returns_none_without_fds_dir():
    assert _smoke_payload(None, [0.0, 1.0]) is None
    assert _smoke_payload("/no/such/fds/dir", [0.0, 1.0]) is None


def test_returns_none_when_no_extinction_slice():
    sim = _FakeSim({})  # no matching quantity
    assert _smoke_payload("ignored", [0.0, 1.0], simulation=sim) is None


def test_packs_one_uint8_frame_per_render_time():
    # 4x3 grid over two FDS timesteps; three render times.
    grid = np.arange(2 * 4 * 3, dtype=float).reshape(2, 4, 3)
    sl = _FakeSlice(grid, xs=[0, 1, 2, 3], ys=[0, 1, 2], times=[0.0, 10.0])
    times = [0.0, 5.0, 10.0]

    payload = _smoke_payload("ignored", times, simulation=_sim_with_slice(sl))

    assert payload is not None
    assert (payload["W"], payload["H"]) == (4, 3)
    assert payload["ext"] == [0.0, 0.0, 3.0, 2.0]
    assert payload["kmax"] == float(grid.max())
    # Packing invariant: one W*H byte frame per render time (catches row/col
    # transposition and frame-count bugs a browser-free test would miss).
    decoded = base64.b64decode(payload["b64"])
    assert len(decoded) == payload["W"] * payload["H"] * len(times)


def test_multi_name_lookup_falls_back_to_bare_extinction():
    grid = np.ones((1, 3, 3), dtype=float)
    sl = _FakeSlice(grid, xs=[0, 1, 2], ys=[0, 1, 2], times=[0.0])
    sim = _FakeSim({"EXTINCTION": [sl]})  # only the older alias present
    payload = _smoke_payload("ignored", [0.0], simulation=sim)
    assert payload is not None
    assert (payload["W"], payload["H"]) == (3, 3)


def test_downsamples_large_grid_to_cell_cap():
    # 200 cells on the long axis must be downsampled below the cap.
    grid = np.zeros((1, 200, 10), dtype=float)
    sl = _FakeSlice(grid, xs=np.arange(200), ys=np.arange(10), times=[0.0])
    payload = _smoke_payload("ignored", [0.0], simulation=_sim_with_slice(sl))
    assert payload is not None
    assert payload["W"] <= 70


def _base_payload(**extra):
    payload = {
        "times": [0.0, 1.0],
        "samples": [[0.0, 0.0], [1.0, 1.0]],
        "colors": ["#cc785c"],
        "fed": [[0.0], [0.0]],
        "hasFed": False,
        "walk": [[0, 0], [1, 0], [1, 1]],
        "exits": [],
        "bounds": [0, 0, 1, 1],
        "smoke": None,
    }
    payload.update(extra)
    return payload


def test_component_shows_smoke_toggle_only_when_smoke_present(monkeypatch):
    from fasthtml.common import to_xml

    from pyfds_evac.webapp import trajviz

    smoke = {"W": 2, "H": 2, "ext": [0, 0, 1, 1], "kmax": 1.0, "b64": "AAAAAA=="}

    monkeypatch.setattr(trajviz, "_payload", lambda *a, **k: _base_payload(smoke=smoke))
    with_smoke = to_xml(trajviz.trajectory_component(object(), object()))
    assert 'id="traj-smoke"' in with_smoke

    monkeypatch.setattr(trajviz, "_payload", lambda *a, **k: _base_payload(smoke=None))
    without_smoke = to_xml(trajviz.trajectory_component(object(), object()))
    assert 'id="traj-smoke"' not in without_smoke
