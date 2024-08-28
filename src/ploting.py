import pedpy
from matplotlib.patches import Circle
import matplotlib.pyplot as plt
from jpstooling import compute_waypoints_and_visibility


def plot_simulation_configuration(
    waypoints, distance_to_waypoints, walkable_area, starting_positions, exits, path1=None, path2=None
):
    axes = pedpy.plot_walkable_area(walkable_area=walkable_area)
    for exit_area in exits:
        axes.fill(*exit_area.exterior.xy, color="indianred", alpha=0.2)

    for starting_position in starting_positions:
        axes.scatter(*zip(*starting_position), s=1, color="gray")

    axes.set_xlabel("x/m")
    axes.set_ylabel("y/m")
    axes.set_aspect("equal")
    for idx, waypoint in enumerate(waypoints):
        axes.plot(waypoint[0], waypoint[1], "go")
        axes.annotate(
            f"$WP_{idx}$",
            (waypoint[0], waypoint[1]),
            textcoords="offset points",
            xytext=(10, -15),
            ha="center",
        )
        circle = Circle(
            (waypoint[0], waypoint[1]),
            distance_to_waypoints,
            fc="green",
            ec="green",
            alpha=0.1,
        )
        axes.add_patch(circle)

    if path1:
        path1 = path1
        x_coords = [point[0] for point in path1]
        y_coords = [point[1] for point in path1]
        for idx, point in enumerate(path1):
            if idx == 0:
                color="black"
                facecolor="black"
            #else:
            #    color = "blue"
            #    facecolor="none"    
            
                axes.plot(
                    point[0],
                    point[1],
                    "o",
                    markerfacecolor=facecolor,
                    markeredgewidth=1,
                    markeredgecolor=color,
                )
        axes.plot(x_coords, y_coords, "b--")

    if path2:
        path2 = path2[:]
        x_coords = [point[0] for point in path2]
        y_coords = [point[1] for point in path2]
        for idx, point in enumerate(path2):
            if idx == 0:
                color="black"
                facecolor="black"
                axes.plot(
                    point[0],
                    point[1],
                    "o",
                    markerfacecolor=facecolor,
                    markeredgewidth=1,
                    markeredgecolor=color,
                )
        axes.plot(x_coords, y_coords, "r--")

    plt.savefig("simulation_configuration.png")
    print("Simulation configuration saved as simulation_configuration.png")



def plot_visibility_path(logger, config, vis, routing, starting_point):
    vis1 = []
    vis2 = []
    times = range(0, 2000, 10)

    for time in times:
        print("time", time)
        waypoints_info = compute_waypoints_and_visibility(
        routing, starting_point, config.primary_exit, config.waypoints, time
    )
    # print(waypoints_info[0:])
        print("------ FIRST PATH -------")
        print(waypoints_info)
        vis_point = 0
        seen = set()
        for wp_id, is_visible in zip(waypoints_info[1], waypoints_info[2]):
            if wp_id not in seen and is_visible:
                seen.add(wp_id)
                print(f"{wp_id = }, {is_visible = }")
                x = config.waypoints[wp_id][1]
                y = config.waypoints[wp_id][2]
                vis_point += vis.get_local_visibility(time=time, x=x, y=y, c=3)

        print("==>> local visibility:", vis_point)
        print("------ SECOND PATH -------")
        vis1.append(vis_point)
        waypoints_info2 = compute_waypoints_and_visibility(
        routing,starting_point, config.secondary_exit, config.waypoints, time
    )
        print(waypoints_info2)
        vis_point2 = 0
        seen2 = set()
        for wp_id, is_visible in zip(waypoints_info2[1], waypoints_info2[2]):
            if wp_id not in seen2 and is_visible:
                print(f"{wp_id = }, {is_visible = }")
                seen2.add(wp_id)
                x = config.waypoints[wp_id][1]
                y = config.waypoints[wp_id][2]
                vis_point2 += vis.get_local_visibility(time=time, x=x, y=y, c=3)

        print("local visibility:", vis_point2)
        vis2.append(vis_point2)

    fig, ax = plt.subplots()
    ax.plot(times, vis1, "-b", label="evac route 1")
    ax.plot(times, vis2, "-r", label="evac route 2")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Local Visibility Along Path")
    ax.grid(alpha=0.3)
    plt.legend()
    fig.savefig("local_visibilioty_along_path.png")
    logger.info("> local_visibilioty_along_path.png")