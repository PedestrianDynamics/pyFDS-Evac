"""Default FDS+Evac FED equations and FDS-backed gas samplers."""

import math
from dataclasses import dataclass

from .fds_sampling import SliceFieldSampler, load_slice_sampler

_SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class DefaultFedInputs:
    """Store gas concentrations for the ISO 13571 FED model.

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

    fds_dir: str
    update_interval_s: float = 1.0
    slice_height_m: float = 2.0


def _co_percent_to_ppm(co_volume_fraction_percent: float) -> float:
    """Convert CO from volume percent to ppm for the FED equation."""
    return max(0.0, float(co_volume_fraction_percent)) * 10000.0


def _co_fed_rate_per_minute(co_ppm: float) -> float:
    """Return the CO FED contribution in 1/min from guide Eq. 13."""

    if not math.isfinite(co_ppm) or co_ppm <= 0.0:
        return 0.0
    return 2.764e-5 * (co_ppm**1.036)


def _hyperventilation_factor(co2_percent: float) -> float:
    """Return the CO2 hyperventilation factor from guide Eq. 19."""

    if not math.isfinite(co2_percent):
        co2_percent = 0.0
    co2_percent = max(0.0, float(co2_percent))
    return math.exp(0.1903 * co2_percent + 2.0004) / 7.1


_O2_HYPOXIA_THRESHOLD_PERCENT: float = 19.5
"""O2 concentration above which hypoxia does not contribute to FED.

At ambient O2 (20.9 %) the SFPE Eq. 18 denominator is non-zero, so the
rate is tiny but finite — accumulating over a long simulation (or when
the agent is outside the FDS domain and O2 defaults to 20.9 %) it
produces spurious FED drift.  OSHA defines the safe lower limit for
working conditions as 19.5 %; below this value hypoxia is a genuine
hazard.  Pathfinder uses the same threshold (default 19.5 %) to prevent
misleading accumulation under safe ambient conditions.
"""


def _o2_hypoxia_rate_per_minute(o2_percent: float) -> float:
    """Return the O2 hypoxia FED contribution in 1/min from guide Eq. 18.

    t_incap [min] = exp(8.13 - 0.54 * (20.9 - C_O2%))   (Purser / FDS Tech Ref)
    rate [1/min]  = 1 / t_incap

    Returns 0 when O2 is at or above ``_O2_HYPOXIA_THRESHOLD_PERCENT``
    (default 19.5 %) to prevent spurious accumulation under safe ambient
    conditions.
    """

    if not math.isfinite(o2_percent):
        o2_percent = 20.9
    if float(o2_percent) >= _O2_HYPOXIA_THRESHOLD_PERCENT:
        return 0.0
    t_incap_min = math.exp(8.13 - 0.54 * (20.9 - float(o2_percent)))
    if t_incap_min <= 0.0:
        return 0.0
    return 1.0 / t_incap_min


def _cn_fed_rate_per_minute(hcn_ppm: float, no2_ppm: float) -> float:
    """Return the CN narcosis FED contribution in 1/min (guide Eq. 14-15).

    C_CN = C_HCN - C_NO2 (NO2 has a protective effect on HCN toxicity).
    Rate = exp(C_CN/43)/220 - 0.0045.
    """
    c_cn = max(0.0, float(hcn_ppm) - float(no2_ppm))
    if not math.isfinite(c_cn) or c_cn <= 0.0:
        return 0.0
    rate = math.exp(c_cn / 43.0) / 220.0 - 0.0045
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
    """Return the irritant FLD contribution in 1/min (ISO 13571).

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
    """Store gas-phase temperature for the ISO TS 13571 heat FED model.

    Tracked independently of ``DefaultFedInputs`` -- heat and toxic gases
    incapacitate through different physiological mechanisms (thermal injury
    vs. asphyxiation), so ISO 13571 keeps their doses as two separate running
    totals rather than summing them (see ``TenabilityConfig``).
    """

    temperature_celsius: float = 20.0


def _heat_fed_rate_per_minute(temperature_celsius: float) -> float:
    """Return the convective-heat FED contribution in 1/min (ISO TS 13571 eq. 5).

    rate [1/min] = T[deg C] ** 3.4 / 5e7

    Not in the FDS+Evac guide like the other terms in this module -- this is
    ISO TS 13571 eq. 5, scoped to convective heat from elevated gas
    temperature only (radiant heat is a separate, unmodelled term). Already
    negligible at ambient temperature, so no floor is applied beyond the
    domain guard.
    """
    if not math.isfinite(temperature_celsius) or temperature_celsius <= 0.0:
        return 0.0
    return (temperature_celsius**3.4) / 5e7


def default_heat_fed_rate_per_minute(inputs: HeatFedInputs) -> float:
    """Return the ISO TS 13571 heat FED accumulation rate in 1/min."""
    return _heat_fed_rate_per_minute(inputs.temperature_celsius)


