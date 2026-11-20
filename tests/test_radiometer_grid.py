"""Radiometer device points and their regular-grid interpolation (#276).

Hand-computed expectations on a 2 x 3 grid with unequal spacings in x and y and
asymmetric values, so a swapped axis or a wrong node moves the result.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np
import pytest

from pyfds_evac.core.fds_deck import parse_fds_text
from pyfds_evac.core.fdsreader_adapter import DevicePoint, DeviceSet
from pyfds_evac.core.radiometer_grid import (
    RadiometerGrid,
    RadiometerGridError,
    device_id_of,
    radiometer_props,
    select_radiometers,
)

XS = (0.5, 1.0, 1.5)
YS = (2.0, 3.0)
TIMES = np.array([0.0, 10.0])
# Value at node (ix, iy) at t = 0; at t = 10 it is 2 * value + 1.
V0 = {
    (0, 0): 1.0,
    (1, 0): 2.0,
    (2, 0): 4.0,
    (0, 1): 3.0,
    (1, 1): 7.0,
    (2, 1): 5.0,
}


def _point(ix, iy, *, z=1.6, orientation=(0.0, 0.0, 1.0), quantity="RADIOMETER"):
    v0 = V0[(ix, iy)]
    return DevicePoint(
        id=f"RAD_r{iy}-{ix + 1}",
        quantity=quantity,
        xyz=(XS[ix], YS[iy], z),
        orientation=orientation,
        unit="kW/m2",
        data=np.array([v0, 2 * v0 + 1]),
    )


def _grid_points(**kwargs):
    return [_point(ix, iy, **kwargs) for iy in range(2) for ix in range(3)]


def _devices(points):
    return DeviceSet("case", Path("case_dir"), TIMES, tuple(points))


def _grid(points=None):
    return RadiometerGrid.from_points(points or _grid_points(), TIMES)


def test_values_at_the_nodes_are_exact_at_both_output_times():
    grid = _grid()
    for (ix, iy), v0 in V0.items():
        assert grid.sample(0.0, XS[ix], YS[iy]) == v0
        assert grid.sample(10.0, XS[ix], YS[iy]) == 2 * v0 + 1


def test_bilinear_values_match_the_hand_computation():
    grid = _grid()
    # Cell x 1.0-1.5, y 2.0-3.0: fx = fy = 0.5. Bottom (2+4)/2 = 3, top
    # (7+5)/2 = 6, so 4.5.
    assert grid.sample(0.0, 1.25, 2.5) == pytest.approx(4.5, abs=1e-12)
    # Cell x 0.5-1.0, fx = 0.2; y fraction 0.2. Bottom 1*0.8 + 2*0.2 = 1.2,
    # top 3*0.8 + 7*0.2 = 3.8, so 1.2*0.8 + 3.8*0.2 = 1.72.
    assert grid.sample(0.0, 0.6, 2.2) == pytest.approx(1.72, abs=1e-12)
    # Along y at x = 1.5 only the y fraction acts: 4 + 0.75 * (5 - 4) = 4.75.
    assert grid.sample(0.0, 1.5, 2.75) == pytest.approx(4.75, abs=1e-12)
    # Along x at y = 3.0 only the x fraction acts: 3 + 0.5 * (7 - 3) = 5.
    assert grid.sample(0.0, 0.75, 3.0) == pytest.approx(5.0, abs=1e-12)


def test_time_is_linear_between_output_times():
    grid = _grid()
    # 4.5 at t = 0 and 2 * 4.5 + 1 = 10 at t = 10; a quarter of the way 5.875.
    assert grid.sample(2.5, 1.25, 2.5) == pytest.approx(4.5 + 0.25 * 5.5, abs=1e-12)
    assert grid.sample(10.0, 1.25, 2.5) == pytest.approx(10.0, abs=1e-12)


def test_many_agents_are_sampled_in_one_call_in_the_given_order():
    grid = _grid()
    got = grid.sample(0.0, np.array([1.25, 0.6, 1.5]), np.array([2.5, 2.2, 3.0]))
    assert got == pytest.approx([4.5, 1.72, 5.0], abs=1e-12)


def test_point_order_does_not_change_the_grid():
    shuffled = _grid_points()[::-1]
    assert _grid(shuffled).sample(0.0, 0.6, 2.2) == pytest.approx(1.72, abs=1e-12)


def test_an_irregular_spacing_is_an_error():
    points = [
        DevicePoint(
            "R-1", "RADIOMETER", (0.0, 0.0, 1.6), (0, 0, 1), "kW/m2", np.zeros(2)
        ),
        DevicePoint(
            "R-2", "RADIOMETER", (1.0, 0.0, 1.6), (0, 0, 1), "kW/m2", np.zeros(2)
        ),
        DevicePoint(
            "R-3", "RADIOMETER", (2.5, 0.0, 1.6), (0, 0, 1), "kW/m2", np.zeros(2)
        ),
    ]
    with pytest.raises(RadiometerGridError, match="not uniform in x"):
        _grid(points)


def test_a_missing_node_is_listed():
    points = [p for p in _grid_points() if p.id != "RAD_r1-2"]
    with pytest.raises(RadiometerGridError, match=r"1 missing nodes.*\(1\.0, 3\.0\)"):
        _grid(points)


def test_two_points_at_one_node_are_an_error():
    points = [*_grid_points(), _point(0, 0)]
    with pytest.raises(RadiometerGridError, match="both at"):
        _grid(points)


def test_an_agent_outside_the_grid_is_an_error_not_an_extrapolation():
    grid = _grid()
    with pytest.raises(RadiometerGridError, match=r"outside the radiometer grid.*1\.6"):
        grid.sample(0.0, np.array([1.0, 1.6]), np.array([2.5, 2.5]))
    with pytest.raises(RadiometerGridError, match="outside the radiometer grid"):
        grid.sample(0.0, 1.0, 3.5)
    assert grid.contains(1.5 + 5e-7, 2.0).item()
    assert not grid.contains(1.5 + 2e-6, 2.0).item()


def test_a_time_outside_the_output_is_an_error():
    with pytest.raises(RadiometerGridError, match="outside the radiometer output"):
        _grid().sample(10.5, 1.0, 2.0)


def test_a_one_row_grid_holds_only_agents_on_the_row():
    row = [_point(ix, 0) for ix in range(3)]
    grid = _grid(row)
    # Between the nodes at 1.0 (2) and 1.5 (4): 2.5 at the quarter.
    assert grid.sample(0.0, 1.125, 2.0) == pytest.approx(2.5, abs=1e-12)
    assert grid.sample(0.0, 1.0, 2.0 + 5e-7) == 2.0
    with pytest.raises(RadiometerGridError, match="outside the radiometer grid"):
        grid.sample(0.0, 1.0, 2.1)


def test_select_by_quantity_orientation_and_z():
    other = [
        _point(0, 0, z=1.8),
        _point(1, 0, orientation=(1.0, 0.0, 0.0)),
        _point(2, 0, quantity="GAUGE HEAT FLUX"),
        _point(2, 1, quantity="TEMPERATURE"),
    ]
    devices = _devices([*_grid_points(), *other])
    chosen = select_radiometers(devices, (0, 0, 1), 1.6)
    assert [p.id for p in chosen] == [p.id for p in _grid_points()]
    # Orientation and z match to 1e-6 and a requested vector is normalised.
    near = select_radiometers(devices, (0, 0, 2.0), 1.6 + 5e-7)
    assert len(near) == 6
    assert [p.id for p in select_radiometers(devices, (1, 0, 0), 1.6)] == ["RAD_r0-2"]


def test_the_gas_spelling_of_the_quantity_is_accepted():
    points = _grid_points(quantity="RADIOMETER GAS")
    assert len(select_radiometers(_devices(points), (0, 0, 1), 1.6)) == 6


def test_the_wrong_orientation_is_an_error_that_names_what_is_there():
    devices = _devices(_grid_points())
    with pytest.raises(RadiometerGridError, match=r"orientation \(0\.0, 0\.0, -1\.0\)"):
        select_radiometers(devices, (0, 0, -1), 1.6)
    with pytest.raises(RadiometerGridError, match="non-zero 3-vector"):
        select_radiometers(devices, (0, 0, 0), 1.6)


def test_the_wrong_z_is_an_error_that_names_the_heights():
    devices = _devices(_grid_points())
    with pytest.raises(RadiometerGridError, match=r"z=1\.8 m.*heights present: 1\.6"):
        select_radiometers(devices, (0, 0, 1), 1.8)
    with pytest.raises(RadiometerGridError, match=r"z=1\.600002"):
        select_radiometers(devices, (0, 0, 1), 1.600002)


def test_a_case_without_radiometers_is_an_error():
    devices = _devices([_point(0, 0, quantity="TEMPERATURE")])
    with pytest.raises(RadiometerGridError, match="no RADIOMETER device"):
        select_radiometers(devices, (0, 0, 1), 1.6)


@pytest.mark.parametrize(
    "point_id, device_id",
    [
        ("RAD_up-3", "RAD_up"),
        ("RAD_up-03", "RAD_up"),
        ("RAD-up-12", "RAD-up"),
        ("R", "R"),
    ],
)
def test_the_devc_id_is_the_point_id_without_its_trailing_digits(point_id, device_id):
    assert device_id_of(point_id) == device_id


DECK = """
&HEAD CHID='case' /
&MISC TMPA=18. /
&PROP ID='skin', GAUGE_TEMPERATURE=35., HEAT_TRANSFER_COEFFICIENT=8. /
&PROP ID='bare' /
&PROP ID='coated', GAUGE_TEMPERATURE=40., GAUGE_EMISSIVITY=0.8 /
&DEVC ID='RAD_a', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1,
      PROP_ID='skin', XBP=0.5,1.5,2.0,2.0,1.6,1.6, POINTS=3 /
