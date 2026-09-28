"""Radiant flux from FDS ``INTEGRATED INTENSITY`` for the total-flux method (#221).

Spec 016 (``specs/016-heat-fed/SPEC.md``, "Radiant flux from FDS") and
issue #221. FDS's ``INTEGRATED INTENSITY`` is U = integral of I over all
solid angles, in kW/m2 (FDS User's Guide 6.10.1, Table 22.4). It is the
radiation arriving from every direction, not the flux onto a surface: a
plate sees one hemisphere with rays weighted by cos(theta), so the incident
flux q lies between U/4 (sphere, or a plate in an isotropic field) and U (one
small source seen face-on). No factor holds everywhere, so the factor is a
user parameter in [0.25, 1] with **no default**: choosing this source without
it is an error.

With this source the total-flux law (SFPE Handbook 5th ed. Ch. 63,
doi:10.1007/978-1-4939-2565-0_63, Eqs. 63.49 and 63.43, pp. 2382-2384) is

    q = f U + h (T_g - T_s) / 1000        [kW/m2]
    t = D / q^1.33                         [min], FED = sum dt / t

- f U is **incident** radiant flux (the radiant tolerance data, Table 63.19,
  are incident; spec 016). The skin's own emission is not subtracted.
- The gas term eps sigma (T_g^4 - T_s^4) of Eq. 63.49 is **not** added: U
  already contains the emission of the gas at the head, and spec 016 says
  not to add two radiant terms. Any ``emissivity`` passed is ignored.
- No 2.5 kW/m2 threshold (spec 016), as for #223.

Consequence (finding, maintainer decision pending, see #221): U is not zero
in a cold room. At 20 deg C, U = 4 sigma T^4 = 1.68 kW/m2, so without the
threshold f U gives a dose with no fire at all. ``test_ambient_background_*``
records the size with hand numbers; the docs must say so. Alternatives for
the maintainer: net f U - sigma T_s^4, or excess f (U - 4 sigma T_a^4).

Expected values are hand formulas in this file, never ``pyfds_evac``.

API under test (``pyfds_evac.core.fed`` unless noted):

- ``radiant_flux_from_integrated_intensity_kw_m2(integrated_intensity_kw_m2,
  u_factor) -> float``: f U; ValueError for f outside [0.25, 1] or non-finite.
- ``HeatFedInputs.integrated_intensity_kw_m2``: ``None`` when not sampled.
- ``FdsHeatField(sampler, intensity_sampler=None)``;
  ``FdsHeatField.from_fds(fds_dir, *, slice_height_m=1.6, simulation=None,
  integrated_intensity=False)`` loads the ``INTEGRATED INTENSITY`` slice at
  the same height as the TEMPERATURE slice when asked.
- ``DefaultHeatFedModel(..., radiant_source="gas", u_factor=None)``:
  ``radiant_source`` is ``"gas"`` (default, #223 behaviour) or
  ``"integrated-intensity"``; the latter needs ``method="total-flux"`` and a
  ``u_factor`` in [0.25, 1], else ValueError.
  ``heat_flux_kw_m2(temperature_celsius, integrated_intensity_kw_m2=None)``.
  ``heat_flux_parameters()`` adds ``radiant_source``, ``u_factor`` and
  ``radiant_flux`` (``"incident"``); ``u_factor`` is user-given, so it is not
  in ``assumed``.
- ``FdsQuantityInventory.canonical_slice_names()`` maps
  ``INTEGRATED INTENSITY`` to ``"integrated_intensity"``.
- ``run.py``: ``--heat-radiant-source {gas,integrated-intensity}`` (dest
  ``heat_radiant_source``, default ``"gas"``) and ``--heat-u-factor`` (dest
  ``heat_u_factor``, default ``None``; outside [0.25, 1] rejected).
- ``build_run_kwargs`` passes them on; the source without a factor, with the
  convective method, or on a case with no ``INTEGRATED INTENSITY`` slice is
  an error (ValueError or SystemExit), never a silent zero.
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
EXPONENT = 1.33  # Eq. 63.43 prints 1.33
DOSE = {"tolerance": 1.33, "injury": 10.0, "fatal": 16.667}  # spec 016


# --- hand formulas ----------------------------------------------------------


def q_u_hand(t_gas_c, u_kw_m2, *, f, h, t_skin_c):
    """Incident f U plus convection h (T_g - T_s), kW/m2; no gas eps term."""
    return f * u_kw_m2 + h * (t_gas_c - t_skin_c) / 1000.0


def q_gas_hand(t_gas_c, *, eps, h, t_skin_c):
    """Eq. 63.49 as in #223 (both terms in W/m2, divided together)."""
    tg, ts = t_gas_c + KELVIN, t_skin_c + KELVIN
    return (eps * SIGMA * (tg**4 - ts**4) + h * (tg - ts)) / 1000.0


