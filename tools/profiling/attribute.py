#!/usr/bin/env python3
"""Per-issue attribution tables from the raw files of a G2 block.

Run from the package directory with the baseline interpreter:

    attribute.py --block <block> --out <dir>      attribution_<block>_<case>.csv per case
    attribute.py --rc-diff <block> --out <dir>    rc_diff_<block>.csv (cProfile O_study vs O_norc)
    attribute.py --counters <block> --out <dir>   counters_<block>.csv (one row per counters run)
    attribute.py --removal <block> --counters-block <block> --out <dir> [--exclude RUN_ID ...]
                  [--rerun-block <block> --rerun-counters-block <block>]
                                                  removal_<block>.csv (G3, one row per arm)
    attribute.py --route-paths <block> --out <dir>
                                                  route_paths_<block>.csv (G4, one row per path)
    attribute.py --equality <block> --out <dir> [--exclude RUN_ID ...]
                                                  equality_<block>.csv (G5, one row per seed)
    attribute.py --paired <block> --counters-block <block> --out <dir> [--exclude RUN_ID ...]
                                                  paired_<block>.csv (G5, one row per seed, ALL row = D40)
    attribute.py --paired-removal <block> --arm <variant> --counters-block <block> --out <dir>
                  [--exclude RUN_ID ...]
                                                  paired_removal_<block>_<arm>.csv (G6, one row per seed, ALL row = D41)
    attribute.py --paired-lookup <block> --arm nlk|nrp --counters-block <block> --out <dir>
                  [--exclude RUN_ID ...]
                                                  paired_lookup_<block>_<arm>.csv (G8 nlk, G11 nrp, one row per seed,
                                                  ALL row = D42 / D43)
    attribute.py --memo-counters <block> --out <dir>
                                                  memo_counters_<block>.csv (G5, one row per counters rep)
    attribute.py --reroute-tree <block> --out <dir> [--exclude RUN_ID ...]
                                                  reroute_tree_<block>.csv (G13, one row per call path at or
                                                  below the two rerouting entry points, scaled to the plain wall)
    attribute.py --repeat-ceiling <block> --tree <reroute_tree.csv> --out <dir> [--exclude RUN_ID ...]
                                                  repeat_ceiling_<block>.csv (G14, one row per seed and path:
                                                  exact repeat share times the path's cost from the G13 tree)

Exit 0 on success; exit 2 with a message naming what is missing; --equality and --paired-lookup
exit 3 when a pair of runs differs (the table is written first).

removal_*.csv compares each arm with the O_norc of its block: diff_s is the
O_norc median minus the arm median; the tie rule uses the interquartile range
of the exclusive-method ``statistics.quantiles`` (n=4), which on five reps is
wider than the inclusive method. A rerun block (G3b) replaces the arms it
contains and compares them with its own O_norc; ``source_block`` names the
block each row's arm and baseline come from.

attribution_*.csv, one row per (subsystem, function) and a ``TOTAL`` row per
subsystem; all seconds are medians over the profiled reps of per-run sums:

    cum_s            inclusive pyinstrument time of the subsystem's frames
    self_s           time in those frames minus the time of their Python children;
                     the frame's own ``[self]`` child and its ``<built-in>`` (C call)
                     children count as the frame's own time
    share_profiled  cum_s / profiled_wall_s
    agreement_pts   (max - min) over the profiled reps of cum_s / wall_s, times 100;
                    blank with a single profiled rep
    profiled_wall_s, plain_wall_s   medians of metrics.wall_s over the profiled / plain reps
    overhead_bound_s                profiled_wall_s - plain_wall_s
    cost_plain_s     cum_s * plain_wall_s / profiled_wall_s
    status           observed when cum_s > 0, else not_observed

No double counting: the ``cum_s`` of a subsystem's TOTAL sums only matching
frames that have no matching ancestor of the same subsystem; the ``cum_s`` of
a function row skips frames that have an ancestor with the same subsystem and
function name; ``self_s`` is additive. The rule holds within a subsystem only:
a frame can match two subsystems (``sample`` below ``evaluate_segment`` is in
route_segments and slice_sampling, shapely below ``distance_to_polygon`` in
steering_exit_test), so TOTAL rows of different subsystems overlap and must
not be summed. pyinstrument sees Python frames only:
native time (NumPy, shapely, fdsreader) lands on the calling Python frame, so
the map attributes by caller module. cProfile inflates small-function costs;
rc_diff_*.csv locates the route-cost history and carries no wall-time saving.
Warm-up runs are never used.
"""
import argparse
import csv
import hashlib
import json
import os
import pstats
import re
import statistics
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent / "results" / "raw"

# Subsystem map, reviewed against pyfds_evac/core in the frozen worktree
# (commit 8f7d29a2). ``file`` is a path suffix, or a directory marker when it
# ends with "/". ``nested_only`` entries match only below a frame of the same
# subsystem (native frames reached from the named Python callers).
ISSUE_MAP = [
    {"subsystem": "vismap_build", "issues": ("#236", "#241"), "file": "visibility.py",
     "functions": ("_build_cache_from_fds", "_vis_metre_array")},
    {"subsystem": "vismap_build", "issues": ("#236", "#241"), "file": "fdsvismap/",
     "functions": ()},
    # SliceFieldSampler.sample also serves per-agent moving-point sampling
    # (smoke_speed.py, fed.py), so TOTAL is a loose bound for #242;
    # _find_subslice and _nearest_index are the tighter rows.
    {"subsystem": "slice_sampling", "issues": ("#242",), "file": "fds_sampling.py",
     "functions": ("sample", "_find_subslice", "_nearest_index")},
    {"subsystem": "route_segments", "issues": ("#243",), "file": "route_graph.py",
     "functions": ("rank_routes", "_generate_candidates", "evaluate_segment")},
    {"subsystem": "route_segments", "issues": ("#243",), "file": "scenario.py",
     "functions": ("_assign_initial_exit",)},
    # The flow-spawn loop is inline in scenario.run_scenario (no own frame);
    # its callees are the frames below. The loop's own work, and callees such
    # as create_agent_parameters that initial placement shares, are not
    # mapped: TOTAL is a lower bound for #739.
    {"subsystem": "flow_spawn", "issues": ("#739",), "file": "simulation_init.py",
     "functions": ("_crowds_agents", "_occupied")},
    {"subsystem": "steering_exit_test", "issues": ("#429",), "file": "direct_steering_runtime.py",
     "functions": ("reached_stage", "distance_to_polygon")},
    {"subsystem": "steering_exit_test", "issues": ("#429",), "file": "shapely/",
     "functions": (), "nested_only": True},
    {"subsystem": "route_cost_history", "issues": ("rc",), "file": "run_outputs.py",
     "functions": ("_write_route_cost_history_csv",)},
]

ATTRIBUTION_COLUMNS = ["block", "case", "variant", "subsystem", "issues", "function", "file",
                       "n_profiled", "n_plain", "cum_s", "self_s", "share_profiled",
                       "agreement_pts", "profiled_wall_s", "plain_wall_s", "overhead_bound_s",
                       "cost_plain_s", "status"]
RC_DIFF_COLUMNS = ["function", "file", "cum_s_O_study", "cum_s_O_norc", "delta_cum_s",
                   "self_s_O_study", "self_s_O_norc", "delta_self_s", "ncalls_O_study",
                   "ncalls_O_norc"]
