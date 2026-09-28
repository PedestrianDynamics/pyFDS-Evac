"""The gas FED reads the slice nearest the sampling height (#238).

``assets/fed_slice_height`` is a sealed room with CO in three layers at t = 0:
8000 ppm below 1 m, 2000 ppm from 1 to 2 m and 500 ppm above 2 m, with CO2
500 ppm and O2 20.9 % everywhere. Its slices are declared in an adversarial
order: a vertical CO slice first (mid-height 1.5 m), then 0.5 m, then 2.5 m,
and the breathing-height slice (PBZ=1.6, placed by FDS at 1.5 m) last. The
FDS output is committed (about 100 kB) so this runs in CI.

Expected values come from the deck, not from pyFDS-Evac: each slice must read
its layer's concentration. A uniform room cannot show this; the CO dose test
passed while the FED read CO at 0.5 m and CO2/O2 at 2.0 m.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fed import FdsFedField
from pyfds_evac.core.run_config import _build_fed_model

pytest.importorskip("fdsreader")

FDS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fed_slice_height" / "fds"
LAYERS_PPM = {0.5: 8000.0, 1.6: 2000.0, 2.6: 500.0}
# The layers mix slightly at the slice planes in the 2 s run (up to 3.4 % at
# 1.5 m, measured); 5 % separates the layers, which differ by a factor of 4.
REL = 0.05


def _co_ppm(field, t=1.0, x=5.0, y=5.0):
    return field.sample_inputs(t, x, y).co_volume_fraction_percent * 1e4


@pytest.mark.parametrize("height, expected_ppm", sorted(LAYERS_PPM.items()))
def test_each_height_reads_its_layer(height, expected_ppm):
    field = FdsFedField.from_fds(str(FDS_DIR), slice_height_m=height)
    assert _co_ppm(field) == pytest.approx(expected_ppm, rel=REL)


def test_the_run_reads_the_breathing_height_by_default():
    """The path a run takes: --smoke-slice-height (1.6 m) into the FED model."""
    opts = SimpleNamespace(
        fds_dir=str(FDS_DIR),
        smoke_update_interval=1.0,
        smoke_slice_height=1.6,
        o2_threshold_percent=20.0,
    )
    model = _build_fed_model(opts, log=lambda *a, **k: None)
    inputs = model.sample_inputs(1.0, 5.0, 5.0)
    assert inputs.co_volume_fraction_percent * 1e4 == pytest.approx(2000.0, rel=REL)
    assert inputs.co2_volume_fraction_percent == pytest.approx(0.05, rel=1e-3)
    assert inputs.o2_volume_fraction_percent == pytest.approx(20.9, rel=1e-3)


def test_the_deck_puts_a_vertical_slice_first():
    """Guard the adversarial order the tests above rely on."""
    fdsreader = pytest.importorskip("fdsreader")
    sim = fdsreader.Simulation(str(FDS_DIR))
    first = sim.slices.filter_by_quantity("CARBON MONOXIDE VOLUME FRACTION")[0]
    assert first.extent.z_start == 0.0 and first.extent.z_end == 3.0
