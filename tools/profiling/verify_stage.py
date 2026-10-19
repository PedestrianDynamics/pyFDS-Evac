"""Verify $STAGE/fds/* against preflight/input_hashes.json (read-only).

Usage: python verify_stage.py STAGE OUT.json
Exit 1 on any missing, extra or mismatching file (pickles ignored).
"""

import hashlib
import json
import pathlib
import sys

STUDY = pathlib.Path(__file__).resolve().parent
MAP = {
    "a047_pvc_h40": ("fds_dirs", "schroeder2015-route/a047_pvc_h40"),
    "t_junction_fire_2MW_PVC": ("fds_dirs", "t_junction/fire_2MW_PVC"),
    "cmm_clear_air": ("fds_dirs", "cognitive_map_memory/clear_air"),
    "fed_incap_co_2000ppm": ("fds_dirs", "fed_incap_co_2000ppm/fds"),
    "world100_fire_4p5MW": ("fds_dirs", "world100/fire_4p5MW"),
    "iso_table21_coupled": ("repo_dirs", "assets/iso_table21_coupled/fds"),
    **{f"iso_table22_{c}": ("repo_dirs", f"assets/iso_table22_coupled/fds/{c}") for c in "abcd"},
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(stage_dir, ref):
    want = {k: v for k, v in ref["files"].items() if not k.endswith(".pickle")}
    have = {p.name: sha(p) for p in stage_dir.iterdir() if p.is_file() and p.suffix != ".pickle"}
    return {
        "n_files": len(have),
        "missing": sorted(set(want) - set(have)),
        "extra": sorted(set(have) - set(want)),
        "mismatch": sorted(k for k in set(want) & set(have) if want[k] != have[k]),
        "aggregate_sha256": hashlib.sha256(
            "".join(f"{k} {have[k]}\n" for k in sorted(have)).encode()
        ).hexdigest(),
    }


def main():
    stage = pathlib.Path(sys.argv[1])
    ref = json.loads((STUDY / "preflight/input_hashes.json").read_text())
    report = {name: check(stage / "fds" / name, ref[sec][key]) for name, (sec, key) in MAP.items()}
    pathlib.Path(sys.argv[2]).write_text(json.dumps(report, indent=1) + "\n")
    bad = {n: r for n, r in report.items() if r["missing"] or r["extra"] or r["mismatch"]}
    for n, r in report.items():
        print(n, r["n_files"], "OK" if n not in bad else "FAIL", r["aggregate_sha256"][:12])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
