"""Main entry script."""

import os
from pathlib import Path

import jupedsim as jps
import matplotlib.pyplot as plt
import pedpy
import shapely
from shapely import Polygon, from_wkt
import logging
from src.jpstooling import calculate_desired_speed, run_simulation
from src.fdstooling import load_or_compute_vis
from src.ploting import plot_simulation_configuration, plot_visibility_path
from typing import List
from src.config import SimulationConfig

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DebugPlots:
    def __init__(self, config, vis):
        self.config = config
        self.vis = vis

    def log_waypoint_visibility(self, x, y, t):
        """Logs visibility and distance information for each waypoint at a given time."""
        for wp_id, _ in enumerate(self.config.waypoints):
            self.logger.debug(f"Time: {t}, Waypoint ID: {wp_id}")
            visibility = self.vis.wp_is_visible(time=t, x=x, y=y, waypoint_id=wp_id)
            self.logger.debug(f"Visibility: {visibility}")
            dis = self.vis.get_distance_to_wp(x=x, y=y, waypoint_id=wp_id)
            logger.debug(f"Distance: {dis:.2f} [m]")
            print("----")

    def plot_local_visibility(self, x, y, c):
        """Plots local visibility over time for a given location and visibility factor."""
        local_visibility = []
        for t in self.config.times:
            visibility = self.vis.get_local_visibility(time=t, x=x, y=y, c=c)
            local_visibility.append(visibility)

        plt.plot(self.config.times, local_visibility)
        plt.xlabel("Time [s]")
        plt.ylabel("Local Visibility")
        plt.savefig("local_visibility.png", dpi=300, bbox_inches="tight")
        logger.info("Local visibility plot saved successfully.")
        return local_visibility

    def plot_desired_speed_visibility(local_visibility: List[float], c):
        """Plots the desired speed over time for a given location and visibility factor."""

        desired_speeds = [
            calculate_desired_speed(visibility, c, max_speed=1.0, range=5)
            for visibility in local_visibility
        ]
        plt.plot(config.times, desired_speeds)
        plt.xlabel("Time [s]")
        plt.ylabel("Desired Speed [m/s]")
        plt.savefig("desired_speed.png", dpi=300, bbox_inches="tight")
        logger.info("Desired speed plot saved successfully.")


config = SimulationConfig()

## Vismap config
vis = load_or_compute_vis(
    config.sim_dir, config.waypoints, config.times, config.pickle_path, config.c0
)

debug_plots = DebugPlots(config, vis)
# Log waypoint visibility for a specific location and time
debug_plots.log_waypoint_visibility(x=18.51, y=6.79, t=16)
# Plot local visibility for a given location and c factor
local_visibility = debug_plots.plot_local_visibility(x=5, y=6, c=3)
debug_plots.plot_desired_speed_visibility(local_visibility, c=3)

fig, ax = vis.create_aset_map_plot(plot_obstructions=True)
fig.savefig("aset_map.png", dpi=300, bbox_inches="tight")
logger.info("ASET map saved successfully.")
fig, ax = vis.create_time_agg_wp_agg_vismap_plot(plot_obstructions=True)
fig.savefig("vismap.png", dpi=300, bbox_inches="tight")
logger.info("Vismap saved successfully.")


# CO2 = np.arange(0, 10, 0.001)
# HV = 0.141 * np.exp(0.1930* CO2+ 2.0004)
# plt.plot(CO2, HV)


with open("geometry.wkt", "r") as file:
    data = file.readlines()

wkt_data = from_wkt(data)
area = wkt_data[0]
obstacles = wkt_data[1:]
obstacle = shapely.union_all(obstacles)
walkable_area = pedpy.WalkableArea(shapely.difference(area, obstacle))
routing = jps.RoutingEngine(walkable_area.polygon)
spawning_area1 = Polygon([(1, 0), (1, 3), (15, 3), (15, 0)])
spawning_area2 = Polygon([(5, 10), (19, 10), (19, 14.5), (5, 14.5)])

# DEBUG
starting_point = config.waypoints[0][0:2]
starting_point = (10.6, 6.89)
path1 = routing.compute_waypoints(starting_point, config.primary_exit)
path2 = routing.compute_waypoints(starting_point, config.secondary_exit)
print("path1:", path1[1:-1])
print("path2:", path2[1:-1])
pos_in_spawning_areas = [
    jps.distributions.distribute_by_number(
        polygon=spawning_area2,
        number_of_agents=config.num_agents,
        distance_to_agents=0.4,
        distance_to_polygon=0.3,
        seed=config.seed,
    ),
    jps.distributions.distribute_by_number(
        polygon=spawning_area1,
        number_of_agents=config.num_agents,
        distance_to_agents=0.4,
        distance_to_polygon=0.3,
        seed=config.seed,
    ),
]
plot_simulation_configuration(
    config.waypoints,
    config.distance_to_waypoints,
    walkable_area,
    pos_in_spawning_areas,
    config.exits,
    path1,
    path2,
)
fig, ax = plt.subplots()
fig.savefig("simulation_configuration.png")
logger.info("Simulation configuration saved successfully.")
# DEBUG

plot_visibility_path(logger, config, vis, routing, starting_point)

run_simulation(
    walkable_area=walkable_area,
    exits=config.exits,
    spawning_area1=spawning_area1,
    spawning_area2=spawning_area2,
    trajectory_file=config.trajectory_file,
    vis=vis,
)
