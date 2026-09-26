# %% [markdown]
# # Quickstart: one corridor, with and without smoke
#
# Runs `assets/ISO-table21` (one agent, 100 m corridor) twice: once in clear
# air and once in a uniform extinction coefficient K [1/m]. No FDS output is
# needed. Run from the repository root:
#
#     uv run python examples/quickstart.py

# %%
from pyfds_evac import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)

K_PER_M = 3.0  # extinction coefficient K [1/m]; visibility S = 3/K = 1 m

# %% [markdown]
# ## Run in clear air

# %%
scenario = load_scenario("assets/ISO-table21")
clear = run_scenario(scenario, seed=420)
print(f"clear air:   {clear.evacuation_time:.2f} s")

# %% [markdown]
# ## Run in smoke

# %%
smoke = SmokeSpeedModel(ConstantExtinctionField(K_PER_M), SmokeSpeedConfig())
smoky = run_scenario(scenario, seed=420, smoke_speed_model=smoke)
print(f"K = {K_PER_M} 1/m: {smoky.evacuation_time:.2f} s")

# %% [markdown]
# ## Check the speed factor and find the run manifest

# %%
factor = smoky.smoke_history[-1]["speed_factor"]
print(f"speed factor in smoke: {factor:.4f}")
print(f"time ratio smoke/clear: {smoky.evacuation_time / clear.evacuation_time:.4f}")
print(f"manifest: {smoky.manifest_file}")

# %% [markdown]
# ## Clean up the temporary trajectory and manifest files

# %%
clear.cleanup()
smoky.cleanup()
