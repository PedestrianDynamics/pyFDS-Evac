"""Total-flux heat method, ``--heat-fed-method total-flux`` (#223, spec 016).

Source: Purser & McAllister, SFPE Handbook 5th ed., Ch. 63,
doi:10.1007/978-1-4939-2565-0_63, book pp. 2382-2384, and spec 016
(``specs/016-heat-fed/SPEC.md``). The heat flux to the skin is Eq. 63.49 with
both terms in W/m2 divided together (spec 016; the Handbook prints ``/1000``
on the convective term only):

    q = [eps sigma (T_g^4 - T_s^4) + h (T_g - T_s)] / 1000 + q_ext   [kW/m2]

T in K, sigma = 5.67e-8 W m^-2 K^-4 (p. 2384). The time to the endpoint is
Eq. 63.43, t = D / q^1.33 [min], with D the radiant dose r of the endpoint
(1.33 tolerance, 10 injury, 16.667 fatal; pp. 2382, 2384; the Handbook
prints the fatal dose as 16.7, spec 016 fixes it at 16.667). The dose is
summed, FED = sum dt / t. Differences from the Handbook text, by spec 016:

- no 2.5 kW/m2 threshold: the dose accumulates at every positive flux;
- mutually exclusive with the convective laws: never 1/t_conv on top;
- FED = 1 is the fatal endpoint by maintainer decision, so the method uses
  the fatal D when ``--heat-endpoint`` is not given.

Only the "head in smoke" regime is covered: T_g is the temperature at the
head, q_ext = 0. The "below a hot layer" regime needs the layer flux of #222
(or the ``INTEGRATED INTENSITY`` input of #221) and is not tested here; q_ext
is tested only as an argument of the pure flux function.

h, T_skin and eps have no sourced values (h "5-8" with no unit and eps
"perhaps 0.5 for smoke", p. 2384; T_skin not given for Eq. 63.49). Every
numeric test below passes them explicitly, so the defaults can change
without breaking a test; the defaults are only checked to be flagged as
assumptions.

Expected values are hand formulas written in this file and published
numbers (spec 016 convection table, the issue's 2.5 kW/m2 points, Table 63.20
radiant rows), never ``pyfds_evac``.

API under test:

- ``pyfds_evac.core.fed.total_heat_flux_kw_m2(gas_temperature_celsius, *,
  emissivity, convective_coefficient, skin_temperature_celsius,
  external_flux_kw_m2=0.0) -> float``: q in kW/m2, may be negative.
- ``pyfds_evac.core.fed.total_flux_heat_fed_rate_per_minute(q_kw_m2, dose)
  -> float``: q^1.33 / dose in 1/min; 0.0 for q <= 0 or non-finite q.
- ``DefaultHeatFedModel(field, config, endpoint=None, method="convective",
  emissivity=..., convective_coefficient=..., skin_temperature_celsius=...)``
  with attributes ``.method``, ``.emissivity``, ``.convective_coefficient``,
  ``.skin_temperature_celsius``. ``method="convective"`` (default) is the
  behaviour before #223; ``method="total-flux"`` uses the flux law.
  Invalid parameters (eps outside [0, 1], h < 0, non-finite) raise ValueError.
- ``run.py``: ``--heat-fed-method {convective,total-flux}`` (dest
  ``heat_fed_method``, default ``"convective"``), ``--heat-emissivity``,
  ``--heat-convective-coefficient``, ``--heat-skin-temperature``.
- ``build_run_kwargs`` passes them to the heat model.
- ``pyfds_evac.core.fed.HEAT_FLUX_ASSUMED_PARAMETERS``: the names of the
  parameters whose defaults are assumptions, at least the three above.
"""

from __future__ import annotations

import math
import pathlib
import re
from argparse import Namespace
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fed import DefaultFedConfig, DefaultHeatFedModel, FdsHeatField

ROOT = pathlib.Path(__file__).resolve().parents[1]

SIGMA = 5.67e-8  # W m^-2 K^-4, as printed on p. 2384
KELVIN = 273.15
EXPONENT = 1.33  # Eqs. 63.43 and 63.49 print 1.33, not 4/3
# Fatal: spec 016 maintainer decision, D = 16.667 (the Handbook prints 16.7).
DOSE = {"tolerance": 1.33, "injury": 10.0, "fatal": 16.667}


