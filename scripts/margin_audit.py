"""Audit one routing-block margin: paired runs with it on and off (#187).

Stage 2 of #187 decides, margin by margin, whether a switch-resisting margin
of the route-cost model has a distinct measured effect. Every audit is a
config sweep: the margin's routing key is set to its off value in a copy of
the scenario, every other key stays as the scenario has it, and nothing in
the code changes. Each seed runs paired, base and off, on the FDS output in
sciebo (no FDS run)::

    <out>/<deck>/seed<N>/<base|off>/scenario/   the config and geometry run
    <out>/<deck>/seed<N>/<base|off>/trajectory.sqlite, route_history.csv,
                                     exit_history.csv, run.log
    <out>/<deck>/seed<N>/<base|off>/metrics.json  the per-run metrics below
    <out>/manifest.json                  commit, dirty state, margin values,
                                         seeds, versions and wall time per run
    <out>/report.{json,md}               written by ``analyse``

Per run the metrics are those of the stage-2 plan: route switches by reason
(a row of the route history with an old exit), exit switches (old and new
exit differ), returns in the #124 sense (an exit switch back to an exit the
agent switched away from earlier), exit shares, FED at egress from
``agent_scalars`` and egress times from the trajectory.

``analyse`` takes the paired per-seed differences d = off - base on the
predeclared primary deck and primary metric, runs a two-sided paired
permutation test on the mean of d (sign flips, exact up to 20 seeds, else
Monte-Carlo with a fixed seed), compares |mean d| with the metric's floor
and applies the stage-2 outcome rule. The other decks and metrics are
descriptive. For a deck run in clear air the report also says whether base
and off are identical: the histories byte for byte, the trajectory table by
table without JuPedSim's per-process geometry hash (C10).

Usage::

    uv run python scripts/margin_audit.py run --margin fed_return_margin \\
        --decks l_corridor_gate t_junction_pre30 [--seeds 1 2 ...] [--jobs 4]
    uv run python scripts/margin_audit.py analyse DIR --primary-deck l_corridor_gate
    uv run python scripts/margin_audit.py metrics DIR/l_corridor_gate/seed1/off

``run`` refuses a tree with uncommitted changes under ``pyfds_evac``,
``run.py`` or ``assets`` unless ``--allow-dirty`` is given, and it skips a
run whose ``metrics.json`` exists, so seeds can be added across sessions.
Each run is its own ``run.py`` process: JuPedSim numbers agents
process-wide.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = Path(
    "/Users/chraibi/sciebo - ped23 (ped23.pbox@fz-juelich.de)"
    "@fz-juelich.sciebo.de/fds-evac-data"
)
AUDIT_DIR = "audit_187"
ARMS = ("base", "off")
CODE_PATHS = ("pyfds_evac", "run.py", "assets")
ALPHA = 0.05
MIN_SEEDS = 6
EXACT_MAX_N = 20
MC_DRAWS = 100_000
# JuPedSim stores hash(wkt) of the geometry in the trajectory, Python's
# per-process salted str hash, so two runs of one code differ there and
# nowhere else. The runs fix the seed so the files can be byte-identical;
# the clear-air gate skips the columns so it does not depend on that.
GEOMETRY_HASH_COLUMNS = {"geometry": "hash", "frame_data": "geometry_hash"}
# Switch reasons always reported, even when a run has none of them.
REPORTED_REASONS = ("fallback", "better_path", "fed_reroute", "smoke_reroute")
# The window of returns reported (returns_within_window): 10 s, the default
# of the return lockout removed in #187 A1.
RETURN_WINDOW_S = 10.0


@dataclass(frozen=True)
class Margin:
    """A routing-block margin: its off value and predeclared primary metric."""

    off: float
    primary: str | None


# Off values and primary metrics from the stage-2 plan (§3.2). A1,
# fallback_return_lockout_s, was audited at c2c2081f and removed (#187).
# A2's "exposure
# co-primary" is covered by the secondary rule: fed_p95 and fed_ge_1 are in
# SECONDARY, so a distinct rise in exposure blocks "remove". A margin
# without a primary metric is not in the audit order; ``analyse`` then
# needs ``--metric``.
MARGINS: dict[str, Margin] = {
    "fed_return_margin": Margin(1.0, "switches_per_agent:fed_reroute"),
    "path_switch_anchor": Margin(1.0, "switches_per_agent:better_path"),
    "fallback_switch_margin": Margin(0.0, "switches_per_agent:fallback"),
    "tau_return_margin": Margin(1.0, "returns"),
    "tau_deadband": Margin(0.0, "returns"),
    "exit_switch_anchor": Margin(1.0, None),
    "current_exit_discount": Margin(1.0, None),
    "clean_exit_margin": Margin(1.0, None),
}


@dataclass(frozen=True)
class AuditDeck:
    """A deck and the seeds the plan assigns to it.

    Paths are relative to the data root, or to the repository when
    *in_repo* is set. A deck without *fds_dir* runs in clear air.
    """

    config: str
    geometry: str
    fds_dir: str | None
    seeds: tuple[int, ...]
    in_repo: bool = False
    extra_args: tuple[str, ...] = ()


# The golden decks hold the last FDS frame past the FDS end, as
# scripts/golden_rerouting.py runs them; the how-to decks run as
# scripts/docs/fire_blind_vs_coupled.py runs arm R (--disable-tenability)
# and R-det (tenability on).
_HOLD = ("--allow-fds-horizon-hold",)
_FAMILIARITY = ("--enable-rerouting", "--reroute-interval", "1")
DECKS: dict[str, AuditDeck] = {
    "l_corridor_gate": AuditDeck(
        "l_corridor/evac/deck_gate/config.json",
        "l_corridor/evac/deck_gate/geometry.wkt",
        "l_corridor/fire_1MW_west",
        tuple(range(1, 21)),
        extra_args=_HOLD,
    ),
    "l_corridor_gate_control": AuditDeck(
        "l_corridor/evac/deck_gate/config.json",
        "l_corridor/evac/deck_gate/geometry.wkt",
        "l_corridor/fire_1MW",
        tuple(range(1, 21)),
        extra_args=_HOLD,
    ),
    "l_corridor_additive": AuditDeck(
        "l_corridor/evac/deck_additive/config.json",
        "l_corridor/evac/deck_additive/geometry.wkt",
        "l_corridor/fire_1MW_west",
        tuple(range(1, 11)),
        extra_args=_HOLD,
    ),
    "world100_stream_east": AuditDeck(
        "world100/evac_4exits/deck_config_stream_east.json",
        "world100/evac_4exits/deck_geometry.wkt",
        "world100/fire_4p5MW",
        tuple(range(100, 110)),
        extra_args=_HOLD,
    ),
    "world100_stream_oval": AuditDeck(
        "world100/evac_4exits/deck_config_stream_oval.json",
        "world100/evac_4exits/deck_geometry.wkt",
        "world100/fire_4p5MW",
        tuple(range(100, 110)),
        extra_args=_HOLD,
    ),
    "t_junction_pre0": AuditDeck(
        "assets/t_junction/config_initial_pre0.json",
        "assets/t_junction/geometry.wkt",
        "t_junction/fire_2MW_PVC",
        tuple(range(4, 24)),
        in_repo=True,
        extra_args=("--disable-tenability",),
    ),
    "t_junction_pre30": AuditDeck(
        "assets/t_junction/config_initial_pre30.json",
        "assets/t_junction/geometry.wkt",
        "t_junction/fire_2MW_PVC",
        tuple(range(4, 14)),
        in_repo=True,
        extra_args=("--disable-tenability",),
    ),
    "t_junction_pre60": AuditDeck(
        "assets/t_junction/config_initial_pre60.json",
        "assets/t_junction/geometry.wkt",
        "t_junction/fire_2MW_PVC",
        tuple(range(4, 14)),
        in_repo=True,
        extra_args=("--disable-tenability",),
    ),
    "t_junction_pre30_det": AuditDeck(
        "assets/t_junction/config_initial_pre30.json",
        "assets/t_junction/geometry.wkt",
        "t_junction/fire_2MW_PVC",
        tuple(range(4, 14)),
        in_repo=True,
    ),
    "familiarity_test_full": AuditDeck(
        "assets/familiarity_test_full/config.json",
        "assets/familiarity_test_full/geometry.wkt",
        None,
        tuple(range(420, 430)),
        in_repo=True,
        extra_args=_FAMILIARITY,
    ),
    "familiarity_test_discovery": AuditDeck(
        "assets/familiarity_test_discovery/config.json",
        "assets/familiarity_test_discovery/geometry.wkt",
        None,
        tuple(range(420, 430)),
        in_repo=True,
        extra_args=_FAMILIARITY,
    ),
}


# ── Running ───────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def _dirty_paths() -> list[str]:
    paths = (*CODE_PATHS, Path(__file__).relative_to(REPO).as_posix())
    return [p for p in paths if _git("status", "--porcelain", "--", p)]


def _versions() -> dict[str, str]:
    found = {"python": sys.version.split()[0]}
    for name in ("pyfds-evac", "jupedsim", "fdsreader", "fdsvismap", "numpy"):
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = "not installed"
    return found


def _base(deck: AuditDeck, root: Path) -> Path:
    return REPO if deck.in_repo else root


def _missing(deck: AuditDeck, root: Path) -> list[Path]:
    base = _base(deck, root)
    paths = [base / deck.config, base / deck.geometry]
    if deck.fds_dir is not None:
        paths.append(root / deck.fds_dir)
    return [p for p in paths if not p.exists()]


def override_routing(config: dict, key: str, value: float) -> dict:
    """A copy of scenario *config* with routing *key* set to *value*."""
    copy: dict = json.loads(json.dumps(config))
    routing = dict(copy.get("routing") or {})
    routing[key] = value
    copy["routing"] = routing
    return copy


def _stage_scenario(
    deck: AuditDeck, root: Path, into: Path, override: tuple[str, float] | None
) -> Path:
    """Copy config and geometry into *into*, the off arm with the key set."""
    into.mkdir(parents=True, exist_ok=True)
    base = _base(deck, root)
    config = json.loads((base / deck.config).read_text(encoding="utf-8"))
    if override is not None:
        config = override_routing(config, *override)
    (into / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy(base / deck.geometry, into / "geometry.wkt")
    return into


def run_command(
    deck: AuditDeck, root: Path, scenario: Path, seed: int, out: Path, costs: bool
) -> list[str]:
    argv = [
        sys.executable,
        str(REPO / "run.py"),
        "--scenario",
        str(scenario),
        "--seed",
        str(seed),
        "--output-sqlite",
        str(out / "trajectory.sqlite"),
        "--output-route-history",
        str(out / "route_history.csv"),
        "--output-exit-history",
        str(out / "exit_history.csv"),
    ]
    if deck.fds_dir is not None:
        argv += ["--fds-dir", str(root / deck.fds_dir)]
    if costs:
        argv += ["--output-route-cost-history", str(out / "route_cost_history.csv")]
    return argv + list(deck.extra_args)


def run_env() -> dict[str, str]:
    """The environment of a run: this one with the str hash seed fixed."""
    return {**os.environ, "PYTHONHASHSEED": "0"}


@dataclass(frozen=True)
class Job:
    deck: str
    seed: int
    arm: str

    @property
    def label(self) -> str:
        return f"{self.deck}/seed{self.seed}/{self.arm}"


def _run_job(
    job: Job, key: str, off: float, root: Path, out: Path, costs: bool
) -> dict:
    """Run one arm of one seed and write its metrics; returns the run record."""
    deck = DECKS[job.deck]
    folder = out / job.deck / f"seed{job.seed}" / job.arm
    folder.mkdir(parents=True, exist_ok=True)
    override = (key, off) if job.arm == "off" else None
    scenario = _stage_scenario(deck, root, folder / "scenario", override)
    started = time.perf_counter()
    with (folder / "run.log").open("w", encoding="utf-8") as log:
        code = subprocess.call(
            run_command(deck, root, scenario, job.seed, folder, costs),
            cwd=REPO,
            env=run_env(),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    wall = time.perf_counter() - started
    if code != 0:
        return {"run": job.label, "status": f"failed (exit {code})", "wall_s": wall}
    value = manifest_margin(_read_json(folder / "trajectory.manifest.json"), key)
    if job.arm == "off" and value != off:
        return {
            "run": job.label,
            "status": f"override not applied: manifest has {key}={value!r}",
            "wall_s": wall,
        }
    metrics = run_metrics(folder)
    metrics.update({"wall_s": wall, "margin_value": value})
    _write_json(folder / "metrics.json", metrics)
    return {"run": job.label, "status": "ok", "wall_s": wall, "margin_value": value}


def manifest_margin(manifest: dict, key: str) -> float | None:
    """The value of routing *key* the run used, from its run manifest.

    Read from what ``run_scenario`` received (``configuration.run.rerouting``):
    the cost config, else the reroute config, where ``exit_switch_anchor``
    may also live. None when the run reports no value for *key*.
    """
    try:
        rerouting = manifest["configuration"]["run"]["rerouting"]
    except KeyError as error:
        raise ValueError(f"run manifest has no configuration.run.rerouting: {error}")
    if rerouting is None:
        raise ValueError("run manifest reports no rerouting configuration")
    cost = rerouting.get("cost_config") or {}
    value = cost.get(key)
    if value is None:
        value = rerouting.get(key)
    return None if value is None else float(value)


def _jobs(names: list[str], seeds: list[int] | None) -> list[Job]:
    jobs = []
    for name in names:
        for seed in seeds if seeds is not None else DECKS[name].seeds:
            jobs += [Job(name, seed, arm) for arm in ARMS]
    return jobs


def _run_all(args: argparse.Namespace) -> int:
    key = args.margin
    off = args.off if args.off is not None else MARGINS[key].off
    root = Path(args.data_root)
    sha = _git("rev-parse", "--short=8", "HEAD")
    out = Path(args.out) if args.out else root / AUDIT_DIR / f"{key}_{sha}"
    dirty = _dirty_paths()
    if dirty and not args.allow_dirty:
        print(f"refusing to run with uncommitted changes in {', '.join(dirty)}")
        return 2
    for name in args.decks:
        missing = _missing(DECKS[name], root)
        if missing:
            print(f"{name}: missing {', '.join(map(str, missing))}")
            return 2
    jobs = _jobs(args.decks, args.seeds)
    pending = [j for j in jobs if not (out / j.label / "metrics.json").is_file()]
    print(f"{key} -> {off}: {len(jobs)} runs, {len(pending)} to do, into {out}")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "margin": key,
        "off_value": off,
        "commit": _git("rev-parse", "HEAD"),
        "dirty": dirty,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "versions": _versions(),
        "data_root": str(root),
        "decks": {n: vars(DECKS[n]) for n in args.decks},
        "seeds": {n: sorted({j.seed for j in jobs if j.deck == n}) for n in args.decks},
        "runs": _read_json(out / "manifest.json").get("runs", {})
        if (out / "manifest.json").is_file()
        else {},
    }
    failed = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [
            pool.submit(_run_job, j, key, off, root, out, args.cost_history)
            for j in pending
        ]
        for job, future in zip(pending, futures):
            try:
                record = future.result()
            except Exception as error:  # noqa: BLE001 - recorded, not hidden
                record = {"run": job.label, "status": f"error: {error}", "wall_s": 0.0}
            manifest["runs"][record["run"]] = record
            failed += record["status"] != "ok"
            print(f"  {record['run']:40s} {record['status']} {record['wall_s']:.1f} s")
            _write_json(out / "manifest.json", manifest)
    _write_json(out / "manifest.json", manifest)
    return 1 if failed else 0


# ── Per-run metrics ───────────────────────────────────────────────────


def _read_json(path: Path) -> dict:
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def switch_rows(rows: list[dict]) -> list[dict]:
    """Rows of a route history that are switches: they name an old exit.

    This agrees with ``route_graph.route_switches`` on every run checked;
    the two differ by definition only on ``explore``/``wander`` rows, which
    carry no old exit but can change the target the core counts.
    """
    return [r for r in rows if r.get("old_exit")]


def exit_switches(rows: list[dict]) -> list[dict]:
    """Switches between two exits: old and new exit set and different."""
    return [
        r for r in switch_rows(rows) if r["new_exit"] and r["new_exit"] != r["old_exit"]
    ]


def returns(rows: list[dict]) -> list[dict]:
    """Returns in the #124 sense, each with the time since it left that exit.

    A return is an exit switch whose new exit is the old exit of an earlier
    exit switch by the same agent. ``since_s`` is measured from the latest
    such earlier switch.
    """
    left_at: dict[tuple[str, str], float] = {}
    found = []
    for row in exit_switches(rows):
        agent, time_s = row["agent_id"], float(row["time_s"])
        back = (agent, row["new_exit"])
        if back in left_at:
            found.append({**row, "since_s": time_s - left_at[back]})
        left_at[(agent, row["old_exit"])] = time_s
    return found


def _route_metrics(rows: list[dict], n_agents: int) -> dict:
    switches = switch_rows(rows)
    by_reason: dict[str, int] = {r: 0 for r in REPORTED_REASONS}
    for row in switches:
        by_reason[row["reason"]] = by_reason.get(row["reason"], 0) + 1
    came_back = returns(rows)
    per_agent = max(n_agents, 1)
    metrics = {
        "switches": len(switches),
        "switches_per_agent": len(switches) / per_agent,
        "exit_switches": len(exit_switches(rows)),
        "returns": len(came_back),
        "returns_agents": len({r["agent_id"] for r in came_back}),
        "returns_within_window": sum(
            r["since_s"] <= RETURN_WINDOW_S for r in came_back
        ),
        "returns_since_s_median": _median([r["since_s"] for r in came_back]),
    }
    for reason, count in sorted(by_reason.items()):
        metrics[f"switches:{reason}"] = count
        metrics[f"switches_per_agent:{reason}"] = count / per_agent
    return metrics


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def _exit_shares(rows: list[dict]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["exit_id"]] = counts.get(row["exit_id"], 0) + 1
    total = max(sum(counts.values()), 1)
    return {f"exit_share:{e}": n / total for e, n in sorted(counts.items())}


def _egress_metrics(sqlite_file: Path, agents_remaining: int | None) -> dict:
    """Egress times from the trajectory and FED at egress from agent_scalars."""
    with sqlite3.connect(sqlite_file) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()[0]
        )
        last_frame = con.execute("SELECT MAX(frame) FROM trajectory_data").fetchone()[0]
        last = con.execute(
            "SELECT id, MAX(frame) FROM trajectory_data GROUP BY id"
        ).fetchall()
        has_fed = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_scalars'"
        ).fetchone()
        fed = (
            [
                row[0]
                for row in con.execute("SELECT MAX(fed) FROM agent_scalars GROUP BY id")
            ]
            if has_fed
            else []
        )
    times = np.array([frame / fps for _, frame in last], dtype=float)
    if agents_remaining is None:
        agents_remaining = int(sum(frame >= last_frame for _, frame in last))
    metrics = {
        "n_agents": len(last),
        "rset_last": float(times.max()) if len(times) else None,
        "rset_p95": float(np.percentile(times, 95)) if len(times) else None,
        "censored": agents_remaining,
    }
    doses = np.array([d for d in fed if d is not None], dtype=float)
    metrics.update(
        {
            "fed_median": float(np.median(doses)) if len(doses) else None,
            "fed_p95": float(np.percentile(doses, 95)) if len(doses) else None,
            "fed_max": float(doses.max()) if len(doses) else None,
            "fed_ge_0_3": int((doses >= 0.3).sum()) if len(doses) else None,
            "fed_ge_1": int((doses >= 1.0).sum()) if len(doses) else None,
        }
    )
    return metrics


def run_metrics(folder: Path) -> dict:
    """All per-run metrics of the run in *folder*."""
    manifest_file = folder / "trajectory.manifest.json"
    outcome = (
        _read_json(manifest_file).get("outcome", {}) if manifest_file.is_file() else {}
    )
    metrics = _egress_metrics(
        folder / "trajectory.sqlite", outcome.get("agents_remaining")
    )
    metrics.update(
        _route_metrics(_read_csv(folder / "route_history.csv"), metrics["n_agents"])
    )
    metrics.update(_exit_shares(_read_csv(folder / "exit_history.csv")))
    return metrics


# ── Clear-air identity ────────────────────────────────────────────────


def _tables(path: Path) -> dict[str, tuple[list[str], list[tuple]]]:
    """Every table of the trajectory *path*, without the geometry hash."""
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as con:
        names = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        tables = {}
        for name in names:
            skip = GEOMETRY_HASH_COLUMNS.get(name)
            columns = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
            kept = [c for c in columns if c != skip]
            quoted = ", ".join(f'"{c}"' for c in kept)
            tables[name] = (
                kept,
                con.execute(f"SELECT {quoted} FROM {name}").fetchall(),
            )
    return tables


def run_differences(a: Path, b: Path) -> list[str]:
    """What differs between the runs *a* and *b*; empty when nothing does.

    The histories must be byte-identical; the trajectory is compared table
    by table, every column but the geometry hash (GEOMETRY_HASH_COLUMNS).
    """
    report = [
        name
        for name in ("route_history.csv", "exit_history.csv")
        if (a / name).read_bytes() != (b / name).read_bytes()
    ]
    tables_a, tables_b = (
        _tables(a / "trajectory.sqlite"),
        _tables(b / "trajectory.sqlite"),
    )
    report += [
        f"trajectory.sqlite:{name}"
        for name in sorted(set(tables_a) | set(tables_b))
        if tables_a.get(name) != tables_b.get(name)
    ]
    return report


def clear_air_identity(folder: Path, deck: str) -> dict | None:
    """Per seed, what differs between the arms of a clear-air *deck* (C10).

    A margin must not change a run without smoke; None for a deck with an
    FDS run or one the harness does not know.
    """
    known = DECKS.get(deck)
    if known is None or known.fds_dir is not None:
        return None
    pairs = _pairs(folder, deck)
    differing = {}
    for seed in pairs:
        arms = [folder / deck / f"seed{seed}" / arm for arm in ARMS]
        found = run_differences(*arms)
        if found:
            differing[seed] = found
    return {"seeds": len(pairs), "differing": differing}


# ── Analysis ──────────────────────────────────────────────────────────


def paired_permutation_p(
    d, *, exact_max_n: int = EXACT_MAX_N, draws: int = MC_DRAWS, mc_seed: int = 0
) -> tuple[float, str]:
    """Two-sided p of the paired permutation test on the mean of *d*.

    Under the null each difference is as likely with either sign; the
    statistic is |sum d|. Exact enumeration of the 2^n sign flips up to
    *exact_max_n*, else *draws* random flips from a fixed seed, with the
    observed assignment counted in. Zero differences stay in: they can
    only make the test more conservative.
    """
    diffs = np.asarray(d, dtype=float)
    n = len(diffs)
    if n == 0:
        raise ValueError("paired permutation test: no differences")
    observed = abs(diffs.sum())
    tolerance = 1e-12 * max(1.0, np.abs(diffs).sum())
    if n <= exact_max_n:
        count = 0
        for chunk in np.array_split(np.arange(2**n), max(1, 2**n >> 16)):
            signs = ((chunk[:, None] >> np.arange(n)) & 1) * 2 - 1
            count += int((np.abs(signs @ diffs) >= observed - tolerance).sum())
        return count / 2**n, "exact"
    rng = np.random.default_rng(mc_seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(draws, n))
    count = int((np.abs(signs @ diffs) >= observed - tolerance).sum())
    return (count + 1) / (draws + 1), "monte-carlo"


def smallest_p(n: int) -> float:
    """The smallest p the exact test can give with *n* seeds."""
    return float(2 / 2**n)


@dataclass(frozen=True)
class MetricRule:
    """How a metric is judged: its floor on |mean d| and which sign is worse."""

    floor: Callable[[float, float], float]
    worse: int  # +1: an increase is worse; 0: no direction (reported only)


def _floor_rule(metric: str) -> MetricRule | None:
    """The plan's floor for *metric*, or None when it is reported only."""
    if metric in ("returns", "returns_within_window"):
        return MetricRule(lambda base, agents: max(0.02 * agents, 0.25 * base), 1)
    if metric.startswith("switches_per_agent"):
        return MetricRule(lambda base, agents: max(0.05, 0.25 * base), 1)
    if metric.startswith("exit_share:"):
        return MetricRule(lambda base, agents: 0.05, 0)
    if metric == "fed_p95":
        return MetricRule(lambda base, agents: 0.05, 1)
    if metric == "fed_ge_1":
        # A change in at least two seeds; the floor is on the seed count.
        return MetricRule(lambda base, agents: 2.0, 1)
    if metric in ("rset_last", "rset_p95"):
        return MetricRule(lambda base, agents: max(0.02 * base, 3.0), 1)
    return None


