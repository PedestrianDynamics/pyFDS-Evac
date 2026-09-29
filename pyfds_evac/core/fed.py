"""Default FDS+Evac FED equations and FDS-backed gas samplers."""

import logging
import math
from dataclasses import dataclass, replace

from .fds_sampling import SliceFieldSampler, _slice_z_mid, load_slice_sampler

_logger = logging.getLogger(__name__)

_SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class DefaultFedInputs:
    """Store gas concentrations for the Purser FED model.

    All toxicant concentrations default to 0 (absent) and O2 defaults to
    normal air (20.9%).  When an FDS simulation does not track a species
    the corresponding field stays at its safe default, contributing nothing
    to the FED sum.
    """

    co_volume_fraction_percent: float = 0.0
    co2_volume_fraction_percent: float = 0.0
    o2_volume_fraction_percent: float = 20.9
    hcn_ppm: float = 0.0
    no_ppm: float = 0.0
    no2_ppm: float = 0.0
    hcl_ppm: float = 0.0
    hbr_ppm: float = 0.0
    hf_ppm: float = 0.0
    so2_ppm: float = 0.0
    acrolein_ppm: float = 0.0
    formaldehyde_ppm: float = 0.0


@dataclass(frozen=True)
class DefaultFedConfig:
    """Store FDS path and sampling settings for FED evaluation."""

    fds_dir: str | None = None
    update_interval_s: float = 1.0
    slice_height_m: float = 1.6
    # O2 [vol %] at or above which the hypoxia term is zero. 20.0 is FDS's
    # guard (func.f90: the O2 term applies only when X_O2 < 0.20); 19.5 is
    # the OSHA / Pathfinder value pyFDS-Evac used before.
    o2_threshold_percent: float = 20.0


def _co_percent_to_ppm(co_volume_fraction_percent: float) -> float:
    """Convert CO from volume percent to ppm for the FED equation."""
    return max(0.0, float(co_volume_fraction_percent)) * 10000.0


def _co_fed_rate_per_minute(co_ppm: float) -> float:
    """Return the CO FED contribution in 1/min from guide Eq. 13."""

    if not math.isfinite(co_ppm) or co_ppm <= 0.0:
        return 0.0
    return 2.764e-5 * (co_ppm**1.036)


def _hyperventilation_factor(co2_percent: float) -> float:
    """Return the CO2 hyperventilation factor from guide Eq. 19.

    As in FDS (``func.f90``, function ``FED``), the factor applies only when
    CO2 is present: with no CO2, or a missing reading, it is 1. Eq. 19 read
    literally would give exp(2.0004)/7.1 = 1.0411 at zero CO2. This follows
    FDS at zero CO2 only: for any CO2 above zero Eq. 19 applies unchanged,
    including its ~4 % offset, so the factor steps from 1 to 1.041 there.
    """

    if not math.isfinite(co2_percent) or co2_percent <= 0.0:
        return 1.0
    return math.exp(0.1903 * float(co2_percent) + 2.0004) / 7.1


_O2_HYPOXIA_THRESHOLD_PERCENT: float = 20.0
"""Default O2 concentration at or above which hypoxia does not contribute to FED.

At ambient O2 (20.9 %) the SFPE Eq. 18 denominator is non-zero, so the
rate is tiny but finite — accumulating over a long simulation (or when
the agent is outside the FDS domain and O2 defaults to 20.9 %) it
produces spurious FED drift.  FDS, and so FDS+Evac, applies the O2 term
only when X_O2 < 0.20 (``FED()`` in ``func.f90``), which is the default
here.  OSHA defines the safe lower limit for working conditions as
19.5 %, and Pathfinder uses that value; pass 19.5 through
``DefaultFedConfig.o2_threshold_percent`` or ``--o2-threshold-percent``
to use it.
"""


def _o2_hypoxia_rate_per_minute(
    o2_percent: float,
    threshold_percent: float = _O2_HYPOXIA_THRESHOLD_PERCENT,
) -> float:
    """Return the O2 hypoxia FED contribution in 1/min from guide Eq. 18.

    t_incap [min] = exp(8.13 - 0.54 * (20.9 - C_O2%))   (Purser / FDS Tech Ref)
    rate [1/min]  = 1 / t_incap

    Returns 0 when O2 is at or above ``threshold_percent`` (default 20.0 %,
    as FDS) to prevent spurious accumulation under safe ambient conditions.
    """

    if not math.isfinite(o2_percent):
        o2_percent = 20.9
    if float(o2_percent) >= float(threshold_percent):
        return 0.0
    t_incap_min = math.exp(8.13 - 0.54 * (20.9 - float(o2_percent)))
    if t_incap_min <= 0.0:
        return 0.0
    return 1.0 / t_incap_min


def _cn_fed_rate_per_minute(hcn_ppm: float, no_ppm: float, no2_ppm: float) -> float:
    """Return the CN narcosis FED contribution in 1/min, as FDS computes it.

    C_CN = C_HCN - (C_NO + C_NO2) (NOx has a protective effect on HCN
    toxicity).  Rate = exp(C_CN/43)/220 - 1/220, which is zero at C_CN = 0.

    This is the form of FDS ``FED()`` in ``func.f90`` (User Guide 6.10.1,
    Eq. 22.45), which FDS+Evac calls, and which has carried the HCN term
    since FDS commit 694e033 (2011).  The FDS+Evac guide's Eq. 15 subtracts
    NO2 only and uses the offset 0.0045; FDS and FDS+Evac never computed
    that form (#159).
    """
    c_nox = max(0.0, float(no_ppm)) + max(0.0, float(no2_ppm))
    c_cn = max(0.0, float(hcn_ppm) - c_nox)
    if not math.isfinite(c_cn) or c_cn <= 0.0:
        return 0.0
    rate = (math.exp(c_cn / 43.0) - 1.0) / 220.0
    return max(0.0, rate)


def _nox_fed_rate_per_minute(no_ppm: float, no2_ppm: float) -> float:
    """Return the NOx FED contribution in 1/min (guide Eq. 16).

    C_NOx = C_NO + C_NO2.  Ct product = 1500 ppm·min.
    """
    c_nox = max(0.0, float(no_ppm)) + max(0.0, float(no2_ppm))
    if not math.isfinite(c_nox) or c_nox <= 0.0:
        return 0.0
    return c_nox / 1500.0


def _irritant_fld_rate_per_minute(inputs: DefaultFedInputs) -> float:
    """Return the irritant FLD contribution in 1/min (Purser).

    Each irritant gas contributes concentration / Ct, where Ct (ppm·min) is
    the lethal exposure dose for that species.
    """
    # Ct products for lethality (ppm·min) from guide Table 2
    terms = (
        (inputs.hcl_ppm, 114000.0),
        (inputs.hbr_ppm, 114000.0),
        (inputs.hf_ppm, 87000.0),
        (inputs.so2_ppm, 12000.0),
        (inputs.no2_ppm, 1900.0),
        (inputs.acrolein_ppm, 4500.0),
        (inputs.formaldehyde_ppm, 22500.0),
    )
    total = 0.0
    for conc, ct in terms:
        if math.isfinite(conc) and conc > 0.0:
            total += conc / ct
    return total


# Purser's F_FIC values (ppm, incapacitating concentration) from the
# FDS+Evac Technical Reference (Korhonen 2021), Table 2.  Used to compute
# the *instantaneous* Fractional Irritant Concentration that drives
# pre-incapacitation walking-speed degradation (Jin's irritant-smoke
# experiments).
_FIC_COEFFS_PPM: tuple[tuple[str, float], ...] = (
    ("hcl_ppm", 900.0),
    ("hbr_ppm", 900.0),
    ("hf_ppm", 900.0),
    ("so2_ppm", 120.0),
    ("no2_ppm", 350.0),
    ("acrolein_ppm", 20.0),
    ("formaldehyde_ppm", 30.0),
)


