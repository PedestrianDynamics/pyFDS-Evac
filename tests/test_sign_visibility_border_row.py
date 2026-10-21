"""Sign visibility on the upper border row of the t_junction extinction slice.

fdsreader <=1.12 built ``Slice.to_global()`` without the outermost node row
and column of the domain: the row at y = 13 m repeated the row at 12.75 m,
and the column at x = 30 m repeated the column at 29.75 m (fdsreader#124,
#130). From 1.13 on the global array holds the FDS node values. The sign
visibility on those cells follows the extinction, so it changed with it.

The expected metres below were recorded with fdsreader 1.14.0 from the
tracked ``fire_2MW_PVC`` extinction slices (z = 2 m), sign ``alpha=90`` at
(0.5, 11.5) as in ``assets/t_junction/config_full.json``. Under 1.11.7 the
same cells read 0.2607 m and 0.3679 m. They are regression values, not a
reference outside the code; the array check against the per-mesh data is
what shows that the new values are the right ones.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyfds_evac.core.fdsreader_adapter import open_fds_simulation
from pyfds_evac.core.visibility import VisibilityModel

FDS_DIR = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "figures"
    / "data"
    / "t_junction_fire_2MW_PVC_extinction"
)
SIGN_A = {"x": 0.5, "y": 11.5, "alpha": 90, "c": 3}
TOP_ROW_Y_M = 13.0


@pytest.fixture(scope="module")
def sign_a_model():
    return VisibilityModel(
        str(FDS_DIR),
        {"exit_A_left": SIGN_A},
        time_step_s=10.0,
        slice_height_m=2.0,
    )


@pytest.mark.parametrize(
    ("time_s", "x_m", "expected_m"),
    [(100.0, 10.0, 0.3645), (200.0, 25.0, 0.2532)],
)
def test_upper_border_row_sight_distance(sign_a_model, time_s, x_m, expected_m):
    metres = sign_a_model.visibility_to_node(time_s, x_m, TOP_ROW_Y_M, "exit_A_left")
    assert metres == pytest.approx(expected_m, abs=1e-3)


def test_global_slice_keeps_the_outermost_node_row_and_column():
    slc = next(iter(open_fds_simulation(str(FDS_DIR)).slices))
    glob = slc.to_global()
    subslices = list(slc.subslices)
    first, last = np.asarray(subslices[0].data), np.asarray(subslices[-1].data)
    nx_mesh = first.shape[1]
    assert np.array_equal(glob[:, :nx_mesh, -1], first[:, :, -1])
    assert np.array_equal(glob[:, -1, :], last[:, -1, :])
