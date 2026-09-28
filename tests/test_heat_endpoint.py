"""Endpoint-coherent heat configuration, ``--heat-endpoint`` (#220).

Source: Purser & McAllister, SFPE Handbook 5th ed., Ch. 63,
doi:10.1007/978-1-4939-2565-0_63, book pp. 2382-2384. Each endpoint pairs a
radiant dose r [(kW/m2)^4/3 min] (Eq. 63.43, p. 2382 and p. 2384) with the
convective time law of the same endpoint:

    tolerance  r = 1.33   Eq. 63.45  t = 2e31 T^-16.963 + 4e8 T^-3.7561
    injury     r = 10     Eq. 63.46  t = 5e22 T^-11.783 + 3e7 T^-2.9636
    fatal      r = 16.7   Eq. 63.47  t = 2e18 T^-9.0403 + 1e8 T^-3.10898

t in min, T in deg C. The printed exponents are negative (the minus signs
are lost in text extraction); Table 63.21, whose values follow Eq. 63.45
although its caption says Eq. 63.44, and Table 63.20 confirm the sign
convention. Without ``--heat-endpoint`` the law stays Eq. 63.44,
t = 5e7 T^-3.4, exactly as before.

Expected values below come from these hand formulas and from the published
Tables 63.20 and 63.21, never from ``pyfds_evac``.

Assumed API (the implementation of #220 does not exist yet). If the
implementation names things differently, adapt the helpers in the "API
under test" block and drop the xfail markers; strict xfail only reports an
unexpected pass, it does not report a name mismatch.

- ``pyfds_evac.core.fed.HEAT_ENDPOINTS``: mapping ``name -> endpoint`` with
  ``.radiant_dose`` (float) and ``.equation`` (str, e.g. ``"63.45"``).
- ``DefaultHeatFedModel(field, config, endpoint=None)`` with an ``.endpoint``
  attribute (``None`` = Eq. 63.44).
- ``pyfds_evac.core.fed.HEAT_CONVECTIVE_VALIDITY_MAX_C``: upper temperature
  of the convective data (about 205 deg C, Table 63.17, p. 2375).
- ``pyfds_evac.core.fed.heat_temperature_outside_validity(T) -> bool``.
- ``run.py``: ``--heat-endpoint {tolerance,injury,fatal}``, dest
  ``heat_endpoint``, default ``None``.
- ``build_run_kwargs``: ``opts.heat_endpoint`` reaches the heat model.
"""

from __future__ import annotations

import math
import pathlib
import re
from argparse import Namespace
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultHeatFedModel,
    FdsHeatField,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
XFAIL_220 = pytest.mark.xfail(strict=True, reason="#220")
ENDPOINTS = ("tolerance", "injury", "fatal")


# --- hand formulas, SFPE Handbook 5th ed. Ch. 63 ---------------------------


def t_eq_63_44_min(t_c: float) -> float:
    """Eq. 63.44, time to incapacitation by convected heat (p. 2382)."""
    return 5e7 * t_c**-3.4


def t_tolerance_min(t_c: float) -> float:
    """Eq. 63.45, tolerance time, mid-humidity (p. 2382)."""
    return 2e31 * t_c**-16.963 + 4e8 * t_c**-3.7561


def t_injury_min(t_c: float) -> float:
    """Eq. 63.46, time to serious injury or severe incapacitation (p. 2383)."""
    return 5e22 * t_c**-11.783 + 3e7 * t_c**-2.9636


def t_fatal_min(t_c: float) -> float:
    """Eq. 63.47, time to fatal exposure, third-degree burns (p. 2383)."""
    return 2e18 * t_c**-9.0403 + 1e8 * t_c**-3.10898


HAND_LAW = {
    "tolerance": t_tolerance_min,
    "injury": t_injury_min,
    "fatal": t_fatal_min,
}

# (endpoint, r, equation), p. 2382 (list and text) and p. 2384 (Eq. 63.49).
PAIRS = [
    ("tolerance", 1.33, "63.45"),
    ("injury", 10.0, "63.46"),
    ("fatal", 16.7, "63.47"),
]


