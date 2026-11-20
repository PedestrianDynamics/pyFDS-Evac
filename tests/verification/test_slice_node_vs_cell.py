"""Node-centred against cell-centred slice readings (#231).

Two levels:

- **Synthetic** (always runs): a two-cell field whose node slice holds the
  averaged values of the cell slice, read through pyFDS-Evac's own samplers,
  with a hand-computed expectation for K, the speed factor, the gas FED rate
  and the zone detection.
- **FDS case** (``external_data``, skipped without the sciebo folder): the
  headline numbers of ``docs/testing-slice-node-vs-cell.md`` from
  ``fds-evac-data/slice_node_vs_cell`` (FDS 6.10.1,
  ``assets/slice_node_vs_cell/slice_node_vs_cell.fds``).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds_evac.core.fds_sampling import SliceFieldSampler
from pyfds_evac.core.fed import (
    DefaultFedInputs,
    FdsFedField,
    FdsHeatField,
    default_fed_rate_per_minute,
)
from pyfds_evac.core.smoke_speed import (
    LUND_ALPHA,
    LUND_BETA,
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "verification"
SCIEBO = next(
    Path.home().glob("sciebo*/fds-evac-data/slice_node_vs_cell"), Path("absent")
)
DATA = Path(os.environ.get("SLICE_NODE_VS_CELL_DATA", SCIEBO))


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


nvc = _load("slice_node_vs_cell")

# Two cells in x (1 m wide), one in y: nodes x = 0, 1, 2 and y = 0, 1.
X_NODES, Y_NODES = [0.0, 1.0, 2.0], [0.0, 1.0]
CO2_FRACTION, O2_FRACTION = 0.0004, 0.209


def _slice(quantity, cell_centred, values):
    """A one-frame fdsreader-like slice; *values* is (nx, ny) of its positions."""
    extent = SimpleNamespace(
        x_start=0.0, x_end=2.0, y_start=0.0, y_end=1.0, z_start=1.6, z_end=1.6
    )
    sub = SimpleNamespace(
        extent=extent,
        mesh=SimpleNamespace(coordinates={"x": X_NODES, "y": Y_NODES, "z": [1.5, 1.7]}),
        cell_centered=cell_centred,
        data=np.asarray(values, dtype=float)[None],
    )
    return SimpleNamespace(
        quantity=SimpleNamespace(name=quantity),
        times=np.array([0.0]),
        get_nearest_timestep=lambda t: 0,
        cell_centered=cell_centred,
        orientation=3,
        extent=extent,
        subslices=[sub],
    )


def _fields(k, co, temperature, cell_centred):
    """Fields of one family; the slices hold *k*, *co* and *temperature*."""

    def make(quantity, values):
        return SliceFieldSampler(_slice(quantity, cell_centred, values))

    def const(value):
        return np.full(np.shape(k), value)

    gas = FdsFedField(
        make("CARBON MONOXIDE VOLUME FRACTION", co),
        make("CARBON DIOXIDE VOLUME FRACTION", const(CO2_FRACTION)),
        make("OXYGEN VOLUME FRACTION", const(O2_FRACTION)),
    )
    ext = ExtinctionField(make("SOOT EXTINCTION COEFFICIENT", k))
    plane = _slice("TEMPERATURE", cell_centred, temperature)
    return nvc.Fields(
        SmokeSpeedModel(ext, SmokeSpeedConfig()),
        gas,
        FdsHeatField(SliceFieldSampler(plane)),
        plane,
    )


@pytest.fixture
def two_cell_readings():
    """Cell values step 0 -> 1 1/m, 0 -> 0.1 % CO; nodes hold their averages."""
    cell_k, cell_co = [[0.0], [1.0]], [[0.0], [1e-3]]
    cell_t = [[20.0], [220.0]]
    node_k = [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]]
    node_co = [[0.0, 0.0], [5e-4, 5e-4], [1e-3, 1e-3]]
    node_t = [[20.0, 20.0], [120.0, 120.0], [220.0, 220.0]]
    node = _fields(node_k, node_co, node_t, cell_centred=False)
    cell = _fields(cell_k, cell_co, cell_t, cell_centred=True)
    times = np.array([0.0])
    xs, ys = nvc.point_grid(*nvc.cell_nodes(node.plane.subslices[0]))
    return (
        nvc.read_fields(node, times, xs, ys),
        nvc.read_fields(cell, times, xs[..., 0], ys[..., 0]),
    )


def test_cell_nodes_and_points():
    sub = _slice("TEMPERATURE", False, [[0, 0]] * 3).subslices[0]
    x_nodes, y_nodes = nvc.cell_nodes(sub)
    assert x_nodes.tolist() == X_NODES and y_nodes.tolist() == Y_NODES
    xs, ys = nvc.point_grid(x_nodes, y_nodes)
    assert xs.shape == (1, 2, 5)
    assert xs[0, 0].tolist() == [0.5, 0.25, 0.75, 0.25, 0.75]
    assert ys[0, 1].tolist() == [0.5, 0.25, 0.25, 0.75, 0.75]


def test_node_reading_of_the_two_cells(two_cell_readings):
    node, cell = two_cell_readings
    # Cell centres sit halfway between nodes, a tie the sampler gives to the
    # lower node: cell 0 reads node 0 (K 0), cell 1 reads node 1 (K 0.5).
    assert node["K"][0, 0, :, 0].tolist() == [0.0, 0.5]
    assert cell["K"][0, 0].tolist() == [0.0, 1.0]
    # The quadrant points of cell 1 read nodes 1 (K 0.5) and 2 (K 1.0).
    assert node["K"][0, 0, 1, 1:].tolist() == [0.5, 1.0, 0.5, 1.0]


def test_speed_factor_follows_the_lund_law(two_cell_readings):
    node, cell = two_cell_readings
    assert node["speed_factor"][0, 0, 1, 0] == pytest.approx(
        1 + LUND_BETA * 0.5 / LUND_ALPHA
    )
    assert cell["speed_factor"][0, 0, 1] == pytest.approx(1 + LUND_BETA / LUND_ALPHA)


def test_fed_rate_is_the_default_rate_of_the_sampled_gas(two_cell_readings):
    node, cell = two_cell_readings
    expected = default_fed_rate_per_minute(
        DefaultFedInputs(
            co_volume_fraction_percent=0.05,
            co2_volume_fraction_percent=100 * CO2_FRACTION,
            o2_volume_fraction_percent=100 * O2_FRACTION,
        )
    )
    assert node["fed_rate"][0, 0, 1, 0] == pytest.approx(expected)
    assert cell["fed_rate"][0, 0, 1] > node["fed_rate"][0, 0, 1, 0]


def test_difference_stats_of_the_two_cells(two_cell_readings):
    node, cell = two_cell_readings
    stats = nvc.difference_stats(node["K"][..., 0], cell["K"], nvc.FLOORS["K"])
    # One cell agrees (0 against 0), one differs by 0.5 against 1.0.
    assert stats["n"] == 2 and stats["n_active"] == 1
    assert stats["abs_max"] == pytest.approx(0.5)
    assert stats["rel_max"] == pytest.approx(0.5)
    assert stats["abs_median"] == pytest.approx(0.25)


def test_difference_stats_respects_the_mask():
    node, cell = np.array([0.0, 2.0, 5.0]), np.array([0.0, 1.0, 1.0])
    mask = np.array([True, True, False])
    stats = nvc.difference_stats(node, cell, 1e-3, mask)
    assert stats["n"] == 2 and stats["abs_max"] == pytest.approx(1.0)


def test_interface_zone_marks_a_step_and_its_neighbours():
    t = np.full((1, 1, 6), 20.0)
    t[0, 0, 3:] = 220.0  # step between cells 2 and 3
    zone = nvc.interface_zone(t, t)[0, 0]
    assert zone.tolist() == [False, True, True, True, True, False]


def test_interface_zone_needs_a_temperature_range():
    t = np.full((1, 4, 4), 20.0)
    t[0, 0, 0] = 22.0  # 2 K, below the minimum range
    assert not nvc.interface_zone(t, t).any()


def test_interface_zone_sees_the_layer_between_the_two_planes():
    low, high = np.full((1, 3, 3), 20.0), np.full((1, 3, 3), 20.0)
    high[0, 1, 1] = 220.0  # hot above the plane, cool below it
    assert nvc.interface_zone(low, high)[0, 1, 1]


def test_accumulated_dose_holds_each_frame_to_the_next():
    rate = np.array([[0.6], [1.2], [1.2]])  # 1/min
    dose = nvc.accumulated(rate, np.array([0.0, 30.0, 60.0]))
    assert dose[0] == pytest.approx(0.6 * 0.5 + 1.2 * 0.5 + 1.2 * 0.5)


@pytest.mark.external_data
@pytest.mark.skipif(not DATA.is_dir(), reason=f"FDS output not found: {DATA.name}")
def test_fds_case_reads_both_slice_families():
    result = nvc.analyse(nvc.open_fds_case(DATA))
    zone = nvc.interface_zone(result["lower"]["T_c"], result["upper"]["T_c"])
    assert result["node"]["K"].shape[1:] == (30, 30, 5)
    assert zone.any()
    # The slices describe one fire: node and cell readings are the same
    # order of magnitude where there is smoke.
    k_node = result["node"]["K"][..., 0]
    k_cell = result["upper"]["K"]
    assert k_node.max() == pytest.approx(k_cell.max(), rel=0.5)


@pytest.mark.external_data
@pytest.mark.skipif(not DATA.is_dir(), reason=f"FDS output not found: {DATA.name}")
def test_fds_case_reproduces_the_page_numbers():
    """The medians of K and the speed factor in docs/testing-slice-node-vs-cell.md."""
    result = nvc.analyse(nvc.open_fds_case(DATA))
    zone = nvc.interface_zone(result["lower"]["T_c"], result["upper"]["T_c"])
    shape = result["node"]["K"].shape
    in_zone = np.broadcast_to(zone[..., None], shape).copy()
    in_zone[..., 0] = False  # the quadrant points, as on the page
    everywhere = np.ones(shape, dtype=bool)
    everywhere[..., 0] = False
    expected = {  # quantity: (median over all, median in the zone)
        "K": (0.020, 0.051),
        "speed_factor": (0.0016, 0.0041),
    }
    for name, (all_median, zone_median) in expected.items():
        ref = np.broadcast_to(result["upper"][name][..., None], shape)
        node, floor = result["node"][name], nvc.FLOORS[name]
        got_all = nvc.difference_stats(node, ref, floor, everywhere)["abs_median"]
        got_zone = nvc.difference_stats(node, ref, floor, in_zone)["abs_median"]
        assert got_all == pytest.approx(all_median, rel=0.05)
        assert got_zone == pytest.approx(zone_median, rel=0.05)
    assert zone.mean() == pytest.approx(0.055, abs=0.002)
