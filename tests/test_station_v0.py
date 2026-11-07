"""Station V0 configs: front-door closure, pre-movement bands, horizon (b11).

Both Station decks carry the registered central scenario (time zero is first
flame): the front exit ``jps-exits_0`` closes at 86 s, pre-movement is uniform
per Galea et al. 2008 (p. 473, Reading A), the horizon is 250 s and
``routing.w_queue`` is 0. The static checks pin the committed files against the
approved mapping, which is written out here and not imported from the build
script. The init checks pin what the V0 keys must not move. The run checks run
seed 4 on ``config_full.json`` (455 agents) once per deck, and are slow.
"""

from __future__ import annotations

import collections
import contextlib
import csv
import importlib.util
import io
import json
import sqlite3
import sys
from pathlib import Path

import jupedsim as jps
import pedpy
import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac import cli
from pyfds_evac.core.scenario import _build_model, load_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json

ROOT = Path(__file__).resolve().parents[1]
DECKS = ("station_fahy", "station_nist")
FRONT_EXIT = "jps-exits_0"
T_JAM = 86.0
HORIZON = 250.0
SEED = 4
FPS = 10.0

# The approved mapping (maintainer M3, Reading A): row -> (a, b) in seconds.
DANCE, BAR, OTHER = (25.0, 30.0), (30.0, 35.0), (35.0, 41.0)
BANDS = {
    "Near stage or on dance floor": DANCE,
    "Stage": DANCE,
    "Back wall platform": DANCE,
    "Behind dance floor": DANCE,
    "Center stage-side": DANCE,
    "Near stage door": DANCE,
    "Main bar": BAR,
    "Between bars": BAR,
    "Rear bar / dart room": BAR,
    "Entryway": BAR,
    "Sunroom": BAR,
    "Back hallway": OTHER,
}
PLACED_PER_BAND = {DANCE: 192, BAR: 127, OTHER: 14}

# The vestibule, from the interior-door line to the exterior doorway line.
VESTIBULE = {
    "station_fahy": box(-1.17, -8.92, 0.65, -5.5),
    "station_nist": box(2.44, -17.11, 4.34, -14.36),
}
DOORWAY = {  # y of the exterior doorway line, and the x of its opening
    "station_fahy": (-9.10, -1.108, 0.619),
    "station_nist": (-17.11, 2.44, 4.34),
}

# The front exit as the hand drawing had it, before it moved to the doorway.
HAND_FRONT_EXIT = [
    [-1.544, -11.951],
    [1.311, -11.951],
    [1.311, -13.717],
    [-1.544, -13.717],
    [-1.544, -11.951],
]


