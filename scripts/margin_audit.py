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
``agent_scalars``, egress times and the mean walking time per agent from
the trajectory.

``analyse`` takes the paired per-seed differences d = off - base on the
predeclared primary deck and primary metric, runs a two-sided paired
permutation test on the mean of d (sign flips, exact up to 20 seeds, else
Monte-Carlo with a fixed seed), compares |mean d| with the metric's floor
and applies the stage-2 outcome rule. The other decks and metrics are
descriptive. For a deck run in clear air the report also says whether base
and off are identical: the histories byte for byte, the trajectory table by
table without JuPedSim's per-process geometry hash (C10).

Usage::

    uv run python scripts/margin_audit.py run --margin fallback_switch_margin \\
        --decks l_corridor_gate t_junction_pre30 [--seeds 1 2 ...] [--jobs 4]
    uv run python scripts/margin_audit.py analyse DIR --primary-deck l_corridor_gate
    uv run python scripts/margin_audit.py metrics DIR/l_corridor_gate/seed1/off

``run`` refuses a tree with uncommitted changes under ``pyfds_evac``,
``run.py`` or ``assets`` unless ``--allow-dirty`` is given, and it skips a
run whose ``metrics.json`` exists, so seeds can be added across sessions.
Each run is its own ``run.py`` process: JuPedSim numbers agents
process-wide. A run that ends at the time limit with agents left (``run.py``
exit 2) counts and its ``censored`` metric holds how many; any other non-zero
exit is a failed run without metrics. With two commit arms ``run`` still
refuses uncommitted changes under ``assets`` (the decks are read from this
checkout) and in this script.

Arms
----

An arm is the code a run uses and the config overrides it runs with. The
first arm is ``base``, the second ``off`` (also in the code audit, where it
is the head): the differences are d = off - base. ``--margin`` is the
config sweep above: both arms run this tree, ``off`` with the key set to
its off value. The arm options give the general form and can be combined
with it:

``--base-commit REF`` / ``--head-commit REF``
    Run that arm's code from a detached worktree of REF (a temporary
    directory removed afterwards), with the locked environment
    (``uv sync --frozen --all-groups --all-extras``) built in it and its
    interpreter used. ``run.py`` and ``pyfds_evac`` are imported from the
    worktree; each arm's import paths are checked and kept in the manifest.
    Without a REF the arm runs this working tree, which must be clean
    unless ``--allow-dirty`` is given. The decks (config, geometry, FDS
    output) are the same for both arms: the config and geometry come from
    this checkout, not from REF, so a model-change PR compares like with
    like. Two arms at one commit share a worktree.
``--base-set PATH=VALUE`` / ``--head-set PATH=VALUE``
    Override one config value of that arm, repeatable. PATH is a dotted path
    into the scenario config, or a bare routing key
    (``impassable_extinction_threshold`` is ``routing.impassable_extinction_threshold``).
    VALUE is JSON, or ``inf``. A path other than ``routing.*`` must exist in
    the config. A numeric routing override is checked against the value the
    run manifest reports.

A deck may carry its own overrides for both arms (``AuditDeck.overrides``),
as the ``a047_pvc_*`` decks do for the 480 s cap of their FDS output.

Examples, the code arm of a model-change PR and the #835 experiment (the
additive must-flee threshold 3.0 against off, ten paired seeds)::

    uv run python scripts/margin_audit.py run --base-commit origin/main \\
        --head-commit my-branch --decks l_corridor_gate --seeds 1 2 3 4 5 6 \\
        --jobs 4 --out DIR
    uv run python scripts/margin_audit.py run --decks a047_pvc_h40 \\
        --base-set routing.impassable_extinction_threshold=3.0 \\
        --head-set routing.impassable_extinction_threshold=inf --jobs 4 --out DIR
    uv run python scripts/margin_audit.py analyse DIR \\
        --primary-deck a047_pvc_h40 --metric rset_p95

