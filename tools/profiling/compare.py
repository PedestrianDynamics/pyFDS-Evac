"""Exact equivalence check between benchmark runs (model_handoff_g0.md §3, §11.2).

Usage:
  python compare.py RUN_A RUN_B [--out results/equivalence/NAME.json]
  python compare.py --negative-control RUN [--out ...]   # review O9
  python compare.py --block BLOCK --ref RUN_ID [--out ...]   # every other run of the
                                                              # block against RUN_ID

RUN_* are run IDs under results/raw/ (or paths to those directories). Run
outputs are read from the manifest's ``outputs_dir``.

Items (exact, no tolerance; floats as repr):
  1 trajectory rows (repr-v1)            7 smoke history (byte-equal)
  2 per-agent spawn/removal frames       8 agent_scalars rows
  3 exit history (byte-equal)            9 app-manifest fields (paths, created_utc excluded)
  4 route history (byte-equal)          10 exit code, summary line, "Looks from a node point" line; 10c route-cost sample
     count only if both runs wrote the route-cost history (else gap, never "equal")
  5 route-cost history (byte-equal)     11 vismap arrays (meta compared without fds_dir), 11b format is 6
  6 FED history (byte-equal)            12 cognitive-map history + metrics (result capture)

An item written by only one run (e.g. route-cost history in O_study vs
O_norc) is "not_in_both" and does not fail the pair; an item written by
neither is "absent". Item 12 needs ``--capture-result`` on both runs (both
through perf_run.py); otherwise it is reported as the named gap
"cognitive-map state not compared". Verdict: "equivalent" only if no
compared item differs; gaps are listed next to the verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

STUDY = Path(__file__).resolve().parent
sys.path.insert(0, str(STUDY))
from traj_hash import traj_hash  # noqa: E402

FILES = {3: "exit.csv", 4: "rh.csv", 5: "rc.csv", 6: "fed.csv", 7: "smoke.csv"}
APP_FIELDS = ["outcome", "fds_coverage", "fds_outside", "seed", "agent_seeding", "versions",
              "uv_lock_sha256", "git_commit", "git_dirty"]
METRIC_EXCLUDE = re.compile(r"wall|elapsed|path|file|created|duration_s_real", re.I)


def load(run: str) -> tuple[dict, Path, Path]:
    rec = Path(run) if Path(run).is_dir() else STUDY / "results" / "raw" / run
    m = json.loads((rec / "manifest.json").read_text())
    return m, rec, Path(m["outputs_dir"])


def sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def pair_state(a, b):
    if a is None and b is None:
        return "absent"
    if a is None or b is None:
        return "not_in_both"
    return "equal" if a == b else "DIFFERENT"


def frames(db: Path):
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [list(r) for r in con.execute(
            "select id, min(frame), max(frame) from trajectory_data group by id order by id")]
    finally:
        con.close()


def scalars(db: Path):
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        if not con.execute("select name from sqlite_master where name='agent_scalars'").fetchone():
            return None
        h = hashlib.sha256()
        for r in con.execute("select * from agent_scalars order by frame, id"):
            h.update((",".join(repr(v) for v in r) + "\n").encode())
        return h.hexdigest()
    finally:
        con.close()


def app_fields(out: Path):
    p = out / "traj.manifest.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return {k: d.get(k) for k in APP_FIELDS}


def log_facts(m: dict, rec: Path):
    log = "".join((rec / n).read_text(errors="replace") for n in ("stdout.log", "stderr.log")
                  if (rec / n).exists())
    f = {"exit_code": m.get("exit_code"), "summary_line": (m.get("outcome") or {}).get("summary_line")}
    # "Route cost samples: N" is printed only with --output-route-cost-history, so it is
    # item 10c, compared only when both runs wrote the history (not part of item 10).
    # Logged only when a run looks from a node point (item 10); None when absent.
    mm = re.search(r"Looks from a node point before a patrol: (\d+), given up: (\d+)", log)
    f["looks_from_node_point"] = [int(mm.group(1)), int(mm.group(2))] if mm else None
    return f


def route_cost_samples(m: dict, rec: Path, out: Path):
    """The 'Route cost samples: N' count, or None when the run wrote no route-cost history."""
    if not (out / "rc.csv").exists():
        return None
    log = (rec / "stdout.log").read_text(errors="replace") if (rec / "stdout.log").exists() else ""
    mm = re.search(r"Route cost samples: (\d+)", log)
    return int(mm.group(1)) if mm else None


def vis_path(m: dict, out: Path) -> Path | None:
    if (out / "vis.npz").exists():
        return out / "vis.npz"
    vc = (m.get("cache_after") or {}).get("vis_cache")
    return Path(vc["path"]) if vc and Path(vc["path"]).exists() else None


def vis_arrays(p: Path | None):
    if p is None:
        return None
    with np.load(p, allow_pickle=False) as d:
        h = {k: hashlib.sha256(np.ascontiguousarray(d[k]).tobytes()).hexdigest()
             + f":{d[k].dtype}:{d[k].shape}" for k in sorted(d.files) if k != "meta"}
        meta = json.loads(str(d["meta"]))
    meta.pop("fds_dir", None)
    h["meta_without_fds_dir"] = json.dumps(meta, sort_keys=True)
    h["format_is_6"] = meta.get("format") == 6
    return h


def capture(m: dict):
    p = m.get("result_capture_path")
    if not p or not Path(p).exists():
        return None
    d = json.loads(Path(p).read_text())
    metrics = {k: v for k, v in (d.get("metrics") or {}).items() if not METRIC_EXCLUDE.search(k)}
    return {"cognitive_map_history": d.get("cognitive_map_history"), "metrics": metrics}


def compare(run_a: str, run_b: str) -> dict:
    (ma, ra, oa), (mb, rb, ob) = load(run_a), load(run_b)
    items = {}
    ta = traj_hash(str(oa / "traj.sqlite")) if (oa / "traj.sqlite").exists() else None
    tb = traj_hash(str(ob / "traj.sqlite")) if (ob / "traj.sqlite").exists() else None
    items["1_trajectory_repr_v1"] = pair_state(ta, tb)
    items["2_spawn_removal_frames"] = pair_state(frames(oa / "traj.sqlite"), frames(ob / "traj.sqlite"))
    for i, name in FILES.items():
        items[f"{i}_{name}"] = pair_state(sha(oa / name), sha(ob / name))
    items["8_agent_scalars"] = pair_state(scalars(oa / "traj.sqlite"), scalars(ob / "traj.sqlite"))
    items["9_app_manifest_fields"] = pair_state(app_fields(oa), app_fields(ob))
    la, lb = log_facts(ma, ra), log_facts(mb, rb)
    items["10_exit_summary_counts"] = pair_state(la, lb)
    sa, sb = route_cost_samples(ma, ra, oa), route_cost_samples(mb, rb, ob)
    items["10c_route_cost_samples"] = pair_state(sa, sb)
    va, vb = vis_arrays(vis_path(ma, oa)), vis_arrays(vis_path(mb, ob))
    items["11_vismap_arrays"] = pair_state(va, vb)
    fmt = [v["format_is_6"] for v in (va, vb) if v is not None]
    items["11b_vismap_format_is_6"] = "absent" if not fmt else ("equal" if all(fmt) else "DIFFERENT")
    ca, cb = capture(ma), capture(mb)
    items["12_cognitive_map_history"] = pair_state(
        ca and ca["cognitive_map_history"], cb and cb["cognitive_map_history"])
    items["12b_result_metrics"] = pair_state(ca and ca["metrics"], cb and cb["metrics"])
    gaps = []
    if items["1_trajectory_repr_v1"] != "equal":
        gaps.append("trajectories not compared (no SQLite copy in one run)")
    if ma["case"].startswith("W3") and items["12_cognitive_map_history"] != "equal":
        gaps.append("cognitive-map state not compared")
    if items["10c_route_cost_samples"] == "not_in_both":
        gaps.append("10c route_cost_samples not compared (route-cost history not written by both)")
    diffs = [k for k, v in items.items() if v == "DIFFERENT"]
    detail = {}
    if "10_exit_summary_counts" in diffs:
        detail["10"] = {"a": la, "b": lb}
    return {"a": ma["run_id"], "b": mb["run_id"],
            "a_combo": [ma["case"], ma["variant"], ma["instrumentation"]["counters_env_set"],
                        ma["seed"]],
            "b_combo": [mb["case"], mb["variant"], mb["instrumentation"]["counters_env_set"],
                        mb["seed"]],
            "items": items, "different": diffs, "gaps": gaps, "detail": detail,
            "verdict": "NOT equivalent" if diffs else "equivalent"}


def negative_control(run: str) -> dict:
    """Copy one run, perturb one output minimally, and require NOT equivalent.

    Perturbations, each in its own scratch copy: one byte of exit.csv (last
    digit of the last line), and one trajectory float (pos_x of the last row
    moved by one ulp). Each must be detected; the unperturbed copy must be
    equivalent to the original.
    """
    import shutil
    import tempfile

    m, rec, out = load(run)
    results = {}
    with tempfile.TemporaryDirectory(dir=STUDY / "results") as tmp:
        for name in ("identity", "exit_csv_one_byte", "trajectory_one_ulp"):
            c_rec, c_out = Path(tmp) / name / "rec", Path(tmp) / name / "out"
            shutil.copytree(rec, c_rec)
            shutil.copytree(out, c_out)
            cm = json.loads((c_rec / "manifest.json").read_text())
            cm["outputs_dir"] = str(c_out)
            cm["run_id"] = f"{m['run_id']}__{name}"
            if cm.get("result_capture_path"):
                cm["result_capture_path"] = str(c_rec / Path(cm["result_capture_path"]).name)
            (c_rec / "manifest.json").write_text(json.dumps(cm))
            if name == "exit_csv_one_byte":
                p = c_out / "exit.csv"
                b = bytearray(p.read_bytes())
                i = max(j for j, ch in enumerate(b) if 48 <= ch <= 57)
                b[i] = 48 + (b[i] - 48 + 1) % 10
                p.write_bytes(bytes(b))
            if name == "trajectory_one_ulp":
                con = sqlite3.connect(c_out / "traj.sqlite")
                fr, i, x = con.execute("select frame, id, pos_x from trajectory_data "
                                       "order by frame desc, id desc limit 1").fetchone()
                con.execute("update trajectory_data set pos_x=? where frame=? and id=?",
                            (float(np.nextafter(x, np.inf)), fr, i))
                con.commit()
                con.close()
            r = compare(run, str(c_rec))
            results[name] = {"verdict": r["verdict"], "different": r["different"]}
    ok = (results["identity"]["verdict"] == "equivalent"
          and results["exit_csv_one_byte"]["different"] == ["3_exit.csv"]
          and "1_trajectory_repr_v1" in results["trajectory_one_ulp"]["different"])
    return {"run": m["run_id"], "controls": results,
            "negative_control": "PASS" if ok else "FAIL"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--block")
    ap.add_argument("--ref")
    ap.add_argument("--out")
    ap.add_argument("--negative-control")
    a = ap.parse_args()
    if a.negative_control:
        res = [negative_control(a.negative_control)]
    elif a.block:
        ids = sorted(p.name for p in (STUDY / "results" / "raw").glob(f"{a.block}_*")
                     if p.name != a.ref)
        res = [compare(a.ref, i) for i in ids]
    else:
        res = [compare(a.runs[0], a.runs[1])]
    text = json.dumps(res, indent=1)
    print(text)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
