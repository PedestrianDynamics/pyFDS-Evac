"""ISO 20414:2020 Test 8 (Table 9) with the smoke read from FDS output (#850).

The synthetic test ``test_iso_test_8_route_allocation.py`` switches a box of
extinction on at t = 5 s in the main passage. ``assets/iso_test_8_fire`` puts the
same box into an FDS deck, so the extinction reaches the router through

    deck → FDS → fdsreader → SliceFieldSampler → route cost → exit choice

An ``&INIT`` acts at t = 0, so the FDS smoke is there from the start. These
tests check allocation under smoke present at spawn: the preference yields at
spawn and the hard allocation holds. The 5 s onset, the before/inside/past
groups and the 1.255 m threshold stay synthetic-only.

The builder, deck and drift tests run without FDS. The premise and run tests
read the output the maintainer produced with the loop in the asset README and
skip until it is on the data store. The runs are compared with the synthetic
box switched on at t = 0 (``_BoxSmokeAt0``), so a difference is due to the FDS
field and not to the scenario.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path

import numpy as np
import pytest
from shapely import wkt
from shapely.geometry import Point, box
from test_iso_test_8_route_allocation import (
    FRAME_RATE,
    MAIN,
    MAIN_ROOMS,
    OCCUPANTS,
    ROOMS,
    SAMPLING_STEP_M,
    SECONDARY,
    SEED,
    SMOKE_ON_S,
    _BoxSmoke,
    _nearest_exit,
    _room_of,
    _run,
    _scenario,
    _usage,
    _walkable,
)

from pyfds_evac.config.parameters import REROUTE_INTERVAL_S
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

pytestmark = [pytest.mark.iso20414, pytest.mark.nist_tn1822]

ASSET = Path("assets/iso_test_8_fire")
SCIEBO = Path.home() / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
FIRE_FDS = Path(
    os.environ.get("ISO_TEST_8_FIRE_FDS", SCIEBO / "fds-evac-data" / "iso_test_8_fire")
)

# The soot table of the model contract: K [1/m], Y, T_box [C]. The builders of
# both fire assets carry the same two formulas, so it is checked once, here.
SOOT_TABLE = [
    (0.05, "4.79465E-06", "19.9981"),
    (0.10, "9.58930E-06", "19.9961"),
    (0.20, "1.91786E-05", "19.9923"),
    (0.5, "4.79465E-05", "19.9807"),
    (1.0, "9.58930E-05", "19.9614"),
    (3.0, "2.87679E-04", "19.8844"),
    (5.0, "4.79465E-04", "19.8073"),
]
DECKS = {"k5": 5.0, "k1": 1.0}
CELL_M = 0.2
LATTICE_M = 0.5
LATE_S = 30.0
# Edge nodes (2 x 0.2 m at K/2) plus the 1 s speed update; hand bound 0.13 s.
END_TIME_ABS_S = 0.5


def builder_module(name: str, asset: Path):
    spec = importlib.util.spec_from_file_location(name, asset / "build_geometry.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _builder():
    return builder_module("iso8f_builder", ASSET)


@pytest.mark.parametrize("k, y, t", SOOT_TABLE)
def test_soot_table(k, y, t):
    builder = _builder()
    assert f"{builder.soot_mass_fraction(k):.5E}" == y
    assert f"{builder.box_temperature_c(k):.4f}" == t


@pytest.mark.parametrize("sub", DECKS)
def test_deck_matches_builder(sub):
    builder = _builder()
    k = DECKS[sub]
    deck = ASSET / f"iso_test_8_fire_{sub}.fds"
    assert deck.read_text(encoding="utf-8") == builder.deck_text(k)
    assert builder.DECK_KS == tuple(DECKS.values())


def test_config_matches_synthetic_scenario():
    config = json.loads((ASSET / "config.json").read_text(encoding="utf-8"))
    raw = _scenario().raw
    for key in ("exits", "distributions", "journeys", "transitions"):
        assert config[key] == raw[key], key
    shape = wkt.loads((ASSET / "geometry.wkt").read_text(encoding="utf-8"))
    assert shape.equals(_walkable())


def test_box_covers_the_passage():
    x0, x1, y0, y1 = _builder().SOOT_BOX_XB[:4]
    assert box(x0, y0, x1, y1).intersection(_walkable()).area == pytest.approx(2.2)


# --- Reading the FDS output -------------------------------------------------


def _needs_output(sub: str) -> list:
    """Marks of a test that reads the output of deck *sub*."""
    smv = FIRE_FDS / sub / f"iso_test_8_fire_{sub}.smv"
    return [
        pytest.mark.external_data,
        pytest.mark.skipif(
            not smv.is_file(),
            reason=f"{smv.name} absent under {FIRE_FDS}; set ISO_TEST_8_FIRE_FDS",
        ),
    ]


def _fds_field(fds_read_only, sub: str) -> ExtinctionField:
    return ExtinctionField.from_fds(str(fds_read_only(FIRE_FDS / sub)))


def lattice_points(area, step: float = LATTICE_M):
    """Walkable points of a *step* lattice anchored at the origin."""
    x0, y0, x1, y1 = area.bounds
    for x in np.arange(np.ceil(x0 / step) * step, x1, step):
        for y in np.arange(np.ceil(y0 / step) * step, y1, step):
            if area.covers(Point(x, y)):
                yield float(x), float(y)


def check_premise(field, area, soot_box, k_target: float, cell: float) -> dict:
    """The field is the prescribed box, and it does not move (model contract B).

    *soot_box* is ``(x_min, y_min, x_max, y_max)``. Returns the edge values for
    the report.
    """
    shape = box(*soot_box)
    inner, outer = shape.buffer(-cell), shape.buffer(cell)
    inside = [p for p in lattice_points(area) if inner.covers(Point(*p))]
    outside = [p for p in lattice_points(area) if not outer.intersects(Point(*p))]
    assert inside and outside
    for t in (0.0, LATE_S):
        for x, y in inside:
            k = field.sample_extinction(t, x, y)
            assert k == pytest.approx(k_target, rel=0.01), f"t={t} ({x}, {y})"
        for x, y in outside:
            k = field.sample_extinction(t, x, y)
            assert k <= 0.01 * k_target, f"t={t} ({x}, {y})"
    for x, y in inside + outside:
        early, late = (
            field.sample_extinction(0.0, x, y),
            field.sample_extinction(LATE_S, x, y),
        )
        assert late == pytest.approx(early, rel=0.01, abs=1e-6), f"({x}, {y})"
    assert max(field.sample_extinction(0.0, x, y) for x, y in inside) > 0.5 * k_target
    ring = [
        p
        for p in lattice_points(area)
        if outer.intersects(Point(*p)) and not inner.covers(Point(*p))
    ]
    return {p: field.sample_extinction(0.0, *p) for p in ring}


@pytest.mark.parametrize(
    "sub", [pytest.param(sub, marks=_needs_output(sub)) for sub in DECKS]
)
def test_premise(sub, fds_read_only, capsys):
    """Traps 1 and 2 of the contract: ambient oxygen and the buoyancy of soot."""
    k_target = DECKS[sub]
    x0, x1, y0, y1 = _builder().SOOT_BOX_XB[:4]
    edge = check_premise(
        _fds_field(fds_read_only, sub),
        _walkable(),
        (x0, y0, x1, y1),
        k_target,
        CELL_M,
    )
    out = FIRE_FDS / sub / f"iso_test_8_fire_{sub}.out"
    with capsys.disabled():
        print(f"\n{sub}: edge values (K = {k_target:g} 1/m)")
        for (x, y), k in sorted(edge.items()):
            print(f"  ({x:5.1f}, {y:4.1f}) K = {k:.3f}")
        if out.is_file():
            head = [line.strip() for line in out.read_text().splitlines()[:40]]
            print("  ", next((ln for ln in head if "Revision" in ln), "no revision"))


# --- Runs -------------------------------------------------------------------


class _BoxSmokeAt0(_BoxSmoke):
    """The synthetic box, on from t = 0 as an ``&INIT`` is."""

    def sample_extinction(self, t: float, x: float, y: float) -> float:
        return super().sample_extinction(max(t, SMOKE_ON_S), x, y)


def _run_with_field(field, mode: str | None, anticipate: bool) -> dict:
    """The rerouting run of ``_run`` with *field* in place of ``_BoxSmoke``."""
    params = {"sampling_step_m": SAMPLING_STEP_M, "anticipate": anticipate}
    reroute = RerouteConfig(
        reevaluation_interval_s=REROUTE_INTERVAL_S,
        cost_config=RouteCostConfig.from_routing_params(params),
    )
    model = SmokeSpeedModel(
        field, SmokeSpeedConfig(fds_dir=".", speed_law="lund", update_interval_s=1.0)
    )
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(
            _scenario(mode=mode),
            seed=SEED,
            reroute_config=reroute,
            smoke_speed_model=model,
        )
    try:
        df = result.trajectory_dataframe().sort_values(["id", "frame"])
        # Agent ids count on across the runs of one process; number them from 0.
        first_id = int(df.id.min())
        last = df.groupby("id").last()
        final = {
            int(i) - first_id: _nearest_exit(row.x, row.y) for i, row in last.iterrows()
        }
        home = {
            int(i) - first_id: _room_of(row.x, row.y)
            for i, row in df.groupby("id").first().iterrows()
        }
        per_room: dict[int, dict[str, list[str]]] = {
            room: {"assigned": [], "final": []} for room in ROOMS
        }
        for rec in result.exit_history or []:
            agent = rec["agent_id"] - first_id
            per_room[home[agent]]["assigned"].append(rec["exit_id"])
            per_room[home[agent]]["final"].append(final[agent])
        return {
            "per_room": per_room,
            "home": home,
            "t_end_s": float(df.frame.max()) / FRAME_RATE,
            "evacuated": result.agents_evacuated,
            "routes": sorted(
                (
                    r["agent_id"] - first_id,
                    r["reason"],
                    r["old_exit"],
                    r["new_exit"],
                    r["time_s"],
                )
                for r in result.route_history or []
            ),
            "exits": sorted(
                (r["agent_id"] - first_id, r["exit_id"])
                for r in result.exit_history or []
            ),
        }
    finally:
        result.cleanup()


# case -> (deck, journey allocation mode, anticipate)
CASES = {
    "preference": ("k5", None, False),
    "weak": ("k1", None, False),
    "hard": ("k5", "hard", False),
    "foresight": ("k5", None, True),
}


@pytest.fixture(scope="module")
def cases(fds_read_only):
    """Run each case once, on the FDS field and on the synthetic box at t = 0."""
    done: dict[tuple[str, str], dict] = {}

    def get(case: str, source: str) -> dict:
        if (case, source) not in done:
            sub, mode, anticipate = CASES[case]
            field = (
                _fds_field(fds_read_only, sub)
                if source == "fds"
                else _BoxSmokeAt0(DECKS[sub])
            )
            done[case, source] = _run_with_field(field, mode, anticipate)
        return done[case, source]

    return get


@pytest.fixture(scope="module")
def clear_run():
    return _run(rerouting=True, mode="hard")


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, marks=_needs_output(CASES[case][0])) for case in CASES],
)
def test_fds_run(case, cases, clear_run, capsys):
    """The FDS box gives the routes and exits of the synthetic box at t = 0."""
    run, synthetic = cases(case, "fds"), cases(case, "synthetic")
    main_agents = sorted(a for a, room in run["home"].items() if room in MAIN_ROOMS)
    assert run["evacuated"] == 23
    assert len(main_agents) == 15

    if case == "hard":
        assert run["routes"] == []
        assert _usage(run) == _usage(clear_run)
        assert run["t_end_s"] > clear_run["t_end_s"]
    else:
        assert len(run["routes"]) == 15
        assert [r[0] for r in run["routes"]] == main_agents
        assert {r[1:] for r in run["routes"]} == {
            ("allocation_preference", MAIN, SECONDARY, 0.0)
        }
        for room, use in _usage(run).items():
            assert use == {MAIN: 0, SECONDARY: OCCUPANTS[room]}, f"room {room}"

    assert run["routes"] == synthetic["routes"]
    assert run["exits"] == synthetic["exits"]
    assert run["t_end_s"] == pytest.approx(synthetic["t_end_s"], abs=END_TIME_ABS_S)
    with capsys.disabled():
        print(
            f"\n{case}: end {run['t_end_s']:.1f} s on FDS, "
            f"{synthetic['t_end_s']:.1f} s synthetic t_on = 0, "
            f"{clear_run['t_end_s']:.1f} s clear"
        )
        for room, use in _usage(run).items():
            print(f"  room {room:2d}: main {use[MAIN]}, secondary {use[SECONDARY]}")