def u_isotropic(t_c):
    """U = 4 pi I = 4 sigma T^4 of a black isotropic field, kW/m2."""
    return 4.0 * SIGMA * (t_c + KELVIN) ** 4 / 1000.0


def t_hand_min(q, dose):
    """Eq. 63.43, t = D / q^1.33 [min]."""
    return dose / q**EXPONENT


# --- the hand formulas against published or physical numbers (pass now) -----


def test_isotropic_plate_gets_a_quarter_of_u():
    """A plate in an isotropic field: q = pi I, U = 4 pi I, so q = U / 4.

    At 300 deg C (the #224 uniform deck) U = 24.47 kW/m2 and q = sigma T^4.
    """
    u = u_isotropic(300.0)
    assert u == pytest.approx(24.47, abs=0.01)
    assert 0.25 * u == pytest.approx(SIGMA * (300.0 + KELVIN) ** 4 / 1000.0)


@pytest.mark.parametrize(("q", "table_s"), [(2.5, 30.0), (10.0, 4.0)])
def test_face_on_flux_bounds_table_63_20(q, table_s):
    """f = 1, T_g = T_s: q = U. Table 63.20 (p. 2383) radiant rows, 2.5 kW/m2
    -> 30 s and 10 kW/m2 -> 4 s; Eq. 63.43, tolerance dose, band 25 %."""
    seconds = 60.0 * t_hand_min(q_u_hand(35.0, q, f=1.0, h=5.0, t_skin_c=35.0), 1.33)
    assert table_s * 0.75 <= seconds <= table_s * 1.25


@pytest.mark.parametrize(("f", "minutes"), [(1.0, 8.9), (0.25, 68.9)])
def test_ambient_background_gives_a_fatal_dose_in_a_cold_room(f, minutes):
    """Finding for the maintainer (#221): 20 deg C, no fire, U = 4 sigma T^4 =
    1.68 kW/m2, h = 5, T_s = 35 deg C. Incident f U minus the convective loss
    stays positive, so with no threshold the fatal FED reaches 1 in about
    9 min (f = 1) to 69 min (f = 0.25)."""
    u = u_isotropic(20.0)
    assert u == pytest.approx(1.675, abs=0.002)
    q = q_u_hand(20.0, u, f=f, h=5.0, t_skin_c=35.0)
    assert q > 0.0
    assert t_hand_min(q, DOSE["fatal"]) == pytest.approx(minutes, abs=0.1)


# --- API helpers ------------------------------------------------------------


class _Sampler:
    """Duck-typed ``SliceFieldSampler``: ``sample(t, x, y)`` only."""

    def __init__(self, value):
        self._value = value

    def sample(self, time_s, x, y):
        return float(self._value)


def _u_model(t_c, u, *, f, h, t_skin_c, eps=0.0, endpoint=None):
    field = FdsHeatField(_Sampler(t_c), intensity_sampler=_Sampler(u))  # type: ignore[arg-type,call-arg]
    return DefaultHeatFedModel(
        field,
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        endpoint=endpoint,
        method="total-flux",
        emissivity=eps,
        convective_coefficient=h,
        skin_temperature_celsius=t_skin_c,
        radiant_source="integrated-intensity",  # type: ignore[call-arg]
        u_factor=f,  # type: ignore[call-arg]
    )


