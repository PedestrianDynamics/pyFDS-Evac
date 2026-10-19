"""Read-only preflight of finished FDS slice output (no fdsreader, no cache writes).

Parses the .smv SLCF blocks and each .sf file (Fortran unformatted) directly,
so the fdsreader pickle next to the data is neither read nor rewritten.
Prints, per horizontal slice quantity and height: meshes, frames, first/last
time, output interval, global min/max and max at probe times.

Usage: python preflight_fds.py FDS_DIR [--probe 60,120,...] [--json OUT]
"""

import argparse
import json
import pathlib
import re
import struct

import numpy as np


def _records(buf):
    pos = 0
    while pos < len(buf):
        (n,) = struct.unpack_from("<i", buf, pos)
        yield buf[pos + 4 : pos + 4 + n]
        pos += n + 8


def read_sf(path):
    buf = path.read_bytes()
    recs = _records(buf)
    name = next(recs).decode(errors="replace").strip()
    next(recs)
    next(recs)
    i1, i2, j1, j2, k1, k2 = struct.unpack("<6i", next(recs))
    times, mins, maxs = [], [], []
    for rec in recs:
        (t,) = struct.unpack("<f", rec)
        data = np.frombuffer(next(recs), dtype="<f4")
        times.append(t)
        mins.append(float(data.min()))
        maxs.append(float(data.max()))
    return name, (i1, i2, j1, j2, k1, k2), np.array(times), np.array(mins), np.array(maxs)


def mesh_dims(smv_text):
    dims = []
    lines = smv_text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("GRID"):
            ijk = [int(v) for v in lines[idx + 1].split()[:3]]
            dims.append({"ijk": ijk})
        if line.startswith("PDIM"):
            xb = [float(v) for v in lines[idx + 1].split()[:6]]
            dims[-1]["xb"] = xb
    return dims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fds_dir")
    ap.add_argument("--probe", default="60,120,180,240,300,400,480")
    ap.add_argument("--json")
    args = ap.parse_args()
    d = pathlib.Path(args.fds_dir)
    smv = next(d.glob("*.smv"))
    text = smv.read_text(errors="replace")
    meshes = mesh_dims(text)
    probes = [float(p) for p in args.probe.split(",") if p]
    groups = {}
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not re.match(r"^\s*SLCF", line):
            continue
        fname = lines[idx + 1].strip()
        qty = lines[idx + 2].strip()
        m = re.search(r"_(\d+)_(\d+)\.sf$", fname)
        mesh = int(m.group(1))
        f = d / fname
        if not f.exists():
            groups.setdefault(("MISSING", fname), []).append(None)
            continue
        _, (i1, i2, j1, j2, k1, k2), t, mn, mx = read_sf(f)
        if k1 != k2:
            continue  # vertical slice
        md = meshes[mesh - 1]
        z0, z1 = md["xb"][4], md["xb"][5]
        z = round(z0 + k1 * (z1 - z0) / md["ijk"][2], 3)
        groups.setdefault((qty, z), []).append(
            {"mesh": mesh, "file": fname, "t": t, "min": mn, "max": mx}
        )
    out = []
    for (qty, z), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if qty == "MISSING":
            out.append({"missing": z})
            continue
        t_last = min(float(it["t"][-1]) for it in items)
        t_first = max(float(it["t"][0]) for it in items)
        nfr = sorted({len(it["t"]) for it in items})
        dt = float(np.median(np.diff(items[0]["t"]))) if len(items[0]["t"]) > 1 else None
        gmin = min(float(it["min"].min()) for it in items)
        gmax = max(float(it["max"].max()) for it in items)
        at = {}
        for p in probes:
            vals = []
            for it in items:
                k = int(np.argmin(np.abs(it["t"] - p)))
                if abs(it["t"][k] - p) <= (dt or 1.0):
                    vals.append(float(it["max"][k]))
            at[str(p)] = max(vals) if vals else None
        out.append(
            {
                "quantity": qty,
                "z_m": z,
                "meshes": sorted(it["mesh"] for it in items),
                "frames": nfr,
                "t_first": t_first,
                "t_last_min_over_meshes": t_last,
                "dt": dt,
                "min": gmin,
                "max": gmax,
                "max_at_probe": at,
            }
        )
    res = {"fds_dir": str(d), "smv": smv.name, "n_meshes": len(meshes),
           "meshes": meshes, "slices": out}
    print(json.dumps(res, indent=1))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