COUNTERS_COLUMNS = ["run_id", "case", "agent_steps", "iterations", "loop_s", "setup_s",
                    "total_s", "us_per_agent_step", "reroute_evaluations",
                    "evaluate_route_calls", "rank_routes_calls", "fdsreader_full_parse"]
USABLE = ("completed", "flows_closed", "incomplete_time_limit")
REMOVAL_ARMS = ("O_norc", "nrr", "nss", "nst")
ARM_ISSUE = {"O_norc": "baseline", "nrr": "#243", "nss": "#242", "nst": "#429"}
REMOVAL_BAR_S = 23.0
REMOVAL_COLUMNS = ["arm", "issue", "n_reps", "n_flagged", "n_used", "wall_s_median", "wall_s_q1",
                   "wall_s_q3", "agent_steps_median", "us_per_agent_step", "diff_s",
                   "diff_per_study_s", "diff_us_per_agent_step", "bar_s", "verdict", "source_block"]
RC_DIFF_ROWS = 60
RC_MUST_INCLUDE = ("_write_route_cost_history_csv",)
TOTAL = "TOTAL"
ROUTE_PATHS_COLUMNS = ["run_id", "path", "calls", "seconds", "overhead_s", "net_seconds", "total",
                       "distinct", "hit_share", "avoidable_s", "avoidable_per_study_s", "capped"]
ROUTE_PATHS = ("evaluate_segment", "first_leg", "cell_los_stats", "step_los_stats", "read_cells",
               "line_parts", "sample_fed_rate", "sample_route")
KEYED_PATHS = ("read_cells", "sample_fed_rate", "sample_route")
MEMO_ARMS = ("O_norc", "nomemo")       # G5: memo at its default, memo off
EQUALITY_FILES = ("exit.csv", "rh.csv")
EQUALITY_COLUMNS = ["seed", "memo_run_id", "nomemo_run_id", "exit_csv_equal", "rh_csv_equal"]
PAIRED_COLUMNS = ["seed", "memo_run_id", "nomemo_run_id", "wall_memo_s", "wall_nomemo_s", "d_s",
                  "flagged_memo", "flagged_nomemo", "outputs_equal", "n_seeds", "n_seeds_dropped",
                  "median_d_s", "iqr_d_s", "diff_per_study_s", "sum_d_s", "agent_steps_median",
                  "d_us_per_agent_step", "verdict"]
PAIRED_REMOVAL_COLUMNS = ["seed", "base_run_id", "arm_run_id", "wall_base_s", "wall_arm_s", "d_s",
                          "flagged_base", "flagged_arm", "sim_time_base_s", "sim_time_arm_s",
                          "evacuated_base", "evacuated_arm", "n_seeds", "n_seeds_dropped",
                          "median_d_s", "iqr_d_s", "diff_per_study_s", "sum_d_s", "agent_steps_median",
                          "d_us_per_agent_step", "verdict"]
LOOKUP_BASE = "O_norc"                           # G8/G11: default code ...
LOOKUP_VARIANTS = ("nlk", "nrp")                 # ... vs the pre-change code patched in by the wrapper
LOOKUP_EQUALITY_FILES = ("exit.csv", "rh.csv", "fed.csv")
PAIRED_LOOKUP_COLUMNS = ["seed", "base_run_id", "arm_run_id", "wall_base_s", "wall_arm_s", "d_s",
                         "flagged_base", "flagged_arm", "outputs_equal", "n_seeds", "n_seeds_dropped",
                         "median_d_s", "iqr_d_s", "diff_per_study_s", "sum_d_s", "agent_steps_median",
                         "d_us_per_agent_step", "verdict"]
MEMO_COUNTERS_COLUMNS = ["run_id", "variant", "agent_steps", "hits", "misses", "clears", "hit_share"]
MEMO_LINE = re.compile(r"FED-rate memo: (\d+) hits, (\d+) misses, (\d+) clears")
STUDY_RUNS = 10
REROUTE_ENTRIES = (("evaluate_and_reroute", "route_graph.py"), ("_assign_initial_exit", "scenario.py"))
REROUTE_MIN_SHARE = 0.01
REROUTE_TREE_COLUMNS = ["block", "entry", "path", "depth", "function", "file", "n_profiled", "n_plain",
                        "cum_s", "self_s", "share_profiled", "agreement_pts", "profiled_wall_s",
                        "plain_wall_s", "cost_plain_s", "cost_per_study_s", "verdict"]
REPEAT_PATHS = ("first_leg", "first_leg_dose", "segment", "first_leg_r01")
REPEAT_COST_FUNCTION = {"first_leg": "_first_leg", "first_leg_dose": "_first_leg_dose",
                        "segment": "evaluate_segment", "first_leg_r01": "_first_leg"}
REPEAT_CEILING_COLUMNS = ["run_id", "seed", "path", "total", "distinct", "hit_share", "capped",
                          "cost_per_study_s", "ceiling_per_study_s", "verdict"]


class AttributionError(Exception):
    """A block lacks what the requested table needs."""


def load_tree(path) -> dict:
    with open(path) as fh:
        return json.load(fh)


def _matches(entry, frame, in_subsystem) -> bool:
    if entry.get("nested_only") and entry["subsystem"] not in in_subsystem:
        return False
    if entry["functions"] and frame["function"] not in entry["functions"]:
        return False
    path = "/" + str(frame.get("file_path", "")).lstrip("/")
    if entry["file"].endswith("/"):
        return "/" + entry["file"] in path
    return path.endswith("/" + entry["file"])


def _is_own_time(child) -> bool:
    """pyinstrument's ``[self]`` node and ``<built-in>`` C calls belong to the caller."""
    return child["function"] == "[self]" or child.get("file_path") == "<built-in>"


def _zero_rows(issue_map) -> dict:
    rows = {}
    for entry in issue_map:
        rows.setdefault((entry["subsystem"], TOTAL), {"cum_s": 0.0, "self_s": 0.0})
        for function in entry["functions"]:
            rows.setdefault((entry["subsystem"], function), {"cum_s": 0.0, "self_s": 0.0})
    return rows


def attribute_tree(root_frame: dict, issue_map) -> dict:
    """Cumulative and self seconds per (subsystem, function) and per subsystem TOTAL."""
    rows = _zero_rows(issue_map)
    stack = [(root_frame, frozenset(), frozenset())]
    while stack:
        frame, subsystems, functions = stack.pop()
        children = frame.get("children", [])
        python_time = sum(child["time"] for child in children if not _is_own_time(child))
        self_s = max(0.0, frame["time"] - python_time)
        hit = {}
        for entry in issue_map:
            if entry["subsystem"] not in hit and _matches(entry, frame, subsystems):
                hit[entry["subsystem"]] = entry
        for subsystem in hit:
            key = (subsystem, frame["function"])
            row = rows.setdefault(key, {"cum_s": 0.0, "self_s": 0.0})
            if key not in functions:
                row["cum_s"] += frame["time"]
            row["self_s"] += self_s
            total = rows[(subsystem, TOTAL)]
            if subsystem not in subsystems:
                total["cum_s"] += frame["time"]
            total["self_s"] += self_s
        below_subsystems = subsystems | frozenset(hit)
        below_functions = functions | frozenset((s, frame["function"]) for s in hit)
        stack.extend((child, below_subsystems, below_functions) for child in children)
    return rows