def _u_rate(t_c, u, **kwargs):
    _, rate = _u_model(t_c, u, **kwargs).sample_rate(0.0, 0.0, 0.0)
    return rate


def _u_flux(u, f):
    from pyfds_evac.core.fed import radiant_flux_from_integrated_intensity_kw_m2

    return radiant_flux_from_integrated_intensity_kw_m2(u, f)


# --- current behaviour stays (pass now) --------------------------------------


def test_cli_total_flux_without_source_keeps_gas_term():
    """#223 unchanged: ``--heat-fed-method total-flux`` alone uses the gas term."""
    import run

    args = run._build_parser().parse_args(
        ["--scenario", "x", "--enable-heat-fed", "--heat-fed-method", "total-flux"]
    )
    assert getattr(args, "heat_radiant_source", "gas") == "gas"
    assert getattr(args, "heat_u_factor", None) is None


def test_total_flux_model_without_source_is_the_gas_law():
    t_c, eps, h, t_s = 150.0, 0.5, 5.0, 35.0
    model = DefaultHeatFedModel(
        FdsHeatField(_Sampler(t_c)),  # type: ignore[arg-type]
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        method="total-flux",
        emissivity=eps,
        convective_coefficient=h,
        skin_temperature_celsius=t_s,
    )
    _, rate = model.sample_rate(0.0, 0.0, 0.0)
    q = q_gas_hand(t_c, eps=eps, h=h, t_skin_c=t_s)
    assert rate == pytest.approx(1.0 / t_hand_min(q, DOSE["fatal"]), rel=1e-9)


# --- pure function ------------------------------------------------------------


@pytest.mark.parametrize("f", [0.25, 0.5, 0.75, 1.0])
@pytest.mark.parametrize("u", [0.0, 1.675, 10.0, 24.47])
def test_radiant_flux_is_f_times_u(u, f):
    assert _u_flux(u, f) == pytest.approx(f * u, rel=1e-12)


@pytest.mark.parametrize("f", [0.0, 0.2, 0.249, 1.01, 2.0, -0.5, math.nan, math.inf])
def test_radiant_flux_rejects_factor_outside_range(f):
    assert _u_flux(10.0, 0.5) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        _u_flux(10.0, f)


# --- field -------------------------------------------------------------------


def test_field_samples_integrated_intensity():
    field = FdsHeatField(_Sampler(150.0), intensity_sampler=_Sampler(12.5))  # type: ignore[arg-type,call-arg]
    inputs = field.sample_inputs(0.0, 0.0, 0.0)
    assert inputs.temperature_celsius == 150.0
    assert inputs.integrated_intensity_kw_m2 == 12.5


def test_field_without_intensity_sampler_reports_none():
    inputs = FdsHeatField(_Sampler(150.0)).sample_inputs(0.0, 0.0, 0.0)  # type: ignore[arg-type]
    assert inputs.integrated_intensity_kw_m2 is None


class _Outside:
    """Duck-typed sampler for a point its slice does not cover."""

    def sample(self, time_s, x, y):
        raise ValueError(f"Point ({x}, {y}) is outside the sampled FDS slice domain")


def test_field_rejects_missing_intensity_where_temperature_exists():
    """U is a required input of this source: a hole in the U slice under a
    valid TEMPERATURE sample must not become a zero dose."""
    field = FdsHeatField(_Sampler(200.0), intensity_sampler=_Outside())  # type: ignore[arg-type,call-arg]
    with pytest.raises(ValueError, match="INTEGRATED INTENSITY"):
        field.sample_inputs(0.0, 0.5, 0.5)


def test_field_rejects_temperature_missing_where_intensity_exists():
    field = FdsHeatField(_Outside(), intensity_sampler=_Sampler(12.5))  # type: ignore[arg-type,call-arg]
    with pytest.raises(ValueError, match="TEMPERATURE"):
        field.sample_inputs(0.0, 0.5, 0.5)