@dataclass(frozen=True)
class TenabilityConfig:
    """Runtime tenability rules applied on top of Frantzich smoke-speed.

    The Frantzich--Nilsson extinction--speed law is already handled by
    ``SmokeSpeedModel``.  This config adds two further Purser/FDS+Evac
    rules on top of it:

    - FIC-driven speed reduction: ``v_final = v_frantzich * max(
      fic_min_factor, 1 - fic_alpha * FIC)``.  Irritant gases are
      assumed to slow evacuees beyond what pure visibility loss
      predicts, bounded so no agent falls below ``fic_min_factor`` of
      its Frantzich speed.
    - Binary incapacitation when ``FED_cumulative >= fed_threshold``,
      matching the FDS+Evac criterion of Korhonen 2021 §3.4: desired
      speed is driven to zero and the agent remains as a static
      obstacle.
    - Binary heat incapacitation when ``FED_HEAT_cumulative >=
      heat_fed_threshold`` (ISO TS 13571 eq. 5), tracked as a completely
      separate running total from the gas ``fed_threshold`` above -- heat
      and toxic gases incapacitate through different mechanisms, so ISO
      13571 does not sum them into one dose. An agent is incapacitated the
      instant *either* threshold is crossed.
    """

    enable_fic_speed: bool = True
    fic_alpha: float = 0.7
    fic_min_factor: float = 0.3
    enable_incapacitation: bool = True
    fed_threshold: float = 1.0
    # Incapacitation is a population endpoint, not a per-individual constant.
    # In "probabilistic" mode (default) each agent draws its own threshold
    #   D_incap = fed_threshold * exp(susceptibility_sigma * Z), Z ~ N(0, 1),
    # a log-normal with median fed_threshold. sigma = 0.94 fits the NIST TN
    # 1797 / Purser bands (~10/50/88 % incapacitated at FED 0.3/1/3). In
    # "deterministic" mode every agent uses fed_threshold (the legacy rule).
    incapacitation_mode: str = "probabilistic"
    susceptibility_sigma: float = 0.94
    enable_heat_incapacitation: bool = True
    heat_fed_threshold: float = 1.0
    # Same log-normal mechanism as susceptibility_sigma above, applied to the
    # independent heat FED track. Unlike the gas sigma (NIST TN 1797-backed),
    # there is no published population-variance data for heat incapacitation;
    # reusing 0.94 is a starting assumption, not a cited value.
    heat_incapacitation_mode: str = "probabilistic"
    heat_susceptibility_sigma: float = 0.94


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
        config.fed_threshold, config.incapacitation_mode, config.susceptibility_sigma, rng
    )


def sample_heat_incapacitation_threshold(config: "TenabilityConfig", rng) -> float:
    """Draw one agent's cumulative heat-FED incapacitation threshold.

    Same mechanism as ``sample_incapacitation_threshold``, applied to
    ``heat_fed_threshold``/``heat_incapacitation_mode``/
    ``heat_susceptibility_sigma`` -- an independent draw from the gas
    threshold, since the two tracks are not the same dose.
    """
    return _sample_threshold(
        config.heat_fed_threshold,
        config.heat_incapacitation_mode,
        config.heat_susceptibility_sigma,
        rng,
    )


