"""The whole-crowd deadlock rule (#760): every counted agent still over the window."""

import pytest

from pyfds_evac.core.deadlock import (
    DEADLOCK_DISPLACEMENT_M,
    DEADLOCK_WINDOW_S,
    Deadlock,
    DeadlockDetector,
)


def _feed(detector, until_s, positions_at, held_at=lambda t: False, start_s=0.0):
    """Observe once per second from *start_s* to *until_s*; the first deadlock or None."""
    t = start_s
    while t <= until_s + 1e-9:
        found = detector.observe(t, positions_at(t), held=held_at(t))
        if found is not None:
            return t, found
        t += 1.0
    return None


def test_a_still_crowd_is_deadlocked_after_the_window():
    hit = _feed(DeadlockDetector(), 200.0, lambda t: {1: (1.0, 2.0), 2: (3.0, 4.0)})
    assert hit is not None
    t, found = hit
    assert t == pytest.approx(DEADLOCK_WINDOW_S)
    assert found.since_s == pytest.approx(0.0)
    assert found.positions == ((1.0, 2.0), (3.0, 4.0))
    assert found.agents == 2


def test_one_moving_agent_keeps_the_run_going():
    def positions(t):
        return {1: (1.0, 2.0), 2: (3.0 + 2 * DEADLOCK_DISPLACEMENT_M * t / 100.0, 4.0)}

    assert _feed(DeadlockDetector(), 100.0, positions) is None


def test_a_displacement_just_under_the_threshold_is_still():
    def positions(t):
        return {1: (1.0 + 0.029 * t / 100.0, 2.0)}

    assert _feed(DeadlockDetector(), 100.0, positions) is not None


def test_a_diagonal_displacement_is_measured_as_a_distance():
    def positions(t):
        return {1: (1.0 + 0.022 * t / 100.0, 2.0 + 0.022 * t / 100.0)}

    assert _feed(DeadlockDetector(), 100.0, positions) is None  # 0.031 m net


def test_a_displacement_of_exactly_the_threshold_is_not_still():
    def positions(t):
        return {1: (DEADLOCK_DISPLACEMENT_M if t >= 100.0 else 0.0, 0.0)}

    assert _feed(DeadlockDetector(), 100.0, positions) is None


def test_net_displacement_not_path_length():
    def positions(t):
        return {1: (1.0 + (0.5 if int(t) % 2 else 0.0), 2.0)}

    hit = _feed(DeadlockDetector(), 100.0, positions)
    assert hit is not None  # back on its start point at t = 100


def test_a_held_agent_restarts_the_window():
    hit = _feed(
        DeadlockDetector(),
        300.0,
        lambda t: {1: (1.0, 2.0)},
        held_at=lambda t: t == 50.0,
    )
    assert hit is not None
    t, found = hit
    assert t == pytest.approx(51.0 + DEADLOCK_WINDOW_S)
    assert found.since_s == pytest.approx(51.0)


def test_an_agent_that_appeared_inside_the_window_is_not_yet_countable():
    def positions(t):
        return {1: (1.0, 2.0)} | ({2: (5.0, 5.0)} if t >= 50.0 else {})

    hit = _feed(DeadlockDetector(), 300.0, positions)
    assert hit is not None
    assert hit[0] == pytest.approx(50.0 + DEADLOCK_WINDOW_S)


def test_an_agent_that_left_does_not_block_the_rule():
    def positions(t):
        return {1: (1.0, 2.0)} | ({2: (5.0 + t, 5.0)} if t < 50.0 else {})

    hit = _feed(DeadlockDetector(), 300.0, positions)
    assert hit is not None
    assert hit[1].positions == ((1.0, 2.0),)


def test_no_counted_agent_is_never_a_deadlock():
    assert _feed(DeadlockDetector(), 300.0, lambda t: {}) is None


def test_due_follows_the_sample_interval():
    detector = DeadlockDetector()
    assert detector.due(0.0)
    detector.observe(0.0, {1: (0.0, 0.0)}, held=False)
    assert not detector.due(0.5)
    assert detector.due(1.0)


def test_samples_off_the_one_second_grid_keep_the_latest_start_sample():
    detector = DeadlockDetector()
    t = 0.0
    while t < 200.0:
        if detector.due(t):
            found = detector.observe(t, {1: (1.0, 2.0)}, held=False)
            if found is not None:
                break
        t += 0.3
    assert found is not None
    assert t == pytest.approx(100.8)
    assert found.since_s == pytest.approx(0.0)


def test_a_held_observation_still_paces_the_samples():
    detector = DeadlockDetector()
    detector.observe(0.0, {1: (0.0, 0.0)}, held=True)
    assert not detector.due(0.5)
    assert detector.due(1.0)


def test_to_dict_rounds_to_a_centimetre():
    found = Deadlock(since_s=12.3456, positions=((1.23456, 2.0), (3.0, 4.98765)))
    assert found.to_dict() == {
        "agents": 2,
        "since_s": 12.35,
        "positions": [[1.23, 2.0], [3.0, 4.99]],
    }
