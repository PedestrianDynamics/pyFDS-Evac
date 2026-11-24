"""Benchmark harness: timed run and phase stamps on the same child process.

Usage
  benchmark.py run   --case CASE --seed N [--rep K] [--kind KIND] [--label TXT]
                     [--cap-s S] [--env KEY=VAL ...] [--vis-cache-from FILE]
                     [--run-id ID] [--commit REV] [--checkout DIR]
                     [--outdir DIR] [--python EXE]
  benchmark.py batch SPEC.json [--dry-run] [same options]
                     serial list of the same arguments; "{OUTDIR}" in an
                     argument is replaced by the results directory; an item
                     with "group" is compared with compare_outputs.py against
                     the previous run of the same group (compare/)

CASE names an entry of cases.json next to this script. Every run is a fresh
process started from the checkout (default: the repository this script lives
in). The harness refuses to start unless the checkout HEAD is the requested
commit (default: HEAD), the tree is clean, and the child imports pyfds_evac
from the checkout. Per run it writes <outdir>/raw/<run_id>/:
  manifest.json   everything below; missing values are null, never zero
  stdout.txt      raw child stdout (progress lines use \\r)
  stdout_stamped.txt  one line per \\n or \\r record, prefixed by seconds
                  since process start (the phase source)
  stderr.txt, tmp/ (TMPDIR of the child), the case outputs
and appends one row to <outdir>/summary.csv. The outdir default is
./benchmark-results in the working directory.

FDS cases read the FDS data subset from $FDS_EVAC_DATA (required for them).

Measurement method: wall = perf_counter around Popen..wait4; CPU = user+sys
of the waited tree (wait4 rusage); peak RSS = ru_maxrss in KiB = the largest
single process in the waited tree (not a sum; includes mapped file pages).
Phases come from child stdout stamps (resolution about 10 ms): startup =
process start to "Initialization started."; setup = to "Simulation started.";
loop = to the "Simulation finished/incomplete" line; finalisation = rest of
the wall time (output writing plus interpreter teardown, not separable).
FDS lazy array loading happens inside the loop and is not separable.
Exit status 2 is the documented incomplete outcome and is valid; any other
non-zero status or a signal is recorded as status "failed".
"""

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENV_KEYS = (
    "PYTHONHASHSEED",
    "PYTHONUNBUFFERED",
    "PYTHONPATH",
    "TMPDIR",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "LANG",
    "LC_ALL",
    "VIRTUAL_ENV",
    "FDS_EVAC_DATA",
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_listing_hash(path):
    """sha256 over sorted (relative name, size, mtime_ns) of a directory tree."""
    rows = []
    for root, _, files in os.walk(path):
        for n in files:
            p = os.path.join(root, n)
            st = os.stat(p)
            rows.append(f"{os.path.relpath(p, path)}\t{st.st_size}\t{st.st_mtime_ns}")
    rows.sort()
    return {
        "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
        "files": len(rows),
    }


def run_cmd(cmd, cwd=None, env=None):
    return subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def host_snapshot():
    """Loadavg plus the busiest other processes (exclusive-slot evidence)."""
    with open("/proc/loadavg") as f:
        load = f.read().split()[:3]
    ps = subprocess.run(
        ["ps", "-eo", "pcpu,pid,args", "--sort=-pcpu"], capture_output=True, text=True
    ).stdout.splitlines()[1:6]
    return {"loadavg": load, "top_processes": [ln.strip()[:120] for ln in ps]}


def resolve_commit(checkout, commit):
    """Full sha of REV in the checkout (default: its HEAD)."""
    rev = (commit or "HEAD") + "^{commit}"
    return run_cmd(["git", "-C", checkout, "rev-parse", rev])


def check_checkout(checkout, commit):
    """HEAD must be the requested commit and the tree clean."""
    want = resolve_commit(checkout, commit)
    head = run_cmd(["git", "-C", checkout, "rev-parse", "HEAD"])
    status = run_cmd(["git", "-C", checkout, "status", "--porcelain"])
    if head != want:
        sys.exit(
            f"refusing to start: checkout HEAD {head} != {want}; check the commit out first"
        )
    if status:
        sys.exit(f"refusing to start: checkout not clean:\n{status}")
    return head, status


def child_env(checkout, out_dir, extra):
    env = dict(os.environ)
    env.update(
        PYTHONHASHSEED="0",
        PYTHONUNBUFFERED="1",
        TMPDIR=os.path.join(out_dir, "tmp"),
        PYTHONPATH=checkout,
        VIRTUAL_ENV=sys.prefix,
    )
    env.update(extra)
    return env


def check_import(py, checkout, env):
    f = run_cmd(
        [py, "-c", "import pyfds_evac;print(pyfds_evac.__file__)"],
        cwd=checkout,
        env=env,
    )
    if not os.path.realpath(f).startswith(os.path.realpath(checkout) + os.sep):
        sys.exit(f"refusing to start: pyfds_evac imported from {f}, not {checkout}")
    return f


PROBE = r"""
import ctypes, importlib, importlib.metadata as md, json, platform, sys
out = {"python": sys.version, "executable": sys.executable, "packages": {}}
for n, dist in (("pyfds_evac", "pyfds-evac"), ("jupedsim", "jupedsim"),
                ("fdsreader", "fdsreader"), ("fdsvismap", "fdsvismap"),
                ("numpy", "numpy"), ("scipy", "scipy"), ("shapely", "shapely")):
    m = importlib.import_module(n)
    out["packages"][n] = {"version": md.version(dist), "file": m.__file__}
libs = sorted({ln.split()[-1] for ln in open("/proc/self/maps") if "openblas" in ln.lower()})
out["blas_libs"] = libs
out["blas_threads"] = None
for lib in libs:
    h = ctypes.CDLL(lib)
    for fn in ("scipy_openblas_get_num_threads64_", "openblas_get_num_threads64_",
               "scipy_openblas_get_num_threads", "openblas_get_num_threads"):
        if hasattr(h, fn):
            out["blas_threads"] = getattr(h, fn)()
            out["blas_threads_source"] = f"{fn} in {lib}"
            break
    if out["blas_threads"] is not None:
        break
print(json.dumps(out))
"""


def env_probe(py, checkout, env):
    """Versions, file locations and the runtime BLAS thread count, as the child sees them."""
    return json.loads(run_cmd([py, "-c", PROBE], cwd=checkout, env=env))


def machine_info():
    with open("/proc/cpuinfo") as f:
        cpu = [ln.split(":", 1)[1].strip() for ln in f if ln.startswith("model name")][
            :1
        ]
    with open("/proc/meminfo") as f:
        mem = [ln for ln in f if ln.startswith("MemTotal")][0].split()[1]
    with open("/etc/os-release") as f:
        osr = dict(ln.strip().split("=", 1) for ln in f if "=" in ln)
    return {
        "cpu_model": cpu[0] if cpu else None,
        "logical_cpus": os.cpu_count(),
        "mem_total_kib": int(mem),
        "os": osr.get("PRETTY_NAME", "").strip('"'),
        "kernel": os.uname().release,
    }


PROGRESS = re.compile(r"Evacuated (\d+)/(\d+)\s+sim=([\d.]+)s\s+wall=(\S+)")


def partial_work(stamped):
    """Last progress line of a run that was killed: labelled partial."""
    last = None
    with open(stamped, errors="replace") as f:
        for line in f:
            last = PROGRESS.search(line) or last
    if not last:
        return {}
    return {
        "partial": True,
        "partial_note": "last progress line before the kill; not an outcome",
        "simulated_time_s": float(last[3]),
        "evacuated": int(last[1]),
        "progress_total": int(last[2]),
        "progress_wall": last[4],
    }


def set_path(d, dotted, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value


def stage_inputs(tpl, out_dir, fmt):
    """Copy (and optionally edit) config and geometry into the run dir."""
    staged = {}
    for src in tpl.get("stage", []):
        src = src.format(**fmt)
        dst = os.path.join(out_dir, os.path.basename(src))
        shutil.copyfile(src, dst)
        staged[os.path.basename(src)] = {
            "source": src,
            "source_sha256": sha256_file(src),
        }
    edits = tpl.get("config_edits")
    if edits:
        cfg_path = os.path.join(out_dir, tpl["config_name"])
        with open(cfg_path) as f:
            cfg = json.load(f)
        for dotted, value in edits.items():
            set_path(cfg, dotted, value)
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)
        staged[tpl["config_name"]]["edits"] = edits
    for name in staged:
        staged[name]["staged_sha256"] = sha256_file(os.path.join(out_dir, name))
    return staged


def check_input_hashes(tpl, checkout):
    """Expected input sha256 values of the case against the files found.

    A mismatch is recorded, not fatal: another commit may change a deck.
    """
    out = {}
    for rel, expected in tpl.get("inputs_sha256", {}).items():
        if rel.startswith("$FDS_EVAC_DATA/"):
            path = os.path.join(
                os.environ["FDS_EVAC_DATA"], rel[len("$FDS_EVAC_DATA/") :]
            )
        else:
            path = os.path.join(checkout, rel)
        actual = sha256_file(path) if os.path.exists(path) else None
        out[rel] = {"expected": expected, "actual": actual, "match": actual == expected}
    return out


def case_pickles(fds_dirs):
    """sha256 of every *.pickle in the FDS case directories."""
    res = {}
    for d in fds_dirs:
        names = [n for n in os.listdir(d) if n.endswith(".pickle")]
        res.update({os.path.join(d, n): sha256_file(os.path.join(d, n)) for n in names})
    return res


STEP = re.compile(r"Simulation (finished|incomplete)")
END_FIN = re.compile(r"Simulation finished in ([\d.]+) s \((\d+)/(\d+) evacuated\)")
END_INC = re.compile(
    r"Simulation incomplete: (.*?) after ([\d.]+) s "
    r"\((\d+)/(\d+) evacuated, (\d+) remaining(?:, (\d+) not spawned)?\)"
)


class Stamper(threading.Thread):
    """Reads the child's stdout pipe, stamps each record, keeps raw bytes."""

    def __init__(self, pipe, t0, raw_path, stamped_path):
        super().__init__(daemon=True)
        self.pipe, self.t0 = pipe, t0
        self.raw = open(raw_path, "wb")
        self.stamped = open(stamped_path, "w")
        self.marks = {}
        self.records = 0

    def mark(self, line, t):
        for key, text in (
            ("init_start", "Initialization started"),
            ("sim_start", "Simulation started"),
        ):
            if key not in self.marks and line.startswith(text):
                self.marks[key] = t
        if "loop_end" not in self.marks and STEP.match(line):
            self.marks["loop_end"] = t

    def emit(self, line, t):
        if not line:
            return
        self.stamped.write(f"{t:9.3f} {line}\n")
        self.records += 1
        self.mark(line, t)

    def split_records(self, buf, t):
        """Emit every complete \\n or \\r record of buf; return the rest."""
        while True:
            idx = [j for j in (buf.find(b"\n"), buf.find(b"\r")) if j >= 0]
            if not idx:
                return buf
            i = min(idx)
            self.emit(buf[:i].decode(errors="replace"), t)
            buf = buf[i + 1 :]

    def run(self):
        buf = b""
        while True:
            chunk = os.read(self.pipe.fileno(), 65536)
            t = time.perf_counter() - self.t0
            if not chunk:
                break
            self.raw.write(chunk)
            buf = self.split_records(buf + chunk, t)
        if buf:
            line = buf.decode(errors="replace")
            self.stamped.write(f"{t:9.3f} {line}\n")
            self.mark(line, t)
        self.raw.close()
        self.stamped.close()


def execute(argv, cwd, env, out_dir, cap_s):
    """Run one fresh child; return timing facts. Never raises on child failure."""
    err = open(os.path.join(out_dir, "stderr.txt"), "wb")
    t_start_utc = now_utc()
    t0 = time.perf_counter()
    p = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=err,
        start_new_session=True,
    )
    st = Stamper(
        p.stdout,
        t0,
        os.path.join(out_dir, "stdout.txt"),
        os.path.join(out_dir, "stdout_stamped.txt"),
    )
    st.start()
    capped = {"hit": False}

    def watchdog():
        time.sleep(cap_s)
        capped["hit"] = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    if cap_s:
        threading.Thread(target=watchdog, daemon=True).start()
    _, status, ru = os.wait4(p.pid, 0)
    wall = time.perf_counter() - t0
    st.join()
    err.close()
    meas = dict(
        started_utc=t_start_utc,
        ended_utc=now_utc(),
        wall_s=wall,
        cpu_user_s=ru.ru_utime,
        cpu_sys_s=ru.ru_stime,
        cpu_total_s=ru.ru_utime + ru.ru_stime,
        peak_rss_kib=ru.ru_maxrss,
        rss_semantics="ru_maxrss of the largest single process in the waited tree (KiB), not a sum",
        vol_ctx_switches=ru.ru_nvcsw,
        invol_ctx_switches=ru.ru_nivcsw,
        major_faults=ru.ru_majflt,
        minor_faults=ru.ru_minflt,
        returncode=os.waitstatus_to_exitcode(status),
        killed_at_cap=capped["hit"],
        cap_s=cap_s or None,
        stdout_records=st.records,
    )
    return meas, st.marks


