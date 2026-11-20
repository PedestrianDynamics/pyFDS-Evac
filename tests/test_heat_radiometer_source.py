"""Radiometer radiant source of the total-flux heat method (#276, contract §4).

With ``radiant_source="radiometer"`` the radiant term of q is the net reading
of FDS ``RADIOMETER GAS`` devices (FDS UG 6.10.1 Eq. 22.36), the 2.5 kW/m2
threshold acts on that reading, and convection h (T_g - T_s) / 1000 is added
after it from the TEMPERATURE slice. Expected values are hand formulas here.

V2 (contract §4.5): R = 3.0, h = 8, T_g = 60 C, T_s = 35 C gives
q = 3.0 + 8 * 25 / 1000 = 3.200 kW/m2. Adding h dT twice gives 3.400; applying
the threshold to q instead of to R, with R = 2.4, gives 2.6 instead of
0 + 0.2 = 0.200.
"""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path

import numpy as np
import pytest

from pyfds_evac import cli
from pyfds_evac.config import rules
from pyfds_evac.core import radiometer_grid
from pyfds_evac.core.fds_sampling import FdsDomainError, FdsHorizonError
from pyfds_evac.core.fdsreader_adapter import DevicePoint, DeviceSet
from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultHeatFedModel,
    FdsHeatField,
    HeatFedInputs,
    heat_flux_row_fields,
)
from pyfds_evac.core.radiometer_grid import (
    RadiometerGrid,
    RadiometerGridError,
    RadiometerSource,
    load_radiometer_source,
)

T_SKIN = 35.0
H = 8.0
TIMES = np.array([0.0, 3.0, 6.0])


class _Slice:
    """A TEMPERATURE sampler stand-in: 60 C for x, y in [0, 4], else outside."""

    quantity = "TEMPERATURE"

    def sample(self, time_s, x, y):
        if not self.covers(x, y):
            raise ValueError("outside")
        return 60.0

    def covers(self, x, y):
        return 0.0 <= x <= 4.0 and 0.0 <= y <= 4.0


def _source(value: float = 3.0, *, hold: bool = False, emissivity: float = 1.0):
    """A 2 x 2 grid on x, y in {1, 2}, constant in space and time."""
    xs, ys = np.array([1.0, 2.0]), np.array([1.0, 2.0])
    values = np.full((TIMES.size, 2, 2), value)
    return RadiometerSource(
        grid=RadiometerGrid(xs, ys, TIMES, values),
        orientation=(0.0, 0.0, 1.0),
        z_m=1.6,
        gauge_temperature_c=T_SKIN,
        gauge_emissivity=emissivity,
        n_devices=4,
        deck_path=Path("case.fds"),
        deck_sha256="0" * 64,
        allow_horizon_hold=hold,
    )


def _config():
    return DefaultFedConfig(fds_dir="", update_interval_s=1.0)


def _model(source=None, *, layer=False, require=False, **kwargs):
    field = FdsHeatField(
        _Slice(),  # type: ignore[arg-type]
        require_fds_coverage=require,
        radiometer=source or _source(),
    )
    if layer:
        kwargs.update(
            regime="layer",
            layer_field=FdsHeatField(_Slice()),  # type: ignore[arg-type]
            view_factor=0.5,
            layer_emissivity=0.9,
            layer_height_m=2.5,
        )
    return DefaultHeatFedModel(
        field,
        _config(),
        method="total-flux",
        convective_coefficient=H,
        skin_temperature_celsius=T_SKIN,
        radiant_source="radiometer",
        radiometer_orientation="0,0,1",
        **kwargs,
    )


# --- V2: the assembly of q -------------------------------------------------


def test_v2_q_is_the_reading_plus_convection_once():
    q = _model().heat_flux_kw_m2(60.0, radiometer_kw_m2=3.0)
    assert q == pytest.approx(3.200, abs=1e-12)
    assert abs(q - 3.400) > 0.1  # h dT added twice


def test_v2_the_threshold_acts_on_the_reading_not_on_q():
    model = _model()
    low = model.heat_flux_kw_m2(60.0, radiometer_kw_m2=2.4, radiant_threshold=True)
    assert low == pytest.approx(0.200, abs=1e-12)
    assert abs(low - 2.600) > 1.0  # the threshold on q would keep 2.6
    # The history keeps the physical q, before the threshold.
    assert model.heat_flux_kw_m2(60.0, radiometer_kw_m2=2.4) == pytest.approx(2.6)


