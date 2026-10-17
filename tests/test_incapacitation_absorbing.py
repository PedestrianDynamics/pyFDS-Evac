"""Incapacitation is absorbing: a dead agent stays, is never counted as
evacuated and is not sampled again; the run ends when every mobile agent
has left (#145, #593, #141).

Decks are synthetic: the corridor of ``tests/verification/harness.py`` with
a uniform lethal CO field (60 000 ppm, collapse at about 23 s) or a lethal
band, so the collapse time is known from the closed form.
"""

from __future__ import annotations

import contextlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "verification"))

from harness import (  # noqa: E402
    CorridorSpec,
    after,
    corridor_scenario,
    deterministic_tenability,
    first_incapacitation_times,
    make_fed_model,
    region_x,
    uniform,
)

from pyfds_evac.core.scenario import run_scenario  # noqa: E402

CO_LETHAL = 0.06  # volume fraction, 60 000 ppm


def _co_model(field, update_interval_s: float = 1.0):
    return make_fed_model(
        co_volume_fraction=field,
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        update_interval_s=update_interval_s,
    )


def _trajectory(result) -> dict[int, list[tuple[float, float, float]]]:
    """Per agent, the (time_s, x, y) rows of the trajectory in time order."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY frame"
        ).fetchall()
    out: dict[int, list[tuple[float, float, float]]] = {}
    for agent_id, frame, x, y in rows:
        out.setdefault(agent_id, []).append((frame / fps, x, y))
    return out


def _run(spec, field, *, premovement_s=None, update_interval_s=1.0, threshold=1.0):
    scenario = corridor_scenario(spec)
    if premovement_s is not None:
        params = scenario.raw["distributions"]["spawn_near"]["parameters"]
        params["use_premovement"] = True
        params["premovement_distribution"] = "constant"
        params["premovement_param_a"] = premovement_s
    return run_scenario(
        scenario,
        seed=spec.seed,
        fed_model=_co_model(field, update_interval_s),
        tenability_config=deterministic_tenability(threshold),
    )


def test_premovement_does_not_wake_an_incapacitated_agent():
    """#145: the activation at the end of the delay must skip a dead agent."""
    spec = CorridorSpec(num_agents=1, max_simulation_time=60.0)
    result = _run(spec, uniform(CO_LETHAL), premovement_s=30.0)
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) == 1
        t_inc = next(iter(incap.values()))
        assert t_inc < 30.0

        (track,) = _trajectory(result).values()
        at_collapse = next((x, y) for t, x, y in track if t >= t_inc)
        for t, x, y in track:
            if t < t_inc:
                continue
            assert x == pytest.approx(at_collapse[0], abs=1e-6)
            assert y == pytest.approx(at_collapse[1], abs=1e-6)

        metrics = result.metrics
        assert metrics["agents_evacuated"] == 0
        assert metrics["agents_remaining"] == 1
    finally:
        result.cleanup()