def counters_summary(path) -> dict:
    data = load_tree(path)
    timers, counters = data.get("timers_s", {}), data.get("counters", {})
    agent_steps = counters.get("agent_steps", 0)
    loop_s = timers.get("loop_first_iterate_to_last_iterate_end")
    return {
        "agent_steps": agent_steps,
        "iterations": counters.get("iterations", 0),
        "loop_s": loop_s,
        "setup_s": timers.get("run_scenario_setup_before_first_iterate"),
        "total_s": timers.get("run_scenario_total"),
        "us_per_agent_step": loop_s / agent_steps * 1e6 if loop_s is not None and agent_steps else None,
        "reroute_evaluations": counters.get("reroute_evaluations", 0),
        "evaluate_route_calls": counters.get("evaluate_route_calls", 0),
        "rank_routes_calls": counters.get("rank_routes_calls", 0),
        "fdsreader_full_parse": counters.get("fdsreader_full_parse", 0),
    }


def _cprofile_table(path) -> dict:
    table = {}
    for (file, _line, func), (_cc, nc, tt, ct, _callers) in pstats.Stats(str(path)).stats.items():
        row = table.setdefault((func, os.path.basename(file)), [0, 0.0, 0.0])
        row[0] += nc
        row[1] += tt
        row[2] += ct
    return table


def cprofile_diff(a_path, b_path, must_include=()) -> list:
    """Rows of profile *a* against profile *b*, sorted by cumulative-time difference.

    The first RC_DIFF_ROWS rows plus every row whose function is in *must_include*.
    Rows join on (function, file basename), so same-named functions of different
    packages (``__init__`` in ``__init__.py``) merge; the rows that matter here
    are unique. Raises AttributionError when a *must_include* name is in neither
    profile.
    """
    first, second = _cprofile_table(a_path), _cprofile_table(b_path)
    rows = []
    for func, file in sorted(set(first) | set(second)):
        nc_a, tt_a, ct_a = first.get((func, file), (0, 0.0, 0.0))
        nc_b, tt_b, ct_b = second.get((func, file), (0, 0.0, 0.0))
        rows.append({"function": func, "file": file,
                     "cum_s_O_study": ct_a, "cum_s_O_norc": ct_b, "delta_cum_s": ct_a - ct_b,
                     "self_s_O_study": tt_a, "self_s_O_norc": tt_b, "delta_self_s": tt_a - tt_b,
                     "ncalls_O_study": nc_a, "ncalls_O_norc": nc_b})
    missing = [name for name in must_include if not any(r["function"] == name for r in rows)]
    if missing:
        raise AttributionError(f"cprofile diff: no row for {', '.join(missing)}")
    rows.sort(key=lambda r: r["delta_cum_s"], reverse=True)
    return rows[:RC_DIFF_ROWS] + [r for r in rows[RC_DIFF_ROWS:] if r["function"] in must_include]


def runs_of(block) -> list:
    manifests = []
    for path in sorted(RAW.glob("*/manifest.json")):
        manifest = json.loads(path.read_text())
        if manifest.get("block") == block and manifest.get("role") == "rep":
            manifests.append(manifest)
    return manifests


def _wall(manifest) -> float:
    wall = (manifest.get("metrics") or {}).get("wall_s")
    if wall is None:
        raise AttributionError(f"{manifest['run_id']}: metrics.wall_s missing")
    return float(wall)


def _is_counters_run(manifest) -> bool:
    entry_point = (manifest.get("instrumentation") or {}).get("entry_point")
    return bool(manifest.get("counters_path")) or entry_point == "perf_run.py"


def _file_of(subsystem, function) -> str:
    entries = [e for e in ISSUE_MAP if e["subsystem"] == subsystem]
    for entry in entries:
        if function in entry["functions"]:
            return entry["file"]
    return next((e["file"] for e in entries if not e["functions"]), "")


def _issues_of(subsystem) -> str:
    seen = []
    for entry in ISSUE_MAP:
        if entry["subsystem"] == subsystem:
            seen.extend(i for i in entry["issues"] if i not in seen)
    return ",".join(seen)


def _row_order(keys) -> list:
    subsystems = list(dict.fromkeys(e["subsystem"] for e in ISSUE_MAP))
    return sorted(keys, key=lambda k: (subsystems.index(k[0]), k[1] != TOTAL, k[1]))


def _group_rows(block, case, variant, profiled, plain) -> list:
    per_run = []
    for manifest in profiled:
        path = RAW / manifest["run_id"] / "pyinstrument.json"
        if not path.exists():
            raise AttributionError(f"{manifest['run_id']}: pyinstrument.json missing")
        per_run.append((attribute_tree(load_tree(path)["root_frame"], ISSUE_MAP), _wall(manifest)))
    profiled_wall = statistics.median(wall for _, wall in per_run)
    plain_wall = statistics.median(_wall(m) for m in plain)
    keys = _row_order({key for rows, _ in per_run for key in rows})
    out = []
    for key in keys:
        cum = [rows.get(key, {}).get("cum_s", 0.0) for rows, _ in per_run]
        self_s = [rows.get(key, {}).get("self_s", 0.0) for rows, _ in per_run]
        cum_s = statistics.median(cum)
        share = cum_s / profiled_wall
        shares = [c / wall for c, (_, wall) in zip(cum, per_run)]
        agreement = (max(shares) - min(shares)) * 100 if len(shares) > 1 else None
        subsystem, function = key
        out.append({
            "block": block, "case": case, "variant": variant, "subsystem": subsystem,
            "issues": _issues_of(subsystem), "function": function,
            "file": "" if function == TOTAL else _file_of(subsystem, function),
            "n_profiled": len(profiled), "n_plain": len(plain),
            "cum_s": cum_s, "self_s": statistics.median(self_s), "share_profiled": share,
            "agreement_pts": agreement, "profiled_wall_s": profiled_wall,
            "plain_wall_s": plain_wall, "overhead_bound_s": profiled_wall - plain_wall,
            "cost_plain_s": cum_s * plain_wall / profiled_wall,
            "status": "observed" if cum_s > 0 else "not_observed"})
    return out


def _write_csv(path, columns, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _fmt(row[c]) for c in columns})


def _fmt(value):
    if value is None:
        return ""
    return round(value, 6) if isinstance(value, float) else value


def _warn_contaminated(manifests) -> None:
    for manifest in manifests:
        if (manifest.get("host_during") or {}).get("contaminated"):
            print(f"warning: {manifest['run_id']} is marked contaminated", file=sys.stderr)


def attribution_tables(block, out_dir) -> list:
    runs = runs_of(block)
    if not runs:
        raise AttributionError(f"block {block}: no reps found under {RAW}")
    _warn_contaminated(runs)
    groups = {}
    for manifest in runs:
        groups.setdefault((manifest["case"], manifest["variant"]), []).append(manifest)
    by_case = {}
    for (case, variant), members in sorted(groups.items()):
        profiled = [m for m in members if m.get("profiler") == "pyinstrument"]
        plain = [m for m in members if m.get("profiler") == "none" and not _is_counters_run(m)]
        where = f"block {block} {case}/{variant}"
        if not profiled:
            raise AttributionError(f"{where}: no profiled (pyinstrument) rep")
        if not plain:
            raise AttributionError(f"{where}: no plain rep")
        if len(profiled) == 1:
            print(f"{where}: one profiled rep, agreement not assessable", file=sys.stderr)
        by_case.setdefault(case, []).extend(_group_rows(block, case, variant, profiled, plain))
    paths = []
    for case, rows in by_case.items():
        path = Path(out_dir) / f"attribution_{block}_{case}.csv"
        _write_csv(path, ATTRIBUTION_COLUMNS, rows)
        paths.append(path)
    return paths