def test_the_threshold_is_on_the_net_reading_and_counts_2_5():
    model = _model()
    at = model.heat_flux_kw_m2(35.0, radiometer_kw_m2=2.5, radiant_threshold=True)
    below = model.heat_flux_kw_m2(35.0, radiometer_kw_m2=2.4999, radiant_threshold=True)
    assert at == pytest.approx(2.5)
    assert below == 0.0


def test_emissivity_does_not_change_q():
    plain = _model().heat_flux_kw_m2(60.0, radiometer_kw_m2=3.0)
    other = _model(emissivity=0.1).heat_flux_kw_m2(60.0, radiometer_kw_m2=3.0)
    assert other == plain


def test_the_rate_uses_the_reading_at_the_agent():
    inputs, rate = _model().sample_rate(3.0, 1.5, 1.5)
    assert inputs.radiometer_kw_m2 == pytest.approx(3.0)
    assert rate == pytest.approx(3.2**1.33 / 16.7, rel=1e-12)


# --- history and manifest fields ------------------------------------------


def test_row_fields_carry_the_net_and_the_incident_flux():
    row = heat_flux_row_fields(
        _model(_source(emissivity=0.8)), 60.0, radiometer_kw_m2=3.0
    )
    t_s = T_SKIN + 273.15
    assert row["heat_flux_kw_m2"] == pytest.approx(3.2)
    assert row["heat_radiometer_kw_m2"] == 3.0
    assert row["heat_radiometer_incident_kw_m2"] == pytest.approx(
        3.0 / 0.8 + 5.67e-8 * t_s**4 / 1000.0, abs=1e-12
    )
    unit = heat_flux_row_fields(_model(), 60.0, radiometer_kw_m2=3.0)
    # With emissivity 1 the offset is sigma T_s^4 = 0.511 kW/m2.
    assert unit["heat_radiometer_incident_kw_m2"] - 3.0 == pytest.approx(
        0.511, abs=1e-3
    )


def test_the_other_sources_have_no_radiometer_columns():
    gas = DefaultHeatFedModel(
        FdsHeatField(_Slice()),  # type: ignore[arg-type]
        _config(),
        method="total-flux",
    )
    assert set(heat_flux_row_fields(gas, 60.0)) == {"heat_flux_kw_m2"}


def test_manifest_parameters_record_the_source():
    params = _model().heat_flux_parameters()
    assert params["radiant_source"] == "radiometer"
    assert params["radiant_flux"] == "net"
    assert params["radiometer_orientation"] == [0.0, 0.0, 1.0]
    assert params["radiometer_gauge_temperature_celsius"] == T_SKIN
    assert params["radiometer_gauge_emissivity"] == 1.0
    assert params["radiometer_device_count"] == 4
    assert params["radiometer_grid_origin_m"] == [1.0, 1.0]
    assert params["radiometer_grid_spacing_m"] == [1.0, 1.0]
    assert params["fds_deck_sha256"] == "0" * 64
    assert "emissivity" not in params["assumed"]


def test_heat_inputs_default_to_no_reading():
    assert HeatFedInputs().radiometer_kw_m2 is None


# --- the layer regime ------------------------------------------------------


def test_layer_regime_warns_once_and_drops_the_layer_term(caplog):
    with caplog.at_level(logging.WARNING):
        model = _model(layer=True)
    hits = [m for m in caplog.messages if "layer term is not added" in m]
    assert len(hits) == 1 and "radiometer" in hits[0]
    assert model.uses_layer_term is False
    assert model.heat_flux_parameters()["layer_term"] is False
    assert model.heat_flux_kw_m2(60.0, radiometer_kw_m2=3.0) == pytest.approx(3.2)


# --- construction rules ----------------------------------------------------


def _build(**kwargs):
    field = FdsHeatField(_Slice(), radiometer=_source())  # type: ignore[arg-type]
    return DefaultHeatFedModel(field, _config(), **kwargs)


def test_the_orientation_is_required_with_the_source():
    with pytest.raises(ValueError, match="needs --heat-radiometer-orientation"):
        _build(method="total-flux", radiant_source="radiometer")


def test_the_orientation_is_refused_without_the_source():
    with pytest.raises(ValueError, match="needs --heat-radiant-source radiometer"):
        _build(method="total-flux", radiometer_orientation="0,0,1")


