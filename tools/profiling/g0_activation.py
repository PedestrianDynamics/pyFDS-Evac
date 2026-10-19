"""G0 preflight: activation counts from one finished run's outputs (read-only).

Usage: python g0_activation.py RUN_DIR PREFIX BASE_SPEED [--horizon-guard S] [--out JSON]

RUN_DIR holds <PREFIX>.sqlite, <PREFIX>.manifest.json, <PREFIX>_log.txt and,
when written, <PREFIX>_fed.csv, <PREFIX>_rc.csv, <PREFIX>_rh.csv,
<PREFIX>_exit.csv, plus exit_code. Missing outputs give null, never zero.
"""

import argparse
import json
import pathlib
import re
import sqlite3

import pandas as pd

LOG_FLAGS = {
    "fds_horizon_error": "FdsHorizonError",
    "holding_last_frame": "holding the last frame",
    "outside_fds_domain": "Outside the FDS domain",
    "setup_smoke": "Configuring smoke calculation",
    "setup_fed": "Configuring FED calculation",
    "setup_rerouting": "Configuring rerouting",
    "setup_tenability": "Configuring tenability",
    "setup_visibility": "Configuring visibility model",
}


def read_csv(path):
    return pd.read_csv(path) if path.exists() else None


def log_facts(text):
    facts = {k: (pat in text) for k, pat in LOG_FLAGS.items()}
    m = re.search(r"Configuring visibility model \((\d+) signs?\)", text)
    facts["visibility_signs"] = int(m.group(1)) if m else None
    m = re.search(r"Simulation (finished|incomplete)[^\n]*", text)
    facts["summary_line"] = m.group(0) if m else None
    for key, pat in {"route_switches": r"Route switches: (\d+)", "route_cost_samples": r"Route cost samples: (\d+)"}.items():
        m = re.search(pat, text)
        facts[key] = int(m.group(1)) if m else None
    return facts


def trajectory_facts(db):
    con = sqlite3.connect(db)
    try:
        first = pd.read_sql("select id, min(frame) f0, max(frame) f1 from trajectory_data group by id", con)
        last_frame = int(pd.read_sql("select max(frame) m from trajectory_data", con).m[0])
        n_rows = int(pd.read_sql("select count(*) n from trajectory_data", con).n[0])
    finally:
        con.close()
    return {
        "agents_in_trajectory": int(len(first)),
        "agents_present_at_frame0": int((first.f0 == 0).sum()),
        "agents_present_at_last_frame": int((first.f1 == last_frame).sum()),
        "last_frame": last_frame,
        "agent_frames_10fps": n_rows,
    }


def fed_facts(fed):
    if fed is None:
        return {"fed_history": None}
    moving = fed[fed.desired_speed > 0]
    return {
        "fed_rows": int(len(fed)),
        "rows_speed_factor_lt1_while_moving": int((moving.speed_factor < 1).sum()),
        "agents_speed_factor_lt1_while_moving": int(moving[moving.speed_factor < 1].agent_id.nunique()),
        "min_speed_factor_while_moving": float(moving.speed_factor.min()) if len(moving) else None,
        "rows_fed_gt0": int((fed.fed_cumulative > 0).sum()),
        "max_fed_cumulative": float(fed.fed_cumulative.max()),
        "rows_fic_gt0": int((fed.fic > 0).sum()),
        "max_fic": float(fed.fic.max()),
        "incapacitated_agents": int(fed[fed.incapacitated.astype(str) == "True"].agent_id.nunique()),
        "rows_outside_fds_domain": int((fed.in_fds_domain.astype(str) != "True").sum()),
        "max_extinction_proxy_note": "hazard ranges at agent positions come from G1 sampled histories",
    }


def rc_facts(rc, base_speed, guard):
    if rc is None:
        return {"route_cost_history": None}
    bound = (rc.time_s + rc.path_length_m / base_speed).max()
    tt = (rc.time_s + rc.travel_time_s).max() if "travel_time_s" in rc else None
    return {
        "route_cost_rows": int(len(rc)),
        "anticipated_horizon_bound_s": float(bound),
        "anticipated_horizon_travel_time_bound_s": float(tt) if tt is not None else None,
        "horizon_guard_s": guard,
        "horizon_margin_s": (guard - float(bound)) if guard is not None else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("prefix")
    ap.add_argument("base_speed", type=float)
    ap.add_argument("--horizon-guard", type=float)
    ap.add_argument("--out")
    a = ap.parse_args()
    d = pathlib.Path(a.run_dir)
    p = a.prefix
    man = json.loads((d / f"{p}.manifest.json").read_text())
    log = (d / f"{p}_log.txt").read_text(errors="replace")
    ec = d / "exit_code"
    rh = read_csv(d / f"{p}_rh.csv")
    ex = read_csv(d / f"{p}_exit.csv")
    res = {
        "exit_code": int(ec.read_text()) if ec.exists() else None,
        "manifest": {
            "git_commit": man.get("git_commit"),
            "git_dirty": man.get("git_dirty"),
            "agent_seeding": man.get("agent_seeding"),
            "uv_lock_sha256": man.get("uv_lock_sha256"),
            "walkable_outside_m2": man.get("fds_coverage", {}).get("walkable_outside_m2"),
            "outcome": man.get("outcome"),
        },
        "log": log_facts(log),
        "trajectory": trajectory_facts(d / f"{p}.sqlite"),
        "fed": fed_facts(read_csv(d / f"{p}_fed.csv")),
        "route_cost": rc_facts(read_csv(d / f"{p}_rc.csv"), a.base_speed, a.horizon_guard),
        "route_history_rows": int(len(rh)) if rh is not None else None,
        "exit_history": (
            {"rows": int(len(ex)), "by_exit": ex.exit_id.value_counts().to_dict(),
             "by_origin": ex.origin.value_counts().to_dict()} if ex is not None else None
        ),
    }
    text = json.dumps(res, indent=1, default=str)
    print(text)
    if a.out:
        pathlib.Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
