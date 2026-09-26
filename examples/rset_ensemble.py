# %% [markdown]
# # Egress time and its spread from an ensemble of seeds
#
# Part 1 runs `assets/fic_vs_fed_speed` (30 agents, one exit, clear air) once
# per seed. It reads each agent's exit time from the trajectory file and
# summarises the last exit over the seeds. Five seeds keep this example fast;
# use many more for a study.
#
# Part 2 runs one occupant held in the CO/CO2/O2 room of
# `assets/iso_table22_coupled` until incapacitation, to show why
# `result.evacuation_time` is not an egress time.
#
# Run from the repository root:
#
#     uv run python examples/rset_ensemble.py

# %%
import json
import pathlib
import sqlite3

import numpy as np
from matplotlib.figure import Figure

from pyfds_evac import (
    DefaultFedConfig,
    DefaultFedModel,
    FdsFedField,
    TenabilityConfig,
    load_scenario,
    run_scenario,
)

SEEDS = [1, 2, 3, 4, 5]
FIGURE = pathlib.Path("site/static/images/howto/egress_exit_curve.png")
COLOURS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9"]  # Okabe-Ito
LINESTYLES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1, 1, 1))]


# %% [markdown]
# ## Read exit times from the trajectory


# %%
def exit_times(result):
    """Exit time [s] of every agent that left, from the trajectory file."""
    con = sqlite3.connect(result.sqlite_file)
    try:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()[0]
        )
        last = con.execute("SELECT MAX(frame) FROM trajectory_data GROUP BY id")
        times = sorted(frame / fps for (frame,) in last)
    finally:
        con.close()
    # Agents still inside at the end are the ones seen in the last frames.
    return times[: len(times) - result.agents_remaining]


def incapacitated(result):
    """Number of agents incapacitated during the run."""
    rows = result.fed_history or []
    return len({row["agent_id"] for row in rows if row["incapacitated"]})


# %% [markdown]
# ## Part 1: clear air, one run per seed

# %%
scenario = load_scenario("assets/fic_vs_fed_speed")
for name, dist in scenario.distributions.items():
    params = dist["parameters"]
    print(
        f"{name}: {params['number']} agents, "
        f"use_premovement={params.get('use_premovement', False)}"
    )

curves = {}
for seed in SEEDS:
    result = run_scenario(scenario, seed=seed)
    manifest = json.loads(pathlib.Path(result.manifest_file).read_text())
    curves[manifest["seed"]] = exit_times(result)
    print(
        f"seed {manifest['seed']}: last exit {curves[seed][-1]:.1f} s, "
        f"evacuated {len(curves[seed])}, incapacitated {incapacitated(result)}, "
        f"remaining {result.agents_remaining}"
    )
    result.cleanup()
print(f"versions: {manifest['versions']}")
print(f"git: {manifest['git_commit']}, dirty: {manifest['git_dirty']}")

# %% [markdown]
# ## Summarise the last exit over the seeds

# %%
last = np.array([times[-1] for times in curves.values()])
print(f"n = {len(last)} seeds")
print(f"mean = {last.mean():.1f} s, SD = {last.std(ddof=1):.1f} s")
print(f"min-max = {last.min():.1f}-{last.max():.1f} s")
print(f"95th percentile = {np.percentile(last, 95):.1f} s")

# %% [markdown]
# ## Plot the exit curves

# %%
fig = Figure(figsize=(6, 4))
ax = fig.subplots()
for (seed, times), colour, style in zip(curves.items(), COLOURS, LINESTYLES):
    counts = np.arange(1, len(times) + 1)
    ax.step(times, counts, where="post", color=colour, ls=style, label=f"seed {seed}")
ax.axvspan(last.min(), last.max(), color="lightgrey", alpha=0.5, lw=0)
ax.text(
    last.min() - 0.3,
    2,
    f"last exit {last.min():.1f}-{last.max():.1f} s\nover {len(last)} seeds",
    color="dimgrey",
    ha="right",
)
ax.grid(color="lightgrey", linewidth=0.8)
ax.set_axisbelow(True)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.tick_params(length=0, labelcolor="dimgrey")
ax.set_xlabel("time since start of simulation [s]", color="dimgrey")
ax.set_ylabel("agents evacuated [-]", color="dimgrey")
ax.legend(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)
FIGURE.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(FIGURE, dpi=150, bbox_inches="tight")
print(f"figure: {FIGURE}")

# %% [markdown]
# ## Part 2: an incapacitated agent and `evacuation_time`

# %%
room = load_scenario("assets/iso_table22_coupled/config_a.json")
gas_dir = "assets/iso_table22_coupled/fds/a"
fed = DefaultFedModel(FdsFedField.from_fds(gas_dir), DefaultFedConfig())
tenability = TenabilityConfig(incapacitation_mode="deterministic")
fire = run_scenario(room, seed=420, fed_model=fed, tenability_config=tenability)
print(
    f"evacuation_time {fire.evacuation_time:.0f} s "
    f"(max_simulation_time {room.max_simulation_time:.0f} s), "
    f"success {fire.success}"
)
print(
    f"exit times {exit_times(fire)}, incapacitated {incapacitated(fire)}, "
    f"remaining {fire.agents_remaining}"
)
fire.cleanup()
