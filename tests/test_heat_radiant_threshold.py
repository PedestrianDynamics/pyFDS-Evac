"""ISO 2.5 kW/m2 radiant threshold in the total-flux dose (spec 016, #223).

Source: ISO 13571:2012 §8.2 and §8.4: the radiant contribution to the heat
FED is zero where the radiant heat flux to the skin is below 2.5 kW/m2 (an
incident flux level in ISO's words). Maintainer decision: the total-flux
method (``--heat-fed-method total-flux``) follows ISO for this threshold.
It applies to the radiant component only; convection keeps counting at all
levels, so hot air still gives a dose. With T in K, sigma = 5.67e-8
W m^-2 K^-4 (SFPE Ch. 63, p. 2384), all fluxes in kW/m2:

    q_rad  = eps sigma (T_g^4 - T_s^4) / 1000           gas at the head
           = f (U - 4 sigma T_s^4 / 1000)                INTEGRATED INTENSITY
           = phi eps_L sigma (T_L^4 - T_s^4) / 1000      hot layer
    q_conv = h (T_g - T_s) / 1000
    q      = (q_rad if q_rad >= 2.5 else 0) + q_conv
    rate   = q^1.33 / D                                  Eq. 63.43, 1/min

ISO says "below 2.5", so 2.5 itself counts. A negative radiant term (source
cooler than the skin) is below 2.5 and counts as zero. The recorded
``heat_flux_kw_m2`` stays the physical q (Eq. 63.49, no threshold); only the
dose uses the counted q.

Expected values are the hand formulas in this file, never ``pyfds_evac``.

API under test:

- ``pyfds_evac.core.fed.ISO_RADIANT_THRESHOLD_KW_M2 == 2.5``.
- ``pyfds_evac.core.fed.counted_radiant_flux_kw_m2(q_rad) -> float``: 0.0
  below the threshold, ``q_rad`` otherwise (NaN passes through).
- ``DefaultHeatFedModel.heat_flux_parameters()["radiant_threshold_kw_m2"]``.
"""

from __future__ import annotations

import math

import pytest

from pyfds_evac.core.fed import DefaultFedConfig, DefaultHeatFedModel, FdsHeatField

SIGMA = 5.67e-8  # W m^-2 K^-4, as printed on SFPE Ch. 63, p. 2384
KELVIN = 273.15
EXPONENT = 1.33  # Eq. 63.43 prints 1.33
D_FATAL = 16.7  # SFPE Ch. 63, p. 2384
ISO_THRESHOLD = 2.5  # ISO 13571:2012 §8.2, §8.4, kW/m2
H, T_SKIN = 5.0, 35.0


# --- hand formulas ----------------------------------------------------------


def counted(q_rad):
    """ISO 13571:2012 §8.2/§8.4: zero below 2.5 kW/m2."""
    return 0.0 if q_rad < ISO_THRESHOLD else q_rad


def conv_hand(t_c):
    return H * (t_c - T_SKIN) / 1000.0


def rate_hand(q_rad, t_c):
    return (counted(q_rad) + conv_hand(t_c)) ** EXPONENT / D_FATAL


def sigma_dt4(t_c):
    """sigma (T^4 - T_s^4) in kW/m2."""
    return SIGMA * ((t_c + KELVIN) ** 4 - (T_SKIN + KELVIN) ** 4) / 1000.0


def t_for_sigma_dt4(q):
    """Temperature in deg C with sigma (T^4 - T_s^4) / 1000 = q."""
    return (q * 1000.0 / SIGMA + (T_SKIN + KELVIN) ** 4) ** 0.25 - KELVIN


U_SKIN = 4.0 * SIGMA * (T_SKIN + KELVIN) ** 4 / 1000.0  # isotropic at T_s


# --- helpers ----------------------------------------------------------------


class _Sampler:
    def __init__(self, value):
        self._value = value

    def sample(self, time_s, x, y):
        return float(self._value)


_CONFIG = DefaultFedConfig(fds_dir="", update_interval_s=1.0)


def _gas_model(t_c, eps):
    return DefaultHeatFedModel(
        FdsHeatField(_Sampler(t_c)),  # type: ignore[arg-type]
        _CONFIG,
        method="total-flux",
        emissivity=eps,
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
    )


def _u_model(t_c, u, f):
    return DefaultHeatFedModel(
        FdsHeatField(_Sampler(t_c), intensity_sampler=_Sampler(u)),  # type: ignore[arg-type]
        _CONFIG,
        method="total-flux",
        emissivity=0.5,
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
        radiant_source="integrated-intensity",
        u_factor=f,
    )


def _layer_model(t_head_c, t_layer_c, phi, eps_l):
    return DefaultHeatFedModel(
        FdsHeatField(_Sampler(t_head_c)),  # type: ignore[arg-type]
        _CONFIG,
        method="total-flux",
        emissivity=0.5,
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
        regime="layer",
        layer_field=FdsHeatField(_Sampler(t_layer_c)),  # type: ignore[arg-type]
        view_factor=phi,
        layer_emissivity=eps_l,
    )


def _rate(model):
    _, rate = model.sample_rate(0.0, 0.0, 0.0)
    return rate


# --- the constant and the helper --------------------------------------------


def test_threshold_constant_is_iso():
    from pyfds_evac.core.fed import ISO_RADIANT_THRESHOLD_KW_M2

    assert ISO_RADIANT_THRESHOLD_KW_M2 == 2.5


