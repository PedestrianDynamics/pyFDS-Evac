"""Checks of ``scripts/verification/familiarity_figures.py`` (Verification > Familiarity).

Criterion 1 of the page says that every agent of the full tier passes CP3.
The script decides "passes" from the recorded trajectory. An agent at
1.3 m/s moves 0.65 m in 0.5 s, more than the depth of CP3's box (0.55 m),
so the check must test every frame, not a subsample (#637).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import box

FPS = 10


def _figures_module():
    """Import the figure script without running it."""
    path = Path("scripts/verification/familiarity_figures.py")
    spec = importlib.util.spec_from_file_location("familiarity_figures", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_check_full_sees_a_box_crossed_between_half_second_samples():
    fig = _figures_module()
    walkable = box(0.0, 0.0, 10.0, 10.0)
    polys = {
        "CP0": box(0.5, 0.5, 1.0, 1.0),
        "CP1": box(1.5, 0.5, 2.0, 1.0),
        "CP2": box(2.5, 0.5, 3.0, 1.0),
        "CP3": box(4.0, 5.0, 6.0, 5.55),  # 0.55 m deep, like the deck's
        "E": box(4.0, 9.0, 6.0, 9.5),
    }
    # 1.3 m/s along x = 5: frames 0, 5, 10 sit at y = 4.30, 4.95, 5.60,
    # all outside the box; frames 6-9 are inside it.
    frames = range(16)
    traj = pd.DataFrame(
        {
            "id": 1,
            "frame": list(frames),
            "x": 5.0,
            "y": [4.3 + 1.3 * k / FPS for k in frames],
        }
    )
    assert not any(
        polys["CP3"].contains(fig.Point(p)) for p in traj[["x", "y"]].to_numpy()[::5]
    )
    edges = {"S": {"CP3"}, "CP3": {"E"}}
    maps = pd.DataFrame(
        {
            "time_s": [0.0],
            "agent_id": [1],
            "nodes": [{"S", "CP3", "E"}],
            "edges": [{("S", "CP3"), ("CP3", "E")}],
        }
    )
    df, _, _ = fig.check_full(fig.Geodesic(walkable), polys, traj, [], maps, edges, 1.3)
    assert df.loc[0, "entered"] == {"CP3"}