def default_fic(inputs: DefaultFedInputs) -> float:
    """Return Purser's Fractional Irritant Concentration (instantaneous).

    FIC = sum_i C_i / F_FIC,i for irritant species; dimensionless.  Unlike
    FED (an accumulated dose) this is a point-in-time exposure index and
    it is not integrated.  At ``FIC >= 1`` roughly half of the exposed
    population would reach irritant incapacitation under sustained
    exposure; sub-unity values degrade performance progressively.
    """
    total = 0.0
    for attr, fic_ppm in _FIC_COEFFS_PPM:
        conc = float(getattr(inputs, attr, 0.0))
        if math.isfinite(conc) and conc > 0.0 and fic_ppm > 0.0:
            total += conc / fic_ppm
    return total


@dataclass(frozen=True)
class HeatFedInputs:
    """Store gas-phase temperature for the SFPE Handbook heat FED model.

    Tracked independently of ``DefaultFedInputs`` -- heat and toxic gases
    incapacitate through different physiological mechanisms (thermal injury
    vs. asphyxiation), so the SFPE Handbook keeps their doses as two separate
    running totals rather than summing them (see ``TenabilityConfig``).
    """

    temperature_celsius: float = 20.0
    # FDS INTEGRATED INTENSITY U [kW/m2] (#221); None when not sampled.
    integrated_intensity_kw_m2: float | None = None
    # Upper-layer temperature, sampled only with ``regime="layer"`` (#222).
    layer_temperature_celsius: float | None = None


# ISO 13571:2012 §8.3.2, air with less than 10 % water vapour by volume:
# t_Iconv [min] = a * T**-b, T in deg C. Eq. (9), fully clothed (Crane 1978);
# Eq. (10), unclothed or lightly clothed, has the constants of SFPE Handbook
# 5th ed. Eq. 63.44. Maps clothing -> (a, b).
HEAT_CLOTHING_LAWS: dict[str, tuple[float, float]] = {
    "clothed": (4.1e8, 3.61),
    "unclothed": (5e7, 3.4),
}
HEAT_CLOTHING = tuple(HEAT_CLOTHING_LAWS)
DEFAULT_HEAT_CLOTHING = "clothed"


def _check_heat_clothing(clothing: str) -> None:
    """Raise ValueError for a clothing that has no convective law."""
    if clothing not in HEAT_CLOTHING_LAWS:
        raise ValueError(
            f"Unknown heat clothing {clothing!r}; expected one of {HEAT_CLOTHING}"
        )


def _heat_fed_rate_per_minute(
    temperature_celsius: float, clothing: str = DEFAULT_HEAT_CLOTHING
) -> float:
    """Return the convective-heat FED contribution in 1/min (ISO 13571:2012).

    rate [1/min] = T[deg C] ** b / a, with (a, b) = (4.1e8, 3.61) for
    ``clothed`` (Eq. (9)) and (5e7, 3.4) for ``unclothed`` (Eq. (10), equal
    to SFPE Handbook Eq. 63.44).

    Not in the FDS+Evac guide like the other terms in this module. Scoped to
    convective heat from elevated gas temperature only (radiant heat is a
    separate term). Already negligible at ambient temperature, so no floor
    is applied beyond the domain guard.
    """
    _check_heat_clothing(clothing)
    if not math.isfinite(temperature_celsius) or temperature_celsius <= 0.0:
        return 0.0
    a, b = HEAT_CLOTHING_LAWS[clothing]
    return (temperature_celsius**b) / a


def default_heat_fed_rate_per_minute(
    inputs: HeatFedInputs, clothing: str = DEFAULT_HEAT_CLOTHING
) -> float:
    """Return the ISO 13571:2012 convective heat FED rate in 1/min.

    Eq. (9) for ``clothed`` (default), Eq. (10) = SFPE Eq. 63.44 for
    ``unclothed``.
    """
    return _heat_fed_rate_per_minute(inputs.temperature_celsius, clothing)


@dataclass(frozen=True)
class HeatEndpoint:
    """One heat endpoint of SFPE Handbook 5th ed. Ch. 63, pp. 2382-2384.

    Pairs the radiant dose ``radiant_dose`` r [(kW/m2)^4/3 min] of Eq. 63.43
    with the convective time law of the same endpoint,
    ``t [min] = a1 * T**-b1 + a2 * T**-b2`` with T in deg C. ``radiant_dose``
    enters the dose only with the total-flux method (#223).
    """

    radiant_dose: float
    equation: str
    a1: float
    b1: float
    a2: float
    b2: float


# SFPE Handbook 5th ed. Ch. 63 (Purser & McAllister): r from the list on
# p. 2382 and the Eq. 63.49 text on p. 2384; convective laws Eqs. 63.45-63.47,
# pp. 2382-2383, fitted to air with less than 10 % water vapour. The fatal
# r is 16.7 as printed on pp. 2382 and 2384; Purser's spreadsheet uses
# 16.667 (personal communication), the code follows the Handbook.
HEAT_ENDPOINTS: dict[str, HeatEndpoint] = {
    "tolerance": HeatEndpoint(1.33, "63.45", 2e31, 16.963, 4e8, 3.7561),
    "injury": HeatEndpoint(10.0, "63.46", 5e22, 11.783, 3e7, 2.9636),
    "fatal": HeatEndpoint(16.7, "63.47", 2e18, 9.0403, 1e8, 3.10898),
}

# Assumption: the Handbook gives no upper temperature for Eqs. 63.45-63.47;
# the limit is taken as the highest dry-air point of the convective tolerance
# data, Table 63.17 (Veghte, 205 deg C, p. 2375). p. 2383 relates the laws to
# air with less than 10 % water vapour. Humidity is not sampled, so its
# status is reported as HEAT_HUMIDITY_STATUS instead of being flagged.
HEAT_CONVECTIVE_VALIDITY_MAX_C = 205.0
HEAT_HUMIDITY_STATUS = "unknown"
HEAT_HUMIDITY_LIMIT = "< 10 % water vapour by volume (SFPE Ch. 63, p. 2383)"


def heat_temperature_outside_validity(temperature_celsius: float) -> bool:
    """Return True above the convective data or for a non-finite sample."""
    if not math.isfinite(temperature_celsius):
        return True
    return temperature_celsius > HEAT_CONVECTIVE_VALIDITY_MAX_C


def heat_endpoint_row_fields(
    endpoint: str | None, temperature_celsius: float
) -> dict[str, object]:
    """Return the FED history fields of ``--heat-endpoint``; ``{}`` without it."""
    if endpoint is None:
        return {}
    return {
        "heat_endpoint": endpoint,
        "heat_outside_validity": heat_temperature_outside_validity(temperature_celsius),
        "heat_humidity": HEAT_HUMIDITY_STATUS,
    }


def heat_endpoint_validity() -> dict[str, object]:
    """Return the validity range of Eqs. 63.45-63.47 for the run manifest."""
    return {
        "max_temperature_c": HEAT_CONVECTIVE_VALIDITY_MAX_C,
        "max_temperature_assumed": True,
        "humidity": HEAT_HUMIDITY_STATUS,
        "humidity_limit": HEAT_HUMIDITY_LIMIT,
    }


