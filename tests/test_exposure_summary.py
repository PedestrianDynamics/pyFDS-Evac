"""The per-agent exposure summary on hand-built histories (#210).

Values are binary-exact (t/8, t/4, t/16), so every expectation is read off
the rows by hand.
"""

import pytest

from pyfds_evac.core.exposure_summary import (
    ExposureSummaryConfig,
    exposure_totals,
    summarise_exposure,
)


def _fed(agent, times, fed, *, fic=None, heat=0.0, incapacitated_from=None):
    return [
        {
            "time_s": float(t),
            "agent_id": agent,
            "fed_cumulative": fed(t),
            "heat_fed_cumulative": heat,
            "fic": fic(t) if fic else 0.0,
            "incapacitated": incapacitated_from is not None and t >= incapacitated_from,
        }
        for t in times
    ]


def _smoke(agent, times, k):
    return [
        {"time_s": float(t), "agent_id": agent, "extinction_per_m": k(t)} for t in times
    ]


def _summary(fed_rows, smoke_rows, exits, **kw):
    kw.setdefault("gas_evaluated", True)
    kw.setdefault("heat_evaluated", False)
    rows = summarise_exposure(fed_rows, smoke_rows, exits, **kw)
    return {row["agent_id"]: row for row in rows}


def test_agent_that_leaves_after_crossing_fails_with_negative_margin():
    fed = _fed(1, range(8), lambda t: t / 8, fic=lambda t: t / 16)
    smoke = _smoke(1, range(8), lambda t: t / 4)
    row = _summary(fed, smoke, {1: 7.0})[1]
    assert row["censored"] is False
    assert row["fed_max"] == 0.875
    assert row["t_fed_ge_0.3_s"] == 3.0
    assert row["t_fed_ge_1_s"] is None
    assert row["t_k_ge_0.3_s"] == 2.0
    assert row["t_fic_ge_0.3_s"] == 5.0
    assert row["diff_fed_ge_0.3_s"] == -4.0
    assert row["diff_k_ge_0.3_s"] == -5.0
    assert row["outcome_fed_ge_0.3"] == "fail"
    assert row["outcome_fed_ge_1"] == "pass"
    assert row["last_sample_s"] == 7.0


def test_censored_agent_without_crossing_is_open_not_passed():
    fed = _fed(2, range(11), lambda t: t / 80)
    row = _summary(fed, None, {})[2]
    assert row["censored"] is True
    assert row["exit_time_s"] is None
    assert row["fed_max"] == 0.125
    assert row["outcome_fed_ge_0.3"] == "open"
    assert row["diff_fed_ge_0.3_s"] is None


def test_censored_agent_that_crossed_fails_without_a_margin():
    fed = _fed(2, range(11), lambda t: t / 8)
    row = _summary(fed, None, {})[2]
    assert row["t_fed_ge_0.3_s"] == 3.0
    assert row["outcome_fed_ge_0.3"] == "fail"
    assert row["diff_fed_ge_0.3_s"] is None


def test_agent_that_leaves_below_every_threshold_passes():
    fed = _fed(3, range(5), lambda t: t / 80)
    row = _summary(fed, None, {3: 4.0})[3]
    assert row["outcome_fed_ge_0.3"] == "pass"
    assert row["outcome_fed_ge_1"] == "pass"


def test_crossing_exactly_at_the_threshold_counts():
    fed = _fed(1, range(5), lambda t: t / 8)
    cfg = ExposureSummaryConfig(fed_thresholds=(0.5, 1.0))
    row = _summary(fed, None, {1: 4.0}, config=cfg)[1]
    assert row["t_fed_ge_0.5_s"] == 4.0


def test_a_sample_at_the_exit_time_is_inside():
    fed = _fed(1, range(8), lambda t: t / 8)
    row = _summary(fed, None, {1: 3.0})[1]
    assert row["t_fed_ge_0.3_s"] == 3.0
    assert row["diff_fed_ge_0.3_s"] == 0.0
    assert row["outcome_fed_ge_0.3"] == "fail"


def test_samples_after_the_exit_do_not_count():
    fed = _fed(1, range(8), lambda t: t / 8)
    row = _summary(fed, None, {1: 2.0})[1]
    assert row["t_fed_ge_0.3_s"] is None
    assert row["fed_max"] == 0.25
    assert row["outcome_fed_ge_0.3"] == "pass"


def test_last_sample_ignores_samples_after_the_exit():
    fed = _fed(1, range(8), lambda t: 0.0)
    smoke = _smoke(1, range(9), lambda t: 0.0)
    row = _summary(fed, smoke, {1: 5.0})[1]
    assert row["last_sample_s"] == 5.0