def _load(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def nist():
    return _load(
        "station_nist_build_v0", ROOT / "assets/station_nist/build_scenario.py"
    )


@pytest.fixture(scope="module")
def fahy(nist):
    return nist.FB


@pytest.fixture(scope="module")
def mods(fahy, nist):
    return {"station_fahy": fahy, "station_nist": nist}


@pytest.fixture(scope="module")
def default_builds(mods):
    """deck -> the default build's config (333 agents)."""
    return {deck: mod.build()[0] for deck, mod in mods.items()}


@pytest.fixture(scope="module")
def full_configs(fahy, default_builds):
    return {deck: fahy.with_populations(cfg) for deck, cfg in default_builds.items()}


def _file(deck: str, name: str) -> dict:
    return json.loads((ROOT / "assets" / deck / name).read_text())


def _flat(config: dict) -> dict:
    """Leaf values by path, the distribution key replaced by ``*``."""
    out: dict = {}

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                step = "*" if path and path[-1] == "distributions" else key
                walk(value, (*path, step))
            return
        out.setdefault(path, []).append(node)

    walk(config, ())
    return out


def _changed_paths(a: dict, b: dict) -> set[tuple]:
    fa, fb = _flat(a), _flat(b)
    return {p for p in fa.keys() | fb.keys() if fa.get(p) != fb.get(p)}


# ---- static checks: the four committed configs ------------------------------


@pytest.mark.parametrize("name", ["config.json", "config_full.json"])
@pytest.mark.parametrize("deck", DECKS)
def test_the_committed_configs_carry_the_v0_settings(deck, name):
    config = _file(deck, name)
    closing = {
        k: v["closed_after_s"]
        for k, v in config["exits"].items()
        if "closed_after_s" in v
    }
    assert closing == {FRONT_EXIT: T_JAM}
    assert not any("open_from_s" in v for v in config["exits"].values())
    sim = config["config"]["simulation_settings"]["simulationParams"]
    assert sim["max_simulation_time"] == HORIZON
    assert config["routing"]["w_queue"] == 0.0


@pytest.mark.parametrize("name", ["config.json", "config_full.json"])
@pytest.mark.parametrize("deck", DECKS)
def test_every_distribution_has_its_rows_band_and_no_seed_or_offset(deck, name):
    config = _file(deck, name)
    for key, dist in config["distributions"].items():
        params = dist["parameters"]
        low, high = BANDS[params["fahy_row"]]
        assert params["use_premovement"] is True, key
        assert params["premovement_distribution"] == "uniform", key
        assert (params["premovement_param_a"], params["premovement_param_b"]) == (
            low,
            high,
        ), key
        stray = {k for k in params if k.startswith("premovement_")} - {
            "premovement_distribution",
            "premovement_param_a",
            "premovement_param_b",
        }
        assert not stray, (key, stray)


@pytest.mark.parametrize("deck", DECKS)
def test_the_placed_agents_per_band(deck):
    config = _file(deck, "config.json")
    per_band: collections.Counter = collections.Counter()
    for dist in config["distributions"].values():
        params = dist["parameters"]
        per_band[BANDS[params["fahy_row"]]] += params["number"]
    assert dict(per_band) == PLACED_PER_BAND


@pytest.mark.parametrize("deck", DECKS)
def test_the_files_are_what_the_build_script_writes(default_builds, full_configs, deck):
    assert json.loads(json.dumps(default_builds[deck])) == _file(deck, "config.json")
    assert json.loads(json.dumps(full_configs[deck])) == _file(deck, "config_full.json")


def test_station_fahy_front_exit_is_on_the_doorway_line(fahy):
    """M2: exit 0 only. The other exits and the geometry are the drawing's."""
    config, walkable = fahy.build()
    source = json.loads((ROOT / "assets/station_fahy/source/config.json").read_text())
    for exit_id in ("jps-exits_1", "jps-exits_2", "jps-exits_3"):
        assert (
            config["exits"][exit_id]["coordinates"]
            == source["exits"][exit_id]["coordinates"]
        )
    drawn = [
        [round(v, 3) for v in p] for p in source["exits"][FRONT_EXIT]["coordinates"]
    ]
    assert drawn == HAND_FRONT_EXIT
    front = Polygon(config["exits"][FRONT_EXIT]["coordinates"])
    assert front.within(walkable)
    # outside the exterior doors' jambs (y -9.10), between them (x -1.108 .. 0.619)
    assert front.bounds[3] <= -9.10 + 1e-9
    assert front.bounds[0] > -1.11 and front.bounds[2] < 0.62
    for dist in config["distributions"].values():
        assert not Polygon(dist["coordinates"]).intersects(front)


# ---- build options ----------------------------------------------------------

PRE_KEYS = (
    "use_premovement",
    "premovement_distribution",
    "premovement_param_a",
    "premovement_param_b",
)
JAM_PATH = {("exits", FRONT_EXIT, "closed_after_s")}
OPTIONS = {
    "w-queue": (dict(w_queue=0.024), {("routing", "w_queue")}),
    "t-jam-71": (dict(t_jam_s=71.0), JAM_PATH),
    "t-jam-102": (dict(t_jam_s=102.0), JAM_PATH),
    "t-jam-none": (dict(t_jam_s=None), JAM_PATH),
    "premovement-zero": (
        dict(premovement="zero"),
        {("distributions", "*", "parameters", k) for k in PRE_KEYS},
    ),
    "premovement-tracked": (
        dict(premovement="tracked"),
        {("distributions", "*", "parameters", k) for k in PRE_KEYS[1:]},
    ),
}


@pytest.mark.parametrize("option", OPTIONS)
@pytest.mark.parametrize("deck", DECKS)
def test_each_option_touches_only_its_keys(mods, default_builds, deck, option):
    kwargs, expected = OPTIONS[option]
    built = mods[deck].build(mods["station_fahy"].V0Options(**kwargs))[0]
    assert _changed_paths(default_builds[deck], built) == expected


@pytest.mark.parametrize("deck", DECKS)
def test_the_tracked_option_is_18_s_on_the_dance_floor_and_29_s_elsewhere(mods, deck):
    fahy = mods["station_fahy"]
    built = mods[deck].build(fahy.V0Options(premovement="tracked"))[0]
    for dist in built["distributions"].values():
        params = dist["parameters"]
        want = 18.0 if BANDS[params["fahy_row"]] == DANCE else 29.0
        assert params["use_premovement"] is True
        assert params["premovement_distribution"] == "constant"
        assert params["premovement_param_a"] == want
        assert "premovement_param_b" not in params


@pytest.mark.parametrize("deck", DECKS)
def test_the_zero_option_says_false_and_leaves_no_other_key(mods, deck):
    fahy = mods["station_fahy"]
    built = mods[deck].build(fahy.V0Options(premovement="zero"))[0]
    for dist in built["distributions"].values():
        params = dist["parameters"]
        assert params["use_premovement"] is False
        assert not {k for k in params if k.startswith("premovement_")}


@pytest.mark.parametrize("deck", DECKS)
def test_a_non_default_option_needs_out_and_never_writes_the_deck(mods, deck, tmp_path):
    main = mods[deck].main
    deck_dir = ROOT / "assets" / deck
    names = ("config.json", "config_full.json", "geometry.wkt")
    before = {n: (deck_dir / n).read_bytes() for n in names}
    with pytest.raises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
        main(["--t-jam", "71"])
    with pytest.raises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
        main(["--t-jam", "71", "--out", str(deck_dir)])
    args = ["--t-jam", "71", "--w-queue", "0.024", "--out", str(tmp_path)]
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(args) == 0
    assert {n: (deck_dir / n).read_bytes() for n in names} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "build_options.json",
        "config.json",
        "config_full.json",
        "geometry.wkt",
    ]
    assert json.loads((tmp_path / "build_options.json").read_text()) == {
        "deck": deck,
        "w_queue": 0.024,
        "t_jam_s": 71.0,
        "premovement": "galea",
    }
    out = json.loads((tmp_path / "config_full.json").read_text())
    assert out["exits"][FRONT_EXIT]["closed_after_s"] == 71.0
    assert out["routing"]["w_queue"] == 0.024


