"""ISO 13571:2012 convective law and single threshold for the heat dose (#290).

Source: ISO 13571:2012, clause 8. For air with less than 10 % water vapour by
volume (§8.3), with T the air temperature in deg C and t in min:

    Eq. (9),  fully clothed:               t_Iconv = 4.1e8 * T**-3.61
    Eq. (10), unclothed or lightly clothed: t_Iconv = 5e7   * T**-3.4

Eq. (10) has the constants of SFPE Handbook 5th ed. Eq. 63.44. The dose is
the sum of dt / t_Iconv (ISO Eq. (11), SFPE Eq. 63.48). ISO asks for one
threshold for both FED and FEC (§5.4), and the heat threshold is chosen "in
the same manner" (§8.5).

Maintainer decisions: with ``--enable-heat-fed`` the convective law is
Eq. (9) by default; ``--heat-clothing unclothed`` selects Eq. (10). The heat
threshold equals ``fed_threshold`` unless ``--heat-fed-threshold`` overrides
it, a departure from ISO recorded in the manifest.

Expected values are written out here from the standard, never taken from
``pyfds_evac``. Hand values: Eq. (9) gives 24.705, 5.716 and 2.023 min at
100, 150 and 200 deg C; Eq. (10) gives 7.924, 1.996 and 0.751 min.
"""

from __future__ import annotations

import logging
import math
import random
from argparse import Namespace
from types import SimpleNamespace

import pytest

from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultHeatFedModel,
    FdsHeatField,
    HeatFedInputs,
    TenabilityConfig,
    accumulate_default_heat_fed,
    default_heat_fed_rate_per_minute,
    sample_heat_incapacitation_threshold,
    time_to_heat_fed_threshold_s,
)

TEMPERATURES_C = (20.0, 65.0, 100.0, 120.0, 150.0, 200.0, 405.0)


def t_iso_9_min(t_c: float) -> float:
    """ISO 13571:2012 Eq. (9), fully clothed."""
    return 4.1e8 * t_c**-3.61


def t_iso_10_min(t_c: float) -> float:
    """ISO 13571:2012 Eq. (10), unclothed or lightly clothed."""
    return 5e7 * t_c**-3.4


def t_fatal_min(t_c: float) -> float:
    """SFPE Eq. 63.47, fatal endpoint (p. 2383)."""
    return 2e18 * t_c**-9.0403 + 1e8 * t_c**-3.10898


class _Sampler:
    def __init__(self, fn):
        self._fn = fn

    def sample(self, time_s, x, y):
        return float(self._fn(float(time_s), float(x), float(y)))


def _field(t_c: float) -> FdsHeatField:
    return FdsHeatField(_Sampler(lambda t, x, y: t_c))  # type: ignore[arg-type]


def _config() -> DefaultFedConfig:
    return DefaultFedConfig(fds_dir="", update_interval_s=1.0)


def _model_rate(t_c: float, **kwargs) -> float:
    model = DefaultHeatFedModel(_field(t_c), _config(), **kwargs)
    _, rate = model.sample_rate(0.0, 0.0, 0.0)
    return rate


# --- hand values ------------------------------------------------------------


@pytest.mark.parametrize(
    ("t_c", "clothed_min", "unclothed_min"),
    [(100.0, 24.705, 7.924), (150.0, 5.716, 1.996), (200.0, 2.023, 0.751)],
)
def test_hand_formulas_give_the_quoted_times(t_c, clothed_min, unclothed_min):
    assert t_iso_9_min(t_c) == pytest.approx(clothed_min, abs=5e-4)
    assert t_iso_10_min(t_c) == pytest.approx(unclothed_min, abs=5e-4)


# --- rate functions ---------------------------------------------------------


@pytest.mark.parametrize("t_c", TEMPERATURES_C)
def test_default_rate_is_iso_eq_9(t_c):
    rate = default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=t_c))
    assert rate == pytest.approx(1.0 / t_iso_9_min(t_c), rel=1e-12)


@pytest.mark.parametrize("t_c", TEMPERATURES_C)
def test_unclothed_rate_is_iso_eq_10(t_c):
    rate = default_heat_fed_rate_per_minute(
        HeatFedInputs(temperature_celsius=t_c), clothing="unclothed"
    )
    assert rate == pytest.approx(1.0 / t_iso_10_min(t_c), rel=1e-12)