def endpoint_heat_fed_rate_per_minute(
    temperature_celsius: float, endpoint: HeatEndpoint
) -> float:
    """Return 1 / t_endpoint(T) in 1/min for one of Eqs. 63.45-63.47.

    Not clipped above the validity range: Table 63.21 (p. 2385) applies the
    law at 405 deg C. Non-finite and non-positive temperatures give 0.
    """
    if not math.isfinite(temperature_celsius) or temperature_celsius <= 0.0:
        return 0.0
    try:
        time_min = (
            endpoint.a1 * temperature_celsius**-endpoint.b1
            + endpoint.a2 * temperature_celsius**-endpoint.b2
        )
    except OverflowError:
        # Near 0 deg C the tolerance time is unbounded.
        return 0.0
    if not math.isfinite(time_min) or time_min <= 0.0:
        return 0.0
    return 1.0 / time_min


# Total-flux method (spec 016, #223): Eq. 63.49 for the heat flux to the skin,
# Eq. 63.43 for the time to the endpoint (SFPE Ch. 63, pp. 2382-2384).
HEAT_FED_METHODS = ("convective", "total-flux")
STEFAN_BOLTZMANN_W_M2_K4 = 5.67e-8  # as printed on p. 2384
HEAT_FLUX_EXPONENT = 1.33  # Eqs. 63.43 and 63.49 print 1.33, not 4/3
_KELVIN = 273.15
# Assumption: eps of the gas at the head. p. 2384 gives 0.05 for a gas and
# "perhaps 0.5 for smoke"; the default takes the head to be in smoke.
DEFAULT_HEAT_EMISSIVITY = 0.5
# Assumption: h in W/m2/K. p. 2384 gives "approximately 5-8 for slow-moving
# air" with no unit; 5 is the value of the spec 016 convection check.
DEFAULT_HEAT_CONVECTIVE_COEFFICIENT = 5.0
# Assumption: fixed skin temperature. The Handbook gives none for Eq. 63.49;
# 35 deg C is the value of the draft reviewed in spec 016.
DEFAULT_HEAT_SKIN_TEMPERATURE_C = 35.0
HEAT_FLUX_ASSUMED_PARAMETERS = (
    "emissivity",
    "convective_coefficient",
    "skin_temperature_celsius",
)
# Radiant term of the total-flux method (#221): "gas" is eps sigma
# (T_g^4 - T_s^4) of Eq. 63.49; "integrated-intensity" is the excess
# f (U - 4 sigma T_s^4) over an isotropic field at the skin temperature, from
# the FDS INTEGRATED INTENSITY slice, with f given by the user (no default).
HEAT_RADIANT_SOURCES = ("gas", "integrated-intensity")
HEAT_U_FACTOR_RANGE = (0.25, 1.0)  # sphere / isotropic field .. source face-on
# Largest z difference [m] accepted between the TEMPERATURE and INTEGRATED
# INTENSITY slices: a numerical tolerance only. FDS moves every slice at one
# PBZ to the same grid plane, so slices meant for one height share their z.
HEAT_SLICE_Z_TOLERANCE_M = 1e-6
# Regimes of spec 016, chosen by the user (no sourced automatic rule):
# "smoke", head in smoke, Eq. 63.49 at the head; "layer", head in clear air
# below a hot layer, convection at the head plus the layer term (#222).
HEAT_FLUX_REGIMES = ("smoke", "layer")


def radiant_flux_from_integrated_intensity_kw_m2(
    integrated_intensity_kw_m2: float, u_factor: float
) -> float:
    """Return the incident radiant flux f U in kW/m2 (spec 016, #221).

    U = integral of I over all solid angles (FDS ``INTEGRATED INTENSITY``).
    A surface sees one hemisphere weighted by cos(theta), so q lies between
    U/4 (sphere, or a plate in an isotropic field) and U (one small source
    seen face-on). ValueError for f outside [0.25, 1] or non-finite.
    """
    _check_u_factor(u_factor)
    return u_factor * integrated_intensity_kw_m2


def _check_u_factor(u_factor) -> None:
    """Raise ValueError unless *u_factor* is a finite number in [0.25, 1]."""
    low, high = HEAT_U_FACTOR_RANGE
    if u_factor is None:
        raise ValueError(
            "The INTEGRATED INTENSITY radiant source needs a factor f in "
            f"[{low}, {high}]; there is no default."
        )
    if not (math.isfinite(u_factor) and low <= u_factor <= high):
        raise ValueError(f"U factor must be in [{low}, {high}], got {u_factor!r}")


def total_heat_flux_kw_m2(
    gas_temperature_celsius: float,
    *,
    emissivity: float,
    convective_coefficient: float,
    skin_temperature_celsius: float,
    external_flux_kw_m2: float = 0.0,
) -> float:
    """Return the heat flux to the skin in kW/m2 (Eq. 63.49, spec 016 units).

    q = [eps sigma (T_g^4 - T_s^4) + h (T_g - T_s)] / 1000 + q_ext, with T in
    K. Both terms are in W/m2 and divided together (spec 016); the Handbook
    prints ``/1000`` on the convective term only. Negative below T_s.
    """
    t_gas = gas_temperature_celsius + _KELVIN
    t_skin = skin_temperature_celsius + _KELVIN
    try:
        radiant = emissivity * STEFAN_BOLTZMANN_W_M2_K4 * (t_gas**4 - t_skin**4)
    except OverflowError:
        return math.inf
    convective = convective_coefficient * (t_gas - t_skin)
    return (radiant + convective) / 1000.0 + external_flux_kw_m2


def layer_radiant_flux_kw_m2(
    layer_temperature_celsius: float,
    *,
    view_factor: float,
    layer_emissivity: float,
    skin_temperature_celsius: float,
) -> float:
    """Return the radiant flux from a hot upper layer in kW/m2 (#222, spec 016).

    q_ext = phi eps_L sigma (T_L^4 - T_s^4) / 1000, with T in K: the radiant
    term of Eq. 63.49 (p. 2384) with the layer as source and a view factor.
    Net flux (a sigma T^4 difference), not incident; signed, negative for a
    layer cooler than the skin.
    """
    t_layer = layer_temperature_celsius + _KELVIN
    t_skin = skin_temperature_celsius + _KELVIN
    try:
        radiant = STEFAN_BOLTZMANN_W_M2_K4 * (t_layer**4 - t_skin**4)
    except OverflowError:
        return math.inf
    return view_factor * layer_emissivity * radiant / 1000.0


def total_flux_heat_fed_rate_per_minute(q_kw_m2: float, dose: float) -> float:
    """Return q^1.33 / D in 1/min (Eq. 63.43), with no 2.5 kW/m2 threshold.

    Zero for q <= 0 (gas at or below skin temperature, no recovery) and for a
    non-finite q.
    """
    if not math.isfinite(q_kw_m2) or q_kw_m2 <= 0.0:
        return 0.0
    return float(q_kw_m2**HEAT_FLUX_EXPONENT / dose)


def _check_heat_flux_parameters(
    method: str,
    emissivity: float,
    convective_coefficient: float,
    skin_temperature_celsius: float,
) -> None:
    """Raise ValueError for an unknown method or an invalid flux parameter."""
    if method not in HEAT_FED_METHODS:
        raise ValueError(
            f"Unknown heat FED method {method!r}; expected one of {HEAT_FED_METHODS}"
        )
    if not (math.isfinite(emissivity) and 0.0 <= emissivity <= 1.0):
        raise ValueError(f"Heat emissivity must be in [0, 1], got {emissivity!r}")
    if not (math.isfinite(convective_coefficient) and convective_coefficient >= 0.0):
        raise ValueError(
            "Heat convective coefficient must be finite and >= 0, "
            f"got {convective_coefficient!r}"
        )
    if not math.isfinite(skin_temperature_celsius):
        raise ValueError(
            f"Skin temperature must be finite, got {skin_temperature_celsius!r}"
        )


