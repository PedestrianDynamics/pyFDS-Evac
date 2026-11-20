"""Water-vapour check of the ``--heat-endpoint`` laws (#272).

SFPE Handbook 5th ed. Ch. 63, p. 2383: Eqs. 63.45-63.47 hold for air with
less than 10 % water vapour by volume. FDS writes the water-vapour volume
fraction in mol/mol (0-1), so the limit is 0.10. The check is observational:
the rate is unchanged.
"""

import pytest

from pyfds_evac.core import fed, manifest
from pyfds_evac.core.fed import (
    DefaultFedConfig,
    DefaultHeatFedModel,
    FdsHeatField,
    heat_endpoint_row_fields,
    heat_humidity_status,
    heat_humidity_summary,
)


class _Sampler:
    def __init__(self, value, z_m=1.6):
        self._value = value
        self.z_m = z_m

    def sample(self, time_s, x, y):
        if callable(self._value):
            return float(self._value(time_s, x, y))
        return float(self._value)


@pytest.mark.parametrize(
    ("fraction", "status"),
    [
        (0.0, "ok"),
        (0.05, "ok"),
        (0.0999, "ok"),
        (0.10, "humid"),  # "less than 10 %": the limit itself is outside
        (0.15, "humid"),
        (5.0, "humid"),  # a percent value read as a fraction is far above
        (float("nan"), "unknown"),
        (None, "unknown"),
    ],
)
def test_status_against_the_ten_percent_limit(fraction, status):
    assert heat_humidity_status(fraction) == status


def test_limit_is_a_fraction_not_a_percent():
    """10 % by volume is 0.10 mol/mol; 10.0 would never flag FDS output."""
    assert fed.HEAT_HUMIDITY_LIMIT_FRACTION == 0.10
    assert heat_humidity_status(0.05) == "ok"  # 5 %
    assert heat_humidity_status(0.12) == "humid"  # 12 %


def test_row_fields_carry_status_and_sample():
    humid = heat_endpoint_row_fields("fatal", 150.0, 0.12)
    assert humid["heat_humidity"] == "humid"
    assert humid["heat_water_vapour_fraction"] == 0.12
    dry = heat_endpoint_row_fields("fatal", 150.0, 0.03)
    assert dry["heat_humidity"] == "ok"


def test_row_fields_without_slice_are_unknown_as_before():
    assert heat_endpoint_row_fields("fatal", 150.0) == {
        "heat_endpoint": "fatal",
        "heat_outside_validity": False,
        "heat_humidity": "unknown",
    }


def test_summary_counts_rows_agents_and_maximum():
    rows = [
        {"agent_id": 1, "heat_humidity": "ok", "heat_water_vapour_fraction": 0.02},
        {"agent_id": 1, "heat_humidity": "humid", "heat_water_vapour_fraction": 0.11},
        {"agent_id": 2, "heat_humidity": "humid", "heat_water_vapour_fraction": 0.14},
        {"agent_id": 2, "heat_humidity": "humid", "heat_water_vapour_fraction": 0.12},
    ]
    assert heat_humidity_summary(rows) == {
        "humidity": "humid",
        "humid_rows": 3,
        "humid_agents": 2,
        "max_water_vapour_fraction": 0.14,
    }


def test_summary_ok_and_unknown():
    ok = [{"agent_id": 1, "heat_humidity": "ok", "heat_water_vapour_fraction": 0.02}]
    assert heat_humidity_summary(ok)["humidity"] == "ok"
    none = [{"agent_id": 1, "heat_humidity": "unknown"}]
    assert heat_humidity_summary(none) == {
        "humidity": "unknown",
        "humid_rows": 0,
        "humid_agents": 0,
        "max_water_vapour_fraction": None,
    }


def test_manifest_records_humidity_summary(tmp_path):
    summary = {
        "humidity": "humid",
        "humid_rows": 3,
        "humid_agents": 2,
        "max_water_vapour_fraction": 0.14,
    }
    data = manifest.build_manifest(
        seed=1,
        scenario_path=None,
        fds_dir=None,
        uv_lock=tmp_path / "missing",
        heat_endpoint="fatal",
        heat_humidity=summary,
    )
    validity = data["heat_validity"]
    assert validity["max_temperature_c"] == 205.0
    assert validity["humidity_limit"].startswith("< 10 % water vapour")
    assert {k: validity[k] for k in summary} == summary


def test_field_samples_vapour_with_the_temperature():
    field = FdsHeatField(_Sampler(150.0), water_vapour_sampler=_Sampler(0.12))  # type: ignore[arg-type]
    inputs = field.sample_inputs(0.0, 1.0, 1.0)
    assert inputs.temperature_celsius == 150.0
    assert inputs.water_vapour_fraction == 0.12