# --- hand formulas ----------------------------------------------------------


def q_hand(t_gas_c, *, eps, h, t_skin_c, q_ext=0.0):
    """Eq. 63.49 in kW/m2, both terms in W/m2 divided together (spec 016)."""
    tg, ts = t_gas_c + KELVIN, t_skin_c + KELVIN
    return (eps * SIGMA * (tg**4 - ts**4) + h * (tg - ts)) / 1000.0 + q_ext


def t_hand_min(q, dose):
    """Eq. 63.43, t = D / q^1.33 [min]."""
    return dose / q**EXPONENT


def t_eq_63_44_min(t_c):
    """Eq. 63.44, p. 2382."""
    return 5e7 * t_c**-3.4


def t_fatal_conv_min(t_c):
    """Eq. 63.47, p. 2383."""
    return 2e18 * t_c**-9.0403 + 1e8 * t_c**-3.10898


# --- the hand formulas against published numbers ---------------------------


@pytest.mark.parametrize(
    ("t_c", "minutes"), [(100.0, 6.0), (120.0, 4.2), (140.0, 3.2), (180.0, 2.1)]
)
def test_hand_formula_reproduces_spec_convection_table(t_c, minutes):
    """Spec 016 "Convection check": eps = 0, h = 5, T_s = 36 deg C, D = 1.33.

    The spec prints one decimal (6.05 min at 100 deg C as 6.0).
    """
    q = q_hand(t_c, eps=0.0, h=5.0, t_skin_c=36.0)
    assert t_hand_min(q, DOSE["tolerance"]) == pytest.approx(minutes, abs=0.06)


@pytest.mark.parametrize(("t_c", "eps"), [(201.0, 0.5), (310.0, 0.05)])
def test_hand_formula_reproduces_issue_threshold_points(t_c, eps):
    """#223: with h = 8, T_s = 35 deg C, q = 2.5 kW/m2 at 201 deg C in smoke
    (eps = 0.5) and 310 deg C in clear air (eps = 0.05)."""
    q = q_hand(t_c, eps=eps, h=8.0, t_skin_c=35.0)
    assert q == pytest.approx(2.5, abs=0.02)


@pytest.mark.parametrize(("q", "table_s"), [(2.5, 30.0), (10.0, 4.0)])
def test_hand_formula_bounds_table_63_20_radiant_rows(q, table_s):
    """Table 63.20 (p. 2383), radiation: 2.5 kW/m2 -> 30 s, 10 kW/m2 -> 4 s.

    Eq. 63.43 with the tolerance dose gives 24 s and 3.7 s; band 25 %.
    """
    seconds = 60.0 * t_hand_min(q, DOSE["tolerance"])
    assert table_s * 0.75 <= seconds <= table_s * 1.25


def test_hand_formula_radiant_term_matters_in_smoke():
    """p. 2384: the radiant term is negligible in hot air (eps 0.05) but not
    in smoke (eps 0.5). At 150 deg C, h = 5, T_s = 35 deg C."""
    air = q_hand(150.0, eps=0.05, h=5.0, t_skin_c=35.0)
    smoke = q_hand(150.0, eps=0.5, h=5.0, t_skin_c=35.0)
    convective = q_hand(150.0, eps=0.0, h=5.0, t_skin_c=35.0)
    assert (air - convective) / air < 0.15
    assert (smoke - convective) / smoke > 0.45
    assert smoke == pytest.approx(1.228, abs=0.002)


# --- API helpers ------------------------------------------------------------


class _Sampler:
    """Duck-typed ``SliceFieldSampler``: ``sample(t, x, y)`` only."""

    def __init__(self, value):
        self._value = value

    def sample(self, time_s, x, y):
        return float(self._value)


def _model(t_c, *, eps, h, t_skin_c, endpoint=None, method="total-flux"):
    field = FdsHeatField(_Sampler(t_c))  # type: ignore[arg-type]
    config = DefaultFedConfig(fds_dir="", update_interval_s=1.0)
    return DefaultHeatFedModel(
        field,
        config,
        endpoint=endpoint,
        method=method,
        emissivity=eps,
        convective_coefficient=h,
        skin_temperature_celsius=t_skin_c,
    )


