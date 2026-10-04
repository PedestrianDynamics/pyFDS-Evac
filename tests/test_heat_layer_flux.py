"""Radiant flux from a hot upper layer, ``--heat-regime layer`` (#222, spec 016).

Source: Purser & McAllister, SFPE Handbook 5th ed., Ch. 63,
doi:10.1007/978-1-4939-2565-0_63, book pp. 2382-2384, and spec 016
(``specs/016-heat-fed/SPEC.md``, "Regimes"). The Handbook says only that a
subject "in air (with a low emissivity), below a hot smoke layer" receives
significant radiation from "the upper layer, the fire, or hot surfaces"
(p. 2384), and that 2.5 kW/m2 "corresponds approximately to a hot layer
temperature of 200 deg C" (p. 2382). The layer term is the radiant term of
Eq. 63.49 with the layer as source, T_i = T_L, and a view factor:

    q_ext = phi eps_L sigma (T_L^4 - T_s^4) / 1000               [kW/m2]

T in K, sigma = 5.67e-8 W m^-2 K^-4 (p. 2384). phi (about 1 for the crown,
about 0.5 for the face, spec 016) and eps_L have no sourced values. This is a
net flux (sigma T^4 difference), not the incident flux of the tolerance data.
The issue body's draft carries a (1 - eps_s) factor; the rescoped issue and
spec 016 drop it, and so do these tests.

Regimes (spec 016), chosen by the user; no automatic rule is sourced:

- ``smoke`` (default, the #223 behaviour): the head is in smoke,
  q = [eps sigma (T_g^4 - T_s^4) + h (T_g - T_s)] / 1000, no layer term.
- ``layer``: the head is in clear air below a hot layer. Convection from the
  temperature at the head plus the layer term, and **no** eps sigma term of
  the gas at the head:

      q = h (T_g - T_s) / 1000 + q_ext

  Adding q_ext on top of the in-smoke radiant term double-counts (the draft's
  "extension": with T_g = T_L, eps = 0.5, phi = eps_L = 1 its radiant part is
  1.5 sigma dT^4 against sigma dT^4 here).

The rate is Eq. 63.43, q^1.33 / D, as in ``tests/test_heat_total_flux.py``.
In the dose the radiant term (q_ext, or the eps term in smoke) counts as zero
below 2.5 kW/m2 (ISO 13571:2012 §8.2, §8.4, maintainer decision); the
convective term always counts.

Expected values are hand formulas written in this file and the Handbook's
200 deg C / 2.5 kW/m2 anchor, never ``pyfds_evac``.

API under test:

- ``pyfds_evac.core.fed.layer_radiant_flux_kw_m2(layer_temperature_celsius,
  *, view_factor, layer_emissivity, skin_temperature_celsius) -> float``:
  q_ext in kW/m2, signed (negative for a layer cooler than the skin).
- ``pyfds_evac.core.fed.HEAT_FLUX_REGIMES == ("smoke", "layer")``.
- ``DefaultHeatFedModel(..., method="total-flux", regime="smoke",
  layer_field=None, view_factor=..., layer_emissivity=...,
  layer_height_m=None)`` with attributes ``.regime``, ``.view_factor``,
  ``.layer_emissivity``, ``.layer_height_m``. ``regime="layer"`` needs
  ``method="total-flux"`` and a ``layer_field`` (an ``FdsHeatField``);
  otherwise ValueError. phi and eps_L outside [0, 1] or non-finite:
  ValueError. With ``regime="smoke"`` a given layer field is ignored.
- ``run.py``: ``--heat-regime {smoke,layer}`` (dest ``heat_regime``, default
  ``"smoke"``), ``--heat-layer-height`` (m, **no default**: it depends on the
  ceiling height), ``--heat-view-factor``, ``--heat-layer-emissivity``.
- ``build_run_kwargs`` loads a second TEMPERATURE slice at
  ``--heat-layer-height`` for the layer regime; the layer regime without a
  layer height, or with ``--heat-fed-method convective``, is an error.
- A default for phi or eps_L, if any, is listed in
  ``HEAT_FLUX_ASSUMED_PARAMETERS`` (as ``view_factor``, ``layer_emissivity``)
  and its help text says it is an assumption.
"""

from __future__ import annotations

import pathlib
import re
from argparse import Namespace
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fed import DefaultFedConfig, DefaultHeatFedModel, FdsHeatField

ROOT = pathlib.Path(__file__).resolve().parents[1]

