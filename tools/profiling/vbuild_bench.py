"""Harness runner for the V-build kernel experiment (plan.md D15, D24).

Runs vbuild.py in fresh processes with the benchmark harness conventions: slot
check, frozen-worktree check, host monitor, /usr/bin/time -l, one manifest per
run under results/raw/<run_id>/ (schema of benchmark.py). Per block:

  1 warm-up + N plain repetitions   vbuild.py --plain --no-stats   (no hooks: the timings
                                    that count; peak RSS excludes the after-timing statistics)
  1 instrumented diagnostic run     vbuild.py with perf_counters and the frame statistics
                                    (stage timers, _get_visibility_array counts, distinct
                                    frames, consecutive-frame change); its totals are
                                    instrumented and never mixed with the plain ones.

Limits (D24): 300 s wall per plain run, 900 s per profiled run (--profiler
cprofile), 8 GB tree RSS; a run over a limit is killed and recorded, never dropped.
Comparison label: controlled kernel experiment, per-(t, wp) cost; no evacuation, no
end-to-end claim; never quoted against the #236/#241 issue figures without the
fdsvismap-revision caveat.

Usage:
  PY vbuild_bench.py --block G1vbuild --exclusive [--n 1001] [--reps 5] [--warmup 1]
  PY vbuild_bench.py --block T --shared --n 10 --reps 1 --warmup 0 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path(__file__).resolve().parent
sys.path.insert(0, str(STUDY))
import benchmark as B  # noqa: E402

GB = 1 << 30


def run_one(args, role: str, rep: int, inst: str) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    tag = "plain" if inst == "plain" else "det"
    run_id = f"{args.block}_VBUILD_n{args.n}_{tag}_s0_{role}{rep}_{stamp}"
    rec = STUDY / "results" / "raw" / run_id
    out = Path(args.stage) / "runs" / run_id
    result_json = rec / "vbuild.json"
    vb = [args.py, str(STUDY / "vbuild.py"), str(args.deck), str(args.fds), str(args.n),
          str(result_json)]
    vb += ["--plain", "--no-stats"] if inst == "plain" else []
    if args.profiler == "cprofile":
        vb = [args.py, "-m", "cProfile", "-o", str(rec / "cprofile.prof"), *vb[1:]]
    cmd = ["/usr/bin/time", "-l", "-o", str(rec / "time_l.txt"), *vb]
    limit_s = args.timeout_profiled if args.profiler != "none" else args.timeout_plain
    env = B.child_env(args.stage, run_id, None, None, not args.dry_run)
    ws = B.worktree_state(args.wt)
    man = {
        "schema": "pyfds-evac profiling run manifest v1", "run_id": run_id, "block": args.block,
        "case": "VBUILD", "variant": f"n{args.n}_{tag}", "label": "controlled kernel experiment",
        "seed": None, "repetition": rep, "role": role, "comparison_label": args.label,
        "measurement_status": ("warmup" if role == "warmup" else
                               "measured" if args.exclusive and inst == "plain" else
                               "not_a_measurement"),
        "profiler": args.profiler,
        "instrumentation": {"counters_env_set": inst != "plain", "entry_point": "vbuild.py",
                            "sha256": {"vbuild.py": B.sha256_file(STUDY / "vbuild.py"),
                                       "instrument/perf_counters.py":
                                       B.sha256_file(STUDY / "instrument/perf_counters.py"),
                                       "vbuild_bench.py": B.sha256_file(Path(__file__))}},
        "venv_fingerprints": {"baseline": B.venv_fingerprint(args.py), "profiling": None},
        "command": cmd, "cwd": args.wt, "limits": {"wall_s": limit_s, "rss_bytes": args.rss_gb * GB},
        "worktree": ws, "outputs_dir": str(out),
        "inputs": {"deck": str(args.deck), "deck_sha256": B.sha256_file(Path(args.deck)),
                   "fds_dir": str(args.fds), "n_time_points_requested": args.n},
        "slot_before": B.slot_check(),
    }
    if args.dry_run:
        print(json.dumps({"run_id": run_id, "command": cmd, "limits": man["limits"]}, indent=1))
        return man
    if not (ws["commit_ok"] and ws["clean"] and ws["uv_lock_sha256"] == B.LOCK_SHA256):
        raise SystemExit(f"worktree not frozen/clean: {json.dumps(ws)[:600]}")
    rec.mkdir(parents=True, exist_ok=False)
    out.mkdir(parents=True, exist_ok=False)
    samples: list = []
    stop = threading.Event()
    man["t_start_utc"] = B.now()
    t0 = time.perf_counter()
    with open(rec / "stdout.log", "wb") as so, open(rec / "stderr.log", "wb") as se:
        proc = subprocess.Popen(cmd, cwd=args.wt, env=env, stdout=so, stderr=se,
                                start_new_session=True)
        th = threading.Thread(target=B.monitor, args=(proc, samples, stop, args.monitor_s),
                              daemon=True)
        th.start()
        killed_for = None
        while proc.poll() is None:
            time.sleep(0.5)
            if time.perf_counter() - t0 > limit_s:
                killed_for = "timeout"
            elif samples and samples[-1]["tree_rss_kb"] * 1024 > args.rss_gb * GB:
                killed_for = "rss_limit"
            if killed_for:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                break
        rc = proc.wait()
        wall = time.perf_counter() - t0
        stop.set()
        th.join()
    man["t_end_utc"] = B.now()
    tl = B.parse_time_l(rec / "time_l.txt")
    slot_after = B.slot_check()
    reasons = []
    if man["slot_before"]["foreign_heavy"]:
        reasons.append("foreign_heavy_before")
    if any(s["foreign_heavy"] for s in samples):
        reasons.append("foreign_heavy_during")
    if slot_after["foreign_heavy"]:
        reasons.append("foreign_heavy_after")
    if man["slot_before"]["load_avg"][0] >= B.SLOT["max_load1"]:
        reasons.append("load1_before")
    if not man["slot_before"]["ac_power"] or man["slot_before"]["low_power_mode"] != "0":
        reasons.append("power")
    result = json.loads(result_json.read_text()) if result_json.exists() else None
    man.update({
        "exit_code": rc, "timed_out": killed_for == "timeout",
        "termination": killed_for or ("completed" if rc == 0 else "failed"),
        "outcome": {"summary_line": None, "status": "completed" if rc == 0 else "failed"},
        "vbuild_result": result,
        "metrics": {"wall_s": wall, **tl,
                    "cpu_s": (tl["user_s"] + tl["sys_s"]) if tl.get("user_s") is not None else None,
                    "build_total_s": result["seconds"]["total"] if result else None,
                    "build_vismap_s": result["seconds"]["_build_vismap_total"] if result else None,
                    "vis_bool_array_s": result["seconds"]["_vis_bool_array"] if result else None,
                    "vis_metre_array_s": result["seconds"]["_vis_metre_array"] if result else None,
                    "method_internal": result["method"] if result else None},
        "host_during": {"samples": samples, "slot_after": slot_after,
                        "contaminated": bool(reasons), "contamination_reasons": reasons,
                        "max_tree_rss_kb": max((s["tree_rss_kb"] for s in samples), default=None)},
        "worktree_after": B.worktree_state(args.wt),
    })
    if result is None:
        man["measurement_status"] = "not_a_measurement"
    (rec / "manifest.json").write_text(json.dumps(man, indent=1, default=str) + "\n")
    print(f"{run_id}: exit {rc} wall {wall:.2f}s build_total "
          f"{man['metrics']['build_total_s']} rss {tl.get('max_rss_bytes')} "
          f"contaminated={bool(reasons)}", flush=True)
    return man


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--block", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--exclusive", action="store_true")
    g.add_argument("--shared", action="store_true")
    ap.add_argument("--n", type=int, default=1001, help="time points (the deck has 1001)")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--no-diagnostic", action="store_true", help="skip the instrumented run")
    ap.add_argument("--profiler", choices=["none", "cprofile"], default="none")
    ap.add_argument("--label", default="controlled-cost")
    ap.add_argument("--timeout-plain", type=float, default=300.0)
    ap.add_argument("--timeout-profiled", type=float, default=900.0)
    ap.add_argument("--rss-gb", type=float, default=8.0)
    ap.add_argument("--monitor-s", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wt", default=B.DEFAULTS["WT"])
    ap.add_argument("--py", default=B.DEFAULTS["PY"])
    ap.add_argument("--stage", default=B.DEFAULTS["STAGE"])
    ap.add_argument("--deck", default=None, help="default: assets/fed_incap_co_2000ppm/config.json in --wt")
    ap.add_argument("--fds", default=None, help="default: $STAGE/fds/fed_incap_co_2000ppm")
    args = ap.parse_args()
    args.deck = args.deck or f"{args.wt}/assets/fed_incap_co_2000ppm/config.json"
    args.fds = args.fds or f"{args.stage}/fds/fed_incap_co_2000ppm"
    if args.exclusive and not args.dry_run:
        slot = B.slot_check()
        if not slot["ok"]:
            raise SystemExit("exclusive slot check failed; block not started")
    for w in range(args.warmup):
        run_one(args, "warmup", w + 1, "plain")
    for r in range(args.reps):
        run_one(args, "rep", r + 1, "plain")
    if not args.no_diagnostic:
        run_one(args, "rep", 1, "instrumented")


if __name__ == "__main__":
    main()
