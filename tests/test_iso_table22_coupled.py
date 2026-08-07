"""Stationary FED, read from real FDS output rather than from hardcoded numbers.

``test_fed.py::test_iso_table22_stationary_runtime_matches_analytic_threshold_time``
verifies that the runtime *accumulator* integrates a dose correctly, but it
injects ``_ConstantInputsFedModel``, whose ``advance()`` ignores ``time_s``,
``x`` and ``y`` and returns three hardcoded numbers.  No slice is read, no unit
is converted, no position is sampled.  It checks our arithmetic against our
arithmetic.

This drives the same occupant through the real chain:

    deck -> FDS -> fdsreader -> slice selection -> unit conversion
         -> DefaultFedInputs -> accumulator -> fed_history

The analytic answer still exists because the gas is *prescribed* by a single
``&INIT`` rather than burned, so it is uniform in space and constant in time.

The FDS output is committed under ``assets/iso_table22_coupled/fds`` (136 kB,
four slices on a 8x8x6 mesh) precisely so this runs in CI.  A test that skips
when FDS output is missing would leave this path as untested as it was before:
no test in the repository read a real slice into the model until this one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from types import SimpleNamespace

from pyfds_evac.core.fed import default_fed_rate_per_minute
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario, run_scenario

ASSET = Path("assets/iso_table22_coupled")
FDS_DIR = ASSET / "fds"


def _builder():
    spec = importlib.util.spec_from_file_location(
        "iso22c_builder", ASSET / "build_geometry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def result():
    """Run through the same option builder the CLI uses.

    Constructing the FED model by hand would skip ``_build_fed_model`` and the
    slice-height plumbing, which are part of what this test exists to cover.
    """
    scenario = load_scenario(str(ASSET / "config.json"))
    opts = SimpleNamespace(
        seed=420,
        fds_dir=str(FDS_DIR),
        constant_extinction=None,
        smoke_update_interval=1.0,
        smoke_slice_height=2.0,
        disable_tenability=False,
        fed_threshold=1.0,
        fic_alpha=0.7,
        fic_min_factor=0.3,
        enable_rerouting=False,
        reroute_interval=1.0,
        vis_cache=None,
        incapacitation_mode="deterministic",
        susceptibility_sigma=0.0,
    )
    outcome = run_scenario(scenario, **build_run_kwargs(scenario, opts))
    yield outcome
    outcome.cleanup()


class TestThePremise:
    def test_the_committed_fds_output_is_present(self):
        """Without it this test would silently become a no-op."""
        assert (FDS_DIR / "iso_table22_coupled.smv").exists()
        assert list(FDS_DIR.glob("*.sf")), "no slice files"

    def test_the_crossing_happens_before_the_deck_ends(self):
        builder = _builder()
        assert builder.expected_threshold_time_s() < builder.T_END


class TestTheGasReachesTheModelUnaltered:
    """The step the stubbed test cannot exercise at all.

    A ppm/vol-% confusion, a mass-fraction/volume-fraction mix-up, or a slice
    read at the wrong height all show up here as a concentration that differs
    from the one the deck prescribes.
    """

    def test_every_species_arrives_at_its_prescribed_concentration(self, result):
        builder = _builder()
        row = result.fed_history[0]
        assert float(row["co_percent"]) == pytest.approx(builder.CO_PERCENT, rel=1e-3)
        assert float(row["co2_percent"]) == pytest.approx(builder.CO2_PERCENT, rel=1e-3)
        assert float(row["o2_percent"]) == pytest.approx(builder.O2_PERCENT, rel=1e-3)

    def test_the_concentration_is_constant_because_the_gas_is_prescribed(self, result):
        """Drift would mean the deck is not doing what the scenario claims."""
        first, last = result.fed_history[0], result.fed_history[-1]
        for column in ("co_percent", "co2_percent", "o2_percent"):
            assert float(last[column]) == pytest.approx(float(first[column]), rel=1e-6)

    def test_none_of_the_three_is_silently_zero(self, result):
        """A missing species disables FED and leaves its column at zero.

        That reads exactly like a genuinely clean atmosphere, which is why
        docs/fds-case-requirements.md calls it a silent failure mode.
        """
        row = result.fed_history[0]
        assert float(row["co_percent"]) > 0.0
        assert float(row["co2_percent"]) > 0.0
        assert 0.0 < float(row["o2_percent"]) < 20.9


class TestTheDoseMatchesTheClosedForm:
    def test_the_rate_matches_the_analytic_rate(self, result):
        builder = _builder()
        expected = default_fed_rate_per_minute(builder.expected_inputs())
        assert float(result.fed_history[0]["fed_rate_per_min"]) == pytest.approx(
            expected, rel=1e-3
        )

    def test_the_threshold_is_crossed_at_the_analytic_time(self, result):
        """The headline: gas from FDS, integrated by the run loop, lands where
        the closed form says it should."""
        builder = _builder()
        analytic = builder.expected_threshold_time_s()
        crossing = next(
            (
                float(row["time_s"])
                for row in result.fed_history
                if float(row["fed_cumulative"]) >= 1.0
            ),
            None,
        )
        assert crossing is not None, "FED never reached 1.0"
        # The history is sampled at the FED update interval, so the observed
        # crossing can only be located to within one row.
        interval = _history_interval(result.fed_history)
        assert abs(crossing - analytic) <= 2 * interval, (
            f"crossed at {crossing} s, analytic {analytic:.1f} s"
        )

    def test_the_dose_grows_monotonically(self, result):
        values = [float(row["fed_cumulative"]) for row in result.fed_history]
        assert all(b >= a for a, b in zip(values, values[1:]))


class TestTheOccupantStaysPut:
    """If the agent walked out, the exposure would have ended early and the
    timing comparison above would be meaningless."""

    def test_it_does_not_evacuate(self, result):
        assert result.metrics["agents_remaining"] == 1
        assert result.metrics["all_evacuated"] is False

    def test_it_does_not_move(self, result):
        xs = {round(float(row["x"]), 3) for row in result.fed_history}
        ys = {round(float(row["y"]), 3) for row in result.fed_history}
        assert len(xs) == 1 and len(ys) == 1

    def test_the_dose_reaches_the_threshold(self, result):
        assert result.metrics["fed_max"] >= 1.0


def _history_interval(history) -> float:
    times = [float(row["time_s"]) for row in history]
    gaps = {round(b - a, 6) for a, b in zip(times, times[1:])}
    return max(gaps) if gaps else 1.0