SIGMA = 5.67e-8  # W m^-2 K^-4, as printed on p. 2384
KELVIN = 273.15
EXPONENT = 1.33  # Eq. 63.43 prints 1.33
# Fatal: D = 16.7 as printed in SFPE Ch. 63, p. 2384 (Eq. 63.49 D values);
# Purser's spreadsheet uses 16.667, the code follows the Handbook.
DOSE = {"tolerance": 1.33, "injury": 10.0, "fatal": 16.7}


# --- hand formulas ----------------------------------------------------------


def radiant_hand(t_source_c, t_skin_c):
    """sigma (T_i^4 - T_s^4) in kW/m2."""
    ti, ts = t_source_c + KELVIN, t_skin_c + KELVIN
    return SIGMA * (ti**4 - ts**4) / 1000.0


def convective_hand(t_gas_c, *, h, t_skin_c):
    return h * (t_gas_c - t_skin_c) / 1000.0


def q_ext_hand(t_layer_c, *, phi, eps_l, t_skin_c):
    return phi * eps_l * radiant_hand(t_layer_c, t_skin_c)


def q_layer_hand(t_head_c, t_layer_c, *, h, phi, eps_l, t_skin_c):
    """Layer regime: convection at the head plus the layer term only."""
    return convective_hand(t_head_c, h=h, t_skin_c=t_skin_c) + q_ext_hand(
        t_layer_c, phi=phi, eps_l=eps_l, t_skin_c=t_skin_c
    )


def q_smoke_hand(t_head_c, *, eps, h, t_skin_c):
    """Smoke regime (#223): Eq. 63.49, both terms divided together."""
    return eps * radiant_hand(t_head_c, t_skin_c) + convective_hand(
        t_head_c, h=h, t_skin_c=t_skin_c
    )


def counted(q_rad):
    """ISO 13571:2012 §8.2, §8.4: radiant term zero below 2.5 kW/m2."""
    return 0.0 if q_rad < 2.5 else q_rad


def q_layer_dose_hand(t_head_c, t_layer_c, *, h, phi, eps_l, t_skin_c):
    """Layer regime q entering the dose: q_ext counted per ISO."""
    return convective_hand(t_head_c, h=h, t_skin_c=t_skin_c) + counted(
        q_ext_hand(t_layer_c, phi=phi, eps_l=eps_l, t_skin_c=t_skin_c)
    )


def q_smoke_dose_hand(t_head_c, *, eps, h, t_skin_c):
    """Smoke regime q entering the dose: eps term counted per ISO."""
    return counted(eps * radiant_hand(t_head_c, t_skin_c)) + convective_hand(
        t_head_c, h=h, t_skin_c=t_skin_c
    )


def rate_hand(q, dose):
    """Eq. 63.43 as a rate, 1/min."""
    return q**EXPONENT / dose


# --- the hand formula against the Handbook ----------------------------------


def test_hand_formula_reproduces_the_200_c_layer_anchor():
    """p. 2382: 2.5 kW/m2 "corresponds approximately to a hot layer
    temperature of 200 deg C". Black layer, phi = 1: net 2.33 kW/m2 with
    T_s = 35 deg C, incident sigma T_L^4 = 2.84 kW/m2; both within 15 %."""
    net = q_ext_hand(200.0, phi=1.0, eps_l=1.0, t_skin_c=35.0)
    incident = SIGMA * (200.0 + KELVIN) ** 4 / 1000.0
    assert net == pytest.approx(2.330, abs=0.002)
    assert incident == pytest.approx(2.842, abs=0.002)
    for q in (net, incident):
        assert q == pytest.approx(2.5, rel=0.15)
    # Net vs incident at the anchor (spec 016: "about 20 % lower").
    assert 0.15 < 1.0 - net / incident < 0.25


def test_hand_formula_double_counting_example():
    """Spec 016 / #222: with T_g = T_L, eps = 0.5, phi = eps_L = 1 the draft's
    radiant part is 1.5 sigma dT^4; the layer regime gives sigma dT^4."""
    d = radiant_hand(250.0, 35.0)
    layer = q_layer_hand(250.0, 250.0, h=0.0, phi=1.0, eps_l=1.0, t_skin_c=35.0)
    draft = layer + 0.5 * d
    assert layer == pytest.approx(d, rel=1e-12)
    assert draft == pytest.approx(1.5 * d, rel=1e-12)


# --- API helpers ------------------------------------------------------------


