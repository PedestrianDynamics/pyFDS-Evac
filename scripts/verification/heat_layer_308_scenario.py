"""Write ``assets/heat_radiometer_layer_308/config.json`` and ``geometry.wkt``.

Seven stationary agents on the FDS device line y = 2.05 m, one at each of
the x positions of the #308 devices, in the 4 x 4 m room of
``assets/heat_radiometer/heat_radiometer_layer_308.fds``. Each agent has a
constant pre-movement of 100 s, longer than the 10 s FDS run, so it stays
where it is placed (``v0`` must be positive, so it cannot be 0). The
distribution polygon is a 0.22 m square around the device point.

Run from the repository root::

    python scripts/verification/heat_layer_308_scenario.py
"""

from __future__ import annotations

import json
from pathlib import Path

from heat_layer_view_factor import GAUGE_X_M, GAUGE_Y_M

OUT = Path(__file__).resolve().parents[2] / "assets" / "heat_radiometer_layer_308"
HALF_M = 0.11
EXIT = [[3.5, 3.5], [4.0, 3.5], [4.0, 4.0], [3.5, 4.0], [3.5, 3.5]]


def square(x: float, y: float) -> list[list[float]]:
    x0, x1, y0, y1 = x - HALF_M, x + HALF_M, y - HALF_M, y + HALF_M
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def distribution(x: float) -> dict:
    return {
        "type": "polygon",
        "coordinates": square(x, GAUGE_Y_M),
        "parameters": {
            "number": 1,
            "radius": 0.1,
            "v0": 1.2,
            "use_flow_spawning": False,
            "distribution_mode": "by_number",
            "percentage": None,
            "use_premovement": True,
            "premovement_distribution": "constant",
            "premovement_param_a": 100,
            "premovement_seed": None,
            "radius_distribution": "constant",
            "v0_distribution": "constant",
            "familiarity": "discovery",
        },
        "journey_weights": [{"journey_id": "journey_0", "weight": 100.0}],
    }


def main() -> None:
    config = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 10,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": 42,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            "exit_corner": {
                "type": "polygon",
                "coordinates": EXIT,
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
        },
        "distributions": {f"agent_x{x:.2f}": distribution(x) for x in GAUGE_X_M},
        "checkpoints": {},
        "zones": {},
        "journeys_v2": [
            {
                "id": "journey_0",
                "name": "journey_0",
                "color": "#4e79a7",
                "sequence": ["exit_corner"],
            }
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (OUT / "geometry.wkt").write_text("POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0))\n")


if __name__ == "__main__":
    main()
