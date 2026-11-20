# %% [markdown]
# # ASET, RSET and DIFF maps
#
# Where in a room does the fire make conditions untenable before the last
# person has left? The ASET map says when each cell becomes untenable, the
# RSET map when each cell is last occupied, and DIFF = ASET - RSET says who
# wins. A negative DIFF is a failure.
#
# The room is the 10 x 10 m gas room of `assets/iso_table22_coupled`, deck e,
# with 20 people leaving through the corner exit in clear air. Its gas is
# uniform in space, so the ASET map is flat and only the RSET map varies. To
# let the room fail somewhere, the FED limit is 0.05 instead of the default
# 0.3. A real study uses a fire that varies in space and many seeds.
#
# Run from the repository root:
#
#     uv run python examples/aset_rset_maps.py               # figure in a temp dir
#     uv run python examples/aset_rset_maps.py <figure.png>  # figure at that path

# %%
import pathlib
import sys
import tempfile

import numpy as np

from pyfds_evac import load_scenario, run_scenario
from pyfds_evac.analysis import (
    AsetCriteria,
    aset_map,
    diff_map,
    grid_from_walkable,
    load_trajectory,
    measures,
    plot_maps,
    pool_rset,
    read_crossings,
    rset_map,
    seed_measures,
)

FDS = "assets/iso_table22_coupled/fds/e"
CELL = 0.6
SEEDS = [1, 2, 3]
FIGURE = pathlib.Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else pathlib.Path(tempfile.mkdtemp()) / "aset_rset_diff.png"
)

# %% [markdown]
# ## ASET from the FDS output
#
# `read_crossings` finds, at every node of the slices, the first time each
# criterion is met. The defaults are K >= 0.3 1/m (10 m of visibility at
# C = 3), 45 degC, and FED 0.3 for someone standing still from t = 0. Here
# only the toxic FED counts, at a limit of 0.05.

# %%
criteria = AsetCriteria(
    visibility_limit_m=None, temperature_c=None, heat_fed=None, fed=0.05
)
crossings = read_crossings(FDS, criteria)
for crossing in crossings:
    print(
        f"{crossing.name}: slice at z = {crossing.z_m} m, data to {crossing.horizon_s:.0f} s"
    )

# %% [markdown]
# ## RSET from the runs
#
# One run per seed, in clear air. `exit_times` tells the map which agents
# left, so that an agent still inside at the end of a run marks its cell as
# censored instead of passing it.

# %%
scenario = load_scenario("assets/iso_table22_coupled/config_a.json")
spawn = scenario.distributions["jps-distributions_0"]
spawn["coordinates"] = [[1, 1], [1, 5], [5, 5], [5, 1], [1, 1]]
spawn["parameters"].update(number=20, use_premovement=False)

rsets, grid = [], None
for seed in SEEDS:
    result = run_scenario(scenario, seed=seed)
    trajectory, walkable = load_trajectory(result.sqlite_file)
    grid = grid or grid_from_walkable(walkable, CELL)
    rsets.append(rset_map(trajectory, walkable, grid, exit_times=result.exit_times))
    print(
        f"seed {seed}: {len(result.exit_times)} left, remaining {result.agents_remaining}"
    )
    result.cleanup()
assert grid is not None

# %% [markdown]
# ## DIFF per seed, and pooled
#
# The 95th-percentile RSET map over the seeds is the pooled map. The failing
# area and C of each seed come with a bootstrap interval; three seeds are only
# enough to run the example, not for a result.

# %%
aset = aset_map(grid, crossings)
per_seed = [measures(diff_map(aset, rset, grid)) for rset in rsets]
for name, interval in seed_measures(per_seed).items():
    print(
        f"{name}: mean {interval.mean:.2f}, 95 % CI {interval.low:.2f} to {interval.high:.2f}"
    )

pooled, pooled_values = pool_rset(rsets, "p95")
diff = diff_map(aset, pooled, grid)
m = measures(diff)
print(
    f"ASET {np.nanmin(aset.time_s):.0f} s everywhere on {int(grid.area.astype(bool).sum())} cells"
)
print(
    f"pooled RSET ({pooled_values.label}): last cell empty at {np.nanmax(pooled.time_s):.1f} s"
)
print(
    f"min DIFF {m.min_diff_s:.1f} s, failing area {m.fail_area_m2:.2f} m2, C {m.c_m2s:.1f} m2 s"
)
print(f"cells by state: { {k: v for k, v in m.counts.items() if v} }")

# %% [markdown]
# ## Plot the maps
#
# `plot_maps` draws the three maps; failing cells are hatched, cells nobody
# visited are grey. With one criterion there is no deciding-criterion panel.

# %%
fig = plot_maps(grid, aset, pooled, diff, walkable=walkable, deciding=False)
fig.text(
    0.5,
    -0.02,
    "FED map: a person standing still from t = 0 at 1.5 m. Not the dose of a walk.",
    ha="center",
    color="dimgrey",
)
FIGURE.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(FIGURE, dpi=150, bbox_inches="tight")
print(f"figure: {FIGURE}")