def test_the_source_needs_the_total_flux_method():
    with pytest.raises(ValueError, match="needs --heat-fed-method total-flux"):
        _build(radiant_source="radiometer", radiometer_orientation="0,0,1")


@pytest.mark.parametrize("text", ["0,0", "a,b,c", "0,0,0", "0,0,nan", ""])
def test_a_bad_orientation_is_an_error(text):
    with pytest.raises(ValueError, match="orientation"):
        _build(
            method="total-flux",
            radiant_source="radiometer",
            radiometer_orientation=text,
        )


# --- coverage (D4) and domain ---------------------------------------------


def test_an_agent_inside_the_slice_but_outside_the_grid_is_an_error():
    with pytest.raises(RadiometerGridError, match="outside the radiometer grid"):
        _model().sample_rate(3.0, 3.5, 3.5)


def test_an_agent_outside_the_domain_gets_no_dose_and_one_warning(caplog):
    model = _model()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            inputs, rate = model.sample_rate(3.0, 9.0, 9.0)
    assert math.isnan(inputs.radiometer_kw_m2)
    assert rate == 0.0
    hits = [m for m in caplog.messages if "outside the TEMPERATURE slice" in m]
    assert len(hits) == 1
    row = heat_flux_row_fields(model, 20.0, radiometer_kw_m2=inputs.radiometer_kw_m2)
    assert math.isnan(row["heat_flux_kw_m2"])


def test_require_fds_coverage_raises_outside_the_domain():
    with pytest.raises(FdsDomainError):
        _model(require=True).sample_rate(3.0, 9.0, 9.0)


# --- time: the horizon rules and the last output time ---------------------


def test_float_noise_at_the_last_output_time_is_absorbed():
    source = _source()
    assert source.reading(6.0000001, 1.5, 1.5) == pytest.approx(3.0)
    assert source.reading(6.0 + 2.9, 1.5, 1.5) == pytest.approx(3.0)  # < 1 interval


def test_past_the_horizon_is_an_error_unless_held(caplog):
    with pytest.raises(FdsHorizonError, match="RADIOMETER"):
        _source().reading(6.0 + 3.5, 1.5, 1.5)
    held = _source(hold=True)
    with caplog.at_level(logging.WARNING):
        assert held.reading(20.0, 1.5, 1.5) == pytest.approx(3.0)
        assert held.reading(30.0, 1.5, 1.5) == pytest.approx(3.0)
    assert len([m for m in caplog.messages if "holding the last frame" in m]) == 1


# --- the loader: height, &PROP, deck, devices ------------------------------

DECK = """\
&HEAD CHID='case' /
&PROP ID='skin', GAUGE_TEMPERATURE={t}, GAUGE_EMISSIVITY={e} /
&DEVC ID='RAD_r1', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1, PROP_ID='skin',
      XBP=1,2,1,1,1.6,1.6, POINTS=2 /
&DEVC ID='RAD_r2', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1, PROP_ID='skin',
      XBP=1,2,2,2,1.6,1.6, POINTS=2 /
"""


def _devices(tmp_path, *, z=1.6, quantity="RADIOMETER", unit="kW/m2"):
    points = tuple(
        DevicePoint(
            f"RAD_r{r}-{k}",
            quantity,
            (float(k), float(r), z),
            (0.0, 0.0, 1.0),
            unit,
            np.array([1.0, 2.0, 3.0]) * k * r,
        )
        for r in (1, 2)
        for k in (1, 2)
    )
    return DeviceSet("case", tmp_path, TIMES, points)


@pytest.fixture
def case(tmp_path, monkeypatch):
    def make(*, t=35.0, e=1.0, write_deck=True, **kwargs):
        if write_deck:
            (tmp_path / "case.fds").write_text(DECK.format(t=t, e=e))
        monkeypatch.setattr(
            radiometer_grid, "read_fds_devices", lambda p: _devices(tmp_path, **kwargs)
        )
        return tmp_path

    return make


def _load(path, **kwargs):
    args = dict(
        orientation="0,0,1",
        skin_temperature_c=T_SKIN,
        slice_z_m=1.6,
        half_cell_m=0.05,
    )
    args.update(kwargs)
    return load_radiometer_source(path, **args)