def phases(wall, marks):
    ks = ("init_start", "sim_start", "loop_end")
    if not all(k in marks for k in ks):
        return dict(
            startup_s=None,
            setup_s=None,
            loop_s=None,
            finalisation_s=None,
            note="phase markers missing: " + ",".join(k for k in ks if k not in marks),
        )
    return dict(
        startup_s=marks["init_start"],
        setup_s=marks["sim_start"] - marks["init_start"],
        loop_s=marks["loop_end"] - marks["sim_start"],
        finalisation_s=wall - marks["loop_end"],
        note="stdout stamps; finalisation = output writing + teardown",
    )


def apply_end_lines(o, stamped):
    """End line and counts from the stamped child stdout."""
    if not os.path.exists(stamped):
        return
    with open(stamped) as f:
        lines = f.read().splitlines()
    for line in lines:
        body = line[10:]
        m = END_FIN.search(body)
        if m:
            o.update(
                end_line=body,
                end_reason="all_evacuated",
                status="finished",
                simulated_time_s=float(m[1]),
                evacuated=int(m[2]),
                remaining=0,
                not_spawned=0,
            )
        m = END_INC.search(body)
        if m:
            o.update(
                end_line=body,
                end_reason=m[1],
                simulated_time_s=float(m[2]),
                evacuated=int(m[3]),
                remaining=int(m[5]),
                not_spawned=int(m[6] or 0),
                status="incomplete",
            )