def test_model_rejects_missing_intensity_with_hot_gas():
    """Reviewer case: 200 deg C gas, no U. Convection alone gives a positive
    rate (hand value below), so a silent zero would be wrong."""
    h, t_s = 5.0, 35.0
    q_conv = h * (200.0 - t_s) / 1000.0
    assert 1.0 / t_hand_min(q_conv, DOSE["fatal"]) == pytest.approx(0.046454, rel=1e-4)
    model = DefaultHeatFedModel(
        FdsHeatField(_Sampler(200.0), intensity_sampler=_Outside()),  # type: ignore[arg-type,call-arg]
        DefaultFedConfig(fds_dir="", update_interval_s=1.0),
        method="total-flux",
        convective_coefficient=h,
        skin_temperature_celsius=t_s,
        radiant_source="integrated-intensity",  # type: ignore[call-arg]
        u_factor=0.5,  # type: ignore[call-arg]
    )
    with pytest.raises(ValueError, match="INTEGRATED INTENSITY"):
        model.sample_rate(0.0, 0.5, 0.5)


def test_field_outside_both_slices_keeps_the_domain_fallback():
    """Outside the FDS domain (neither slice covers the point): 20 deg C and a
    non-finite U, as before; no error."""
    inputs = FdsHeatField(_Outside(), intensity_sampler=_Outside()).sample_inputs(  # type: ignore[arg-type,call-arg]
        0.0, 9.0, 9.0
    )
    assert inputs.temperature_celsius == 20.0
    assert math.isnan(inputs.integrated_intensity_kw_m2)


def _fake_simulation(heights_by_quantity):
    """fdsreader-like case holding horizontal slices at the given z."""

    def slc(z):
        extent = SimpleNamespace(z_start=z, z_end=z)
        return SimpleNamespace(orientation=3, extent=extent, subslices=[])

    slices = {q: [slc(z) for z in zs] for q, zs in heights_by_quantity.items()}
    return SimpleNamespace(
        slices=SimpleNamespace(filter_by_quantity=lambda q: slices.get(q, []))
    )


def test_field_rejects_intensity_slice_at_another_height():
    """Reviewer case: TEMPERATURE at 1.6 m, U only at 1.2 m. Both are within
    the 0.5 m warning distance of the requested 1.6 m, but radiation and
    convection would come from different heights of a stratified room."""
    sim = _fake_simulation({"TEMPERATURE": [0.4, 1.6], "INTEGRATED INTENSITY": [1.2]})
    with pytest.raises(ValueError, match="height"):
        FdsHeatField.from_fds(  # type: ignore[call-arg]
            "case", slice_height_m=1.6, simulation=sim, integrated_intensity=True
        )


def test_field_accepts_intensity_slice_at_the_temperature_height():
    sim = _fake_simulation(
        {"TEMPERATURE": [0.4, 1.6], "INTEGRATED INTENSITY": [1.2, 1.6]}
    )
    FdsHeatField.from_fds(  # type: ignore[call-arg]
        "case", slice_height_m=1.6, simulation=sim, integrated_intensity=True
    )


# --- model --------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DOSE))
@pytest.mark.parametrize("f", [0.25, 0.5, 1.0])
@pytest.mark.parametrize("u", [2.0, 10.0, 24.47])
def test_model_rate_radiant_only(u, f, name):
    """T_g = T_s: no convection, q = f U, rate = (f U)^1.33 / D."""
    got = _u_rate(35.0, u, f=f, h=8.0, t_skin_c=35.0, endpoint=name)
    assert got == pytest.approx(1.0 / t_hand_min(f * u, DOSE[name]), rel=1e-9)