# ---- initialisation at seed 4 -----------------------------------------------


def _init(deck: str, config: dict, seed: int, tmp_path: Path):
    """Draws by agent id (position, radius, v0, familiarity) and pre-movement times."""
    scenario = load_scenario(str(ROOT / "assets" / deck / "config.json"))
    path = tmp_path / "c.json"
    path.write_text(json.dumps(config))
    walkable = pedpy.WalkableArea(scenario.walkable_area_wkt)
    simulation = jps.Simulation(
        model=_build_model(scenario.model_type, scenario.sim_params),
        geometry=walkable.polygon,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        _, _, radii, info = initialize_simulation_from_json(
            str(path), simulation, walkable, seed=seed, model_type=scenario.model_type
        )
    held = info.get("premovement_times") or {}
    # JuPedSim numbers agents across simulations in a process: count from the first
    first = min(agent.id for agent in simulation.agents())
    agents = {}
    for agent in simulation.agents():
        # a held agent's JuPedSim speed is 0 until it is released; its draw is kept aside
        v0 = held[agent.id]["desired_speed"] if agent.id in held else None
        agents[agent.id - first] = {
            "position": (agent.position[0], agent.position[1]),
            "radius": radii[agent.id],
            "v0": agent.model.desired_speed if v0 is None else v0,
            "familiarity": info["agent_wait_info"][agent.id]["familiarity"],
            "distribution": info["agent_distributions"][agent.id],
        }
    return agents, {i - first: h["premovement_time"] for i, h in held.items()}


def _before_v0(config: dict) -> dict:
    """*config* with the V0 keys reverted: hand front exit, no pre-movement, no closure."""
    old = json.loads(json.dumps(config))
    for exit_cfg in old["exits"].values():
        exit_cfg.pop("closed_after_s", None)
    for dist in old["distributions"].values():
        params = dist["parameters"]
        for key in [k for k in params if k.startswith("premovement_")]:
            del params[key]
        params["use_premovement"] = False
    return old


@pytest.mark.parametrize("deck", DECKS)
def test_the_v0_keys_move_no_position_radius_v0_or_familiarity(
    deck, full_configs, tmp_path
):
    """Pre-movement has its own stream; the closure touches no draw.

    On station_fahy the front exit (reverted here to the hand drawing's) moves
    no spawn either.
    """
    config = full_configs[deck]
    now, times = _init(deck, config, SEED, tmp_path)
    reverted = _before_v0(config)
    if deck == "station_fahy":
        reverted["exits"][FRONT_EXIT]["coordinates"] = HAND_FRONT_EXIT
    before, no_times = _init(deck, reverted, SEED, tmp_path)
    assert not no_times
    assert len(times) == len(now) == len(before) == 455
    assert now == before


@pytest.mark.parametrize("deck", DECKS)
def test_the_premovement_arms_move_no_draw(deck, mods, full_configs, tmp_path):
    fahy = mods["station_fahy"]
    base, _ = _init(deck, full_configs[deck], SEED, tmp_path)
    for mode in ("zero", "tracked"):
        built = mods[deck].build(fahy.V0Options(premovement=mode))[0]
        arm, _ = _init(deck, fahy.with_populations(built), SEED, tmp_path)
        assert arm == base, mode


@pytest.mark.parametrize("deck", DECKS)
def test_premovement_times_lie_in_the_band_and_differ_between_seeds(
    deck, full_configs, tmp_path
):
    config = full_configs[deck]
    rows = {k: d["parameters"]["fahy_row"] for k, d in config["distributions"].items()}
    drawn = {}
    for seed in (SEED, SEED + 1):
        agents, times = _init(deck, config, seed, tmp_path)
        assert len(times) == 455
        per_band: dict = collections.defaultdict(list)
        for agent_id, t in times.items():
            band = BANDS[rows[agents[agent_id]["distribution"]]]
            assert band[0] <= t < band[1], (seed, agent_id, t)
            per_band[band].append(t)
        assert all(len(set(v)) > 1 for v in per_band.values())
        drawn[seed] = {band: sorted(v) for band, v in per_band.items()}
    assert drawn[SEED] != drawn[SEED + 1]


@pytest.mark.parametrize("deck", DECKS)
def test_placed_times_do_not_depend_on_the_file_or_the_arm(
    deck, mods, fahy, default_builds, full_configs, tmp_path
):
    def per_distribution(config):
        agents, times = _init(deck, config, SEED, tmp_path)
        placed = {
            key
            for key, dist in config["distributions"].items()
            if dist["parameters"].get("population", "placed") == "placed"
        }
        out = collections.defaultdict(list)
        for agent_id, t in times.items():
            key = agents[agent_id]["distribution"]
            if key in placed:
                out[key].append(round(t, 9))
        return {k: sorted(v) for k, v in out.items()}

    reference = per_distribution(default_builds[deck])
    assert len(reference) == len(default_builds[deck]["distributions"])
    assert per_distribution(full_configs[deck]) == reference
    other_arm = mods[deck].build(fahy.V0Options(t_jam_s=None, w_queue=0.024))[0]
    assert per_distribution(fahy.with_populations(other_arm)) == reference


# ---- run checks: seed 4, config_full.json, both decks (slow) ----------------


def _vestibule_count(db: Path, deck: str) -> int:
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT pos_x, pos_y FROM trajectory_data WHERE frame = ?",
            (round(T_JAM * FPS),),
        ).fetchall()
    finally:
        con.close()
    return sum(VESTIBULE[deck].contains(Point(x, y)) for x, y in rows)