def test_no_heat_model_reads_not_evaluated_never_zero():
    fed = _fed(1, range(4), lambda t: 0.0)
    row = _summary(fed, None, {1: 3.0})[1]
    assert row["heat_evaluated"] is False
    assert row["heat_fed_max"] is None
    assert row["t_heat_fed_ge_0.3_s"] is None
    assert row["outcome_heat_fed_ge_0.3"] == "not_evaluated"


def test_heat_model_is_evaluated_when_it_ran():
    fed = _fed(1, range(4), lambda t: 0.0, heat=0.5)
    row = _summary(fed, None, {1: 3.0}, heat_evaluated=True)[1]
    assert row["heat_evaluated"] is True
    assert row["heat_fed_max"] == 0.5
    assert row["outcome_heat_fed_ge_0.3"] == "fail"
    assert row["outcome_heat_fed_ge_1"] == "pass"


def test_heat_only_run_does_not_report_default_gas_values():
    fed = _fed(1, range(4), lambda t: 0.0, heat=0.5)
    row = _summary(fed, None, {1: 3.0}, gas_evaluated=False, heat_evaluated=True)[1]
    assert row["fed_max"] is None
    assert row["outcome_fed_ge_0.3"] == "not_evaluated"
    assert row["outcome_fic_ge_0.3"] == "not_evaluated"
    assert row["outcome_heat_fed_ge_0.3"] == "fail"


def test_no_smoke_rows_reads_not_evaluated():
    fed = _fed(1, range(4), lambda t: 0.0)
    row = _summary(fed, None, {1: 3.0})[1]
    assert row["k_max"] is None
    assert row["outcome_k_ge_0.3"] == "not_evaluated"


def test_no_fed_rows_reads_not_evaluated():
    smoke = _smoke(1, range(4), lambda t: 0.0)
    row = _summary(None, smoke, {1: 3.0})[1]
    assert row["outcome_fed_ge_0.3"] == "not_evaluated"
    assert row["outcome_k_ge_0.3"] == "pass"


def test_incapacitated_agent_is_open_for_a_criterion_it_never_crossed():
    fed = _fed(4, range(7), lambda t: t / 4, incapacitated_from=6)
    smoke = _smoke(4, range(7), lambda t: t / 100)
    row = _summary(fed, smoke, {})[4]
    assert row["incapacitated_s"] == 6.0
    assert row["outcome_k_ge_0.3"] == "open"
    assert row["outcome_fed_ge_1"] == "fail"


def test_agent_without_samples_is_open_even_if_it_left():
    fed = _fed(1, range(3), lambda t: 0.0)
    rows = _summary(fed, None, {1: 2.0, 9: 1.0})
    assert rows[9]["outcome_fed_ge_0.3"] == "open"


def test_outside_domain_samples_are_counted():
    fed = _fed(1, range(4), lambda t: 0.0)
    for row in fed[:2]:
        row["in_fds_domain"] = False
    for row in fed[2:]:
        row["in_fds_domain"] = True
    assert _summary(fed, None, {1: 3.0})[1]["outside_fds_samples"] == 2


def test_visibility_limit_is_c_over_the_distance():
    cfg = ExposureSummaryConfig(visibility_c=8.0, visibility_limit_m=10.0)
    smoke = _smoke(1, range(8), lambda t: t / 8)
    row = _summary(None, smoke, {1: 7.0}, config=cfg)[1]
    assert cfg.k_limit_per_m == 0.8
    assert row["t_k_ge_0.8_s"] == 7.0


def test_default_visibility_limit_is_k_0_3():
    assert ExposureSummaryConfig().k_limit_per_m == 0.3


def test_totals_count_outcomes_and_first_crossing():
    fed = _fed(1, range(8), lambda t: t / 8) + _fed(2, range(8), lambda t: 0.0)
    rows = summarise_exposure(
        fed, None, {1: 7.0}, gas_evaluated=True, heat_evaluated=False
    )
    total = exposure_totals(rows)["fed_ge_0.3"]
    assert (total["fail"], total["open"], total["pass"]) == (1, 1, 0)
    assert total["crossed"] == 1 and total["first_s"] == 3.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fed_thresholds": ()},
        {"fed_thresholds": (0.3, 0.3)},
        {"fed_thresholds": (0.0,)},
        {"visibility_c": float("nan")},
        {"visibility_limit_m": -1.0},
    ],
)
def test_config_rejects_unusable_values(kwargs):
    with pytest.raises(ValueError, match="ExposureSummaryConfig"):
        ExposureSummaryConfig(**kwargs)
