"""Write environment.json for the profiling study (read-only inventory).

Usage: VENV_PYTHON=/path/to/.venv/bin/python python collect_env.py WORKTREE OUT.json
       [--profiling-python /path/to/venv_prof/bin/python]

Records OS/CPU/RAM/power, the target commit and lockfile hash, Python and
key dependency versions with their import locations (per interpreter),
NumPy BLAS, thread-related environment variables and profiler availability
notes. Secrets and host identifiers beyond the model name are not stored.
"""

import argparse
import hashlib
import json
import os
import pathlib
import platform
import subprocess
from datetime import datetime, timezone

PACKAGES = [
    "pyfds_evac",
    "jupedsim",
    "fdsreader",
    "fdsvismap",
    "numpy",
    "scipy",
    "shapely",
    "pandas",
    "matplotlib",
    "skimage",
]
PROFILERS = ["memray", "scalene", "pyinstrument"]
THREAD_VARS = [
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "PYTHONHASHSEED",
    "PYTHONOPTIMIZE",
    "PYTHONDONTWRITEBYTECODE",
]

PROBE = r"""
import importlib, importlib.metadata as md, json, sys
names = json.loads(sys.argv[1])
dist = {"pyfds_evac": "pyfds-evac", "skimage": "scikit-image"}
out = {"python": sys.version, "executable": sys.executable, "packages": {}}
for n in names:
    try:
        m = importlib.import_module(n)
        try:
            v = md.version(dist.get(n, n))
        except Exception:
            v = getattr(m, "__version__", None)
        out["packages"][n] = {"version": v, "location": getattr(m, "__file__", None)}
    except Exception as exc:
        out["packages"][n] = {"version": None, "location": None, "error": repr(exc)}
try:
    import numpy
    cfg = numpy.show_config(mode="dicts")
    out["numpy_blas"] = cfg["Build Dependencies"]["blas"]["name"]
    out["numpy_lapack"] = cfg["Build Dependencies"]["lapack"]["name"]
except Exception as exc:
    out["numpy_blas"] = None
print(json.dumps(out))
"""


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def probe(python, names):
    res = subprocess.run(
        [python, "-c", PROBE, json.dumps(names)], capture_output=True, text=True
    )
    return json.loads(res.stdout) if res.returncode == 0 else {"error": res.stderr[-2000:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("worktree")
    ap.add_argument("out")
    ap.add_argument("--profiling-python")
    a = ap.parse_args()
    wt = pathlib.Path(a.worktree)
    venv_py = os.environ.get("VENV_PYTHON", str(wt / ".venv/bin/python"))
    lock = wt / "uv.lock"
    env = {
        "collected_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": {
            "product": sh("sw_vers", "-productName"),
            "version": sh("sw_vers", "-productVersion"),
            "build": sh("sw_vers", "-buildVersion"),
            "kernel": platform.release(),
            "arch": platform.machine(),
        },
        "hardware": {
            "model": sh("sysctl", "-n", "hw.model"),
            "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string"),
            "logical_cpus": int(sh("sysctl", "-n", "hw.ncpu") or 0) or None,
            "performance_cores": int(sh("sysctl", "-n", "hw.perflevel0.physicalcpu") or 0) or None,
            "efficiency_cores": int(sh("sysctl", "-n", "hw.perflevel1.physicalcpu") or 0) or None,
            "ram_bytes": int(sh("sysctl", "-n", "hw.memsize") or 0) or None,
            "power_source": (sh("pmset", "-g", "batt") or "").splitlines()[0:1],
            "low_power_mode": sh("sh", "-c", "pmset -g | awk '/lowpowermode/{print $2}'"),
        },
        "application": {
            "repo": "PedestrianDynamics/pyFDS-Evac",
            "worktree": str(wt),
            "commit": sh("git", "-C", str(wt), "rev-parse", "HEAD"),
            "git_dirty": bool(sh("git", "-C", str(wt), "status", "--porcelain")),
            "uv_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            "uv_version": sh("uv", "--version"),
            "venv_created_with": "UV_CACHE_DIR=/Users/chraibi/profiling-stage/uvcache uv sync --frozen --python 3.12 (CPython 3.12 chosen by the coordinator; the lock at 8f7d29a2 resolves scikit-image 0.26.0)",
        },
        "interpreters": {"baseline": probe(venv_py, PACKAGES)},
        "thread_env": {k: os.environ.get(k) for k in THREAD_VARS},
        "profilers": {
            "py-spy": "0.4.2 installed in profiling venv; 'record' refuses without root on macOS "
            "('This program requires root on OSX'); --native unsupported on this platform. Not usable "
            "unless the maintainer grants sudo.",
            "cProfile": "works (stdlib)",
            "memray": "1.20.0 works (Python and --native capture; native frames symbolised, e.g. PyArray_*, checked on a toy script)",
            "scalene": "2.3.0 works ('scalene run -o out.json'); CPU+memory, writes JSON",
            "pyinstrument": "5.1.3 works; non-root statistical sampler (Python frames only)",
            "macos_sample": "/usr/bin/sample works without root on own processes; native C frames "
            "(e.g. libBLAS, jupedsim) but no Python frames",
            "usr_bin_time_l": "works; wall/user/sys, max RSS, peak memory footprint, instructions",
        },
    }
    if a.profiling_python:
        env["interpreters"]["profiling"] = probe(a.profiling_python, PACKAGES + PROFILERS)
    pathlib.Path(a.out).write_text(json.dumps(env, indent=1) + "\n")


if __name__ == "__main__":
    main()