def apply_run_manifest(o, path):
    """Outcome fields of the simulator's own run manifest, if present."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        mj = json.load(f)
    oc = mj.get("outcome", {})
    o["manifest_outcome"] = oc
    o["dt_s"] = mj.get("dt")
    if oc.get("end_reason"):
        o["end_reason"] = oc["end_reason"]
    if oc.get("agents_remaining") is not None:
        o["remaining"] = oc["agents_remaining"]
    if oc.get("agents_not_spawned") is not None:
        o["not_spawned"] = oc["agents_not_spawned"]


def apply_sqlite_facts(o, path):
    if not os.path.exists(path):
        return
    con = sqlite3.connect(path)
    o["spawned"] = con.execute(
        "select count(distinct id) from trajectory_data"
    ).fetchone()[0]
    o["frames"] = con.execute("select max(frame) from trajectory_data").fetchone()[0]
    con.close()


def apply_incapacitated(o, path):
    if not os.path.exists(path):
        return
    with open(path, newline="") as f:
        ids = {
            row["agent_id"]
            for row in csv.DictReader(f)
            if row.get("incapacitation_cause")
        }
    o["incapacitated"] = len(ids)
    o["incapacitated_note"] = "agents with a non-empty incapacitation_cause in fed.csv"


def parse_outcome(out_dir, stamped):
    """End line, counts and sqlite-derived facts; null where unavailable."""
    o = dict(
        end_line=None,
        end_reason=None,
        status=None,
        simulated_time_s=None,
        planned=None,
        spawned=None,
        evacuated=None,
        remaining=None,
        not_spawned=None,
        incapacitated=None,
        steps=None,
        agent_steps=None,
        frames=None,
        dt_s=None,
    )
    apply_end_lines(o, stamped)
    sq = os.path.join(out_dir, "run.sqlite")
    apply_run_manifest(o, os.path.join(out_dir, "run.manifest.json"))
    apply_sqlite_facts(o, sq)
    if o["spawned"] is not None and o["not_spawned"] is not None:
        o["planned"] = o["spawned"] + o["not_spawned"]
    if o["simulated_time_s"] is not None and o["dt_s"]:
        o["steps"] = round(o["simulated_time_s"] / o["dt_s"])
        o["steps_note"] = (
            "derived: simulated_time / dt; agent_steps need instrumentation"
        )
    apply_incapacitated(o, os.path.join(out_dir, "fed.csv"))
    return o


def hash_outputs(out_dir):
    res = {}
    for n in sorted(os.listdir(out_dir)):
        p = os.path.join(out_dir, n)
        if os.path.isfile(p) and n != "manifest.json":
            res[n] = sha256_file(p)
    return res


def load_case(name):
    with open(os.path.join(HERE, "cases.json")) as f:
        cases = json.load(f)["cases"]
    if name not in cases:
        sys.exit(f"unknown case {name!r}; known: {', '.join(cases)}")
    return cases[name]


SUMMARY_COLS = [
    "run_id",
    "case",
    "kind",
    "label",
    "seed",
    "rep",
    "status",
    "exit_status",
    "end_reason",
    "wall_s",
    "cpu_total_s",
    "peak_rss_kib",
    "startup_s",
    "setup_s",
    "loop_s",
    "finalisation_s",
    "simulated_time_s",
    "planned",
    "spawned",
    "evacuated",
    "remaining",
    "not_spawned",
    "incapacitated",
    "steps",
    "agent_steps",
    "killed_at_cap",
    "started_utc",
]


def append_summary(m, outdir):
    path = os.path.join(outdir, "summary.csv")
    new = not os.path.exists(path)
    row = {c: m.get(c) for c in SUMMARY_COLS}
    for k in ("wall_s", "cpu_total_s", "peak_rss_kib", "started_utc", "killed_at_cap"):
        row[k] = m["measurements"].get(k)
    row.update(
        {
            k: m["phases"].get(k)
            for k in ("startup_s", "setup_s", "loop_s", "finalisation_s")
        }
    )
    work_keys = (
        "simulated_time_s",
        "planned",
        "spawned",
        "evacuated",
        "remaining",
        "not_spawned",
        "incapacitated",
        "steps",
        "agent_steps",
        "end_reason",
    )
    row.update({k: m["work"].get(k) for k in work_keys})
    row["exit_status"] = m["measurements"]["returncode"]
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, SUMMARY_COLS)
        if new:
            w.writeheader()
        w.writerow({k: ("" if v is None else v) for k, v in row.items()})


def classify(meas):
    """Run status: exit 0 ok, exit 2 the documented incomplete outcome, else failed."""
    if meas["killed_at_cap"]:
        return "cap_hit"
    if meas["returncode"] == 0:
        return "ok"
    return "incomplete_exit2" if meas["returncode"] == 2 else "failed"


def require_fds(tpl):
    if "{FDS}" in json.dumps(tpl) and not os.environ.get("FDS_EVAC_DATA"):
        sys.exit(
            "FDS_EVAC_DATA must be exported (FDS data subset, see README.md) for this case"
        )


def sha_or_none(path):
    return sha256_file(path) if os.path.exists(path) else None


def prepare_run(a, tpl):
    """Run directory, environment and the formatted command of one run."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_id = a.run_id or f"{a.case}_s{a.seed}_{a.kind}{a.rep}_{ts}"
    out_dir = os.path.join(a.outdir, "raw", run_id)
    if os.path.exists(out_dir):
        sys.exit(f"run dir exists: {out_dir}; use a fresh --outdir or another --run-id")
    os.makedirs(os.path.join(out_dir, "tmp"))
    extra = dict(kv.split("=", 1) for kv in a.env)
    env = child_env(a.checkout, out_dir, extra)
    fmt = dict(
        ROOT=a.checkout,
        OUT=out_dir,
        FDS=os.environ.get("FDS_EVAC_DATA", ""),
        PY=a.python,
        SEED=a.seed,
    )
    return run_id, out_dir, env, extra, fmt


