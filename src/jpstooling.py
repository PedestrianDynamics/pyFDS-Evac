"""jupedsim related functions."""

import numpy as np
from .utilities import distance
from typing import List, Tuple, Any
import jupedsim as jps
from pathlib import Path

from .config import SimulationConfig
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def calculate_desired_speed(
    visibility: float, c: float, max_speed: float, range: float = 2.0
):
    """
    Calculate the desired speed based on the proximity of v to c.

    Parameters:
    visibility (float): Visibility value.
    c (float): Constant.
    max_speed (float): The maximum speed.
    range (float, optional): The range parameter for adjusting the speed. Defaults to 2.0.

    Returns:
    float: The adjusted speed based on the proximity of v to c.
    """
    if visibility <= c:
        return 0
    else:
        return max_speed * (1 - np.exp(-(visibility - c) / range))


def get_next_waypoint(point, waypoints):
    """Return the waypoint that is closest to point."""
    min_distance = float("inf")
    next_waypoint = None
    next_waypoint_id = -1
    # print(point)
    for wp in waypoints:
        d = distance(point, wp)
        if d < min_distance:
            min_distance = d
            next_waypoint = wp
            next_waypoint_id = waypoints.index(wp)

    # print(f"Next waypoint: {next_waypoint}")
    return next_waypoint_id, next_waypoint


def compute_waypoints_and_visibility(
    vis: Any,
    routing: Any,
    agent_position: Tuple[float, float],
    primary_exit: Tuple[float, float],
    waypoints: List[Tuple[float, float, float]],
    time: float,
):
    """Compute the waypoints and their visibility.

    returns:
    wps_on_path: List of waypoints on the path.
    wps_on_path_id: List of waypoint IDs on the path.
    wps_on_path_visibility: List of visibility values for the waypoints on the path.
    """
    path = routing.compute_waypoints(agent_position, primary_exit)
    wps_on_path = []
    wps_on_path_id = []
    wps_on_path_visibility = []

    for point in path[1:]:
        wp_id, wp = get_next_waypoint(point=point, waypoints=waypoints)
        wps_on_path.append(wp)
        wps_on_path_id.append(wp_id)
        # distance = vis.get_distance_to_wp(
        #     x=agent_position[0], y=agent_position[1], waypoint_id=wp_id
        # )
        wp_is_visible = vis.wp_is_visible(
            time=time,
            x=agent_position[0],
            y=agent_position[1],
            waypoint_id=wp_id,
        )
        wps_on_path_visibility.append(wp_is_visible)

    return wps_on_path, wps_on_path_id, wps_on_path_visibility


def log_path_info(
    time: float,
    path: List[Any],
    agent: jps.Agent,
    waypoints_info: List[Any],
    speed: float,
):
    """Print logging messages."""
    print("path: ", path[1:-1])
    wp_ids = waypoints_info[1]
    wp_visibility = waypoints_info[2]
    wp = waypoints_info[0]
    for wp_id, wp, wp_is_visible in zip(wp_ids, wp, wp_visibility):
        print(
            f"time = {time:.2f}, x = {agent.position[0]:.2f}, y = {agent.position[1]:.2f}, "
            f"v = {speed:.2f}, agent.id = {agent.id}, wp_id = {wp_id}, wp = {wp}, wp_is_visible = {wp_is_visible}, "
            f"agent.model.desiredSpeed = {agent.model.desiredSpeed:.2f}",
            end="\n",
        )
    print("RESULT: ", any(waypoints_info[2]))
    print("===========")


def process_waypoints(
    waypoints_info: List, waypoints: List, vis: Any, time: float
) -> Tuple[float, float]:
    vis_point = 0
    seen = set()
    for wp_id, is_visible in zip(waypoints_info[1], waypoints_info[2]):
        if wp_id not in seen and is_visible:
            seen.add(wp_id)
            x = waypoints[wp_id][1]
            y = waypoints[wp_id][2]
            vis_point += vis.get_local_visibility(time=time, x=x, y=y, c=3)
    return vis_point


