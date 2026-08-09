"""``run_scenario(collect_cognitive_map_history=True)`` reports what agents learn.

The map is built and grown inside ``run_scenario``; before this flag the only
way to see it from outside was to re-implement the expansion, which tests the
re-implementation rather than the engine's call sites. These tests pin the
recorded history against the two things that are true by construction: the map
only ever grows, and a ``full`` agent knows everything from the first frame.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.visibility import extract_sign_descriptors

ASSET = Path("assets/blind_spawn_discovery")
MAX_VIS_M = 30.0


class ClearAirVisMap:
    """``node_is_visible`` reduced to line of sight, as in clear air.

    Mirrors ``OccludingVisMap`` in test_blind_spawn_discovery: without it a
    discovery agent perceives nothing (``cognitive_map._expand_visible`` returns
    early when ``vis_model is None``) and the history has nothing to show.
    """

    def __init__(self, signs: dict[str, dict], walkable):
        self._signs = signs
        self._walkable = walkable

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        del time
        sign = self._signs.get(node_id)
        if sign is None:
            return True
        target = (float(sign["x"]), float(sign["y"]))
        if math.dist((x, y), target) > MAX_VIS_M:
            return False
        return self._walkable.covers(LineString([(x, y), target]))


def _bundle(tmp_path: Path, variant: str) -> Path:
    """Lay out one of the asset's config variants as a loadable bundle."""
    out = tmp_path / variant
    out.mkdir(parents=True)
    shutil.copy(ASSET / f"config_{variant}.json", out / "config.json")
    shutil.copy(ASSET / "geometry.wkt", out / "geometry.wkt")
    return out


def _run(bundle: Path, *, collect: bool, with_vis: bool):
    scenario = load_scenario(str(bundle))
    vis = None
    if with_vis:
        walkable = shapely_wkt.loads((bundle / "geometry.wkt").read_text().strip())
        vis = ClearAirVisMap(extract_sign_descriptors(scenario.raw), walkable)
    return run_scenario(
        scenario,
        seed=420,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        vis_model=vis,
        collect_cognitive_map_history=collect,
    )


def test_history_is_none_unless_requested(tmp_path):
    result = _run(_bundle(tmp_path, "discovery"), collect=False, with_vis=True)
    try:
        assert result.cognitive_map_history is None
        assert "cognitive_map_events" not in result.metrics
    finally:
        result.cleanup()


def test_discovery_agents_learn_and_never_forget(tmp_path):
    result = _run(_bundle(tmp_path, "discovery"), collect=True, with_vis=True)
    try:
        history = result.cognitive_map_history
        assert history, "expected at least one recorded learning event"
        assert result.metrics["cognitive_map_events"] == len(history)

        per_agent: dict[int, list[dict]] = {}
        for event in history:
            per_agent.setdefault(event["agent_id"], []).append(event)

        for agent_id, events in per_agent.items():
            assert [e["time_s"] for e in events] == sorted(
                e["time_s"] for e in events
            ), f"agent {agent_id}: events out of order"
            for older, newer in zip(events, events[1:]):
                # A cognitive map is memory: it only ever grows.
                assert set(older["known_nodes"]) <= set(newer["known_nodes"])
                assert set(older["known_edges"]) <= set(newer["known_edges"])
                assert len(newer["known_nodes"]) + len(newer["known_edges"]) > len(
                    older["known_nodes"]
                ) + len(older["known_edges"]), "a recorded event that changed nothing"

        # Catches expansion stopping altogether. Deliberately NOT a claim about
        # perception: on this asset the recorded history is byte-identical with
        # and without a vis_model, because the agents reach the checkpoints and
        # expand_on_arrival alone produces the same final maps. A test that
        # named perception here would pass with perception disabled.
        grew = [a for a, e in per_agent.items() if len(e) > 1]
        assert grew, "no discovery agent's map grew during the run"
    finally:
        result.cleanup()


def test_full_familiarity_knows_everything_from_the_first_frame(tmp_path):
    bundle = _bundle(tmp_path, "full")
    raw = json.loads((bundle / "config.json").read_text())
    n_nodes = (
        len(raw["exits"]) + len(raw.get("checkpoints", {})) + len(raw["distributions"])
    )
    result = _run(bundle, collect=True, with_vis=True)
    try:
        history = result.cognitive_map_history or []
        assert history
        for event in history:
            assert event["familiarity"] == "full"
            # One event per agent, recorded once and never revised.
            assert len(event["known_nodes"]) == n_nodes
        seen = [e["agent_id"] for e in history]
        assert len(seen) == len(set(seen)), "a full agent's map changed mid-run"
    finally:
        result.cleanup()


@pytest.mark.parametrize("variant", ["discovery", "full"])
def test_history_does_not_change_the_run(tmp_path, variant):
    """Collecting is an observation, not an intervention."""
    off = _run(_bundle(tmp_path / "a", variant), collect=False, with_vis=True)
    on = _run(_bundle(tmp_path / "b", variant), collect=True, with_vis=True)
    try:
        assert off.agents_evacuated == on.agents_evacuated
        assert off.evacuation_time == pytest.approx(on.evacuation_time)
    finally:
        off.cleanup()
        on.cleanup()
