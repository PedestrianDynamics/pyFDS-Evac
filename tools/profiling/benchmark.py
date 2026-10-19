"""Serial benchmark harness for the pyFDS-Evac profiling study.

Each run is one fresh ``run.py`` process (or a profiler / counter wrapper
around it), started from the frozen worktree with an explicit environment.
Every run, including warm-ups, timeouts and failures, gets a manifest in
``results/raw/<run_id>/manifest.json``; nothing is discarded. Large run
outputs go to ``$STAGE/runs/<run_id>/``; the manifest stores their sha256.

Subcommands
  check                 exclusive-slot check only (JSON to stdout)
  run   [options]       run one block (see --help); --dry-run prints the plan

Timing: wall seconds measured by this parent around the child process
(``time.perf_counter``); process-tree user+sys CPU and peak RSS from
``/usr/bin/time -l`` (macOS rusage of the waited child tree). Phases are
log-marker phases (review F2), child run with PYTHONUNBUFFERED=1:
  phase_pre_run_s       start -> "Simulation started." (imports, config,
                        build_run_kwargs: FDS inventory/horizon, samplers,
                        vismap build/load)
  phase_run_scenario_s  -> summary line: all of run_scenario, i.e. JuPedSim
                        setup, spawning, initial route choice, the time loop
                        and the temp trajectory SQLite
  phase_post_run_s      -> exit: CSV/SQLite copies, agent scalars, cleanup
The evacuation loop alone is timed in-process by the counters
(``timers_s`` in counters.json), which is diagnostic, not a benchmark.

Cache states (model_handoff_g0_v2.md §1.4a, plan.md D13). fdsreader has no
cache state: the adapter (#716/#720) parses the .smv on every open, so opens and
parses are recorded per opener with seconds (cache_label), not as a cache split.
  vis first          -> --vis-cache at a fresh path in the run's output dir
  vis repeated       -> --vis-cache $STAGE/cache/<case>_vis.npz, must exist
  vis noflag         -> no --vis-cache (in-memory build every run)
Vis-cache presence and sha256 are recorded before and after each run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path(__file__).resolve().parent
ROOT = Path("/Users/chraibi/profiling-stage")
DEFAULTS = {
    "WT": os.environ.get("PROF_WT", str(ROOT / "wt_8f7d29a2")),
    "PY": os.environ.get("PROF_PY", str(ROOT / "wt_8f7d29a2/.venv/bin/python")),
    "PROF_VENV_PY": os.environ.get("PROF_PROFILER_PY", str(ROOT / "venv_prof_8f7d29a2/bin/python")),
    "STAGE": os.environ.get("PROF_STAGE", "/Users/chraibi/profiling-stage"),
}
COMMIT = "8f7d29a2e056db46183e8cccabce338c398606a1"  # main after PR #790
LOCK_SHA256 = "7f64a58db6d321441e320ad47ba960dc51d25c4a8dbaff8e8d95ba09fac25fc8"
FIX_COMMIT = "29f9d3a583ac82d796fa113143dbf9ab4dae793a"  # fix/243-fed-rate-memo head (plan g5-243-fix)
MAIN_COMMIT = "d96894acb08543798e03b220eb825c41c37c75b4"  # main after PR #812 (#239 fix, FED-rate memo); G6
LOOKUP_COMMIT = "621060020b840bff8e7caa5ca82879f31cfcaf5b"  # fix/242-faster-point-lookup head (plan g7-242-fix); G8
PRUNE_COMMIT = "f7efcf9b25b9fa9dcc001836437c2959e3a906d3"  # perf/429-exit-reach-prune head (plan g10-429-fix); G11
MAIN2_COMMIT = "b6dff31c1375f9b8a2cfe7b08a085917ebc72285"  # main after PR #814 (#243 memo, #242 lookup, #429 prune); G12
# Staged pyFDS-Evac worktrees benchmark.py may run, keyed by directory name under ROOT.
STAGES = {
    "wt_8f7d29a2": {"commit": COMMIT, "uv_lock_sha256": LOCK_SHA256},
    "wt_29f9d3a5": {"commit": FIX_COMMIT, "uv_lock_sha256": LOCK_SHA256},
    "wt_d96894ac": {"commit": MAIN_COMMIT, "uv_lock_sha256": LOCK_SHA256},
    "wt_62106002": {"commit": LOOKUP_COMMIT, "uv_lock_sha256": LOCK_SHA256},
    "wt_f7efcf9b": {"commit": PRUNE_COMMIT, "uv_lock_sha256": LOCK_SHA256},
    "wt_b6dff31c": {"commit": MAIN2_COMMIT, "uv_lock_sha256": LOCK_SHA256},
}
THREAD_ENV = {"OMP_NUM_THREADS": "4", "VECLIB_MAXIMUM_THREADS": None}
# Any process outside the benchmark's own process tree above max_foreign_cpu
# (ps %CPU) flags a run, whatever its name; the macOS system processes in
# SYSTEM_EXEMPT flag only above max_system_cpu (plan.md "System processes during
# measured blocks", decided before any G1 data). ps %CPU on macOS is a decaying
# average over roughly the last minute, not an instantaneous rate (review O10).
SLOT = {"max_load1": 2.5, "max_foreign_cpu": 20.0, "max_system_cpu": 50.0,
        "record_floor_cpu": 5.0}
SYSTEM_EXACT = {"WindowServer", "kernel_task", "mds", "mds_stores", "syspolicyd", "airportd"}
SYSTEM_PREFIX = ("mdworker",)

# ---------------------------------------------------------------- cases

W1_FDS = ("a047_pvc_h40", "a047_pvc_h40")
W3_FDS = ("t_junction_fire_2MW_PVC", "t_junction")
CMM_FDS = ("cmm_clear_air", "cognitive_map_memory")


def _w1_outputs(variant: str) -> list[str]:
    o = {
        "O_study": ["--output-route-cost-history", "{OUT}/rc.csv",
                    "--output-fed-history", "{OUT}/fed.csv",
                    "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                    "--output-route-history", "{OUT}/rh.csv",
                    "--output-exit-history", "{OUT}/exit.csv"],
        "O_norc": ["--output-fed-history", "{OUT}/fed.csv",
                   "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                   "--output-route-history", "{OUT}/rh.csv",
                   "--output-exit-history", "{OUT}/exit.csv"],
        # O_norc with rerouting off (removal experiment, see "variant_extra")
        "nrr": ["--output-fed-history", "{OUT}/fed.csv",
                "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                "--output-route-history", "{OUT}/rh.csv",
                "--output-exit-history", "{OUT}/exit.csv"],
        # O_norc with the slice sampler stubbed (G3 removal arm, PYFDS_PERF_STUB=nss)
        "nss": ["--output-fed-history", "{OUT}/fed.csv",
                "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                "--output-route-history", "{OUT}/rh.csv",
                "--output-exit-history", "{OUT}/exit.csv"],
        # O_norc with reached_stage reduced to the point test (G3 removal arm, PYFDS_PERF_STUB=nst)
        "nst": ["--output-fed-history", "{OUT}/fed.csv",
                "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                "--output-route-history", "{OUT}/rh.csv",
                "--output-exit-history", "{OUT}/exit.csv"],
        # O_norc with the pre-change SliceFieldSampler.sample patched back in (G8 arm, PYFDS_PERF_STUB=nlk)
        "nlk": ["--output-fed-history", "{OUT}/fed.csv",
                "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                "--output-route-history", "{OUT}/rh.csv",
                "--output-exit-history", "{OUT}/exit.csv"],
        # O_norc with the pre-change reached_stage patched back in (G11 arm, PYFDS_PERF_STUB=nrp)
        "nrp": ["--output-fed-history", "{OUT}/fed.csv",
                "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                "--output-route-history", "{OUT}/rh.csv",
                "--output-exit-history", "{OUT}/exit.csv"],
        # O_norc at the fix head with routing.fed_rate_memo false (G5 memo arm; see variant_scenario)
        "nomemo": ["--output-fed-history", "{OUT}/fed.csv",
                   "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                   "--output-route-history", "{OUT}/rh.csv",
                   "--output-exit-history", "{OUT}/exit.csv"],
        "O_min": ["--cleanup"],
        # untimed equivalence check of O_min (model §9.1)
        "O_min_check": ["--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                        "--output-exit-history", "{OUT}/exit.csv"],
    }
    return o[variant]


CASES = {
    "W1": {"scenario": "assets/schroeder2015_route/evac/config_gate.json", "fds": W1_FDS,
           "seed": 1, "variants": ["O_study", "O_norc", "O_min", "O_min_check", "nrr", "nss", "nst",
                                   "nomemo", "nlk", "nrp"],
           "variant_extra": {"nrr": ["--no-enable-rerouting"]},
           "variant_scenario": {"nomemo": "{STUDY}/scenarios/w1_nomemo/config_gate.json"},
           "variant_env": {"nss": {"PYFDS_PERF_STUB": "nss"}, "nst": {"PYFDS_PERF_STUB": "nst"},
                           "nlk": {"PYFDS_PERF_STUB": "nlk"}, "nrp": {"PYFDS_PERF_STUB": "nrp"}},
           "outputs": _w1_outputs, "vis": False, "label": "time-limited, 400 s observation window"},
    "W1_n100": {"scenario": "{STUDY}/scenarios/w1_scaling_n100/config_gate.json", "fds": W1_FDS,
                "seed": 1, "variants": ["O_study", "O_norc", "nrr", "nss", "nst"],
                "variant_extra": {"nrr": ["--no-enable-rerouting"]},
                "variant_env": {"nss": {"PYFDS_PERF_STUB": "nss"},
                                "nst": {"PYFDS_PERF_STUB": "nst"}},
                "outputs": _w1_outputs, "vis": False,
                "label": "scaling N=100, 400 s window"},
    "W1_n400": {"scenario": "{STUDY}/scenarios/w1_scaling_n400/config_gate.json", "fds": W1_FDS,
                "seed": 1, "variants": ["O_study"], "outputs": _w1_outputs, "vis": False,
                "label": "scaling N=400, 400 s window"},
    "W1_add": {"scenario": "assets/schroeder2015_route/evac/config_additive.json", "fds": W1_FDS,
               "seed": 1, "variants": ["O_study"], "outputs": _w1_outputs, "vis": False,
               "label": "end-to-end arm (additive)"},
    "W1_sb": {"scenario": "assets/schroeder2015_route/evac/config_gate.json", "fds": W1_FDS,
              "seed": 1, "variants": ["sb"], "extra": ["--smoke-blind"],
              "outputs": lambda v: ["--output-fed-history", "{OUT}/fed.csv",
                                    "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                                    "--output-route-history", "{OUT}/rh.csv",
                                    "--output-exit-history", "{OUT}/exit.csv"],
              "vis": False, "label": "end-to-end arm (smoke-blind)"},
    "W2": {"scenario": "assets/schroeder2015_route/evac/config_gate.json", "fds": None,
           "seed": 1, "variants": ["nf"],
           "outputs": lambda v: ["--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                                 "--output-route-history", "{OUT}/rh.csv",
                                 "--output-exit-history", "{OUT}/exit.csv"],
           "vis": False, "label": "complete evacuation, clear air"},
    "W3": {"scenario": "assets/t_junction/config_discovery.json", "fds": W3_FDS,
           "seed": 42, "variants": ["O_study"],
           "outputs": lambda v: ["--output-route-cost-history", "{OUT}/rc.csv",
                                 "--output-fed-history", "{OUT}/fed.csv",
                                 "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                                 "--output-route-history", "{OUT}/rh.csv",
                                 "--output-exit-history", "{OUT}/exit.csv"],
           "vis": True, "label": "sign legibility in smoke under no_known_exit=default_route; no exploration; time-limited 300 s"},
    "W3b_cmm": {"scenario": "{STUDY}/scenarios/w4_cmm_cap120/config_cap120.json", "fds": CMM_FDS,
                "seed": 5150, "variants": ["O_study"],
                "outputs": lambda v: ["--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                                      "--output-route-history", "{OUT}/rh.csv",
                                      "--output-exit-history", "{OUT}/exit.csv"],
                "vis": True, "label": "second visibility case, 120 s, exact-dedupe case for #236, clear-air FDS"},
    "W1r": {"scenario": "{STUDY}/scenarios/w1r_cap250/config_stream_east_cap250.json",
            "fds": ("world100_fire_4p5MW", "world_100_fire"), "seed": 1, "variants": ["O_study"],
            "outputs": _w1_outputs, "vis": False,
            "label": "end-to-end, different workload (world100, WarpDriver), cap 250 s; never pooled with W1"},
    "W4_flow_saturated": {"scenario": "{STUDY}/scenarios/w4_flow_saturated/config_flow_saturated.json",
                          "fds": None, "seed": 42, "variants": ["fixture"],
                          "outputs": lambda v: ["--output-sqlite", "{OUT}/traj.sqlite", "--cleanup",
                                                "--output-route-history", "{OUT}/rh.csv",
                                                "--output-exit-history", "{OUT}/exit.csv"],
                          "vis": False, "label": "controlled mechanism fixture (#739), not throughput"},
    "W4_iso21": {"scenario": "assets/iso_table21_coupled/config.json",
                 "fds": ("iso_table21_coupled", "iso_table21_coupled"), "seed": 420,
                 "variants": ["fixture"], "extra": ["--smoke-update-interval", "0.1"],
                 "outputs": lambda v: ["--output-smoke-history", "{OUT}/smoke.csv",
                                       "--output-sqlite", "{OUT}/traj.sqlite", "--cleanup"],
                 "vis": False, "label": "fixture, not throughput"},
}

# ---------------------------------------------------------------- helpers


def sha256_file(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sh(cmd: list[str], cwd: str | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def ps_snapshot(exclude: set[int]) -> list[dict]:
    rows = []
    for line in sh(["ps", "-Ao", "pid=,ppid=,pcpu=,rss=,comm="]).splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, ppid, pcpu, rss, comm = parts
        rows.append({"pid": int(pid), "ppid": int(ppid), "pcpu": float(pcpu),
                     "rss_kb": int(rss), "comm": comm})
    return [r for r in rows if r["pid"] not in exclude]


def descendants(root: int, rows: list[dict]) -> set[int]:
    kids, todo = {root}, [root]
    while todo:
        p = todo.pop()
        for r in rows:
            if r["ppid"] == p and r["pid"] not in kids:
                kids.add(r["pid"])
                todo.append(r["pid"])
    return kids


def is_system(comm: str) -> bool:
    base = os.path.basename(comm)
    return base in SYSTEM_EXACT or base.startswith(SYSTEM_PREFIX)


SYSTEM_DAEMON_PATHS = ("/System/", "/usr/libexec/", "/usr/sbin/", "/sbin/", "/bin/", "/usr/bin/")
# (class, lower-case path fragments), first match wins; D31(e) classes by name
OFFENDER_CLASSES = (
    ("own_session", ("claude",)),
    ("installer", ("installd", "appstoreagent", "softwareupdated")),
    ("indexer", ("mds", "mdworker", "corespotlightd", "spotlightknowledged")),
    ("app_extension", (".appex",)),
    ("user_app", ("/applications/", ".app/contents/macos/")),
    ("system_tool", ("/launchd", "/spindump")),
)


def offender_class(comm: str) -> str:
    """D31(e) tag by name: own_session, installer, indexer, app_extension, user_app,
    system_tool (launchd, spindump), system_daemon (other system path), else user.

    Descriptive only; it never enters the contamination verdict.
    """
    low = comm.lower()
    for cls, frags in OFFENDER_CLASSES:
        if any(f in low for f in frags):
            return cls
    return "system_daemon" if comm.startswith(SYSTEM_DAEMON_PATHS) else "user"


def threshold(comm: str) -> float:
    return SLOT["max_system_cpu"] if is_system(comm) else SLOT["max_foreign_cpu"]


def foreign_heavy(rows: list[dict]) -> list[dict]:
    """Processes above their threshold; *rows* must already exclude our own tree."""
    return [r for r in rows if r["pcpu"] > threshold(r["comm"])]


def foreign_recorded(rows: list[dict]) -> list[dict]:
    """What a sample keeps: every exempt-list process and any other >= record floor."""
    return [{**r, "system_exempt": is_system(r["comm"])} for r in rows
            if is_system(r["comm"]) or r["pcpu"] >= SLOT["record_floor_cpu"]]


def own_tree(rows: list[dict]) -> set[int]:
    """This benchmark process, its descendants (run under test, ps) and its parent shell."""
    return descendants(os.getpid(), rows) | {os.getppid()}


def slot_check() -> dict:
    rows = ps_snapshot(set())
    mine = own_tree(rows)
    rows = [r for r in rows if r["pid"] not in mine]
    batt = sh(["pmset", "-g", "batt"]).splitlines()
    lpm = re.search(r"lowpowermode\s+(\d)", sh(["pmset", "-g"]))
    res = {
        "time_utc": now(),
        "load_avg": list(os.getloadavg()),
        "foreign_heavy": foreign_heavy(rows),
        "foreign_recorded": foreign_recorded(rows),
        "top_cpu": sorted(rows, key=lambda r: -r["pcpu"])[:5],
        "ac_power": bool(batt) and "AC Power" in batt[0],
        "low_power_mode": lpm.group(1) if lpm else None,
    }
    res["ok"] = (res["load_avg"][0] < SLOT["max_load1"] and not res["foreign_heavy"]
                 and res["ac_power"] and res["low_power_mode"] == "0")
    return res


def stage_pin(wt: str) -> dict:
    """Commit and uv.lock sha256 a staged worktree must have; None for an unknown stage."""
    return STAGES.get(Path(wt).name, {"commit": None, "uv_lock_sha256": None})


def worktree_state(wt: str) -> dict:
    head = sh(["git", "rev-parse", "HEAD"], cwd=wt).strip()
    porcelain = sh(["git", "status", "--porcelain", "--untracked-files=all"], cwd=wt)
    ignored = [line for line in sh(["git", "status", "--porcelain", "--ignored",
                                    "--untracked-files=all"], cwd=wt).splitlines()
               if line.startswith("!!") and not re.search(r"\.venv/|__pycache__", line)]
    pin = stage_pin(wt)
    lock = sha256_file(Path(wt) / "uv.lock")
    return {"stage": Path(wt).name, "commit": head, "commit_ok": head == pin["commit"],
            "porcelain_untracked_all": porcelain.splitlines(),
            "clean": porcelain.strip() == "",
            "ignored_non_venv": ignored,
            "uv_lock_sha256": lock, "lock_ok": lock == pin["uv_lock_sha256"]}


def instrumentation_identity(counters_on: bool) -> dict:
    files = sorted((STUDY / "instrument").glob("*.py")) + [Path(__file__)]
    return {"counters_env_set": counters_on,
            "sha256": {str(p.relative_to(STUDY)): sha256_file(p) for p in files}}


def venv_fingerprint(py: str) -> dict:
    freeze = subprocess.run(["uv", "pip", "freeze", "--python", py], capture_output=True,
                            text=True).stdout
    return {"python": py, "uv_pip_freeze_sha256": hashlib.sha256(freeze.encode()).hexdigest(),
            "n_packages": len(freeze.splitlines())}


def profiler_options(profiler: str) -> dict | None:
    return {
        "none": None,
        "cprofile": {"tool": "cProfile", "mode": "deterministic", "output": "cprofile.prof"},
        "pyinstrument": {"tool": "pyinstrument 5.1.3", "mode": "statistical, wall clock, "
                         "default interval 1 ms, main thread only", "renderer": "json"},
        "scalene": {"tool": "scalene 2.3.0", "mode": "CPU (Python/native split) + memory",
                    "output": "scalene.json"},
        "memray": {"tool": "memray 1.20.0", "mode": "--native allocation tracking",
                   "output": "memray.bin"},
    }[profiler]


PROFILERS = ("none", "cprofile", "pyinstrument", "scalene", "memray")
_PROFILER_TAG = {"none": "", "cprofile": "_cpr", "pyinstrument": "_pyi", "scalene": "_scl",
                 "memray": "_mem"}


def profiler_tag(prof: str) -> str:
    """Run-id tag of a profiled run; plain runs carry none."""
    return _PROFILER_TAG[prof]


def stat_fingerprint(d: Path) -> str | None:
    if not d.exists():
        return None
    h = hashlib.sha256()
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix != ".pickle":
            st = p.stat()
            h.update(f"{p.name} {st.st_size} {int(st.st_mtime)}\n".encode())
    return h.hexdigest()


def cache_state(stage: Path, case: dict, vis_path: Path | None) -> dict:
    out = {}
    if vis_path is not None:
        out["vis_cache"] = {"path": str(vis_path), "present": vis_path.exists(),
                            "sha256": sha256_file(vis_path)}
    return out


SUMMARY_RE = re.compile(
    r"Simulation (?:finished in (?P<fin>[\d.]+) s \((?P<fe>\d+)/(?P<ft>\d+) evacuated\)"
    r"|incomplete: (?P<why>time limit reached|flow windows closed) after (?P<inc>[\d.]+) s \((?P<ie>\d+)/(?P<it>\d+) evacuated, "
    r"(?P<rem>\d+) remaining(?:, (?P<ns>\d+) not spawned)?\))")


def parse_summary(text: str) -> dict:
    m = SUMMARY_RE.search(text)
    if not m:
        return {"summary_line": None}
    g = m.groupdict()
    if g["fin"]:
        return {"summary_line": m.group(0), "status": "completed", "sim_time_s": float(g["fin"]),
                "evacuated": int(g["fe"]), "total": int(g["ft"]), "remaining": 0, "not_spawned": 0}
    end = "flows_closed" if g["why"].startswith("flow") else "time_limit"
    return {"summary_line": m.group(0), "status": "incomplete", "end_reason": end,
            "sim_time_s": float(g["inc"]),
            "evacuated": int(g["ie"]), "total": int(g["it"]), "remaining": int(g["rem"]),
            "not_spawned": int(g["ns"] or 0)}


def parse_time_l(path: Path) -> dict:
    if not path.exists():
        return {}
    t = path.read_text()

    def num(pat):
        m = re.search(pat, t)
        return float(m.group(1)) if m else None
    return {"time_real_s": num(r"([\d.]+) real"), "user_s": num(r"([\d.]+) user"),
            "sys_s": num(r"([\d.]+) sys"),
            "max_rss_bytes": num(r"(\d+)\s+maximum resident set size"),
            "peak_footprint_bytes": num(r"(\d+)\s+peak memory footprint"),
            "instructions": num(r"(\d+)\s+instructions retired")}


# ---------------------------------------------------------------- one run


def build_command(args, case, variant, seed, out: Path, rec: Path, vis_path, counters_out,
                  result_out=None, profiler: str = "none", via_wrapper: bool = False):
    """run.py outputs go to *out* (/runs/<id>); logs and profiles to *rec*."""
    prof_out = rec
    sub = {"OUT": str(out), "STUDY": str(STUDY), "STAGE": args.stage}
    scen = case.get("variant_scenario", {}).get(variant, case["scenario"]).format(**sub)
    runpy_args = ["--scenario", scen, "--seed", str(seed)]
    if case["fds"]:
        runpy_args += ["--fds-dir", f"{args.stage}/fds/{case['fds'][0]}"]
    runpy_args += case.get("extra", [])
    runpy_args += case.get("variant_extra", {}).get(variant, [])
    if vis_path is not None:
        runpy_args += ["--vis-cache", str(vis_path)]
    runpy_args += [a.format(**sub) for a in case["outputs"](variant)]
    py = args.py
    if profiler != "none":
        py = args.prof_py
    if counters_out or result_out or via_wrapper:
        head = [py, str(STUDY / "instrument" / "perf_run.py")]
    elif profiler == "cprofile":
        head = [py, "-m", "cProfile", "-o", str(prof_out / "cprofile.prof"), "run.py"]
    elif profiler == "pyinstrument":
        head = [py, "-m", "pyinstrument", "-r", "json", "-p", "processor_options.filter_threshold=0",
                "-o", str(prof_out / "pyinstrument.json"), "run.py"]
    elif profiler == "scalene":
        head = [py, "-m", "scalene", "run", "-o", str(prof_out / "scalene.json"), "run.py"]
    elif profiler == "memray":
        head = [py, "-m", "memray", "run", "--native", "-fo", str(prof_out / "memray.bin"),
                "run.py"]
    else:
        head = [py, "run.py"]
    return ["/usr/bin/time", "-l", "-o", str(rec / "time_l.txt"), *head, *runpy_args]


def child_env(stage: str, run_id: str, counters_out: Path | None, result_out: Path | None,
              create_tmp: bool, stub_env: dict | None = None,
              memo_log: Path | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in THREAD_ENV}
    for k, v in THREAD_ENV.items():
        if v is not None:
            env[k] = v
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONUNBUFFERED"] = "1"
    tmp = Path(stage) / "tmp" / run_id
    if create_tmp:
        tmp.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmp)
    env.pop("PYFDS_PERF_COUNTERS_OUT", None)
    env.pop("PYFDS_PERF_RESULT_OUT", None)
    env.pop("PYFDS_PERF_DETAIL", None)
    env.pop("PYFDS_PERF_STUB", None)
    env.pop("PYFDS_PERF_MEMO_LOG", None)
    if counters_out is not None:
        env["PYFDS_PERF_COUNTERS_OUT"] = str(counters_out)
    if memo_log is not None:
        env["PYFDS_PERF_MEMO_LOG"] = str(memo_log)
    if result_out is not None:
        env["PYFDS_PERF_RESULT_OUT"] = str(result_out)
    env.update(stub_env or {})
    return env


def prepare_caches(args, case, out_runs: Path, role: str) -> Path | None:
    stage = Path(args.stage)
    if not case["vis"]:
        return None
    if args.vis_cache == "noflag":
        return None
    if args.vis_cache == "first":
        return out_runs / "vis.npz"
    vp = stage / "cache" / f"{args.case}_vis.npz"
    if not vp.exists() and role != "warmup":
        _refuse(args, f"repeated-use vis cache {vp} is absent; run a warm-up first")
    return vp


def _refuse(args, msg: str) -> None:
    if args.dry_run:
        print(f"DRY-RUN WARNING: {msg}", flush=True)
        return
    raise SystemExit(msg)


def monitor(proc, samples: list, stop: threading.Event, period: float):
    while not stop.wait(period):
        rows = ps_snapshot(set())
        mine = own_tree(rows)
        foreign = [r for r in rows if r["pid"] not in mine]
        tree = [r for r in rows if r["pid"] in descendants(proc.pid, rows)]
        samples.append({"t": time.time(), "load1": os.getloadavg()[0],
                        "foreign_heavy": foreign_heavy(foreign),
                        "foreign_recorded": foreign_recorded(foreign),
                        "tree_rss_kb": sum(r["rss_kb"] for r in tree)})


def run_one(args, block: str, variant: str, seed: int, rep: int, role: str,
            inst: str = "none", prof: str = "none") -> dict:
    case = CASES[args.case]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    tag = (("_ctr" if inst == "counters" else "_det" if inst == "detail" else "")
           + profiler_tag(prof) + ("_cap" if args.capture_result else ""))
    run_id = f"{block}_{args.case}_{variant}{tag}_s{seed}_{role}{rep}_{stamp}"
    rec = STUDY / "results" / "raw" / run_id
    out = Path(args.stage) / "runs" / run_id
    if not args.dry_run:
        rec.mkdir(parents=True, exist_ok=False)
        out.mkdir(parents=True, exist_ok=False)
    counters_out = rec / "counters.json" if inst in ("counters", "detail") else None
    memo_log = rec / "memo.log" if inst == "counters" else None
    result_out = rec / "result_capture.json" if args.capture_result else None
    vis_path = prepare_caches(args, case, out, role)
    stub_env = case.get("variant_env", {}).get(variant)
    cmd = build_command(args, case, variant, seed, out, rec, vis_path, counters_out, result_out,
                        profiler=prof, via_wrapper=args.via_wrapper)
    scen = cmd[cmd.index("--scenario") + 1]
    scen_path = Path(scen) if scen.startswith("/") else Path(args.wt) / scen
    env = child_env(args.stage, run_id, counters_out, result_out, not args.dry_run,
                    stub_env=stub_env, memo_log=memo_log)
    if inst == "detail":
        env["PYFDS_PERF_DETAIL"] = "1"  # opt-in caller/stack counters, own overhead
    man = {
        "schema": "pyfds-evac profiling run manifest v1",
        "run_id": run_id, "block": block, "case": args.case, "variant": variant,
        "label": case["label"], "seed": seed, "repetition": rep, "role": role,
        "comparison_label": args.label,
        # capture runs go through perf_run.py and write JSON in the timed process:
        # never measurements (review C1)
        "measurement_status": "measured" if (args.exclusive and role == "rep"
                                             and not args.capture_result) else
                              ("warmup" if role == "warmup" else "not_a_measurement"),
        "profiler": prof, "profiler_options": profiler_options(prof),
        "instrumentation": {**instrumentation_identity(bool(counters_out)),
                            "result_capture_env_set": result_out is not None,
                            "entry_point": "perf_run.py"
                            if (counters_out or result_out or args.via_wrapper) else "run.py",
                            "stubs": sorted(s for s in (stub_env or {}).get(
                                "PYFDS_PERF_STUB", "").split(",") if s)},
        "venv_fingerprints": args.venv_fp,
        "cache_state_requested": {"vis": args.vis_cache if case["vis"] else None},
        "command": cmd, "cwd": args.wt,
        "env": {k: env.get(k) for k in ["PYTHONHASHSEED", "PYTHONUNBUFFERED", "TMPDIR",
                                         "PYFDS_PERF_COUNTERS_OUT", "PYFDS_PERF_RESULT_OUT", "PYFDS_PERF_DETAIL",
                                         "PYFDS_PERF_STUB", "PYFDS_PERF_MEMO_LOG",
                                         *THREAD_ENV]},
        "worktree": worktree_state(args.wt),
        "inputs": {"scenario": str(scen_path), "scenario_sha256": sha256_file(scen_path),
                   "geometry_wkt_sha256": sha256_file(scen_path.parent / "geometry.wkt"),
                   "fds_dir_stat_fingerprint": stat_fingerprint(
                       Path(args.stage) / "fds" / case["fds"][0]) if case["fds"] else None,
                   "stage_verification": "results/stage_verification_v2.json"},
        "cache_before": cache_state(Path(args.stage), case, vis_path),
        "slot_before": slot_check(),
        "outputs_dir": str(out),
        "os": {"product_version": sh(["sw_vers", "-productVersion"]).strip() or None,
               "build_version": sh(["sw_vers", "-buildVersion"]).strip() or None,
               "boottime": sh(["sysctl", "-n", "kern.boottime"]).strip() or None},
    }
    if args.dry_run:
        print(json.dumps({"run_id": run_id, "command": cmd, "cache": man["cache_before"],
                          "stubs": man["instrumentation"]["stubs"]}, indent=1))
        return man
    stdout_path, stderr_path = rec / "stdout.log", rec / "stderr.log"
    markers = {"Simulation started.": None, "Simulation finished": None,
               "Simulation incomplete": None}
    samples: list = []
    stop = threading.Event()
    man["t_start_utc"] = now()
    t0 = time.perf_counter()
    with open(stdout_path, "wb") as so, open(stderr_path, "wb") as se:
        proc = subprocess.Popen(cmd, cwd=args.wt, env=env, stdout=subprocess.PIPE, stderr=se,
                                start_new_session=True)
        th = threading.Thread(target=monitor, args=(proc, samples, stop, args.monitor_s),
                              daemon=True)
        th.start()
        buf = b""
        killed = threading.Event()

        def _kill():
            killed.set()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        timer = threading.Timer(args.timeout, _kill)
        timer.start()
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            tnow = time.perf_counter()
            so.write(chunk)
            buf = (buf + chunk)[-4096:]
            text = buf.decode(errors="replace")
            for k in markers:
                if markers[k] is None and k in text:
                    markers[k] = tnow - t0
        rc = proc.wait()
        wall = time.perf_counter() - t0
        timer.cancel()
        timed_out = killed.is_set()
        stop.set()
        th.join()
    man["t_end_utc"] = now()
    log = stdout_path.read_text(errors="replace")
    summ = parse_summary(log)
    t_loop0 = markers["Simulation started."]
    t_loop1 = markers["Simulation finished"] or markers["Simulation incomplete"]
    tl = parse_time_l(rec / "time_l.txt")
    slot_after = slot_check()
    reasons = []
    if man["slot_before"]["foreign_heavy"]:
        reasons.append("foreign_heavy_before")
    if any(s["foreign_heavy"] for s in samples):
        reasons.append("foreign_heavy_during")
    if slot_after["foreign_heavy"]:
        reasons.append("foreign_heavy_after")
    if man["slot_before"]["load_avg"][0] >= SLOT["max_load1"]:
        reasons.append("load1_before")  # may be self-load from the previous run (F4)
    if not man["slot_before"]["ac_power"] or man["slot_before"]["low_power_mode"] != "0":
        reasons.append("power")
    contaminated = bool(reasons)
    offenders: dict[str, float] = {}
    seen: dict[str, float] = {}
    ppids: dict[str, set] = {}
    for key, store in (("foreign_heavy", offenders), ("foreign_recorded", seen)):
        for snap in [man["slot_before"][key], *[x[key] for x in samples], slot_after[key]]:
            for r in snap:
                store[r["comm"]] = max(store.get(r["comm"], 0.0), r["pcpu"])
                ppids.setdefault(r["comm"], set()).add(r["ppid"])

    def detail(store: dict) -> list[dict]:
        # one entry per executable path, classed by name (offender_class)
        rows = []
        for comm, mx in sorted(store.items()):
            pp = sorted(ppids.get(comm, []))
            rows.append({"path": comm, "name": os.path.basename(comm), "ppids": pp,
                         "max_pcpu": mx, "class": offender_class(comm)})
        return rows
    man.update({
        "exit_code": rc, "timed_out": timed_out,
        "termination": ("timeout" if timed_out else "completed" if rc == 0 else
                        "flows_closed" if summ.get("end_reason") == "flows_closed" and rc == 2 else
                        "incomplete_time_limit" if rc == 2 else "failed"),
        "outcome": summ,
        "metrics": {
            "wall_s": wall, **tl,
            "cpu_s": (tl["user_s"] + tl["sys_s"]) if tl.get("user_s") is not None else None,
            "phase_method": "stdout log markers, PYTHONUNBUFFERED=1 (see module docstring)",
            "phase_pre_run_s": t_loop0,
            "phase_run_scenario_s": (t_loop1 - t_loop0) if (t_loop0 is not None and t_loop1)
            else None,
            "phase_post_run_s": (wall - t_loop1) if t_loop1 else None,
        },
        "host_during": {"samples": samples, "n_samples": len(samples),
                        "period_s": args.monitor_s, "contaminated": contaminated,
                        "contamination_reasons": reasons,
                        "offenders_max_pcpu": offenders,
                        "offenders_detail": detail(offenders),
                        "offenders_class_rule": ("class by executable path: "
                                                 f"{[(c, list(f)) for c, f in OFFENDER_CLASSES]}, "
                                                 f"then system_daemon for a path under {list(SYSTEM_DAEMON_PATHS)}, "
                                                 "else user; descriptive, not part of the verdict"),
                        "recorded_max_pcpu": {k: {"max_pcpu": v, "system_exempt": is_system(k)}
                                              for k, v in sorted(seen.items())},
                        "rule": (f"any process outside the own tree > {SLOT['max_foreign_cpu']} % CPU, "
                                 f"system list {sorted(SYSTEM_EXACT)} + {list(SYSTEM_PREFIX)}* "
                                 f"> {SLOT['max_system_cpu']} %; ps %CPU (decaying average); "
                                 "before / every period_s / after; recorded: system list always, "
                                 f"others >= {SLOT['record_floor_cpu']} %")},
        "slot_after": slot_after,
        "cache_after": cache_state(Path(args.stage), case, vis_path),
        "worktree_after": worktree_state(args.wt),
        "output_sha256": {p.name: sha256_file(p) for p in sorted(out.glob("*")) if p.is_file()},
        "counters_path": str(counters_out) if counters_out else None,
        "result_capture_path": str(result_out) if result_out else None,
    })
    traj = out / "traj.sqlite"
    if traj.exists():
        sys.path.insert(0, str(STUDY))
        from traj_hash import traj_hash
        man["trajectory_hash_repr_v1"] = traj_hash(str(traj))
    app_man = out / "traj.manifest.json"
    if app_man.exists():
        man["app_manifest"] = json.loads(app_man.read_text())
    man["cache_label"] = derive_cache_label(man, counters_out)
    (rec / "manifest.json").write_text(json.dumps(man, indent=1, default=str) + "\n")
    print(f"{run_id}: exit {rc} wall {wall:.2f}s cpu {man['metrics']['cpu_s']} "
          f"rss {tl.get('max_rss_bytes')} contaminated={contaminated}", flush=True)
    return man


def derive_cache_label(man: dict, counters_out: Path | None) -> dict:
    """Label the vismap cache state; record fdsreader opens per opener (D13)."""
    req = man["cache_state_requested"]
    before = man["cache_before"]
    lab = {"requested": req}
    vc = before.get("vis_cache")
    if vc is not None:
        lab["vis"] = "repeated_use" if vc["present"] else "first_use"
    elif req.get("vis"):
        lab["vis"] = "noflag"
    if counters_out and counters_out.exists():
        c = json.loads(counters_out.read_text())
        ev = c.get("events", {})
        inits = ev.get("fdsreader_init", [])
        # Every open parses (adapter policy #716/#720: cache off). Seconds are
        # a setup sub-phase, not loop or vismap-kernel time.
        lab["fds_opens_per_process"] = len(inits)
        lab["fds_open_seconds_total"] = sum(e["seconds_init"] for e in inits) if inits else None
        by = {}
        for e in inits:
            d = by.setdefault(e.get("opener"), {"opens": 0, "seconds": 0.0})
            d["opens"] += 1
            d["seconds"] += e["seconds_init"]
        lab["fds_opens_by_opener"] = by
        vm = [e["event"] for e in ev.get("vismap", [])]
        lab["vismap_events"] = vm
        lab["counters_agree"] = not (lab.get("vis") == "repeated_use"
                                     and not any(e in vm for e in ("load_hit", "clear_air_loaded")))
    return lab


# ---------------------------------------------------------------- block


def order(combos: list, reps: int, scheme: str, flip: bool = False) -> list[tuple]:
    """Interleave paired combos: alternate = ABAB..., abba = AB BA AB ...

    flip starts abba with the reversed pair (BA AB ...), so a one-rep block can
    alternate the arm order across seeds (G5)."""
    seq = []
    for r in range(reps):
        cs = combos if (scheme == "alternate" or (r + flip) % 2 == 0) else list(reversed(combos))
        seq += [(c, r + 1) for c in cs]
    return seq


def cmd_run(args):
    case = CASES[args.case]
    variants = args.variants.split(",") if args.variants else case["variants"][:1]
    for v in variants:
        if v not in case["variants"]:
            raise SystemExit(f"variant {v} not defined for {args.case}")
    need = [v for v in variants if case.get("variant_env", {}).get(v)]
    if need and not args.via_wrapper:
        raise SystemExit(f"stub variants need --via-wrapper: {','.join(need)}")
    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else [case["seed"]]
    slot = slot_check()
    print(json.dumps({"slot_before_block": slot}, default=str)[:600], flush=True)
    if args.exclusive and not slot["ok"] and not args.dry_run:
        raise SystemExit("exclusive slot check failed; block not started (use --shared for "
                         "non-measurement development runs)")
    ws = worktree_state(args.wt)
    if not (ws["commit_ok"] and ws["clean"] and ws["lock_ok"]):
        raise SystemExit(f"worktree not frozen/clean: {json.dumps(ws)[:800]}")
    block = args.block
    insts = args.instrument.split(",")
    profs = args.profiler.split(",")
    combos = [(v, i, p) for v in variants for i in insts for p in profs]
    for n, seed in enumerate(seeds):
        for w in range(args.warmup):
            for v, i, p in combos:
                run_one(args, block, v, seed, w + 1, "warmup", i, p)
        for (v, i, p), r in order(combos, args.reps, args.order,
                                  flip=(args.order == "abba" and n % 2 == 1)):
            run_one(args, block, v, seed, r, "rep", i, p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    r = sub.add_parser("run")
    r.add_argument("--block", required=True, help="block name, prefix of every run ID")
    r.add_argument("--case", required=True, choices=sorted(CASES))
    r.add_argument("--variants", help="comma list; paired variants are interleaved")
    r.add_argument("--seeds", help="comma list (default: case seed)")
    r.add_argument("--reps", type=int, default=5)
    r.add_argument("--warmup", type=int, default=1, help="untimed warm-up runs per variant/seed")
    r.add_argument("--order", choices=["alternate", "abba"], default="alternate")
    r.add_argument("--vis-cache", choices=["first", "repeated", "noflag"], default="repeated")
    r.add_argument("--instrument", default="none",
                   help="none, counters, detail (counters plus caller/stack counters) or a comma list "
                        "such as none,counters (paired, interleaved) for overhead")
    r.add_argument("--profiler", default="none",
                   help="none, cprofile, pyinstrument, scalene, memray or a comma list such as "
                        "none,pyinstrument (paired, interleaved) for overhead")
    r.add_argument("--label", default="baseline",
                   help="comparison label: baseline / end-to-end / controlled-cost / diagnostic")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--exclusive", action="store_true", help="measured block: slot check must pass")
    g.add_argument("--shared", action="store_true", help="development run, never a measurement")
    r.add_argument("--timeout", type=float, default=300.0)
    r.add_argument("--monitor-s", type=float, default=2.0)
    r.add_argument("--capture-result", action="store_true",
                   help="also dump cognitive_map_history and metrics (equivalence item 12); "
                        "entry point becomes perf_run.py, so never for timed baselines")
    r.add_argument("--via-wrapper", action="store_true",
                   help="every run of the block enters through instrument/perf_run.py (stub arms "
                        "require it; the plain baseline of a stub block uses it too so all arms "
                        "share one entry point)")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--wt", default=DEFAULTS["WT"])
    r.add_argument("--py", default=DEFAULTS["PY"])
    r.add_argument("--prof-py", default=DEFAULTS["PROF_VENV_PY"])
    r.add_argument("--stage", default=DEFAULTS["STAGE"])
    args = ap.parse_args()
    if args.cmd == "check":
        print(json.dumps(slot_check(), indent=1, default=str))
        return
    if not set(args.instrument.split(",")) <= {"none", "counters", "detail"}:
        raise SystemExit("--instrument takes none, counters, detail or a comma list")
    if not set(args.profiler.split(",")) <= set(PROFILERS):
        raise SystemExit("--profiler takes " + ", ".join(PROFILERS) + " or a comma list")
    any_prof = any(p != "none" for p in args.profiler.split(","))
    if any(i != "none" for i in args.instrument.split(",")) and any_prof:
        raise SystemExit("counters and profilers are separate runs")
    if args.via_wrapper and any_prof:
        raise SystemExit("--via-wrapper and profilers are separate runs")
    if any_prof and args.timeout == 300.0:
        args.timeout = 900.0
    args.venv_fp = {"baseline": venv_fingerprint(args.py),
                    "profiling": venv_fingerprint(args.prof_py) if any_prof else None}
    cmd_run(args)


if __name__ == "__main__":
    main()