SECONDARY = (
    "returns",
    "switches_per_agent",
    "fed_p95",
    "fed_ge_1",
    "rset_last",
    "rset_p95",
)


def _pairs(folder: Path, deck: str) -> dict[int, dict[str, dict]]:
    """Seeds of *deck* with metrics in both arms."""
    pairs: dict[int, dict[str, dict]] = {}
    for seed_dir in sorted((folder / deck).glob("seed*")):
        files = {arm: seed_dir / arm / "metrics.json" for arm in ARMS}
        if all(f.is_file() for f in files.values()):
            pairs[int(seed_dir.name[4:])] = {a: _read_json(f) for a, f in files.items()}
    return pairs


def judge(metric: str, pairs: dict[int, dict[str, dict]], mc_seed: int = 0) -> dict:
    """Effect, p and floor of *metric* over the paired seeds."""
    seeds = sorted(s for s in pairs if _present(pairs[s], metric))
    if not seeds:
        return {"metric": metric, "n": 0, "note": "metric absent"}
    base = np.array([_value(pairs[s]["base"], metric) for s in seeds], dtype=float)
    off = np.array([_value(pairs[s]["off"], metric) for s in seeds], dtype=float)
    d = off - base
    p, method = paired_permutation_p(d, mc_seed=mc_seed)
    agents = float(np.mean([pairs[s]["base"]["n_agents"] for s in seeds]))
    rule = _floor_rule(metric)
    result = {
        "metric": metric,
        "n": len(seeds),
        "seeds": seeds,
        "base_mean": float(base.mean()),
        "off_mean": float(off.mean()),
        "effect": float(d.mean()),
        "d": d.tolist(),
        "changed_seeds": int((d != 0).sum()),
        "p": p,
        "method": method,
        "smallest_p": smallest_p(len(seeds)),
    }
    if rule is None:
        return {**result, "floor": None, "distinct": None, "worse": None}
    floor = rule.floor(float(base.mean()), agents)
    size = result["changed_seeds"] if metric == "fed_ge_1" else abs(d.mean())
    distinct = p < ALPHA and size >= floor and len(seeds) >= MIN_SEEDS
    worse = None if rule.worse == 0 else bool(d.mean() * rule.worse > 0)
    return {**result, "floor": floor, "distinct": bool(distinct), "worse": worse}


