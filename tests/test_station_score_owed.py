"""The owed Station scorers in ``assets/station_fahy/score_owed.py`` (#950).

Every expectation is worked by hand on synthetic tables, runs and fields. No
Station output is read here.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

ASSET = Path(__file__).resolve().parents[1] / "assets" / "station_fahy"
sys.path.insert(0, str(ASSET))

import fahy_table2 as F  # noqa: E402
import score_owed as S  # noqa: E402
import validate as V  # noqa: E402

FPS = 10


def _agent(aid, origin="A", door="front", t=10.0, start=(0.0, 0.0), **kw):
    return V.AgentExit(aid, origin, door, t, start, **kw)


def _db(tmp_path, rows, remaining=None, name="run"):
    db = tmp_path / f"{name}.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE metadata(key TEXT, value TEXT)")
    con.execute(f"INSERT INTO metadata VALUES ('fps', '{FPS}')")
    con.execute(
        "CREATE TABLE trajectory_data(frame INT, id INT, pos_x REAL, pos_y REAL)"
    )
    con.executemany("INSERT INTO trajectory_data VALUES (?, ?, ?, ?)", rows)
    con.commit()
    con.close()
    if remaining is not None:
        manifest = {"outcome": {"agents_remaining": remaining}}
        (tmp_path / f"{name}.manifest.json").write_text(json.dumps(manifest))
    return db


# --- tabulation ---------------------------------------------------------------


def test_score_text_is_parsed_from_the_real_validate_output(capsys):
    row = F.PLACEABLE[0]
    runs = [
        [_agent(1, origin=row, t=50.0), _agent(2, origin=row, t=120.0)],
        [_agent(1, origin=row, t=60.0, door="stage"), _agent(2, origin=row, t=90.0)],
    ]
    V.report_statistic(runs, t_jam=86.0, draws=10)
    parsed = S.parse_score_text(capsys.readouterr().out)
    assert parsed["censored"] == 0 and parsed["placed"] == 4
    assert parsed["t_jam"] == 86.0
    # before 86 s: agents at 50 s (front) and 60 s (stage): T1 50 %.
    assert parsed["before"][0] == pytest.approx(50.0)
    # at or after: agents at 120 s and 90 s, both front: T1 100 %.
    assert parsed["after"][0] == pytest.approx(100.0)


def test_score_text_without_t_jam_has_no_split(capsys):
    row = F.PLACEABLE[0]
    V.report_statistic([[_agent(1, origin=row)]], t_jam=None, draws=10)
    parsed = S.parse_score_text(capsys.readouterr().out)
    assert "before" not in parsed and "after" not in parsed


def test_tabulate_refuses_a_file_that_is_not_validate_output(tmp_path):
    (tmp_path / "01_x.txt").write_text("nothing here")
    with pytest.raises(ValueError, match="not a validate.py output"):
        S.tabulate_scores(tmp_path)


def test_tabulate_row(tmp_path, capsys):
    row = F.PLACEABLE[0]
    V.report_statistic([[_agent(1, origin=row, t=50.0)]], t_jam=86.0, draws=10)
    (tmp_path / "16_tjam71__Cjam.txt").write_text(capsys.readouterr().out)
    table = S.tabulate_scores(tmp_path)
    assert "16_tjam71__Cjam | 0 of 1 (0.0%)" in table
    assert "T1 100.0 %" in table


# --- trajectories -----------------------------------------------------------


def test_outbound_crossing_time_is_interpolated(tmp_path):
    # Agent 1 goes from y -14.0 (frame 0) to -15.0 (frame 10): crosses -14.36
    # at 0.36 of the step, 0.36 s. Agent 2 walks inward and never counts.
    rows = [
        (0, 1, 3.0, -14.0),
        (10, 1, 3.0, -15.0),
        (0, 2, 3.0, -15.0),
        (10, 2, 3.0, -14.0),
    ]
    run = S.load_run(_db(tmp_path, rows))
    assert S.outbound_crossing_times(run) == pytest.approx([0.36])


def test_crossing_outside_the_door_width_is_ignored(tmp_path):
    rows = [(0, 1, 9.0, -14.0), (10, 1, 9.0, -15.0)]
    run = S.load_run(_db(tmp_path, rows))
    assert S.outbound_crossing_times(run) == []


def test_agent_counts_once_at_its_first_crossing(tmp_path):
    rows = [
        (0, 1, 3.0, -14.0),
        (10, 1, 3.0, -15.0),
        (20, 1, 3.0, -14.0),
        (30, 1, 3.0, -15.0),
    ]
    run = S.load_run(_db(tmp_path, rows))
    assert len(S.outbound_crossing_times(run)) == 1


def test_vestibule_count_uses_the_frame_nearest_t_jam(tmp_path):
    rows = [
        (860, 1, 3.0, -15.5),  # inside the vestibule at 86 s
        (860, 2, 3.0, -13.0),  # inside the building, past the interior door
        (860, 3, 3.0, -18.0),  # outside
        (700, 4, 3.0, -15.5),  # gone by 86 s
    ]
    run = S.load_run(_db(tmp_path, rows))
    assert S.vestibule_count(run, 86.0) == 1


def test_v5_is_undefined_when_no_window_fits():
    # First arrival at 30 s, t_jam 86 s: 56 s of span, no 60 s window.
    result = S.v5_max_moving_mean([30.0 + i for i in range(56)], t_jam=86.0)
    assert result["rate"] is None
    assert result["span"] == pytest.approx(56.0)
    assert result["count"] == 56


def test_v5_is_not_shortened_or_run_past_t_jam():
    # One person per second after t_jam does not count and does not make a window.
    result = S.v5_max_moving_mean([30.0 + i for i in range(100)], t_jam=86.0)
    assert result["rate"] is None and result["count"] == 56


def test_v5_highest_moving_mean_by_hand():
    # First arrival at 10 s; t_jam 100 s. 2 persons/s during [10, 40), then 0.5/s.
    times = [10 + 0.5 * i for i in range(60)] + [40 + 2.0 * i for i in range(30)]
    result = S.v5_max_moving_mean(times, t_jam=100.0, step_s=0.5)
    # Best window starts at 10 s: 60 crossings in [10, 40) plus 15 in [40, 70).
    assert result["rate"] == pytest.approx(75 / 60)
    assert S.band_verdict(result["rate"], S.V5_BAND) == "pass"


def test_v5_second_reading_lets_the_window_start_before_the_first_arrival():
    # One person per second from 30 s to 85 s: 56 crossings. The registered
    # window cannot fit; the window of the last 60 s before t_jam holds them all.
    result = S.v5_max_moving_mean([30.0 + i for i in range(56)], t_jam=86.0)
    assert result["rate"] is None
    assert result["rate_window_to_t_jam"] == pytest.approx(56 / 60)


def test_v5_second_reading_is_none_when_t_jam_is_inside_the_window():
    result = S.v5_max_moving_mean([10.0, 20.0], t_jam=50.0)
    assert result["rate_window_to_t_jam"] is None


def test_v5_without_crossing_is_empty():
    assert S.v5_max_moving_mean([], t_jam=86.0)["first"] is None


def test_stopped_agents_are_those_present_at_the_last_frame(tmp_path):
    rows = [(0, 1, 0, 0), (50, 1, 0, 0), (0, 2, 0, 0), (30, 2, 1, 1)]
    run = S.load_run(_db(tmp_path, rows, remaining=1))
    assert S.stopped_ids(run) == {1}


def test_stopped_count_must_match_the_manifest(tmp_path):
    rows = [(0, 1, 0, 0), (50, 1, 0, 0), (0, 2, 0, 0), (50, 2, 1, 1)]
    run = S.load_run(_db(tmp_path, rows, remaining=1))
    with pytest.raises(ValueError, match="manifest"):
        S.stopped_ids(run)


def test_run_that_emptied_has_no_stopped_agents(tmp_path):
    rows = [(0, 1, 0, 0), (50, 1, 0, 0)]
    assert S.stopped_ids(S.load_run(_db(tmp_path, rows, remaining=0))) == set()
    with pytest.raises(ValueError, match="no manifest"):
        S.stopped_ids(S.load_run(_db(tmp_path, rows, name="bare")))


def test_nist_construct_by_hand_and_stopped_near_the_door_is_not_an_exit(tmp_path):
    # Agent 1 exits by the front; agent 2 by the stage door; agent 3 is stopped
    # 1 m from the front door (it would pass validate's 2 m reach) inside the
    # entry; agent 4 is stopped in the dance floor box.
    rows = [
        (0, 1, 3.0, -14.0),
        (30, 1, 3.0, -18.0),
        (0, 2, 12.0, -8.0),
        (30, 2, 17.9, -11.9),
        (0, 3, 3.0, -15.0),
        (60, 3, 3.0, -16.0),
        (0, 4, 12.0, -8.0),
        (60, 4, 12.0, -8.0),
    ]
    run = S.load_run(_db(tmp_path, rows, remaining=2))
    agents = [
        _agent(1, door="front", t=3.0),
        _agent(2, door="stage", t=3.0),
        _agent(3, door="front", t=6.0),  # within reach of the front door
        _agent(4, door=None, t=6.0),
    ]
    result = S.nist_construct(agents, run)
    assert result["front_exits"] == 1 and result["door_users"] == 2
    assert result["stopped"] == 2 and result["stopped_in_entry_sunroom"] == 1
    assert result["construct"] == pytest.approx((1 + 1) / (2 + 2))


def test_first_target_share_and_empty_input():
    assert (
        S.first_target_front_share({1: "front", 2: "stage", 3: "front", 4: "kitchen"})
        == 0.5
    )
    with pytest.raises(ValueError, match="empty"):
        S.first_target_front_share({})


# --- agent_scalars ----------------------------------------------------------


def test_heat_fed_recorded_counts_only_non_null_rows(tmp_path):
    db = _db(tmp_path, [(0, 1, 0, 0)])
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE agent_scalars(frame INT, id INT, fed REAL, heat_fed REAL)"
    )
    con.execute("INSERT INTO agent_scalars VALUES (0, 1, 0.5, NULL)")
    con.commit()
    assert S.heat_fed_recorded(db) == 0
    con.execute("INSERT INTO agent_scalars VALUES (1, 1, 0.6, 0.1)")
    con.commit()
    con.close()
    assert S.heat_fed_recorded(db) == 1


def test_heat_incapacitated_counts_agents_at_or_above_one(tmp_path):
    db = _db(tmp_path, [(0, 1, 0, 0)])
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE agent_scalars(frame INT, id INT, fed REAL, heat_fed REAL)"
    )
    con.executemany(
        "INSERT INTO agent_scalars VALUES (?, ?, 0.0, ?)",
        [(0, 1, 0.4), (1, 1, 1.0), (2, 1, 1.5), (0, 2, 0.99), (0, 3, None)],
    )
    con.commit()
    con.close()
    assert S.heat_incapacitated(db) == (1, 1.5)


def test_heat_incapacitated_without_any_heat_fed(tmp_path):
    assert S.heat_incapacitated(_db(tmp_path, [(0, 1, 0, 0)])) == (0, None)


def test_heat_fed_recorded_without_a_scalars_table(tmp_path):
    assert S.heat_fed_recorded(_db(tmp_path, [(0, 1, 0, 0)])) == 0


def test_raised_floor_groups_by_start_position():
    agents = [
        _agent(1, start=(15.0, -8.0), incapacitated=True),  # platform
        _agent(2, start=(19.0, -7.0), incapacitated=False),  # alcove
        _agent(3, start=(10.0, -3.0), incapacitated=True),  # rear strip
        _agent(4, start=(0.0, -10.0), incapacitated=True),  # elsewhere
        _agent(5, start=(15.0, -8.0), incapacitated=True, population="victim"),
    ]
    groups = S.raised_floor_fed(agents)
    assert groups["platform"] == {"agents": 1, "incapacitated": 1}
    assert groups["alcove"] == {"agents": 1, "incapacitated": 0}
    assert groups["any"] == {"agents": 3, "incapacitated": 2}
    assert groups["elsewhere"] == {"agents": 1, "incapacitated": 1}


def test_raised_floor_fed_is_none_without_recorded_fed():
    groups = S.raised_floor_fed([_agent(1, start=(15.0, -8.0))])
    assert groups["platform"]["incapacitated"] is None


# --- resampling -------------------------------------------------------------


def _matrix_run(front_share_by_row):
    """Door matrix with ten users per Fahy row, ``share`` of them at the front."""
    return {
        row: {"front": round(10 * s), "bar_door": 10 - round(10 * s)}
        for row, s in front_share_by_row.items()
    }


def _agents_from_matrix(matrix, offset=0):
    agents, aid = [], offset
    for row, doors in matrix.items():
        for door, n in doors.items():
            for _ in range(n):
                agents.append(
                    _agent(aid, origin=row, door=door, start=(float(aid), 0.0))
                )
                aid += 1
    return agents


def test_w_against_the_table_equals_the_frozen_statistic():
    targets = V.fahy_targets()
    matrix = _matrix_run(dict.fromkeys(F.PLACEABLE, 0.3))
    groups, vectors = S._target_layout(targets)
    table = {g: v[None, :] for g, v in vectors.items()}
    got = S._w_against(V.pool(matrix, groups), vectors, table)[0]
    assert got == pytest.approx(V.w_statistic(matrix, targets))


def test_w_draws_resampled_centre_is_near_the_table_value():
    targets = V.fahy_targets()
    matrix = _matrix_run(dict.fromkeys(F.PLACEABLE, 0.5))
    draws = S.w_draws(matrix, targets, 4000, np.random.default_rng(1))
    # Resampling noise only adds to the distance: the mean is at or above W.
    assert draws.mean() >= V.w_statistic(matrix, targets) - 0.02
    assert draws.shape == (4000,)


def test_empty_model_row_counts_as_distance_one_in_draws():
    targets = V.fahy_targets()
    draws = S.w_draws({}, targets, 5, np.random.default_rng(0))
    assert draws == pytest.approx(np.ones(5))


def test_paired_draws_observed_matches_validate_paired_w():
    targets = V.fahy_targets()
    run_a = _agents_from_matrix(_matrix_run(dict.fromkeys(F.PLACEABLE, 0.2)))
    run_b = _agents_from_matrix(_matrix_run(dict.fromkeys(F.PLACEABLE, 0.8)))
    # The two runs must spawn the same agents: same ids, areas and starts.
    run_b = [
        V.AgentExit(a.agent_id, a.origin, b.door, 1.0, a.start)
        for a, b in zip(run_a, run_b, strict=False)
    ] + run_a[len(run_b) :]
    paired = S.paired_draws([run_a], [run_b], targets, draws=50, seed=0)
    w_a, w_b, _ = V.paired_w(run_a, run_b, targets)
    assert paired["observed"][0] == pytest.approx(w_a - w_b)
    assert paired["resampled"].shape == (1, 50)


def test_survival_by_hand():
    observed = np.array([0.05, 0.05, -0.05])
    resampled = np.array(
        [
            [0.04, 0.02, 0.05, 0.06],  # sign kept 4 of 4; also >= 0.03 in 3 of 4
            [0.05, 0.05, 0.05, 0.05],  # 4 of 4 and 4 of 4
            [-0.05, 0.05, -0.03, -0.02],  # sign kept in draws 0, 2, 3; size in 0, 2
        ]
    )
    out = S.survival({"observed": observed, "resampled": resampled}, threshold=0.03)
    assert out["sign_per_seed"] == pytest.approx((0.75, 1.0, 1.0))
    assert out["size_per_seed"] == pytest.approx((0.5, 0.75, 1.0))
    assert out["draws"] == 4
    # R lower in 15 of 20 seeds never holds with three seeds: needs min(15, 3) = 3.
    assert out["v3_holds"] == pytest.approx(0.0)


def test_a_uniform_shift_of_003_keeps_its_sign_in_over_99_percent():
    # Plan line 146: a difference of 0.03 spread uniformly over the rows
    # survives resampling of Fahy's table in more than 99 % of draws. Model B
    # is Fahy's table itself, model A mixes every row toward the uniform
    # distribution until W(A) = 0.03.
    targets = V.fahy_targets()
    exact = {r: {d: c * 1000 for d, c in cs.items()} for r, cs in targets.items()}

    def mixed(lam):
        out = {}
        for row, counts in exact.items():
            n = sum(counts.values())
            out[row] = {d: (1 - lam) * counts.get(d, 0) + lam * n / 4 for d in F.DOORS}
        return out

    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if V.w_statistic(mixed(mid), targets) < 0.03 else (lo, mid)
    shifted = mixed(lo)
    assert V.w_statistic(shifted, targets) == pytest.approx(0.03, abs=1e-6)
    groups, vectors = S._target_layout(targets)
    rng = np.random.default_rng(0)
    resampled = {
        g: rng.multinomial(int(v.sum()), v / v.sum(), size=4000).astype(float)
        for g, v in vectors.items()
    }
    delta = S._w_against(V.pool(shifted, groups), vectors, resampled) - S._w_against(
        V.pool(exact, groups), vectors, resampled
    )
    out = S.survival({"observed": np.array([0.03]), "resampled": delta[None, :]})
    assert out["sign_per_seed"][0] > 0.99
    # The stricter reading (sign and size >= 0.03) fails here: 0.03 is the
    # observed difference, and resampling moves it either way.
    assert out["size_per_seed"][0] < 0.5


def test_survival_of_a_passing_v3():
    seeds = 20
    observed = np.full(seeds, -0.05)
    resampled = np.full((seeds, 3), -0.05)
    resampled[:, 2] = 0.01  # one draw where R is no longer lower
    out = S.survival({"observed": observed, "resampled": resampled})
    assert out["v3_holds"] == pytest.approx(2 / 3)
    assert out["sign_mean"] == pytest.approx(2 / 3)
    assert out["size_mean"] == pytest.approx(2 / 3)


# --- V6 ---------------------------------------------------------------------


def test_fds_hrr_file_is_read_by_its_column_names():
    fixture = (
        ASSET.parents[1] / "tests" / "data" / "cell_centred" / "cell_centred_hrr.csv"
    )
    t, q = S.read_fds_hrr(fixture)
    assert t[0] == 0.0 and len(t) == len(q) >= 2


def test_prescribed_hrr_skips_comments_and_header(tmp_path):
    path = tmp_path / "hrr.csv"
    path.write_text("# note\nt_s,hrr_kw\n1.0,10\n3.0,30\n")
    t, q = S.read_prescribed_hrr(path)
    assert list(t) == [1.0, 3.0] and list(q) == [10.0, 30.0]


def test_hrr_report_energy_ratio_and_peaks():
    prescribed = (np.array([0.0, 10.0, 20.0]), np.array([0.0, 100.0, 0.0]))
    real = (np.array([0.0, 10.0, 20.0]), np.array([0.0, 50.0, 0.0]))
    out = S.hrr_report(real, prescribed)
    assert out["energy_ratio"] == pytest.approx(0.5, rel=1e-3)
    assert out["peak_prescribed"] == (100.0, 10.0)
    assert out["peak_realised"][0] == pytest.approx(50.0, rel=1e-3)


def test_first_time_at_or_above_is_inclusive_and_none_when_never():
    t = [0, 1, 2, 3]
    assert S.first_time_at_or_above(t, [0.0, 0.5, 0.7, 1.0], 0.5) == 1.0
    assert S.first_time_at_or_above(t, [0.0, 0.1, 0.2, 0.3], 0.5) is None


def test_band_verdict_edges():
    assert S.band_verdict(65.0, S.T5_BAND) == "pass"
    assert S.band_verdict(100.0, S.T5_BAND) == "pass"
    assert S.band_verdict(100.5, S.T5_BAND) == "fail"
    assert S.band_verdict(None, S.T6_BAND) == "undefined"
    # Not crossed by the end of the data, which is past the band.
    assert S.band_verdict(None, S.T6_BAND, last_time=250.0) == "not reached by 250 s"
    assert S.band_verdict(None, S.T6_BAND, last_time=100.0) == "undefined"


def test_unreached_regions_group_by_connectivity():
    mask = np.ones((4, 6), dtype=bool)
    o2 = np.full(mask.shape, 0.05)
    o2[0, 0:2] = 0.2  # a pair of nodes still at ambient
    o2[3, 5] = 0.2  # a single node
    o2[2, 2] = 0.2  # unmasked below: masked out
    mask[2, 2] = False
    xc, yc = np.arange(6.0), np.arange(4.0)
    groups = S.unreached_regions(o2, mask, xc, yc)
    assert [g["nodes"] for g in groups] == [2, 1]
    assert groups[0]["box"] == (0.0, 1.0, 0.0, 0.0)


def test_interior_mask_excludes_a_sealed_room_and_flags_a_leak():
    free = np.ones((6, 8), dtype=bool)
    free[:, 3] = False  # a wall across the whole domain splits it in two
    seed = np.zeros_like(free)
    seed[2, 1] = True
    mask, edge = S.interior_mask(free, seed)
    assert mask[:, :3].all() and not mask[:, 4:].any()
    assert edge  # the left part reaches the domain edge: a leak is reported

    sealed = np.zeros((7, 7), dtype=bool)
    sealed[1:6, 1:6] = True
    seed = np.zeros_like(sealed)
    seed[3, 3] = True
    mask, edge = S.interior_mask(sealed, seed)
    assert mask.sum() == 25 and not edge


def test_seed_cells_inside_a_solid_are_not_in_the_mask():
    free = np.ones((3, 3), dtype=bool)
    free[1, 1] = False
    seed = np.zeros_like(free)
    seed[1, 1] = True
    mask, _ = S.interior_mask(free, seed)
    assert not mask.any()


def test_exceedance_fraction_and_nan_guard():
    cells = np.array([[True, True], [False, True]])
    frames = [
        np.array([[130.0, 100.0], [0.0, 121.0]]),
        np.array([[130.0, 130.0], [0.0, 130.0]]),
    ]
    got = S.exceedance_fractions(frames, cells, lambda v: v > 120.0)
    assert got == pytest.approx([2 / 3, 1.0])
    frames[0][0, 0] = np.nan
    with pytest.raises(ValueError, match="no value"):
        S.exceedance_fractions(frames, cells, lambda v: v > 120.0)


def test_v6_times_on_a_synthetic_room():
    # 0.5 m lattice over x 10 to 15, y -12 to -4: a closed room, dance floor inside.
    xc = np.arange(10.25, 15.0, 0.5)
    yc = np.arange(-11.75, -4.0, 0.5)
    free = np.zeros((len(yc), len(xc)), dtype=bool)
    free[1:-1, 1:-1] = True
    times = np.array([0.0, 10.0, 20.0, 30.0])
    hot = np.full(free.shape, 20.0)
    temperature = [hot, hot, np.where(free, 150.0, 20.0), np.where(free, 150.0, 20.0)]
    ambient = np.full(free.shape, 0.2095)
    low = np.full(free.shape, 0.10)
    o2 = [ambient, ambient, ambient, low]
    result = S.v6_times(times, temperature, o2, xc, yc, free)
    assert result["T5"]["50%"] == 20.0
    assert result["T6"] == 30.0
    assert result["mask_cells"] == int(free.sum())
    assert not result["mask_touches_domain_edge"]


def test_node_lattice_and_free_mask_of_a_real_fds_mesh():
    pytest.importorskip("fdsreader")
    from pyfds_evac.core.fdsreader_adapter import open_fds_simulation

    case = ASSET.parents[1] / "tests" / "data" / "cell_centred"
    sim = open_fds_simulation(str(case))
    xc, yc, free = S._node_lattice_and_free(sim, 1.5)
    # One 2 m x 2 m mesh of 0.5 m cells without obstructions: 5 x 5 nodes.
    assert list(xc) == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])
    assert list(yc) == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])
    assert free.shape == (5, 5) and free.all()


class _Mesh:
    """Two 1 m meshes side by side; asks for the node mask and blocks one node."""

    def __init__(self, x0, blocked):
        self.coordinates = {
            "x": [x0, x0 + 0.5, x0 + 1.0],
            "y": [0.0, 0.5, 1.0],
            "z": [0.0, 1.0, 2.0],
        }
        self._blocked = blocked

    def get_obstruction_mask(self, times, cell_centered=False):
        assert not cell_centered, "a zero-thickness wall blocks nodes, not cells"
        mask = np.ones((1, 3, 3, 3), dtype=bool)
        for i, j in self._blocked:
            mask[0, i, j, :] = False
        return mask


def test_node_free_mask_uses_node_mask_and_the_and_of_shared_nodes():
    class Sim:
        # Node x = 1.0 is shared; mesh B blocks it at y = 0.5 (a thin wall edge).
        meshes = [_Mesh(0.0, []), _Mesh(1.0, [(0, 1)])]

    xc, yc, free = S._node_lattice_and_free(Sim(), 1.0)
    assert list(xc) == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])
    assert not free[1, 2]  # blocked through mesh B although mesh A holds it free
    assert free.sum() == free.size - 1


def test_missing_fire_quantity_names_the_quantity(tmp_path):
    pytest.importorskip("fdsreader")
    case = ASSET.parents[1] / "tests" / "data" / "cell_centred"
    with pytest.raises(IndexError, match="TEMPERATURE"):
        S.read_fire_fields(case, 1.75)