&DEVC ID='RAD_b', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1,
      PROP_ID='bare', XBP=0.5,1.5,3.0,3.0,1.6,1.6, POINTS=3 /
&DEVC ID='RAD_c', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1,
      PROP_ID='coated', XYZ=1,1,1.6 /
&DEVC ID='RAD_d', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1, XYZ=1,1,1.6 /
&DEVC ID='RAD_e', QUANTITY='RADIOMETER GAS', PROP_ID='nope', XYZ=1,1,1.6 /
"""


def _props(*ids):
    points = [_pt(i) for i in ids]
    return radiometer_props(parse_fds_text(DECK), points)


def _pt(point_id):
    return DevicePoint(
        point_id, "RADIOMETER", (0, 0, 1.6), (0, 0, 1), "kW/m2", np.zeros(1)
    )


def test_a_deck_without_tmpa_gives_a_gauge_at_20_c():
    """FDS's TMPA default (20 degC) is the gauge temperature D5 checks."""
    deck = DECK.replace("&MISC TMPA=18. /\n", "")
    got = radiometer_props(parse_fds_text(deck), [_pt("RAD_b-1"), _pt("RAD_d")])
    assert [p.gauge_temperature_c for p in got.values()] == [20.0, 20.0]


def test_prop_values_come_from_the_deck_with_fds_defaults():
    got = _props("RAD_a-1", "RAD_a-2", "RAD_b-1", "RAD_c", "RAD_d")
    assert list(got) == ["RAD_a", "RAD_b", "RAD_c", "RAD_d"]
    a, b, c, d = got.values()
    assert (a.prop_id, a.gauge_temperature_c, a.heat_transfer_coefficient) == (
        "skin",
        35.0,
        8.0,
    )
    assert a.gauge_emissivity == 1.0
    # A &PROP without GAUGE_TEMPERATURE reads as TMPA (18 here), h as 10.
    assert (b.gauge_temperature_c, b.heat_transfer_coefficient) == (18.0, 10.0)
    assert (c.gauge_temperature_c, c.gauge_emissivity) == (40.0, 0.8)
    # No PROP_ID at all: the defaults.
    assert (d.prop_id, d.gauge_temperature_c, d.gauge_emissivity) == (None, 18.0, 1.0)


