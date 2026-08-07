"""ISO 20414 Table 22, with the gas read from real FDS output.

ISO 20414:2020 Table 22 (Test 19) specifies a room with no fire source,
10 m x 10 m x 3 m, an occupant at the centre held still by a pre-evacuation
time above 10 000 000 s, and this expected result:

    "the time to reach occupant incapacitation (FED=1) in Step 1 is the same
     as the time to reach FED=1 in the measurement point in Step 2"

where Step 2 is "hand calculations or an independent validated fire model".
Step 1 here is a real ``run_scenario``; Step 2 is ``time_to_fed_threshold_s()``,
exact because the gas is prescribed by a single ``&INIT`` and therefore uniform
in space and constant in time.

ISO says to "repeat for each hazardous condition available in the
incapacitation sub-model" but prescribes no concentrations. The four sets come
from the FDS+Evac Technical Reference, Figure 8 ("A FED test"), and are chosen
so the terms can be told apart -- one isolates O2 hypoxia, one isolates CO, one
adds the CO2 hyperventilation factor, one runs all three.

Contrast ``test_fed.py::test_iso_table22_stationary_runtime_matches_analytic_threshold_time``,
which performs the same test with the field *stubbed*: its FED model ignores
``time_s``, ``x`` and ``y``. That verifies the accumulator; this verifies the
whole chain from deck to dose. The FDS output is committed (256 kB for all four
cases) so this runs in CI -- skipping when output is absent would leave the path
as untested as it was before.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fed import default_fed_rate_per_minute
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario, run_scenario

ASSET = Path("assets/iso_table22_coupled")
CASES = ("a", "b", "c", "d")


def _builder():
    spec = importlib.util.spec_from_file_location(
        "iso22c_builder", ASSET / "build_geometry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(case: str):
    """Step 1 of the ISO test, through the same option builder the CLI uses.

    Constructing the FED model by hand would skip ``_build_fed_model`` and the
    slice-height plumbing, which are part of what this exists to cover.
    """
    scenario = load_scenario(str(ASSET / f"config_{case}.json"))
    opts = SimpleNamespace(
        seed=420,
        fds_dir=str(ASSET / "fds" / case),
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
    return run_scenario(scenario, **build_run_kwargs(scenario, opts))


@pytest.fixture(scope="module")
def results():
    """Run all four cases, cleaning up even if one fails to start.

    Built incrementally rather than in a comprehension: if ``_run`` raises on
    case c, the comprehension never reaches ``yield`` and the temporary SQLite
    files from a and b are never released.
    """
    outcomes: dict[str, object] = {}
    try:
        for case in CASES:
            outcomes[case] = _run(case)
        yield outcomes
    finally:
        for outcome in outcomes.values():
            outcome.cleanup()


def _history_interval(history) -> float:
    times = [float(row["time_s"]) for row in history]
    gaps = {round(b - a, 6) for a, b in zip(times, times[1:])}
    return max(gaps) if gaps else 1.0


class TestThePremise:
    def test_the_room_matches_the_standard(self):
        """ISO 20414 Table 22: "A room with no fire source (10 m x 10 m x 3 m)"."""
        builder = _builder()
        assert builder.ROOM == (0.0, 0.0, 10.0, 10.0)
        assert builder.CEILING == 3.0

    def test_the_occupant_is_held_by_a_pre_evacuation_time_above_ten_million(self):
        """ISO's own method, and the draw is bounded below so it always holds.

        A uniform draw over [0, 2e7] -- which is what assets/ISO-table22 does --
        can return a few seconds and let the occupant walk away mid-test.
        """
        builder = _builder()
        assert builder.PREMOVEMENT_LO > 1.0e7
        params = builder.build_config("a")["distributions"]["jps-distributions_0"][
            "parameters"
        ]
        assert params["use_premovement"] is True
        assert params["premovement_param_a"] > 1.0e7

    def test_the_committed_fds_output_is_present_for_every_case(self):
        for case in CASES:
            directory = ASSET / "fds" / case
            assert list(directory.glob("*.sf")), f"case {case}: no slice files"
            assert list(directory.glob("*.smv")), f"case {case}: no .smv"

    @pytest.mark.parametrize("case", CASES)
    def test_the_crossing_happens_before_the_deck_ends(self, case):
        builder = _builder()
        assert builder.threshold_time_s(case) < builder.end_time_s(case)


class TestTheGasReachesTheModelUnaltered:
    """The step the stubbed test cannot exercise at all.

    A ppm/vol-% confusion, a mass-fraction/volume-fraction mix-up, or a slice
    read at the wrong height all surface here as a concentration that differs
    from what the deck prescribes.
    """

    @pytest.mark.parametrize("case", CASES)
    def test_every_species_arrives_at_its_prescribed_concentration(self, results, case):
        builder = _builder()
        spec = builder.CASES[case]
        row = results[case].fed_history[0]
        assert float(row["co_percent"]) == pytest.approx(spec["co"], abs=2e-3)
        assert float(row["co2_percent"]) == pytest.approx(spec["co2"], abs=2e-2)
        assert float(row["o2_percent"]) == pytest.approx(spec["o2"], abs=2e-2)

    @pytest.mark.parametrize("case", CASES)
    def test_the_concentration_is_constant_because_the_gas_is_prescribed(
        self, results, case
    ):
        first, last = results[case].fed_history[0], results[case].fed_history[-1]
        for column in ("co_percent", "co2_percent", "o2_percent"):
            assert float(last[column]) == pytest.approx(float(first[column]), rel=1e-6)

    def test_the_cases_that_should_be_free_of_a_species_really_are(self, results):
        """Case b has no CO at all, and b and c no CO2.

        A sampler that quietly returned a default, or read the wrong slice,
        would show a non-zero value here.
        """
        assert float(results["b"].fed_history[0]["co_percent"]) == pytest.approx(
            0.0, abs=1e-4
        )
        for case in ("b", "c"):
            assert float(results[case].fed_history[0]["co2_percent"]) == pytest.approx(
                0.0, abs=1e-3
            )


class TestTheDoseMatchesTheHandCalculation:
    """ISO's expected result: Step 1 time equals Step 2 time."""

    @pytest.mark.parametrize("case", CASES)
    def test_the_rate_matches(self, results, case):
        builder = _builder()
        expected = default_fed_rate_per_minute(builder.inputs_for(case))
        assert float(results[case].fed_history[0]["fed_rate_per_min"]) == pytest.approx(
            expected, rel=2e-3
        )

    @pytest.mark.parametrize("case", CASES)
    def test_the_threshold_is_crossed_at_the_hand_calculated_time(self, results, case):
        builder = _builder()
        analytic = builder.threshold_time_s(case)
        history = results[case].fed_history
        crossing = next(
            (
                float(row["time_s"])
                for row in history
                if float(row["fed_cumulative"]) >= 1.0
            ),
            None,
        )
        assert crossing is not None, f"case {case}: FED never reached 1.0"
        # The history is sampled at the FED update interval, so the observed
        # crossing can only be located to within one row.
        tolerance = 2 * _history_interval(history)
        assert abs(crossing - analytic) <= tolerance, (
            f"case {case}: crossed at {crossing} s, hand calculation {analytic:.1f} s"
        )

    def test_the_four_cases_separate_the_terms(self):
        """The reason the guide uses four sets rather than one.

        Case c is CO alone -- its O2 is above the 19.5 % gate and it has no CO2.
        Case d adds only the CO2 hyperventilation factor, so it must be strictly
        faster while sharing case c's CO. If the CO2 term were dropped the two
        would coincide, and a single-case test would not notice.
        """
        builder = _builder()
        rate = {c: default_fed_rate_per_minute(builder.inputs_for(c)) for c in CASES}
        assert rate["d"] > rate["c"], "the CO2 factor must accelerate the dose"
        assert builder.CASES["c"]["co"] == builder.CASES["d"]["co"]
        assert rate["b"] > 0.0, "O2 hypoxia alone must still accumulate a dose"
        assert builder.CASES["b"]["co"] == 0.0


class TestTheOccupantStaysPut:
    """If the occupant moved, the exposure would have changed and the timing
    comparison above would be meaningless."""

    @pytest.mark.parametrize("case", CASES)
    def test_it_does_not_evacuate(self, results, case):
        assert results[case].metrics["agents_remaining"] == 1
        assert results[case].metrics["all_evacuated"] is False

    @pytest.mark.parametrize("case", CASES)
    def test_it_does_not_move(self, results, case):
        history = results[case].fed_history
        xs = {round(float(row["x"]), 3) for row in history}
        ys = {round(float(row["y"]), 3) for row in history}
        assert len(xs) == 1 and len(ys) == 1

    @pytest.mark.parametrize("case", CASES)
    def test_the_dose_reaches_the_threshold(self, results, case):
        assert results[case].metrics["fed_max"] >= 1.0