def one_run(a):
    tpl = load_case(a.case)
    require_fds(tpl)
    head, status = check_checkout(a.checkout, a.commit)
    run_id, out_dir, env, extra, fmt = prepare_run(a, tpl)
    imported = check_import(a.python, a.checkout, env)
    probe = env_probe(a.python, a.checkout, env)
    staged = stage_inputs(tpl, out_dir, fmt)
    vis = os.path.join(out_dir, "vis.npz")
    if a.vis_cache_from:
        shutil.copyfile(a.vis_cache_from, vis)
    argv = [x.format(**fmt) for x in tpl["argv"]]
    fds_dirs = {d.format(**fmt): None for d in tpl.get("fds_dirs", [])}
    fds_before = {d: dir_listing_hash(d) for d in fds_dirs}
    pickles = case_pickles(fds_dirs)
    vis_before = sha_or_none(vis)
    host_before = host_snapshot()
    meas, marks = execute(argv, a.checkout, env, out_dir, a.cap_s)
    host_after = host_snapshot()
    fds_after = {d: dir_listing_hash(d) for d in fds_dirs}
    pick_after = {p: sha256_file(p) for p in pickles}
    st = classify(meas)
    stamped = os.path.join(out_dir, "stdout_stamped.txt")
    work = parse_outcome(out_dir, stamped)
    if st == "cap_hit":
        work.update(partial_work(stamped))
    m = dict(
        run_id=run_id,
        case=a.case,
        kind=a.kind,
        label=a.label,
        seed=a.seed,
        rep=a.rep,
        status=st,
        commit=head,
        checkout=a.checkout,
        git_status_porcelain=status,
        harness=dict(
            benchmark_py_sha256=sha256_file(__file__),
            cases_json_sha256=sha256_file(os.path.join(HERE, "cases.json")),
            commit=head,
        ),
        command=argv,
        cwd=a.checkout,
        template=tpl.get("note"),
        env={k: env.get(k) for k in ENV_KEYS},
        env_extra=extra,
        pyfds_evac_file=imported,
        python=a.python,
        probe=probe,
        uv_lock_sha256=sha256_file(os.path.join(a.checkout, "uv.lock")),
        machine=machine_info(),
        input_fingerprints=dict(
            staged=staged,
            input_sha256_check=check_input_hashes(tpl, a.checkout),
            fds_dir_listing_before=fds_before,
            fds_dir_listing_after=fds_after,
            fds_dir_listing_unchanged=fds_before == fds_after,
            pickles_before=pickles,
            pickles_after=pick_after,
            pickles_unchanged=pickles == pick_after,
            vis_cache_sha256_before=vis_before,
            vis_cache_sha256_after=sha_or_none(vis),
            vis_cache_seeded_from=a.vis_cache_from,
        ),
        cache_state=tpl.get("cache_state"),
        host_before=host_before,
        host_after=host_after,
        measurements=meas,
        phases=phases(meas["wall_s"], marks),
        work=work,
        markers_s=marks,
        output_sha256=hash_outputs(out_dir),
        tmpdir_listing_after=sorted(os.listdir(os.path.join(out_dir, "tmp"))),
        notes="Exit status 2 is a valid incomplete outcome. Page cache uncontrolled. Missing values are null.",
    )
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(m, f, indent=2)
    append_summary(m, a.outdir)
    print(
        json.dumps(
            dict(
                run_id=run_id,
                status=st,
                wall_s=round(meas["wall_s"], 2),
                cpu_s=round(meas["cpu_total_s"], 1),
                rss_mib=round(meas["peak_rss_kib"] / 1024),
                rc=meas["returncode"],
                end=work["end_reason"],
                evac=work["evacuated"],
                rem=work["remaining"],
            )
        )
    )
    return m