class _Sampler:
    """Duck-typed ``SliceFieldSampler``: ``sample(t, x, y)`` only."""

    def __init__(self, value):
        self._value = value

    def sample(self, time_s, x, y):
        return float(self._value)


def _model(t_head_c, t_layer_c=None, *, regime="layer", **params):
    kwargs = dict(
        endpoint=params.pop("endpoint", None),
        method=params.pop("method", "total-flux"),
        emissivity=params.pop("eps", 0.5),
        convective_coefficient=params.pop("h", 5.0),
        skin_temperature_celsius=params.pop("t_skin_c", 35.0),
        regime=regime,
    )
    if t_layer_c is not None:
        kwargs["layer_field"] = FdsHeatField(_Sampler(t_layer_c))  # type: ignore[arg-type]
    if "phi" in params:
        kwargs["view_factor"] = params.pop("phi")
    if "eps_l" in params:
        kwargs["layer_emissivity"] = params.pop("eps_l")
    kwargs.update(params)
    return DefaultHeatFedModel(
        FdsHeatField(_Sampler(t_head_c)),  # type: ignore[arg-type]
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        **kwargs,
    )


def _rate(*args, **kwargs):
    _, rate = _model(*args, **kwargs).sample_rate(0.0, 0.0, 0.0)
    return rate


def _q_ext(*args, **kwargs):
    from pyfds_evac.core.fed import layer_radiant_flux_kw_m2

    return layer_radiant_flux_kw_m2(*args, **kwargs)


# --- current behaviour stays ------------------------------------------------


def test_cli_default_is_not_the_layer_regime():
    """Opt-in: total-flux alone keeps the head-in-smoke regime of #223."""
    import run

    args = run._build_parser().parse_args(
        ["--scenario", "x", "--enable-heat-fed", "--heat-fed-method", "total-flux"]
    )
    assert getattr(args, "heat_regime", None) in (None, "smoke")


@pytest.mark.parametrize(
    ("t_c", "eps", "h", "t_skin_c"), [(150.0, 0.5, 5.0, 35.0), (100.0, 0.05, 8.0, 35.0)]
)
def test_total_flux_without_regime_is_the_smoke_formula(t_c, eps, h, t_skin_c):
    field = FdsHeatField(_Sampler(t_c))  # type: ignore[arg-type]
    model = DefaultHeatFedModel(
        field,
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        method="total-flux",
        emissivity=eps,
        convective_coefficient=h,
        skin_temperature_celsius=t_skin_c,
    )
    _, rate = model.sample_rate(0.0, 0.0, 0.0)
    q = q_smoke_dose_hand(t_c, eps=eps, h=h, t_skin_c=t_skin_c)
    assert rate == pytest.approx(rate_hand(q, DOSE["fatal"]), rel=1e-9)


# --- q_ext -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("t_l", "phi", "eps_l", "t_skin_c"),
    [
        (200.0, 1.0, 1.0, 35.0),
        (250.0, 0.5, 0.9, 35.0),
        (300.0, 1.0, 0.7, 36.0),
        (500.0, 0.5, 1.0, 34.0),
    ],
)
def test_layer_flux_formula(t_l, phi, eps_l, t_skin_c):
    got = _q_ext(
        t_l, view_factor=phi, layer_emissivity=eps_l, skin_temperature_celsius=t_skin_c
    )
    assert got == pytest.approx(
        q_ext_hand(t_l, phi=phi, eps_l=eps_l, t_skin_c=t_skin_c), rel=1e-9
    )


def test_layer_flux_reproduces_the_200_c_anchor():
    """p. 2382 through the code: black layer at 200 deg C, phi = 1."""
    got = _q_ext(
        200.0, view_factor=1.0, layer_emissivity=1.0, skin_temperature_celsius=35.0
    )
    assert got == pytest.approx(2.5, rel=0.15)


def test_layer_flux_face_is_half_the_crown():
    kwargs = dict(layer_emissivity=0.9, skin_temperature_celsius=35.0)
    crown = _q_ext(300.0, view_factor=1.0, **kwargs)
    face = _q_ext(300.0, view_factor=0.5, **kwargs)
    assert face == pytest.approx(0.5 * crown, rel=1e-12)


def test_layer_flux_sign():
    """Zero at skin temperature; a layer cooler than the skin gives a
    negative net flux (it is not clipped here)."""
    kwargs = dict(view_factor=1.0, layer_emissivity=1.0, skin_temperature_celsius=35.0)
    assert _q_ext(35.0, **kwargs) == pytest.approx(0.0, abs=1e-12)
    assert _q_ext(20.0, **kwargs) < 0.0