def _check_radiant_source(radiant_source: str, method: str, u_factor) -> None:
    """Raise ValueError for an unknown source, or a U source without f or flux."""
    if radiant_source not in HEAT_RADIANT_SOURCES:
        raise ValueError(
            f"Unknown heat radiant source {radiant_source!r}; "
            f"expected one of {HEAT_RADIANT_SOURCES}"
        )
    if radiant_source != "integrated-intensity":
        return
    if method != "total-flux":
        raise ValueError(
            "The INTEGRATED INTENSITY radiant source needs the total-flux method."
        )
    _check_u_factor(u_factor)


def _check_layer_parameters(
    regime: str,
    method: str,
    layer_field,
    view_factor: float | None,
    layer_emissivity: float | None,
) -> None:
    """Raise ValueError for an unknown regime or an invalid layer setting."""
    if regime not in HEAT_FLUX_REGIMES:
        raise ValueError(
            f"Unknown heat regime {regime!r}; expected one of {HEAT_FLUX_REGIMES}"
        )
    for name, value in (
        ("view factor", view_factor),
        ("layer emissivity", layer_emissivity),
    ):
        if value is not None and not (math.isfinite(value) and 0.0 <= value <= 1.0):
            raise ValueError(f"Heat {name} must be in [0, 1], got {value!r}")
    if regime != "layer":
        return
    if method != "total-flux":
        raise ValueError("The layer heat regime needs method='total-flux'")
    if layer_field is None:
        raise ValueError("The layer heat regime needs a layer temperature field")
    if view_factor is None or layer_emissivity is None:
        raise ValueError(
            "The layer heat regime needs a view factor and a layer emissivity"
        )


def heat_flux_row_fields(
    heat_fed_model,
    temperature_celsius: float,
    layer_temperature_celsius: float | None = None,
    integrated_intensity_kw_m2: float | None = None,
) -> dict:
    """Return the FED history fields of the total-flux method; ``{}`` otherwise.

    In the layer regime the row also carries ``heat_layer_temperature_c``;
    with the INTEGRATED INTENSITY source it also carries U (#221).
    """
    if getattr(heat_fed_model, "method", "convective") != "total-flux":
        return {}
    if getattr(heat_fed_model, "uses_layer_term", False):
        return {
            "heat_flux_kw_m2": heat_fed_model.heat_flux_kw_m2(
                temperature_celsius, layer_temperature_celsius
            ),
            "heat_layer_temperature_c": layer_temperature_celsius,
        }
    if getattr(heat_fed_model, "radiant_source", "gas") != "integrated-intensity":
        return {"heat_flux_kw_m2": heat_fed_model.heat_flux_kw_m2(temperature_celsius)}
    u = math.nan if integrated_intensity_kw_m2 is None else integrated_intensity_kw_m2
    return {
        "heat_flux_kw_m2": heat_fed_model.heat_flux_kw_m2(
            temperature_celsius, integrated_intensity_kw_m2=u
        ),
        "heat_integrated_intensity_kw_m2": float(u),
    }


@dataclass(frozen=True)
class TenabilityConfig:
    """Runtime tenability rules applied on top of Frantzich smoke-speed.

    The Frantzich--Nilsson extinction--speed law is already handled by
    ``SmokeSpeedModel``.  This config adds three further rules on top
    of it:

    - FIC-driven speed reduction, off by default (``enable_fic_speed``):
      ``v_final = v_frantzich * max(fic_min_factor, 1 - fic_alpha * FIC)``.
      A pyFDS-Evac assumption, source unknown (#147): FDS+Evac has no
      irritant slowdown, so it is opt-in, and Purser's own curve is SFPE
      Handbook Eq. 63.13.  Irritant gases are assumed to slow evacuees
      beyond what pure visibility loss predicts, bounded so no agent falls
      below ``fic_min_factor`` of its Frantzich speed.
    - Binary incapacitation when ``FED_cumulative`` reaches the agent's
      threshold: a per-agent log-normal draw with median
      ``fed_threshold`` in ``probabilistic`` mode, ``fed_threshold``
      itself in ``deterministic`` mode (the FDS+Evac criterion of
      Korhonen 2021 §3.4, with the default 1.0): desired
      speed is driven to zero and the agent remains as a static
      obstacle.
    - Binary heat incapacitation when ``FED_HEAT_cumulative`` reaches the
      heat threshold, tracked as a completely separate running total from
      the gas FED above -- heat and toxic gases incapacitate through
      different mechanisms, so neither SFPE Ch. 63 nor ISO 13571:2012 sums
      them into one dose. The threshold is ``fed_threshold``, as ISO
      13571:2012 asks for one threshold for FED and FEC (§5.4) and chooses
      the heat threshold in the same manner (§8.5); ``heat_fed_threshold``
      overrides it, a departure from ISO. An agent is incapacitated the
      instant *either* threshold is crossed.
    """

    enable_fic_speed: bool = False
    fic_alpha: float = 0.7
    fic_min_factor: float = 0.3
    enable_incapacitation: bool = True
    fed_threshold: float = 1.0
    # In "deterministic" mode (default) every agent uses fed_threshold, the
    # FDS+Evac rule (Korhonen 2021 §3.4). The opt-in "probabilistic" mode
    # treats incapacitation as a population endpoint: each agent draws
    #   D_incap = fed_threshold * exp(susceptibility_sigma * Z), Z ~ N(0, 1),
    # a log-normal with median fed_threshold. sigma = 0.94 fits the NIST TN
    # 1797 / Purser bands (~10/50/88 % incapacitated at FED 0.3/1/3).
    incapacitation_mode: str = "deterministic"
    susceptibility_sigma: float = 0.94
    enable_heat_incapacitation: bool = True
    # None: the heat track uses fed_threshold (ISO 13571:2012 §5.4, §8.5).
    heat_fed_threshold: float | None = None
    # Heat is deterministic by default. SFPE Handbook 5th ed. Ch. 63 gives no
    # population spread for heat tolerance; its only population figures are
    # for radiant lethality (p. 2382). In "probabilistic" mode the heat track
    # uses the same log-normal mechanism as the gas track, and the default
    # sigma 0.94 is borrowed from the gas value, an assumption, not a cited
    # value.
    heat_incapacitation_mode: str = "deterministic"
    heat_susceptibility_sigma: float = 0.94

    @property
    def resolved_heat_fed_threshold(self) -> float:
        """Return the heat threshold: the override, else ``fed_threshold``."""
        if self.heat_fed_threshold is None:
            return self.fed_threshold
        return self.heat_fed_threshold


def _sample_threshold(threshold: float, mode: str, sigma: float, rng) -> float:
    """Draw one log-normal (or flat) incapacitation threshold.

    Shared by the gas and heat FED tracks. Deterministic mode returns
    ``threshold`` for every agent. Probabilistic mode returns a log-normal
    draw with median ``threshold`` and log-scale ``sigma`` (``rng`` is a
    ``random.Random``), so a population of agents reproduces an
    incapacitation band instead of all collapsing at the median.
    """
    if mode == "deterministic":
        return float(threshold)
    return float(threshold) * math.exp(float(sigma) * rng.gauss(0.0, 1.0))


