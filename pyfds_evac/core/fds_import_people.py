"""Agent parameters from FDS+Evac ``&PERS``/``&EVAC``: speed, delay, familiarity.

FDS+Evac distribution indices (Guide, Table "Statistical distributions"):
0 none (MEAN), 1 uniform (LOW, HIGH), 2 truncated normal (MEAN, PARA, LOW,
HIGH), 3 gamma (PARA=k, PARA2=theta), 4 normal (MEAN, PARA), 5 log-normal
(MEAN, PARA, HIGH, PARA2=x0), 6 beta (PARA, PARA2), 7 triangular (MEAN=peak,
LOW, HIGH), 8 Weibull (PARA=alpha shape, PARA2=lambda rate), 9 Gumbel (PARA).

Maintainer decisions applied here (import task record, 2026-10-06):

- Q2: the delay is detection + pre-movement. Exact where the sum is one of
  our distributions, or one of them shifted by ``premovement_offset_s``;
  otherwise (I1) min(detection) + min(reaction) as the offset plus a gamma
  with the mean and variance of the rest, or the mean where a moment is not known
  in closed form.
- Q3: a uniform speed range becomes a Gaussian with the same mean and
  variance (std = half-range / sqrt(3)).
- Q4 (#699, 2026-10-10): the radius is the mean
  torso radius R_t of the FDS+Evac three-circle body (D1), constant (D2),
  for every operational model (D3). One circle as deep as the FDS+Evac
  body (0.30 m for an adult) but narrower than its shoulders (0.51 m).
- Q1: no known doors -> ``discovery``; every exit known -> ``full``; one
  known exit -> ``discovery`` with that ``entrance``; else the closest of
  these, with a warning.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .fds_deck import NamelistRecord

#: FDS+Evac default agent types: speed (mean, half-range) [m/s].
DEFAULT_PROPERTIES_SPEED = {
    "ADULT": (1.25, 0.30),
    "MALE": (1.35, 0.20),
    "FEMALE": (1.15, 0.20),
    "CHILD": (0.90, 0.30),
    "ELDERLY": (0.80, 0.30),
}
#: FDS+Evac default agent types: body (DIA_MEAN, DIA_LOW, DIA_HIGH,
#: D_TORSO_MEAN, D_SHOULDER_MEAN) [m], with 2R_d uniform on [DIA_LOW, DIA_HIGH]
#: (evac.f90:1850-1961, FDS 6.7.6-404-gc9da70d7a; Guide Table_DefaultHumans).
DEFAULT_PROPERTIES_BODY = {
    "ADULT": (0.51, 0.44, 0.58, 0.30, 0.19),
    "MALE": (0.54, 0.50, 0.58, 0.32, 0.20),
    "FEMALE": (0.48, 0.44, 0.52, 0.28, 0.18),
    "CHILD": (0.42, 0.39, 0.45, 0.24, 0.14),
    "ELDERLY": (0.50, 0.46, 0.54, 0.30, 0.18),
}
#: FDS+Evac global D_TORSO_MEAN default [m] (evac.f90:1683).
D_TORSO_MEAN_DEFAULT = 0.30
_BODY_SOURCE = "FDS+Evac Guide Table_DefaultHumans; evac.f90 PERS presets"
_EXPLICIT_SOURCE = "evac.f90:1998-2020, 14583-14584, 14669, 14955-14957"
_CONSTANT_SOURCE = "evac.f90:1998, 14583-14584, 14669, 14955"
#: FDS+Evac HUMAN_SMOKE_HEIGHT default [m above the floor].
HUMAN_SMOKE_HEIGHT_M = 1.6
_EULER_GAMMA = 0.5772156649015329
# Distributions whose sum with another one we can express exactly.
_EXACT = {"constant", "uniform", "gamma", "weibull"}

AddItem = Callable[..., None]


@dataclass(frozen=True)
class Component:
    """One FDS+Evac random quantity: our form, its moments, and its source."""

    kind: str
    a: float | None
    b: float | None
    mean: float
    var: float
    #: Fixed delay added to every draw (``premovement_offset_s``) [s].
    offset: float = 0.0


def component(keys: dict[str, Any], prefix: str, dist_key: str) -> Component | None:
    """Read ``<prefix>_*`` keys as a :class:`Component`; None if none is set."""
    if not any(k.startswith(prefix + "_") or k == dist_key for k in keys):
        return None
    dist = int(_num(keys, dist_key, 0))
    reader = _READERS.get(dist)
    if reader is None:
        raise ValueError(f"{dist_key}={dist} is not an FDS+Evac distribution index")
    return reader(keys, prefix)


def _num(keys: dict[str, Any], key: str, default: float | None = None) -> float:
    value = keys.get(key, default)
    if value is None:
        raise ValueError(f"{key} is required by the distribution but not given")
    return float(value)


# FDS+Evac's x_MEAN defaults: PRE_MEAN 10 s, DET_MEAN T_BEGIN (0 s here).
_MEAN_DEFAULTS = {"PRE": 10.0, "DET": 0.0, "VEL": 1.25}


def _constant(keys, p):
    mean = _num(keys, f"{p}_MEAN", _MEAN_DEFAULTS.get(p))
    return Component("constant", mean, None, mean, 0.0)


def _uniform(keys, p):
    lo, hi = _num(keys, f"{p}_LOW"), _num(keys, f"{p}_HIGH")
    return Component("uniform", lo, hi, (lo + hi) / 2, (hi - lo) ** 2 / 12)


def _truncated_normal(keys, p):
    mean, sd = _num(keys, f"{p}_MEAN"), _num(keys, f"{p}_PARA")
    return Component("truncated_normal", mean, sd, mean, sd * sd)


def _normal(keys, p):
    mean, sd = _num(keys, f"{p}_MEAN"), _num(keys, f"{p}_PARA")
    return Component("normal", mean, sd, mean, sd * sd)


def _gamma(keys, p):
    k, theta = _num(keys, f"{p}_PARA"), _num(keys, f"{p}_PARA2")
    return Component("gamma", k, theta, k * theta, k * theta * theta)


def _lognormal(keys, p):
    mu, sigma = _num(keys, f"{p}_MEAN"), _num(keys, f"{p}_PARA")
    x0 = _num(keys, f"{p}_PARA2", 0.0)
    mean = x0 + math.exp(mu + sigma * sigma / 2)
    var = (math.exp(sigma * sigma) - 1) * math.exp(2 * mu + sigma * sigma)
    return Component("lognormal", mu, sigma, mean, var)


def _beta(keys, p):
    a, b = _num(keys, f"{p}_PARA"), _num(keys, f"{p}_PARA2")
    var = a * b / ((a + b) ** 2 * (a + b + 1))
    return Component("beta", a, b, a / (a + b), var)


def _triangular(keys, p):
    peak, lo, hi = (_num(keys, f"{p}_{k}") for k in ("MEAN", "LOW", "HIGH"))
    var = (lo * lo + peak * peak + hi * hi - lo * peak - lo * hi - peak * hi) / 18
    return Component("triangular", peak, None, (lo + peak + hi) / 3, var)


def _weibull(keys, p):
    """FDS+Evac (alpha shape, lambda rate) -> ours (a = 1/lambda scale, b = alpha)."""
    alpha, lam = _num(keys, f"{p}_PARA"), _num(keys, f"{p}_PARA2")
    g1, g2 = math.gamma(1 + 1 / alpha), math.gamma(1 + 2 / alpha)
    return Component("weibull", 1 / lam, alpha, g1 / lam, (g2 - g1 * g1) / lam**2)


def _gumbel(keys, p):
    alpha = _num(keys, f"{p}_PARA")
    var = math.pi**2 / (6 * alpha * alpha)
    return Component("gumbel", alpha, None, _EULER_GAMMA / alpha, var)


_READERS = {
    0: _constant,
    1: _uniform,
    2: _truncated_normal,
    3: _gamma,
    4: _normal,
    5: _lognormal,
    6: _beta,
    7: _triangular,
    8: _weibull,
    9: _gumbel,
}


# --- speed -----------------------------------------------------------------


def speed_parameters(pers: NamelistRecord | None, add: AddItem) -> dict[str, Any]:
    """``v0`` keys from a ``&PERS``; empty when it sets no speed."""
    if pers is None:
        return {}
    if _preset_wins(pers):
        _note_ignored_vel_keys(pers, add)
        return _default_properties_speed(pers, add)
    speed = component(_scalars(pers), "VEL", "VELOCITY_DIST")
    if speed is None:
        return _default_properties_speed(pers, add)
    return _speed_from(speed, pers, add)


def _preset_wins(pers: NamelistRecord) -> bool:
    """FDS+Evac applies a DEFAULT_PROPERTIES speed only while VELOCITY_DIST
    is unset (-1, evac.f90:1645), and then overwrites VEL_MEAN/LOW/HIGH
    (``IF (VELOCITY_DIST < 0)``, evac.f90:1850-1857 for 'Adult'; FDS
    6.7.6-404-gc9da70d7a)."""
    name = pers.text("DEFAULT_PROPERTIES")
    known = name is not None and name.upper() in DEFAULT_PROPERTIES_SPEED
    return known and not pers.has("VELOCITY_DIST")


def _note_ignored_vel_keys(pers: NamelistRecord, add: AddItem) -> None:
    ignored = sorted(k for k in pers.params if k.startswith("VEL_"))
    if ignored:
        add(
            "A",
            "warning",
            "PERS",
            f"{', '.join(ignored)} ignored: without "
            "VELOCITY_DIST, FDS+Evac uses the DEFAULT_PROPERTIES speed",
            pers,
        )


def _scalars(record: NamelistRecord) -> dict[str, Any]:
    return {key: record.value(key) for key in record.params}


def _default_properties_speed(pers: NamelistRecord, add: AddItem) -> dict[str, Any]:
    name = pers.text("DEFAULT_PROPERTIES")
    if name is None:
        return {}
    preset = DEFAULT_PROPERTIES_SPEED.get(name.upper())
    if preset is None:
        add("D", "warning", "PERS", f"DEFAULT_PROPERTIES={name!r} is unknown", pers)
        return {}
    mean, half = preset
    std = half / math.sqrt(3)
    add(
        "A",
        "warning",
        "PERS",
        f"DEFAULT_PROPERTIES={name!r}: speed uniform {mean - half:g}..{mean + half:g} "
        f"m/s -> Gaussian v0={mean:g}, v0_std={std:.6g} (same mean and variance)",
        pers,
    )
    return {"v0": mean, "v0_distribution": "gaussian", "v0_std": round(std, 9)}


def _speed_from(speed: Component, pers: NamelistRecord, add: AddItem):
    if speed.kind == "constant":
        add("S", "info", "PERS", f"constant speed v0={speed.mean:g} m/s", pers)
        return {"v0": speed.mean, "v0_distribution": "constant"}
    std = math.sqrt(speed.var)
    note = {
        "uniform": "uniform -> Gaussian with the same mean and variance",
        "truncated_normal": "truncated normal -> Gaussian; LOW/HIGH cut-offs "
        "dropped, draws are clipped to [0.1, 5] m/s",
        "normal": "normal -> Gaussian",
    }.get(speed.kind)
    if note is None:
        add(
            "A",
            "warning",
            "PERS",
            f"{speed.kind} speed -> constant at its mean {speed.mean:g} m/s",
            pers,
        )
        return {"v0": speed.mean, "v0_distribution": "constant"}
    status = "S" if speed.kind == "normal" else "A"
    level = "info" if status == "S" else "warning"
    add(
        status,
        level,
        "PERS",
        f"speed {note}: v0={speed.mean:g}, v0_std={std:.6g}",
        pers,
    )
    return {"v0": speed.mean, "v0_distribution": "gaussian", "v0_std": round(std, 9)}


def body_size_parameters(pers: NamelistRecord, add: AddItem) -> dict[str, Any]:
    """``radius`` from a ``&PERS``: the mean torso radius R_t (#699).

    FDS+Evac applies the DEFAULT_PROPERTIES body only while DIAMETER_DIST is
    unset, i.e. below 0 (``IF (DIAMETER_DIST < 0)``, evac.f90:1858);
    otherwise the line's DIA_* keys and D_TORSO_MEAN (else 0.30 m) apply.
    Without either, a positive DIA_MEAN is a constant body (DIAMETER_DIST 0,
    evac.f90:1998). Empty when no branch defines a body.
    """
    name = pers.text("DEFAULT_PROPERTIES")
    preset = DEFAULT_PROPERTIES_BODY.get(name.upper()) if name else None
    explicit = pers.num("DIAMETER_DIST", -1) >= 0
    if name is not None and preset is None:
        why = f"DEFAULT_PROPERTIES={name!r} is not one of the five Guide presets"
        return _body_not_mapped(pers, add, why)
    if preset is not None and not explicit:
        _note_ignored_body_keys(
            pers,
            add,
            [k for k in pers.params if k.startswith("DIA_") or k in _TORSO_KEYS],
            "without DIAMETER_DIST, FDS+Evac uses the DEFAULT_PROPERTIES body",
        )
        return _preset_body(str(name), preset, pers, add)
    _note_ignored_body_keys(
        pers,
        add,
        [k for k in ("D_SHOULDER_MEAN",) if pers.has(k)],
        "the radius is the torso circle; the shoulder circles have no counterpart",
    )
    if explicit:
        return _explicit_body(pers, add)
    if pers.num("DIA_MEAN", -1) > 0:
        return _constant_body(pers, add)
    why = (
        "no known DEFAULT_PROPERTIES, no DIAMETER_DIST and no positive "
        "DIA_MEAN: FDS+Evac's body is undefined, clamped to 0.05 m"
    )
    return _body_not_mapped(pers, add, why)


_TORSO_KEYS = ("D_TORSO_MEAN", "D_SHOULDER_MEAN")
#: FDS+Evac clamps R_d at 0.05 m before scaling the torso (evac.f90:14669).
_MIN_BODY_RADIUS_M = 0.05


def _note_ignored_body_keys(
    pers: NamelistRecord, add: AddItem, ignored: list[str], why: str
) -> None:
    if ignored:
        add(
            "A", "warning", "PERS", f"{', '.join(sorted(ignored))} ignored: {why}", pers
        )


def _preset_body(name, preset, pers: NamelistRecord, add: AddItem) -> dict[str, Any]:
    dia, lo, hi, torso, shoulder = preset
    r_t = torso / 2
    t_lo, t_hi = r_t * lo / dia, r_t * hi / dia
    std = (t_hi - t_lo) / (2 * math.sqrt(3))
    add(
        "A",
        "warning",
        "PERS",
        f"DEFAULT_PROPERTIES={name!r}: body three circles R_d={dia / 2:g} "
        f"({lo / 2:g}-{hi / 2:g}), R_t={r_t:g}, R_s={shoulder / 2:g} m -> "
        f"radius={r_t:g} m (torso radius, constant; FDS+Evac draws R_t uniform "
        f"{t_lo:.4g}-{t_hi:.4g}, std {std:.6f}). Approximation: one circle as "
        f"deep as the FDS+Evac body but {torso:g} m wide instead of {dia:g} m; "
        f"with SocialForceModel R_d={dia / 2:g} m is the closer counterpart "
        f"({_BODY_SOURCE})",
        pers,
    )
    return {"radius": round(r_t, 9)}


def _constant_body(pers: NamelistRecord, add: AddItem) -> dict[str, Any]:
    """No preset and no DIAMETER_DIST: FDS+Evac sets DIAMETER_DIST to 0, so
    every agent has R_d = max(DIA_MEAN / 2, 0.05) and R_t = R_d * D_TORSO_MEAN
    / DIA_MEAN (evac.f90:1998, 14583-14584, 14669, 14955)."""
    _note_ignored_body_keys(
        pers,
        add,
        [k for k in ("DIA_LOW", "DIA_HIGH", "DIA_PARA", "DIA_PARA2") if pers.has(k)],
        "without DIAMETER_DIST, FDS+Evac's body diameter is the constant DIA_MEAN",
    )
    torso = pers.num("D_TORSO_MEAN", D_TORSO_MEAN_DEFAULT)
    dia = pers.num("DIA_MEAN", -1.0)
    radius = round(max(0.5 * dia, _MIN_BODY_RADIUS_M) * torso / dia, 9)
    if not (math.isfinite(radius) and radius > 0):
        why = f"max(DIA_MEAN / 2, 0.05) * D_TORSO_MEAN / DIA_MEAN = {radius:g} m"
        return _body_not_mapped(pers, add, why)
    add(
        "A",
        "warning",
        "PERS",
        f"DIA_MEAN={dia:g} m without DIAMETER_DIST: constant body (DIAMETER_DIST "
        f"0), FDS+Evac has no spread; D_TORSO_MEAN={torso:g} m -> "
        f"radius={radius:.6g} m (torso radius). Approximation: one circle as "
        f"deep as the FDS+Evac body but narrower than its shoulders "
        f"({_CONSTANT_SOURCE})",
        pers,
    )
    return {"radius": radius}


def _explicit_body(pers: NamelistRecord, add: AddItem) -> dict[str, Any]:
    """R_t,i = R_d,i * D_TORSO_MEAN / DIA_MEAN with R_d,i = max(D_i / 2, 0.05)
    (evac.f90:14669, 14955-14957), so the mean is 0.5 * D_TORSO_MEAN * E[D] /
    DIA_MEAN, clamped as one draw for a constant diameter; a negative DIA_MEAN
    means the distribution mean (evac.f90:2001-2020)."""
    torso = pers.num("D_TORSO_MEAN", D_TORSO_MEAN_DEFAULT)
    try:
        dia, d_mean, radius, std = _explicit_torso(pers, torso)
    except (ValueError, ArithmeticError) as exc:
        return _body_not_mapped(pers, add, f"{type(exc).__name__}: {exc}")
    if not (math.isfinite(radius) and radius > 0):
        why = f"R_d * D_TORSO_MEAN / DIA_MEAN = {radius:g} m"
        return _body_not_mapped(pers, add, why)
    spread = f"draws R_t with std {std:.6f} m"
    if dia.kind == "uniform":
        lo, hi = (0.5 * torso * float(x or 0.0) / d_mean for x in (dia.a, dia.b))
        spread = f"draws R_t uniform {lo:.4g}-{hi:.4g} m, std {std:.6f} m"
    if dia.kind == "constant":
        spread = "has no spread"
    add(
        "A",
        "warning",
        "PERS",
        f"DIAMETER_DIST: body diameter {dia.kind}, mean {dia.mean:g} m, "
        f"D_TORSO_MEAN={torso:g} m -> radius={radius:.6g} m (torso radius "
        f"R_d * D_TORSO_MEAN / {d_mean:g}, constant; FDS+Evac {spread}). "
        f"Approximation: one circle as deep as the FDS+Evac body but narrower "
        f"than its shoulders ({_EXPLICIT_SOURCE})",
        pers,
    )
    return {"radius": radius}


def _explicit_torso(
    pers: NamelistRecord, torso: float
) -> tuple[Component, float, float, float]:
    """Diameter distribution, D_mean, rounded mean R_t and its std; raises
    ValueError or ArithmeticError for a distribution with no usable mean."""
    dia = component(_scalars(pers), "DIA", "DIAMETER_DIST")
    if dia is None:
        raise ValueError("no body diameter")
    d_mean = pers.num("DIA_MEAN", -1.0)
    d_mean = dia.mean if d_mean < 0 else d_mean
    if not d_mean > 0:
        raise ValueError(f"body diameter mean {d_mean:g} m is not positive")
    r_d = 0.5 * dia.mean
    if dia.kind == "constant":
        r_d = max(r_d, _MIN_BODY_RADIUS_M)
    radius = round(r_d * torso / d_mean, 9)
    return dia, d_mean, radius, 0.5 * torso * math.sqrt(dia.var) / d_mean


def _body_not_mapped(pers: NamelistRecord, add: AddItem, why: str) -> dict[str, Any]:
    add(
        "D",
        "warning",
        "PERS",
        f"body not mapped ({why}); the 0.2 m loader default applies",
        pers,
    )
    return {}


# --- delay (detection + pre-movement) --------------------------------------


def delay_parameters(
    pers: NamelistRecord | None, group: NamelistRecord, add: AddItem, label: str
) -> dict[str, Any]:
    """Premovement keys from DET + PRE; empty when neither is set (Q2)."""
    keys = _delay_keys(pers)
    keys.update(_delay_keys(group))
    det = component(keys, "DET", "DET_EVAC_DIST")
    pre = component(keys, "PRE", "PRE_EVAC_DIST")
    if det is None and pre is None:
        return {}
    det = det or Component("constant", 0.0, None, 0.0, 0.0)
    pre = pre or Component("constant", 10.0, None, 10.0, 0.0)
    combined, status, how = combine_delays(det, pre)
    level = "info" if status == "S" else "warning"
    add(status, level, label, f"delay: detection + reaction = {how}", group)
    return _premovement_keys(combined)


def _delay_keys(record: NamelistRecord | None) -> dict[str, Any]:
    if record is None:
        return {}
    return {k: record.value(k) for k in record.params if k.startswith(("PRE_", "DET_"))}


def combine_delays(det: Component, pre: Component) -> tuple[Component, str, str]:
    """Sum of two independent delays as one of our distributions."""
    if det.kind == "constant" and pre.kind == "constant":
        total = det.mean + pre.mean
        return (
            Component("constant", total, None, total, 0.0),
            "S",
            f"constant {total:g} s",
        )
    constant, other = (det, pre) if det.kind == "constant" else (pre, det)
    if constant.kind == "constant":
        return _shift(constant.mean, other)
    if det.kind in _EXACT and pre.kind in _EXACT:
        return _offset_gamma(det, pre)
    return _at_mean(det.mean + pre.mean, det, pre)


def _offset_gamma(det: Component, pre: Component) -> tuple[Component, str, str]:
    """I1: FDS+Evac starts an agent at detection + reaction (evac.f90:9209),
    so nobody starts before min(detection) + min(reaction) (uniform low; 0
    for gamma or Weibull). That floor is the offset; a gamma carries the
    mean and variance of what lies above it, so both are kept exactly."""
    floor = _minimum(det) + _minimum(pre)
    rest = [
        Component(c.kind, c.a, c.b, c.mean - _minimum(c), c.var) for c in (det, pre)
    ]
    gamma, status, how = _moment_gamma(*rest)
    if floor <= 0:
        return gamma, status, how
    shifted = Component("gamma", gamma.a, gamma.b, gamma.mean + floor, gamma.var, floor)
    how = (
        f"{floor:g} s + gamma(k={gamma.a:.6g}, theta={gamma.b:.6g}), mean "
        f"{shifted.mean:.6g} s; variance {shifted.var:.6g} s2 kept; {det.kind} + "
        f"{pre.kind}, the offset is min detection + min reaction"
    )
    return shifted, status, how


def _minimum(part: Component) -> float:
    """Lower bound of a delay: the uniform's low, else 0 (gamma, Weibull)."""
    return float(part.a or 0.0) if part.kind == "uniform" else 0.0


def _shift(c: float, other: Component) -> tuple[Component, str, str]:
    if other.kind == "uniform":
        lo, hi = float(other.a or 0.0) + c, float(other.b or 0.0) + c
        shifted = Component("uniform", lo, hi, other.mean + c, other.var)
        return shifted, "S", f"uniform {lo:g}..{hi:g} s"
    if other.kind in ("gamma", "weibull") and c == 0:
        return other, "S", f"{other.kind} a={other.a:.6g}, b={other.b:.6g}"
    if other.kind in ("gamma", "weibull"):
        shifted = Component(other.kind, other.a, other.b, other.mean + c, other.var, c)
        how = f"offset {c:g} s + {other.kind} a={other.a:.6g}, b={other.b:.6g}"
        return shifted, "S", how
    return _at_mean(other.mean + c, other)


def _moment_gamma(*parts: Component) -> tuple[Component, str, str]:
    mean = sum(p.mean for p in parts)
    var = sum(p.var for p in parts)
    k, theta = mean * mean / var, var / mean
    how = (
        f"{' + '.join(p.kind for p in parts)} -> gamma with the same mean "
        f"{mean:.6g} s and variance {var:.6g} s2 (k={k:.6g}, theta={theta:.6g})"
    )
    return Component("gamma", k, theta, mean, var), "A", how


def _at_mean(mean: float, *parts: Component) -> tuple[Component, str, str]:
    how = f"{' + '.join(p.kind for p in parts)} -> constant at the mean {mean:.6g} s"
    return Component("constant", mean, None, mean, 0.0), "A", how


def _premovement_keys(delay: Component) -> dict[str, Any]:
    keys: dict[str, Any] = {
        "use_premovement": True,
        "premovement_distribution": delay.kind,
        "premovement_param_a": round(delay.a or 0.0, 9),
    }
    if delay.b is not None:
        keys["premovement_param_b"] = round(delay.b, 9)
    if delay.offset > 0:
        keys["premovement_offset_s"] = round(delay.offset, 9)
    return keys


# --- familiarity -----------------------------------------------------------


def familiarity_parameters(
    group: NamelistRecord,
    exit_ids: list[str],
    known_exits: list[str],
    add: AddItem,
    label: str,
) -> dict[str, Any]:
    """Q1 mapping of ``KNOWN_DOOR_NAMES``/``KNOWN_DOOR_PROBS``."""
    names = [str(n) for n in group.values("KNOWN_DOOR_NAMES")]
    probs = [float(p) for p in group.values("KNOWN_DOOR_PROBS")] or [1.0] * len(names)
    if len(probs) != len(names):
        add(
            "A",
            "warning",
            label,
            "KNOWN_DOOR_PROBS and KNOWN_DOOR_NAMES differ in "
            "length; every listed door taken as known",
            group,
        )
        probs = [1.0] * len(names)
    unknown = [n for n in names if n not in exit_ids]
    if unknown:
        add(
            "D",
            "warning",
            label,
            f"known doors not imported as exits: {unknown}",
            group,
        )
    known = {n: p for n, p in zip(names, probs, strict=True) if n in exit_ids and p > 0}
    known.update({e: 1.0 for e in known_exits if e in exit_ids})
    return _familiarity_for(known, exit_ids, group, add, label)


def _familiarity_for(known, exit_ids, group, add, label) -> dict[str, Any]:
    certain = sorted(n for n, p in known.items() if p >= 1.0)
    if not known:
        add(
            "A",
            "warning",
            label,
            "no known doors -> familiarity 'discovery'; agents "
            "find exits by signs read within 30 m, FDS+Evac by unlimited sight",
            group,
        )
        return {"familiarity": "discovery"}
    if len(certain) == len(known) and set(certain) == set(exit_ids):
        add("S", "info", label, "every exit known -> familiarity 'full'", group)
        return {"familiarity": "full"}
    if len(certain) == len(known) == 1:
        add(
            "S",
            "info",
            label,
            f"one known exit -> 'discovery', entrance {certain[0]!r}",
            group,
        )
        return {"familiarity": "discovery", "entrance": certain[0]}
    best = max(known, key=lambda n: (known[n], -list(known).index(n)))
    add(
        "A",
        "warning",
        label,
        f"known doors {dict(known)} cannot be expressed; "
        f"closest: 'discovery' with entrance {best!r}",
        group,
    )
    return {"familiarity": "discovery", "entrance": best}