# --- the model in the layer regime ------------------------------------------


@pytest.mark.parametrize("name", sorted(DOSE))
@pytest.mark.parametrize(
    ("t_head", "t_layer", "phi", "eps_l", "h", "t_skin_c"),
    [
        (60.0, 250.0, 1.0, 0.9, 5.0, 35.0),
        (120.0, 300.0, 0.5, 0.9, 5.0, 35.0),
        (40.0, 200.0, 1.0, 1.0, 8.0, 36.0),
    ],
)
def test_model_layer_rate(name, t_head, t_layer, phi, eps_l, h, t_skin_c):
    """The 200 deg C black layer gives 2.3 kW/m2 net, below the ISO
    threshold: convection only."""
    q = q_layer_dose_hand(t_head, t_layer, h=h, phi=phi, eps_l=eps_l, t_skin_c=t_skin_c)
    got = _rate(
        t_head,
        t_layer,
        endpoint=name,
        eps=0.5,
        h=h,
        t_skin_c=t_skin_c,
        phi=phi,
        eps_l=eps_l,
    )
    assert got == pytest.approx(rate_hand(q, DOSE[name]), rel=1e-9)


@pytest.mark.parametrize("eps", [0.05, 0.5, 0.9])
def test_layer_regime_has_no_radiant_term_of_the_gas_at_the_head(eps):
    """Double counting (#222): with T_g = T_L = 250 deg C, phi = eps_L = 1,
    the radiant part is sigma dT^4 once, whatever --heat-emissivity is."""
    q = q_layer_hand(250.0, 250.0, h=5.0, phi=1.0, eps_l=1.0, t_skin_c=35.0)
    doubled = q + eps * radiant_hand(250.0, 35.0)
    got = _rate(250.0, 250.0, eps=eps, h=5.0, t_skin_c=35.0, phi=1.0, eps_l=1.0)
    assert got == pytest.approx(rate_hand(q, DOSE["fatal"]), rel=1e-9)
    assert got < 0.99 * rate_hand(doubled, DOSE["fatal"])


def test_layer_regime_reads_the_layer_field_for_the_layer_term():
    """Swap check: head 60 deg C, layer 300 deg C. A model that takes the
    layer temperature for convection, or the head temperature for the layer
    term, gives a different rate."""
    params = dict(h=5.0, phi=1.0, eps_l=0.9, t_skin_c=35.0)
    q = q_layer_hand(60.0, 300.0, **params)
    swapped = q_layer_hand(300.0, 60.0, **params)
    assert abs(q - swapped) / q > 0.5
    got = _rate(60.0, 300.0, eps=0.5, **params)
    assert got == pytest.approx(rate_hand(q, DOSE["fatal"]), rel=1e-9)


def test_smoke_regime_ignores_a_layer_field():
    """regime="smoke" with a layer field and phi, eps_L given: #223 formula."""
    q = q_smoke_dose_hand(150.0, eps=0.5, h=5.0, t_skin_c=35.0)
    got = _rate(150.0, 400.0, regime="smoke", eps=0.5, phi=1.0, eps_l=1.0)
    assert got == pytest.approx(rate_hand(q, DOSE["fatal"]), rel=1e-9)


def test_layer_regime_cool_layer_still_gives_convection():
    """A layer cooler than the skin gives a negative q_ext, below the ISO
    threshold, so it counts as zero: the dose is convection alone, even
    where the physical total q <= 0."""
    params = dict(h=5.0, phi=1.0, eps_l=1.0, t_skin_c=35.0)
    assert q_ext_hand(30.0, phi=1.0, eps_l=1.0, t_skin_c=35.0) < 0.0
    got = _rate(120.0, 30.0, eps=0.5, **params)
    conv = convective_hand(120.0, h=5.0, t_skin_c=35.0)
    assert got == pytest.approx(rate_hand(conv, DOSE["fatal"]), rel=1e-9)
    assert q_layer_hand(36.0, 20.0, **params) < 0.0
    conv = convective_hand(36.0, h=5.0, t_skin_c=35.0)
    got = _rate(36.0, 20.0, eps=0.5, **params)
    assert got == pytest.approx(rate_hand(conv, DOSE["fatal"]), rel=1e-9)


@pytest.mark.parametrize("t_layer", [float("nan"), float("inf")])
def test_layer_regime_non_finite_layer_gives_no_dose(t_layer):
    rate = _rate(60.0, t_layer, eps=0.5, h=5.0, phi=1.0, eps_l=1.0)
    assert isinstance(rate, float)
    assert rate == 0.0