def test_the_loader_reads_grid_props_and_deck_hash(case):
    path = case()
    source = _load(path)
    assert source.n_devices == 4
    assert source.z_m == 1.6
    assert source.gauge_temperature_c == T_SKIN
    assert source.gauge_emissivity == 1.0
    assert (
        source.deck_sha256
        == hashlib.sha256((path / "case.fds").read_bytes()).hexdigest()
    )
    entry = source.manifest_entry()
    assert entry["radiometer_grid_origin_m"] == [1.0, 1.0]
    assert entry["radiometer_grid_spacing_m"] == [1.0, 1.0]
    # Node (2, 2) holds 4 * [1, 2, 3]; the cell centre averages 1, 2, 2, 4.
    assert source.reading(3.0, 2.0, 2.0) == pytest.approx(8.0)
    assert source.reading(0.0, 1.5, 1.5) == pytest.approx(2.25)


def test_devices_off_the_slice_height_name_both_heights(case):
    path = case(z=1.8)
    with pytest.raises(RadiometerGridError) as err:
        _load(path)
    message = str(err.value)
    assert "z=1.8" in message and "z=1.6" in message and "half a cell" in message
    assert _load(path, slice_z_m=1.8).z_m == 1.8
    assert _load(path, half_cell_m=0.25).z_m == 1.8  # within half a cell


def test_a_gauge_temperature_other_than_the_skin_is_an_error(case):
    with pytest.raises(RadiometerGridError, match="GAUGE_TEMPERATURE=20"):
        _load(case(t=20.0))
    with pytest.raises(RadiometerGridError, match="GAUGE_TEMPERATURE=35"):
        _load(case(), skin_temperature_c=35.001)


def test_a_missing_deck_is_an_error(case):
    with pytest.raises(RadiometerGridError, match="case.fds is not in"):
        _load(case(write_deck=False))


def test_without_matching_devices_the_error_shows_the_devc_line(case):
    with pytest.raises(RadiometerGridError) as err:
        _load(case(), orientation="1,0,0")
    message = str(err.value)
    assert "&DEVC ID='RAD_r01', QUANTITY='RADIOMETER GAS'" in message
    assert "ORIENTATION=1,0,0" in message and "1.6,1.6" in message
    assert "GAUGE_TEMPERATURE=35" in message


def test_a_case_without_radiometers_is_an_error_not_a_fallback(case):
    with pytest.raises(RadiometerGridError, match="no RADIOMETER device"):
        _load(case(quantity="TEMPERATURE"))


def test_device_units_must_be_kw_m2(case):
    with pytest.raises(RadiometerGridError, match="expected kW/m2"):
        _load(case(unit="W/m2"))


def test_mixed_emissivities_are_an_error(case):
    path = case(e=0.9)
    deck = (path / "case.fds").read_text()
    deck = deck.replace(
        "PROP_ID='skin',\n      XBP=1,2,2", "PROP_ID='other',\n      XBP=1,2,2"
    )
    deck += "&PROP ID='other', GAUGE_TEMPERATURE=35., GAUGE_EMISSIVITY=1.0 /\n"
    (path / "case.fds").write_text(deck)
    with pytest.raises(RadiometerGridError, match="different GAUGE_EMISSIVITY"):
        _load(path)


# --- CLI and configuration rules ------------------------------------------


def _parse(*argv):
    return cli._build_parser().parse_args(["--scenario", "s", *argv])


TOTAL_FLUX = ["--fds-dir", "c", "--enable-heat-fed", "--heat-fed-method", "total-flux"]
RADIOMETER = ["--heat-radiant-source", "radiometer"]
FACING_UP = ["--heat-radiometer-orientation", "0,0,1"]


def test_the_flag_and_the_choice_exist():
    opts = _parse(*RADIOMETER, "--heat-radiometer-orientation", " 0, 0 ,1")
    assert opts.heat_radiant_source == "radiometer"
    assert opts.heat_radiometer_orientation == "0, 0 ,1"
    assert _parse().heat_radiometer_orientation is None


@pytest.mark.parametrize("text", ["0,0", "x,y,z", "0,0,0", "inf,0,0"])
def test_a_bad_orientation_is_rejected_at_parse(text, capsys):
    with pytest.raises(SystemExit):
        _parse("--heat-radiometer-orientation", text)
    assert "orientation" in capsys.readouterr().err


def test_config_rules_require_the_orientation_with_the_source():
    issue = rules.radiometer_issue(_parse(*TOTAL_FLUX, *RADIOMETER))
    assert issue is not None and issue.rule == "D17"
    assert issue.option == "heat_radiometer_orientation"
    assert "needs --heat-radiometer-orientation" in issue.message
    assert rules.radiometer_issue(_parse(*TOTAL_FLUX, *RADIOMETER, *FACING_UP)) is None


