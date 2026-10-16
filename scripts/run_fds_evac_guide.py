"""Run the converted guide cases, keeping generated files outside the inputs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COLLECTION = REPO / "assets" / "fds_evac_guide_converted"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_process(command, directory, log_path, env, timeout):
    """Record errors even when FDS reports input failure with exit status zero."""
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=directory,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        )
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                import signal

                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise


def fds_completed(returncode, log_path):
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return (
        returncode == 0
        and "STOP: FDS completed successfully" in text
        and "ERROR" not in text
    )


def required_quantities(case):
    names = {"extinction", "temperature"}
    if case["coupling"] == "smoke_and_gas":
        names.update(("co", "co2", "o2"))
    return names


def run_case(case, args):
    started = time.monotonic()
    row = {"id": case["id"], "phase": args.phase, "seed": args.seed}
    source = COLLECTION / "cases" / case["id"]
    output = args.output / case["id"]
    try:
        output.mkdir(parents=True, exist_ok=False)
        env = dict(
            os.environ,
            PYTHONUTF8="1",
            PYTHONUNBUFFERED="1",
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MPLBACKEND="Agg",
        )
        env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
        fire_dir = None
        if case["fire_input"] and args.phase in ("auto", "fds"):
            fire_dir = output / "fds"
            fire_dir.mkdir()
            content = (source / case["fire_input"]).read_text(encoding="utf-8")
            if args.duration is not None:
                end = min(args.duration, case["max_simulation_time_s"])
                content = re.sub(r"T_END=[^, /]+", f"T_END={end}", content)
            (fire_dir / "fire.fds").write_text(content, encoding="utf-8")
            mpi = Path(args.fds_exe).parent / "mpi"
            if os.name == "nt" and mpi.is_dir():
                env["I_MPI_ROOT"] = str(mpi)
                env["PATH"] = str(mpi) + os.pathsep + env["PATH"]
            log = output / "fds.log"
            code = run_process(
                [args.fds_exe, "fire.fds"], fire_dir, log, env, args.timeout
            )
            row["fds_returncode"] = code
            if not fds_completed(code, log):
                raise RuntimeError("FDS did not complete successfully; see fds.log")
        if args.phase == "fds":
            row["status"] = "fds_completed" if fire_dir else "no_fire_mesh"
        else:
            if case["fire_input"] and args.phase == "coupled":
                fire_dir = args.fds_root / case["id"] / "fds"
            if fire_dir is not None:
                from pyfds_evac.core.fds_inventory import inspect_fds_quantities

                quantities = inspect_fds_quantities(
                    str(fire_dir)
                ).canonical_slice_names()
                missing = required_quantities(case) - quantities.keys()
                if missing:
                    raise RuntimeError(f"Missing FDS quantities: {sorted(missing)}")
                row["fds_quantities"] = quantities
            evac_dir = output / "evac"
            evac_dir.mkdir()
            config = json.loads((source / "config.json").read_text())
            if args.duration is not None:
                params = config["config"]["simulation_settings"]["simulationParams"]
                params["max_simulation_time"] = min(
                    args.duration, params["max_simulation_time"]
                )
            write_json(evac_dir / "config.json", config)
            shutil.copyfile(source / "geometry.wkt", evac_dir / "geometry.wkt")
            command = [
                sys.executable,
                "-m",
                "pyfds_evac.cli",
                "--scenario",
                str(evac_dir),
                "--seed",
                str(args.seed),
                "--output-sqlite",
                str(evac_dir / "trajectory.sqlite"),
            ]
            if fire_dir is not None:
                command.extend(("--fds-dir", str(fire_dir)))
            code = run_process(command, REPO, output / "evac.log", env, args.timeout)
            row["evac_returncode"] = code
            row["status"] = {0: "completed", 2: "incomplete"}.get(code, "error")
            row["coupling"] = case["coupling"] if fire_dir else "clear_air"
    except subprocess.TimeoutExpired:
        row.update(status="timeout", timeout_s=args.timeout)
    except Exception as exc:
        row.update(status="error", error=str(exc))
    row["wall_seconds"] = round(time.monotonic() - started, 3)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        help="Exact case ID; repeat to select several. Default: all 94.",
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--phase",
        choices=("auto", "evac", "fds", "coupled"),
        default="auto",
        help="auto: generate fire data then run evacuation; evac: clear air; coupled: use --fds-root",
    )
    parser.add_argument(
        "--fds-exe", default="fds", help="FDS executable, not a batch wrapper"
    )
    parser.add_argument(
        "--fds-root", type=Path, help="Output root of an earlier --phase fds run"
    )
    parser.add_argument(
        "--output", type=Path, help="New output directory (required except with --list)"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Concurrent cases; each FDS case uses one OpenMP thread",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help="Optional wall seconds per subprocess; default: no limit",
    )
    parser.add_argument(
        "--duration",
        type=float,
        help="Cap simulation seconds in output copies only (smoke test)",
    )
    args = parser.parse_args()
    manifest = json.loads((COLLECTION / "manifest.json").read_text())
    cases = manifest["cases"]
    if args.case:
        unknown = set(args.case) - {case["id"] for case in cases}
        if unknown:
            parser.error(f"Unknown cases: {sorted(unknown)}")
        cases = [case for case in cases if case["id"] in args.case]
    if args.list:
        for case in cases:
            print(f"{case['id']} ({case['coupling']})")
        return 0
    if args.output is None:
        parser.error("--output is required")
    if args.jobs < 1 or any(
        v is not None and v <= 0 for v in (args.timeout, args.duration)
    ):
        parser.error("--jobs, --timeout and --duration must be positive")
    if args.phase == "coupled" and args.fds_root is None:
        parser.error("--phase coupled requires --fds-root")
    if args.fds_root:
        args.fds_root = args.fds_root.resolve()
    if args.phase in ("auto", "fds") and any(c["fire_input"] for c in cases):
        executable = shutil.which(args.fds_exe)
        if not executable:
            parser.error("FDS executable not found; set --fds-exe")
        args.fds_exe = str(Path(executable).resolve())
    args.output = args.output.resolve()
    if args.output == COLLECTION or COLLECTION in args.output.parents:
        parser.error("--output must be outside the collection")
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(REPO))
    report = {
        "seed": args.seed,
        "phase": args.phase,
        "duration_cap_s": args.duration,
        "timeout_s": args.timeout,
        "results": [],
    }
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_case, case, args) for case in cases]
        for future in as_completed(futures):
            row = future.result()
            report["results"].append(row)
            print(f"{row['id']}: {row['status']}", flush=True)
            write_json(args.output / "summary.json", report)
    statuses = {r["status"] for r in report["results"]}
    return (
        1 if statuses & {"error", "timeout"} else 2 if "incomplete" in statuses else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