@pytest.mark.parametrize(
    ("t_c", "u", "f", "h", "t_s"),
    [(150.0, 5.0, 0.5, 5.0, 35.0), (300.0, 24.47, 0.25, 8.0, 35.0)],
)
def test_model_rate_adds_convection(t_c, u, f, h, t_s):
    q = q_u_hand(t_c, u, f=f, h=h, t_skin_c=t_s)
    got = _u_rate(t_c, u, f=f, h=h, t_skin_c=t_s)
    assert got == pytest.approx(1.0 / t_hand_min(q, DOSE["fatal"]), rel=1e-9)


def test_model_ignores_gas_emissivity_with_integrated_intensity():
    """U already holds the gas emission: eps sigma (T_g^4 - T_s^4) is not added."""
    t_c, u, f, h, t_s = 200.0, 8.0, 0.5, 8.0, 35.0
    q = q_u_hand(t_c, u, f=f, h=h, t_skin_c=t_s)
    got = _u_rate(t_c, u, f=f, h=h, t_skin_c=t_s, eps=0.5)
    assert got == pytest.approx(1.0 / t_hand_min(q, DOSE["fatal"]), rel=1e-9)
    doubled = q + q_gas_hand(t_c, eps=0.5, h=0.0, t_skin_c=t_s)
    assert not math.isclose(got, 1.0 / t_hand_min(doubled, DOSE["fatal"]), rel_tol=1e-2)


def test_model_heat_flux_takes_integrated_intensity():
    model = _u_model(150.0, 5.0, f=0.5, h=5.0, t_skin_c=35.0)
    got = model.heat_flux_kw_m2(150.0, integrated_intensity_kw_m2=5.0)
    assert got == pytest.approx(q_u_hand(150.0, 5.0, f=0.5, h=5.0, t_skin_c=35.0))


def test_model_no_threshold_below_2_5_kw():
    q = q_u_hand(35.0, 2.0, f=0.5, h=5.0, t_skin_c=35.0)
    assert q < 2.5
    assert _u_rate(35.0, 2.0, f=0.5, h=5.0, t_skin_c=35.0) > 0.0


@pytest.mark.parametrize("u", [0.0, math.nan, math.inf])
def test_model_domain_guard(u):
    """No radiation and T_g = T_s, or a non-finite U: no dose."""
    rate = _u_rate(35.0, u, f=0.5, h=5.0, t_skin_c=35.0)
    assert isinstance(rate, float)
    assert rate == 0.0


def test_model_records_source_factor_and_incident():
    params = _u_model(150.0, 5.0, f=0.5, h=5.0, t_skin_c=35.0).heat_flux_parameters()
    assert params["radiant_source"] == "integrated-intensity"
    assert params["u_factor"] == 0.5
    assert params["radiant_flux"] == "incident"
    assert "u_factor" not in params["assumed"]


@pytest.mark.parametrize("f", [None, 0.2, 1.1, math.nan])
def test_model_requires_a_factor_in_range(f):
    _u_model(150.0, 5.0, f=0.5, h=5.0, t_skin_c=35.0)
    with pytest.raises(ValueError):
        _u_model(150.0, 5.0, f=f, h=5.0, t_skin_c=35.0)


def test_model_rejects_integrated_intensity_with_convective_method():
    _u_model(150.0, 5.0, f=0.5, h=5.0, t_skin_c=35.0)
    with pytest.raises(ValueError):
        DefaultHeatFedModel(
            FdsHeatField(_Sampler(150.0), intensity_sampler=_Sampler(5.0)),  # type: ignore[arg-type,call-arg]
            DefaultFedConfig(fds_dir="", update_interval_s=1.0),
            method="convective",
            radiant_source="integrated-intensity",  # type: ignore[call-arg]
            u_factor=0.5,  # type: ignore[call-arg]
        )


def test_model_rejects_unknown_radiant_source():
    _u_model(150.0, 5.0, f=0.5, h=5.0, t_skin_c=35.0)
    with pytest.raises(ValueError):
        DefaultHeatFedModel(
            FdsHeatField(_Sampler(150.0)),  # type: ignore[arg-type]
            DefaultFedConfig(fds_dir="", update_interval_s=1.0),
            method="total-flux",
            radiant_source="layer",  # type: ignore[call-arg]
            u_factor=0.5,  # type: ignore[call-arg]
        )