# --- API under test ---------------------------------------------------------


class _Sampler:
    """Duck-typed ``SliceFieldSampler``: ``sample(t, x, y)`` only."""

    def __init__(self, fn):
        self._fn = fn

    def sample(self, time_s, x, y):
        return float(self._fn(float(time_s), float(x), float(y)))


def _field(temperature_c: float) -> FdsHeatField:
    return FdsHeatField(_Sampler(lambda t, x, y: temperature_c))  # type: ignore[arg-type]


def _config() -> DefaultFedConfig:
    return DefaultFedConfig(fds_dir="", update_interval_s=1.0)


def _endpoint_model(temperature_c: float, endpoint: str):
    return DefaultHeatFedModel(_field(temperature_c), _config(), endpoint=endpoint)


def _endpoint_rate(temperature_c: float, endpoint: str) -> float:
    _, rate = _endpoint_model(temperature_c, endpoint).sample_rate(0.0, 0.0, 0.0)
    return rate


def _endpoints():
    from pyfds_evac.core.fed import HEAT_ENDPOINTS

    return HEAT_ENDPOINTS


def _outside_validity(temperature_c: float) -> bool:
    from pyfds_evac.core.fed import heat_temperature_outside_validity

    return heat_temperature_outside_validity(temperature_c)


# --- default stays Eq. 63.44 (passes now) ----------------------------------


@pytest.mark.parametrize("t_c", [20.0, 65.0, 100.0, 150.0, 205.0, 405.0])
def test_default_model_is_eq_63_44(t_c):
    """Without an endpoint the rate is 1 / Eq. 63.44, unchanged by #220."""
    model = DefaultHeatFedModel(_field(t_c), _config())
    _, rate = model.sample_rate(0.0, 0.0, 0.0)
    assert rate == pytest.approx(1.0 / t_eq_63_44_min(t_c), rel=1e-12)


def test_cli_heat_endpoint_is_absent_by_default():
    """Opt-in: a run without ``--heat-endpoint`` keeps Eq. 63.44."""
    import run

    args = run._build_parser().parse_args(["--scenario", "x", "--enable-heat-fed"])
    assert getattr(args, "heat_endpoint", None) is None


# --- hand formulas against the published tables (passes now) ---------------


def test_table_63_21_follows_eq_63_45():
    """Table 63.21 (p. 2385) is Eq. 63.45, not Eq. 63.44 as its caption says.

    This pins the tolerance law used for the tolerance endpoint to published
    numbers; the Eq. 63.44 rate misses them (e.g. 0.27 vs 0.19 at 125 deg C).
    """
    per_minute = {65.0: 0.02, 125.0: 0.19, 220.0: 1.57, 405.0: 15.55}
    for t_c, fih in per_minute.items():
        assert round(1.0 / t_tolerance_min(t_c), 2) == fih
    assert round(1.0 / t_eq_63_44_min(125.0), 2) != per_minute[125.0]


@pytest.mark.parametrize(
    ("t_c", "table_min"),
    [(100.0, 12.0), (120.0, 7.0), (140.0, 4.0), (160.0, 2.0), (180.0, 1.0)],
)
def test_table_63_20_convective_rows_bound_eq_63_45(t_c, table_min):
    """Table 63.20 (p. 2383), < 10 % H2O: Eq. 63.45 within a factor of 1.5.

    A loose band: at 180 deg C Eq. 63.45 gives 1.35 min against 1 min.
    """
    assert table_min / 1.5 <= t_tolerance_min(t_c) <= table_min * 1.5


def test_endpoint_laws_are_ordered():
    """Tolerance comes before injury, injury before death, at every T."""
    for t_c in range(60, 401, 5):
        tol, inj, fat = t_tolerance_min(t_c), t_injury_min(t_c), t_fatal_min(t_c)
        assert tol < inj < fat, t_c


# --- endpoint pairs ---------------------------------------------------------


