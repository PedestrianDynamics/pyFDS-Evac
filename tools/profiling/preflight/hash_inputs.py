"""Hash FDS output directories and commit-pinned repo inputs (read-only).

Usage: python hash_inputs.py OUT.json
FDS dirs: every regular file except the mutable fdsreader cache (*.pickle),
which is listed with size/mtime only. Aggregate = sha256 over sorted
"<name> <sha256>" lines. Repo inputs are hashed from `git show COMMIT:path`.
"""

import hashlib
import json
import pathlib
import subprocess
import sys

REPO = "/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/pyFDS-EVAC"
COMMIT = "8f7d29a2e056db46183e8cccabce338c398606a1"
SCIEBO = pathlib.Path(
    "/Users/chraibi/sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de/fds-evac-data"
)
FDS_DIRS = {
    "schroeder2015-route/a047_pvc_h40": SCIEBO / "schroeder2015-route/a047_pvc_h40",
    "t_junction/fire_2MW_PVC": SCIEBO / "t_junction/fire_2MW_PVC",
    "cognitive_map_memory/clear_air": SCIEBO / "cognitive_map_memory/clear_air",
}
SCIEBO_FILES = [
    "schroeder2015-route/evac/config_gate.json",
    "schroeder2015-route/evac/config_additive.json",
    "schroeder2015-route/evac/geometry.wkt",
]
REPO_FILES = [
    "run.py",
    "uv.lock",
    "pyproject.toml",
    "scripts/ab_trajectories.py",
    "assets/schroeder2015_route/evac/config_gate.json",
    "assets/schroeder2015_route/evac/config_additive.json",
    "assets/schroeder2015_route/evac/geometry.wkt",
    "assets/schroeder2015_route/a047_pvc_h40/a047_pvc_h40.fds",
    "assets/schroeder2015_route/run_p1.sh",
    "assets/schroeder2015_route/make_configs.py",
    "assets/t_junction/config_discovery.json",
    "assets/t_junction/config_full.json",
    "assets/t_junction/config.json",
    "assets/t_junction/geometry.wkt",
    "assets/t_junction/t_junction.fds",
    "assets/cognitive_map_memory/config.json",
    "assets/cognitive_map_memory/geometry.wkt",
    "assets/iso_table21_coupled/config.json",
    "assets/iso_table21_coupled/geometry.wkt",
    "assets/iso_table22_coupled/config_a.json",
    "assets/iso_table22_coupled/config_b.json",
    "assets/iso_table22_coupled/config_c.json",
    "assets/iso_table22_coupled/config_d.json",
    "assets/iso_table22_coupled/geometry.wkt",
]
REPO_DIRS = [
    "assets/iso_table21_coupled/fds",
    "assets/iso_table22_coupled/fds/a",
    "assets/iso_table22_coupled/fds/b",
    "assets/iso_table22_coupled/fds/c",
    "assets/iso_table22_coupled/fds/d",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def aggregate(files: dict) -> str:
    return sha("".join(f"{k} {v}\n" for k, v in sorted(files.items())).encode())


def git_show(path: str) -> bytes:
    return subprocess.check_output(["git", "-C", REPO, "show", f"{COMMIT}:{path}"])


def main():
    out = {"commit": COMMIT, "fds_dirs": {}, "sciebo_files": {}, "repo_files": {}, "repo_dirs": {}}
    for key, d in FDS_DIRS.items():
        files, mutable = {}, {}
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            if p.suffix == ".pickle":
                st = p.stat()
                mutable[p.name] = {"bytes": st.st_size, "mtime": st.st_mtime}
                continue
            files[p.name] = sha_file(p)
        out["fds_dirs"][key] = {
            "path": str(d),
            "n_files": len(files),
            "bytes": sum((d / n).stat().st_size for n in files),
            "aggregate_sha256": aggregate(files),
            "files": files,
            "excluded_mutable_cache": mutable,
        }
    for rel in SCIEBO_FILES:
        out["sciebo_files"][rel] = sha_file(SCIEBO / rel)
    for rel in REPO_FILES:
        out["repo_files"][rel] = sha(git_show(rel))
    for rel in REPO_DIRS:
        names = subprocess.check_output(
            ["git", "-C", REPO, "ls-tree", "--name-only", COMMIT, rel + "/"], text=True
        ).split()
        files = {pathlib.Path(n).name: sha(git_show(n)) for n in names}
        out["repo_dirs"][rel] = {"aggregate_sha256": aggregate(files), "files": files}
    pathlib.Path(sys.argv[1]).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
