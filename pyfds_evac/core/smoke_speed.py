"""Smoke-speed models driven by local smoke extinction from FDS outputs.

Model overview
--------------
Two speed-law options are available, selected via ``SmokeSpeedConfig.speed_law``:

``"lund"`` (default)
    Linear FDS+Evac / Frantzich-Nilsson (Lund) correlation based on extinction K:

        speed_factor(K) = 1 + beta * K / alpha

    where alpha = 0.706 and beta = -0.057 by default.  The factor is clamped
    to [min_speed_factor, 1.0].

``"fridolf"``
    Additive law from Fridolf et al. (2019), Eq. 7 (method 3; first
    presented in Fridolf et al. 2018), based on visibility
    V [m] and the agent's smoke-free speed w_free [m/s]:

        w(V) = min(w_free, max(0.2, w_free - 0.34 * (3 - V)))

    Above 3 m the speed is unchanged; below, it drops by 0.34 m/s per metre
    of visibility, to an absolute floor of 0.2 m/s.  Visibility is derived
    from extinction via V = C / K (Jin 1970-1978).  The 2018 abstract gives
    no constant; the 2019 paper used A = 2 (reflecting) or 8 (emitting),
    Eq. 1.  pyFDS-Evac uses the FDS default C = 3, so for reflecting targets
    agents slow later and less than the calibration; C = 2 matches it.
    The speed factor applied to the agent is w / w_free.

When evaluating route costs, the extinction along a line of sight between
two points is computed as the arithmetic mean of K sampled at uniform
intervals along the ray (Boerger et al. 2024, Eq. 8-9):

    K_bar = (1 / |P|) * sum_p K_p

where K_p is the extinction coefficient ``SOOT EXTINCTION COEFFICIENT``
sampled from FDS at each point along the path and |P| is the number of
sample points.

The conversion from soot density to extinction (K = K_m * rho_s) is
handled upstream by FDS itself; pyFDS-Evac reads the pre-computed K
field directly.

FDS slice data is read via ``fdsreader`` and sampled with nearest-neighbor
lookup.

References
----------
- Jin (1970-1978): empirical visibility-extinction correlation V = C / sigma
- Frantzich & Nilsson (Lund): linear speed-extinction relation used by FDS+Evac
- Ronchi et al. (2013): interpretation A3 comparison across evacuation tools
- Fridolf, Nilsson, Frantzich, Ronchi & Arias (2018): "Walking speed in
  smoke: representation in life safety verifications", SFPE 2018 extended
  abstract.  Individual speed-visibility law (method 3).
- Fridolf, Ronchi, Nilsson & Frantzich (2019), Tunnelling and Underground
  Space Technology 90:28-41, doi:10.1016/j.tust.2019.04.016, Eq. 7.
- Boerger et al. (2024), Fire Safety Journal 150:104269:
  Beer-Lambert integrated extinction along line of sight (Eq. 8-9),
  view-angle correction (Eq. 7), waypoint-based visibility maps
"""

import inspect
import logging
import math
from dataclasses import dataclass

import numpy as np

from .fds_sampling import (
    FdsDomainError,
    FdsHorizonError,
    SliceFieldSampler,
    domain_error_message,
    load_slice_sampler,
    sampler_quantity,
)

_logger = logging.getLogger(__name__)


@dataclass
class SmokeSpeedConfig:
    """Store coefficients and sampling settings for the smoke-speed model.

    speed_law
        ``"lund"`` (default): linear FDS+Evac / Lund correlation
        ``speed_factor(K) = 1 + beta * K / alpha``, clamped to
        ``[min_speed_factor, 1.0]``.

        ``"fridolf"``: additive Fridolf et al. (2018) law
        ``w = min(w_free, max(0.2, w_free - 0.34 (3 - V)))`` where
        ``V = C / K``; the speed factor is ``w / w_free``.

    visibility_factor_c
        Visibility factor C in the Jin (1970-1978) relation V = C / K.
        Only used when ``speed_law = "fridolf"``.
        C = 3 corresponds to a reflective sign; C = 8 to a light-emitting sign.

    fridolf_slope, fridolf_visibility_threshold_m, fridolf_min_speed_m_per_s
        Speed drop per metre of visibility [m/s per m], the visibility below
        which it applies [m], and the absolute speed floor [m/s].
    """

    fds_dir: str | None = None
    update_interval_s: float = 1.0
    slice_height_m: float = 1.6
    speed_law: str = "lund"
    # lund coefficients
    alpha: float = 0.706
    beta: float = -0.057
    min_speed_factor: float = 0.1
    # fridolf coefficients
    visibility_factor_c: float = 3.0
    fridolf_slope: float = 0.34
    fridolf_visibility_threshold_m: float = 3.0
    fridolf_min_speed_m_per_s: float = 0.2


