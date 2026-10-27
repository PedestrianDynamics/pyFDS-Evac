"""ISO 20414:2020 Test 16 (Table 18) with the smoke read from FDS output (#850).

The synthetic test ``test_iso_test_16_familiar_exit.py`` fills the east of the
room and the exit-2 door strip with a static extinction coefficient K.
``assets/iso_test_16_fire`` puts the same box into five FDS decks, so the
extinction reaches the router through

    deck → FDS → fdsreader → SliceFieldSampler → route cost → exit choice

The box is on from t = 0 in both, so the FDS runs are compared with the hand
values of the synthetic test: tau_2 = K × 4.5 against the refusal limit 6 and
the deadband 0.6.

The builder, deck and drift tests run without FDS. The premise and run tests
read the output the maintainer produced with the loop in the asset README and
skip until it is on the data store.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path

import pytest
from shapely import wkt
from test_iso_test_8_fire import builder_module, check_premise
from test_iso_test_16_familiar_exit import (
    BRACKET_ABOVE_PER_M,
    BRACKET_BELOW_PER_M,
    EXPECTED_EXIT_2,
    FRAME_S,
    OCCUPANT_A,
    OCCUPANT_B,
    OCCUPANTS,
    SMOKE_LEVELS_PER_M,
    SMOKE_REROUTE_S,
    _repeat_until_stable,
    _scenario,
    _smoke_run,
    _smoke_scenario,
)

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

pytestmark = [pytest.mark.iso20414, pytest.mark.nist_tn1822]

ASSET = Path("assets/iso_test_16_fire")
SCIEBO = Path.home() / "sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de"
FIRE_FDS = Path(
    os.environ.get(
        "ISO_TEST_16_FIRE_FDS", SCIEBO / "fds-evac-data" / "iso_test_16_fire"
    )
)

DECKS = {"k0p05": 0.05, "k0p10": 0.10, "k0p20": 0.20, "k0p5": 0.5, "k3": 3.0}
CELL_M = 0.25
# The runs end by about 6 s; the 10 s frame covers them. The box mixes out
# later (2.5 % low at 30 s), which no run reads.
READ_HORIZON_S = 10.0


def _builder():
    return builder_module("iso16f_builder", ASSET)


@pytest.mark.parametrize("sub", DECKS)
def test_deck_matches_builder(sub):
    builder = _builder()
    deck = ASSET / f"iso_test_16_fire_{sub}.fds"
    assert deck.read_text(encoding="utf-8") == builder.deck_text(DECKS[sub])
    assert builder.DECK_KS == tuple(DECKS.values())


def test_config_matches_synthetic_scenario():
    config = json.loads((ASSET / "config.json").read_text(encoding="utf-8"))
    scenario = _smoke_scenario(1, OCCUPANT_A[0], OCCUPANT_A[1])
    for key in ("exits", "distributions", "journeys", "transitions"):
        assert config[key] == scenario.raw[key], key
    shape = wkt.loads((ASSET / "geometry.wkt").read_text(encoding="utf-8"))
    assert shape.equals(wkt.loads(scenario.walkable_area_wkt))


# --- Reading the FDS output -------------------------------------------------


def _needs_output(*subs: str) -> list:
    """Marks of a test that reads the output of the decks *subs*."""
    smvs = [FIRE_FDS / sub / f"iso_test_16_fire_{sub}.smv" for sub in subs]
    absent = [smv.name for smv in smvs if not smv.is_file()]
    return [
        pytest.mark.external_data,
        pytest.mark.skipif(
            bool(absent),
            reason=f"{absent} absent under {FIRE_FDS}; set ISO_TEST_16_FIRE_FDS",
        ),
    ]


@pytest.fixture(scope="module")
def fields(fds_read_only):
    """The extinction field of a deck, loaded once."""
    loaded: dict[str, ExtinctionField] = {}

    def get(sub: str) -> ExtinctionField:
        if sub not in loaded:
            loaded[sub] = ExtinctionField.from_fds(str(fds_read_only(FIRE_FDS / sub)))
        return loaded[sub]

    return get


def _fds_run(seed: int, occupant: tuple[dict, str | None], field) -> dict:
    """``_smoke_run`` with *field* in place of ``_BoxSmoke``."""
    parameters, journey = occupant
    model = SmokeSpeedModel(
        field, SmokeSpeedConfig(fds_dir=".", speed_law="lund", update_interval_s=1.0)
    )
    reroute = RerouteConfig(
        reevaluation_interval_s=SMOKE_REROUTE_S,
        cost_config=RouteCostConfig.from_routing_params({"sampling_step_m": 0.25}),
    )
    result = run_scenario(
        _smoke_scenario(seed, parameters, journey),
        seed=seed,
        reroute_config=reroute,
        smoke_speed_model=model,
    )
    try:
        frames = result.trajectory_dataframe()["frame"]
        return {
            "exits": [r["exit_id"] for r in result.exit_history or []],
            "routes": [
                (r["time_s"], r["old_exit"], r["new_exit"], r["reason"])
                for r in result.route_history or []
            ],
            "evacuated": result.agents_evacuated,
            "exit_time_s": float(frames.max()) * FRAME_S,
        }
    finally:
        result.cleanup()


def _fds_exit_used(seed, parameters, occupant, field) -> str:
    run = _fds_run(seed, occupant, field)
    assert run["evacuated"] == 1, f"seed {seed}: occupant did not leave"
    assert len(run["exits"]) == 1, f"seed {seed}: exits {run['exits']}"
    return run["exits"][0]


@pytest.mark.parametrize(
    "sub", [pytest.param(sub, marks=_needs_output(sub)) for sub in DECKS]
)
def test_premise(sub, fields, capsys):
    """Traps 1 and 2 of the contract: ambient oxygen and the buoyancy of soot."""
    k_target = DECKS[sub]
    x0, x1, y0, y1 = _builder().SOOT_BOX_XB[:4]
    area = wkt.loads(_scenario(1, {}).walkable_area_wkt)
    edge = check_premise(
        fields(sub), area, (x0, y0, x1, y1), k_target, CELL_M, READ_HORIZON_S
    )
    out = FIRE_FDS / sub / f"iso_test_16_fire_{sub}.out"
    with capsys.disabled():
        print(f"\n{sub}: edge values (K = {k_target:g} 1/m)")
        for (x, y), k in sorted(edge.items()):
            print(f"  ({x:5.1f}, {y:4.1f}) K = {k:.3f}")
        if out.is_file():
            head = [line.strip() for line in out.read_text().splitlines()[:40]]
            print("  ", next((ln for ln in head if "Revision" in ln), "no revision"))


# --- Runs -------------------------------------------------------------------

LEVEL_DECKS = {0.05: "k0p05", 0.5: "k0p5", 3.0: "k3"}
assert tuple(LEVEL_DECKS) == SMOKE_LEVELS_PER_M


@pytest.mark.parametrize(
    "name, level",
    [
        pytest.param(
            name,
            level,
            marks=_needs_output(LEVEL_DECKS[level]),
            id=f"{name}-{level:g}",
        )
        for name in OCCUPANTS
        for level in SMOKE_LEVELS_PER_M
    ],
)
def test_expected_exit_2(name, level, fields):
    """Exit-2 usage per occupant and K, under the stopping rule of the module.

    Each outcome is 0 or 1, so the rule stops after 11 runs (seeds 1 to 11).
    """
    occupant = OCCUPANTS[name]
    field = fields(LEVEL_DECKS[level])
    exit_used = functools.partial(_fds_exit_used, occupant=occupant, field=field)
    fraction, runs, _ = _repeat_until_stable(occupant[0], exit_used)
    print(f"  {name}, K={level}: exit 2 used {fraction:.3f} after {runs} runs")
    expected = EXPECTED_EXIT_2[name][SMOKE_LEVELS_PER_M.index(level)]
    assert fraction == expected


@pytest.mark.external_data
@pytest.mark.skipif(
    not (FIRE_FDS / "k3" / "iso_test_16_fire_k3.smv").is_file(),
    reason=f"iso_test_16_fire_k3.smv absent under {FIRE_FDS}",
)
def test_affiliated_occupant_on_k3(fields, capsys):
    """A knows exit 2 only: no reroute, no fallback row, slower through smoke."""
    clear = _smoke_run(1, OCCUPANT_A, 0.0)
    smoky = _fds_run(1, OCCUPANT_A, fields("k3"))
    assert smoky["exits"] == ["exit_2"]
    assert smoky["routes"] == []
    assert smoky["evacuated"] == 1
    assert smoky["exit_time_s"] > clear["exit_time_s"]
    # On the FDS 6.10.1 output (synthetic box 6.2 s, clear 4.9 s).
    assert smoky["exit_time_s"] == pytest.approx(6.0, abs=0.05)
    with capsys.disabled():
        print(
            f"\nA on k3: exit at {smoky['exit_time_s']:.1f} s, "
            f"clear {clear['exit_time_s']:.1f} s"
        )


@pytest.mark.parametrize(
    "sub, routes",
    [
        pytest.param(
            sub,
            routes,
            marks=_needs_output(sub),
        )
        for sub, routes in (
            ("k0p5", [(0.0, "exit_2", "exit_1", "allocation_preference")]),
            ("k3", [(0.0, "exit_2", "exit_1", "allocation_preference")]),
            ("k0p05", []),
        )
    ],
)
def test_preference_yields_at_spawn(sub, routes, fields):
    assert _fds_run(1, OCCUPANT_B, fields(sub))["routes"] == routes


@pytest.mark.parametrize(
    "sub, exit_id",
    [
        pytest.param("k0p10", "exit_2", marks=_needs_output("k0p10")),
        pytest.param("k0p20", "exit_1", marks=_needs_output("k0p20")),
    ],
)
def test_deadband_bracket(sub, exit_id, fields):
    """tau_2 = 0.45 (K = 0.10) stays; tau_2 = 0.9 (K = 0.20) yields."""
    assert DECKS[sub] in (BRACKET_BELOW_PER_M, BRACKET_ABOVE_PER_M)
    for seed in (1, 2):
        run = _fds_run(seed, OCCUPANT_B, fields(sub))
        assert run["exits"] == [exit_id], f"seed {seed}"
