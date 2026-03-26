"""Smoke-speed models driven by local smoke extinction from FDS outputs.

Model overview
--------------
Walking speed through smoke is reduced based on the local extinction
coefficient K [1/m] using the linear FDS+Evac / Frantzich-Nilsson (Lund)
correlation:

    speed_factor(K) = 1 + beta * K / alpha

where alpha = 0.706 and beta = -0.057 by default.  The factor is clamped
to [min_speed_factor, 1.0].

When evaluating route costs, the extinction along a line of sight between
two points is computed as the Beer-Lambert path-integrated mean
(Boerger et al. 2024, Eq. 9):

    sigma_bar = (K_m / |P|) * sum(rho_s(l))

where rho_s is the soot density sampled at each cell along the ray and
K_m = 8700 m^2/kg is the mass-specific extinction coefficient for red
light at 633 nm (well-ventilated flaming combustion).

FDS slice data is read via ``fdsreader`` and sampled with nearest-neighbor
lookup.

References
----------
- Jin (1970-1978): empirical visibility-extinction correlation V = C / sigma
- Frantzich & Nilsson (Lund): linear speed-extinction relation used by FDS+Evac
- Ronchi et al. (2013): interpretation A3 comparison across evacuation tools
- Boerger et al. (2024), Fire Safety Journal 150:104269:
  Beer-Lambert integrated extinction along line of sight (Eq. 8-9),
  view-angle correction (Eq. 7), waypoint-based visibility maps
"""

from dataclasses import dataclass

import numpy as np

from .fds_sampling import SliceFieldSampler, load_slice_sampler


@dataclass
class SmokeSpeedConfig:
    """Store coefficients and sampling settings for the smoke-speed model.

    The default coefficients follow the linear extinction correlation used by
    FDS+Evac / Lund-style smoke-speed reduction:

        speed_factor(K) = 1 + beta * K / alpha

    where:
    - K is the local extinction coefficient in 1/m
    - alpha = 0.706
    - beta = -0.057

    The resulting factor is clamped to [min_speed_factor, 1.0].
    """

    fds_dir: str
    update_interval_s: float = 1.0
    slice_height_m: float = 2.0
    alpha: float = 0.706
    beta: float = -0.057
    min_speed_factor: float = 0.1


class ExtinctionField:
    """Sample local smoke extinction K [1/m] from FDS slices via fdsreader.

    This class treats the extinction coefficient as the primary normative
    quantity for smoke-speed modelling.  Derived visibility (V = C/K) can
    be computed elsewhere, but speed reduction is based directly on K.
    """

    def __init__(self, sampler: SliceFieldSampler):
        """Wrap a ``SliceFieldSampler`` for the extinction slice."""
        self._sampler = sampler

    @classmethod
    def from_fds(
        cls,
        fds_dir: str,
        *,
        slice_height_m: float = 2.0,
    ) -> "ExtinctionField":
        """Load extinction slices from an FDS case directory via fdsreader."""
        _ = slice_height_m  # reserved for future multi-height support
        sampler = load_slice_sampler(fds_dir, "SOOT EXTINCTION COEFFICIENT")
        return cls(sampler)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return the nearest-grid extinction coefficient K [1/m]."""
        try:
            return self._sampler.sample(time_s, x, y)
        except ValueError:
            return 0.0


class ConstantExtinctionField:
    """Return a constant extinction coefficient everywhere.

    This is primarily useful for deterministic verification cases such as
    ISO 20414 Table 21, where the corridor is assigned a uniform extinction
    coefficient before the evacuation run starts.
    """

    def __init__(self, extinction_per_m: float):
        """Store a constant extinction coefficient in 1/m."""
        self.extinction_per_m = float(extinction_per_m)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return the configured constant value for any point and time."""
        del time_s, x, y
        return self.extinction_per_m


def extinction_from_soot_density(
    soot_density_mg_per_m3: float,
    *,
    mass_extinction_coefficient_m2_per_kg: float = 8700.0,
) -> float:
    """Convert soot density in mg/m^3 to extinction coefficient K in 1/m.

    FDS+Evac uses:
        K = MASS_EXTINCTION_COEFFICIENT * SOOT_DENS * 1e-6

    where:
    - `MASS_EXTINCTION_COEFFICIENT` is in m^2/kg
    - `SOOT_DENS` is in mg/m^3
    """

    soot_density = max(0.0, float(soot_density_mg_per_m3))
    return float(mass_extinction_coefficient_m2_per_kg) * soot_density * 1.0e-6


def speed_from_soot_density(
    base_speed_m_per_s: float,
    soot_density_mg_per_m3: float,
    *,
    alpha: float = 0.706,
    beta: float = -0.057,
    mass_extinction_coefficient_m2_per_kg: float = 8700.0,
    min_speed_factor: float = 0.1,
) -> float:
    """Compute walking speed directly from soot density using the FDS+Evac path."""

    extinction = extinction_from_soot_density(
        soot_density_mg_per_m3,
        mass_extinction_coefficient_m2_per_kg=mass_extinction_coefficient_m2_per_kg,
    )
    return float(base_speed_m_per_s) * speed_factor_from_extinction(
        extinction,
        alpha=alpha,
        beta=beta,
        min_speed_factor=min_speed_factor,
    )


def speed_factor_from_extinction(
    extinction_per_m: float,
    *,
    alpha: float = 0.706,
    beta: float = -0.057,
    min_speed_factor: float = 0.1,
) -> float:
    """Convert extinction coefficient K [1/m] to a normalized speed factor.

    Reference model:
    - FDS+Evac applies the Frantzich/Nilsson data with a fractional speed
      reduction and variable minimum speed.
    - Ronchi et al. (2013) describe this as interpretation A3 and show that
      model results remain comparable when the same dataset and interpretation
      are used consistently across tools.
    - The implementation here follows the linear FDS+Evac/Lund relation:
      v(K) = v0 * (1 + beta * K / alpha)

    Notes:
    - This function returns the multiplicative factor v(K) / v0.
    - beta < 0 means speed decreases as extinction increases.
    - We clamp to a minimum speed factor instead of zero. That preserves the
      FDS+Evac-style fractional interpretation with a variable minimum speed:
      the minimum absolute speed is still proportional to the individual's
      clear-air speed.
    """

    if not np.isfinite(extinction_per_m):
        extinction_per_m = 0.0
    extinction_per_m = max(0.0, float(extinction_per_m))
    factor = 1.0 + (beta * extinction_per_m) / alpha
    return float(np.clip(factor, min_speed_factor, 1.0))


class SmokeSpeedModel:
    """Couple a sampled extinction field with the configured speed law.

    The field can come from ``fdsreader`` for real FDS output or from a
    constant field for deterministic verification tests.
    """

    def __init__(self, field: ExtinctionField, config: SmokeSpeedConfig):
        """Store the field sampler and model coefficients."""
        self.field = field
        self.config = config

    def sample(self, time_s: float, x: float, y: float) -> tuple[float, float]:
        """Return `(extinction_K, speed_factor)` at the requested position/time."""
        extinction = self.field.sample_extinction(time_s, x, y)
        return extinction, speed_factor_from_extinction(
            extinction,
            alpha=self.config.alpha,
            beta=self.config.beta,
            min_speed_factor=self.config.min_speed_factor,
        )

    def speed_factor(self, time_s: float, x: float, y: float) -> float:
        """Return only the speed factor at the requested position/time."""
        _, factor = self.sample(time_s, x, y)
        return factor