def test_model_records_the_layer_parameters():
    model = _model(60.0, 250.0, phi=0.5, eps_l=0.8, layer_height_m=2.4)
    assert model.regime == "layer"
    assert (model.view_factor, model.layer_emissivity) == (0.5, 0.8)
    assert model.layer_height_m == 2.4


def test_model_default_regime_is_smoke():
    field = FdsHeatField(_Sampler(150.0))  # type: ignore[arg-type]
    model = DefaultHeatFedModel(
        field,
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        method="total-flux",
    )
    assert model.regime == "smoke"


def test_regimes_constant():
    from pyfds_evac.core.fed import HEAT_FLUX_REGIMES

    assert tuple(HEAT_FLUX_REGIMES) == ("smoke", "layer")


@pytest.mark.parametrize(
    ("phi", "eps_l"),
    [(-0.1, 0.9), (1.1, 0.9), (0.5, -0.1), (0.5, 1.1), (float("nan"), 0.9)],
)
def test_model_rejects_invalid_layer_parameters(phi, eps_l):
    with pytest.raises(ValueError):
        _model(60.0, 250.0, phi=phi, eps_l=eps_l)


@pytest.mark.parametrize(
    ("phi", "eps_l", "name"),
    [(1.1, 0.9, "view factor"), (0.5, -0.1, "layer emissivity")],
)
def test_smoke_regime_still_checks_the_layer_ranges(phi, eps_l, name):
    """The range checks run before the regime gate; config's B check relies on it."""
    with pytest.raises(ValueError, match=rf"Heat {name} must be in \[0, 1\]"):
        _model(60.0, None, regime="smoke", phi=phi, eps_l=eps_l)


def test_layer_regime_needs_a_layer_field():
    with pytest.raises(ValueError):
        _model(60.0, None, phi=1.0, eps_l=0.9)


def test_layer_regime_needs_total_flux():
    """Eq. 63.44 and the convective laws have no flux to add q_ext to."""
    with pytest.raises(ValueError):
        _model(60.0, 250.0, method="convective", phi=1.0, eps_l=0.9)


def test_model_rejects_unknown_regime():
    with pytest.raises(ValueError):
        _model(60.0, 250.0, regime="auto", phi=1.0, eps_l=0.9)


# --- CLI and run_config ------------------------------------------------------


_LAYER_ARGS = [
    "--scenario",
    "x",
    "--enable-heat-fed",
    "--heat-fed-method",
    "total-flux",
    "--heat-regime",
    "layer",
    "--heat-layer-height",
    "2.4",
    "--heat-view-factor",
    "0.5",
    "--heat-layer-emissivity",
    "0.8",
]


def test_cli_layer_options():
    import run

    args = run._build_parser().parse_args(_LAYER_ARGS)
    assert args.heat_regime == "layer"
    assert args.heat_layer_height == 2.4
    assert (args.heat_view_factor, args.heat_layer_emissivity) == (0.5, 0.8)


