"""Regenerate results/summary.csv and results/summary_groups.csv from raw runs.

Usage: python analyse.py [--include-dev]

summary.csv: one row per run manifest (schema v1), every run including
warm-ups, timeouts, failures, contaminated and development runs.
Missing values stay empty (never zero).

summary_groups.csv: median, Q1, Q3, IQR and n per group of *measured*,
uncontaminated runs. Groups never pool different case, variant, seed, cache
state, instrumentation, profiler, commit or comparison label. Contaminated
measured runs are counted in n_contaminated and left out of the statistics.
Figures are produced separately from these frozen tables.

Flag handling (plan.md D31): flag_status is "inconclusive" when more than one
third of a group's runs are flagged, "record_only" for the determinism and
output-check blocks (counts only, no statistics), else "ok". The clean table
blanks every statistic when n_used < 3 (n_used stays). The flagged-inclusive
table adds wall_s_median_sensitivity: the wall median without the runs that
D31 rule (b) excludes, named in excluded_runs, with n_sensitivity. A run is
excluded when a process named in D31B_NAMES is among its offenders
(host_during.offenders_max_pcpu keys) or its instructions (metrics.instructions,
the same /usr/bin/time -l value as time_l.txt) deviate more than 1 % from the
median of its group's runs; with fewer than 3 instruction values in a group only
the name test applies.
"""

import argparse
import csv
import json
import statistics
from pathlib import Path

STUDY = Path(__file__).resolve().parent
RAW = STUDY / "results" / "raw"
METRICS = ["wall_s", "cpu_s", "max_rss_bytes", "peak_footprint_bytes", "phase_pre_run_s",
           "phase_run_scenario_s", "phase_post_run_s"]
GROUP = ["block", "case", "variant", "seed", "vis_cache", "instrument_level", "instrumented",
         "result_capture", "entry_point", "profiler", "commit", "comparison_label"]


# D31 (b): path fragments of installers, indexers, user apps and the own session
D31B_NAMES = ("installd", "appstoreagent", "softwareupdated", "mds", "mdworker",
              "corespotlightd", "spotlightknowledged", "/applications/",
              "/system/applications/", "claude")
INSTR_TOL = 0.01
# D31 (c): determinism and output-check blocks are records only, never statistics
RECORD_ONLY_BLOCKS = {"G1b_ovhD", "G1b_scale400", "G1b_det", "G1b_outchk", "G1det", "G1outchk",
                     "G4det", "G5_memo_W1", "G5_ctr_W1", "G6_nss_W1", "G6_ctr_W1",
                     "G8_lk_W1", "G8_ctr_W1", "G11_pr_W1", "G11_ctr_W1",
                     "G12_nrr_W1", "G12_nss_W1", "G12_ctr_W1",
                     "G13_prof_W1", "G13_det_W1", "G14_cnt_W1"}


def d31b_hits(m):
    offs = m.get("host_during", {}).get("offenders_max_pcpu") or {}
    return sorted({n for path in offs for n in D31B_NAMES if n in path.lower()})


def counters_of(m):
    p = m.get("counters_path")
    if not p or not Path(p).exists():
        return {}
    return json.loads(Path(p).read_text()).get("counters", {})


def instrument_level(m):
    """none / counters / detail (detail adds the caller-keyed group, PYFDS_PERF_DETAIL=1)."""
    if not m["instrumentation"]["counters_env_set"]:
        return "none"
    return "detail" if (m.get("env") or {}).get("PYFDS_PERF_DETAIL") else "counters"


def row_of(m):
    met = m.get("metrics", {})
    lab = m.get("cache_label", {})
    out = m.get("outcome", {})
    c = counters_of(m)
    r = {
        "run_id": m["run_id"], "block": m["block"], "case": m["case"], "variant": m["variant"],
        "seed": m["seed"], "role": m["role"], "repetition": m["repetition"],
        "measurement_status": m["measurement_status"],
        "contaminated": m.get("host_during", {}).get("contaminated"),
        "instructions": met.get("instructions"),
        "d31b_offenders": ";".join(d31b_hits(m)),
        "comparison_label": m.get("comparison_label"),
        "commit": m["worktree"]["commit"], "worktree_clean": m["worktree"]["clean"],
        "instrumented": m["instrumentation"]["counters_env_set"],
        "instrument_level": instrument_level(m),
        "result_capture": m["instrumentation"].get("result_capture_env_set", False),
        "entry_point": m["instrumentation"].get("entry_point", "run.py"),
        "profiler": m["profiler"],
        "vis_cache": lab.get("vis"),
        "fds_opens_per_process": lab.get("fds_opens_per_process"),
        "fds_open_seconds_total": lab.get("fds_open_seconds_total"),
        "cache_counters_agree": lab.get("counters_agree"),
        "exit_code": m.get("exit_code"), "termination": m.get("termination"),
        "sim_time_s": out.get("sim_time_s"), "evacuated": out.get("evacuated"),
        "total": out.get("total"), "remaining": out.get("remaining"),
        "not_spawned": out.get("not_spawned"),
        "trajectory_hash_repr_v1": m.get("trajectory_hash_repr_v1"),
        "agent_steps": c.get("agent_steps"), "iterations": c.get("iterations"),
        "reroute_evaluations": c.get("reroute_evaluations"),
        "sign_queries": c.get("node_is_visible_sign_calls"),
    }
    hz = RAW / m["run_id"] / "horizon.json"
    h = json.loads(hz.read_text()) if hz.exists() else {}
    r["max_bound"], r["held_share"] = h.get("max_bound_s"), h.get("held_share")
    r["warning_count"] = h.get("warning_count")
    for k in METRICS:
        r[k] = met.get(k)
    # run_scenario includes JuPedSim setup and spawning, not only the loop (F2)
    rs, sim = r["phase_run_scenario_s"], r["sim_time_s"]
    r["run_scenario_s_per_sim_s"] = rs / sim if rs is not None and sim else None
    r["run_scenario_us_per_agent_step"] = (rs * 1e6 / r["agent_steps"]
                                           if rs is not None and r["agent_steps"] else None)
    r["contamination_reasons"] = ";".join(m.get("host_during", {}).get("contamination_reasons", []))
    return r