# --- inventory ------------------------------------------------------------------


def test_inventory_names_integrated_intensity():
    from pyfds_evac.core.fds_inventory import FdsQuantityInventory

    inventory = FdsQuantityInventory(
        slices=["INTEGRATED INTENSITY", "TEMPERATURE"],
        smoke_3d=[],
        data_3d=[],
        devices=[],
    )
    assert "integrated_intensity" in inventory.canonical_slice_names()


# --- CLI ------------------------------------------------------------------------


_U_ARGS = [
    "--scenario",
    "x",
    "--enable-heat-fed",
    "--heat-fed-method",
    "total-flux",
    "--heat-radiant-source",
    "integrated-intensity",
]


@pytest.mark.parametrize("f", ["0.25", "0.5", "1.0"])
def test_cli_source_and_factor(f):
    import run

    args = run._build_parser().parse_args([*_U_ARGS, "--heat-u-factor", f])
    assert args.heat_radiant_source == "integrated-intensity"
    assert args.heat_u_factor == float(f)


def test_cli_factor_has_no_default():
    import run

    parser = run._build_parser()
    parser.parse_args([*_U_ARGS, "--heat-u-factor", "0.5"])
    assert parser.parse_args(["--scenario", "x"]).heat_u_factor is None


@pytest.mark.parametrize("f", ["0.2", "1.1", "nan", "-1"])
def test_cli_rejects_factor_outside_range(f):
    import run

    parser = run._build_parser()
    parser.parse_args([*_U_ARGS, "--heat-u-factor", "0.5"])
    with pytest.raises(SystemExit):
        parser.parse_args([*_U_ARGS, "--heat-u-factor", f])


