"""FDS case for ``--heat-regime layer`` with a geometric view factor (#308).

Two levels:

- **View factor** (always runs): the closed forms of
  ``scripts/verification/heat_layer_view_factor.py`` (Howell C-11, C-14)
  against a midpoint integration of cos(t1) cos(t2) / (pi R^2) over the
  layer base, and the limit of an infinite parallel plane (phi = 1).
- **FDS case** (``external_data``, skipped without the sciebo folder): the
  CLI run per gauge position and orientation on
  ``fds-evac-data/heat_radiometer/layer_308`` (FDS 6.10.1,
  ``assets/heat_radiometer/heat_radiometer_layer_308.fds``), flux against
  FDS ``GAUGE HEAT FLUX GAS`` at t = 3, 6, 9 s.

Predeclared band: |q_model / q_FDS - 1| <= 0.30 at every point and time.
The recorded result is a miss: 54 of 63 (point, time) pairs are inside the
band, 9 are not (see ``MISSES``). The test pins that result; it does not
widen the band or change phi. The model flux equals the hand formula from
its own sampled T_g and T_L (1e-6 kW/m2); the sampled T_L stays within 2 %
of the ``T_z25`` device, and T_g within 2 % at t = 3 s (worst 0.2 %); at 6 s
it differs from the ``T_z16`` device by up to 2.9 %, at 9 s by up to 12 %,
while the head temperature rises by up to 20 K/s.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from math import pi
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "verification"
SCIEBO = next(Path.home().glob("sciebo*/fds-evac-data/heat_radiometer"), Path("absent"))
DATA = Path(os.environ.get("HEAT_RADIOMETER_DATA", SCIEBO)) / "layer_308"

# (orientation, x_m, t_s) outside the band in the recorded run.
MISSES = {
    ("up", 1.45, 9.0),
    ("up", 1.95, 9.0),
    ("up", 2.45, 9.0),
    ("px", 3.45, 3.0),
    ("px", 3.45, 6.0),
    ("px", 3.45, 9.0),
    ("mx", 0.45, 3.0),
    ("mx", 0.45, 6.0),
    ("mx", 0.45, 9.0),
}


def _load(name):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(SCRIPTS))
    return mod


vf = _load("heat_layer_view_factor")


def numeric_phi(x_m, orientation, n=1200):
    """Midpoint integration over the layer base, element normal per gauge."""
    c = vf.LAYER_BASE_M - vf.GAUGE_Z_M
    xs = (np.arange(n) + 0.5) / n * vf.ROOM_X_M - x_m
    ys = (np.arange(n) + 0.5) / n * vf.ROOM_Y_M - vf.GAUGE_Y_M
    dx, dy = np.meshgrid(xs, ys)
    r2 = dx**2 + dy**2 + c**2
    r = np.sqrt(r2)
    cos2 = c / r
    cos1 = {"up": c / r, "px": dx / r, "mx": -dx / r}[orientation]
    f = np.clip(cos1, 0.0, None) * cos2 / (pi * r2)
    return float(f.sum() * (vf.ROOM_X_M / n) * (vf.ROOM_Y_M / n))


@pytest.mark.parametrize("orientation", vf.ORIENTATIONS)
@pytest.mark.parametrize("x_m", vf.GAUGE_X_M)
def test_closed_form_matches_integration(x_m, orientation):
    assert vf.view_factor(x_m, orientation) == pytest.approx(
        numeric_phi(x_m, orientation), abs=2e-3
    )


def test_infinite_plane_limit_is_one():
    big = 1.0e5
    assert 4 * vf._c11(big, big, 0.4) == pytest.approx(1.0, abs=1e-4)


def test_perpendicular_halves_sum_to_half_of_the_parallel_plane():
    """An element normal to x sees half the plane z = c in front of it."""
    big = 1.0e5
    assert 2 * vf._c14(big, big, 0.4) == pytest.approx(0.5, abs=1e-4)


def test_gauge_must_be_below_the_layer_base(monkeypatch):
    monkeypatch.setattr(vf, "GAUGE_Z_M", 2.0)
    with pytest.raises(ValueError, match="not below the layer base"):
        vf.view_factor(2.0, "up")


@pytest.mark.external_data
@pytest.mark.skipif(not DATA.is_dir(), reason=f"FDS output not found: {DATA.name}")
def test_layer_regime_against_fds_gauges(fds_read_only, tmp_path):
    case = _load("heat_layer_308")
    results = case.run_all(fds_read_only(DATA), tmp_path)
    assert len(results) == 63

    for r in results:
        where = (r["orientation"], r["x_m"], r["t_s"])
        assert abs(r["hand_diff_kw"]) < case.HAND_TOL, where
        assert r["t_layer_model_c"] == pytest.approx(
            r["t_layer_devc_c"], rel=case.T_TOL
        ), where
        if r["t_s"] == 3.0:
            assert r["t_gas_model_c"] == pytest.approx(
                r["t_gas_devc_c"], rel=case.T_TOL
            ), where

    outside = {
        (r["orientation"], round(r["x_m"], 2), r["t_s"])
        for r in results
        if not r["within_band"]
    }
    assert outside == MISSES