def _rate(t_c, **kwargs):
    _, rate = _model(t_c, **kwargs).sample_rate(0.0, 0.0, 0.0)
    return rate


def _flux(*args, **kwargs):
    from pyfds_evac.core.fed import total_heat_flux_kw_m2

    return total_heat_flux_kw_m2(*args, **kwargs)


def _flux_rate(q, dose):
    from pyfds_evac.core.fed import total_flux_heat_fed_rate_per_minute

    return total_flux_heat_fed_rate_per_minute(q, dose)


# --- current behaviour stays ------------------------------------------------


def test_cli_default_method_is_not_total_flux():
    """Opt-in: ``--enable-heat-fed`` alone keeps the convective law."""
    import run

    args = run._build_parser().parse_args(["--scenario", "x", "--enable-heat-fed"])
    assert getattr(args, "heat_fed_method", None) in (None, "convective")


@pytest.mark.parametrize("t_c", [65.0, 150.0, 405.0])
def test_default_model_is_still_eq_63_44(t_c):
    field = FdsHeatField(_Sampler(t_c))  # type: ignore[arg-type]
    model = DefaultHeatFedModel(
        field, DefaultFedConfig(fds_dir="", update_interval_s=1.0)
    )
    _, rate = model.sample_rate(0.0, 0.0, 0.0)
    assert rate == pytest.approx(1.0 / t_eq_63_44_min(t_c), rel=1e-12)


# --- flux -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("t_c", "eps", "h", "t_skin_c"),
    [
        (150.0, 0.5, 5.0, 35.0),
        (100.0, 0.05, 8.0, 35.0),
        (201.0, 0.5, 8.0, 35.0),
        (310.0, 0.05, 8.0, 35.0),
        (120.0, 0.0, 5.0, 36.0),
        (400.0, 0.9, 5.0, 37.0),
    ],
)
def test_flux_is_eq_63_49_with_both_terms_in_w(t_c, eps, h, t_skin_c):
    """Both terms divided by 1000 together: 1.228 kW/m2 at 150 deg C, eps 0.5,
    h = 5, T_s = 35 deg C; the printed form would give about 653."""
    got = _flux(
        t_c, emissivity=eps, convective_coefficient=h, skin_temperature_celsius=t_skin_c
    )
    assert got == pytest.approx(q_hand(t_c, eps=eps, h=h, t_skin_c=t_skin_c), rel=1e-9)


def test_flux_units_catch_the_printed_form():
    got = _flux(
        150.0, emissivity=0.5, convective_coefficient=5.0, skin_temperature_celsius=35.0
    )
    assert 1.2 < got < 1.3


def test_flux_adds_external_radiation():
    """q_ext (kW/m2) is added to the flux of the gas around the head."""
    got = _flux(
        150.0,
        emissivity=0.5,
        convective_coefficient=5.0,
        skin_temperature_celsius=35.0,
        external_flux_kw_m2=2.0,
    )
    assert got == pytest.approx(
        q_hand(150.0, eps=0.5, h=5.0, t_skin_c=35.0, q_ext=2.0), rel=1e-9
    )


def test_flux_is_zero_at_skin_temperature():
    got = _flux(
        35.0, emissivity=0.5, convective_coefficient=5.0, skin_temperature_celsius=35.0
    )
    assert got == pytest.approx(0.0, abs=1e-12)


# --- rate: Eq. 63.43, no threshold ------------------------------------------


@pytest.mark.parametrize("name", sorted(DOSE))
@pytest.mark.parametrize("q", [0.1, 1.0, 2.5, 10.0])
def test_rate_is_q_to_the_1_33_over_dose(name, q):
    """Exponent 1.33 as printed; 4/3 would be 0.8 % off at 10 kW/m2."""
    assert _flux_rate(q, DOSE[name]) == pytest.approx(
        1.0 / t_hand_min(q, DOSE[name]), rel=1e-9
    )


