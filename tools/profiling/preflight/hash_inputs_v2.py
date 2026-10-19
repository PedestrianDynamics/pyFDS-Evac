"""Append the G0 v2 staged inputs (D15, D17) to input_hashes.json (copy-only staging).

Hashes the sciebo source and the staged copy of each directory, requires them
equal, and adds the entry under fds_dirs / sciebo_files with the same layout as
hash_inputs.py. Existing entries are left as they are.

Usage: python hash_inputs_v2.py STAGE
"""

import json
import pathlib
import sys

from hash_inputs import SCIEBO, aggregate, sha_file

STUDY = pathlib.Path(__file__).resolve().parent
FDS = {
    "fed_incap_co_2000ppm/fds": "fed_incap_co_2000ppm",
    "world100/fire_4p5MW": "world100_fire_4p5MW",
}
DECK = ["world100/evac_4exits/deck_config_stream_east.json", "world100/evac_4exits/deck_geometry.wkt"]


def hash_dir(d):
    return {p.name: sha_file(p) for p in sorted(d.iterdir()) if p.is_file() and p.suffix != ".pickle"}


def main():
    stage = pathlib.Path(sys.argv[1])
    ref = json.loads((STUDY / "input_hashes.json").read_text())
    for key, name in FDS.items():
        src, dst = hash_dir(SCIEBO / key), hash_dir(stage / "fds" / name)
        if src != dst:
            raise SystemExit(f"{key}: staged copy differs from sciebo")
        ref["fds_dirs"][key] = {
            "path": str(SCIEBO / key), "staged_as": f"fds/{name}", "n_files": len(dst),
            "bytes": sum((stage / "fds" / name / n).stat().st_size for n in dst),
            "aggregate_sha256": aggregate(dst), "files": dst, "excluded_mutable_cache": {},
        }
    for rel in DECK:
        ref["sciebo_files"][rel] = sha_file(SCIEBO / rel)
        staged = stage / "decks/world100_evac_4exits" / pathlib.Path(rel).name
        if sha_file(staged) != ref["sciebo_files"][rel]:
            raise SystemExit(f"{rel}: staged copy differs")
    (STUDY / "input_hashes.json").write_text(json.dumps(ref, indent=1))
    print({k: ref["fds_dirs"][k]["aggregate_sha256"][:12] for k in FDS})


if __name__ == "__main__":
    main()