def rc_diff_table(block, out_dir) -> Path:
    runs = [m for m in runs_of(block) if m.get("profiler") == "cprofile"]
    picked = {}
    for variant in ("O_study", "O_norc"):
        found = [m for m in runs if m["variant"] == variant]
        if not found:
            raise AttributionError(f"block {block}: no cprofile rep of variant {variant}")
        if len(found) > 1:
            raise AttributionError(f"block {block}: {len(found)} cprofile reps of variant "
                                   f"{variant}, need exactly 1")
        picked[variant] = RAW / found[0]["run_id"] / "cprofile.prof"
        if not picked[variant].exists():
            raise AttributionError(f"{found[0]['run_id']}: cprofile.prof missing")
    rows = cprofile_diff(picked["O_study"], picked["O_norc"], must_include=RC_MUST_INCLUDE)
    path = Path(out_dir) / f"rc_diff_{block}.csv"
    _write_csv(path, RC_DIFF_COLUMNS, rows)
    return path


def counters_table(block, out_dir) -> Path:
    runs = [m for m in runs_of(block) if m.get("counters_path")]
    if not runs:
        raise AttributionError(f"block {block}: no counters reps")
    rows = []
    for manifest in sorted(runs, key=lambda m: m["run_id"]):
        path = RAW / manifest["run_id"] / "counters.json"
        if not path.exists():
            raise AttributionError(f"{manifest['run_id']}: counters.json missing")
        rows.append({"run_id": manifest["run_id"], "case": manifest["case"],
                     **counters_summary(path)})
    path = Path(out_dir) / f"counters_{block}.csv"
    _write_csv(path, COUNTERS_COLUMNS, rows)
    return path


def _usable(manifests, exclude):
    return [m for m in manifests
            if m.get("termination") in USABLE and m["run_id"] not in set(exclude)]


def _quartiles(values):
    if len(values) < 2:
        return values[0], values[0]
    q = statistics.quantiles(values, n=4)
    return q[0], q[2]


def _arm_stats(block, variant, reps, exclude):
    arm = [m for m in reps if m.get("variant") == variant]
    used = _usable(arm, exclude)
    if not used:
        raise AttributionError(f"block {block}: arm {variant} has no usable reps")
    walls = sorted(_wall(m) for m in used)
    q1, q3 = _quartiles(walls)
    return {"n_reps": len(arm), "n_used": len(used),
            "n_flagged": sum(1 for m in used if (m.get("host_during") or {}).get("contaminated")),
            "wall_s_median": statistics.median(walls), "wall_s_q1": q1, "wall_s_q3": q3}


def _agent_steps_median(counters_block, variant, exclude):
    reps = [m for m in runs_of(counters_block)
            if m.get("variant") == variant and m.get("counters_path")]
    used = _usable(reps, exclude)
    if not used:
        raise AttributionError(f"block {counters_block}: arm {variant} has no usable counters reps")
    steps = []
    for manifest in used:
        path = RAW / manifest["run_id"] / "counters.json"
        if not path.exists():
            raise AttributionError(f"{manifest['run_id']}: counters.json missing")
        steps.append(counters_summary(path)["agent_steps"])
    return statistics.median(steps)


def _verdict(base, arm):
    spread = max(base["wall_s_q3"] - base["wall_s_q1"], arm["wall_s_q3"] - arm["wall_s_q1"])
    if abs(arm["diff_s"]) <= spread:
        return "tie"
    return "fix_first" if arm["diff_per_study_s"] > REMOVAL_BAR_S else "below_bar"


def _removal_row(block, counters_block, variant, reps, exclude):
    row = {"arm": variant, "issue": ARM_ISSUE[variant], "source_block": block,
           **_arm_stats(block, variant, reps, exclude)}
    row["agent_steps_median"] = _agent_steps_median(counters_block, variant, exclude)
    if not row["agent_steps_median"]:
        raise AttributionError(f"block {counters_block}: arm {variant} has zero agent-steps")
    row["us_per_agent_step"] = row["wall_s_median"] / row["agent_steps_median"] * 1e6
    row["bar_s"] = REMOVAL_BAR_S
    return row


def _compare_to_baseline(base, row):
    row["diff_s"] = base["wall_s_median"] - row["wall_s_median"]
    row["diff_per_study_s"] = row["diff_s"] * 10
    row["diff_us_per_agent_step"] = base["us_per_agent_step"] - row["us_per_agent_step"]
    row["verdict"] = _verdict(base, row)


def _block_reps(block):
    reps = [m for m in runs_of(block) if not m.get("counters_path")]
    if not reps:
        raise AttributionError(f"block {block}: no reps found under {RAW}")
    _warn_contaminated(reps)
    return reps


def _check_exclude(exclude, blocks):
    known = {m["run_id"] for b in blocks if b for m in runs_of(b)}
    unknown = sorted(set(exclude) - known)
    if unknown:
        raise AttributionError(f"--exclude ids match no rep: {', '.join(unknown)}")


def _rerun_variants(reps):
    """Arms of a rerun block that replace the main block's arm (everything but the baseline)."""
    found = {m.get("variant") for m in reps}
    if "O_norc" not in found:
        raise AttributionError("rerun block has no O_norc baseline")
    unknown = found - set(REMOVAL_ARMS)
    if unknown:
        raise AttributionError(f"rerun block has unknown arms {sorted(unknown)}")
    return [v for v in REMOVAL_ARMS[1:] if v in found]


def removal_table(block, counters_block, out_dir, exclude=(), rerun_block=None,
                  rerun_counters_block=None) -> Path:
    """One row per arm against the O_norc of its own block.

    An arm present in the rerun block (G3b: O_norc and nss) is compared with that
    block's O_norc instead of the main block's; source_block names the block each
    row's arm and baseline come from. The O_norc row is the main block's.
    """
    reps = _block_reps(block)
    _check_exclude(exclude, [block, counters_block, rerun_block, rerun_counters_block])
    rows = {v: _removal_row(block, counters_block, v, reps, exclude) for v in REMOVAL_ARMS}
    base = rows["O_norc"]
    base.update({"diff_s": None, "diff_per_study_s": None, "diff_us_per_agent_step": None,
                 "verdict": "baseline"})
    for variant in REMOVAL_ARMS[1:]:
        _compare_to_baseline(base, rows[variant])
    if rerun_block:
        rerun_reps = _block_reps(rerun_block)
        rerun_base = _removal_row(rerun_block, rerun_counters_block, "O_norc", rerun_reps, exclude)
        for variant in _rerun_variants(rerun_reps):
            rows[variant] = _removal_row(rerun_block, rerun_counters_block, variant, rerun_reps,
                                         exclude)
            _compare_to_baseline(rerun_base, rows[variant])
    path = Path(out_dir) / f"removal_{block}.csv"
    _write_csv(path, REMOVAL_COLUMNS, [rows[v] for v in REMOVAL_ARMS])
    return path