def add_common(p):
    p.add_argument(
        "--commit", help="revision the checkout must be at (default: its HEAD)"
    )
    p.add_argument(
        "--checkout",
        default=ROOT,
        help="repository to run from (default: this repository)",
    )
    p.add_argument("--outdir", default=os.path.join(os.getcwd(), "benchmark-results"))
    p.add_argument("--python", default=sys.executable, help="interpreter of the child")


def parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--case", required=True)
    r.add_argument("--seed", type=int, required=True)
    r.add_argument("--rep", type=int, default=0)
    r.add_argument(
        "--kind",
        default="measured",
        help="warmup | measured | first_use | diagnostic | ...",
    )
    r.add_argument("--label", default=None)
    r.add_argument("--cap-s", type=float, default=900)
    r.add_argument("--env", action="append", default=[])
    r.add_argument("--vis-cache-from")
    r.add_argument("--run-id")
    add_common(r)
    b = sub.add_parser("batch")
    b.add_argument("spec")
    b.add_argument(
        "--dry-run", action="store_true", help="print the runs, execute nothing"
    )
    add_common(b)
    return p


def common_flags(a):
    flags = ["--checkout", a.checkout, "--outdir", a.outdir, "--python", a.python]
    return flags + (["--commit", a.commit] if a.commit else [])


