"""Exact comparison of two kept benchmark runs (run directories).

Usage: compare_outputs.py RUN_DIR_A RUN_DIR_B [OUT_JSON]
Compares, with no tolerance:
  - every table of run.sqlite (all columns, rowid order; if only the order
    differs the sorted comparison is reported separately), except that the
    geometry blob is compared by hash like the rest;
  - every CSV (rh, exit, fed, rc, knowledge, smoke) byte for byte (sha256),
    with the first differing line when they differ;
  - run.manifest.json outcome and seed;
  - stdout without the progress lines (which carry wall-clock time) and
    without time stamps;
  - stderr byte for byte after replacing each run's checkout path by
    <CHECKOUT> (checkouts of different runs may live in different paths);
  - the CSV set is the union of both runs (a file missing on one side is NOT
    equal);
  - vis.npz: sha256, or (if the sha differs) all arrays equal and the meta
    equal after the same path normalisation; inputs and FDS listing hashes from the
    benchmark manifests.
Exit status 0 only if every item is equal.

Option --allow-missing=NAME (repeatable): a CSV that one run deliberately lacks
(route-cost history in E2); the stdout lines that report it are ignored too.

Deliberately NOT compared (they differ between identical runs by design):
timestamps and wall times (manifest.json, stdout_stamped.txt, progress lines
"Evacuated ..." which carry wall-clock), run ids and absolute paths, the
run.manifest.json fields other than outcome and seed (created_utc, paths),
the contents of tmp/, host load and measurements. Staged inputs are compared
by sha256, not by path. The sqlite files are compared by table content, not
by file bytes.
"""

import hashlib
import json
import os
import sqlite3
import sys


def table_hash(con, table, order):
    h = hashlib.sha256()
    n = 0
    for row in con.execute(f"select * from {table} {order}"):
        h.update(repr(row).encode())
        n += 1
    return h.hexdigest(), n


def compare_sqlite(pa, pb):
    ca, cb = sqlite3.connect(pa), sqlite3.connect(pb)
    names = [
        r[0]
        for r in ca.execute(
            "select name from sqlite_master where type='table' order by name"
        )
    ]
    names_b = [
        r[0]
        for r in cb.execute(
            "select name from sqlite_master where type='table' order by name"
        )
    ]
    out = {"tables_equal": names == names_b}
    for t in names:
        ha, na = table_hash(ca, t, "order by rowid")
        hb, nb = table_hash(cb, t, "order by rowid")
        entry = {"rows": [na, nb], "equal": ha == hb, "sha256_a": ha[:16]}
        if ha != hb:
            cols = [r[1] for r in ca.execute(f"pragma table_info({t})")]
            order = "order by " + ",".join(cols)
            sa, _ = table_hash(ca, t, order)
            sb, _ = table_hash(cb, t, order)
            entry["equal_when_sorted"] = sa == sb
        out[t] = entry
    return out


def first_diff(pa, pb):
    with open(pa, errors="replace") as fa, open(pb, errors="replace") as fb:
        pairs = enumerate(zip(fa, fb), 1)
        hit = next(((i, x, y) for i, (x, y) in pairs if x != y), None)
    if hit is None:
        return {"note": "common prefix equal, lengths differ"}
    i, x, y = hit
    return {"line": i, "a": x[:200], "b": y[:200]}


def vis_cache_equal(a, b, wa, wb, ba, bb):
    """Same sha256, or equal arrays and equal meta once the checkout path is
    normalised (the cache meta records the FDS directory path)."""
    sha_a, sha_b = ba["vis_cache_sha256_after"], bb["vis_cache_sha256_after"]
    out = {
        "sha256_after_a": sha_a,
        "sha256_after_b": sha_b,
        "sha_equal": sha_a == sha_b,
    }
    if sha_a == sha_b:
        out["equal"] = True
        return out
    import numpy as np

    za = np.load(a + "/vis.npz", allow_pickle=True)
    zb = np.load(b + "/vis.npz", allow_pickle=True)
    same = za.files == zb.files
    for k in za.files:
        if k == "meta":
            ma = str(za[k]).replace(wa.decode(), "<CHECKOUT>")
            mb = str(zb[k]).replace(wb.decode(), "<CHECKOUT>")
            same = same and ma == mb
        else:
            same = same and np.array_equal(za[k], zb[k])
    out["equal"] = same
    out["note"] = "sha differs; arrays and path-normalised meta compared"
    return out