def sample_incapacitation_threshold(config: "TenabilityConfig", rng) -> float:
    """Draw one agent's cumulative-FED (gas) incapacitation threshold.

    See ``_sample_threshold``; deterministic mode returns ``fed_threshold``
    for every agent, probabilistic mode log-normal-draws around it with
    ``susceptibility_sigma``, reproducing the NIST TN 1797 / Purser
    incapacitation bands instead of all agents collapsing at the median.
    """
    return _sample_threshold(
        config.fed_threshold,
        config.incapacitation_mode,
        config.susceptibility_sigma,
        rng,
    )


def sample_heat_incapacitation_threshold(config: "TenabilityConfig", rng) -> float:
    """Draw one agent's cumulative heat-FED incapacitation threshold.

    Same mechanism as ``sample_incapacitation_threshold``, applied to
    ``resolved_heat_fed_threshold``/``heat_incapacitation_mode``/
    ``heat_susceptibility_sigma`` -- an independent draw from the gas
    threshold, since the two tracks are not the same dose.
    """
    return _sample_threshold(
        config.resolved_heat_fed_threshold,
        config.heat_incapacitation_mode,
        config.heat_susceptibility_sigma,
        rng,
    )


@dataclass(frozen=True)
class FedComponents:
    """Per-term breakdown of one FED rate evaluation (all in 1/min).

    Summed per Purser (FDS+Evac guide): total = (co + cn + nox + fld) * hv_co2 + o2.
    Each narcotic/irritant term is reported pre-HV so contributions stack
    cleanly in plots; ``hv_co2`` carries the multiplier separately.
    """

    co_rate_per_min: float
    cn_rate_per_min: float
    nox_rate_per_min: float
    fld_rate_per_min: float
    hv_co2: float
    o2_rate_per_min: float

    @property
    def total_rate_per_min(self) -> float:
        """Return the summed FED rate applying the HV_CO2 multiplier."""
        narcotic_sum = (
            self.co_rate_per_min
            + self.cn_rate_per_min
            + self.nox_rate_per_min
            + self.fld_rate_per_min
        )
        return narcotic_sum * self.hv_co2 + self.o2_rate_per_min


def default_fed_components(
    inputs: DefaultFedInputs,
    *,
    o2_threshold_percent: float = _O2_HYPOXIA_THRESHOLD_PERCENT,
) -> FedComponents:
    """Return the per-term FED rate breakdown for one gas sample."""
    return FedComponents(
        co_rate_per_min=_co_fed_rate_per_minute(
            _co_percent_to_ppm(inputs.co_volume_fraction_percent)
        ),
        cn_rate_per_min=_cn_fed_rate_per_minute(
            inputs.hcn_ppm, inputs.no_ppm, inputs.no2_ppm
        ),
        nox_rate_per_min=_nox_fed_rate_per_minute(inputs.no_ppm, inputs.no2_ppm),
        fld_rate_per_min=_irritant_fld_rate_per_minute(inputs),
        hv_co2=_hyperventilation_factor(inputs.co2_volume_fraction_percent),
        o2_rate_per_min=_o2_hypoxia_rate_per_minute(
            inputs.o2_volume_fraction_percent, o2_threshold_percent
        ),
    )


def default_fed_rate_per_minute(
    inputs: DefaultFedInputs,
    *,
    o2_threshold_percent: float = _O2_HYPOXIA_THRESHOLD_PERCENT,
) -> float:
    """Return the Purser FED accumulation rate in 1/min.

    FED_tot = (FED_CO + FED_CN + FED_NOx + FLD_irr) * HV_CO2 + FED_O2

    Missing gas species default to 0, reducing to the original 3-term
    model (FED_CO * HV_CO2 + FED_O2) when only CO/CO2/O2 are available.
    """
    return default_fed_components(
        inputs, o2_threshold_percent=o2_threshold_percent
    ).total_rate_per_min


def accumulate_default_fed(
    inputs: DefaultFedInputs,
    *,
    duration_s: float,
    initial_fed: float = 0.0,
) -> float:
    """Accumulate FED over a constant-exposure interval in seconds."""

    duration_min = max(0.0, float(duration_s)) / _SECONDS_PER_MINUTE
    return float(initial_fed) + default_fed_rate_per_minute(inputs) * duration_min


def time_to_fed_threshold_s(
    inputs: DefaultFedInputs,
    *,
    threshold: float = 1.0,
    initial_fed: float = 0.0,
) -> float:
    """Return the seconds needed to reach a FED threshold under constant exposure."""

    remaining = float(threshold) - float(initial_fed)
    if remaining <= 0.0:
        return 0.0
    rate_per_min = default_fed_rate_per_minute(inputs)
    if rate_per_min <= 0.0:
        return math.inf
    return (remaining / rate_per_min) * _SECONDS_PER_MINUTE


def accumulate_default_heat_fed(
    inputs: HeatFedInputs,
    *,
    duration_s: float,
    initial_fed: float = 0.0,
    clothing: str = DEFAULT_HEAT_CLOTHING,
) -> float:
    """Accumulate heat FED over a constant-exposure interval in seconds."""

    duration_min = max(0.0, float(duration_s)) / _SECONDS_PER_MINUTE
    rate = default_heat_fed_rate_per_minute(inputs, clothing)
    return float(initial_fed) + rate * duration_min


def time_to_heat_fed_threshold_s(
    inputs: HeatFedInputs,
    *,
    threshold: float = 1.0,
    initial_fed: float = 0.0,
    clothing: str = DEFAULT_HEAT_CLOTHING,
) -> float:
    """Return the seconds needed to reach a heat FED threshold under constant exposure."""

    remaining = float(threshold) - float(initial_fed)
    if remaining <= 0.0:
        return 0.0
    rate_per_min = default_heat_fed_rate_per_minute(inputs, clothing)
    if rate_per_min <= 0.0:
        return math.inf
    return (remaining / rate_per_min) * _SECONDS_PER_MINUTE