def batch_items(a):
    with open(a.spec) as f:
        items = json.load(f)
    for item in items:
        item["args"] = [str(x).replace("{OUTDIR}", a.outdir) for x in item["args"]]
    return items


def run_batch(a):
    last = {}
    for item in batch_items(a):
        if a.dry_run:
            print("run", shlex.join(item["args"]))
            continue
        m = one_run(parser().parse_args(["run", *common_flags(a), *item["args"]]))
        group = item.get("group")
        if group:
            compare_to_previous(m, last.get(group), a)
            last[group] = m["run_id"]


def main():
    a = parser().parse_args()
    here = os.path.realpath(HERE) + os.sep
    if (os.path.realpath(a.outdir) + os.sep).startswith(here):
        sys.exit("--outdir must not be inside scripts/benchmark")
    if a.cmd == "run":
        one_run(a)
        return
    run_batch(a)


def compare_to_previous(m, prev, a):
    """Exact comparison of a finished run with the previous run of its group."""
    if prev is None or m["status"] in ("cap_hit", "failed"):
        return
    os.makedirs(os.path.join(a.outdir, "compare"), exist_ok=True)
    out = os.path.join(a.outdir, "compare", f"{m['run_id']}_vs_{prev}.json")
    raw = os.path.join(a.outdir, "raw")
    cmp_py = os.path.join(HERE, "compare_outputs.py")
    r = subprocess.run(
        [
            a.python,
            cmp_py,
            os.path.join(raw, prev),
            os.path.join(raw, m["run_id"]),
            out,
        ],
        capture_output=True,
        text=True,
    )
    verdict = "EQUAL" if r.returncode == 0 else "DIFFERS"
    print(json.dumps({"compare": f"{m['run_id']} vs {prev}", "verdict": verdict}))


if __name__ == "__main__":
    main()
