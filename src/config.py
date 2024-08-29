from pathlib import Path
import os
from shapely import Polygon


class SimulationConfig:
    def __init__(
        self,
        num_agents=40,
        premovement_time=300,
        v0=1.0,
        seed=1,
        c0=3.0,
        update_time=1,
        max_vis_simulation_time=1000,
        distance_to_waypoints=0.5,
    ):
        self.num_agents = num_agents
        self.premovement_time = premovement_time
        self.v0 = v0
        self.seed = seed
        self.c0 = c0
        self.premovement_time = 400  # seconds
        self.update_time = update_time
        self.max_vis_simulation_time = max_vis_simulation_time
        self.times = range(premovement_time, max_vis_simulation_time, update_time)
        self.trajectory_file = f"output_N{num_agents}.sqlite"
        # Path configurations
        self.project_root = Path(os.path.abspath("")).parent
        print(self.project_root)
        self.sim_dir = self.project_root / "fds_data"
        self.pickle_path = self.project_root / "processed_data" / "vismap.pkl"

        # Exit polygons and waypoints
        self.exits = [
            # left
            Polygon([(1, 16), (4, 16), (4, 17.0), (1, 17.0), (1, 16)]),
            # right
            Polygon([(24, 16.0), (27, 16.0), (27, 17.0), (24, 17.0), (24, 16.0)]),
        ]
        self.primary_exit = (
            self.exits[1].centroid.xy[0][0],
            self.exits[1].centroid.xy[1][0],
        )
        self.secondary_exit = (
            self.exits[0].centroid.xy[0][0],
            self.exits[0].centroid.xy[1][0],
        )

        self.distance_to_waypoints = distance_to_waypoints

        self.waypoints = [
            (0, 13.5, 8.5, 0),
            (1, 10.5, 4.5, 180),
            (2, 18.5, 6.5, 270),
            (3, 25, 14.5, 180),
            (4, 4, 6.5, 90),
            (5, 2.5, 14.5, 180),
            (6, self.primary_exit[0], self.primary_exit[1], 180),
            (7, self.secondary_exit[0], self.secondary_exit[1], 180),
        ]