class FdsFedField:
    """Sample FED input quantities from FDS slice outputs via fdsreader.

    Required slices: CO, CO2, O2 (volume fractions in [0, 1]).
    Optional slices: HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde.
    Missing optional species contribute 0 to the FED sum.
    """

    # Map from attribute name to FDS quantity name.
    # Volume-fraction slices are stored as fractions [0,1] in FDS;
    # _sample_optional_ppm() multiplies by 1e6 to convert to ppm.
    _OPTIONAL_SPECIES: list[tuple[str, str]] = [
        ("_hcn", "HYDROGEN CYANIDE VOLUME FRACTION"),
        ("_no", "NITRIC OXIDE VOLUME FRACTION"),
        ("_no2", "NITROGEN DIOXIDE VOLUME FRACTION"),
        ("_hcl", "HYDROGEN CHLORIDE VOLUME FRACTION"),
        ("_hbr", "HYDROGEN BROMIDE VOLUME FRACTION"),
        ("_hf", "HYDROGEN FLUORIDE VOLUME FRACTION"),
        ("_so2", "SULFUR DIOXIDE VOLUME FRACTION"),
        ("_acrolein", "ACROLEIN VOLUME FRACTION"),
        ("_formaldehyde", "FORMALDEHYDE VOLUME FRACTION"),
    ]

    def __init__(
        self,
        co_sampler: SliceFieldSampler,
        co2_sampler: SliceFieldSampler,
        o2_sampler: SliceFieldSampler,
        **optional_samplers: SliceFieldSampler,
    ):
        """Store one sampler per gas quantity used by the FED model."""
        self._co = co_sampler
        self._co2 = co2_sampler
        self._o2 = o2_sampler
        self._hcn = optional_samplers.get("hcn")
        self._no = optional_samplers.get("no")
        self._no2 = optional_samplers.get("no2")
        self._hcl = optional_samplers.get("hcl")
        self._hbr = optional_samplers.get("hbr")
        self._hf = optional_samplers.get("hf")
        self._so2 = optional_samplers.get("so2")
        self._acrolein = optional_samplers.get("acrolein")
        self._formaldehyde = optional_samplers.get("formaldehyde")

    @classmethod
    def from_fds(
        cls, fds_dir: str, *, simulation=None, slice_height_m: float | None = 1.6
    ) -> "FdsFedField":
        """Build gas samplers from an FDS case directory.

        Required: CO, CO2, O2 slices.
        Optional: HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde.

        Parameters
        ----------
        simulation : optional
            A pre-loaded ``fdsreader.Simulation`` instance.  When provided
            the expensive directory parse is skipped.
        slice_height_m : optional
            Each species is read from its horizontal slice nearest this
            height (default 1.6 m, FDS+Evac's ``HUMAN_SMOKE_HEIGHT``), as
            ``load_slice_sampler`` selects it.
        """
        if simulation is not None:
            sim = simulation
        else:
            from .fds_sampling import Simulation as _Sim

            if _Sim is None:
                raise ModuleNotFoundError(
                    "fdsreader is required to load FED fields from FDS data."
                )
            sim = _Sim(str(fds_dir))

        def sampler(quantity):
            return load_slice_sampler(
                fds_dir, quantity, simulation=sim, slice_height_m=slice_height_m
            )

        co = sampler("CARBON MONOXIDE VOLUME FRACTION")
        co2 = sampler("CARBON DIOXIDE VOLUME FRACTION")
        o2 = sampler("OXYGEN VOLUME FRACTION")

        optional = {}
        for attr, quantity in cls._OPTIONAL_SPECIES:
            if not sim.slices.filter_by_quantity(quantity):
                continue
            optional[attr.lstrip("_")] = sampler(quantity)
        field = cls(co, co2, o2, **optional)
        field.fds_dir = str(fds_dir)
        return field

    def _sample_optional_ppm(
        self, sampler: SliceFieldSampler | None, time_s: float, x: float, y: float
    ) -> float:
        """Sample an optional species; return 0 if sampler is absent or point is outside."""
        if sampler is None:
            return 0.0
        try:
            return 1e6 * sampler.sample(time_s, x, y)
        except ValueError:
            return 0.0

    def sample_inputs(self, time_s: float, x: float, y: float) -> DefaultFedInputs:
        """Return FED gas inputs at one time and x/y point."""
        try:
            co_pct = 100.0 * self._co.sample(time_s, x, y)
            co2_pct = 100.0 * self._co2.sample(time_s, x, y)
            o2_pct = 100.0 * self._o2.sample(time_s, x, y)
        except ValueError:
            return DefaultFedInputs()
        return DefaultFedInputs(
            co_volume_fraction_percent=co_pct,
            co2_volume_fraction_percent=co2_pct,
            o2_volume_fraction_percent=o2_pct,
            hcn_ppm=self._sample_optional_ppm(self._hcn, time_s, x, y),
            no_ppm=self._sample_optional_ppm(self._no, time_s, x, y),
            no2_ppm=self._sample_optional_ppm(self._no2, time_s, x, y),
            hcl_ppm=self._sample_optional_ppm(self._hcl, time_s, x, y),
            hbr_ppm=self._sample_optional_ppm(self._hbr, time_s, x, y),
            hf_ppm=self._sample_optional_ppm(self._hf, time_s, x, y),
            so2_ppm=self._sample_optional_ppm(self._so2, time_s, x, y),
            acrolein_ppm=self._sample_optional_ppm(self._acrolein, time_s, x, y),
            formaldehyde_ppm=self._sample_optional_ppm(
                self._formaldehyde, time_s, x, y
            ),
        )


class DefaultFedModel:
    """Combine sampled gas fields with the default FDS+Evac FED equations."""

    def __init__(self, field: FdsFedField, config: DefaultFedConfig):
        """Store the gas field sampler and FED runtime settings."""
        self.field = field
        self.config = config
        self._warned_zero_co2 = False

    def sample_inputs(self, time_s: float, x: float, y: float) -> DefaultFedInputs:
        """Return the FED gas inputs at one time and x/y point."""
        inputs = self.field.sample_inputs(time_s, x, y)
        self._warn_zero_co2(inputs, time_s, x, y)
        return inputs

    def _warn_zero_co2(
        self, inputs: DefaultFedInputs, time_s: float, x: float, y: float
    ) -> None:
        """Warn once when CO is present but CO2 is exactly zero.

        In fire smoke CO comes with CO2, and FDS's ambient air carries some.
        Zero CO2 with CO points to a deck with a CO2-free background; the
        hyperventilation factor is then 1 there (FDS convention).
        """
        if self._warned_zero_co2:
            return
        co = inputs.co_volume_fraction_percent
        if not math.isfinite(co) or co <= 0.0:
            return
        if inputs.co2_volume_fraction_percent != 0.0:
            return
        self._warned_zero_co2 = True
        _logger.warning(
            "CO is present but CO2 is zero at t=%.1f s, (%.2f, %.2f): the "
            "CO2 hyperventilation factor is 1 there. Check that the FDS deck "
            "has ambient CO2 and a CO2 slice.",
            time_s,
            x,
            y,
        )

    def sample_rate(
        self, time_s: float, x: float, y: float
    ) -> tuple[DefaultFedInputs, float]:
        """Return both the sampled inputs and their FED rate in 1/min."""
        inputs = self.sample_inputs(time_s, x, y)
        return inputs, default_fed_rate_per_minute(
            inputs, o2_threshold_percent=self.config.o2_threshold_percent
        )

    def sample_components(
        self, time_s: float, x: float, y: float
    ) -> tuple[DefaultFedInputs, FedComponents]:
        """Return the sampled inputs together with the per-term FED breakdown."""
        inputs = self.sample_inputs(time_s, x, y)
        return inputs, default_fed_components(
            inputs, o2_threshold_percent=self.config.o2_threshold_percent
        )

    def advance(
        self,
        time_s: float,
        x: float,
        y: float,
        *,
        dt_s: float,
        current_fed: float,
    ) -> tuple[DefaultFedInputs, float, float]:
        """Advance cumulative FED by one simulation interval."""
        inputs, rate_per_min = self.sample_rate(time_s, x, y)
        updated = (
            float(current_fed)
            + rate_per_min * max(0.0, float(dt_s)) / _SECONDS_PER_MINUTE
        )
        return inputs, rate_per_min, updated

    def advance_with_components(
        self,
        time_s: float,
        x: float,
        y: float,
        *,
        dt_s: float,
        current_fed: float,
    ) -> tuple[DefaultFedInputs, FedComponents, float]:
        """Advance cumulative FED and return the per-term rate breakdown."""
        inputs, components = self.sample_components(time_s, x, y)
        updated = (
            float(current_fed)
            + components.total_rate_per_min
            * max(0.0, float(dt_s))
            / _SECONDS_PER_MINUTE
        )
        return inputs, components, updated