@dataclass(frozen=True)
class FedComponents:
    """Per-term breakdown of one FED rate evaluation (all in 1/min).

    Summed per ISO 13571: total = (co + cn + nox + fld) * hv_co2 + o2.
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


def default_fed_components(inputs: DefaultFedInputs) -> FedComponents:
    """Return the per-term FED rate breakdown for one gas sample."""
    return FedComponents(
        co_rate_per_min=_co_fed_rate_per_minute(
            _co_percent_to_ppm(inputs.co_volume_fraction_percent)
        ),
        cn_rate_per_min=_cn_fed_rate_per_minute(inputs.hcn_ppm, inputs.no2_ppm),
        nox_rate_per_min=_nox_fed_rate_per_minute(inputs.no_ppm, inputs.no2_ppm),
        fld_rate_per_min=_irritant_fld_rate_per_minute(inputs),
        hv_co2=_hyperventilation_factor(inputs.co2_volume_fraction_percent),
        o2_rate_per_min=_o2_hypoxia_rate_per_minute(inputs.o2_volume_fraction_percent),
    )


def default_fed_rate_per_minute(inputs: DefaultFedInputs) -> float:
    """Return the full ISO 13571 FED accumulation rate in 1/min.

    FED_tot = (FED_CO + FED_CN + FED_NOx + FLD_irr) * HV_CO2 + FED_O2

    Missing gas species default to 0, reducing to the original 3-term
    model (FED_CO * HV_CO2 + FED_O2) when only CO/CO2/O2 are available.
    """
    return default_fed_components(inputs).total_rate_per_min


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
) -> float:
    """Accumulate heat FED over a constant-exposure interval in seconds."""

    duration_min = max(0.0, float(duration_s)) / _SECONDS_PER_MINUTE
    return float(initial_fed) + default_heat_fed_rate_per_minute(inputs) * duration_min


def time_to_heat_fed_threshold_s(
    inputs: HeatFedInputs,
    *,
    threshold: float = 1.0,
    initial_fed: float = 0.0,
) -> float:
    """Return the seconds needed to reach a heat FED threshold under constant exposure."""

    remaining = float(threshold) - float(initial_fed)
    if remaining <= 0.0:
        return 0.0
    rate_per_min = default_heat_fed_rate_per_minute(inputs)
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
    def from_fds(cls, fds_dir: str, *, simulation=None) -> "FdsFedField":
        """Build gas samplers from an FDS case directory.

        Required: CO, CO2, O2 slices.
        Optional: HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde.

        Parameters
        ----------
        simulation : optional
            A pre-loaded ``fdsreader.Simulation`` instance.  When provided
            the expensive directory parse is skipped.
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
        co_slice = sim.slices.filter_by_quantity("CARBON MONOXIDE VOLUME FRACTION")[0]
        co2_slice = sim.slices.filter_by_quantity("CARBON DIOXIDE VOLUME FRACTION")[0]
        o2_slice = sim.slices.filter_by_quantity("OXYGEN VOLUME FRACTION")[0]

        optional = {}
        for attr, quantity in cls._OPTIONAL_SPECIES:
            key = attr.lstrip("_")
            matches = sim.slices.filter_by_quantity(quantity)
            if matches:
                optional[key] = SliceFieldSampler(matches[0])
        return cls(
            SliceFieldSampler(co_slice),
            SliceFieldSampler(co2_slice),
            SliceFieldSampler(o2_slice),
            **optional,
        )

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

    def sample_inputs(self, time_s: float, x: float, y: float) -> DefaultFedInputs:
        """Return the FED gas inputs at one time and x/y point."""
        return self.field.sample_inputs(time_s, x, y)

    def sample_rate(
        self, time_s: float, x: float, y: float
    ) -> tuple[DefaultFedInputs, float]:
        """Return both the sampled inputs and their FED rate in 1/min."""
        inputs = self.sample_inputs(time_s, x, y)
        return inputs, default_fed_rate_per_minute(inputs)

    def sample_components(
        self, time_s: float, x: float, y: float
    ) -> tuple[DefaultFedInputs, FedComponents]:
        """Return the sampled inputs together with the per-term FED breakdown."""
        inputs = self.sample_inputs(time_s, x, y)
        return inputs, default_fed_components(inputs)

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

    def __init__(self, sampler: SliceFieldSampler):
        """Wrap a ``SliceFieldSampler`` for the TEMPERATURE slice."""
        self._sampler = sampler

    @classmethod
    def from_fds(
        cls,
        fds_dir: str,
        *,
        slice_height_m: float = 2.0,
        simulation=None,
    ) -> "FdsHeatField":
        """Load the TEMPERATURE slice from an FDS case directory."""
        sampler = load_slice_sampler(
            fds_dir,
            "TEMPERATURE",
            simulation=simulation,
            slice_height_m=slice_height_m,
        )
        return cls(sampler)

    def sample_inputs(self, time_s: float, x: float, y: float) -> HeatFedInputs:
        """Return the heat FED gas-temperature input at one time and x/y point.

        FDS's TEMPERATURE quantity is natively in degrees Celsius, so unlike
        the gas volume-fraction slices sampled by ``FdsFedField`` this needs
        no unit conversion.
        """
        try:
            temperature_celsius = self._sampler.sample(time_s, x, y)
        except ValueError:
            return HeatFedInputs()
        return HeatFedInputs(temperature_celsius=temperature_celsius)


class DefaultHeatFedModel:
    """Combine sampled gas-phase temperature with the ISO TS 13571 heat FED equation."""

    def __init__(self, field: FdsHeatField, config: DefaultFedConfig):
        """Store the temperature field sampler and FED runtime settings."""
        self.field = field
        self.config = config

    def sample_inputs(self, time_s: float, x: float, y: float) -> HeatFedInputs:
        """Return the heat FED input at one time and x/y point."""
        return self.field.sample_inputs(time_s, x, y)

    def sample_rate(
        self, time_s: float, x: float, y: float
    ) -> tuple[HeatFedInputs, float]:
        """Return both the sampled input and its heat FED rate in 1/min."""
        inputs = self.sample_inputs(time_s, x, y)
        return inputs, default_heat_fed_rate_per_minute(inputs)

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
