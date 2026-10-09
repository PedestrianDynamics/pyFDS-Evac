"""Console output of a run (issue #486).

A default run prints setup, progress and the outcome. The rerouting trace is
a debug log, shown with ``--debug``; fdsreader's repeated module-parse
warning reaches the console once.

The scenario is synthetic: a 10 x 6 m room with one door in each end wall.
"""

from __future__ import annotations

import logging

import pytest
from shapely.geometry import Polygon, box

from pyfds_evac import cli
from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.run_outputs import _RepeatedFdsreaderWarning
from pyfds_evac.core.scenario import Scenario, run_scenario

LENGTH_M = 10.0
WIDTH_M = 6.0
SEED = 3
TRACE = "Reroute debug"
FDSREADER_WARNING = (
    "Module vents: could not convert string to float: '!'\n"
    "The error can be safely ignored if not requiring the vents module."
)


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario() -> Scenario:
    doors = {
        "west": box(-1.0, 2.5, 0.0, 3.5),
        "east": box(LENGTH_M, 2.5, LENGTH_M + 1.0, 3.5),
    }
    walkable = box(0.0, 0.0, LENGTH_M, WIDTH_M)
    for door in doors.values():
        walkable = walkable.union(door)
    sim_params = {"max_simulation_time": 5.0, "model_type": "CollisionFreeSpeedModel"}
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": sim_params,
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            name: {
                "type": "polygon",
                "coordinates": _coords(poly),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
            for name, poly in doors.items()
        },
        "distributions": {
            "room": {
                "type": "polygon",
                "coordinates": _coords(box(0.5, 0.5, LENGTH_M - 0.5, WIDTH_M - 0.5)),
                "parameters": {
                    "number": 6,
                    "radius": 0.2,
                    "v0": 1.2,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


@pytest.fixture
def restore_logging():
    """Undo what cli._configure_logging does to the root and model loggers."""
    root = logging.getLogger()
    model = logging.getLogger("pyfds_evac")
    saved = (
        list(root.filters),
        list(model.handlers),
        model.level,
        model.propagate,
    )
    # An earlier cli.main or run_stream call in this process leaves its filter
    # installed, with the warnings it has already passed; start without it.
    root.filters[:] = [
        f for f in root.filters if not isinstance(f, _RepeatedFdsreaderWarning)
    ]
    yield
    root.filters[:] = saved[0]
    model.handlers[:] = saved[1]
    model.setLevel(saved[2])
    model.propagate = saved[3]


def test_rerouting_trace_is_not_printed_by_default(capsys):
    run_scenario(_scenario(), reroute_config=RerouteConfig(reevaluation_interval_s=1.0))
    out = capsys.readouterr().out
    assert "Evacuated" in out
    assert TRACE not in out


def test_rerouting_trace_is_a_debug_log(caplog):
    with caplog.at_level(logging.DEBUG, logger="pyfds_evac.core.scenario"):
        run_scenario(
            _scenario(), reroute_config=RerouteConfig(reevaluation_interval_s=1.0)
        )
    trace = [r for r in caplog.records if r.getMessage().startswith(TRACE)]
    assert trace
    assert all(r.levelno == logging.DEBUG for r in trace)


def test_debug_flag_prints_model_debug_lines(capsys, restore_logging):
    args = cli._build_parser().parse_args(["--scenario", "x.json", "--debug"])
    assert args.debug
    cli._configure_logging(args.debug)
    logging.getLogger("pyfds_evac.core.scenario").debug("Reroute debug pass: x")
    assert capsys.readouterr().out == "Reroute debug pass: x\n"


def test_debug_is_off_by_default(restore_logging):
    args = cli._build_parser().parse_args(["--scenario", "x.json"])
    assert not args.debug
    cli._configure_logging(args.debug)
    model = logging.getLogger("pyfds_evac.core.scenario")
    assert not model.isEnabledFor(logging.DEBUG)


def test_repeated_fdsreader_warning_reaches_the_console_once(caplog, restore_logging):
    cli._configure_logging(debug=False)
    cli._configure_logging(debug=False)  # a second call adds no second filter
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            logging.warning(FDSREADER_WARNING)
        logging.warning(FDSREADER_WARNING.replace("vents", "devices"))
        logging.warning("an unrelated root warning")
        logging.warning("an unrelated root warning")
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        FDSREADER_WARNING,
        FDSREADER_WARNING.replace("vents", "devices"),
        "an unrelated root warning",
        "an unrelated root warning",
    ]