class FdsHeatField:
    """Sample gas-phase temperature from FDS slice output via fdsreader.

    Required slice: TEMPERATURE. Unlike ``FdsFedField``, this goes through
    ``load_slice_sampler`` so a mismatched slice height triggers the same
    warning the extinction/smoke-speed path already gets -- ``FdsFedField``
    bypasses that check entirely (raw ``filter_by_quantity(...)[0]``, no
    height-matching), a known blind spot this project has been bitten by
    twice before (the O2 hypoxia rate bug, the conflicting ``&INIT`` bug);
    the new heat sampler should not repeat it.
    """

    def __init__(
        self,
        sampler: SliceFieldSampler,
        intensity_sampler: SliceFieldSampler | None = None,
    ):
        """Wrap the TEMPERATURE and, optionally, INTEGRATED INTENSITY samplers."""
        self._sampler = sampler
        self._intensity_sampler = intensity_sampler

    @classmethod
    def from_fds(
        cls,
        fds_dir: str,
        *,
        slice_height_m: float = 1.6,
        simulation=None,
        integrated_intensity: bool = False,
    ) -> "FdsHeatField":
        """Load the TEMPERATURE slice from an FDS case directory.

        With *integrated_intensity* also the INTEGRATED INTENSITY slice
        (#221), at the same height.
        """
        sampler = load_slice_sampler(
            fds_dir,
            "TEMPERATURE",
            simulation=simulation,
            slice_height_m=slice_height_m,
        )
        intensity_sampler = None
        if integrated_intensity:
            intensity_sampler = load_slice_sampler(
                fds_dir,
                "INTEGRATED INTENSITY",
                simulation=simulation,
                slice_height_m=slice_height_m,
            )
            _check_same_slice_height(sampler, intensity_sampler, fds_dir)
        field = cls(sampler, intensity_sampler=intensity_sampler)
        field.fds_dir = str(fds_dir)
        return field

    def sample_inputs(self, time_s: float, x: float, y: float) -> HeatFedInputs:
        """Return the heat FED gas-temperature input at one time and x/y point.

        FDS's TEMPERATURE quantity is natively in degrees Celsius, so unlike
        the gas volume-fraction slices sampled by ``FdsFedField`` this needs
        no unit conversion.
        """
        temperature_celsius = _sample_or_none(self._sampler, time_s, x, y)
        if self._intensity_sampler is None:
            if temperature_celsius is None:
                return HeatFedInputs()
            return HeatFedInputs(temperature_celsius=temperature_celsius)
        intensity = _sample_or_none(self._intensity_sampler, time_s, x, y)
        _check_same_coverage(temperature_celsius, intensity, x, y)
        if temperature_celsius is None:
            # Outside the FDS domain: no U, so no radiant dose.
            return HeatFedInputs(integrated_intensity_kw_m2=math.nan)
        return HeatFedInputs(
            temperature_celsius=temperature_celsius,
            integrated_intensity_kw_m2=intensity,
        )


def _sample_or_none(sampler: SliceFieldSampler, time_s: float, x, y) -> float | None:
    """Return the sampled value, or None outside the slice."""
    try:
        return sampler.sample(time_s, x, y)
    except ValueError:
        return None


def _check_same_coverage(temperature: float | None, intensity: float | None, x, y):
    """Raise ValueError when only one of TEMPERATURE and U covers the point.

    U is a required input of this source: a hole in one slice under a valid
    sample of the other must not turn into a zero or partial dose.
    """
    if (temperature is None) == (intensity is None):
        return
    have, missing = ("TEMPERATURE", "INTEGRATED INTENSITY")
    if temperature is None:
        have, missing = missing, have
    raise ValueError(
        f"Point ({x}, {y}) lies in the {have} slice but outside the {missing} "
        "slice; the heat FED needs both at every agent."
    )


def _check_same_slice_height(
    temperature: SliceFieldSampler, intensity: SliceFieldSampler, fds_dir: str
) -> None:
    """Raise ValueError unless both slices lie at the same z.

    Each slice is chosen as the one nearest the requested height, so the two
    can differ; radiation and convection must come from one height.
    """
    z_t = _slice_z_mid(temperature._slice)
    z_u = _slice_z_mid(intensity._slice)
    if abs(z_t - z_u) <= HEAT_SLICE_Z_TOLERANCE_M:
        return
    raise ValueError(
        f"The TEMPERATURE slice in {fds_dir} is at z={z_t:.3f} m but the "
        f"nearest INTEGRATED INTENSITY slice is at z={z_u:.3f} m; the heat "
        "FED needs both at the same height. Add "
        f"`&SLCF PBZ={z_t:g}, QUANTITY='INTEGRATED INTENSITY' /` to the case."
    )