def _value(metrics: dict, metric: str) -> float | None:
    """A run's value of *metric*; an exit nobody used has share 0."""
    value = metrics.get(metric)
    if value is None and metric.startswith("exit_share:"):
        return 0.0
    return value


def _present(pair: dict[str, dict], metric: str) -> bool:
    return all(_value(pair[arm], metric) is not None for arm in ARMS)


def outcome(primary: dict, secondary: list[dict]) -> str:
    """The stage-2 outcome rule on the primary deck."""
    if primary.get("n", 0) < MIN_SEEDS:
        return f"undecided: {primary.get('n', 0)} seeds, fewer than {MIN_SEEDS}"
    if not primary["distinct"]:
        return "remove: no distinct effect"
    if primary["worse"]:
        return "keep: distinct effect, removal is worse"
    harmed = [s["metric"] for s in secondary if s.get("distinct") and s.get("worse")]
    if harmed:
        return f"maintainer: removal better on the primary metric, worse on {', '.join(harmed)}"
    return "remove: distinct effect, removal is better, no secondary metric worse"


def _analyse(args: argparse.Namespace) -> int:
    folder = Path(args.run)
    manifest = _read_json(folder / "manifest.json")
    key = manifest["margin"]
    metric = args.metric or MARGINS.get(key, Margin(0.0, None)).primary
    if metric is None:
        print(f"{key} has no predeclared primary metric; pass --metric")
        return 2
    decks = sorted(p.name for p in folder.iterdir() if p.is_dir())
    if args.primary_deck not in decks:
        print(f"primary deck {args.primary_deck} has no runs in {folder}")
        return 2
    report = {
        "margin": key,
        "off_value": manifest["off_value"],
        "commit": manifest["commit"],
        "dirty": manifest["dirty"],
        "primary_deck": args.primary_deck,
        "primary_metric": metric,
        "alpha": ALPHA,
        "min_seeds": MIN_SEEDS,
        "decks": {},
    }
    for deck in decks:
        pairs = _pairs(folder, deck)
        metrics = _metric_names(pairs)
        report["decks"][deck] = {
            "n": len(pairs),
            "results": [judge(m, pairs, args.mc_seed) for m in metrics],
            "clear_air": clear_air_identity(folder, deck),
        }
    primary = _find(report["decks"][args.primary_deck]["results"], metric)
    secondary = [
        _find(report["decks"][args.primary_deck]["results"], m)
        for m in SECONDARY
        if m != metric
    ]
    report["primary"] = primary
    report["outcome"] = outcome(primary, [s for s in secondary if s])
    text = _report_markdown(report)
    print(text)
    _write_json(folder / "report.json", report)
    (folder / "report.md").write_text(text, encoding="utf-8")
    return 0