def check_and_update_journeys(
    routing,
    simulation: jps.Simulation,
    time: float,
    primary_exit: Tuple[float, float],
    secondary_exit: Tuple[float, float],
    primary_journey_id: int,
    secondary_journey_id: int,
    primary_exit_id: int,
    secondary_exit_id: int,
    waypoints: List[Tuple[float, float, float]],
    vis: Any,
    config: SimulationConfig,
):
    """
    Check and update the journeys of agents in the simulation based on their current positions and visibility.

    Args:
        routing: The routing object used for computing waypoints and visibility.
        simulation (jps.Simulation): The simulation object.
        time (float): The current simulation time.
        primary_exit (Tuple[float, float]): The coordinates of the primary exit.
        secondary_exit (Tuple[float, float]): The coordinates of the secondary exit.
        primary_journey_id (int): The ID of the primary journey.
        secondary_journey_id (int): The ID of the secondary journey.
        primary_exit_id (int): The ID of the primary exit.
        secondary_exit_id (int): The ID of the secondary exit.
        waypoints (List[Tuple[float, float, float]]): The list of waypoints.
        vis (Any): The visibility object.
        config (SimulationConfig): The simulation configuration.

    Returns:
        None
    """
    for agent in simulation.agents():
        agent_position = agent.position
        waypoints_info = compute_waypoints_and_visibility(
            vis, routing, agent_position, primary_exit, waypoints, time
        )
        waypoints_info_s = compute_waypoints_and_visibility(
            vis, routing, agent_position, secondary_exit, waypoints, time
        )

        # Set the speed
        local_visibility = vis.get_local_visibility(
            time=time, x=agent_position[0], y=agent_position[1], c=config.c0
        )
        agent.model.desiredSpeed = calculate_desired_speed(
            local_visibility, config.c0, config.v0, range=5
        )
        vis_point = process_waypoints(waypoints_info, waypoints, vis, time)
        vis_point_s = process_waypoints(waypoints_info_s, waypoints, vis, time)

        if vis_point_s > vis_point:
            simulation.switch_agent_journey(
                agent.id, secondary_journey_id, secondary_exit_id
            )
        else:
            simulation.switch_agent_journey(
                agent.id, primary_journey_id, primary_exit_id
            )


def add_agents_to_simulation(
    simulation: jps.Simulation, pos_in_spawning_areas, journey_primary_id, exit_ids
):
    # Add agents to the upper room
    ids_up = set(
        [
            simulation.add_agent(
                jps.SocialForceModelAgentParameters(
                    desiredSpeed=0,
                    radius=0.1,
                    journey_id=journey_primary_id,
                    stage_id=exit_ids[1],
                    position=pos,
                )
            )
            for pos in pos_in_spawning_areas[0]
        ]
    )
    # Add agents to the lower room
    ids_down = set(
        [
            simulation.add_agent(
                jps.SocialForceModelAgentParameters(
                    desiredSpeed=0,
                    radius=0.1,
                    journey_id=journey_primary_id,
                    stage_id=exit_ids[1],
                    position=pos,
                )
            )
            for pos in pos_in_spawning_areas[1]
        ]
    )
    return ids_up, ids_down


def run_simulation(
    trajectory_file,
    walkable_area,
    exits,
    spawning_area1,
    spawning_area2,
    vis,
    config: SimulationConfig,
):
    simulation = jps.Simulation(
        model=jps.SocialForceModel(),
        geometry=walkable_area.polygon,
        trajectory_writer=jps.SqliteTrajectoryWriter(output_file=Path(trajectory_file)),
    )

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
    exit_ids = [
        simulation.add_exit_stage(exit_area.exterior.coords[:-1]) for exit_area in exits
    ]
    # Notausgang
    journey_secondary = jps.JourneyDescription([exit_ids[0]])
    journey_secondary_id = simulation.add_journey(journey_secondary)
    secondary_exit = (exits[0].centroid.xy[0][0], exits[0].centroid.xy[1][0])
    # Hauptausgang
    journey_primary = jps.JourneyDescription([exit_ids[1]])
    journey_primary_id = simulation.add_journey(journey_primary)
    primary_exit = (exits[1].centroid.xy[0][0], exits[1].centroid.xy[1][0])
    # Add agents to the upper room
    add_agents_to_simulation(
        simulation, pos_in_spawning_areas, journey_primary_id, exit_ids
    )
    routing = jps.RoutingEngine(walkable_area.polygon)
    # Simulate premovement time in seconds
    premovement_iterations = config.premovement_time * int(1 / simulation.delta_time())
    simulation.iterate(premovement_iterations)
    # Start movement. The simulation will stop if no agents are left or the max_vis_simulation_time is reached
    while (
        simulation.elapsed_time() < config.premovement_time + 200
    ):  # max_vis_simulation_time:
        t = simulation.elapsed_time()  # seconds
        # Generate new agents every 10 seconds
        if (
            simulation.iteration_count() > premovement_iterations + 200
            and simulation.iteration_count() % 2000 == 0
        ):
            add_agents_to_simulation(
                simulation, pos_in_spawning_areas, journey_primary_id, exit_ids
            )

        if simulation.iteration_count() % 2000 == 0:
            print(f"Simulation time: {t:2.2f} s", end="\r")
            check_and_update_journeys(
                routing=routing,
                simulation=simulation,
                time=t,
                primary_exit=primary_exit,
                primary_exit_id=exit_ids[1],
                primary_journey_id=journey_primary_id,
                secondary_exit=secondary_exit,
                secondary_exit_id=exit_ids[0],
                secondary_journey_id=journey_secondary_id,
                waypoints=config.waypoints,
                vis=vis,
                config=config,
            )

        simulation.iterate()

    logger.info(f"Simulation finished after {simulation.elapsed_time():.2f} seconds.")
