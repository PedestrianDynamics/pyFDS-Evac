"""ASET inputs from FDS output: the field adapter.

Reads the slices the engine reads, at the nodes of the slice, with the
engine's rules (``docs/fds-sampling.md``): the nearest slice value and the
nearest frame, no interpolation, the slice nearest the engine's sampling
height. FED and heat dose rates come from the ``core/fed.py`` functions the
engine calls; no equation is repeated here.

A point is never read through ``ExtinctionField`` or ``FdsFedField`` sample
methods, which return clear or ambient air outside a slice. Here an uncovered
point stays uncovered: a species that does not cover a node raises, and the
map has no data there. Time never runs past the last frame of the slices.

The FED and heat maps are for a person standing still at the node from
t = 0, at the sampling height. They are not the dose of anyone's walk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pyfds_evac.core.fds_import_people import HUMAN_SMOKE_HEIGHT_M
from pyfds_evac.core.fds_sampling import SliceFieldSampler, load_slice_sampler
from pyfds_evac.core.fed import (
    DEFAULT_HEAT_CLOTHING,
    DefaultFedConfig,
    DefaultFedInputs,
    FdsFedField,
    HeatFedInputs,
    default_fed_rate_per_minute,
    default_heat_fed_rate_per_minute,
)

from .aset_rset import (
    PointCrossing,
    PointSeries,
    first_crossing_dose,
    first_crossing_level,
)

EXTINCTION_QUANTITY = "SOOT EXTINCTION COEFFICIENT"
TEMPERATURE_QUANTITY = "TEMPERATURE"

STAY_TEMPERATURE_C = {"<30 min": 45.0, "~15 min": 50.0, "<5 min": 50.0}
"""Gas temperature limit by stay in the smoke, vfdb TB 04-01 Table 8.3 and
DIN 18009-2 Table 1. Dry air (< 10 vol % water vapour), at 2 m."""


@dataclass(frozen=True)
class AsetCriteria:
    """What makes a cell untenable. A ``None`` limit leaves that criterion out.

    * Visibility: ``K >= C / V_lim``. 10 m and C = 3 give 0.3 1/m
      (Engineers Australia 2014, NZBC C/VM2, vfdb TB 04-01 Table 8.3; C from
      Jin as quoted in vfdb p. 314 and ISO 13571 Note 2). *extinction_per_m*
      sets K directly and wins (Schröder et al. use 0.23 1/m).
    * Temperature: ``T >= temperature_c`` at the sampling height. 45 degC is
      the stay under 30 min of vfdb and DIN 18009-2, for dry air; see
      ``STAY_TEMPERATURE_C`` and ``with_stay``.
    * Toxic FED: the FED of someone standing still from t = 0 reaches *fed*.
    * Heat FED: the same for the convective heat dose, *heat_clothing* law.
    """

    visibility_limit_m: float | None = 10.0
    visibility_c: float = 3.0
    extinction_per_m: float | None = None
    temperature_c: float | None = 45.0
    fed: float | None = 0.3
    heat_fed: float | None = 0.3
    heat_clothing: str = DEFAULT_HEAT_CLOTHING

    def __post_init__(self) -> None:
        for name in (
            "visibility_limit_m",
            "visibility_c",
            "extinction_per_m",
            "fed",
            "heat_fed",
        ):
            value = getattr(self, name)
            if value is not None and not value > 0:
                raise ValueError(f"AsetCriteria.{name} must be positive, got {value}")

    @classmethod
    def with_stay(cls, stay: str, **kwargs) -> AsetCriteria:
        """Criteria with the temperature limit of a stay class."""
        if stay not in STAY_TEMPERATURE_C:
            raise ValueError(f"stay {stay!r} not one of {tuple(STAY_TEMPERATURE_C)}")
        return cls(temperature_c=STAY_TEMPERATURE_C[stay], **kwargs)

    @property
    def k_limit_per_m(self) -> float | None:
        """The extinction coefficient limit [1/m], or None without visibility."""
        if self.extinction_per_m is not None:
            return self.extinction_per_m
        if self.visibility_limit_m is None:
            return None
        return self.visibility_c / self.visibility_limit_m


def _no_nan(values: np.ndarray, what: str) -> np.ndarray:
    if np.isnan(values).any():
        raise ValueError(
            f"{what}: a sample node lies outside a slice that the criterion "
            "needs; the slices of one criterion must cover the same nodes"
        )
    return values


def _frames(grid, indices) -> np.ndarray:
    """The slice values of each frame index at the grid's points, (n, points)."""
    return np.stack([grid.values(i).ravel() for i in indices]).astype(float)