def _route_path_row(run_id, path, entry, per_call_s) -> dict:
    overhead = entry["calls"] * per_call_s
    row = dict.fromkeys(ROUTE_PATHS_COLUMNS)
    row.update({"run_id": run_id, "path": path, "calls": entry["calls"],
                "seconds": entry["seconds"], "overhead_s": overhead,
                "net_seconds": entry["seconds"] - overhead})
    if path not in KEYED_PATHS:
        return row
    row.update({"total": entry["total"], "distinct": entry["distinct"],
                "capped": entry["capped"]})
    if entry["total"] > 0:
        row["hit_share"] = 1 - entry["distinct"] / entry["total"]
        row["avoidable_s"] = row["hit_share"] * row["net_seconds"]
        row["avoidable_per_study_s"] = STUDY_RUNS * row["avoidable_s"]
    return row


def _route_path_rows(run_id, paths, overhead) -> list:
    per_call_s = overhead["noop_wrapper_seconds"] / overhead["noop_wrapper_calls"]
    rows = [_route_path_row(run_id, p, paths[p], per_call_s) for p in ROUTE_PATHS]
    by_path = {r["path"]: r for r in rows}
    segment = by_path["evaluate_segment"]
    # Time in evaluate_segment that no timed path covers; flat child seconds would also
    # subtract the first_leg calls of the same paths.
    remainder = dict.fromkeys(ROUTE_PATHS_COLUMNS)
    remainder.update({"run_id": run_id, "path": "remainder",
                      "net_seconds": paths["evaluate_segment"]["self_seconds"]
                      - segment["overhead_s"]})
    keyed = [by_path[p] for p in KEYED_PATHS if by_path[p]["avoidable_s"] is not None]
    total = dict.fromkeys(ROUTE_PATHS_COLUMNS)
    total.update({"run_id": run_id, "path": TOTAL,
                  "net_seconds": segment["net_seconds"] + by_path["first_leg"]["net_seconds"],
                  "avoidable_s": sum(r["avoidable_s"] for r in keyed),
                  "avoidable_per_study_s": sum(r["avoidable_per_study_s"] for r in keyed),
                  "capped": any(by_path[p]["capped"] for p in KEYED_PATHS)})
    return rows + [remainder, total]


def route_paths_table(block, out_dir) -> Path:
    rows = []
    for manifest in runs_of(block):
        if not manifest.get("counters_path"):
            continue
        detail = load_tree(RAW / manifest["run_id"] / "counters.json").get("detail", {})
        if not detail.get("route_paths"):
            continue
        rows.extend(_route_path_rows(manifest["run_id"], detail["route_paths"],
                                     detail["route_paths_overhead"]))
    if not rows:
        raise AttributionError(f"block {block}: no route_paths in any counters.json")
    path = Path(out_dir) / f"route_paths_{block}.csv"
    _write_csv(path, ROUTE_PATHS_COLUMNS, rows)
    return path


def _sha256(path: Path) -> str:
    if not path.exists():
        raise AttributionError(f"{path}: missing (timed-run output)")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _outputs_dir(manifest) -> Path:
    if not manifest.get("outputs_dir"):
        raise AttributionError(f"{manifest['run_id']}: outputs_dir missing")
    return Path(manifest["outputs_dir"])


def _paired_reps(block, exclude, arms=MEMO_ARMS) -> dict:
    """seed -> {arm: manifest}: the first usable timed rep of each *arms* arm per seed."""
    pairs: dict = {}
    for manifest in _usable(runs_of(block), exclude):
        if manifest.get("variant") in arms:
            pairs.setdefault(_seed(manifest), {}).setdefault(manifest["variant"], manifest)
    return pairs


def _seed(manifest) -> int:
    if manifest.get("seed") is None:
        raise AttributionError(f"{manifest['run_id']}: seed missing")
    return int(manifest["seed"])


def _attempted_seeds(block, arms=MEMO_ARMS) -> set:
    """Seeds with any rep of an *arms* arm, whatever its termination."""
    return {_seed(m) for m in runs_of(block) if m.get("variant") in arms}


def equality_table(block, out_dir, exclude=()) -> tuple:
    """Per seed, whether O_norc and nomemo wrote the same exit.csv and rh.csv (G5, D40 precondition).

    Seeds that never started are not visible here; the driver's PARTIAL status line records them."""
    pairs = _paired_reps(block, exclude)
    if not pairs:
        raise AttributionError(f"block {block}: no usable O_norc/nomemo reps")
    rows = []
    for seed in sorted(_attempted_seeds(block) | set(pairs)):
        arms = pairs.get(seed, {})
        if set(arms) != set(MEMO_ARMS):
            raise AttributionError(f"block {block}: seed {seed} lacks a usable rep in both arms")
        row = {"seed": seed, "memo_run_id": arms["O_norc"]["run_id"],
               "nomemo_run_id": arms["nomemo"]["run_id"]}
        for name in EQUALITY_FILES:
            digests = [_sha256(_outputs_dir(arms[arm]) / name) for arm in MEMO_ARMS]
            row[name.replace(".", "_") + "_equal"] = digests[0] == digests[1]
        rows.append(row)
    path = Path(out_dir) / f"equality_{block}.csv"
    _write_csv(path, EQUALITY_COLUMNS, rows)
    return path, all(r["exit_csv_equal"] and r["rh_csv_equal"] for r in rows)


def _flagged(manifest) -> bool:
    return bool((manifest.get("host_during") or {}).get("contaminated"))


def _outputs_equal(memo, nomemo) -> bool:
    return all(_sha256(_outputs_dir(memo) / name) == _sha256(_outputs_dir(nomemo) / name)
               for name in EQUALITY_FILES)


def _paired_verdict(median_d, iqr, per_study, any_unequal) -> str:
    """D40: paired per-seed differences; a differing output pair withholds the verdict."""
    if any_unequal:
        return "invalid_outputs_differ"
    if abs(median_d) <= iqr:
        return "tie"
    return "fix_first" if per_study > REMOVAL_BAR_S else "below_bar"


def paired_table(block, counters_block, out_dir, exclude=()) -> Path:
    """One row per seed (wall of nomemo minus wall of memo) and an ALL row with the D40 verdict (G5)."""
    _check_exclude(exclude, [block, counters_block])
    pairs = _paired_reps(block, exclude)
    complete = {s: arms for s, arms in pairs.items() if set(arms) == set(MEMO_ARMS)}
    if not complete:
        raise AttributionError(f"block {block}: no seed with a usable rep in both arms")
    rows, diffs = [], []
    for seed in sorted(complete):
        memo, nomemo = complete[seed]["O_norc"], complete[seed]["nomemo"]
        row = dict.fromkeys(PAIRED_COLUMNS)
        row.update({"seed": seed, "memo_run_id": memo["run_id"], "nomemo_run_id": nomemo["run_id"],
                    "wall_memo_s": _wall(memo), "wall_nomemo_s": _wall(nomemo),
                    "d_s": _wall(nomemo) - _wall(memo), "flagged_memo": _flagged(memo),
                    "flagged_nomemo": _flagged(nomemo), "outputs_equal": _outputs_equal(memo, nomemo)})
        rows.append(row)
        diffs.append(row["d_s"])
    q1, q3 = _quartiles(sorted(diffs))
    median = statistics.median(diffs)
    steps = _agent_steps_median(counters_block, "O_norc", exclude)
    if not steps:
        raise AttributionError(f"block {counters_block}: O_norc has zero agent-steps")
    total = dict.fromkeys(PAIRED_COLUMNS)
    total.update({"seed": "ALL", "n_seeds": len(diffs), "n_seeds_dropped": len(_attempted_seeds(block) | set(pairs)) - len(complete),
                  "median_d_s": median, "iqr_d_s": q3 - q1, "diff_per_study_s": STUDY_RUNS * median,
                  "sum_d_s": sum(diffs), "agent_steps_median": steps,
                  "d_us_per_agent_step": median / steps * 1e6,
                  "verdict": _paired_verdict(median, q3 - q1, STUDY_RUNS * median,
                                             not all(r["outputs_equal"] for r in rows))})
    rows.append(total)
    path = Path(out_dir) / f"paired_{block}.csv"
    _write_csv(path, PAIRED_COLUMNS, rows)
    return path


