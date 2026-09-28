"""FDS verification case Species/FED_FIC, all four zones (#194).

Each zone of `Verification/Species/FED_FIC.fds` holds constant mole fractions
for 100 s (given in the deck's comments); `FED_FIC.csv` gives the expected FED
and FIC at 100 s. FDS accepts a relative error of 0.01 at the end time
(`FDS_verification_dataplot_inputs.csv`); we hold the published 4-5 significant
figures to 1e-3.

The "Irritants" zone has no CO2. FDS (`func.f90`, function `FED`) applies the
CO2 hyperventilation factor only when X_CO2 > 0, so the factor there is 1;
using exp(2.0004)/7.1 = 1.0411 instead overshoots FDS by 4.1 %.
"""

import math

import pytest

from pyfds_evac.core.fed import (
    DefaultFedInputs,
    _hyperventilation_factor,
    accumulate_default_fed,
    default_fic,
)

_PPM = 1e6
_ZONES = {
    "O2 CO2 CO": (
        DefaultFedInputs(
            o2_volume_fraction_percent=100.0 * 0.09772709,
            co2_volume_fraction_percent=100.0 * 0.03430594,
            co_volume_fraction_percent=100.0 * 0.00324186,
        ),
        0.5994,
        0.0,
    ),
    "Asphyxiants": (
        DefaultFedInputs(
            o2_volume_fraction_percent=100.0 * 0.09021848,
            co2_volume_fraction_percent=100.0 * 0.01918864,
            co_volume_fraction_percent=2455.82e-4,
            no_ppm=134.87,
            hcn_ppm=265.33,
        ),
        0.97403,
        0.0,
    ),
    "Irritants": (
        DefaultFedInputs(
            o2_volume_fraction_percent=100.0 * 0.20900000,
            no2_ppm=_PPM * 0.00000114,
            hcl_ppm=_PPM * 0.00006833,
            hbr_ppm=_PPM * 0.00006833,
            hf_ppm=_PPM * 0.00005215,
            so2_ppm=_PPM * 0.00000719,
            acrolein_ppm=_PPM * 0.00000270,
            formaldehyde_ppm=_PPM * 0.00001349,
        ),
        0.0082584,
        0.8574,
    ),
    "All": (
        DefaultFedInputs(
            o2_volume_fraction_percent=100.0 * 0.10305454,
            co2_volume_fraction_percent=100.0 * 0.00746276,
            co_volume_fraction_percent=100.0 * 0.00166045,
            no_ppm=_PPM * 0.00008934,
            no2_ppm=_PPM * 0.00000057,
            hcn_ppm=_PPM * 0.00020396,
            hcl_ppm=_PPM * 0.00003417,
            hbr_ppm=_PPM * 0.00003417,
            hf_ppm=_PPM * 0.00002607,
            so2_ppm=_PPM * 0.00000360,
            acrolein_ppm=_PPM * 0.00000135,
            formaldehyde_ppm=_PPM * 0.00000674,
        ),
        0.51369,
        0.4287,
    ),
}


@pytest.mark.parametrize("zone", list(_ZONES))
def test_fed_at_100_s_matches_fds(zone):
    inputs, fed_expected, _ = _ZONES[zone]
    got = accumulate_default_fed(inputs, duration_s=100.0)
    assert got == pytest.approx(fed_expected, rel=1e-3)


@pytest.mark.parametrize("zone", list(_ZONES))
def test_fic_matches_fds(zone):
    inputs, _, fic_expected = _ZONES[zone]
    assert default_fic(inputs) == pytest.approx(fic_expected, rel=1e-3, abs=1e-12)


@pytest.mark.parametrize("co2_percent", [0.0, -1.0, math.nan])
def test_no_hyperventilation_without_co2(co2_percent):
    """FDS applies exp(0.1903*C + 2.0004)/7.1 only for X_CO2 > 0."""
    assert _hyperventilation_factor(co2_percent) == 1.0


def test_hyperventilation_formula_with_co2():
    assert _hyperventilation_factor(3.0) == pytest.approx(
        math.exp(0.1903 * 3.0 + 2.0004) / 7.1, rel=1e-12
    )