@pytest.fixture(scope="module", params=DECKS)
def run(request, tmp_path_factory):
    deck = request.param
    out = tmp_path_factory.mktemp(deck)
    files = {
        "sqlite": out / "run.sqlite",
        "routes": out / "routes.csv",
        "exits": out / "exits.csv",
        "pre": out / "pre.csv",
    }
    captured = []
    original = cli._run_or_exit

    def capture(scenario, run_kwargs):
        result = original(scenario, run_kwargs)
        captured.append(result)
        return result

    argv = [
        "pyfds-evac",
        "--scenario",
        str(ROOT / "assets" / deck / "config_full.json"),
        "--seed",
        str(SEED),
        "--output-sqlite",
        str(files["sqlite"]),
        "--output-route-history",
        str(files["routes"]),
        "--output-exit-history",
        str(files["exits"]),
        "--output-pre-evacuation-times",
        str(files["pre"]),
    ]
    mp = pytest.MonkeyPatch()
    mp.setattr(cli, "_run_or_exit", capture)
    mp.setattr(sys, "argv", argv)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main()
    finally:
        mp.undo()
    yield {"deck": deck, "files": files, "result": captured[0]}
    captured[0].cleanup()


def _csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _last_frames(db: Path) -> dict[int, int]:
    con = sqlite3.connect(db)
    try:
        return dict(
            con.execute("SELECT id, MAX(frame) FROM trajectory_data GROUP BY id")
        )
    finally:
        con.close()


