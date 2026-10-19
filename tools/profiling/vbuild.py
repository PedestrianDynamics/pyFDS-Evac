"""V-build kernel runner (D15): the real vismap build on the first N time points.

Controlled kernel experiment, not an evacuation: no JuPedSim, no agents. It
calls the unchanged pyfds_evac.core.visibility functions `_build_vismap`,
`_vis_bool_array`, `_vis_metre_array` with `_vismap_time_points` cut to its
first N points (the only change; the FDS data, signs, grid and caps are the
deck's). The stage timers and `_get_visibility_array` counts come from
instrument/perf_counters.py; the distinct-frame count and the consecutive-frame
change max|K_t - K_(t-1)| are computed after the timed part.

Usage (cwd = the pyFDS-Evac worktree, baseline venv):
    PYTHONHASHSEED=0 $PY vbuild.py DECK.json FDS_DIR N OUT.json [--time-step 1.0]
        [--slice-height 1.6] [--max-sign-distance 30]
"""

import argparse
import json
import os
import pathlib
import sys
import time

STUDY = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(STUDY / "instrument"))
sys.path.insert(0, os.getcwd())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("fds_dir")
    ap.add_argument("n", type=int)
    ap.add_argument("out")
    ap.add_argument("--time-step", type=float, default=1.0)
    ap.add_argument("--slice-height", type=float, default=1.6)
    ap.add_argument("--max-sign-distance", type=float, default=30.0)
    ap.add_argument("--plain", action="store_true",
                    help="no hooks installed: the three top-level timings are plain")
    ap.add_argument("--no-stats", action="store_true",
                    help="skip the after-timing frame statistics (plain repetitions)")
    a = ap.parse_args()

    import numpy as np

    if not a.plain:
        import perf_counters as pc

        pc.install(a.out + ".counters.json")
    from pyfds_evac.core import visibility as vis_mod

    raw = json.loads(pathlib.Path(a.deck).read_text())
    signs = vis_mod.extract_sign_descriptors(raw)
    full = vis_mod._vismap_time_points
    vis_mod._vismap_time_points = lambda t_end, step: full(t_end, step)[: a.n]

    t0 = time.perf_counter()
    vis = vis_mod._build_vismap(a.fds_dir, signs, a.time_step, a.slice_height, a.max_sign_distance)
    t1 = time.perf_counter()
    arrays = vis_mod._vis_bool_array(vis)
    t2 = time.perf_counter()
    metres = vis_mod._vis_metre_array(vis)
    t3 = time.perf_counter()

    n_t, n_wp = len(vis.vismap_time_points), len(vis.all_sign_dict)
    stats = {}
    if not a.no_stats:
        frames = [np.asarray(vis.get_extco_array_at_time(t)) for t in vis.vismap_time_points]
        distinct = len({f.tobytes() for f in frames})
        # Consecutive-frame change max|K_t - K_(t-1)| [1/m] per time-point pair (outside the timing).
        steps = [float(np.max(np.abs(frames[i] - frames[i - 1]))) for i in range(1, len(frames))]
        steps_arr = np.array(steps) if steps else np.zeros(0)
        consecutive = {
            "pairs": len(steps), "pairs_identical": int(np.sum(steps_arr == 0)),
            "max_abs_diff_max": float(steps_arr.max()) if steps else None,
            "max_abs_diff_median": float(np.median(steps_arr)) if steps else None,
            "max_abs_diff_min": float(steps_arr.min()) if steps else None,
            "max_abs_diff_p90": float(np.percentile(steps_arr, 90)) if steps else None,
        }
        stats = {"distinct": distinct, "consecutive": consecutive}
    res = {
        "schema": "pyfds-evac V-build kernel run v1", "n_time_points": n_t, "n_signs": n_wp,
        "time_step_s": a.time_step, "slice_height_m": a.slice_height,
        "grid_shape_vis": list(arrays.shape), "metres_shape": list(metres.shape),
        "seconds": {"_build_vismap_total": t1 - t0, "_vis_bool_array": t2 - t1,
                    "_vis_metre_array": t3 - t2, "total": t3 - t0},
        "seconds_per_t_wp_metre_array": (t3 - t2) / (n_t * n_wp),
        "distinct_extinction_frames_among_time_points": stats.get("distinct"),
        "consecutive_frame_change_K_per_m": stats.get("consecutive"),
        "method": ("perf_counter in-process; plain (no hooks)" if a.plain else
                   "perf_counter in-process; instrumented (stage hooks), diagnostic"),
    }
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