def _node_points(ax: np.ndarray, ay: np.ndarray):
    gx, gy = np.meshgrid(ax, ay)
    return gx.ravel(), gy.ravel()


def _level_crossing(
    sampler: SliceFieldSampler,
    name: str,
    limit: float,
    description: str,
    scale: float = 1.0,
) -> PointCrossing:
    """First time ``scale * quantity`` reaches *limit* at every node, on frame times."""
    xs, ys, firsts = [], [], []
    times = sampler.frame_times_s
    for ax, ay in sampler.node_axes():
        grid = sampler.grid(ax, ay)
        frames = scale * _no_nan(_frames(grid, range(len(times))), name)
        x, y = _node_points(ax, ay)
        series = PointSeries(x, y, times, np.arange(len(times)), frames)
        xs.append(x)
        ys.append(y)
        firsts.append(first_crossing_level(series, limit))
    return PointCrossing(
        name,
        np.concatenate(xs),
        np.concatenate(ys),
        np.concatenate(firsts),
        float(times[-1]),
        sampler.z_m,
        description,
    )


def _engine_clock(horizon_s: float, step_s: float) -> np.ndarray:
    """Sample times 0, step, 2 step, ... up to the last slice frame."""
    if not step_s > 0:
        raise ValueError(f"dose step must be positive, got {step_s}")
    return np.arange(0.0, horizon_s + 1e-9, step_s)


def _rates_by_step(grids: dict, samplers: dict, times: np.ndarray, rate_of):
    """Per-step dose rate at the nodes, each quantity at its own nearest frame.

    Returns ``(frame, frames)`` for a ``PointSeries``: steps with the same
    frame of every quantity share one rate array.
    """
    keys: dict[tuple, int] = {}
    frame = np.empty(len(times), dtype=int)
    arrays: list[np.ndarray] = []
    for k, t in enumerate(times):
        key = tuple(grids[n].time_index(t) for n in samplers)
        if key not in keys:
            keys[key] = len(arrays)
            values = {
                n: _no_nan(grids[n].values(i).ravel().astype(float), f"{n} slice")
                for n, i in zip(samplers, key)
            }
            arrays.append(rate_of(values))
        frame[k] = keys[key]
    return frame, np.stack(arrays)


def _unique_rows_rate(matrix: np.ndarray, scalar_rate) -> np.ndarray:
    """Apply the engine's scalar rate to each distinct input row once."""
    rows, inverse = np.unique(matrix, axis=0, return_inverse=True)
    rates = np.array([scalar_rate(row) for row in rows])
    return rates[inverse.ravel()]


def _fed_crossing(
    field: FdsFedField, threshold: float, config: DefaultFedConfig, step_s: float
) -> PointCrossing:
    """First time the toxic FED of a person standing from t = 0 reaches *threshold*."""
    samplers = field.gas_samplers()
    names = list(samplers)
    reference = samplers["co"]
    horizon = min(s.end_time_s for s in samplers.values())
    times = _engine_clock(horizon, step_s)
    xs, ys, firsts = [], [], []
    for ax, ay in reference.node_axes():
        grids = {n: s.grid(ax, ay) for n, s in samplers.items()}

        def rate_of(values):
            matrix = np.column_stack([_gas_input(n, values[n]) for n in names])
            return _unique_rows_rate(matrix, lambda row: _gas_rate(names, row, config))

        frame, frames = _rates_by_step(grids, samplers, times, rate_of)
        x, y = _node_points(ax, ay)
        series = PointSeries(x, y, times, frame, frames)
        xs.append(x)
        ys.append(y)
        firsts.append(first_crossing_dose(series, threshold))
    return PointCrossing(
        f"FED {threshold:g}",
        np.concatenate(xs),
        np.concatenate(ys),
        np.concatenate(firsts),
        float(horizon),
        reference.z_m,
        f"toxic FED >= {threshold:g}, standing still from t = 0",
    )


def _gas_input(name: str, values: np.ndarray) -> np.ndarray:
    """A slice volume fraction in the unit ``DefaultFedInputs`` holds it in."""
    return 100.0 * values if name in ("co", "co2", "o2") else 1e6 * values


def _gas_rate(names, row, config: DefaultFedConfig) -> float:
    fields = {
        "co": "co_volume_fraction_percent",
        "co2": "co2_volume_fraction_percent",
        "o2": "o2_volume_fraction_percent",
    }
    kwargs = {fields.get(n, f"{n}_ppm"): float(v) for n, v in zip(names, row)}
    return default_fed_rate_per_minute(
        DefaultFedInputs(**kwargs),
        o2_threshold_percent=config.o2_threshold_percent,
        activity_level=config.activity_level,
    )


