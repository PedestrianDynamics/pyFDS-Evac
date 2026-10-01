"""Agents, signs and route edges outside the FDS domain (#426, #427).

Outside the FDS slices pyFDS-Evac reads ambient air and clear sight, as
FDS+Evac does (``evac.f90`` sets every evacuation cell outside the fire meshes
to ambient and clear). These tests pin that default, the diagnostics that make
it visible, and the strict mode ``--require-fds-coverage``. The two defects
(#426, #427) are pinned in ``test_fds_domain_defects.py``.

The synthetic slices are one-cell rectangles with a value per frame; the
coupled cases use the committed ``assets/iso_table21_coupled`` output, a
corridor x -50..50 m, y -1..1 m with K = 1/m at 1.6 and 2.0 m.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon
from test_fds_domain_defects import _FAR, _ISO, _fed_field, _sampler, _vis_model

from pyfds_evac.core.fds_coverage import (
    apply_coverage_policy,
    check_fds_coverage,
    count_outside,
)
from pyfds_evac.core.fds_sampling import FdsDomainError
from pyfds_evac.core.fed import FdsHeatField
from pyfds_evac.core.route_graph import StageEdge, _los_stats, _polyline_stats
from pyfds_evac.core.smoke_speed import ExtinctionField


def test_strict_extinction_names_quantity_position_and_time():
    field = ExtinctionField(
        _sampler("SOOT EXTINCTION COEFFICIENT"), require_fds_coverage=True
    )
    assert field.sample_extinction(3.0, 0.5, 0.5) == 0.03
    with pytest.raises(FdsDomainError) as excinfo:
        field.sample_extinction(3.0, 7.25, 0.5)
    message = str(excinfo.value)
    assert "SOOT EXTINCTION COEFFICIENT" in message
    assert "(7.25, 0.50)" in message
    assert "t=3.0 s" in message


def test_ambient_extinction_outside_reads_zero():
    field = ExtinctionField(_sampler("SOOT EXTINCTION COEFFICIENT"))
    assert field.sample_extinction(3.0, 7.25, 0.5) == 0.0


def test_strict_fed_and_heat_raise_outside():
    gas = _fed_field(co=_FAR, co2=_FAR, o2=_FAR, require_fds_coverage=True)
    with pytest.raises(FdsDomainError, match="CARBON MONOXIDE"):
        gas.sample_inputs(3.0, 0.5, 0.5)
    heat = FdsHeatField(_sampler("TEMPERATURE", _FAR), require_fds_coverage=True)
    with pytest.raises(FdsDomainError, match="TEMPERATURE"):
        heat.sample_inputs(3.0, 0.5, 0.5)


def test_strict_mode_does_not_hide_the_horizon():
    """Past the FDS output the horizon error wins over the domain (I4)."""
    from pyfds_evac.core.fds_sampling import FdsHorizonError

    field = ExtinctionField(
        _sampler("SOOT EXTINCTION COEFFICIENT"), require_fds_coverage=True
    )
    with pytest.raises(FdsHorizonError):
        field.sample_extinction(30.0, 7.25, 0.5)


def test_covers_leaves_the_subslice_cache_alone():
    """Asking for coverage must not change which subslice a sample reads."""
    sampler = _sampler("SOOT EXTINCTION COEFFICIENT")
    sampler.sample(3.0, 0.5, 0.5)
    last = sampler._last_subslice
    assert sampler.covers(0.5, 0.5) and not sampler.covers(7.0, 0.5)
    assert sampler._last_subslice is last


def test_strict_observer_off_the_grid_raises():
    model = _vis_model(visible=True, require_fds_coverage=True)
    with pytest.raises(FdsDomainError, match="sign visibility"):
        model.node_is_visible(0.0, -20.0, 0.0, "s")


def test_sign_off_the_grid_warns_by_default(caplog):
    signs = {"in": {"x": 1.0, "y": 0.0}, "out": {"x": 6.5, "y": 0.0}}
    with caplog.at_level(logging.WARNING):
        model = _vis_model(visible=True, signs=signs)
    assert model.signs_outside_grid() == {"out": pytest.approx(4.0)}
    assert any("out (4.00 m)" in r.getMessage() for r in caplog.records)


def test_sign_off_the_grid_raises_in_strict_mode():
    signs = {"out": {"x": 6.5, "y": 0.0}}
    with pytest.raises(FdsDomainError, match="out"):
        _vis_model(visible=True, signs=signs, require_fds_coverage=True)


def _graph(*edges):
    return SimpleNamespace(
        edges={e.source: [e] for e in edges},
    )


def test_coverage_report_measures_what_lies_outside():
    """Domain x 0..30; the scenario reaches to x = -12, as the t-junction test."""
    samplers = [
        _sampler(
            "SOOT EXTINCTION COEFFICIENT",
            (0.0, 15.0, 0.0, 13.0),
            (15.0, 30.0, 0.0, 13.0),
        )
    ]
    walkable = Polygon([(-12, 10), (30, 10), (30, 13), (-12, 13)])
    raw = {
        "exits": {"A": {"coordinates": [(-12, 10), (-11, 10), (-11, 13), (-12, 13)]}},
        "checkpoints": {"in": {"coordinates": [(5, 10), (6, 10), (6, 13), (5, 13)]}},
    }
    edge = StageEdge("cp", "A", 41.5, [(29.0, 11.5), (-11.5, 11.5)])
    report = check_fds_coverage(
        walkable=walkable, raw=raw, samplers=samplers, stage_graph=_graph(edge)
    )
    assert report.walkable_outside_m2 == pytest.approx(36.0, abs=0.01)
    assert report.areas_outside_m2 == {"exit A": pytest.approx(3.0)}
    assert report.edges_outside_m == {"cp -> A": pytest.approx(11.5, abs=0.01)}
    assert report.signs_outside == ["A"]  # the exit's sign at its centroid
    assert not report.is_empty
    with pytest.raises(FdsDomainError, match="exit A"):
        apply_coverage_policy(report, require_fds_coverage=True)


def test_coverage_report_counts_a_hole_between_subslices():
    samplers = [
        _sampler(
            "SOOT EXTINCTION COEFFICIENT", (0.0, 7.5, 0.0, 2.0), (15.0, 30.0, 0.0, 2.0)
        )
    ]
    walkable = Polygon([(0, 0), (30, 0), (30, 2), (0, 2)])
    report = check_fds_coverage(walkable=walkable, raw={}, samplers=samplers)
    assert report.walkable_outside_m2 == pytest.approx(15.0)


def test_coverage_report_is_empty_inside_the_domain(caplog):
    samplers = [_sampler("TEMPERATURE", (0.0, 30.0, 0.0, 13.0))]
    walkable = Polygon([(0, 0), (30, 0), (30, 13), (0, 13)])  # on the faces
    report = check_fds_coverage(walkable=walkable, raw={}, samplers=samplers)
    assert report.is_empty
    with caplog.at_level(logging.WARNING):
        apply_coverage_policy(report, require_fds_coverage=True)
    assert not caplog.records


def test_count_outside_counts_flagged_rows():
    rows = [
        {"agent_id": 1, "in_fds_domain": False},
        {"agent_id": 1, "in_fds_domain": False},
        {"agent_id": 2, "in_fds_domain": True},
        {"agent_id": 3},
    ]
    assert count_outside(rows, 0.5) == {"rows": 2, "agents": 1, "agent_seconds": 1.0}


@pytest.mark.parametrize("x_to", [20.0, 3.0])
def test_route_samples_outside_stay_finite(x_to):
    """A line fully or partly outside reads K = 0 there, never NaN."""
    field = ExtinctionField(_sampler("SOOT EXTINCTION COEFFICIENT", (0.0, 4.0, 0, 1)))
    mean, worst = _los_stats(10.0, 0.5, x_to, 0.5, 3.0, field, 1.0, abs(x_to - 10))
    assert math.isfinite(mean) and math.isfinite(worst)
    mean, worst = _polyline_stats([(10.0, 0.5), (x_to, 0.5)], 3.0, field, 1.0)
    assert math.isfinite(mean) and math.isfinite(worst)


def _iso_scenario(tmp_path: Path) -> Path:
    """The ISO corridor walkable to x = 60 m, one agent spawned at x 55..56.

    The exit moves to x 40..41 m so that the agent walks 14 m, 5 m of them
    outside the mesh (x > 50 m) and 9 m inside.
    """
    config = json.loads((_ISO / "config.json").read_text())
    dist = next(iter(config["distributions"].values()))
    dist["coordinates"] = [[55.0, -0.5], [56.0, -0.5], [56.0, 0.5], [55.0, 0.5]]
    exit_ = next(iter(config["exits"].values()))
    exit_["coordinates"] = [[40.0, -0.5], [41.0, -0.5], [41.0, 0.5], [40.0, 0.5]]
    config["config"]["simulation_settings"]["simulationParams"][
        "max_simulation_time"
    ] = 20.0
    (tmp_path / "config.json").write_text(json.dumps(config))
    (tmp_path / "geometry.wkt").write_text(
        "POLYGON ((60 -1, 60 1, -50 1, -50 -1, 60 -1))\n"
    )
    shutil.copy(_ISO / "build_geometry.py", tmp_path / "build_geometry.py")
    return tmp_path / "config.json"


def _iso_opts(**overrides):
    base = dict(
        seed=420,
        fds_dir=str(_ISO / "fds"),
        constant_extinction=None,
        smoke_update_interval=0.5,
        smoke_slice_height=2.0,
        disable_tenability=True,
        fed_threshold=1.0,
        fic_alpha=0.7,
        fic_min_factor=0.3,
        enable_rerouting=False,
        reroute_interval=1.0,
        vis_cache=None,
        incapacitation_mode="deterministic",
        susceptibility_sigma=0.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _iso_run(tmp_path, **overrides):
    from pyfds_evac.core.run_config import build_run_kwargs
    from pyfds_evac.core.scenario import load_scenario, run_scenario

    scenario = load_scenario(str(_iso_scenario(tmp_path)))
    return run_scenario(scenario, **build_run_kwargs(scenario, _iso_opts(**overrides)))


def test_coupled_run_flags_the_rows_outside(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        result = _iso_run(tmp_path)
    try:
        rows = result.smoke_history
        assert rows
        for row in rows:
            assert row["in_fds_domain"] is (row["x"] <= 50.0)
            if not row["in_fds_domain"]:
                assert row["extinction_per_m"] == 0.0
        outside = [r for r in rows if not r["in_fds_domain"]]
        assert outside and len(outside) < len(rows)
        counts = result.metrics["fds_outside"]
        assert counts["rows"] == len(outside)
        assert counts["agents"] == 1
        coverage = result.metrics["fds_coverage"]
        assert coverage["walkable_outside_m2"] == pytest.approx(20.0)
        assert coverage["areas_outside_m2"] == {
            "distribution jps-distributions_0": pytest.approx(1.0)
        }
        messages = [r.getMessage() for r in caplog.records]
        assert any("FDS coverage: outside" in m for m in messages)
        assert any("Outside the FDS domain: 1 agent(s)" in m for m in messages)
    finally:
        result.cleanup()


def test_coupled_run_strict_mode_stops_at_setup(tmp_path):
    with pytest.raises(FdsDomainError) as excinfo:
        _iso_run(tmp_path, require_fds_coverage=True)
    message = str(excinfo.value)
    assert "walkable area 20.00 m²" in message
    assert "distribution jps-distributions_0" in message


def test_history_csv_carries_the_flag(tmp_path):
    import run as cli

    rows = [{"time_s": 0.0, "agent_id": 1, "x": 55.0, "y": 0.0, "in_fds_domain": False}]
    path = tmp_path / "smoke.csv"
    cli._write_smoke_history_csv(rows, str(path))
    with path.open() as handle:
        record = next(csv.DictReader(handle))
    assert record["in_fds_domain"] == "False"
    cli._write_smoke_history_csv([{"time_s": 0.0}], str(path))
    assert "in_fds_domain" not in path.read_text().splitlines()[0]