class DefaultHeatFedModel:
    """Combine sampled gas-phase temperature with a heat FED law.

    With ``method="convective"`` (default): without *endpoint* the rate is
    the ISO 13571:2012 law of *clothing*, Eq. (9) for ``clothed`` (default)
    or Eq. (10) = SFPE Eq. 63.44 for ``unclothed``; with *endpoint* (a key of
    ``HEAT_ENDPOINTS``) it is that endpoint's convective law of SFPE Ch. 63,
    and *clothing* has no effect. With ``method="total-flux"`` the rate is
    q^1.33 / D (Eqs. 63.49 and 63.43, spec 016), D the radiant dose of
    *endpoint*, or of ``fatal`` without one; the convective laws are not added.
    With ``radiant_source="integrated-intensity"`` (total-flux only, #221)
    the radiant term is the excess f (U - 4 sigma T_s^4) over an isotropic
    field at the skin temperature instead of the gas term, and *u_factor* f
    in [0.25, 1] is required. Outside the FDS domain U is
    NaN and the rate is zero; the first such sample logs one warning.

    *regime* (total-flux only, spec 016): ``"smoke"`` (default) applies
    Eq. 63.49 at the head. ``"layer"`` takes the head to be in clear air below
    a hot layer: convection at the head plus ``layer_radiant_flux_kw_m2`` from
    *layer_field*, with no eps sigma term of the gas at the head, so the two
    radiant terms are never added together. *view_factor* and
    *layer_emissivity* have no sourced values and no defaults.

    With both the layer regime and the INTEGRATED INTENSITY source, U
    supplies the radiant term: FDS's radiation solution already contains the
    layer's emission, so the layer term is not added (it would count that
    emission twice), and one warning is logged.
    """

    def __init__(
        self,
        field: FdsHeatField,
        config: DefaultFedConfig,
        endpoint: str | None = None,
        method: str = "convective",
        emissivity: float = DEFAULT_HEAT_EMISSIVITY,
        convective_coefficient: float = DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
        skin_temperature_celsius: float = DEFAULT_HEAT_SKIN_TEMPERATURE_C,
        radiant_source: str = "gas",
        u_factor: float | None = None,
        regime: str = "smoke",
        layer_field: FdsHeatField | None = None,
        view_factor: float | None = None,
        layer_emissivity: float | None = None,
        layer_height_m: float | None = None,
        clothing: str = DEFAULT_HEAT_CLOTHING,
    ):
        """Store the temperature field sampler, FED settings and heat law."""
        if endpoint is not None and endpoint not in HEAT_ENDPOINTS:
            raise ValueError(
                f"Unknown heat endpoint {endpoint!r}; "
                f"expected one of {sorted(HEAT_ENDPOINTS)}"
            )
        _check_heat_clothing(clothing)
        _check_heat_flux_parameters(
            method, emissivity, convective_coefficient, skin_temperature_celsius
        )
        _check_radiant_source(radiant_source, method, u_factor)
        _check_layer_parameters(
            regime, method, layer_field, view_factor, layer_emissivity
        )
        self.field = field
        self.config = config
        self.endpoint = endpoint
        self.clothing = clothing
        self.method = method
        self.emissivity = emissivity
        self.convective_coefficient = convective_coefficient
        self.skin_temperature_celsius = skin_temperature_celsius
        self.radiant_source = radiant_source
        self.u_factor = u_factor
        self.regime = regime
        # The layer term is used only when U is not the radiant source.
        self.uses_layer_term = (
            regime == "layer" and radiant_source != "integrated-intensity"
        )
        if regime == "layer" and not self.uses_layer_term:
            _logger.warning(
                "--heat-regime layer and --heat-radiant-source "
                "integrated-intensity are both set: U already contains the "
                "layer's emission, so it supplies the radiant term and the "
                "layer term is not added."
            )
        self.layer_field = layer_field if self.uses_layer_term else None
        self.view_factor = view_factor
        self.layer_emissivity = layer_emissivity
        self.layer_height_m = layer_height_m
        self._warned_missing_intensity = False

    def convective_clothing(self) -> str | None:
        """Return the clothing of the ISO law in use, None under another law."""
        if self.method != "convective" or self.endpoint is not None:
            return None
        return self.clothing

    def heat_flux_parameters(self) -> dict[str, object]:
        """Return the flux parameters for the run manifest."""
        params: dict[str, object] = {
            "emissivity": self.emissivity,
            "convective_coefficient": self.convective_coefficient,
            "skin_temperature_celsius": self.skin_temperature_celsius,
            "radiant_dose": HEAT_ENDPOINTS[self.endpoint or "fatal"].radiant_dose,
            "assumed": list(HEAT_FLUX_ASSUMED_PARAMETERS),
        }
        if self.regime == "layer":
            params.update(
                regime=self.regime,
                view_factor=self.view_factor,
                layer_emissivity=self.layer_emissivity,
                layer_height_m=self.layer_height_m,
                layer_term=self.uses_layer_term,
            )
        if self.radiant_source != "integrated-intensity":
            return params
        # eps is not used with this source; f is user-given, not assumed.
        params["assumed"] = [
            name for name in HEAT_FLUX_ASSUMED_PARAMETERS if name != "emissivity"
        ]
        params["radiant_source"] = self.radiant_source
        params["u_factor"] = self.u_factor
        params["radiant_flux"] = "excess"
        return params

    def heat_flux_kw_m2(
        self,
        temperature_celsius: float,
        layer_temperature_celsius: float | None = None,
        integrated_intensity_kw_m2: float | None = None,
    ) -> float:
        """Return the total-flux q in kW/m2 for one gas temperature.

        In the layer regime: h (T_g - T_s) / 1000 + q_ext, no eps sigma term
        of the gas at the head. With the INTEGRATED INTENSITY source,
        q = f (U - 4 sigma T_s^4 / 1000) + h (T_g - T_s) / 1000 (excess over
        an isotropic field at the skin temperature, maintainer decision on
        #221): U already holds the gas emission, so the eps term is not added.
        """
        if self.uses_layer_term:
            return self._layer_heat_flux_kw_m2(
                temperature_celsius, layer_temperature_celsius
            )
        if self.radiant_source != "integrated-intensity":
            return total_heat_flux_kw_m2(
                temperature_celsius,
                emissivity=self.emissivity,
                convective_coefficient=self.convective_coefficient,
                skin_temperature_celsius=self.skin_temperature_celsius,
            )
        u = (
            math.nan
            if integrated_intensity_kw_m2 is None
            else integrated_intensity_kw_m2
        )
        u_skin = (
            4.0
            * STEFAN_BOLTZMANN_W_M2_K4
            * (self.skin_temperature_celsius + _KELVIN) ** 4
            / 1000.0
        )
        return total_heat_flux_kw_m2(
            temperature_celsius,
            emissivity=0.0,
            convective_coefficient=self.convective_coefficient,
            skin_temperature_celsius=self.skin_temperature_celsius,
            external_flux_kw_m2=radiant_flux_from_integrated_intensity_kw_m2(
                u - u_skin, self.u_factor
            ),
        )

    def _layer_heat_flux_kw_m2(
        self, temperature_celsius: float, layer_temperature_celsius: float | None
    ) -> float:
        """Return h (T_g - T_s) / 1000 plus the layer term, in kW/m2."""
        if layer_temperature_celsius is None:
            return math.nan
        q_ext = layer_radiant_flux_kw_m2(
            layer_temperature_celsius,
            view_factor=self.view_factor,
            layer_emissivity=self.layer_emissivity,
            skin_temperature_celsius=self.skin_temperature_celsius,
        )
        return total_heat_flux_kw_m2(
            temperature_celsius,
            emissivity=0.0,
            convective_coefficient=self.convective_coefficient,
            skin_temperature_celsius=self.skin_temperature_celsius,
            external_flux_kw_m2=q_ext,
        )

    def _total_flux_rate(self, inputs: HeatFedInputs) -> float:
        """Return q^1.33 / D in 1/min; fatal D without an endpoint."""
        dose = HEAT_ENDPOINTS[self.endpoint or "fatal"].radiant_dose
        q = self.heat_flux_kw_m2(
            inputs.temperature_celsius,
            inputs.layer_temperature_celsius,
            integrated_intensity_kw_m2=inputs.integrated_intensity_kw_m2,
        )
        return total_flux_heat_fed_rate_per_minute(q, dose)

    def sample_inputs(self, time_s: float, x: float, y: float) -> HeatFedInputs:
        """Return the heat FED input at one time and x/y point.

        In the layer regime it also carries the layer temperature, sampled
        the same way as the temperature at the head.
        """
        inputs = self.field.sample_inputs(time_s, x, y)
        if self.layer_field is None:
            return inputs
        # Assumption, unsourced: where the layer slice has no value,
        # HeatFedInputs falls back to 20 C. Below the skin temperature this
        # gives a small negative (cooling) layer flux, about
        # -0.09 phi eps_L kW/m2 at T_s = 35 C.
        layer = self.layer_field.sample_inputs(time_s, x, y).temperature_celsius
        return replace(inputs, layer_temperature_celsius=float(layer))

    def sample_rate(
        self, time_s: float, x: float, y: float
    ) -> tuple[HeatFedInputs, float]:
        """Return both the sampled input and its heat FED rate in 1/min."""
        inputs = self.sample_inputs(time_s, x, y)
        if self.method == "total-flux":
            self._warn_missing_intensity_once(inputs)
            return inputs, self._total_flux_rate(inputs)
        if self.endpoint is None:
            return inputs, default_heat_fed_rate_per_minute(inputs, self.clothing)
        return inputs, endpoint_heat_fed_rate_per_minute(
            inputs.temperature_celsius, HEAT_ENDPOINTS[self.endpoint]
        )

    def _warn_missing_intensity_once(self, inputs: HeatFedInputs) -> None:
        """Log once per model when U is missing, e.g. outside the FDS domain."""
        if self.radiant_source != "integrated-intensity":
            return
        if self._warned_missing_intensity:
            return
        u = inputs.integrated_intensity_kw_m2
        if u is not None and math.isfinite(u):
            return
        self._warned_missing_intensity = True
        _logger.warning(
            "An agent is outside the INTEGRATED INTENSITY slice (outside the "
            "FDS domain) or U is not finite: its heat dose rate is zero there, "
            "and U and q read NaN in the FED history. Logged once per run."
        )

    def advance(
        self,
        time_s: float,
        x: float,
        y: float,
        *,
        dt_s: float,
        current_fed: float,
    ) -> tuple[HeatFedInputs, float, float]:
        """Advance cumulative heat FED by one simulation interval."""
        inputs, rate_per_min = self.sample_rate(time_s, x, y)
        updated = (
            float(current_fed)
            + rate_per_min * max(0.0, float(dt_s)) / _SECONDS_PER_MINUTE
        )
        return inputs, rate_per_min, updated
