"""FED and FIC act on different timescales, and only one of them bites early.

Drives the ``assets/fic_vs_fed_speed`` gas mixture through the real tenability
model.  The scenario's claim, stated in advance so it can be falsified:

* **FED alone changes nothing** on a short egress.  It is a cumulative dose
  with a threshold, and the dose does not get near the threshold in the time
  an agent needs to walk out.
* **FIC bites immediately**, because it responds to the concentration present
  right now rather than to an accumulated dose.

If that is wrong -- if FED materially slows an agent over a minute of exposure
-- then either the model or this reasoning is broken, and the tests below say
which.

No FDS output is needed: the mixture is prescribed in the deck, so the same
numbers can be handed straight to the model.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pyfds_evac.core.fed import (
    DefaultFedInputs,
    default_fed_rate_per_minute,
    default_fic,
)

ASSET = Path("assets/fic_vs_fed_speed")


def _builder():
    spec = importlib.util.spec_from_file_location(
        "fvf_builder", ASSET / "build_geometry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mixture(builder) -> DefaultFedInputs:
    """The gas the deck prescribes, as the model sees it."""
    return DefaultFedInputs(
        co_volume_fraction_percent=builder.CO_PPM / 1e4,
        co2_volume_fraction_percent=0.05,
        o2_volume_fraction_percent=20.9,
        acrolein_ppm=builder.ACROLEIN_PPM,
    )


def _fic_speed_factor(builder, fic: float) -> float:
    return max(builder.FIC_MIN_FACTOR, 1.0 - builder.FIC_ALPHA * fic)


class TestScenarioPremises:
    """The comparison is meaningless if these drift."""

    def test_fic_is_off_its_floor_and_off_unity(self):
        """Pinned at the floor would hide an fic_alpha error; near 1 is unmeasurable."""
        builder = _builder()
        factor = _fic_speed_factor(builder, default_fic(_mixture(builder)))
        assert builder.FIC_MIN_FACTOR < factor < 0.95

    def test_the_deck_and_the_model_agree_on_the_mixture(self):
        """The builder's arithmetic must match what the model computes."""
        builder = _builder()
        assert default_fic(_mixture(builder)) == pytest.approx(
            builder.expected_fic(), rel=1e-9
        )
        assert _fic_speed_factor(builder, default_fic(_mixture(builder))) == (
            pytest.approx(builder.expected_speed_factor(), rel=1e-9)
        )


class TestFedIsSlowAndFicIsFast:
    def test_fic_cuts_speed_immediately(self):
        builder = _builder()
        fic = default_fic(_mixture(builder))
        assert fic == pytest.approx(0.5, abs=1e-9)
        assert _fic_speed_factor(builder, fic) == pytest.approx(0.65, abs=1e-9)

    def test_fed_does_not_reach_the_threshold_during_the_egress(self):
        """The load-bearing claim: FED alone is inert on this timescale."""
        builder = _builder()
        rate = default_fed_rate_per_minute(_mixture(builder))
        walk_seconds = (builder.EXIT_BOX[1] - builder.SPAWN[3]) / (
            builder.V0 * builder.expected_speed_factor()
        )
        dose = rate * walk_seconds / 60.0
        assert dose < 0.1, "FED should stay far below the incapacitation threshold"
        assert 1.0 / rate > 10.0, "time to FED=1 should be minutes, not seconds"

    def test_fed_would_bite_eventually(self):
        """Not that FED is broken -- only that it is slow. Sanity on the other side."""
        builder = _builder()
        rate = default_fed_rate_per_minute(_mixture(builder))
        assert rate > 0.0
        assert rate * (30.0 * 60.0) / 60.0 > 1.0, (
            "30 min of exposure should incapacitate"
        )

    def test_removing_the_irritant_removes_the_speed_penalty(self):
        """Control: the speed penalty is attributable to acrolein alone.

        Acrolein is not only an irritant -- it also appears in FED's Fractional
        Lethal Dose sum, so removing it moves both quantities.  The asymmetry is
        the point: it removes *all* of the speed penalty but only 3 % of the
        dose rate, which is what makes FIC and FED separable at all.
        """
        builder = _builder()
        no_irritant = DefaultFedInputs(
            co_volume_fraction_percent=builder.CO_PPM / 1e4,
            co2_volume_fraction_percent=0.05,
            o2_volume_fraction_percent=20.9,
        )
        assert default_fic(no_irritant) == 0.0
        assert _fic_speed_factor(builder, default_fic(no_irritant)) == 1.0

        with_irritant = default_fed_rate_per_minute(_mixture(builder))
        without = default_fed_rate_per_minute(no_irritant)
        assert without < with_irritant, "acrolein does contribute to the dose"
        assert without / with_irritant > 0.95, (
            "but CO dominates the dose rate, so the FED arm is essentially "
            "unchanged by the irritant while the FIC arm is entirely driven by it"
        )


class TestO2HypoxiaReference:
    """The published closed form, cited rather than re-derived.

    Recorded here because the reference in the verification suite carried a
    spurious 60x for seven weeks (fixed in #52). ``FI_O2`` in the literature is
    already a *rate* per minute, so there is no seconds conversion to apply.
    """

    def test_o2_rate_matches_the_published_closed_form(self):
        import math

        # Fire Safety Journal, "On the use of surrogate gases in fire toxicity
        # calculations", Eq. (9), the form the paper states is implemented in
        # FDS:  FI_O2 = 1 / exp{8.13 - 0.54 (20.9 - X_O2 [%])}
        for o2 in (19.4, 18.0, 15.0):
            expected = 1.0 / math.exp(8.13 - 0.54 * (20.9 - o2))
            got = default_fed_rate_per_minute(
                DefaultFedInputs(o2_volume_fraction_percent=o2)
            )
            assert got == pytest.approx(expected, rel=1e-9), f"at {o2} % O2"

    def test_the_gate_closes_at_and_above_the_safe_threshold(self):
        for o2 in (19.5, 20.9):
            assert (
                default_fed_rate_per_minute(
                    DefaultFedInputs(o2_volume_fraction_percent=o2)
                )
                == 0.0
            )