@pytest.mark.parametrize(("q", "table_s"), [(2.5, 30.0), (10.0, 4.0)])
def test_rate_bounds_table_63_20_radiant_rows(q, table_s):
    """Table 63.20 (p. 2383) through the code, tolerance dose; band 25 %."""
    seconds = 60.0 / _flux_rate(q, DOSE["tolerance"])
    assert table_s * 0.75 <= seconds <= table_s * 1.25


@pytest.mark.parametrize("q", [0.05, 0.5, 1.0, 2.0, 2.49])
def test_no_threshold_below_2_5_kw(q):
    """Spec 016: no 2.5 kW/m2 threshold; the dose accumulates below it."""
    rate = _flux_rate(q, DOSE["fatal"])
    assert rate > 0.0
    assert rate == pytest.approx(1.0 / t_hand_min(q, DOSE["fatal"]), rel=1e-9)


@pytest.mark.parametrize(
    "q", [0.0, -0.5, -10.0, float("nan"), float("inf"), -float("inf")]
)
def test_rate_domain_guard(q):
    """q <= 0 (gas cooler than skin) or non-finite gives 0, never complex."""
    rate = _flux_rate(q, DOSE["fatal"])
    assert isinstance(rate, float)
    assert rate == 0.0


# --- the model in total-flux mode -------------------------------------------


@pytest.mark.parametrize("name", sorted(DOSE))
@pytest.mark.parametrize(
    ("t_c", "eps", "h", "t_skin_c"),
    [(100.0, 0.05, 8.0, 35.0), (150.0, 0.5, 5.0, 35.0), (250.0, 0.5, 8.0, 36.0)],
)
def test_model_rate_uses_the_endpoint_dose(name, t_c, eps, h, t_skin_c):
    q = q_hand(t_c, eps=eps, h=h, t_skin_c=t_skin_c)
    expected = 1.0 / t_hand_min(q, DOSE[name])
    got = _rate(t_c, eps=eps, h=h, t_skin_c=t_skin_c, endpoint=name)
    assert got == pytest.approx(expected, rel=1e-9)


def test_model_without_endpoint_uses_the_fatal_dose():
    """FED = 1 = fatal (spec 016 maintainer decision): D = 16.667."""
    q = q_hand(150.0, eps=0.5, h=5.0, t_skin_c=35.0)
    got = _rate(150.0, eps=0.5, h=5.0, t_skin_c=35.0)
    assert got == pytest.approx(1.0 / t_hand_min(q, DOSE["fatal"]), rel=1e-9)


@pytest.mark.parametrize("name", sorted(DOSE))
def test_no_convective_law_on_top(name):
    """Mutually exclusive: the rate is q^1.33/D alone, not plus 1/t_conv."""
    t_c = 150.0
    q = q_hand(t_c, eps=0.5, h=5.0, t_skin_c=35.0)
    flux_only = 1.0 / t_hand_min(q, DOSE[name])
    got = _rate(t_c, eps=0.5, h=5.0, t_skin_c=35.0, endpoint=name)
    assert got == pytest.approx(flux_only, rel=1e-9)
    for t_conv in (t_eq_63_44_min(t_c), t_fatal_conv_min(t_c)):
        assert not math.isclose(got, flux_only + 1.0 / t_conv, rel_tol=1e-2)


def test_model_no_threshold_in_clear_air():
    """#223 gap: 100 deg C, eps 0.05, h 8 gives q < 2.5 kW/m2 and still a dose."""
    q = q_hand(100.0, eps=0.05, h=8.0, t_skin_c=35.0)
    assert q < 2.5
    assert _rate(100.0, eps=0.05, h=8.0, t_skin_c=35.0) > 0.0


@pytest.mark.parametrize("t_c", [20.0, 35.0, 0.0, -10.0, float("nan"), float("inf")])
def test_model_domain_guard(t_c):
    """Gas at or below skin temperature, or non-finite: no dose, no recovery."""
    rate = _rate(t_c, eps=0.5, h=5.0, t_skin_c=35.0)
    assert isinstance(rate, float)
    assert rate == 0.0