def _metric_names(pairs: dict[int, dict[str, dict]]) -> list[str]:
    names: set[str] = set()
    for pair in pairs.values():
        names.update(k for k in pair["base"] if k not in ("wall_s", "margin_value"))
    return sorted(names)


def _find(results: list[dict], metric: str) -> dict:
    return next(
        (r for r in results if r["metric"] == metric), {"metric": metric, "n": 0}
    )


def _report_markdown(report: dict) -> str:
    primary = report["primary"]
    lines = [
        f"# Margin audit: {report['margin']} -> {report['off_value']}",
        "",
        f"Commit {report['commit']}" + (" (dirty)" if report["dirty"] else ""),
        f"Primary deck: {report['primary_deck']}; primary metric: "
        f"{report['primary_metric']}; alpha = {report['alpha']}, "
        f"at least {report['min_seeds']} seeds.",
        "",
        f"**Outcome: {report['outcome']}**",
        "",
    ]
    if primary.get("n"):
        lines += [
            f"Primary: n = {primary['n']}, effect (off - base) = {primary['effect']:.4g}, "
            f"floor = {primary['floor']}, p = {primary['p']:.4g} ({primary['method']}, "
            f"smallest possible {primary['smallest_p']:.2g}), "
            f"distinct = {primary['distinct']}.",
            "",
        ]
    for deck, data in report["decks"].items():
        lines += [f"## {deck} (n = {data['n']})", ""]
        if data.get("clear_air"):
            lines += [_clear_air_line(data["clear_air"]), ""]
        lines += [
            "| metric | n | base | off | effect | p | floor | distinct |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in data["results"]:
            if not r.get("n"):
                continue
            lines.append(
                f"| {r['metric']} | {r['n']} | {r['base_mean']:.4g} | {r['off_mean']:.4g} "
                f"| {r['effect']:.4g} | {r['p']:.3g} | {_fmt(r['floor'])} "
                f"| {_fmt(r['distinct'])} |"
            )
        lines.append("")
    return "\n".join(lines)


def _clear_air_line(identity: dict) -> str:
    """One line on the clear-air gate: identical, or which seeds differ."""
    differing = identity["differing"]
    if not differing:
        return f"Clear air: base and off identical on {identity['seeds']} seeds."
    where = "; ".join(f"seed {s}: {', '.join(d)}" for s, d in differing.items())
    return (
        f"**Clear air: base and off differ on {len(differing)} of "
        f"{identity['seeds']} seeds** ({where})."
    )


def _fmt(value) -> str:
    if value is None:
        return "-"
    return f"{value:.3g}" if isinstance(value, float) else str(value)


# ── Command line ──────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the paired base/off arms of one margin")
    run.add_argument("--margin", required=True, help="routing key to sweep")
    run.add_argument("--off", type=float, help="off value; default from the plan")
    run.add_argument("--decks", nargs="+", required=True, choices=sorted(DECKS))
    run.add_argument("--seeds", nargs="+", type=int, help="override every deck's seeds")
    run.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    run.add_argument("--out", help=f"default <data-root>/{AUDIT_DIR}/<margin>_<sha>")
    run.add_argument("--jobs", type=int, default=1, help="run.py processes at once")
    run.add_argument("--cost-history", action="store_true", help="also write it")
    run.add_argument("--allow-dirty", action="store_true")
    run.set_defaults(func=_run_all)
    analyse = sub.add_parser("analyse", help="decide a margin from a run folder")
    analyse.add_argument("run")
    analyse.add_argument("--primary-deck", required=True)
    analyse.add_argument("--metric", help="primary metric; default from the plan")
    analyse.add_argument("--mc-seed", type=int, default=0)
    analyse.set_defaults(func=_analyse)
    metrics = sub.add_parser("metrics", help="print the metrics of one run folder")
    metrics.add_argument("folder")
    metrics.set_defaults(
        func=lambda a: print(json.dumps(run_metrics(Path(a.folder)), indent=1))
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "run" and args.margin not in MARGINS and args.off is None:
        print(f"{args.margin} is not a known margin; pass --off VALUE")
        return 2
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