The decision rule is the same for every audit: two-sided paired permutation
p < 0.05, |mean d| at least the metric's floor and at least 6 seeds
(``outcome``). ``analyse`` needs ``--metric`` for an audit without a
margin. The outcome text speaks of "remove": for a code audit read it as
"the change has no distinct effect on the primary metric". A rerun with the
same ``--out`` must use the same arms; it refuses otherwise. In a code
audit the report words the outcome neutrally ("no distinct effect on the
primary metric", or the direction of a distinct one) instead of "remove".

Override keys are checked before the first run starts: a ``routing.*`` key
must be one the loader reads (a ``RouteCostConfig`` field or
``fed_rate_memo``), and every other path must exist in each deck's config.

In ``manifest.json``, ``commit`` and ``dirty`` describe the checkout the
script was called from; ``arms`` (commit and overrides per side) and
``imports`` (where each arm imported the code from) identify what ran. A
code audit has ``margin`` "arms" and no ``off_value``.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
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
CODE_PATHS = ("pyfds_evac", "run.py", "assets", "tests")
ALPHA = 0.05
# run.py's exit code for a run that ends with agents left (cli.EXIT_INCOMPLETE).
INCOMPLETE_EXIT = 2
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


# Off values and primary metrics from the stage-2 plan (§3.2).
# fallback_return_lockout_s (A1, audited at c2c2081f), fed_return_margin
# (A2, audited on the targeted FED decks), path_switch_anchor (A3) and
# tau_return_margin (A5) were removed (#187). A margin
# without a primary metric is not in the audit order; ``analyse`` then
# needs ``--metric``.
MARGINS: dict[str, Margin] = {
    "fallback_switch_margin": Margin(0.0, "switches_per_agent:fallback"),
    "tau_deadband": Margin(0.0, "returns"),
    "exit_switch_anchor": Margin(1.0, None),
    "current_exit_discount": Margin(1.0, None),
    "clean_exit_margin": Margin(1.0, None),
}


@dataclass(frozen=True)
class AuditDeck:
    """A deck and the seeds the plan assigns to it.

    Paths are relative to the data root, or to the repository when
    *in_repo* is set. A deck without *fds_dir* runs in clear air, unless a
    *runner* stands in for ``run.py``: a script under the repository that
    takes run.py's options and writes its outputs, with its own synthetic
    fire (``tests/test_fed_margin_deck.py``). *overrides* are config
    overrides (dotted path, value) both arms get, before the arm's own.
    """

    config: str
    geometry: str
    fds_dir: str | None
    seeds: tuple[int, ...]
    in_repo: bool = False
    extra_args: tuple[str, ...] = ()
    runner: tuple[str, ...] = ()
    overrides: tuple[tuple[str, object], ...] = ()


# The golden decks hold the last FDS frame past the FDS end, as
# scripts/golden_rerouting.py runs them; the how-to decks run as
# scripts/docs/fire_blind_vs_coupled.py runs arm R (--disable-tenability)
# and R-det (tenability on).
_HOLD = ("--allow-fds-horizon-hold",)
_FAMILIARITY = ("--enable-rerouting", "--reroute-interval", "1")
_FED_DECK = "tests/test_fed_margin_deck.py"
_SIM_TIME_PATH = "config.simulation_settings.simulationParams.max_simulation_time"


def _fed_deck(name: str) -> AuditDeck:
    """A targeted FED deck of tests/test_fed_margin_deck.py (#187 A2)."""
    return AuditDeck(
        "assets/t_junction/config_full.json",
        "assets/t_junction/geometry.wkt",
        None,
        tuple(range(11, 21)),
        in_repo=True,
        runner=(_FED_DECK, "--fed-deck", name),
    )


def _schroeder_deck(name: str) -> AuditDeck:
    """A Schroeder 2015 route deck on its #796 rerun FDS output (#835).

    The FDS run ends at 480 s; the config's 400 s limit is raised to match.
    """
    return AuditDeck(
        "assets/schroeder2015_route/evac/config_additive.json",
        "assets/schroeder2015_route/evac/geometry.wkt",
        f"schroeder2015-route/rerun_796/{name}",
        tuple(range(1, 11)),
        in_repo=True,
        overrides=((_SIM_TIME_PATH, 480),),
    )


def _allocation_deck(name: str) -> AuditDeck:
    """A clear-air deck of the allocation audit (#854), ten seeds."""
    return AuditDeck(
        f"assets/{name}/config.json",
        f"assets/{name}/geometry.wkt",
        None,
        tuple(range(1, 11)),
        in_repo=True,
        extra_args=_FAMILIARITY,
    )


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
    "a047_pvc_h40": _schroeder_deck("a047_pvc_h40"),
    "a047_pvc_h35": _schroeder_deck("a047_pvc_h35"),
    "fed_near1_hold_gate": _fed_deck("near1_hold_gate"),
    "fed_near1_hold_additive": _fed_deck("near1_hold_additive"),
    "fed_near1_rise_gate": _fed_deck("near1_rise_gate"),
    "fed_near1_rise_additive": _fed_deck("near1_rise_additive"),
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
    # Single-exit journeys in clear air (#854). The ISO 20414 Test 8 deck
    # (tests/test_iso_test_8_route_allocation.py) and a hall with two spawn
    # areas, one whose allocated exit costs 1/0.85 of the other and one 1/0.95
    # (tests/test_allocation_preference.py); each with a twin whose journeys
    # are "allocation": "hard", which must not move.
    "iso_test_8_route_allocation": _allocation_deck("iso_test_8_route_allocation"),
    "iso_test_8_route_allocation_hard": _allocation_deck(
        "iso_test_8_route_allocation_hard"
    ),
    "single_exit_clear_air": _allocation_deck("single_exit_clear_air"),
    "single_exit_clear_air_hard": _allocation_deck("single_exit_clear_air_hard"),
}