def _outcome(manifest, key):
    value = (manifest.get("outcome") or {}).get(key)
    if value is None:
        raise AttributionError(f"{manifest['run_id']}: outcome.{key} missing")
    return value


def _removal_verdict(median_d, iqr, per_study) -> str:
    """D41: paired per-seed differences of a removal arm; no output equality, the arm changes trajectories."""
    if abs(median_d) <= iqr:
        return "tie"
    return "fix_first" if per_study > REMOVAL_BAR_S else "below_bar"


def paired_removal_table(block, arm, counters_block, out_dir, exclude=()) -> Path:
    """One row per seed (wall of O_norc minus wall of *arm*) and an ALL row with the verdict (G6).

    Positive d_s means removing the mechanism saves time (the G3 diff_s convention). Each row carries the
    sim time and evacuated count of both reps, since a removal arm may end the simulation earlier."""
    others = [k for k in ARM_ISSUE if k != "O_norc"]
    if arm not in others:
        raise AttributionError(f"--arm must be one of {', '.join(others)}, got {arm}")
    arms = ("O_norc", arm)
    _check_exclude(exclude, [block, counters_block])
    pairs = _paired_reps(block, exclude, arms)
    complete = {s: reps for s, reps in pairs.items() if set(reps) == set(arms)}
    if not complete:
        raise AttributionError(f"block {block}: no seed with a usable rep in both arms")
    rows, diffs = [], []
    for seed in sorted(complete):
        base, other = complete[seed]["O_norc"], complete[seed][arm]
        row = dict.fromkeys(PAIRED_REMOVAL_COLUMNS)
        row.update({"seed": seed, "base_run_id": base["run_id"], "arm_run_id": other["run_id"],
                    "wall_base_s": _wall(base), "wall_arm_s": _wall(other), "d_s": _wall(base) - _wall(other),
                    "flagged_base": _flagged(base), "flagged_arm": _flagged(other),
                    "sim_time_base_s": _outcome(base, "sim_time_s"), "sim_time_arm_s": _outcome(other, "sim_time_s"),
                    "evacuated_base": _outcome(base, "evacuated"), "evacuated_arm": _outcome(other, "evacuated")})
        rows.append(row)
        diffs.append(row["d_s"])
    q1, q3 = _quartiles(sorted(diffs))
    median = statistics.median(diffs)
    steps = _agent_steps_median(counters_block, "O_norc", exclude)
    if not steps:
        raise AttributionError(f"block {counters_block}: O_norc has zero agent-steps")
    total = dict.fromkeys(PAIRED_REMOVAL_COLUMNS)
    total.update({"seed": "ALL", "n_seeds": len(diffs),
                  "n_seeds_dropped": len(_attempted_seeds(block, arms) | set(pairs)) - len(complete),
                  "median_d_s": median, "iqr_d_s": q3 - q1, "diff_per_study_s": STUDY_RUNS * median,
                  "sum_d_s": sum(diffs), "agent_steps_median": steps,
                  "d_us_per_agent_step": median / steps * 1e6,
                  "verdict": _removal_verdict(median, q3 - q1, STUDY_RUNS * median)})
    rows.append(total)
    path = Path(out_dir) / f"paired_removal_{block}_{arm}.csv"
    _write_csv(path, PAIRED_REMOVAL_COLUMNS, rows)
    return path


def _lookup_outputs_equal(base, arm) -> bool:
    return all(_sha256(_outputs_dir(base) / name) == _sha256(_outputs_dir(arm) / name)
               for name in LOOKUP_EQUALITY_FILES)


def paired_lookup_table(block, arm, counters_block, out_dir, exclude=()) -> tuple:
    """One row per seed (wall of *arm* minus wall of O_norc) and an ALL row with the D42/D43 verdict (G8 nlk, G11 nrp).

    O_norc runs the default code, nlk (G8) the pre-change point lookup and nrp (G11) the pre-change exit test on
    the same stage, so a positive d_s means the change is faster. The outputs of each pair are compared; one
    unequal pair withholds the verdict. Returns (path, outputs_equal)."""
    if arm not in LOOKUP_VARIANTS:
        raise AttributionError(f"--arm must be nlk or nrp, got {arm}")
    _check_exclude(exclude, [block, counters_block])
    arms = (LOOKUP_BASE, arm)
    pairs = _paired_reps(block, exclude, arms)
    complete = {s: reps for s, reps in pairs.items() if set(reps) == set(arms)}
    if not complete:
        raise AttributionError(f"block {block}: no seed with a usable rep in both arms")
    rows, diffs = [], []
    for seed in sorted(complete):
        base, other = complete[seed]["O_norc"], complete[seed][arm]
        row = dict.fromkeys(PAIRED_LOOKUP_COLUMNS)
        row.update({"seed": seed, "base_run_id": base["run_id"], "arm_run_id": other["run_id"],
                    "wall_base_s": _wall(base), "wall_arm_s": _wall(other), "d_s": _wall(other) - _wall(base),
                    "flagged_base": _flagged(base), "flagged_arm": _flagged(other),
                    "outputs_equal": _lookup_outputs_equal(base, other)})
        rows.append(row)
        diffs.append(row["d_s"])
    q1, q3 = _quartiles(sorted(diffs))
    median = statistics.median(diffs)
    steps = _agent_steps_median(counters_block, "O_norc", exclude)
    if not steps:
        raise AttributionError(f"block {counters_block}: O_norc has zero agent-steps")
    equal = all(r["outputs_equal"] for r in rows)
    total = dict.fromkeys(PAIRED_LOOKUP_COLUMNS)
    total.update({"seed": "ALL", "n_seeds": len(diffs),
                  "n_seeds_dropped": len(_attempted_seeds(block, arms) | set(pairs)) - len(complete),
                  "median_d_s": median, "iqr_d_s": q3 - q1, "diff_per_study_s": STUDY_RUNS * median,
                  "sum_d_s": sum(diffs), "agent_steps_median": steps,
                  "d_us_per_agent_step": median / steps * 1e6,
                  "verdict": _paired_verdict(median, q3 - q1, STUDY_RUNS * median, not equal)})
    rows.append(total)
    path = Path(out_dir) / f"paired_lookup_{block}_{arm}.csv"
    _write_csv(path, PAIRED_LOOKUP_COLUMNS, rows)
    return path, equal


def _is_entry(frame, name, suffix) -> bool:
    path = "/" + str(frame.get("file_path", "")).lstrip("/")
    return frame["function"] == name and path.endswith("/" + suffix)