def test_field_without_slice_reports_no_fraction():
    inputs = FdsHeatField(_Sampler(150.0)).sample_inputs(0.0, 1.0, 1.0)  # type: ignore[arg-type]
    assert inputs.water_vapour_fraction is None


def test_humidity_does_not_change_the_dose():
    config = DefaultFedConfig(fds_dir="", update_interval_s=1.0)

    def dose(vapour):
        sampler = None if vapour is None else _Sampler(vapour)
        field = FdsHeatField(_Sampler(150.0), water_vapour_sampler=sampler)  # type: ignore[arg-type]
        model = DefaultHeatFedModel(field, config, endpoint="fatal")
        return model.advance(0.0, 1.0, 1.0, dt_s=1.0, current_fed=0.0)[1:]

    assert dose(None) == dose(0.02) == dose(0.30)


class _Slices:
    def __init__(self, quantities):
        self._quantities = quantities

    def filter_by_quantity(self, quantity):
        return [quantity] if quantity in self._quantities else []


class _Sim:
    def __init__(self, quantities):
        self.slices = _Slices(quantities)


def _patch_loader(monkeypatch, vapour_z_m=1.6):
    from pyfds_evac.core import fds_sampling

    loaded = []

    def load(fds_dir, quantity, **kwargs):
        loaded.append(quantity)
        height = vapour_z_m if "WATER" in quantity else 1.6
        return _Sampler(20.0, z_m=height)

    monkeypatch.setattr(fds_sampling, "load_slice_sampler", load)
    return loaded


def test_from_fds_loads_the_water_vapour_slice_when_present(monkeypatch):
    loaded = _patch_loader(monkeypatch)
    sim = _Sim({"TEMPERATURE", "WATER VAPOR VOLUME FRACTION"})
    field = FdsHeatField.from_fds("case", simulation=sim, water_vapour=True)
    assert loaded == ["TEMPERATURE", "WATER VAPOR VOLUME FRACTION"]
    assert field._water_vapour_sampler is not None


def test_from_fds_without_slice_or_request_keeps_unknown(monkeypatch):
    loaded = _patch_loader(monkeypatch)
    sim = _Sim({"TEMPERATURE"})
    field = FdsHeatField.from_fds("c", simulation=sim, water_vapour=True)
    assert field._water_vapour_sampler is None
    sim = _Sim({"TEMPERATURE", "WATER VAPOR VOLUME FRACTION"})
    field = FdsHeatField.from_fds("c", simulation=sim)
    assert field._water_vapour_sampler is None
    assert "WATER VAPOR VOLUME FRACTION" not in loaded


def test_vapour_slice_at_another_height_warns_and_stays_unknown(monkeypatch, caplog):
    loaded = _patch_loader(monkeypatch, vapour_z_m=2.4)
    sim = _Sim({"TEMPERATURE", "WATER VAPOR VOLUME FRACTION"})
    with caplog.at_level("WARNING"):
        field = FdsHeatField.from_fds("c", simulation=sim, water_vapour=True)
    assert "WATER VAPOR VOLUME FRACTION" in loaded
    assert field._water_vapour_sampler is None
    assert "not at the height of the TEMPERATURE slice" in caplog.text


def test_vapour_is_sampled_at_the_time_and_point_of_the_temperature():
    """A time- and space-varying vapour field pins the sample arguments."""
    field = FdsHeatField(
        _Sampler(150.0),  # type: ignore[arg-type]
        water_vapour_sampler=_Sampler(lambda t, x, y: 0.001 * t + 0.01 * x + 0.1 * y),  # type: ignore[arg-type]
    )
    assert field.sample_inputs(30.0, 2.0, 0.5).water_vapour_fraction == (
        pytest.approx(0.03 + 0.02 + 0.05)
    )
    assert field.sample_inputs(60.0, 4.0, 0.0).water_vapour_fraction == (
        pytest.approx(0.06 + 0.04)
    )


def test_fed_csv_with_a_late_vapour_column_does_not_crash(tmp_path):
    """The first row lacks the sample (outside the slice); a later row has it."""
    from pyfds_evac.core import run_outputs

    base = {"heat_endpoint": "fatal", "heat_outside_validity": False}
    rows = [
        {**base, "heat_humidity": "unknown"},
        {**base, "heat_humidity": "humid", "heat_water_vapour_fraction": 0.12},
    ]
    path = tmp_path / "fed.csv"
    run_outputs._write_fed_history_csv(rows, str(path))
    lines = path.read_text().splitlines()
    assert lines[0].endswith("heat_humidity,heat_water_vapour_fraction")
    assert lines[1].endswith("unknown,")
    assert lines[2].endswith("humid,0.12")
