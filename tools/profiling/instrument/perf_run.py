"""Run run.py with opt-in observational hooks installed (G1).

Usage (cwd = the fds-evac worktree, same arguments as run.py):
    PYFDS_PERF_COUNTERS_OUT=counters.json python perf_run.py <run.py args>
    PYFDS_PERF_RESULT_OUT=result.json     python perf_run.py <run.py args>

PYFDS_PERF_COUNTERS_OUT installs the aggregate counters (perf_counters.py).
PYFDS_PERF_RESULT_OUT saves ScenarioResult.cognitive_map_history and
ScenarioResult.metrics as JSON (floats in repr form) for the model §3
equivalence check; the CLI does not write them. Both are independent.
PYFDS_PERF_MEMO_LOG=path writes the FED-rate memo debug line (hits, misses, clears) of
pyfds_evac.core.scenario to that file (G5 counters runs).
PYFDS_PERF_STUB=nss,nst installs the G3 removal stubs (plan.md D36): nss
returns a neutral ambient value from SliceFieldSampler.sample after the
horizon check (0.209 for the oxygen volume fraction, 0.0 for every other
quantity; route-cost line-of-sight still reads the slice through line_parts
and read_cells, which the stub does not touch); nst reduces reached_stage to
the point-distance test. Both change trajectories; runs with a stub are end-to-end arms, never baselines.
nlk (G8) patches the pre-change SliceFieldSampler.sample back in (two numpy
lookups per read instead of the shared lookup); it changes no value, so a
run with nlk follows the same trajectory.
nrp (G11) patches the pre-change reached_stage back in (the exact polygon distance for every exit test instead of
the bounds pre-test); it changes no decision, so a run with nrp follows the same trajectory.
With neither variable set nothing is installed; this entry point is still
not the overhead baseline (that is plain run.py).
"""

import json
import os
import pathlib
import runpy
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, os.getcwd())
counters_out = os.environ.get("PYFDS_PERF_COUNTERS_OUT")
result_out = os.environ.get("PYFDS_PERF_RESULT_OUT")
memo_log = os.environ.get("PYFDS_PERF_MEMO_LOG")
STUBS = ("nss", "nst", "nlk", "nrp")
AMBIENT_O2_FRACTION = 0.209


def _stub_sample(self, time_s, x, y):
    """nss (#242): keep the horizon rule, skip subslice lookup, index search and data read.

    Returns the neutral value of the sampler's quantity: ambient oxygen (0 would
    put every agent at 0 % O2 and incapacitate it), 0.0 for the rest.
    """
    self._time_index(float(time_s))
    neutral = self.__dict__.get("_stub_neutral")
    if neutral is None:
        quantity = str(getattr(self, "quantity", "")).upper()
        neutral = AMBIENT_O2_FRACTION if quantity.startswith("OXYGEN") else 0.0
        self._stub_neutral = neutral
    return neutral


def _legacy_sample(self, time_s, x, y):
    """nlk (#242): SliceFieldSampler.sample as before the shared point lookup (d96894ac).

    Two numpy searchsorted calls per read. The value, the horizon rule and the error for a point
    outside the slice are those of the shared lookup, so outputs are identical and only the cost differs.
    """
    ts = float(time_s)
    if ts != self._cached_time_s:
        self._cached_t_index = self._time_index(ts)
        self._cached_time_s = ts
    t_index = self._cached_t_index
    subslice = self._find_subslice(float(x), float(y))
    if subslice is None:
        raise ValueError(f"Point ({x}, {y}) is outside the sampled FDS slice domain")
    xs, ys = self._axes(subslice)
    i_index = self._nearest_index(xs, float(x))
    j_index = self._nearest_index(ys, float(y))
    return float(subslice.data[t_index, i_index, j_index])