@XFAIL_220
@pytest.mark.parametrize(("name", "r", "equation"), PAIRS)
def test_endpoint_pairs_radiant_dose_with_its_convective_law(name, r, equation):
    """Each endpoint pairs r (Eq. 63.43) with the convective law of the same endpoint.

    Fatal: the Handbook prints 16.7; 16.667 (spec 016) is accepted too.
    """
    endpoint = _endpoints()[name]
    assert endpoint.radiant_dose == pytest.approx(r, abs=0.04)
    assert endpoint.equation == equation


@XFAIL_220
def test_endpoint_names_are_exactly_the_three_endpoints():
    assert set(_endpoints()) == set(ENDPOINTS)


@XFAIL_220
@pytest.mark.parametrize("name", ENDPOINTS)
@pytest.mark.parametrize("t_c", [40.0, 65.0, 100.0, 125.0, 150.0, 205.0, 405.0])
def test_endpoint_rate_is_its_convective_law(name, t_c):
    """The rate is 1 / t_endpoint(T); radiant flux is not an input yet (#221-#223)."""
    expected = 1.0 / HAND_LAW[name](t_c)
    assert _endpoint_rate(t_c, name) == pytest.approx(expected, rel=1e-9)


@XFAIL_220
@pytest.mark.parametrize("name", ENDPOINTS)
def test_endpoint_is_recorded_on_the_model(name):
    assert _endpoint_model(100.0, name).endpoint == name


def test_default_model_has_no_endpoint():
    """Passes now through ``getattr``; must stay ``None`` after #220."""
    model = DefaultHeatFedModel(_field(100.0), _config())
    assert getattr(model, "endpoint", None) is None


@XFAIL_220
def test_unknown_endpoint_is_rejected():
    with pytest.raises(ValueError):
        _endpoint_model(100.0, "pain")


@XFAIL_220
@pytest.mark.parametrize("name", ENDPOINTS)
@pytest.mark.parametrize("t_c", [0.0, -10.0, float("nan"), float("inf")])
def test_endpoint_rate_domain_guard(name, t_c):
    """No complex numbers, no ZeroDivisionError: out-of-domain T gives 0."""
    rate = _endpoint_rate(t_c, name)
    assert isinstance(rate, float)
    assert rate == 0.0


@XFAIL_220
def test_tolerance_endpoint_reproduces_table_63_21_cumulative():
    """Summed per-minute doses of Table 63.21 (p. 2385) under the tolerance endpoint.

    The table's cumulative row sums its rounded per-minute values, hence the
    0.01 tolerance (exact sums: 0.20, 1.77, 17.33, 32.88).
    """
    temperatures = [20.0, 65.0, 125.0, 220.0, 405.0, 405.0]
    published = {3: 0.21, 4: 1.78, 5: 17.33, 6: 32.88}
    cumulative = 0.0
    history = []
    for minute, t_c in enumerate(temperatures, start=1):
        cumulative += _endpoint_rate(t_c, "tolerance")
        history.append(cumulative)
        if minute in published:
            assert cumulative == pytest.approx(published[minute], abs=0.011)
    # FED = 1 is crossed during the fourth minute, as the Handbook states.
    assert history[2] < 1.0 <= history[3]


@XFAIL_220
def test_fatal_endpoint_differs_from_default():
    """At 150 deg C the fatal law is 8.6x slower than Eq. 63.44."""
    ratio = t_fatal_min(150.0) / t_eq_63_44_min(150.0)
    assert ratio > 8.0
    fatal = _endpoint_rate(150.0, "fatal")
    default = 1.0 / t_eq_63_44_min(150.0)
    assert fatal == pytest.approx(default / ratio, rel=1e-9)


# --- validity range ---------------------------------------------------------


@XFAIL_220
def test_validity_limit_is_the_highest_convective_data_point():
    """Table 63.17 (p. 2375): highest dry-air point is 205 deg C (Veghte)."""
    from pyfds_evac.core.fed import HEAT_CONVECTIVE_VALIDITY_MAX_C

    assert 200.0 <= HEAT_CONVECTIVE_VALIDITY_MAX_C <= 210.0