def quartiles(xs):
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0], xs[0], xs[0]
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return q[0], statistics.median(xs), q[2]


MIN_CLEAN_FOR_SPREAD = 3


def sensitivity(rs):
    """D31 (b): wall median without excluded runs; returns (median, n, excluded ids)."""
    ins = [r["instructions"] for r in rs if r["instructions"] is not None]
    ref = statistics.median(ins) if len(ins) >= 3 else None
    bad = [r["run_id"] for r in rs if r["d31b_offenders"] or (
        ref and r["instructions"] is not None and abs(r["instructions"] / ref - 1) > INSTR_TOL)]
    xs = [r["wall_s"] for r in rs if r["run_id"] not in bad and r["wall_s"] is not None
          and r["termination"] != "timeout"]
    return (statistics.median(xs) if xs else None), len(xs), ";".join(bad)


def aggregate(groups, clean_only):
    out = []
    for key, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        clean = [r for r in rs if not r["contaminated"]]
        used = clean if clean_only else rs
        g = dict(zip(GROUP + ["measurement_status"], key))
        g["table"] = "clean" if clean_only else "flagged_inclusive"
        g["n_runs"], g["n_contaminated"] = len(rs), len(rs) - len(clean)
        g["n_used"] = len(used)
        rec_only = g["block"] in RECORD_ONLY_BLOCKS
        g["record_only"] = rec_only
        g["flag_status"] = ("record_only" if rec_only else
                            "inconclusive" if 3 * g["n_contaminated"] > g["n_runs"] else "ok")
        g["n_failed_or_timeout"] = sum(r["termination"] in ("failed", "timeout") for r in rs)
        g["trajectory_hashes"] = len({r["trajectory_hash_repr_v1"] for r in rs
                                      if r["trajectory_hash_repr_v1"]})
        for k in METRICS + ["run_scenario_s_per_sim_s", "run_scenario_us_per_agent_step"]:
            xs = [r[k] for r in used if r[k] is not None and r["termination"] != "timeout"]
            g[f"{k}_median"] = g[f"{k}_q1"] = g[f"{k}_q3"] = g[f"{k}_iqr"] = None
            if not xs or rec_only or (clean_only and len(xs) < MIN_CLEAN_FOR_SPREAD):
                continue
            q1, med, q3 = quartiles(xs)
            g[f"{k}_median"] = med
            if len(xs) >= MIN_CLEAN_FOR_SPREAD:  # no spread from fewer than 3 runs
                g[f"{k}_q1"], g[f"{k}_q3"], g[f"{k}_iqr"] = q1, q3, q3 - q1
        if not clean_only:
            sens = (None, None, "") if rec_only else sensitivity(rs)
            g["wall_s_median_sensitivity"], g["n_sensitivity"], g["excluded_runs"] = sens
        out.append(g)
    return out


def write_groups(path, out):
    with open(path, "w", newline="") as f:
        if out:
            w = csv.DictWriter(f, fieldnames=list(out[0]))
            w.writeheader()
            w.writerows(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-dev", action="store_true",
                    help="also group non-measurement runs (labelled, for harness checks)")
    a = ap.parse_args()
    rows = []
    for mf in sorted(RAW.glob("*/manifest.json")):
        m = json.loads(mf.read_text())
        if m.get("schema") != "pyfds-evac profiling run manifest v1":
            continue
        rows.append(row_of(m))
    cols = list(rows[0]) if rows else ["run_id"]
    with open(STUDY / "results" / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    groups = {}
    for r in rows:
        if r["role"] == "warmup":
            continue
        if r["measurement_status"] != "measured" and not a.include_dev:
            continue
        groups.setdefault(tuple(r[k] for k in GROUP + ["measurement_status"]), []).append(r)
    # Clean table (default): runs flagged contaminated by the predeclared rule are excluded.
    # Flagged-inclusive table: every run of the group, labelled; never pools across blocks.
    out_clean = aggregate(groups, clean_only=True)
    out_all = aggregate(groups, clean_only=False)
    write_groups(STUDY / "results" / "summary_groups.csv", out_clean)
    write_groups(STUDY / "results" / "summary_groups_all.csv", out_all)
    print(f"{len(rows)} runs -> results/summary.csv; {len(out_clean)} clean groups -> results/summary_groups.csv, {len(out_all)} flagged-inclusive -> results/summary_groups_all.csv")


if __name__ == "__main__":
    main()