def test_cli_rejects_unknown_regime():
    import run

    parser = run._build_parser()
    parser.parse_args(["--scenario", "x", "--heat-regime", "layer"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--scenario", "x", "--heat-regime", "auto"])


def test_cli_layer_height_has_no_default():
    """The layer height depends on the ceiling; no 2.4 m is assumed."""
    import run

    args = run._build_parser().parse_args(["--scenario", "x"])
    assert args.heat_layer_height is None


def test_layer_defaults_are_explicit_or_flagged():
    """phi and eps_L: either required (default None) or an assumption listed
    in HEAT_FLUX_ASSUMED_PARAMETERS whose help text says so."""
    import run
    from pyfds_evac.core.fed import HEAT_FLUX_ASSUMED_PARAMETERS

    parser = run._build_parser()
    args = parser.parse_args(["--scenario", "x"])
    help_text = parser.format_help()
    for option, dest, name in (
        ("--heat-view-factor", "heat_view_factor", "view_factor"),
        ("--heat-layer-emissivity", "heat_layer_emissivity", "layer_emissivity"),
    ):
        if getattr(args, dest) is None:
            continue
        assert name in HEAT_FLUX_ASSUMED_PARAMETERS, name
        block = help_text.split("\n  " + option, 1)[1].split("\n  --", 1)[0]
        assert "assum" in block.lower(), option


_OPTS = dict(
    seed=None,
    fds_dir="fds_data",
    constant_extinction=0.0,
    smoke_update_interval=1.0,
    smoke_slice_height=1.6,
    enable_rerouting=False,
    reroute_interval=1.0,
    vis_cache=None,
    disable_tenability=False,
    fic_alpha=1.2,
    fic_min_factor=0.0,
    fed_threshold=1.0,
    output_route_cost_history=None,
)

_LAYER_OPTS = dict(
    enable_heat_fed=True,
    heat_fed_method="total-flux",
    heat_regime="layer",
    heat_layer_height=2.4,
    heat_view_factor=0.5,
    heat_layer_emissivity=0.8,
)


class _TemperatureOnlyInventory:
    def supports_default_fed(self):
        return False

    def supports_heat_fed(self):
        return True

    def canonical_slice_names(self):
        return {"temperature"}


@pytest.fixture
def loaded_heights(monkeypatch):
    """Record the slice height of every TEMPERATURE field loaded."""
    import pyfds_evac.core.run_config as run_config

    heights: list[float] = []

    def _from_fds(cls, _d, slice_height_m=1.6, **_kw):
        heights.append(slice_height_m)
        return cls(sampler=None)

    monkeypatch.setattr(
        run_config, "inspect_fds_quantities", lambda _d: _TemperatureOnlyInventory()
    )
    monkeypatch.setattr(run_config.FdsHeatField, "from_fds", classmethod(_from_fds))
    return heights


def _build(**overrides):
    from pyfds_evac.core.run_config import build_run_kwargs

    return build_run_kwargs(
        SimpleNamespace(raw={}), Namespace(**{**_OPTS, **overrides})
    )


def test_run_config_loads_the_layer_slice(loaded_heights):
    model = _build(**_LAYER_OPTS)["heat_fed_model"]
    assert model.regime == "layer"
    assert (model.view_factor, model.layer_emissivity) == (0.5, 0.8)
    assert model.layer_height_m == 2.4
    assert sorted(loaded_heights) == [1.6, 2.4]


def test_run_config_smoke_regime_loads_one_slice(loaded_heights):
    """Passes now: total-flux without a regime loads the head slice only."""
    model = _build(enable_heat_fed=True, heat_fed_method="total-flux")["heat_fed_model"]
    assert getattr(model, "regime", "smoke") == "smoke"
    assert loaded_heights == [1.6]


def test_run_config_layer_regime_needs_a_height(loaded_heights):
    with pytest.raises((ValueError, SystemExit)):
        _build(**{**_LAYER_OPTS, "heat_layer_height": None})


@pytest.mark.parametrize("height", [float("nan"), float("inf"), float("-inf")])
def test_run_config_layer_regime_rejects_non_finite_height(loaded_heights, height):
    """A non-finite height would select an arbitrary slice, e.g. the head's."""
    with pytest.raises(ValueError, match="heat-layer-height"):
        _build(**{**_LAYER_OPTS, "heat_layer_height": height})
    assert loaded_heights == []


def test_run_config_layer_regime_needs_total_flux(loaded_heights):
    with pytest.raises((ValueError, SystemExit)):
        _build(**{**_LAYER_OPTS, "heat_fed_method": "convective"})


def test_layer_regime_without_enable_heat_fed_leaves_heat_off(loaded_heights):
    """Heat stays opt-in: the regime alone does not switch it on."""
    opts = {**_LAYER_OPTS, "enable_heat_fed": False}
    assert _build(**opts)["heat_fed_model"] is None
    assert loaded_heights == []


# --- docs --------------------------------------------------------------------


def _section(text, heading):
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def test_models_heat_page_documents_the_layer_regime():
    text = (ROOT / "site" / "content" / "models" / "heat.md").read_text()
    for option in (
        "--heat-regime",
        "--heat-layer-height",
        "--heat-view-factor",
        "--heat-layer-emissivity",
    ):
        assert option in text, option
    assert re.search(r"\bnet\b", text)
    assert "reduces to Eq. 63.49" not in text
    limits = _section(text, "## What is not modelled")
    assert "ceiling" in limits.lower()
    assert "#221" in limits or "issues/221" in limits


def test_changelog_mentions_the_layer_regime():
    text = (ROOT / "CHANGELOG.md").read_text()
    unreleased = text.split("## [0.2.0]", 1)[1].split("\n## [", 1)[0]
    assert "--heat-regime" in unreleased
    assert "#222" in unreleased or "issues/222" in unreleased