@pytest.mark.parametrize(
    ("q_rad", "expected"),
    [(2.4, 0.0), (2.4999, 0.0), (2.5, 2.5), (2.6, 2.6), (10.0, 10.0)],
)
def test_helper_zero_below_threshold(q_rad, expected):
    """ISO "below 2.5": 2.4 -> 0, exactly 2.5 counts, 2.6 counts."""
    from pyfds_evac.core.fed import counted_radiant_flux_kw_m2

    assert counted_radiant_flux_kw_m2(q_rad) == expected


@pytest.mark.parametrize("q_rad", [0.0, -0.3, -5.0, -math.inf])
def test_helper_negative_radiant_is_zero(q_rad):
    from pyfds_evac.core.fed import counted_radiant_flux_kw_m2

    assert counted_radiant_flux_kw_m2(q_rad) == 0.0


def test_helper_passes_nan_and_inf_through():
    """NaN (no sample) must still void the dose; inf stays inf."""
    from pyfds_evac.core.fed import counted_radiant_flux_kw_m2

    assert math.isnan(counted_radiant_flux_kw_m2(math.nan))
    assert counted_radiant_flux_kw_m2(math.inf) == math.inf


# --- gas term at the head ----------------------------------------------------


@pytest.mark.parametrize("q_rad", [2.4, 2.6])
def test_gas_term_threshold(q_rad):
    """eps = 0.5; T_g chosen so eps sigma dT^4 = q_rad. 2.4 drops the radiant
    part (convection alone), 2.6 keeps it."""
    eps = 0.5
    t_c = t_for_sigma_dt4(q_rad / eps)
    assert eps * sigma_dt4(t_c) == pytest.approx(q_rad, rel=1e-12)
    assert _rate(_gas_model(t_c, eps)) == pytest.approx(rate_hand(q_rad, t_c), rel=1e-9)


def test_gas_term_below_threshold_leaves_convection_unchanged():
    """2.4 kW/m2 radiant: rate is exactly q_conv^1.33 / D."""
    eps = 0.5
    t_c = t_for_sigma_dt4(2.4 / eps)
    expected = conv_hand(t_c) ** EXPONENT / D_FATAL
    assert _rate(_gas_model(t_c, eps)) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("t_c", [100.0, 150.0, 200.0])
def test_hot_air_convection_still_accumulates(t_c):
    """Clear air, eps = 0.05: the radiant part is far below 2.5 kW/m2
    (0.04 kW/m2 at 150 deg C), yet the dose accrues from h (T_g - T_s)."""
    eps = 0.05
    assert eps * sigma_dt4(t_c) < ISO_THRESHOLD
    got = _rate(_gas_model(t_c, eps))
    assert got > 0.0
    assert got == pytest.approx(conv_hand(t_c) ** EXPONENT / D_FATAL, rel=1e-9)


def test_history_flux_stays_physical():
    """heat_flux_kw_m2 is Eq. 63.49 without the threshold."""
    eps, t_c = 0.5, 150.0
    q_physical = eps * sigma_dt4(t_c) + conv_hand(t_c)
    assert _gas_model(t_c, eps).heat_flux_kw_m2(t_c) == pytest.approx(
        q_physical, rel=1e-9
    )


# --- INTEGRATED INTENSITY term -----------------------------------------------


@pytest.mark.parametrize("q_rad", [2.4, 2.6])
def test_integrated_intensity_term_threshold(q_rad):
    """f (U - 4 sigma T_s^4 / 1000) = q_rad with f = 0.5, T_g = 150 deg C."""
    f, t_c = 0.5, 150.0
    u = U_SKIN + q_rad / f
    assert f * (u - U_SKIN) == pytest.approx(q_rad, rel=1e-12)
    assert _rate(_u_model(t_c, u, f)) == pytest.approx(rate_hand(q_rad, t_c), rel=1e-9)


def test_integrated_intensity_below_skin_field_is_zero_not_negative():
    """U below the skin field: the negative radiant excess counts as zero
    and no longer subtracts from convection."""
    f, t_c = 0.5, 150.0
    u = U_SKIN - 1.0
    assert _rate(_u_model(t_c, u, f)) == pytest.approx(
        conv_hand(t_c) ** EXPONENT / D_FATAL, rel=1e-9
    )


def test_integrated_intensity_nan_still_voids_the_dose():
    """Outside the INTEGRATED INTENSITY slice U is NaN: rate 0, not
    convection alone."""
    assert _rate(_u_model(150.0, math.nan, 0.5)) == 0.0


# --- hot-layer term ----------------------------------------------------------


@pytest.mark.parametrize("q_rad", [2.4, 2.6])
def test_layer_term_threshold(q_rad):
    """phi eps_L sigma (T_L^4 - T_s^4) / 1000 = q_rad with phi = eps_L = 1,
    head in clear air at 60 deg C."""
    t_head = 60.0
    t_layer = t_for_sigma_dt4(q_rad)
    assert sigma_dt4(t_layer) == pytest.approx(q_rad, rel=1e-12)
    got = _rate(_layer_model(t_head, t_layer, 1.0, 1.0))
    assert got == pytest.approx(rate_hand(q_rad, t_head), rel=1e-9)


def test_layer_cooler_than_skin_counts_as_zero():
    """Layer at 20 deg C: net radiant term negative, counted as zero."""
    t_head = 60.0
    assert sigma_dt4(20.0) < 0.0
    got = _rate(_layer_model(t_head, 20.0, 1.0, 1.0))
    assert got == pytest.approx(conv_hand(t_head) ** EXPONENT / D_FATAL, rel=1e-9)


# --- provenance --------------------------------------------------------------


def test_manifest_records_the_threshold():
    params = _gas_model(150.0, 0.5).heat_flux_parameters()
    assert params["radiant_threshold_kw_m2"] == 2.5
    assert "radiant_threshold_kw_m2" not in params["assumed"]