def test_cli_rejects_unknown_source():
    import run

    parser = run._build_parser()
    parser.parse_args([*_U_ARGS, "--heat-u-factor", "0.5"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--scenario", "x", "--heat-radiant-source", "layer"])


def test_cli_help_states_range_no_default_and_incident():
    import run

    help_text = run._build_parser().format_help()
    block = help_text.split("\n  --heat-u-factor", 1)[1].split("\n  --", 1)[0]
    flat = " ".join(block.split()).lower()
    assert "0.25" in flat and "1" in flat
    assert "no default" in flat
    assert "incident" in flat


# --- run_config -------------------------------------------------------------------


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
    enable_heat_fed=True,
    heat_fed_method="total-flux",
)


class _Inventory:
    def __init__(self, slices):
        self._slices = slices

    def supports_default_fed(self):
        return False

    def supports_heat_fed(self):
        return "temperature" in self._slices

    def canonical_slice_names(self):
        return {name: name for name in self._slices}


def _patch(monkeypatch, slices):
    import pyfds_evac.core.run_config as run_config

    calls = []

    def fake_from_fds(cls, fds_dir, **kwargs):
        calls.append(kwargs)
        intensity = _Sampler(10.0) if kwargs.get("integrated_intensity") else None
        return cls(_Sampler(35.0), intensity_sampler=intensity)

    monkeypatch.setattr(
        run_config, "inspect_fds_quantities", lambda _d: _Inventory(slices)
    )
    monkeypatch.setattr(run_config.FdsHeatField, "from_fds", classmethod(fake_from_fds))
    return calls


def _build(**overrides):
    from pyfds_evac.core.run_config import build_run_kwargs

    return build_run_kwargs(
        SimpleNamespace(raw={}), Namespace(**{**_OPTS, **overrides})
    )


def test_run_config_passes_source_and_factor(monkeypatch):
    calls = _patch(monkeypatch, {"temperature", "integrated_intensity"})
    model = _build(heat_radiant_source="integrated-intensity", heat_u_factor=0.5)[
        "heat_fed_model"
    ]
    assert model.radiant_source == "integrated-intensity"
    assert model.u_factor == 0.5
    # Same height as the TEMPERATURE slice.
    assert calls[-1]["integrated_intensity"] is True
    assert calls[-1]["slice_height_m"] == 2.0


def test_run_config_default_source_is_gas(monkeypatch):
    _patch(monkeypatch, {"temperature", "integrated_intensity"})
    _build(heat_radiant_source="integrated-intensity", heat_u_factor=0.5)
    model = _build()["heat_fed_model"]
    assert model.radiant_source == "gas"


def test_run_config_requires_a_factor(monkeypatch):
    _patch(monkeypatch, {"temperature", "integrated_intensity"})
    _build(heat_radiant_source="integrated-intensity", heat_u_factor=0.5)
    with pytest.raises((ValueError, SystemExit)):
        _build(heat_radiant_source="integrated-intensity", heat_u_factor=None)


def test_run_config_rejects_source_with_convective_method(monkeypatch):
    _patch(monkeypatch, {"temperature", "integrated_intensity"})
    _build(heat_radiant_source="integrated-intensity", heat_u_factor=0.5)
    with pytest.raises((ValueError, SystemExit)):
        _build(
            heat_fed_method="convective",
            heat_radiant_source="integrated-intensity",
            heat_u_factor=0.5,
        )


def test_run_config_rejects_case_without_intensity_slice(monkeypatch):
    """A chosen source whose slice is missing must not read as zero radiation."""
    _patch(monkeypatch, {"temperature", "integrated_intensity"})
    _build(heat_radiant_source="integrated-intensity", heat_u_factor=0.5)
    _patch(monkeypatch, {"temperature"})
    with pytest.raises((ValueError, SystemExit)):
        _build(heat_radiant_source="integrated-intensity", heat_u_factor=0.5)


# --- FED history CSV ----------------------------------------------------------------


def test_fed_history_csv_writes_integrated_intensity(tmp_path):
    import csv

    import run

    row = {"time_s": 0.0, "agent_id": 1, "heat_flux_kw_m2": 5.0}
    run._write_fed_history_csv([row], str(tmp_path / "a.csv"))
    row = {**row, "heat_integrated_intensity_kw_m2": 10.0}
    run._write_fed_history_csv([row], str(tmp_path / "b.csv"))
    with (tmp_path / "b.csv").open(newline="") as handle:
        written = next(csv.DictReader(handle))
    assert float(written["heat_integrated_intensity_kw_m2"]) == 10.0
    assert float(written["heat_flux_kw_m2"]) == 5.0


# --- docs ---------------------------------------------------------------------------


def _models_heat() -> str:
    return (ROOT / "site" / "content" / "models" / "heat.md").read_text()


def test_models_heat_page_documents_integrated_intensity():
    text = _models_heat()
    flat = " ".join(text.split())
    assert "--heat-radiant-source" in text and "--heat-u-factor" in text
    assert "INTEGRATED INTENSITY" in text
    assert "0.25" in flat
    assert re.search(r"no default", flat, re.IGNORECASE)
    assert re.search(r"\bincident\b", flat, re.IGNORECASE)


def test_models_heat_limits_cover_integrated_intensity():
    """Limits: ambient background, falling exposure (Eq. 63.48), the hot-air
    double-count question, and gauge devices (#224) as the preferred input."""
    text = _models_heat()
    limits = re.split(r"^#+ .*Limit", text, flags=re.MULTILINE | re.IGNORECASE)
    assert len(limits) > 1, "no Limits section"
    flat = " ".join(limits[1].split()).lower()
    assert "background" in flat or "ambient" in flat
    assert "63.48" in flat
    assert "double" in flat
    assert "#224" in flat or "issues/224" in flat
    assert "gauge" in flat


def test_changelog_mentions_integrated_intensity():
    text = (ROOT / "CHANGELOG.md").read_text()
    unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert "--heat-radiant-source" in unreleased
    assert "--heat-u-factor" in unreleased
