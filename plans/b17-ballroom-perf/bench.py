"""Interleaved wall/CPU/RSS timing of the ballroom run, rerouting on vs off.

    python bench.py run --fire DIR --out DIR --seed 1 --reps 5 [--warmup]
    python bench.py summary --out DIR

Runs `pyfds-evac` in fresh processes, serially, in abba order. One JSON
line per run goes to <out>/runs.jsonl. Rerouting off changes trajectories,
so the difference is an end-to-end ceiling, not a per-subsystem cost.
"""

import argparse
import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
FLAGS = {"base": [], "nrr": ["--no-enable-rerouting"]}


def sha(path):
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def run_one(fire, out, variant, seed, rep):
    run_dir = out / f"{variant}_seed{seed:02d}_rep{rep}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pyfds-evac",
        "--scenario",
        str(HERE / "scenario"),
        "--fds-dir",
        str(fire),
        "--seed",
        str(seed),
        "--smoke-slice-height",
        "2.0",
        "--output-exit-history",
        str(run_dir / "exits.csv"),
        "--output-fed-summary",
        str(run_dir / "fed.csv"),
        *FLAGS[variant],
    ]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    load_before = os.getloadavg()[0]
    t0 = time.perf_counter()
    with open(run_dir / "run.log", "w") as log:
        rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    wall = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "variant": variant,
        "seed": seed,
        "rep": rep,
        "rc": rc,
        "wall_s": round(wall, 2),
        "cpu_user_s": round(after.ru_utime - before.ru_utime, 2),
        "cpu_sys_s": round(after.ru_stime - before.ru_stime, 2),
        "maxrss_mb": round(after.ru_maxrss / 1024, 1),  # Linux: KiB
        "load1_before": load_before,
        "load1_after": os.getloadavg()[0],
        "exits_sha": sha(run_dir / "exits.csv"),
        "fed_sha": sha(run_dir / "fed.csv"),
        "cmd": cmd,
    }


def cmd_run(a):
    a.out.mkdir(parents=True, exist_ok=True)
    jsonl = a.out / "runs.jsonl"
    if a.warmup:
        rec = run_one(a.fire, a.out, "base", a.seed, 0)
        print("warmup", rec["wall_s"], "rc", rec["rc"], flush=True)
    for rep in range(1, a.reps + 1):
        order = ["base", "nrr"] if rep % 2 else ["nrr", "base"]
        for variant in order:
            rec = run_one(a.fire, a.out, variant, a.seed, rep)
            with open(jsonl, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(variant, a.seed, rep, rec["wall_s"], "rc", rec["rc"], flush=True)


def iqr(values):
    if len(values) < 4:
        return None
    q = statistics.quantiles(values, n=4, method="exclusive")
    return round(q[2] - q[0], 2)


def cmd_summary(a):
    rows = [json.loads(line) for line in (a.out / "runs.jsonl").open()]
    seeds = sorted({r["seed"] for r in rows})
    for seed in seeds:
        print(f"seed {seed}")
        med = {}
        for variant in FLAGS:
            ok = [
                r
                for r in rows
                if r["seed"] == seed and r["variant"] == variant and r["rc"] == 0
            ]
            bad = sum(
                1 for r in rows if r["seed"] == seed and r["variant"] == variant
            ) - len(ok)
            walls = [r["wall_s"] for r in ok]
            if not walls:
                print(f"  {variant}: no usable runs ({bad} failed)")
                continue
            med[variant] = statistics.median(walls)
            print(
                f"  {variant}: n={len(ok)} failed={bad} median={med[variant]:.1f} s "
                f"IQR={iqr(walls)} all={walls} "
                f"rss={statistics.median(r['maxrss_mb'] for r in ok):.0f} MB "
                f"exits_sha={sorted({r['exits_sha'] for r in ok})}"
            )
        if len(med) == 2:
            diff = med["base"] - med["nrr"]
            print(
                f"  base - nrr = {diff:.1f} s per run, {10 * diff:.0f} s per ten-run study "
                f"(bar 5% of ten base runs = {0.5 * med['base']:.0f} s)"
            )


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--fire", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--reps", type=int, default=5)
    r.add_argument("--warmup", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    {"run": cmd_run, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