# ── Running ───────────────────────────────────────────────────────────


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def _dirty_paths(code_arms: bool = True) -> list[str]:
    """Uncommitted paths that a run would use.

    With *code_arms* false every arm runs a commit's code, so only what is
    still read from this checkout counts: the decks' ``assets`` and this
    script.
    """
    paths = CODE_PATHS if code_arms else ("assets",)
    paths = (*paths, Path(__file__).relative_to(REPO).as_posix())
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


Overrides = tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class Arm:
    """One side of a pair: the code it runs and the config overrides it gets.

    *commit* is a full sha, or None for this working tree.
    """

    commit: str | None = None
    overrides: Overrides = ()

    def describe(self) -> dict:
        return {"commit": self.commit, "overrides": dict(self.overrides)}


@dataclass(frozen=True)
class CodeTree:
    """The checkout an arm runs from and the interpreter of its environment."""

    root: Path
    python: str


def parse_override(text: str) -> tuple[str, object]:
    """``PATH=VALUE`` as (dotted path, value); VALUE is JSON or ``inf``.

    A path without a dot is a routing key.
    """
    path, sep, raw = text.partition("=")
    if not sep or not path:
        raise ValueError(f"override {text!r}: expected PATH=VALUE")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        try:
            value = float(raw)
        except ValueError:
            raise ValueError(f"override {text!r}: {raw!r} is not JSON or inf") from None
    return (path if "." in path else f"routing.{path}"), value


def set_config_path(config: dict, path: str, value: object) -> dict:
    """A copy of scenario *config* with the dotted *path* set to *value*.

    ``routing`` and the keys under it may be new; every other part of the
    path must exist, so a misspelt path fails instead of being ignored.
    """
    copy: dict = json.loads(json.dumps(config))
    *parents, leaf = path.split(".")
    node = copy
    for depth, key in enumerate(parents):
        child = node.get(key)
        if child is None and parents[0] == "routing":
            child = node[key] = {}
        if not isinstance(child, dict):
            where = ".".join(parents[: depth + 1])
            raise ValueError(f"config override {path}: no object at {where!r}")
        node = child
    if leaf not in node and parents[0] != "routing":
        raise ValueError(f"config override {path}: no key {leaf!r} in the config")
    node[leaf] = value
    return copy


def routing_keys() -> frozenset[str]:
    """The ``routing`` keys the scenario loader reads.

    The fields of ``RouteCostConfig`` (``from_routing_params`` reads one key
    per field, but ``fallback_rule``, a code-level field) and
    ``fed_rate_memo``. The loader ignores any other key, so an override of
    one would run unchanged.
    """
    import dataclasses

    from pyfds_evac.core.route_graph import RouteCostConfig

    fields = {f.name for f in dataclasses.fields(RouteCostConfig)}
    return frozenset(fields - {"fallback_rule"} | {"fed_rate_memo"})