def test_a_missing_devc_or_prop_is_an_error():
    with pytest.raises(RadiometerGridError, match="'RAD_x': no &DEVC with that ID"):
        _props("RAD_x-1")
    with pytest.raises(RadiometerGridError, match="PROP_ID 'nope'"):
        _props("RAD_e")


# --- the real #224 devices ---------------------------------------------------------

SCIEBO = Path.home() / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
HEAT_DATA = Path(
    os.environ.get("HEAT_RADIOMETER_DATA", SCIEBO / "fds-evac-data" / "heat_radiometer")
)
LAYER = HEAT_DATA / "layer"


@pytest.mark.external_data
@pytest.mark.skipif(
    not (LAYER / "heat_radiometer_layer.smv").is_file(),
    reason="heat_radiometer/layer FDS output absent; set HEAT_RADIOMETER_DATA",
)
def test_the_224_radiometers_are_read_unchanged(fds_read_only):
    from pyfds_evac.core.fds_deck import parse_fds_deck
    from pyfds_evac.core.fdsreader_adapter import read_fds_devices

    case = fds_read_only(LAYER)
    devices = read_fds_devices(case)
    with (case / "heat_radiometer_layer_devc.csv").open(newline="") as handle:
        rows = list(csv.reader(handle))
    header = [name.strip().strip('"') for name in rows[1]]
    table = np.array([[float(v) for v in row] for row in rows[2:]])
    column = {name: table[:, i] for i, name in enumerate(header)}

    assert devices.times == pytest.approx(column["Time"], rel=1e-6)
    point = next(p for p in devices.points if p.id == "RAD_z16_up-3")
    assert point.quantity == "RADIOMETER"
    assert point.xyz == pytest.approx((1.45, 2.05, 1.6))
    assert point.orientation == (0.0, 0.0, 1.0)
    assert point.unit == "kW/m2"
    assert point.data == pytest.approx(column["RAD_z16_up-3"], rel=1e-6, abs=1e-7)
    assert point.data[5] == pytest.approx(4.7194996, rel=1e-6)

    selected = select_radiometers(devices, (0, 0, 1), 1.6)
    assert [p.id for p in selected] == [f"RAD_z16_up-{k}" for k in range(1, 8)]
    props = radiometer_props(parse_fds_deck(case / f"{devices.chid}.fds"), selected)
    assert props["RAD_z16_up"].gauge_temperature_c == 35.0
    assert props["RAD_z16_up"].heat_transfer_coefficient == 8.0

    grid = RadiometerGrid.from_points(selected, devices.times)
    t = float(devices.times[60])
    assert grid.sample(t, 1.45, 2.05) == pytest.approx(
        column["RAD_z16_up-3"][60], rel=1e-6, abs=1e-7
    )
    mid = grid.sample(t, 1.70, 2.05)
    assert mid == pytest.approx(
        0.5 * (column["RAD_z16_up-3"][60] + column["RAD_z16_up-4"][60]), rel=1e-6
    )