def filtered_stdout(path):
    keep = []
    for line in open(path + "/stdout_stamped.txt"):
        body = line[10:].rstrip("\n")
        if (
            not body.startswith(("Evacuated ", "Route cost samples"))
            and "Route cost history" not in body
        ):
            keep.append(body)
    return keep


def is_flag(key):
    if key in ("equal", "tables_equal", "staged_equal"):
        return True
    return key.startswith(("fds_listing", "pickles_"))


def flat(x, acc):
    """Collect every equality flag of the nested report."""
    if not isinstance(x, dict):
        return acc
    for k, v in x.items():
        if is_flag(k):
            acc.append(v)
        flat(v, acc)
    return acc


def main():
    allowed = [x.split("=", 1)[1] for x in sys.argv if x.startswith("--allow-missing=")]
    args = [x for x in sys.argv[1:] if not x.startswith("--allow-missing=")]
    a, b = args[:2]
    sys.argv = [sys.argv[0]] + args
    rep = {
        "run_a": os.path.basename(a.rstrip("/")),
        "run_b": os.path.basename(b.rstrip("/")),
    }
    rep["sqlite"] = compare_sqlite(a + "/run.sqlite", b + "/run.sqlite")
    csvs = sorted(
        {
            f
            for d in (a, b)
            for f in os.listdir(d)
            if f.endswith(".csv") and f not in allowed
        }
    )
    rep["csv_allowed_missing"] = allowed
    rep["csv"] = {}
    for f in csvs:
        missing = [
            n for n, d in (("a", a), ("b", b)) if not os.path.exists(os.path.join(d, f))
        ]
        if missing:
            rep["csv"][f] = {"equal": False, "note": "missing in " + ",".join(missing)}
            continue
        ha = hashlib.sha256(open(os.path.join(a, f), "rb").read()).hexdigest()
        hb = hashlib.sha256(open(os.path.join(b, f), "rb").read()).hexdigest()
        rep["csv"][f] = {"equal": ha == hb, "sha256_a": ha[:16]}
        if ha != hb:
            rep["csv"][f]["first_diff"] = first_diff(
                os.path.join(a, f), os.path.join(b, f)
            )
    ma = json.load(open(a + "/run.manifest.json"))
    mb = json.load(open(b + "/run.manifest.json"))
    rep["manifest_outcome_seed"] = {
        "equal": (ma["outcome"], ma["seed"]) == (mb["outcome"], mb["seed"]),
        "a": ma["outcome"],
    }
    rep["stdout_without_progress"] = {"equal": filtered_stdout(a) == filtered_stdout(b)}
    wa = json.load(open(a + "/manifest.json"))["checkout"].encode()
    wb = json.load(open(b + "/manifest.json"))["checkout"].encode()
    sa = open(a + "/stderr.txt", "rb").read().replace(wa, b"<CHECKOUT>")
    sb = open(b + "/stderr.txt", "rb").read().replace(wb, b"<CHECKOUT>")
    rep["stderr"] = {"equal": sa == sb, "bytes": [len(sa), len(sb)]}
    rep["vis_cache"] = None
    if os.path.exists(a + "/vis.npz"):
        ba = json.load(open(a + "/manifest.json"))["input_fingerprints"]
        bb = json.load(open(b + "/manifest.json"))["input_fingerprints"]
        rep["vis_cache"] = vis_cache_equal(a, b, wa, wb, ba, bb)
    ia = json.load(open(a + "/manifest.json"))["input_fingerprints"]
    ib = json.load(open(b + "/manifest.json"))["input_fingerprints"]
    rep["inputs"] = {
        "staged_equal": ia["staged"] == ib["staged"]
        or {k: v["staged_sha256"] for k, v in ia["staged"].items()}
        == {k: v["staged_sha256"] for k, v in ib["staged"].items()},
        "fds_listing_unchanged_a": ia["fds_dir_listing_unchanged"],
        "fds_listing_unchanged_b": ib["fds_dir_listing_unchanged"],
        "pickles_unchanged_a": ia["pickles_unchanged"],
        "pickles_unchanged_b": ib["pickles_unchanged"],
    }
    flags = flat(rep, [])
    rep["verdict"] = "EQUAL" if flags and all(flags) else "DIFFERS"
    rep["n_checks"] = len(flags)
    text = json.dumps(rep, indent=1, default=str)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w").write(text)
    print(text)
    sys.exit(0 if rep["verdict"] == "EQUAL" else 1)


if __name__ == "__main__":
    main()