def test_config_rules_reject_the_orientation_without_the_source():
    issue = rules.radiometer_issue(_parse(*TOTAL_FLUX, *FACING_UP))
    assert issue is not None and issue.rule == "D17"
    assert "needs --heat-radiant-source radiometer" in issue.message


def test_config_rules_need_total_flux_for_the_source():
    opts = _parse("--fds-dir", "c", "--enable-heat-fed", *RADIOMETER, *FACING_UP)
    issue = rules.radiometer_issue(opts)
    assert issue is not None and "needs --heat-fed-method total-flux" in issue.message


class _HeatOn:
    heat_fed = True
    tenability = True


def test_emissivity_and_u_factor_are_reported_as_ignored():
    opts = _parse(
        *TOTAL_FLUX,
        *RADIOMETER,
        *FACING_UP,
        "--heat-emissivity",
        "0.9",
        "--heat-u-factor",
        "0.5",
    )
    emissivity = rules._heat_reason(opts, "heat_emissivity", _HeatOn())
    assert emissivity == ("D18", "with --heat-radiant-source radiometer", False)
    u_factor = rules._heat_reason(opts, "heat_u_factor", _HeatOn())
    assert u_factor is not None and u_factor[0] == "D18"


# --- the real loader and the run wiring on committed cases ------------------

REPO = Path(__file__).resolve().parents[1]
NO_DEVICES = str(REPO / "assets" / "heat_only_no_soot" / "fds")
OTHER_DEVICES = str(REPO / "assets" / "heat_integrated_intensity" / "fds")
SOURCE = [
    "--enable-heat-fed",
    "--heat-fed-method",
    "total-flux",
    "--heat-radiant-source",
    "radiometer",
    "--allow-fds-horizon-hold",
]


def _scenario():
    from pyfds_evac.core.scenario import load_scenario

    return load_scenario(str(REPO / "assets" / "t_junction"))


@pytest.mark.parametrize("fds_dir", [NO_DEVICES, OTHER_DEVICES])
def test_a_case_without_radiometers_stops_the_run_with_the_devc_line(fds_dir):
    """The common mistake: a case with no device output, or devices of another
    quantity. The run stops; it does not fall back to another source."""
    from pyfds_evac.core.run_config import build_run_kwargs

    opts = _parse("--fds-dir", fds_dir, *SOURCE, *FACING_UP)
    with pytest.raises(RadiometerGridError) as raised:
        build_run_kwargs(_scenario(), opts)
    message = str(raised.value)
    assert "&DEVC ID='RAD_r01', QUANTITY='RADIOMETER GAS'" in message
    assert "ORIENTATION=0,0,1" in message


def test_the_missing_orientation_is_a_setup_error_the_model_predicts():
    from pyfds_evac.config import effective_configuration
    from pyfds_evac.core.run_config import build_run_kwargs

    opts = _parse("--fds-dir", NO_DEVICES, *SOURCE)
    with pytest.raises(ValueError) as raised:
        build_run_kwargs(_scenario(), opts)
    errors = effective_configuration(opts, _scenario()).errors
    assert [e.rule for e in errors] == ["D17"]
    assert errors[0].message == str(raised.value)


def test_the_orientation_without_the_source_is_a_setup_error_the_model_predicts():
    from pyfds_evac.config import effective_configuration
    from pyfds_evac.core.run_config import build_run_kwargs

    opts = _parse(
        "--fds-dir",
        NO_DEVICES,
        "--enable-heat-fed",
        "--allow-fds-horizon-hold",
        *FACING_UP,
    )
    with pytest.raises(ValueError) as raised:
        build_run_kwargs(_scenario(), opts)
    errors = effective_configuration(opts, _scenario()).errors
    assert [e.rule for e in errors] == ["D17"]
    assert errors[0].message == str(raised.value)


def test_slice_cell_height_is_the_z_size_of_the_cell_holding_the_slice():
    """assets/heat_integrated_intensity: IJK 12 over 2.4 m in z, so 0.2 m cells."""
    from pyfds_evac.core.fds_sampling import load_slice_sampler, slice_cell_height_m

    sampler = load_slice_sampler(OTHER_DEVICES, "TEMPERATURE", slice_height_m=1.6)
    assert slice_cell_height_m(sampler._slice) == pytest.approx(0.2, abs=1e-6)
