"""Per-agent exposure summary: when each criterion was first crossed (#210).

A post-processing of the histories a run sampled (``fed_history``,
``smoke_history``) and of the exit times the engine recorded. It reads no
FDS data and no simulation object, so tests hand it plain rows.

One row per agent. For every criterion the row holds the first sample time at
which the value reached the threshold (``>=``), the difference to the exit
time (``crossing - exit``, negative: crossed before leaving, the sign of
DIFF = ASET - RSET) and an outcome:

- ``fail``: crossed while inside (an agent still inside at the end that
  crossed is a failure);
- ``pass``: left, and nothing crossed before it;
- ``open``: still inside with no crossing seen, or no sample at all, so the
  margin is undetermined. It is never computed from the last frame;
- ``not_evaluated``: the run did not compute that quantity.

Crossing times have the resolution of the history (``update_interval_s``,
1 s by default): the first sample at or after the true crossing. An agent
that crossed between its last sample and its exit reads ``pass``. Agents
that read ambient air outside the FDS domain are counted in
``outside_fds_samples``; a crossing there is not evidence.

Irritants are the engine's FIC (SFPE incapacitation denominators, HCl
900 ppm), not the ISO 13571 FEC (HCl 1000 ppm).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

OUTCOMES = ("fail", "pass", "open", "not_evaluated")

_Samples = list[tuple[float, float]]


@dataclass(frozen=True)
class ExposureSummaryConfig:
    """Thresholds of the exposure summary.

    ``fed_thresholds`` apply to the gas FED, the heat FED and the FIC. The
    visibility limit is ``visibility_c / visibility_limit_m`` (the extinction
    coefficient K at which a target at ``visibility_limit_m`` is lost, with
    the contrast constant C). The defaults are 10 m (Engineers Australia
    2014 p.15, NZBC C/VM2 commentary p.30, vfdb TB 04-01 Table 8.3) and C = 3
    for light-reflecting signs (C = 8 for light-emitting ones; Jin as quoted
    in vfdb p.314 and ISO 13571:2012 Note 2 p.11), so K = 0.3 1/m. The vfdb
    limit D_L = 0.1 1/m is K = 0.23 1/m, which Schroeder et al. (2020) used.
    """

    fed_thresholds: tuple[float, ...] = (0.3, 1.0)
    visibility_c: float = 3.0
    visibility_limit_m: float = 10.0

    def __post_init__(self) -> None:
        """Reject thresholds that are not finite and positive."""
        values = (*self.fed_thresholds, self.visibility_c, self.visibility_limit_m)
        if not self.fed_thresholds:
            raise ValueError("ExposureSummaryConfig: fed_thresholds is empty")
        for value in values:
            if not (math.isfinite(value) and value > 0.0):
                raise ValueError(
                    f"ExposureSummaryConfig: {value!r} is not a positive finite "
                    f"number (fed_thresholds={self.fed_thresholds}, "
                    f"visibility_c={self.visibility_c}, "
                    f"visibility_limit_m={self.visibility_limit_m})"
                )
        names = [_number(t) for t in self.fed_thresholds]
        if len(set(names)) != len(names):
            raise ValueError(
                f"ExposureSummaryConfig: duplicate fed_thresholds {self.fed_thresholds}"
            )

    @property
    def k_limit_per_m(self) -> float:
        """Extinction coefficient [1/m] at which the visibility limit is met."""
        return self.visibility_c / self.visibility_limit_m


def _number(value: float) -> str:
    """Return *value* as it appears in a column name."""
    return f"{value:g}"


@dataclass(frozen=True)
class _Criterion:
    """One threshold on one quantity: its column key and the quantity."""

    key: str
    quantity: str
    threshold: float


def _criteria(config: ExposureSummaryConfig) -> list[_Criterion]:
    out = [
        _Criterion(f"{quantity}_ge_{_number(thr)}", quantity, thr)
        for quantity in ("fed", "heat_fed", "fic")
        for thr in config.fed_thresholds
    ]
    k_limit = config.k_limit_per_m
    out.append(_Criterion(f"k_ge_{_number(k_limit)}", "k", k_limit))
    return out


def _by_agent(rows: Iterable[Mapping[str, Any]], field: str) -> dict[int, _Samples]:
    """Group ``(time_s, value)`` samples of *field* by agent, in time order."""
    grouped: dict[int, _Samples] = {}
    for row in rows:
        grouped.setdefault(int(row["agent_id"]), []).append(
            (float(row["time_s"]), float(row[field]))
        )
    for samples in grouped.values():
        samples.sort()
    return grouped


def _inside(samples: _Samples, exit_s: float | None) -> _Samples:
    """Samples up to and including the exit time (a sample at exit is inside)."""
    if exit_s is None:
        return samples
    return [s for s in samples if s[0] <= exit_s]


def _first_crossing(samples: _Samples, threshold: float) -> float | None:
    for time_s, value in samples:
        if value >= threshold:
            return time_s
    return None


def outcome_of(
    crossing_s: float | None, exit_s: float | None, *, observed: bool
) -> str:
    """Return ``fail``, ``pass`` or ``open`` for one agent and one criterion."""
    if crossing_s is not None:
        return "fail"
    if exit_s is not None and observed:
        return "pass"
    return "open"


_QUANTITY_FIELD = {
    "fed": "fed_cumulative",
    "heat_fed": "heat_fed_cumulative",
    "fic": "fic",
    "k": "extinction_per_m",
}


def summarise_exposure(
    fed_rows: Sequence[Mapping[str, Any]] | None,
    smoke_rows: Sequence[Mapping[str, Any]] | None,
    exit_times: Mapping[int, float],
    *,
    gas_evaluated: bool,
    heat_evaluated: bool,
    config: ExposureSummaryConfig | None = None,
) -> list[dict[str, Any]]:
    """Return one summary row per agent seen in the histories or exits.

    ``fed_rows`` and ``smoke_rows`` are the run's histories (``None``: that
    stream did not run). ``gas_evaluated`` is False when only the heat FED
    ran, so the gas FED and the FIC in the rows are defaults, not results;
    ``heat_evaluated`` is False when no heat model ran, so the 20 degC in the
    rows is ambient, not a result. Quantities that were not evaluated read
    ``not_evaluated`` and have empty cells.
    """
    cfg = config or ExposureSummaryConfig()
    fed_rows = list(fed_rows) if fed_rows is not None else None
    smoke_rows = list(smoke_rows) if smoke_rows is not None else None
    evaluated = {
        "fed": fed_rows is not None and gas_evaluated,
        "fic": fed_rows is not None and gas_evaluated,
        "heat_fed": fed_rows is not None and heat_evaluated,
        "k": smoke_rows is not None,
    }
    streams = {
        "fed": fed_rows or [],
        "fic": fed_rows or [],
        "heat_fed": fed_rows or [],
        "k": smoke_rows or [],
    }
    samples = {
        quantity: _by_agent(streams[quantity], _QUANTITY_FIELD[quantity])
        for quantity in _QUANTITY_FIELD
        if evaluated[quantity]
    }
    agent_ids = set(exit_times)
    for per_agent in samples.values():
        agent_ids |= set(per_agent)
    has_domain_flag = bool(fed_rows) and "in_fds_domain" in fed_rows[0]
    outside = Counter(
        int(r["agent_id"]) for r in fed_rows or [] if r.get("in_fds_domain") is False
    )
    incapacitated = _incapacitation_times(fed_rows or [])
    last_sample = _last_samples(fed_rows or [], smoke_rows or [], exit_times)

    summary = []
    for agent_id in sorted(agent_ids):
        exit_s = exit_times.get(agent_id)
        row: dict[str, Any] = {
            "agent_id": agent_id,
            "exit_time_s": exit_s,
            "censored": exit_s is None,
            "last_sample_s": last_sample.get(agent_id),
            "incapacitated_s": incapacitated.get(agent_id),
            "heat_evaluated": evaluated["heat_fed"],
        }
        if has_domain_flag:
            row["outside_fds_samples"] = outside.get(agent_id, 0)
        crossings = _agent_criteria(agent_id, exit_s, samples, evaluated, cfg)
        row.update(crossings)
        summary.append(row)
    return [_ordered(row, cfg) for row in summary]


def _incapacitation_times(fed_rows: Iterable[Mapping[str, Any]]) -> dict[int, float]:
    first: dict[int, float] = {}
    for row in fed_rows:
        if not row.get("incapacitated"):
            continue
        agent_id = int(row["agent_id"])
        time_s = float(row["time_s"])
        first[agent_id] = min(first.get(agent_id, time_s), time_s)
    return first


def _last_samples(
    fed_rows: Iterable[Mapping[str, Any]],
    smoke_rows: Iterable[Mapping[str, Any]],
    exit_times: Mapping[int, float],
) -> dict[int, float]:
    """Last history sample time per agent while inside."""
    last: dict[int, float] = {}
    for row in (*fed_rows, *smoke_rows):
        agent_id = int(row["agent_id"])
        time_s = float(row["time_s"])
        exit_s = exit_times.get(agent_id)
        if exit_s is not None and time_s > exit_s:
            continue
        last[agent_id] = max(last.get(agent_id, time_s), time_s)
    return last


def _agent_criteria(
    agent_id: int,
    exit_s: float | None,
    samples: Mapping[str, Mapping[int, _Samples]],
    evaluated: Mapping[str, bool],
    cfg: ExposureSummaryConfig,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    inside = {
        quantity: _inside(per_agent.get(agent_id, []), exit_s)
        for quantity, per_agent in samples.items()
    }
    for quantity in _QUANTITY_FIELD:
        if not evaluated[quantity]:
            out[f"{quantity}_max"] = None
            continue
        values = [v for _, v in inside[quantity]]
        out[f"{quantity}_max"] = max(values) if values else None
    for crit in _criteria(cfg):
        if not evaluated[crit.quantity]:
            out[f"t_{crit.key}_s"] = None
            out[f"diff_{crit.key}_s"] = None
            out[f"outcome_{crit.key}"] = "not_evaluated"
            continue
        seen = inside[crit.quantity]
        crossing = _first_crossing(seen, crit.threshold)
        out[f"t_{crit.key}_s"] = crossing
        out[f"diff_{crit.key}_s"] = (
            crossing - exit_s if crossing is not None and exit_s is not None else None
        )
        out[f"outcome_{crit.key}"] = outcome_of(crossing, exit_s, observed=bool(seen))
    return out


def _ordered(row: dict[str, Any], cfg: ExposureSummaryConfig) -> dict[str, Any]:
    """Return *row* with its keys in the documented column order."""
    head = ["agent_id", "exit_time_s", "censored", "last_sample_s", "incapacitated_s"]
    if "outside_fds_samples" in row:
        head.append("outside_fds_samples")
    head.append("heat_evaluated")
    criteria = _criteria(cfg)
    body: list[str] = []
    for quantity in _QUANTITY_FIELD:
        body.append(f"{quantity}_max")
        body += [f"t_{c.key}_s" for c in criteria if c.quantity == quantity]
    body += [f"diff_{c.key}_s" for c in criteria]
    body += [f"outcome_{c.key}" for c in criteria]
    return {name: row[name] for name in (*head, *body)}


def exposure_totals(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return per criterion the outcome counts and the first crossing time.

    Keys are the criterion keys of the columns (``fed_ge_0.3``, ``k_ge_0.3``).
    """
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        for column, value in row.items():
            if not column.startswith("outcome_"):
                continue
            key = column.removeprefix("outcome_")
            entry = totals.setdefault(
                key, {**dict.fromkeys(OUTCOMES, 0), "crossed": 0, "first_s": None}
            )
            entry[value] += 1
            crossing = row.get(f"t_{key}_s")
            if crossing is None:
                continue
            entry["crossed"] += 1
            first = entry["first_s"]
            entry["first_s"] = crossing if first is None else min(first, crossing)
    return totals
