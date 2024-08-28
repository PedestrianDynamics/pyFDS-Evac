import pickle
import sys
import fdsvismap as fv
import logging
from typing import List, Any

# TODO: setuplogger in main script?
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_or_compute_vis(sim_dir: str, waypoints: List[Any], times: List[float], pickle_path: str, c0: str):
    """
    Load or compute the visualization object.

    Args:
        sim_dir (str): The directory containing the simulation data.
        waypoints (list): List of waypoints.
        times (list): List of time points.
        pickle_path (str): The path to the pickle file to load or save the visualization object.
        c0 (float): The value of parameter c0.

    Returns:
        vis (VisMap): The visualization object.

    Raises:
        FileNotFoundError: If the pickle file is not found.
        Exception: If an error occurs while loading or saving the visualization object.

    """
    if pickle_path.is_file():
        try:
            with open(pickle_path, "rb") as file:
                vis = pickle.load(file)
            logger.info("Vis object loaded successfully.")
        except FileNotFoundError:
            logger.critical(f"No file found at {pickle_path}, please check the file path.")
            sys.exit()

        except Exception as e:
            logger.critical(f"An error occurred while loading the visualization: {e}")
            sys.exit()
    else:
        # Read and process data if not existing
        vis = fv.VisMap()
        vis.read_fds_data(str(sim_dir))
        vis.set_start_point(8, 8)

        for wp in waypoints:
            vis.set_waypoint(x=wp[0], y=wp[1], c=c0, alpha=wp[2])

        # Define time points and compute the visualization
        vis.set_time_points(times)
        vis.compute_all()

        # Save results to pickle file
        pickle_path.parent.mkdir(exist_ok=True)  # Ensure directory exists
        try:
            with open(pickle_path, "wb") as file:
                pickle.dump(vis, file)
                logger.info("Visualization saved successfully.")
        except Exception as e:
            logger.critical(f"An error occurred while saving the visualization: {e}")

    return vis