@XFAIL_220
@pytest.mark.parametrize(
    ("t_c", "outside"),
    [(20.0, False), (100.0, False), (180.0, False), (250.0, True), (405.0, True)],
)
def test_samples_above_the_data_are_flagged(t_c, outside):
    assert _outside_validity(t_c) is outside


@XFAIL_220
@pytest.mark.parametrize("name", ENDPOINTS)
def test_flag_does_not_change_the_rate(name):
    """Table 63.21 applies the law at 405 deg C: flag, do not clip."""
    assert _outside_validity(405.0)
    assert _endpoint_rate(405.0, name) == pytest.approx(
        1.0 / HAND_LAW[name](405.0), rel=1e-9
    )


# --- CLI and run_config -----------------------------------------------------


@XFAIL_220
def test_cli_heat_endpoint_choices():
    import run

    parser = run._build_parser()
    for name in ENDPOINTS:
        args = parser.parse_args(
            ["--scenario", "x", "--enable-heat-fed", "--heat-endpoint", name]
        )
        assert args.heat_endpoint == name
    with pytest.raises(SystemExit):
        parser.parse_args(["--scenario", "x", "--heat-endpoint", "pain"])


_OPTS = dict(
    seed=None,
    fds_dir="fds_data",
    constant_extinction=0.0,
    smoke_update_interval=1.0,
    smoke_slice_height=2.0,
    enable_rerouting=False,
    reroute_interval=1.0,
    vis_cache=None,
    disable_tenability=False,
    fic_alpha=1.2,
    fic_min_factor=0.0,
    fed_threshold=1.0,
    output_route_cost_history=None,
)


class _TemperatureOnlyInventory:
    def supports_default_fed(self):
        return False

    def supports_heat_fed(self):
        return True

    def canonical_slice_names(self):
        return {"temperature"}


@pytest.fixture
def temperature_only_case(monkeypatch):
    import pyfds_evac.core.run_config as run_config

    monkeypatch.setattr(
        run_config, "inspect_fds_quantities", lambda _d: _TemperatureOnlyInventory()
    )
    monkeypatch.setattr(
        run_config.FdsHeatField,
        "from_fds",
        classmethod(lambda cls, _d, slice_height_m=1.6: cls(sampler=None)),
    )


def _build(**overrides):
    from pyfds_evac.core.run_config import build_run_kwargs

    return build_run_kwargs(
        SimpleNamespace(raw={}), Namespace(**{**_OPTS, **overrides})
    )


def test_run_config_without_endpoint_keeps_eq_63_44(temperature_only_case):
    model = _build(enable_heat_fed=True)["heat_fed_model"]
    assert getattr(model, "endpoint", None) is None


@XFAIL_220
@pytest.mark.parametrize("name", ENDPOINTS)
def test_run_config_passes_the_endpoint(temperature_only_case, name):
    model = _build(enable_heat_fed=True, heat_endpoint=name)["heat_fed_model"]
    assert model.endpoint == name


def test_endpoint_without_enable_heat_fed_leaves_heat_off(temperature_only_case):
    """Heat stays opt-in: ``--heat-endpoint`` alone does not switch it on."""
    assert _build(heat_endpoint="fatal")["heat_fed_model"] is None


# --- docs -------------------------------------------------------------------


@XFAIL_220
def test_models_heat_page_documents_the_endpoint_option():
    text = (ROOT / "site" / "content" / "models" / "heat.md").read_text()
    assert "--heat-endpoint" in text
    for equation in ("63.45", "63.46", "63.47"):
        assert equation in text
    assert re.search(r"205\s*°C", text)


@XFAIL_220
def test_changelog_mentions_the_endpoint_option():
    text = (ROOT / "CHANGELOG.md").read_text()
    unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert "--heat-endpoint" in unreleased


def test_hand_formulas_are_finite_on_the_test_range():
    """Guard for the oracles themselves."""
    for law in (t_eq_63_44_min, *HAND_LAW.values()):
        for t_c in (40.0, 205.0, 405.0):
            assert math.isfinite(law(t_c)) and law(t_c) > 0.0
