"""Target clearance, the next-stage stream and the speed-factor clip (#876).

Expected values come from ``docs/howto-place-checkpoints.md`` (target
clearance) and ``docs/scenario-json.md`` (speed-factor clip), or are pinned
as stated in the docstrings.
"""

from __future__ import annotations

import random

import pytest
from shapely.geometry import Point, box

from pyfds_evac.core.direct_steering_runtime import (
    advance_path_target,
    pick_stage_target,
)
from pyfds_evac.core.simulation_init import (
    _normalize_speed_factor,
    _pick_initial_stage_target,
)

STAGE = box(0.0, 0.0, 2.0, 2.0)
DRAWS = 3000


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.5, 0.5),
        ("0.5", 0.5),
        (1, 1.0),
        (0.0, 0.0),
        (3.0, 3.0),
        (5.0, 3.0),
        (-0.1, 1.0),
        (None, 1.0),
        ("abc", 1.0),
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (float("-inf"), 1.0),
        ([0.5], 1.0),
    ],
)
def test_simulation_init_clips_the_speed_factor_to_zero_to_three(value, expected):
    """The set-up copy of the clip: [0, 3], negative or non-numeric gives 1.0.

    ``docs/scenario-json.md``: "clipped to [0, 3]. A negative or non-numeric
    value becomes 1.0." The same table pins the runtime copy in
    ``test_speed_update_pin.py::test_normalize_speed_factor``.
    """
    assert _normalize_speed_factor(value) == expected


def _distances_to_edge(points) -> list[float]:
    return [STAGE.exterior.distance(Point(p)) for p in points]


def _assert_clearance_is_exactly(distances, clearance):
    """No point closer than ``clearance``; some within 0.01 m of it.

    The second half kills a clearance that is too deep: the points are
    uniform in the shrunk polygon, so about 1.5 % lie in the first 0.01 m.
    """
    assert min(distances) >= clearance - 1e-9
    assert min(distances) < clearance + 0.01


@pytest.mark.parametrize(
    ("radius", "clearance"),
    [(0.2, 0.25), (0.5, 0.4)],
)
def test_the_first_stage_target_keeps_the_documented_clearance(radius, clearance):
    """First stage: max(0.05, 0.8 r, 0.25) m (``howto-place-checkpoints.md``).

    Radius 0.2 gives max(0.05, 0.16, 0.25) = 0.25; radius 0.5 gives
    max(0.05, 0.4, 0.25) = 0.4.
    """
    rng = random.Random(1)
    points = [
        _pick_initial_stage_target({"polygon": STAGE}, None, rng, radius)
        for _ in range(DRAWS)
    ]
    _assert_clearance_is_exactly(_distances_to_edge(points), clearance)


@pytest.mark.parametrize(
    ("state", "clearance"),
    [
        ({"agent_radius": 0.2}, 0.16),
        ({"agent_radius": 0.5}, 0.4),
        ({}, 0.16),
        ({"agent_radius": 0.01}, 0.05),
    ],
)
def test_a_later_stage_target_keeps_the_documented_clearance(state, clearance):
    """Later stages: max(0.05, 0.8 r) m; a missing radius counts as 0.2 m.

    0.8 * 0.2 = 0.16; 0.8 * 0.5 = 0.4; 0.8 * 0.01 = 0.008 is below the
    0.05 floor. Each target is drawn with its own ``base_seed``.
    """
    points = [
        pick_stage_target(
            {**state, "base_seed": seed, "step_index": 0}, {"polygon": STAGE}
        )
        for seed in range(DRAWS)
    ]
    _assert_clearance_is_exactly(_distances_to_edge(points), clearance)


@pytest.mark.parametrize(
    ("choice_seed", "step_index", "stage"),
    [(5, 0, "s11"), (5, 3, "s0"), (7, 1, "s15"), (100, 2, "s15"), (12345, 5, "s14")],
)
def test_the_next_stage_is_drawn_from_choice_seed_plus_step_stream(
    choice_seed, step_index, stage
):
    """Twenty equal-weight stages; the pick is pinned per (seed, step).

    The stream is ``random.Random(choice_seed + 131 * step_index + 53)``
    (``direct_steering_runtime.advance_path_target``); the stages are
    recorded from the shipped stream, whose ``random()`` is stable across
    Python versions. Five combinations, so each of the stream's three terms
    changes at least one pick (a changed term moves a pick with probability
    19/20).
    """
    stages = {f"s{i}": {"polygon": box(i, 0, i + 1, 1)} for i in range(20)}
    wait_info = {
        "path_choices": {"a": [(name, 1.0) for name in stages]},
        "stage_configs": stages,
        "current_target_stage": "a",
        "step_index": step_index,
        "choice_seed": choice_seed,
    }
    advance_path_target(wait_info)
    assert wait_info["current_target_stage"] == stage
