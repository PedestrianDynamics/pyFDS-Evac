# %% [markdown]
# # First real FDS case: a T-junction with a fire
#
# Runs `assets/t_junction` (150 agents, two exits) in the fire that FDS
# computed for the deck `assets/t_junction/t_junction.fds`. Without an FDS
# output directory it runs the same scenario in clear air. Run from the
# repository root:
#
#     uv run python examples/first_fds_case.py                  # clear air
#     uv run python examples/first_fds_case.py <fds-output-dir> # fire
#
# It is the Python equivalent of
# `run.py --scenario assets/t_junction [--fds-dir <fds-output-dir>]`:
# `build_run_kwargs` is the function `run.py` calls.

# %%
import sys
from collections import Counter
from types import SimpleNamespace

from pyfds_evac import build_run_kwargs, load_scenario, run_scenario

FDS_DIR = sys.argv[1] if len(sys.argv) > 1 else None

# %% [markdown]
# ## Run

# %%
scenario = load_scenario("assets/t_junction")
opts = SimpleNamespace(
    seed=None,  # the scenario's baseSeed, 42
    fds_dir=FDS_DIR,
    constant_extinction=None,
    smoke_update_interval=1.0,
    smoke_slice_height=1.6,
    disable_tenability=False,
    fed_threshold=1.0,
    fic_alpha=0.7,
    fic_min_factor=0.3,
    enable_rerouting=True,
    reroute_interval=1.0,
    vis_cache=None,
)
result = run_scenario(scenario, **build_run_kwargs(scenario, opts))

print(f"evacuated: {result.agents_evacuated}/{result.total_agents} in 300 s")
if FDS_DIR is not None:
    print(f"FED max:   {result.metrics['fed_max']:.2f}")
    reasons = Counter(r["reason"] for r in result.route_history)
    print(f"route history rows by reason: {dict(reasons)}")

# %%
result.cleanup()  # deletes the temporary trajectory file; copy it first to keep it
