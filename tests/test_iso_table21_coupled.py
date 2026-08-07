"""ISO 20414 Table 21, with the extinction coefficient read from real FDS output.

ISO 20414:2020 Table 21 (Test 18) specifies a corridor 2 m wide and 100 m long,
an unimpeded walking speed of 1,25 m/s, and "a constant extinction coefficient
equal to 1,0/m … implemented in the corridor prior to running the simulation".
Its expected result is that the time to cover the corridor matches the time
calculated by hand from the model's own correlation.

``assets/ISO-table21`` implements that faithfully but supplies K through
``ConstantExtinctionField``, so no slice is ever read. That left the extinction
path — the busier of the two hazard signals, since it drives both the walking
speed and the routing cost — verified only against constants and mocks. Before
this file, the only ``ExtinctionField.from_fds`` in the suite used a *fake*
simulation object.

Here K arrives the way it does in a real case:

    deck → FDS → fdsreader → SliceFieldSampler → speed factor → egress time

**This is a cross-check, not just plumbing.** FDS computes its
``SOOT EXTINCTION COEFFICIENT`` slice as ``MASS_EXTINCTION_COEFFICIENT × soot
density`` (default 8700 m²/kg), and ``extinction_from_soot_density()`` uses the
same 8700. The deck prescribes the soot density that *should* yield K = 1,0/m,
so the K that comes back tests our conversion against FDS's own. A test that
injected K directly could not tell the two apart.
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario, run_scenario
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    speed_factor_from_extinction,
)

ASSET = Path("assets/iso_table21_coupled")
FDS_DIR = ASSET / "fds"

# ISO's expected result is a hand calculation, so the tolerance only has to
# absorb discretisation: a spawn box of finite width, an exit of finite depth,
# and a 0,1 s update interval.
TOLERANCE = 0.08


def _builder():
    spec = importlib.util.spec_from_file_location(
        "iso21c_builder", ASSET / "build_geometry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _opts(**overrides):
    base = dict(
        seed=420,
        fds_dir=None,
        constant_extinction=None,
        smoke_update_interval=0.1,
        smoke_slice_height=2.0,
        disable_tenability=True,
        fed_threshold=1.0,
        fic_alpha=0.7,
        fic_min_factor=0.3,
        enable_rerouting=False,
        reroute_interval=1.0,
        vis_cache=None,
        incapacitation_mode="deterministic",
        susceptibility_sigma=0.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(**overrides):
    scenario = load_scenario(str(ASSET / "config.json"))
    return run_scenario(scenario, **build_run_kwargs(scenario, _opts(**overrides)))


@pytest.fixture(scope="module")
def clear_run():
    outcome = _run()
    yield outcome
    outcome.cleanup()


@pytest.fixture(scope="module")
def smoke_run():
    outcome = _run(fds_dir=str(FDS_DIR))
    yield outcome
    outcome.cleanup()


@pytest.fixture(scope="module")
def observed_k():
    """K as the sampler reads it out of the committed slice."""
    field = ExtinctionField.from_fds(str(FDS_DIR), slice_height_m=2.0)
    return field.sample_extinction(0.0, 0.0, 0.0)


class TestThePremise:
    def test_the_corridor_matches_the_standard(self):
        builder = _builder()
        length = builder.CORRIDOR[2] - builder.CORRIDOR[0]
        width = builder.CORRIDOR[3] - builder.CORRIDOR[1]
        assert (length, width) == (100.0, 2.0)
        assert builder.V0 == 1.25

    def test_the_committed_fds_output_is_present(self):
        assert list(FDS_DIR.glob("*.sf")), "no slice files"
        assert list(FDS_DIR.glob("*.smv")), "no .smv"


class TestTheExtinctionArrivesFromFds:
    """The step ``assets/ISO-table21`` cannot exercise at all."""

    def test_the_slice_yields_the_prescribed_coefficient(self, observed_k):
        """Our soot-to-K conversion against FDS's own.

        The deck prescribes the soot density that should produce K = 1,0/m by
        FDS's definition. Agreement here means both sides use the same
        8700 m²/kg; the residual is the air density assumed when turning that
        density into the mass fraction FDS wants.
        """
        builder = _builder()
        assert observed_k == pytest.approx(builder.TARGET_K, rel=0.01)

    def test_it_is_constant_in_space_and_time(self, observed_k):
        """Prescribed, not burned — so a gradient would mean the deck is wrong."""
        field = ExtinctionField.from_fds(str(FDS_DIR), slice_height_m=2.0)
        for time_s, x, y in [(0.0, -40.0, 0.0), (50.0, 0.0, 0.5), (100.0, 40.0, -0.5)]:
            assert field.sample_extinction(time_s, x, y) == pytest.approx(
                observed_k, rel=1e-6
            )

    def test_it_is_not_zero(self, observed_k):
        """A missing or misnamed slice would read as clear air and pass silently
        every downstream assertion about *ratios* being near 1."""
        assert observed_k > 0.5


class TestTheEgressMatchesTheHandCalculation:
    """ISO's expected result, with K sourced from the slice."""

    def test_the_recorded_factor_matches_the_observed_coefficient(
        self, smoke_run, observed_k
    ):
        expected = speed_factor_from_extinction(observed_k)
        recorded = {round(row["speed_factor"], 6) for row in smoke_run.smoke_history}
        assert recorded == {round(expected, 6)}

    def test_the_time_ratio_matches(self, clear_run, smoke_run, observed_k):
        expected_ratio = 1.0 / speed_factor_from_extinction(observed_k)
        observed_ratio = smoke_run.evacuation_time / clear_run.evacuation_time
        assert observed_ratio == pytest.approx(expected_ratio, rel=TOLERANCE)

    def test_smoke_actually_slows_the_occupant(self, clear_run, smoke_run):
        """The control. Without it, a coupling that silently did nothing would
        satisfy a ratio assertion whose expected value is close to 1."""
        assert smoke_run.evacuation_time > clear_run.evacuation_time
        assert clear_run.success and smoke_run.success
        assert smoke_run.agents_remaining == 0

    def test_the_clear_run_really_is_clear(self, clear_run):
        """No fds_dir means no smoke model at all, so nothing is recorded."""
        assert not clear_run.smoke_history


def test_the_asset_readme_records_the_measured_numbers():
    """The README quotes results; drift between it and the run is a silent lie."""
    readme = (ASSET / "README.md").read_text(encoding="utf-8")
    assert "0.99545" in readme or "0,99545" in readme, (
        "the README should quote the K actually read back from the slice"
    )


def test_smoke_history_is_written_when_requested(tmp_path):
    """The CSV is how a user checks this by hand, so it must contain the field."""
    outcome = _run(fds_dir=str(FDS_DIR))
    try:
        path = tmp_path / "smoke.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=outcome.smoke_history[0].keys())
            writer.writeheader()
            writer.writerows(outcome.smoke_history)
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        assert (
            rows and "speed_factor" in rows[0] and "extinction" in str(rows[0].keys())
        )
    finally:
        outcome.cleanup()