@pytest.mark.slow
def test_run_exits_at_the_front_occur_before_the_jam_only(run, record_property):
    files = run["files"]
    last = _last_frames(files["sqlite"])
    left_by = {int(r["agent_id"]): r["exit_id"] for r in _csv(files["exits"])}
    front_exits = [last[i] / FPS for i, e in left_by.items() if e == FRONT_EXIT]
    assert front_exits, "nobody used the front door before the jam"
    assert max(front_exits) <= T_JAM + 1 / FPS

    routes = _csv(files["routes"])
    closure_rows = [
        r
        for r in routes
        if r["reason"] in ("exit_closed", "default_route")
        and r["old_exit"] == FRONT_EXIT
    ]
    assert closure_rows
    assert all(T_JAM <= float(r["time_s"]) <= T_JAM + 1 + 1 / FPS for r in closure_rows)
    # Every agent re-routed this way was still inside at the jam.
    rerouted = {int(r["agent_id"]) for r in closure_rows}
    assert all(last[i] >= T_JAM * FPS for i in rerouted)
    # Every agent still inside whose last route before the jam ended at the
    # front is among them. An agent that never changed route has no row, so this
    # is a lower bound on the agents bound for the front.
    target = {}
    for r in routes:
        if float(r["time_s"]) < T_JAM and r["new_exit"].startswith("jps-exits"):
            target[int(r["agent_id"])] = r["new_exit"]
    inside = {i for i, f in last.items() if f >= T_JAM * FPS}
    assert {i for i in inside if target.get(i) == FRONT_EXIT} <= rerouted
    record_property("vestibule_at_86s", _vestibule_count(files["sqlite"], run["deck"]))


@pytest.mark.slow
def test_run_nobody_passes_the_front_doorway_inward_after_the_jam(run):
    """No agent outside at t >= 86 s returns inside through the front doorway.

    By construction this holds when every agent that reaches the front exit
    leaves the simulation. An agent caught on the exit strip by the closure
    walks on outside to another exit (seed 4 on station_fahy has one).
    """
    line, x_low, x_high = DOORWAY[run["deck"]]
    con = sqlite3.connect(run["files"]["sqlite"])
    try:
        rows = con.execute(
            "SELECT id, pos_x, pos_y FROM trajectory_data WHERE frame >= ? "
            "ORDER BY id, frame",
            (round(T_JAM * FPS),),
        ).fetchall()
    finally:
        con.close()
    previous: dict[int, float] = {}
    for agent_id, x, y in rows:
        came_from_outside = previous.get(agent_id, line) < line
        assert not (came_from_outside and y >= line and x_low < x < x_high), agent_id
        previous[agent_id] = y


@pytest.mark.slow
def test_run_premovement_lies_in_the_band_through_agent_distributions(run):
    config = _file(run["deck"], "config_full.json")
    rows = {k: d["parameters"]["fahy_row"] for k, d in config["distributions"].items()}
    con = sqlite3.connect(run["files"]["sqlite"])
    try:
        mapping = dict(con.execute("SELECT id, distribution FROM agent_distributions"))
    finally:
        con.close()
    pre = _csv(run["files"]["pre"])
    assert len(pre) == 455
    per_band: dict = collections.defaultdict(set)
    for r in pre:
        t = float(r["premovement_time_s"])
        band = BANDS[rows[mapping[int(r["agent_id"])]]]
        assert band[0] <= t <= band[1], r
        assert r["distribution"] == mapping[int(r["agent_id"])]
        per_band[band].add(t)
    assert all(len(v) > 1 for v in per_band.values())


@pytest.mark.slow
def test_run_ends_within_the_horizon(run):
    result = run["result"]
    assert result.end_reason in ("all_evacuated", "time_limit")
    assert result.evacuation_time <= HORIZON + 1 / FPS
    assert result.agents_evacuated + result.agents_remaining == 455