def install_stubs(names):
    """Patch the frozen application in-process; names are a subset of STUBS."""
    for name in names:
        if name not in STUBS:
            raise SystemExit(f"perf_run.py: unknown stub {name}")
    if "nss" in names:
        import pyfds_evac.core.fds_sampling as fds_sampling

        fds_sampling.SliceFieldSampler.sample = _stub_sample
    if "nlk" in names:
        import pyfds_evac.core.fds_sampling as fds_sampling

        fds_sampling.SliceFieldSampler.sample = _legacy_sample
    if "nrp" in names:
        import math

        import pyfds_evac.core.direct_steering_runtime as dsr
        import pyfds_evac.core.scenario as scenario_mod

        def _legacy_reached_stage(x, y, target, stage_cfg, agent_radius):
            """nrp (#429): reached_stage as before the exit bounds pre-test (c2216523).

            The exact polygon distance for every exit test. The answers equal those of the pruned version, so outputs are identical and only the cost differs.
            Modules are bound at install time (the function runs once per agent step); dsr attributes are read at call time so the counters hooks still wrap them.
            """
            stage_cfg = stage_cfg or {}
            polygon = stage_cfg.get("polygon")
            stage_type = stage_cfg.get("stage_type", "checkpoint")
            if stage_type == "exit" and polygon is not None:
                return dsr.distance_to_polygon(x, y, polygon) <= dsr.EXIT_REACH_TOLERANCE_M
            if target is not None:
                reach_dist = float(agent_radius) + dsr.TARGET_REACH_MARGIN_M
                if math.hypot(x - float(target[0]), y - float(target[1])) <= reach_dist:
                    return True
            return stage_type == "checkpoint" and dsr.is_inside_polygon(x, y, polygon)

        dsr.reached_stage = _legacy_reached_stage
        scenario_mod.reached_stage = _legacy_reached_stage
    if "nst" in names:
        import math

        import pyfds_evac.core.direct_steering_runtime as dsr
        import pyfds_evac.core.scenario as scenario_mod

        margin = dsr.TARGET_REACH_MARGIN_M

        def _stub_reached_stage(x, y, target, stage_cfg, agent_radius):
            """nst (#429): point-distance test only; no polygon distance, no shapely."""
            if target is None:
                return False
            reach = float(agent_radius) + margin
            return math.hypot(x - float(target[0]), y - float(target[1])) <= reach

        dsr.reached_stage = _stub_reached_stage
        scenario_mod.reached_stage = _stub_reached_stage


def install_memo_log(path):
    """Write the FED-rate memo debug line of pyfds_evac.core.scenario to *path*.

    The CLI configures no logging, so the line would otherwise be dropped; only this
    logger's level changes, the root logger stays at WARNING. The logger's other DEBUG
    records (reroute traces) are filtered out so the file holds the memo line alone.
    """
    import logging

    handler = logging.FileHandler(path, mode="w")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(lambda record: record.getMessage().startswith("FED-rate memo:"))
    logger = logging.getLogger("pyfds_evac.core.scenario")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)


stub_names = [s for s in os.environ.get("PYFDS_PERF_STUB", "").split(",") if s]
if stub_names:
    install_stubs(stub_names)
if memo_log:
    install_memo_log(memo_log)
if counters_out:
    import perf_counters

    perf_counters.install(counters_out)
if result_out:
    import pyfds_evac.core as core_pkg

    _inner = core_pkg.run_scenario

    def _capture(*a, **k):
        res = _inner(*a, **k)
        with open(result_out, "w") as f:
            json.dump({"cognitive_map_history": res.cognitive_map_history,
                       "metrics": res.metrics}, f, indent=0, default=repr)
        return res

    # The CLI resolves run_scenario from pyfds_evac.core.scenario (cli.py lazy names),
    # not from the package attribute: patch the module the call goes through as well.
    import pyfds_evac.core.scenario as scenario_mod

    scenario_mod.run_scenario = _capture
    core_pkg.run_scenario = _capture
sys.argv = ["run.py", *sys.argv[1:]]
runpy.run_path(str(pathlib.Path.cwd() / "run.py"), run_name="__main__")