def test_model_records_its_parameters():
    model = _model(150.0, eps=0.3, h=6.5, t_skin_c=34.0)
    assert model.method == "total-flux"
    assert (model.emissivity, model.convective_coefficient) == (0.3, 6.5)
    assert model.skin_temperature_celsius == 34.0


def test_model_default_method_is_convective():
    field = FdsHeatField(_Sampler(150.0))  # type: ignore[arg-type]
    model = DefaultHeatFedModel(
        field, DefaultFedConfig(fds_dir="", update_interval_s=1.0)
    )
    assert model.method == "convective"


@pytest.mark.parametrize(
    ("eps", "h"),
    [(-0.1, 5.0), (1.1, 5.0), (0.5, -1.0), (float("nan"), 5.0), (0.5, float("inf"))],
)
def test_model_rejects_invalid_parameters(eps, h):
    with pytest.raises(ValueError):
        _model(150.0, eps=eps, h=h, t_skin_c=35.0)


def test_model_rejects_unknown_method():
    with pytest.raises((ValueError, TypeError)):
        _model(150.0, eps=0.5, h=5.0, t_skin_c=35.0, method="summed")


# --- CLI and run_config ------------------------------------------------------


def test_cli_method_and_parameters():
    import run

    args = run._build_parser().parse_args(
        [
            "--scenario",
            "x",
            "--enable-heat-fed",
            "--heat-fed-method",
            "total-flux",
            "--heat-emissivity",
            "0.3",
            "--heat-convective-coefficient",
            "6.5",
            "--heat-skin-temperature",
            "34",
        ]
    )
    assert args.heat_fed_method == "total-flux"
    assert (args.heat_emissivity, args.heat_convective_coefficient) == (0.3, 6.5)
    assert args.heat_skin_temperature == 34.0


def test_cli_rejects_unknown_method():
    import run

    parser = run._build_parser()
    parser.parse_args(["--scenario", "x", "--heat-fed-method", "total-flux"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--scenario", "x", "--heat-fed-method", "summed"])


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


def test_run_config_passes_method_and_parameters(temperature_only_case):
    model = _build(
        enable_heat_fed=True,
        heat_fed_method="total-flux",
        heat_emissivity=0.3,
        heat_convective_coefficient=6.5,
        heat_skin_temperature=34.0,
    )["heat_fed_model"]
    assert model.method == "total-flux"
    assert (model.emissivity, model.convective_coefficient) == (0.3, 6.5)
    assert model.skin_temperature_celsius == 34.0


def test_run_config_default_method_is_convective(temperature_only_case):
    assert _build(enable_heat_fed=True)["heat_fed_model"].method == "convective"


def test_method_without_enable_heat_fed_leaves_heat_off(temperature_only_case):
    """Heat stays opt-in: the method alone does not switch it on."""
    assert _build(heat_fed_method="total-flux")["heat_fed_model"] is None


# --- assumptions are flagged ------------------------------------------------


def test_unsourced_defaults_are_listed_as_assumptions():
    from pyfds_evac.core.fed import HEAT_FLUX_ASSUMED_PARAMETERS

    assert {
        "emissivity",
        "convective_coefficient",
        "skin_temperature_celsius",
    } <= set(HEAT_FLUX_ASSUMED_PARAMETERS)


def test_cli_help_marks_defaults_as_assumptions():
    import run

    help_text = run._build_parser().format_help()
    for option in (
        "--heat-emissivity",
        "--heat-convective-coefficient",
        "--heat-skin-temperature",
    ):
        # Anchor on the options list; the first occurrence is the usage line.
        block = help_text.split("\n  " + option, 1)[1].split("\n  --", 1)[0]
        assert "assum" in block.lower(), option


# --- docs --------------------------------------------------------------------


def test_models_heat_page_documents_total_flux():
    text = (ROOT / "site" / "content" / "models" / "heat.md").read_text()
    assert "--heat-fed-method" in text and "total-flux" in text
    assert "63.49" in text
    assert re.search(r"assum", text, re.IGNORECASE)
    assert "#222" in text or "issues/222" in text


def test_changelog_mentions_total_flux():
    text = (ROOT / "CHANGELOG.md").read_text()
    unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert "--heat-fed-method" in unreleased