def _heat_crossing(
    sampler: SliceFieldSampler, threshold: float, clothing: str, step_s: float
) -> PointCrossing:
    """First time the convective heat FED of a person standing from t = 0 reaches *threshold*."""
    times = _engine_clock(sampler.end_time_s, step_s)
    xs, ys, firsts = [], [], []
    for ax, ay in sampler.node_axes():
        grids = {"temperature": sampler.grid(ax, ay)}

        def rate_of(values):
            return _unique_rows_rate(
                values["temperature"][:, None],
                lambda row: default_heat_fed_rate_per_minute(
                    HeatFedInputs(temperature_celsius=float(row[0])), clothing
                ),
            )

        frame, frames = _rates_by_step(grids, {"temperature": sampler}, times, rate_of)
        x, y = _node_points(ax, ay)
        series = PointSeries(x, y, times, frame, frames)
        xs.append(x)
        ys.append(y)
        firsts.append(first_crossing_dose(series, threshold))
    return PointCrossing(
        f"heat FED {threshold:g}",
        np.concatenate(xs),
        np.concatenate(ys),
        np.concatenate(firsts),
        float(times[-1]),
        sampler.z_m,
        f"convective heat FED >= {threshold:g} ({clothing}), standing still from t = 0",
    )


def read_level_crossing(
    fds_dir: str,
    quantity: str,
    limit: float,
    *,
    scale: float = 1.0,
    name: str | None = None,
    slice_height_m: float = HUMAN_SMOKE_HEIGHT_M,
    simulation=None,
) -> PointCrossing:
    """First time ``scale * quantity >= limit`` at every node of one slice.

    For the level criteria ``AsetCriteria`` does not name: CO or HCl in ppm
    (*scale* ``1e6`` for a volume fraction), CO2 in per cent (*scale* ``100``),
    or a second extinction limit. *quantity* is the FDS slice quantity name,
    for example ``"CARBON MONOXIDE VOLUME FRACTION"``. Frame times, no
    interpolation; an uncovered node raises, as in ``read_crossings``.
    """
    if not limit > 0 or not scale > 0:
        raise ValueError(
            f"read_level_crossing {quantity!r}: limit and scale must be positive, "
            f"got limit {limit}, scale {scale}"
        )
    sampler = load_slice_sampler(
        fds_dir, quantity, simulation=simulation, slice_height_m=slice_height_m
    )
    label = name or f"{quantity} {limit:g}"
    return _level_crossing(
        sampler, label, limit, f"{scale:g} x {quantity} >= {limit:g}", scale
    )


def read_crossings(
    fds_dir: str,
    criteria: AsetCriteria = AsetCriteria(),
    *,
    slice_height_m: float = HUMAN_SMOKE_HEIGHT_M,
    simulation=None,
    dose_step_s: float | None = None,
    fed_config: DefaultFedConfig | None = None,
) -> list[PointCrossing]:
    """First-crossing times of every selected criterion at the slice nodes.

    Visibility and temperature are level criteria on the slice frame times.
    The two dose criteria run on the engine's clock, ``t = k * step`` from 0
    (*dose_step_s*, default the ``update_interval_s`` of *fed_config*, 1 s),
    with the engine's right-endpoint rule. A missing slice raises
    ``IndexError`` naming the quantity: a requested criterion is never
    dropped silently. Each ``PointCrossing`` records the slice height read.
    """
    config = fed_config or DefaultFedConfig()
    step = config.update_interval_s if dose_step_s is None else dose_step_s
    out: list[PointCrossing] = []

    def sampler(quantity: str) -> SliceFieldSampler:
        return load_slice_sampler(
            fds_dir, quantity, simulation=simulation, slice_height_m=slice_height_m
        )

    k_limit = criteria.k_limit_per_m
    if k_limit is not None:
        out.append(
            _level_crossing(
                sampler(EXTINCTION_QUANTITY),
                f"K {k_limit:g}",
                k_limit,
                f"extinction coefficient >= {k_limit:g} 1/m",
            )
        )
    if criteria.temperature_c is not None:
        t = criteria.temperature_c
        out.append(
            _level_crossing(
                sampler(TEMPERATURE_QUANTITY),
                f"T {t:g}",
                t,
                f"gas temperature >= {t:g} degC",
            )
        )
    if criteria.fed is not None:
        field = FdsFedField.from_fds(
            fds_dir, simulation=simulation, slice_height_m=slice_height_m
        )
        out.append(_fed_crossing(field, criteria.fed, config, step))
    if criteria.heat_fed is not None:
        out.append(
            _heat_crossing(
                sampler(TEMPERATURE_QUANTITY),
                criteria.heat_fed,
                criteria.heat_clothing,
                step,
            )
        )
    return out