@pytest.mark.parametrize("clothing", ["clothed", "unclothed"])
@pytest.mark.parametrize("t_c", [0.0, -10.0, float("nan"), float("inf")])
def test_rate_domain_guard(clothing, t_c):
    inputs = HeatFedInputs(temperature_celsius=t_c)
    assert default_heat_fed_rate_per_minute(inputs, clothing=clothing) == 0.0


def test_unknown_clothing_is_rejected():
    with pytest.raises(ValueError):
        default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=100.0), clothing="naked"
        )


def test_clothed_time_is_about_three_times_unclothed():
    """Eq. (9) / Eq. (10): 3.12 at 100 deg C, 2.76 at 180 deg C."""
    assert t_iso_9_min(100.0) / t_iso_10_min(100.0) == pytest.approx(3.12, abs=0.01)
    assert t_iso_9_min(180.0) / t_iso_10_min(180.0) == pytest.approx(2.76, abs=0.01)
    ratio = default_heat_fed_rate_per_minute(
        HeatFedInputs(temperature_celsius=100.0), clothing="unclothed"
    ) / default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=100.0))
    assert ratio == pytest.approx(t_iso_9_min(100.0) / t_iso_10_min(100.0), rel=1e-12)


def test_accumulation_and_time_to_threshold_use_the_clothed_law():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    assert accumulate_default_heat_fed(inputs, duration_s=90.0) == pytest.approx(
        1.5 / t_iso_9_min(150.0), rel=1e-12
    )
    assert time_to_heat_fed_threshold_s(inputs, threshold=1.0) == pytest.approx(
        60.0 * t_iso_9_min(150.0), rel=1e-12
    )
    assert time_to_heat_fed_threshold_s(
        inputs, threshold=1.0, clothing="unclothed"
    ) == pytest.approx(60.0 * t_iso_10_min(150.0), rel=1e-12)
    assert accumulate_default_heat_fed(
        inputs, duration_s=90.0, clothing="unclothed"
    ) == pytest.approx(1.5 / t_iso_10_min(150.0), rel=1e-12)


# --- model ------------------------------------------------------------------


@pytest.mark.parametrize("t_c", TEMPERATURES_C)
def test_model_default_is_clothed(t_c):
    assert _model_rate(t_c) == pytest.approx(1.0 / t_iso_9_min(t_c), rel=1e-12)
    assert DefaultHeatFedModel(_field(t_c), _config()).clothing == "clothed"


@pytest.mark.parametrize("t_c", TEMPERATURES_C)
def test_model_unclothed_is_eq_10(t_c):
    rate = _model_rate(t_c, clothing="unclothed")
    assert rate == pytest.approx(1.0 / t_iso_10_min(t_c), rel=1e-12)


def test_model_rejects_unknown_clothing():
    with pytest.raises(ValueError):
        DefaultHeatFedModel(_field(100.0), _config(), clothing="naked")


@pytest.mark.parametrize("clothing", ["clothed", "unclothed"])
def test_endpoint_law_ignores_clothing(clothing):
    rate = _model_rate(150.0, endpoint="fatal", clothing=clothing)
    assert rate == pytest.approx(1.0 / t_fatal_min(150.0), rel=1e-12)


def test_total_flux_ignores_clothing():
    kwargs = dict(
        method="total-flux",
        emissivity=0.5,
        convective_coefficient=8.0,
        skin_temperature_celsius=35.0,
    )
    clothed = _model_rate(200.0, **kwargs)
    unclothed = _model_rate(200.0, clothing="unclothed", **kwargs)
    assert clothed == unclothed


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, "clothed"),
        ({"clothing": "unclothed"}, "unclothed"),
        ({"endpoint": "fatal"}, None),
        ({"method": "total-flux"}, None),
    ],
)
def test_convective_clothing_is_reported_only_when_it_applies(kwargs, expected):
    model = DefaultHeatFedModel(_field(100.0), _config(), **kwargs)
    assert model.convective_clothing() == expected


# --- one threshold (ISO 13571 §5.4, §8.5) -----------------------------------


def test_heat_threshold_is_unset_by_default():
    assert TenabilityConfig().heat_fed_threshold is None


@pytest.mark.parametrize("gas", [0.3, 0.5, 1.0, 2.0])
def test_deterministic_heat_threshold_follows_the_gas_threshold(gas):
    cfg = TenabilityConfig(fed_threshold=gas)
    rng = random.Random(3)
    assert sample_heat_incapacitation_threshold(cfg, rng) == gas