def _extend_anchors(anchors, frame) -> dict:
    """entry -> path from its entry frame to ``frame``; an entry already anchored starts no second subtree."""
    anchors = {entry: path + (frame["function"],) for entry, path in anchors.items()}
    for name, suffix in REROUTE_ENTRIES:
        if name not in anchors and _is_entry(frame, name, suffix):
            anchors[name] = (frame["function"],)
    return anchors


def _reroute_rows_of(root_frame) -> dict:
    """(entry, path) -> cum_s, self_s, depth, file for every frame at or below an entry point.

    A frame inside an entry's subtree starts no second subtree of the same entry; a frame
    below both entry points has a row under each. Repeated call paths sum.
    """
    rows = {}
    stack = [(root_frame, {})]
    while stack:
        frame, anchors = stack.pop()
        anchors = _extend_anchors(anchors, frame)
        children = [c for c in frame.get("children", []) if not _is_own_time(c)]
        self_s = max(0.0, frame["time"] - sum(c["time"] for c in children))
        for entry, path in anchors.items():
            row = rows.setdefault((entry, " > ".join(path)), {
                "cum_s": 0.0, "self_s": 0.0, "depth": len(path) - 1, "function": frame["function"],
                "file": Path(str(frame.get("file_path", ""))).name})
            row["cum_s"] += frame["time"]
            row["self_s"] += self_s
        stack.extend((child, anchors) for child in children)
    return rows


def _reroute_order(rows) -> list:
    """Entries in REROUTE_ENTRIES order; within an entry parents before children, larger cum_s first."""
    children = {}
    for entry, path in rows:
        parent = path.rsplit(" > ", 1)[0] if " > " in path else None
        children.setdefault((entry, parent), []).append(path)
    ordered = []
    for name, _ in REROUTE_ENTRIES:
        stack = sorted(children.get((name, None), []), key=lambda p: (rows[(name, p)]["cum_s"], p))
        while stack:
            path = stack.pop()
            ordered.append((name, path))
            stack.extend(sorted(children.get((name, path), []), key=lambda p: (rows[(name, p)]["cum_s"], p)))
    return ordered


def reroute_tree_table(block, out_dir, exclude=()) -> Path:
    """Every call path at or below the rerouting entry points, medians over the profiled reps (G13)."""
    runs = runs_of(block)
    _check_exclude(exclude, [block])
    _warn_contaminated(runs)
    profiled = _usable([m for m in runs if m.get("profiler") == "pyinstrument"], exclude)
    plain = _usable([m for m in runs if m.get("profiler") == "none" and not _is_counters_run(m)], exclude)
    if not profiled:
        raise AttributionError(f"block {block}: no usable profiled (pyinstrument) rep")
    if not plain:
        raise AttributionError(f"block {block}: no plain rep")
    if len(profiled) == 1:
        print(f"block {block}: one profiled rep, agreement not assessable", file=sys.stderr)
    per_run = []
    for manifest in profiled:
        path = RAW / manifest["run_id"] / "pyinstrument.json"
        if not path.exists():
            raise AttributionError(f"{manifest['run_id']}: pyinstrument.json missing")
        per_run.append((_reroute_rows_of(load_tree(path)["root_frame"]), _wall(manifest)))
    keys = {key for rows, _ in per_run for key in rows}
    if not keys:
        raise AttributionError(f"block {block}: no frame matches a rerouting entry point")
    profiled_wall = statistics.median(wall for _, wall in per_run)
    plain_wall = statistics.median(_wall(m) for m in plain)
    table = {}
    for key in keys:
        cum = [rows.get(key, {}).get("cum_s", 0.0) for rows, _ in per_run]
        shares = [c / wall for c, (_, wall) in zip(cum, per_run)]
        first = next(rows[key] for rows, _ in per_run if key in rows)
        if first["depth"] and statistics.median(shares) < REROUTE_MIN_SHARE:
            continue
        cum_s = statistics.median(cum)
        cost = cum_s * plain_wall / profiled_wall
        table[key] = {
            "block": block, "entry": key[0], "path": key[1], "depth": first["depth"],
            "function": first["function"], "file": first["file"],
            "n_profiled": len(profiled), "n_plain": len(plain), "cum_s": cum_s,
            "self_s": statistics.median(rows.get(key, {}).get("self_s", 0.0) for rows, _ in per_run),
            "share_profiled": statistics.median(shares),
            "agreement_pts": (max(shares) - min(shares)) * 100 if len(shares) > 1 else None,
            "profiled_wall_s": profiled_wall, "plain_wall_s": plain_wall, "cost_plain_s": cost,
            "cost_per_study_s": STUDY_RUNS * cost,
            "verdict": "above_bar" if STUDY_RUNS * cost > REMOVAL_BAR_S else "below_bar"}
    path = Path(out_dir) / f"reroute_tree_{block}.csv"
    _write_csv(path, REROUTE_TREE_COLUMNS, [table[key] for key in _reroute_order(table)])
    return path


def _tree_costs(tree_csv) -> dict:
    """cost function -> summed cost_per_study_s of its outermost occurrences in a reroute-tree CSV (G14)."""
    costs: dict = {}
    try:
        with open(tree_csv, newline="") as fh:
            for row in csv.DictReader(fh):
                elements = row["path"].split(" > ")
                function = elements[-1]
                if function in elements[:-1]:
                    continue
                costs[function] = costs.get(function, 0.0) + float(row["cost_per_study_s"])
    except (OSError, KeyError, ValueError) as exc:
        raise AttributionError(f"tree {tree_csv}: cannot read path/cost_per_study_s ({exc!r})") from exc
    return costs


def _repeat_ceiling_row(manifest, path, entry, costs) -> dict:
    if entry is None:
        raise AttributionError(f"{manifest['run_id']}: route_paths lacks {path}")
    if entry.get("total") is None or entry.get("distinct") is None:
        raise AttributionError(f"{manifest['run_id']}: {path} has no total or distinct")
    function = REPEAT_COST_FUNCTION[path]
    if function not in costs:
        raise AttributionError(f"tree has no row for {function}")
    total, cost = entry["total"], costs[function]
    share = 1 - entry["distinct"] / total if total else None
    ceiling = share * cost if total else None
    verdict = "info" if path == "first_leg_r01" else (
        "above_bar" if ceiling is not None and ceiling > REMOVAL_BAR_S else "below_bar")
    return {"run_id": manifest["run_id"], "seed": _seed(manifest), "path": path, "total": total,
            "distinct": entry["distinct"], "hit_share": share, "capped": bool(entry.get("capped")),
            "cost_per_study_s": cost, "ceiling_per_study_s": ceiling, "verdict": verdict}


def repeat_ceiling_table(block, tree_csv, out_dir, exclude=()) -> Path:
    """Exact repeat share of the keyed route walks times the path's cost per study (G14)."""
    runs = runs_of(block)
    _check_exclude(exclude, [block])
    usable = _usable([m for m in runs if m.get("counters_path")], exclude)
    if not usable:
        raise AttributionError(f"block {block}: no usable detail run")
    costs = _tree_costs(tree_csv)
    rows = []
    for manifest in sorted(usable, key=_seed):
        detail = load_tree(RAW / manifest["run_id"] / "counters.json").get("detail", {})
        route_paths = detail.get("route_paths") or {}
        rows.extend(_repeat_ceiling_row(manifest, path, route_paths.get(path), costs)
                    for path in REPEAT_PATHS)
    path = Path(out_dir) / f"repeat_ceiling_{block}.csv"
    _write_csv(path, REPEAT_CEILING_COLUMNS, rows)
    return path


