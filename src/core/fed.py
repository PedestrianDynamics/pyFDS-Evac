"""Default FDS+Evac FED equations and FDS-backed gas samplers."""

from dataclasses import dataclass
import math

try:
    from fdsreader import Simulation
except ModuleNotFoundError:
    Simulation = None


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


def _o2_hypoxia_rate_per_minute(o2_percent: float) -> float:
    """Return the O2 hypoxia FED contribution in 1/min from guide Eq. 18."""

    if not math.isfinite(o2_percent):
        o2_percent = 20.9
    denominator = 60.0 * math.exp(8.13 - 0.54 * (20.9 - float(o2_percent)))
    if denominator <= 0.0:
        return 0.0
    return 1.0 / denominator


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


def default_fed_rate_per_minute(inputs: DefaultFedInputs) -> float:
    """Return the full ISO 13571 FED accumulation rate in 1/min.

    FED_tot = (FED_CO + FED_CN + FED_NOx + FLD_irr) * HV_CO2 + FED_O2

    Missing gas species default to 0, reducing to the original 3-term
    model (FED_CO * HV_CO2 + FED_O2) when only CO/CO2/O2 are available.
    """
    co_rate = _co_fed_rate_per_minute(
        _co_percent_to_ppm(inputs.co_volume_fraction_percent)
    )
    cn_rate = _cn_fed_rate_per_minute(inputs.hcn_ppm, inputs.no2_ppm)
    nox_rate = _nox_fed_rate_per_minute(inputs.no_ppm, inputs.no2_ppm)
    fld_irr = _irritant_fld_rate_per_minute(inputs)
    hv_co2 = _hyperventilation_factor(inputs.co2_volume_fraction_percent)
    o2_rate = _o2_hypoxia_rate_per_minute(inputs.o2_volume_fraction_percent)
    return (co_rate + cn_rate + nox_rate + fld_irr) * hv_co2 + o2_rate


def accumulate_default_fed(
    inputs: DefaultFedInputs,
    *,
    duration_s: float,
    initial_fed: float = 0.0,
) -> float:
    """Accumulate FED over a constant-exposure interval in seconds."""

    duration_min = max(0.0, float(duration_s)) / 60.0
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
    return (remaining / rate_per_min) * 60.0


class _SliceFieldSampler:
    """Sample one `fdsreader` slice quantity with nearest-neighbor lookup."""

    def __init__(self, slice_obj):
        """Cache the slice object and its subslices for repeated sampling."""
        self._slice = slice_obj
        self._subslices = list(slice_obj.subslices)

    def _find_subslice(self, x: float, y: float):
        """Return the subslice covering the requested x/y point."""
        for subslice in self._subslices:
            extent = subslice.extent
            if (
                extent.x_start <= x <= extent.x_end
                and extent.y_start <= y <= extent.y_end
            ):
                return subslice
        return None

    @staticmethod
    def _nearest_index(start: float, end: float, count: int, value: float) -> int:
        """Return the nearest cell index along one slice axis."""
        if count <= 1 or end <= start:
            return 0
        dx = (end - start) / count
        center = start + 0.5 * dx
        index = round((value - center) / dx)
        return max(0, min(count - 1, int(index)))

    def sample(self, time_s: float, x: float, y: float) -> float:
        """Return the sampled scalar value at one time and x/y point."""
        subslice = self._find_subslice(float(x), float(y))
        if subslice is None:
            raise ValueError(
                f"Point ({x}, {y}) is outside the sampled FDS slice domain"
            )

        t_index = int(self._slice.get_nearest_timestep(float(time_s)))
        i_index = self._nearest_index(
            subslice.extent.x_start, subslice.extent.x_end, subslice.shape[0], float(x)
        )
        j_index = self._nearest_index(
            subslice.extent.y_start, subslice.extent.y_end, subslice.shape[1], float(y)
        )
        return float(subslice.data[t_index, i_index, j_index])


class FdsFedField:
    """Sample FED input quantities from FDS slice outputs via fdsreader.

    Required slices: CO, CO2, O2 (volume fractions in [0, 1]).
    Optional slices: HCN, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde.
    Missing optional species contribute 0 to the FED sum.
    """

    # Map from attribute name to (FDS quantity name, unit-to-ppm factor).
    # Volume-fraction slices are stored as fractions [0,1] in FDS; multiply
    # by 1e6 to get ppm.
    _OPTIONAL_SPECIES: list[tuple[str, str, float]] = [
        ("_hcn", "HYDROGEN CYANIDE VOLUME FRACTION", 1e6),
        ("_no", "NITRIC OXIDE VOLUME FRACTION", 1e6),
        ("_no2", "NITROGEN DIOXIDE VOLUME FRACTION", 1e6),
        ("_hcl", "HYDROGEN CHLORIDE VOLUME FRACTION", 1e6),
        ("_hbr", "HYDROGEN BROMIDE VOLUME FRACTION", 1e6),
        ("_hf", "HYDROGEN FLUORIDE VOLUME FRACTION", 1e6),
        ("_so2", "SULFUR DIOXIDE VOLUME FRACTION", 1e6),
        ("_acrolein", "ACROLEIN VOLUME FRACTION", 1e6),
        ("_formaldehyde", "FORMALDEHYDE VOLUME FRACTION", 1e6),
    ]

    def __init__(
        self,
        co_sampler: _SliceFieldSampler,
        co2_sampler: _SliceFieldSampler,
        o2_sampler: _SliceFieldSampler,
        **optional_samplers: _SliceFieldSampler,
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
    def from_fds(cls, fds_dir: str) -> "FdsFedField":
        """Build gas samplers from an FDS case directory.

        Required: CO, CO2, O2 slices.
        Optional: HCN, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde.
        """
        if Simulation is None:
            raise ModuleNotFoundError(
                "fdsreader is required to load FED fields from FDS data."
            )
        sim = Simulation(str(fds_dir))
        co_slice = sim.slices.filter_by_quantity("CARBON MONOXIDE VOLUME FRACTION")[0]
        co2_slice = sim.slices.filter_by_quantity("CARBON DIOXIDE VOLUME FRACTION")[0]
        o2_slice = sim.slices.filter_by_quantity("OXYGEN VOLUME FRACTION")[0]

        optional = {}
        for attr, quantity, _ in cls._OPTIONAL_SPECIES:
            key = attr.lstrip("_")
            matches = sim.slices.filter_by_quantity(quantity)
            if matches:
                optional[key] = _SliceFieldSampler(matches[0])
        return cls(
            _SliceFieldSampler(co_slice),
            _SliceFieldSampler(co2_slice),
            _SliceFieldSampler(o2_slice),
            **optional,
        )

    def _sample_optional_ppm(
        self, sampler: _SliceFieldSampler | None, time_s: float, x: float, y: float
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
            formaldehyde_ppm=self._sample_optional_ppm(self._formaldehyde, time_s, x, y),
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
        updated = float(current_fed) + rate_per_min * max(0.0, float(dt_s)) / 60.0
        return inputs, rate_per_min, updated
