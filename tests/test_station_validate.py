"""The registered agreement statistic in ``assets/station_fahy/validate.py``.

The statistic itself (W, row pooling, the noise floor, T1, the time split and
the same-agent set) is checked on synthetic tables. Only the last block uses
Fahy's Table 2, to pin the reference values the study plan registers.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path

import pytest

ASSET = Path(__file__).resolve().parents[1] / "assets" / "station_fahy"
sys.path.insert(0, str(ASSET))

import fahy_table2 as F  # noqa: E402
import validate as V  # noqa: E402

TWO_ROWS = {"A": {"front": 6, "bar": 4}, "B": {"front": 2, "bar": 8}}


def _agent(aid, origin="A", door="front", t=10.0, start=(0.0, 0.0)):
    return V.AgentExit(aid, origin, door, t, start)


def test_w_two_rows_by_hand():
    # A: model 100 % front vs 60 % -> 0.4; B: 50 % vs 20 % -> 0.3; weights 10/10.
    model = {"A": {"front": 5}, "B": {"front": 3, "bar": 3}}
    assert V.w_statistic(model, TWO_ROWS) == pytest.approx(0.35)


def test_w_is_zero_for_the_target_itself():
    assert V.w_statistic(TWO_ROWS, TWO_ROWS) == pytest.approx(0.0)


def test_small_rows_are_pooled_with_their_model_agents():
    targets = {"A": {"front": 10}, "B": {"front": 3}, "C": {"bar": 3}}
    assert V.pooling(targets) == {"A": "A", "B": V.POOLED_ROW, "C": V.POOLED_ROW}
    # Pooled target is 50/50; model B all bar and C all front pools to 50/50 too.
    model = {"A": {"front": 4}, "B": {"bar": 2}, "C": {"front": 2}}
    assert V.w_statistic(model, targets) == pytest.approx(0.0)


def test_row_without_model_door_users_counts_as_distance_one():
    model = {"A": {"front": 6, "bar": 4}}
    assert V.w_statistic(model, TWO_ROWS) == pytest.approx(0.5)
    assert V.empty_rows(model, TWO_ROWS) == ["B"]


def test_rows_outside_the_targets_are_ignored():
    model = {"A": {"front": 6, "bar": 4}, "B": {"front": 2, "bar": 8}, "X": {"bar": 9}}
    assert V.w_statistic(model, TWO_ROWS) == pytest.approx(0.0)
    assert V.t1(model, rows=("A", "B")) == pytest.approx(8 / 20)


def test_t1_without_door_users_is_none():
    assert V.t1({}, rows=("A",)) is None


def test_noise_floor_is_zero_for_a_one_door_table():
    floor = V.noise_floor({"A": {"front": 12}, "B": {"bar": 15}}, draws=100)
    assert max(floor) == 0.0


def test_noise_floor_is_reproducible_and_positive():
    a = V.noise_floor(TWO_ROWS, draws=500, seed=3)
    b = V.noise_floor(TWO_ROWS, draws=500, seed=3)
    assert list(a) == list(b)
    assert statistics.median(a) > 0.0


def test_door_matrix_splits_at_t_jam_and_drops_stuck_and_unplaced():
    agents = [
        _agent(1, t=50.0),
        _agent(2, door="bar", t=86.0),
        _agent(3, door=None, t=250.0),
        _agent(4, origin=None, t=20.0),
    ]
    assert V.door_matrix(agents) == {"A": {"front": 1, "bar": 1}}
    assert V.door_matrix(agents, t_to=86.0) == {"A": {"front": 1}}
    assert V.door_matrix(agents, t_from=86.0) == {"A": {"bar": 1}}
    assert V.stuck_counts(agents) == {"A": 1}


def test_same_agents_keeps_those_that_exited_in_both():
    a = [_agent(1), _agent(2), _agent(3, door=None)]
    b = [_agent(1, door="bar"), _agent(2, door=None), _agent(3)]
    assert V.same_agents(a, b) == {1}


def test_censored_agents_leave_the_matrix_and_the_same_agent_set():
    censored = V.AgentExit(2, "A", "front", 250.0, (0.0, 0.0), censored=True)
    agents = [_agent(1, door="bar"), censored]
    assert V.door_matrix(agents) == {"A": {"bar": 1}}
    assert V.censored_count(agents) == 1
    assert V.same_agents(agents, [_agent(1), _agent(2)]) == {1}
    assert V.same_agents([_agent(1), _agent(2)], agents) == {1}


def test_paired_w_scores_both_arms_on_the_same_agents():
    a = [_agent(1), _agent(2, door="bar"), _agent(3, origin="B", door="bar")]
    b = [_agent(1), _agent(2, door=None), _agent(3, origin="B", door="front")]
    w_a, w_b, n = V.paired_w(a, b, TWO_ROWS)
    assert n == 2
    # Agent 2 is out: A row 100 % front (0.4); B row all bar (0.2) vs all front (0.8).
    assert w_a == pytest.approx((10 * 0.4 + 10 * 0.2) / 20)
    assert w_b == pytest.approx((10 * 0.4 + 10 * 0.8) / 20)


@pytest.mark.parametrize(
    "other",
    [
        [_agent(1, origin="B")],
        [_agent(1, start=(1.0, 0.0))],
        [_agent(2)],
        [_agent(1), _agent(2)],
    ],
)
def test_same_agents_rejects_runs_that_spawn_differently(other):
    with pytest.raises(ValueError):
        V.same_agents([_agent(1)], other)


def _square(x0, y0, size=1.0):
    return [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size]]


def _config(tmp_path, horizon=None):
    exits = {
        f"jps-exits_{i}": {"coordinates": _square(10.0 * i, 20.0)} for i in range(4)
    }
    config = {
        "exits": exits,
        "distributions": {
            "d0": {
                "coordinates": _square(0.0, 0.0, 5.0),
                "parameters": {"fahy_row": "A"},
            }
        },
    }
    if horizon is not None:
        params = {"max_simulation_time": horizon}
        config["config"] = {"simulation_settings": {"simulationParams": params}}
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(config))
    return cfg


def _sqlite(tmp_path, rows):
    db = tmp_path / "run.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE metadata(key TEXT, value TEXT)")
    con.execute("INSERT INTO metadata VALUES ('fps', '10')")
    con.execute(
        "CREATE TABLE trajectory_data(frame INT, id INT, pos_x REAL, pos_y REAL)"
    )
    con.executemany("INSERT INTO trajectory_data VALUES (?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    return db


def test_observed_agents_reads_area_door_and_exit_time(tmp_path):
    cfg = _config(tmp_path)
    rows = [
        (0, 1, 1.0, 1.0),
        (125, 1, 10.5, 19.5),  # next to jps-exits_1 (bar_door) at 12.5 s
        (0, 2, 2.0, 2.0),
        (300, 2, 2.0, 2.0),  # never left the area
        (0, 3, 50.0, 50.0),  # outside every area
    ]
    db = _sqlite(tmp_path, rows)

    agents = {a.agent_id: a for a in V.observed_agents(db, cfg, reach=2.0)}
    assert agents[1] == V.AgentExit(1, "A", "bar_door", 12.5, (1.0, 1.0))
    assert agents[2].door is None and agents[2].exit_time == 30.0
    assert agents[3].origin is None
    assert V.observed_matrix(db, cfg, reach=2.0) == ({"A": {"bar_door": 1}}, {"A": 1})


# Agent 1 leaves at 12.5 s; agent 2 is still present at the horizon, 1.5 m from
# jps-exits_0 (front).
CENSORED_RUN = [(0, 1, 1.0, 1.0), (125, 1, 10.5, 19.5), (0, 2, 2.0, 2.0)]


def test_agent_on_the_grid_at_the_horizon_is_censored(tmp_path):
    cfg = _config(tmp_path, horizon=250.0)
    db = _sqlite(tmp_path, [*CENSORED_RUN, (2500, 2, 0.5, 18.5)])
    horizon = V.config_horizon(cfg)
    assert horizon == 250.0
    agents = V.observed_agents(db, cfg, reach=2.0, horizon=horizon)
    by_id = {a.agent_id: a for a in agents}
    assert by_id[2].door == "front" and by_id[2].censored
    assert not by_id[1].censored
    assert V.door_matrix(agents) == {"A": {"bar_door": 1}}
    # observed_matrix keeps scoring every agent at a door (sweep_queue_weight.py).
    assert V.observed_matrix(db, cfg, reach=2.0) == (
        {"A": {"bar_door": 1, "front": 1}},
        {},
    )


def test_run_that_empties_before_the_horizon_censors_nobody(tmp_path):
    cfg = _config(tmp_path, horizon=250.0)
    db = _sqlite(tmp_path, [*CENSORED_RUN, (1026, 2, 0.5, 18.5)])
    agents = V.observed_agents(db, cfg, reach=2.0, horizon=250.0)
    assert V.censored_count(agents) == 0
    assert V.door_matrix(agents) == {"A": {"bar_door": 1, "front": 1}}


def test_run_longer_than_the_horizon_is_rejected(tmp_path):
    cfg = _config(tmp_path)
    db = _sqlite(tmp_path, [*CENSORED_RUN, (6000, 2, 0.5, 18.5)])
    with pytest.raises(ValueError, match="after the horizon"):
        V.observed_agents(db, cfg, reach=2.0, horizon=250.0)


# Registered reference values on Fahy's Table 2 (study plan, "Row statistic").


def test_fahy_pooling_scores_seven_rows_and_one_pool():
    groups = V.pooling(V.fahy_targets())
    kept = sorted(r for r, g in groups.items() if g == r)
    assert len(kept) == 7
    pooled = [r for r, g in groups.items() if g == V.POOLED_ROW]
    assert sum(sum(F.door_counts(r).values()) for r in pooled) == 34


def test_fahy_t1_over_placed_rows():
    assert V.t1(V.fahy_targets()) == pytest.approx(117 / 229)
    assert F.placed_door_shares()["front"] == pytest.approx(117 / 229)


def test_fahy_everyone_to_the_front_door():
    model = {r: {"front": 1} for r in F.PLACEABLE}
    assert V.w_statistic(model, V.fahy_targets()) == pytest.approx(112 / 229)


def test_fahy_same_door_shares_in_every_row():
    shares = F.placed_door_shares()
    model = {r: {d: 10_000 * s for d, s in shares.items()} for r in F.PLACEABLE}
    assert V.w_statistic(model, V.fahy_targets()) == pytest.approx(0.30, abs=0.005)


def test_fahy_noise_floor():
    floor = sorted(V.noise_floor(V.fahy_targets()))
    assert len(floor) == V.NOISE_DRAWS
    assert statistics.median(floor) == pytest.approx(0.079, abs=0.003)
    assert floor[int(0.95 * (len(floor) - 1))] == pytest.approx(0.109, abs=0.003)