def check_override_keys(overrides: Overrides) -> None:
    """Raise ValueError for a ``routing.*`` override the loader does not read."""
    known = routing_keys()
    for path, _ in overrides:
        key = path.removeprefix("routing.")
        if path.startswith("routing.") and key not in known:
            raise ValueError(
                f"override {path}: not a routing key the loader reads "
                f"(known: {', '.join(sorted(known))})"
            )


def check_override_paths(decks: list[str], root: Path, arms: dict[str, "Arm"]) -> None:
    """Raise ValueError unless every arm's overrides apply to every deck's config.

    Stages nothing: the check runs before the first run starts.
    """
    for name in decks:
        deck = DECKS[name]
        config = json.loads((_base(deck, root) / deck.config).read_text("utf-8"))
        for arm in arms.values():
            for path, value in (*deck.overrides, *arm.overrides):
                config = set_config_path(config, path, value)


def _stage_scenario(
    deck: AuditDeck, root: Path, into: Path, overrides: Overrides
) -> Path:
    """Copy config and geometry into *into*, with the *overrides* applied."""
    into.mkdir(parents=True, exist_ok=True)
    base = _base(deck, root)
    config = json.loads((base / deck.config).read_text(encoding="utf-8"))
    for path, value in (*deck.overrides, *overrides):
        config = set_config_path(config, path, value)
    (into / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy(base / deck.geometry, into / "geometry.wkt")
    return into


def run_command(
    deck: AuditDeck,
    root: Path,
    scenario: Path,
    seed: int,
    out: Path,
    costs: bool,
    code: CodeTree | None = None,
) -> list[str]:
    code = code or CodeTree(REPO, sys.executable)
    runner = deck.runner or ("run.py",)
    argv = [
        code.python,
        str(code.root / runner[0]),
        *runner[1:],
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


def run_env(code: Path = REPO) -> dict[str, str]:
    """The environment of a run: the str hash seed fixed, *code* first.

    A runner under tests/ would otherwise import the installed pyfds_evac,
    which can be another checkout's (#721).
    """
    python_path = os.pathsep.join(
        p for p in (str(code), os.environ.get("PYTHONPATH", "")) if p
    )
    return {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": python_path}


@dataclass(frozen=True)
class Job:
    deck: str
    seed: int
    arm: str

    @property
    def label(self) -> str:
        return f"{self.deck}/seed{self.seed}/{self.arm}"


def _run_job(
    job: Job, arm: Arm, code: CodeTree, root: Path, out: Path, costs: bool
) -> dict:
    """Run one arm of one seed and write its metrics; returns the run record."""
    deck = DECKS[job.deck]
    folder = out / job.deck / f"seed{job.seed}" / job.arm
    folder.mkdir(parents=True, exist_ok=True)
    scenario = _stage_scenario(deck, root, folder / "scenario", arm.overrides)
    # A manifest left by an earlier try must not stand in for this run's.
    (folder / "trajectory.manifest.json").unlink(missing_ok=True)
    started = time.perf_counter()
    with (folder / "run.log").open("w", encoding="utf-8") as log:
        exit_code = subprocess.call(
            run_command(deck, root, scenario, job.seed, folder, costs, code),
            cwd=code.root,
            env=run_env(code.root),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    wall = time.perf_counter() - started
    manifest_file = folder / "trajectory.manifest.json"
    reported = _read_json(manifest_file) if manifest_file.is_file() else None
    usable, status = exit_status(exit_code, reported)
    if not usable:
        return {"run": job.label, "status": status, "wall_s": wall}
    assert reported is not None
    unapplied = unapplied_overrides(reported, arm.overrides)
    if unapplied:
        status = f"override not applied: {'; '.join(unapplied)}"
        return {"run": job.label, "status": status, "wall_s": wall}
    metrics = run_metrics(folder)
    metrics.update({"wall_s": wall})
    _write_json(folder / "metrics.json", metrics)
    return {"run": job.label, "status": status, "wall_s": wall}


def exit_status(exit_code: int, manifest: dict | None) -> tuple[bool, str]:
    """Whether a run's outputs are usable, and its status text.

    ``run.py`` exits 2 for a run that ends with agents left at the time
    limit (``EXIT_INCOMPLETE``), and its outputs are complete; argparse
    also exits 2, with none. So 2 counts only with a run manifest that
    reports agents remaining. ``censored`` in the metrics carries the count.
    """
    if exit_code == 0:
        return True, "ok"
    remaining = ((manifest or {}).get("outcome") or {}).get("agents_remaining")
    if exit_code == INCOMPLETE_EXIT and remaining:
        return True, f"ok (incomplete: {remaining} remaining)"
    return False, f"failed (exit {exit_code})"


def unapplied_overrides(manifest: dict, overrides: Overrides) -> list[str]:
    """The numeric routing overrides the run manifest does not report.

    Read from what ``run_scenario`` received; other overrides (strings,
    paths outside ``routing``) are not reported there and are not checked.
    """
    found = []
    for path, want in overrides:
        key = path.removeprefix("routing.")
        if not path.startswith("routing.") or isinstance(want, bool):
            continue
        if not isinstance(want, (int, float)):
            continue
        got = manifest_margin(manifest, key)
        if got != float(want):
            found.append(f"manifest has {key}={got!r}, wanted {want!r}")
    return found


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


def _resolve_commit(ref: str) -> str:
    """The full sha of *ref*; an unknown ref is an error naming it."""
    try:
        return _git("rev-parse", "--verify", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError as error:
        raise ValueError(f"unknown commit {ref!r}: {error.stderr.strip()}") from None


def _arm_requested(args: argparse.Namespace) -> bool:
    options = (args.margin, args.base_commit, args.head_commit)
    return any(options) or bool(args.base_set or args.head_set)


def build_arms(args: argparse.Namespace) -> tuple[str, dict[str, Arm]]:
    """The label and the two arms of a ``run`` from its options."""
    head_set = tuple(parse_override(t) for t in args.head_set)
    if args.margin:
        off = args.off if args.off is not None else MARGINS[args.margin].off
        head_set = (*head_set, (f"routing.{args.margin}", off))
    base = Arm(
        _resolve_commit(args.base_commit) if args.base_commit else None,
        tuple(parse_override(t) for t in args.base_set),
    )
    head_commit = _resolve_commit(args.head_commit) if args.head_commit else None
    return args.margin or "arms", {"base": base, "off": Arm(head_commit, head_set)}


def _arm_name(arm: Arm) -> str:
    return "tree" if arm.commit is None else arm.commit[:8]


def default_out(root: Path, label: str, arms: dict[str, Arm]) -> Path:
    """The default run folder; arm audits are named by commits and a spec hash."""
    if label != "arms":
        return root / AUDIT_DIR / f"{label}_{_git('rev-parse', '--short=8', 'HEAD')}"
    spec = json.dumps({k: a.describe() for k, a in arms.items()}, sort_keys=True)
    digest = hashlib.sha256(spec.encode()).hexdigest()[:6]
    names = "_".join(_arm_name(a) for a in arms.values())
    return root / AUDIT_DIR / f"arms_{names}_{digest}"


def _uv_sync(path: Path) -> None:
    """Build the locked environment (``uv sync --frozen``) in *path*."""
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    done = subprocess.run(
        ["uv", "sync", "--frozen", "--all-groups", "--all-extras"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
    )
    if done.returncode:
        raise RuntimeError(
            f"uv sync --frozen failed in {path}: {done.stderr.strip()[-800:]}"
        )


def _checkout(commit: str, stack: contextlib.ExitStack) -> CodeTree:
    """A detached worktree of *commit* with its locked environment.

    Removed when *stack* closes, as scripts/golden_rerouting.py does for its
    snapshots.
    """
    tmp = stack.enter_context(tempfile.TemporaryDirectory(prefix="margin_audit_"))
    path = Path(tmp) / "code"
    _git("worktree", "add", "--detach", str(path), commit)
    stack.callback(lambda: _git("worktree", "remove", "--force", str(path)))
    _uv_sync(path)
    return CodeTree(path, str(path / ".venv" / "bin" / "python"))


def code_trees(
    arms: dict[str, Arm], stack: contextlib.ExitStack
) -> dict[str, CodeTree]:
    """The code each arm runs from; arms at one commit share a checkout."""
    made: dict[str | None, CodeTree] = {None: CodeTree(REPO, sys.executable)}
    trees = {}
    for name, arm in arms.items():
        if arm.commit is not None and arm.commit not in made:
            made[arm.commit] = _checkout(arm.commit, stack)
        trees[name] = made[arm.commit]
    return trees


def imported_from(tree: CodeTree) -> dict[str, str]:
    """Where *tree*'s interpreter imports ``pyfds_evac`` and ``run`` from.

    Fails closed: the run is refused unless both lie under the checkout.
    """
    code = "import pyfds_evac, run; print(pyfds_evac.__file__); print(run.__file__)"
    done = subprocess.run(
        [tree.python, "-c", code],
        cwd=tree.root,
        env=run_env(tree.root),
        capture_output=True,
        text=True,
    )
    if done.returncode:
        raise RuntimeError(f"cannot import from {tree.root}: {done.stderr.strip()}")
    found = dict(zip(("pyfds_evac", "run"), done.stdout.split("\n")))
    for module, where in found.items():
        if not Path(where).resolve().is_relative_to(tree.root.resolve()):
            raise RuntimeError(f"{module} imported from {where}, not {tree.root}")
    return found


def _arms_clash(out: Path, arms: dict[str, Arm]) -> str | None:
    """Why *out* cannot take more runs of *arms*: it holds other arms."""
    path = out / "manifest.json"
    if not path.is_file():
        return None
    held = _read_json(path).get("arms")
    wanted = json.loads(json.dumps({k: a.describe() for k, a in arms.items()}))
    if held is None or held == wanted:
        return None
    return f"{out} holds runs of other arms: {json.dumps(held)}"


def _run_all(args: argparse.Namespace) -> int:
    if not _arm_requested(args):
        print("pass --margin or an arm option (--base-commit, --head-set, ...)")
        return 2
    try:
        label, arms = build_arms(args)
        for arm in arms.values():
            check_override_keys(arm.overrides)
    except ValueError as error:
        print(error)
        return 2
    root = Path(args.data_root)
    out = Path(args.out) if args.out else default_out(root, label, arms)
    dirty = _dirty_paths(any(a.commit is None for a in arms.values()))
    if dirty and not args.allow_dirty:
        print(f"refusing to run with uncommitted changes in {', '.join(dirty)}")
        return 2
    for name in args.decks:
        missing = _missing(DECKS[name], root)
        if missing:
            print(f"{name}: missing {', '.join(map(str, missing))}")
            return 2
    try:
        check_override_paths(args.decks, root, arms)
    except ValueError as error:
        print(error)
        return 2
    clash = _arms_clash(out, arms)
    if clash:
        print(clash)
        return 2
    jobs = _jobs(args.decks, args.seeds)
    pending = [j for j in jobs if not (out / j.label / "metrics.json").is_file()]
    print(f"{label}: {len(jobs)} runs, {len(pending)} to do, into {out}")
    out.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        trees = code_trees(arms, stack) if pending else {}
        return _run_pending(args, label, arms, trees, jobs, pending, root, out, dirty)


def _run_pending(
    args: argparse.Namespace,
    label: str,
    arms: dict[str, Arm],
    trees: dict[str, CodeTree],
    jobs: list[Job],
    pending: list[Job],
    root: Path,
    out: Path,
    dirty: list[str],
) -> int:
    off_value: object = None  # a code audit: the arms record both sides
    if args.margin:
        off_value = args.off if args.off is not None else MARGINS[args.margin].off
    manifest = {
        "margin": label,
        "off_value": off_value,
        "arms": {k: a.describe() for k, a in arms.items()},
        "imports": {name: imported_from(tree) for name, tree in trees.items()},
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
            pool.submit(
                _run_job, j, arms[j.arm], trees[j.arm], root, out, args.cost_history
            )
            for j in pending
        ]
        for job, future in zip(pending, futures):
            try:
                record = future.result()
            except Exception as error:  # noqa: BLE001 - recorded, not hidden
                record = {"run": job.label, "status": f"error: {error}", "wall_s": 0.0}
            manifest["runs"][record["run"]] = record
            failed += not record["status"].startswith("ok")
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
        spans = con.execute(
            "SELECT MAX(frame) - MIN(frame) FROM trajectory_data GROUP BY id"
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
    # Walking time per agent, spawn to egress: the mean sees a detour taken
    # by a minority of agents that rset_p95 and rset_last do not (#187 A6).
    walks = np.array([span / fps for (span,) in spans], dtype=float)
    if agents_remaining is None:
        agents_remaining = int(sum(frame >= last_frame for _, frame in last))
    metrics = {
        "n_agents": len(last),
        "rset_last": float(times.max()) if len(times) else None,
        "rset_p95": float(np.percentile(times, 95)) if len(times) else None,
        "walk_mean": float(walks.mean()) if len(walks) else None,
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
    FDS run, a deck with its own runner, or one the harness does not know.
    """
    known = DECKS.get(deck)
    if known is None or known.fds_dir is not None or known.runner:
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
    if metric == "walk_mean":
        return MetricRule(lambda base, agents: max(0.02 * base, 1.0), 1)
    return None


SECONDARY = (
    "returns",
    "switches_per_agent",
    "fed_p95",
    "fed_ge_1",
    "rset_last",
    "rset_p95",
    "walk_mean",
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


def code_audit_outcome(primary: dict, secondary: list[dict]) -> str:
    """The outcome of a code audit, in words that do not say "remove".

    The same rule as ``outcome``: not enough seeds, no distinct effect, or a
    distinct effect with its direction on the primary metric.
    """
    if primary.get("n", 0) < MIN_SEEDS:
        return f"undecided: {primary.get('n', 0)} seeds, fewer than {MIN_SEEDS}"
    if not primary["distinct"]:
        return "no distinct effect on the primary metric"
    word = {None: "changed", True: "worse", False: "better"}[primary["worse"]]
    text = (
        f"distinct effect on the primary metric: {word} "
        f"(mean d = {primary['effect']:.4g}, head minus base)"
    )
    harmed = [s["metric"] for s in secondary if s.get("distinct") and s.get("worse")]
    if harmed:
        text += f"; secondary metrics distinctly worse: {', '.join(harmed)}"
    return text


def _analyse(args: argparse.Namespace) -> int:
    folder = Path(args.run)
    manifest = _read_json(folder / "manifest.json")
    key = manifest["margin"]
    arms = manifest.get("arms")
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
        "arms": arms,
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
    judged = code_audit_outcome if key == "arms" else outcome
    report["outcome"] = judged(primary, [s for s in secondary if s])
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
    title = (
        "Arm audit"
        if report["margin"] == "arms"
        else f"Margin audit: {report['margin']} -> {report['off_value']}"
    )
    lines = [
        f"# {title}",
        "",
        f"Commit {report['commit']}" + (" (dirty)" if report["dirty"] else ""),
        *_arm_lines(report.get("arms")),
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


def _arm_lines(arms: dict | None) -> list[str]:
    """One line per arm: its commit (or the working tree) and overrides."""
    if not arms:
        return []
    return [
        f"Arm {name}: "
        + (arm["commit"][:8] if arm["commit"] else "working tree")
        + "".join(f", {path}={value}" for path, value in arm["overrides"].items())
        for name, arm in arms.items()
    ]


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
    run = sub.add_parser("run", help="run the paired base/off arms")
    run.add_argument("--margin", help="routing key to sweep: off arm has it off")
    run.add_argument("--off", type=float, help="off value; default from the plan")
    for arm in ("base", "head"):
        run.add_argument(f"--{arm}-commit", help=f"run the {arm} arm at this commit")
        run.add_argument(
            f"--{arm}-set",
            action="append",
            default=[],
            metavar="PATH=VALUE",
            help=f"override a config value of the {arm} arm",
        )
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
    margin = getattr(args, "margin", None)
    if margin and margin not in MARGINS and args.off is None:
        print(f"{margin} is not a known margin; pass --off VALUE")
        return 2
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