def _memo_counts(run_dir: Path) -> dict:
    """hits, misses, clears, hit_share from memo.log; empty when the file or the line is missing."""
    counts = {"hits": None, "misses": None, "clears": None, "hit_share": None}
    log = run_dir / "memo.log"
    match = MEMO_LINE.search(log.read_text()) if log.exists() else None
    if match is None:
        return counts
    hits, misses, clears = (int(g) for g in match.groups())
    counts.update({"hits": hits, "misses": misses, "clears": clears,
                   "hit_share": hits / (hits + misses) if hits + misses else None})
    return counts


def memo_counters_table(counters_block, out_dir) -> Path:
    """One row per counters rep: agent-steps and the memo's hits, misses, clears (G5)."""
    runs = [m for m in runs_of(counters_block) if m.get("counters_path")]
    if not runs:
        raise AttributionError(f"block {counters_block}: no counters reps")
    rows = []
    for manifest in sorted(runs, key=lambda m: m["run_id"]):
        run_dir = RAW / manifest["run_id"]
        if not (run_dir / "counters.json").exists():
            raise AttributionError(f"{manifest['run_id']}: counters.json missing")
        rows.append({"run_id": manifest["run_id"], "variant": manifest["variant"],
                     "agent_steps": counters_summary(run_dir / "counters.json")["agent_steps"],
                     **_memo_counts(run_dir)})
    path = Path(out_dir) / f"memo_counters_{counters_block}.csv"
    _write_csv(path, MEMO_COUNTERS_COLUMNS, rows)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--block", help="attribution tables for the block's pyinstrument reps")
    mode.add_argument("--rc-diff", metavar="BLOCK", help="cProfile diff O_study vs O_norc")
    mode.add_argument("--counters", metavar="BLOCK", help="counters table of the block")
    mode.add_argument("--removal", metavar="BLOCK",
                      help="removal table: O_norc vs nrr, nss, nst (G3)")
    mode.add_argument("--route-paths", metavar="BLOCK",
                      help="route-path table of the block's detail run (G4)")
    mode.add_argument("--equality", metavar="BLOCK",
                      help="per-seed output equality of O_norc vs nomemo (G5)")
    mode.add_argument("--paired", metavar="BLOCK",
                      help="paired per-seed memo table with the D40 verdict (G5)")
    mode.add_argument("--paired-removal", metavar="BLOCK",
                      help="paired per-seed removal table of O_norc vs --arm with the D41 verdict (G6)")
    mode.add_argument("--paired-lookup", metavar="BLOCK",
                      help="paired per-seed table of O_norc vs --arm with output equality and the D42/D43 verdict (G8, G11)")
    mode.add_argument("--memo-counters", metavar="BLOCK",
                      help="hits, misses, clears per counters rep from memo.log (G5)")
    mode.add_argument("--reroute-tree", metavar="BLOCK",
                      help="call paths at or below the rerouting entry points from the pyinstrument reps (G13)")
    mode.add_argument("--repeat-ceiling", metavar="BLOCK",
                      help="exact repeat share times path cost per study, with --tree (G14)")
    parser.add_argument("--tree", metavar="TREE_CSV",
                        help="reroute-tree CSV giving the path costs (required with --repeat-ceiling)")
    parser.add_argument("--counters-block", metavar="BLOCK",
                        help="counters block giving agent-steps per arm (required with --removal)")
    parser.add_argument("--rerun-block", metavar="BLOCK",
                        help="rerun block (G3b): its non-baseline arms replace the main block's "
                             "and are compared with its own O_norc (needs --rerun-counters-block)")
    parser.add_argument("--rerun-counters-block", metavar="BLOCK",
                        help="counters block of the rerun block")
    parser.add_argument("--arm", metavar="VARIANT", help="arm of --paired-removal (nrr, nss, nst) or --paired-lookup (nlk, nrp)")
    parser.add_argument("--exclude", action="append", default=[], metavar="RUN_ID",
                        help="rep to leave out (claude offender)")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)
    if args.repeat_ceiling and not args.tree:
        parser.error("--repeat-ceiling needs --tree")
    if args.tree and not args.repeat_ceiling:
        parser.error("--tree needs --repeat-ceiling")
    if args.removal and not args.counters_block:
        parser.error("--removal needs --counters-block")
    if args.paired and not args.counters_block:
        parser.error("--paired needs --counters-block")
    if args.paired_removal and not args.arm:
        parser.error("--paired-removal needs --arm")
    if args.paired_removal and not args.counters_block:
        parser.error("--paired-removal needs --counters-block")
    if args.paired_lookup and not args.arm:
        parser.error("--paired-lookup needs --arm")
    if args.paired_lookup and not args.counters_block:
        parser.error("--paired-lookup needs --counters-block")
    if args.arm and not (args.paired_removal or args.paired_lookup):
        parser.error("--arm needs --paired-removal or --paired-lookup")
    if args.counters_block and not (args.removal or args.paired or args.paired_removal or args.paired_lookup):
        parser.error("--counters-block needs --removal, --paired or --paired-removal, or --paired-lookup")
    if args.exclude and not (args.removal or args.equality or args.paired or args.paired_removal
                             or args.paired_lookup or args.reroute_tree or args.repeat_ceiling):
        parser.error("--exclude needs --removal, --equality, --paired or --paired-removal, --paired-lookup, "
                     "--reroute-tree or --repeat-ceiling")
    if bool(args.rerun_block) != bool(args.rerun_counters_block):
        parser.error("--rerun-block and --rerun-counters-block go together")
    if args.rerun_block and not args.removal:
        parser.error("--rerun-block needs --removal")
    rc = 0
    try:
        if args.block:
            paths = attribution_tables(args.block, args.out)
        elif args.removal:
            paths = [removal_table(args.removal, args.counters_block, args.out, args.exclude,
                                   args.rerun_block, args.rerun_counters_block)]
        elif args.equality:
            path, equal = equality_table(args.equality, args.out, args.exclude)
            paths, rc = [path], 0 if equal else 3
        elif args.paired:
            paths = [paired_table(args.paired, args.counters_block, args.out, args.exclude)]
        elif args.paired_removal:
            paths = [paired_removal_table(args.paired_removal, args.arm, args.counters_block, args.out,
                                          args.exclude)]
        elif args.paired_lookup:
            path, equal = paired_lookup_table(args.paired_lookup, args.arm, args.counters_block, args.out,
                                              args.exclude)
            paths, rc = [path], 0 if equal else 3
        elif args.memo_counters:
            paths = [memo_counters_table(args.memo_counters, args.out)]
        elif args.reroute_tree:
            paths = [reroute_tree_table(args.reroute_tree, args.out, args.exclude)]
        elif args.repeat_ceiling:
            paths = [repeat_ceiling_table(args.repeat_ceiling, args.tree, args.out, args.exclude)]
        elif args.rc_diff:
            paths = [rc_diff_table(args.rc_diff, args.out)]
        elif args.route_paths:
            paths = [route_paths_table(args.route_paths, args.out)]
        else:
            paths = [counters_table(args.counters, args.out)]
    except AttributionError as err:
        print(f"attribute.py: {err}", file=sys.stderr)
        return 2
    for path in paths:
        print(path)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