class ExtinctionField:
    """Sample local smoke extinction K [1/m] from FDS slices via fdsreader.

    This class treats the extinction coefficient as the primary normative
    quantity for smoke-speed modelling.  Derived visibility (V = C/K) can
    be computed elsewhere, but speed reduction is based directly on K.
    """

    def __init__(
        self, sampler: SliceFieldSampler, *, require_fds_coverage: bool = False
    ):
        """Wrap a ``SliceFieldSampler`` for the extinction slice.

        Outside the slice K reads 0 (clear air, as FDS+Evac), unless
        *require_fds_coverage* is set: then such a sample raises
        ``FdsDomainError``.
        """
        self._sampler = sampler
        self._require_fds_coverage = require_fds_coverage
        self._warned_ood = False

    @classmethod
    def from_fds(
        cls,
        fds_dir: str,
        *,
        slice_height_m: float = 1.6,
        simulation=None,
        allow_horizon_hold: bool = False,
        require_fds_coverage: bool = False,
    ) -> "ExtinctionField":
        """Load extinction slices from an FDS case directory via fdsreader."""
        sampler = load_slice_sampler(
            fds_dir,
            "SOOT EXTINCTION COEFFICIENT",
            simulation=simulation,
            slice_height_m=slice_height_m,
            allow_horizon_hold=allow_horizon_hold,
        )
        field = cls(sampler, require_fds_coverage=require_fds_coverage)
        field.fds_dir = str(fds_dir)
        return field

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return the nearest-grid extinction coefficient K [1/m]."""
        try:
            return self._sampler.sample(time_s, x, y)
        except FdsHorizonError:
            raise
        except ValueError:
            if self._require_fds_coverage:
                raise FdsDomainError(
                    domain_error_message(sampler_quantity(self._sampler), time_s, x, y)
                ) from None
            if not self._warned_ood:
                _logger.warning(
                    "Extinction sample at (%.2f, %.2f, t=%.1f) is outside "
                    "the FDS slice domain; returning 0.0 for out-of-domain points",
                    x,
                    y,
                    time_s,
                )
                self._warned_ood = True
            return 0.0

    def covers(self, x: float, y: float) -> bool:
        """Return whether the extinction slice covers the x/y point."""
        return self._sampler.covers(x, y)

    def samplers(self) -> list[SliceFieldSampler]:
        """Return the FDS slice samplers this field reads."""
        return [self._sampler]


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

    def covers(self, x: float, y: float) -> bool:
        """Return True: a constant field is defined everywhere."""
        del x, y
        return True

    def samplers(self) -> list[SliceFieldSampler]:
        """Return no samplers: a constant field reads no FDS slice."""
        return []


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
    """Convert K [1/m] to a speed factor using the Lund (FDS+Evac) linear law.

    v(K) / v0 = 1 + beta * K / alpha, clamped to [min_speed_factor, 1.0].

    - Frantzich & Nilsson (Lund): linear speed-extinction relation used by FDS+Evac.
    - Ronchi et al. (2013): interpretation A3; results comparable across tools.
    - beta < 0: speed decreases as extinction increases.
    - Hard clamp at min_speed_factor preserves the FDS+Evac fractional interpretation.
    """

    if not np.isfinite(extinction_per_m):
        extinction_per_m = 0.0
    extinction_per_m = max(0.0, float(extinction_per_m))
    factor = 1.0 + (beta * extinction_per_m) / alpha
    return float(np.clip(factor, min_speed_factor, 1.0))


def speed_factor_from_extinction_fridolf(
    extinction_per_m: float,
    *,
    visibility_factor_c: float = 3.0,
    free_speed_m_per_s: float = 1.0,
    slope: float = 0.34,
    visibility_threshold_m: float = 3.0,
    min_speed_m_per_s: float = 0.2,
) -> float:
    """Convert K [1/m] to a speed factor using the Fridolf et al. (2019) law.

    Visibility is derived via V = C / K (Jin 1970-1978), then:

        w = min(w_free, max(0.2, w_free - 0.34 * (3 - V)))

    and the factor is w / w_free, so w_free * factor is the paper's w.
    The reduction is additive (0.34 m/s per metre of visibility) and the
    floor is an absolute 0.2 m/s.  The default w_free = 1 m/s is method 1.

    Fridolf, Ronchi, Nilsson & Frantzich (2019), TUST 90:28-41, Eq. 7
    (method 3; also in Fridolf et al. 2018, SFPE extended abstract, a
    summary of their 2016 SP report).  The 2019 paper used A = 2 (reflecting) or 8 (emitting);
    C = 3 is the FDS default, C = 2 matches the calibration.

    Properties:
    - At K = 0 (clear air) or V >= 3 m: factor = 1.
    - The floor never raises the speed above w_free.
    - w_free <= 0: factor = 1 (nothing to slow).
    - C must be finite and positive; otherwise ValueError.
    """

    if not (math.isfinite(visibility_factor_c) and visibility_factor_c > 0.0):
        raise ValueError(
            f"visibility_factor_c must be finite and > 0, got {visibility_factor_c}"
        )
    if not np.isfinite(extinction_per_m):
        extinction_per_m = 0.0
    extinction_per_m = max(0.0, float(extinction_per_m))
    free_speed = float(free_speed_m_per_s)
    if extinction_per_m == 0.0 or free_speed <= 0.0:
        return 1.0
    visibility = visibility_factor_c / extinction_per_m
    reduced = free_speed - slope * (visibility_threshold_m - visibility)
    speed = min(free_speed, max(min_speed_m_per_s, reduced))
    return float(speed / free_speed)


def sample_accepts_free_speed(sample) -> bool:
    """Return whether a ``sample`` callable takes ``free_speed_m_per_s``.

    Custom smoke models may define ``sample(time_s, x, y)`` only; callers
    pass the free speed to those that accept it.
    """
    try:
        params = inspect.signature(sample).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        p.name == "free_speed_m_per_s" or p.kind is inspect.Parameter.VAR_KEYWORD
        for p in params
    )


class SmokeSpeedModel:
    """Couple a sampled extinction field with the configured speed law.

    The field can come from ``fdsreader`` for real FDS output or from a
    constant field for deterministic verification tests.
    """

    def __init__(self, field: ExtinctionField, config: SmokeSpeedConfig):
        """Store the field sampler and model coefficients."""
        self.field = field
        self.config = config

    def sample(
        self,
        time_s: float,
        x: float,
        y: float,
        free_speed_m_per_s: float | None = None,
    ) -> tuple[float, float]:
        """Return `(extinction_K, speed_factor)` at the requested position/time.

        ``free_speed_m_per_s`` is the agent's smoke-free speed, needed by the
        additive ``fridolf`` law; without it that law uses 1 m/s (method 1).
        The ``lund`` law ignores it.
        """
        extinction = self.field.sample_extinction(time_s, x, y)
        if self.config.speed_law == "fridolf":
            factor = speed_factor_from_extinction_fridolf(
                extinction,
                visibility_factor_c=self.config.visibility_factor_c,
                free_speed_m_per_s=(
                    1.0 if free_speed_m_per_s is None else free_speed_m_per_s
                ),
                slope=self.config.fridolf_slope,
                visibility_threshold_m=self.config.fridolf_visibility_threshold_m,
                min_speed_m_per_s=self.config.fridolf_min_speed_m_per_s,
            )
        else:
            factor = speed_factor_from_extinction(
                extinction,
                alpha=self.config.alpha,
                beta=self.config.beta,
                min_speed_factor=self.config.min_speed_factor,
            )
        return extinction, factor

    def speed_factor(
        self,
        time_s: float,
        x: float,
        y: float,
        free_speed_m_per_s: float | None = None,
    ) -> float:
        """Return only the speed factor at the requested position/time."""
        if free_speed_m_per_s is None or not sample_accepts_free_speed(self.sample):
            _, factor = self.sample(time_s, x, y)
            return factor
        _, factor = self.sample(time_s, x, y, free_speed_m_per_s=free_speed_m_per_s)
        return factor
