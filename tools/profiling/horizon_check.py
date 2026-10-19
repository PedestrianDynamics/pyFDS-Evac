"""Horizon criterion of one run (plan.md D26; scenarios.json global_rules.horizon_criterion).

For a run directory (results/raw/<id> or just the id) write horizon.json with

  bound_i       = time_s + path_length_m / base_speed_m_per_s   for every row of rc.csv
  guard         = last FDS frame + largest output interval       (fds_sampling.fds_output_horizon,
                                                                  the code's own horizon rule)
  max_bound, rows, rows_past_guard (bound > guard), rows_past_last_frame (bound > last frame:
  "held-foresight" rows), held_share = rows_past_last_frame / rows,
  warning_count  = '#666 Route foresight reaches beyond' lines in stderr.log
  passes         = max_bound < guard and warning_count == 0

Base speed per case: W1 family 1.0; W3, W3b_cmm, W1r 1.3 (the RouteCostConfig default).
Missing inputs give null, never zero: a case that writes no route-cost history (W3b_cmm),
or has no FDS (W2), gets null bound fields and a note. Untimed; run with the baseline
venv python from any directory:  PY horizon_check.py RUN [RUN ...]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

STUDY = Path(__file__).resolve().parent
BASE_SPEED = {"W1": 1.0, "W1_n100": 1.0, "W1_n400": 1.0, "W1_add": 1.0, "W1_sb": 1.0,
              "W3": 1.3, "W3b_cmm": 1.3, "W1r": 1.3}
WARNING = "Route foresight reaches beyond"


def run_dir(arg: str) -> Path:
    p = Path(arg)
    return p if p.is_dir() else STUDY / "results" / "raw" / arg


def fds_dir_of(man: dict) -> str | None:
    cmd = man.get("command") or []
    return cmd[cmd.index("--fds-dir") + 1] if "--fds-dir" in cmd else None


def guard_of(man: dict) -> tuple[float | None, float | None, str | None]:
    fds = fds_dir_of(man)
    if fds is None:
        return None, None, "no FDS directory in the command"
    sys.path.insert(0, man["cwd"])
    from pyfds_evac.core.fds_sampling import fds_output_horizon

    h = fds_output_horizon(fds)
    if h is None:
        return None, None, "no slice with two frames"
    return h[0], h[1], None


def check(arg: str) -> dict:
    rec = run_dir(arg)
    man = json.loads((rec / "manifest.json").read_text())
    case = man["case"]
    res = {"run_id": man["run_id"], "case": case, "base_speed_m_per_s": BASE_SPEED.get(case),
           "notes": []}
    last, interval, why = guard_of(man)
    res["last_fds_frame_s"], res["output_interval_s"] = last, interval
    res["guard_s"] = None if last is None else last + interval
    if why:
        res["notes"].append(why)
    err = rec / "stderr.log"
    res["warning_count"] = (err.read_text(errors="replace").count(WARNING)
                            if err.exists() else None)
    rc = Path(man["outputs_dir"]) / "rc.csv"
    speed = BASE_SPEED.get(case)
    rows = None
    if speed is None:
        res["notes"].append("no base speed defined for this case")
    elif not rc.exists():
        res["notes"].append("no route-cost history (rc.csv) written by this case")
    else:
        with open(rc, newline="") as f:
            rows = [float(r["time_s"]) + float(r["path_length_m"]) / speed
                    for r in csv.DictReader(f)]
    res["rows"] = None if rows is None else len(rows)
    res["max_bound_s"] = max(rows) if rows else None
    guard, lastf = res["guard_s"], last
    res["rows_past_guard"] = (None if rows is None or guard is None
                              else sum(b > guard for b in rows))
    res["rows_past_last_frame"] = (None if rows is None or lastf is None
                                   else sum(b > lastf for b in rows))
    res["held_share"] = (res["rows_past_last_frame"] / len(rows)
                         if rows and res["rows_past_last_frame"] is not None else None)
    res["passes"] = (None if res["max_bound_s"] is None or guard is None
                     or res["warning_count"] is None
                     else res["max_bound_s"] < guard and res["warning_count"] == 0)
    (rec / "horizon.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    for a in sys.argv[1:]:
        r = check(a)
        print(json.dumps({k: r[k] for k in ("run_id", "max_bound_s", "guard_s", "rows",
                                            "rows_past_guard", "rows_past_last_frame",
                                            "held_share", "warning_count", "passes")}))
