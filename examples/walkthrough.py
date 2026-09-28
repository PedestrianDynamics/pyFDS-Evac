# %% [markdown]
# # Real-FDS walkthrough
#
# Reads the FDS output tracked in the repository. FDS itself is not run.
#
# - `assets/iso_table21_coupled/fds`: extinction coefficient only. It drives
#   the smoke-speed model for one agent walking a 100 m corridor.
# - `assets/iso_table22_coupled/fds/a`: CO, CO2, O2 and extinction. It drives
#   the FED model for one occupant held still in a 10 m x 10 m room.
#
# The last part removes the CO slice from a copy of the second case and shows
# that the run still finishes. Run from the repository root:
#
#     uv run python examples/walkthrough.py

# %%
import json
import pathlib
import shutil
import tempfile
from types import SimpleNamespace

from pyfds_evac import (
    DefaultFedConfig,
    DefaultFedModel,
    ExtinctionField,
    FdsFedField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    TenabilityConfig,
    build_run_kwargs,
    load_scenario,
    run_scenario,
)

SMOKE_DIR = "assets/iso_table21_coupled/fds"
GAS_DIR = "assets/iso_table22_coupled/fds/a"

# %% [markdown]
# ## 1. Smoke: extinction from FDS slows the walk

# %%
corridor = load_scenario("assets/iso_table21_coupled")
clear = run_scenario(corridor, seed=420)

extinction = ExtinctionField.from_fds(SMOKE_DIR)
smoke = SmokeSpeedModel(extinction, SmokeSpeedConfig())
smoky = run_scenario(corridor, seed=420, smoke_speed_model=smoke)

row = smoky.smoke_history[-1]
print(f"K sampled:    {row['extinction_per_m']:.5f} 1/m")
print(f"speed factor: {row['speed_factor']:.6f}")
print(
    f"exit time:    {clear.evacuation_time:.2f} s clear, "
    f"{smoky.evacuation_time:.2f} s in smoke"
)

manifest = json.loads(pathlib.Path(smoky.manifest_file).read_text())
print(f"manifest: fds_dir={manifest['fds_dir']}")
print(f"          fds_version={manifest['fds_version']}")

# %% [markdown]
# ## 2. Gas: FED from FDS CO, CO2 and O2 slices

# %%
room = load_scenario("assets/iso_table22_coupled/config_a.json")
fed = DefaultFedModel(FdsFedField.from_fds(GAS_DIR), DefaultFedConfig())
tenability = TenabilityConfig(incapacitation_mode="deterministic")
exposed = run_scenario(room, seed=420, fed_model=fed, tenability_config=tenability)

for row in exposed.fed_history[::200]:
    print(
        f"t={row['time_s']:6.0f} s  CO={row['co_percent']:.3f} %  "
        f"FED={row['fed_cumulative']:.3f}"
    )
crossing = next(r for r in exposed.fed_history if r["fed_cumulative"] >= 1.0)
print(
    f"FED >= 1 at t = {crossing['time_s']:.0f} s; "
    f"incapacitated: {exposed.fed_history[-1]['incapacitated']}"
)
print(f"FED max: {exposed.metrics['fed_max']:.3f}")

# %% [markdown]
# ## 3. Successful but wrong: the same case without its CO slice

# %%
broken = pathlib.Path(tempfile.mkdtemp()) / "a"
shutil.copytree(GAS_DIR, broken, ignore=shutil.ignore_patterns("*.pickle"))
for path in broken.glob("iso_table22_a_1_1.sf*"):  # the CO slice
    path.unlink()
smv = broken / "iso_table22_a.smv"
lines = smv.read_text().splitlines(keepends=True)
start = next(i for i, line in enumerate(lines) if "iso_table22_a_1_1.sf" in line) - 1
smv.write_text("".join(lines[:start] + lines[start + 5 :]))

# %% [markdown]
# Built by hand, the FED field fails loudly:

# %%
try:
    FdsFedField.from_fds(str(broken))
except IndexError as error:
    print(f"FdsFedField.from_fds: IndexError: {error}")

# %% [markdown]
# Built through `build_run_kwargs` (what `run.py` and the web GUI call), the
# run goes ahead without FED:

# %%
opts = SimpleNamespace(
    seed=420,
    fds_dir=str(broken),
    constant_extinction=None,
    smoke_update_interval=1.0,
    smoke_slice_height=2.0,
    disable_tenability=False,
    fed_threshold=1.0,
    fic_alpha=0.7,
    fic_min_factor=0.3,
    incapacitation_mode="deterministic",
    enable_rerouting=False,
    reroute_interval=1.0,
    vis_cache=None,
)
kwargs = build_run_kwargs(room, opts)
silent = run_scenario(room, **kwargs)
print(
    f"finished at {silent.evacuation_time:.0f} s, "
    f"{silent.agents_remaining} agent still in the room"
)

# %% [markdown]
# ## 4. Detect it: before and after the run

# %%
print(f"before: fed_model = {kwargs['fed_model']}")
print(
    f"after:  fed_history = {silent.fed_history}, "
    f"'fed_max' in metrics = {'fed_max' in silent.metrics}"
)

# %%
for result in (clear, smoky, exposed, silent):
    result.cleanup()
shutil.rmtree(broken.parent)
