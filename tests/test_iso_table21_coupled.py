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
from pyfds_evac.core.smoke_speed import ExtinctionField

pytestmark = [pytest.mark.iso20414, pytest.mark.nist_tn1822]

ASSET = Path("assets/iso_table21_coupled")
FDS_DIR = ASSET / "fds"

# The sampling height of ``run.py`` (#164). FDS snaps PBZ=1.6 to the cell face
# at 1.5 m, so this reads the 1.5 m slice, not the 2.0 m one also committed.
SLICE_HEIGHT = 1.6

# K read from the committed slices. They differ by ~6e-5 /m (hydrostatic
# density), so the value tells which slice was read:
#   1.5 m slice  0.9955004 .. 0.9955090
#   2.0 m slice  0.9954433 .. 0.9954541
K_AT_1_5_M = 0.995505
K_SLICE_TOLERANCE = 1e-5

# The simulation time step; ``run_scenario`` fixes it at 0.01 s.
DT = 0.01


def _lund_factor(k: float) -> float:
    """f(K) = 1 + (beta/alpha) K with beta = -0.057, alpha = 0.706, as literals.

    Written out here so the expectation does not come from the function under
    test: a wrong alpha or beta would otherwise move both sides together.
    """
    return 1.0 - (0.057 / 0.706) * k


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
        smoke_slice_height=SLICE_HEIGHT,
        disable_tenability=True,
        fed_threshold=1.0,
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
    field = ExtinctionField.from_fds(str(FDS_DIR), slice_height_m=SLICE_HEIGHT)
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
        """Prescribed, not burned — so a gradient would mean the deck is wrong.

        Not bit-identical, though. FDS still solves the flow, so density varies
        by a few parts per million across the mesh and K varies with it; the
        committed 1.5 m slice spans 0.9955004..0.9955090. The tolerance is 1e-4
        — about twelve times that spread, and two decades below the 1 % the
        cross-check asserts, so it still fails on any real gradient.
        """
        field = ExtinctionField.from_fds(str(FDS_DIR), slice_height_m=SLICE_HEIGHT)
        samples = [
            field.sample_extinction(time_s, x, y)
            for time_s in (0.0, 50.0, 100.0)
            for x in (-49.0, -25.0, 0.0, 25.0, 49.0)
            for y in (-0.9, 0.0, 0.9)
        ]
        assert min(samples) == pytest.approx(max(samples), rel=1e-4)
        assert min(samples) == pytest.approx(observed_k, rel=1e-4)

    def test_the_default_height_reads_the_1_5_m_slice(self, observed_k):
        """Tells the 1.5 m slice from the 2.0 m one, which lies 5.6e-5 /m below.

        PBZ=1.6 is written at 1.5 m; a sampler that read the 2.0 m slice, or a
        height option that no longer reaches it, would land outside this band.
        """
        assert abs(observed_k - K_AT_1_5_M) < K_SLICE_TOLERANCE

    def test_the_run_samples_the_same_slice(self, smoke_run):
        recorded = [row["extinction_per_m"] for row in smoke_run.smoke_history]
        assert all(abs(k - K_AT_1_5_M) < K_SLICE_TOLERANCE for k in recorded)

    def test_it_is_not_zero(self, observed_k):
        """A missing or misnamed slice would read as clear air and pass silently
        every downstream assertion about *ratios* being near 1."""
        assert observed_k > 0.5


class TestTheEgressMatchesTheHandCalculation:
    """ISO's expected result, with K sourced from the slice."""

    def test_the_recorded_factor_matches_the_sampled_coefficient(self, smoke_run):
        """Row by row: K varies by ~1e-5 /m along the corridor, f by ~1e-6."""
        history = smoke_run.smoke_history
        for row in history:
            expected = _lund_factor(row["extinction_per_m"])
            assert row["speed_factor"] == pytest.approx(expected, abs=1e-9)
        # f(0.99550) by hand, to six places.
        factors = [row["speed_factor"] for row in history]
        assert min(factors) == pytest.approx(0.919626, abs=2e-6)
        assert max(factors) == pytest.approx(0.919626, abs=2e-6)

    def test_the_egress_time_is_the_clear_time_over_the_factor(
        self, clear_run, smoke_run, observed_k
    ):
        """The collision-free model has no inertia, so t_smoke = t_clear / f.

        The two times are each located to one time step, hence (1 + 1/f) dt:
        dt on the clear run and dt / f on the slowed one.
        """
        factor = _lund_factor(observed_k)
        assert smoke_run.dt == DT
        expected = clear_run.evacuation_time / factor
        tolerance = (1.0 + 1.0 / factor) * DT
        assert abs(smoke_run.evacuation_time - expected) <= tolerance

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
    """The CSV is how a user checks this by hand, so it must carry both fields.

    Named exactly: a substring test for "extinction" would pass on any column
    whose name merely contains it, which is no check at all.
    """
    outcome = _run(fds_dir=str(FDS_DIR))
    try:
        history = outcome.smoke_history
        assert history, "no smoke history was recorded"

        path = tmp_path / "smoke.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(history[0]))
            writer.writeheader()
            writer.writerows(history)

        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        assert rows
        assert "speed_factor" in rows[0]
        assert "extinction_per_m" in rows[0]
        assert float(rows[0]["extinction_per_m"]) > 0.5
    finally:
        outcome.cleanup()