def test_explicit_heat_threshold_overrides_the_gas_threshold():
    cfg = TenabilityConfig(fed_threshold=0.5, heat_fed_threshold=2.0)
    assert sample_heat_incapacitation_threshold(cfg, random.Random(3)) == 2.0


def test_probabilistic_heat_median_is_the_gas_threshold():
    cfg = TenabilityConfig(fed_threshold=0.5, heat_incapacitation_mode="probabilistic")
    draws = sorted(
        sample_heat_incapacitation_threshold(cfg, random.Random(i)) for i in range(4001)
    )
    assert draws[2000] == pytest.approx(0.5, rel=0.08)


def test_heat_mode_stays_deterministic_by_default():
    assert TenabilityConfig().heat_incapacitation_mode == "deterministic"
    assert TenabilityConfig().incapacitation_mode == "deterministic"
    assert TenabilityConfig().fed_threshold == 1.0


# --- CLI --------------------------------------------------------------------


def _parse(*extra):
    import run

    return run._build_parser().parse_args(["--scenario", "x", *extra])


def test_cli_defaults():
    args = _parse("--enable-heat-fed")
    assert args.heat_clothing is None
    assert args.heat_fed_threshold is None
    assert args.fed_threshold == 1.0


def test_cli_clothing_choices():
    assert _parse("--heat-clothing", "clothed").heat_clothing == "clothed"
    assert _parse("--heat-clothing", "unclothed").heat_clothing == "unclothed"
    with pytest.raises(SystemExit):
        _parse("--heat-clothing", "naked")


def test_cli_help_names_both_iso_equations():
    import run

    help_text = run._build_parser().format_help()
    block = help_text.split("\n  --heat-clothing", 1)[1].split("\n  --", 1)[0]
    flat = " ".join(block.split())
    assert "Eq. (9)" in flat and "Eq. (10)" in flat and "63.44" in flat


# --- run_config -------------------------------------------------------------


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


def test_run_config_default_is_clothed(temperature_only_case):
    assert _build()["heat_fed_model"].clothing == "clothed"


def test_run_config_passes_unclothed(temperature_only_case):
    assert _build(heat_clothing="unclothed")["heat_fed_model"].clothing == "unclothed"


def test_run_config_warns_clothing_with_endpoint(temperature_only_case, caplog):
    with caplog.at_level(logging.WARNING):
        _build(heat_clothing="unclothed", heat_endpoint="fatal")
    assert any("--heat-clothing" in r.getMessage() for r in caplog.records)


def test_run_config_warns_clothing_without_heat(temperature_only_case, caplog):
    with caplog.at_level(logging.WARNING):
        _build(enable_heat_fed=False, heat_clothing="unclothed")
    assert any("--heat-clothing" in r.getMessage() for r in caplog.records)


def test_run_config_heat_threshold_follows_fed_threshold(temperature_only_case):
    cfg = _build(fed_threshold=0.5)["tenability_config"]
    assert cfg.heat_fed_threshold is None
    assert sample_heat_incapacitation_threshold(cfg, random.Random(1)) == 0.5


def test_run_config_override_warns_departure_from_iso(temperature_only_case, caplog):
    with caplog.at_level(logging.WARNING):
        cfg = _build(fed_threshold=0.5, heat_fed_threshold=2.0)["tenability_config"]
    assert cfg.heat_fed_threshold == 2.0
    assert any("ISO 13571" in r.getMessage() for r in caplog.records)


# --- manifest ---------------------------------------------------------------


def test_manifest_records_clothing_and_override(tmp_path):
    from pyfds_evac.core import manifest

    data = manifest.build_manifest(
        seed=1,
        scenario_path=None,
        fds_dir=None,
        uv_lock=tmp_path / "missing",
        heat_clothing="clothed",
        heat_fed_threshold_override=2.0,
    )
    assert data["heat_clothing"] == "clothed"
    assert data["heat_fed_threshold_override"] == 2.0


def test_manifest_without_heat_has_neither_key(tmp_path):
    from pyfds_evac.core import manifest

    data = manifest.build_manifest(
        seed=1, scenario_path=None, fds_dir=None, uv_lock=tmp_path / "missing"
    )
    assert not {"heat_clothing", "heat_fed_threshold_override"} & set(data)


def test_ratio_sanity():
    """Guard the hand formulas themselves against a typo in the exponents."""
    assert math.log(t_iso_9_min(200.0) / t_iso_9_min(100.0)) / math.log(
        0.5
    ) == pytest.approx(3.61, rel=1e-12)
