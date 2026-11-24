"""Summarise benchmark runs: median, range, IQR, n, peak RSS and outcome per case.

Usage: analyse.py [--outdir DIR]     (default: ./benchmark-results)
Reads DIR/summary.csv (written by benchmark.py) and writes
  DIR/stats.csv         one row per case, seed and variant
  DIR/paper_table.md    the same as a markdown table
  DIR/runs_table.md     every run, warm-ups and failures included
Groups never pool different seeds, variants or cache states. Warm-up runs are
listed in runs_table.md only. Runs killed at the cap or failed are counted in
n_failed and left out of the timing statistics, never dropped from the report.
n <= 3 groups report the range as spread, n >= 4 groups also the IQR
(inclusive quartiles). Missing values are null (empty), never zero.
"""

import argparse
import csv
import os
import statistics as st
from collections import defaultdict

CASE_ORDER = ("W1a", "W1a_minimal", "W2a", "W3", "W1a_n100", "W1a_n400", "W1b")
VALID = ("ok", "incomplete_exit2")
STATS_COLS = [
    "case",
    "seed",
    "variant",
    "n",
    "n_failed",
    "median_wall_s",
    "min_wall_s",
    "max_wall_s",
    "range_s",
    "iqr_s",
    "median_loop_s",
    "median_cpu_s",
    "max_rss_mib",
    "outcome",
]


def num(x):
    return float(x) if x not in ("", None) else None


def variant(row):
    kind = row["kind"]
    if kind == "first_use":
        return "first use"
    if kind == "measured":
        return "reuse" if row["case"] == "W3" else "normal"
    return kind


def outcome(rows):
    """Distinct end states as 'status/end_reason evacuated/remaining'."""
    states = {
        f"{r['status']}/{r['end_reason'] or 'null'} {r['evacuated'] or 'null'}/{r['remaining'] or 'null'}"
        for r in rows
    }
    return "; ".join(sorted(states))


def median_or_none(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 2) if xs else None


def group_stats(key, rows):
    case, seed, var = key
    ok = [r for r in rows if r["status"] in VALID]
    w = sorted(float(r["wall_s"]) for r in ok)
    out = dict(
        case=case, seed=seed, variant=var, n=len(ok), n_failed=len(rows) - len(ok)
    )
    out["outcome"] = outcome(rows)
    if not w:
        return out
    q = st.quantiles(w, n=4, method="inclusive") if len(w) >= 4 else None
    out.update(
        median_wall_s=round(st.median(w), 2),
        min_wall_s=round(w[0], 2),
        max_wall_s=round(w[-1], 2),
        range_s=round(w[-1] - w[0], 2),
        iqr_s=round(q[2] - q[0], 2) if q else None,
        median_loop_s=median_or_none([num(r["loop_s"]) for r in ok]),
        median_cpu_s=median_or_none([num(r["cpu_total_s"]) for r in ok]),
        max_rss_mib=max(int(r["peak_rss_kib"]) for r in ok) // 1024,
    )
    return out


def sort_key(row):
    order = (
        CASE_ORDER.index(row["case"]) if row["case"] in CASE_ORDER else len(CASE_ORDER)
    )
    return (order, row["case"], int(row["seed"]), row["variant"])


def stats_table(rows):
    groups = defaultdict(list)
    for r in rows:
        if r["kind"] != "warmup":
            groups[(r["case"], r["seed"], variant(r))].append(r)
    return sorted((group_stats(k, v) for k, v in groups.items()), key=sort_key)


def cell(x, fmt="{}"):
    return "null" if x is None else fmt.format(x)


def paper_table(table):
    head = "| case | seed | variant | n | failed | median wall s | range s | IQR s | median CPU s | peak RSS MiB | outcome |"
    lines = [head, "|" + "---|" * 11]
    for r in table:
        rng = f"{cell(r.get('min_wall_s'), '{:.1f}')} to {cell(r.get('max_wall_s'), '{:.1f}')}"
        lines.append(
            f"| {r['case']} | {r['seed']} | {r['variant']} | {r['n']} | {r['n_failed']} "
            f"| {cell(r.get('median_wall_s'), '{:.1f}')} | {rng} "
            f"| {cell(r.get('iqr_s'), '{:.1f}') if r['n'] >= 4 else '-'} "
            f"| {cell(r.get('median_cpu_s'), '{:.1f}')} | {cell(r.get('max_rss_mib'))} | {r['outcome']} |"
        )
    return "\n".join(lines)


def runs_table(rows):
    lines = [
        "| run_id | kind | status | wall s | loop s | evac/remaining | peak RSS MiB |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        loop = num(r["loop_s"])
        rss = int(r["peak_rss_kib"]) // 1024 if r["peak_rss_kib"] else None
        lines.append(
            f"| {r['run_id']} | {r['kind']} | {r['status']} | {float(r['wall_s']):.1f} "
            f"| {cell(loop, '{:.1f}')} | {r['evacuated'] or 'null'}/{r['remaining'] or 'null'} | {cell(rss)} |"
        )
    return "\n".join(lines)


def write_stats(path, table):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, STATS_COLS)
        w.writeheader()
        w.writerows(
            {k: ("" if r.get(k) is None else r[k]) for k in STATS_COLS} for r in table
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default=os.path.join(os.getcwd(), "benchmark-results"))
    a = p.parse_args()
    with open(os.path.join(a.outdir, "summary.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    table = stats_table(rows)
    write_stats(os.path.join(a.outdir, "stats.csv"), table)
    md = paper_table(table)
    with open(os.path.join(a.outdir, "paper_table.md"), "w") as f:
        f.write(md + "\n")
    with open(os.path.join(a.outdir, "runs_table.md"), "w") as f:
        f.write(runs_table(rows) + "\n")
    print(md)


if __name__ == "__main__":
    main()
