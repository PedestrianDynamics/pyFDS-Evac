"""Full-precision base-vs-head differential of the routing unit cases (#187).

The routing snapshots in ``tests/golden/`` round floats to 4 digits and
compare them to 1e-3, so they cannot show that a refactor step left the
routing bit for bit unchanged. This script runs the same case builders,
``tests/test_rerouting_golden.py`` and ``tests/test_routing_decisions.py``,
in two checkouts and compares everything they produce at full precision:
every field of each ``RouteCost`` (with its segments), ``RouteSwitch`` and
``AgentRouteState``, the ``wait_info`` left behind, every extinction and FED
sample in the order it was taken, and every segment-cache entry in the
order it was written.

Each checkout runs in its own interpreter with that checkout first on
``sys.path``, so each side uses its own code and its own case builders. The
serialisation is this script's: the snapshot functions of the test modules
are replaced by full-field dumps, and their float rounding by the identity.

Usage::

    uv run python scripts/routing_differential.py BASE_CHECKOUT HEAD_CHECKOUT

It prints each checkout's commit and the hashes of its case builders, then
``identical`` or the differences, and exits non-zero on a difference. Both
checkouts must use the same interpreter and dependencies (this one).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The case builders the dump runs, and the code whose hash is recorded.
BUILDERS = (
    "tests/test_rerouting_golden.py",
    "tests/test_routing_decisions.py",
)
RECORDED = (*BUILDERS, "pyfds_evac/core/route_graph.py")
MAX_REPORT = 30


# ── Child: dump one checkout ──────────────────────────────────────────


def _full(value):
    """*value* as JSON data, losing nothing a comparison should see.

    Floats stay floats (JSON writes them with ``repr``), dict order is kept,
    sets are sorted, dataclasses give every field, including those left out
    of their ``==``, and a shapely geometry gives its WKB. Anything else is
    an error, not a ``repr`` that could hold a memory address.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _full(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(k): _full(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_full(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_full(v) for v in value), key=repr)
    if hasattr(value, "wkb_hex"):
        return value.wkb_hex
    raise TypeError(f"routing differential: cannot dump a {type(value).__name__}")


def _identity(value, digits=None):
    """Stands in for the snapshot rounding ``test_rerouting_golden._r``."""
    del digits
    return value


def _check_imported_from(root: Path, module) -> None:
    """Exit with an error unless *module* was imported from *root* (#721)."""
    where = Path(module.__file__).resolve()
    if not where.is_relative_to(root.resolve()):
        sys.exit(
            f"routing differential: {module.__name__} was imported from "
            f"{where}, not from the checkout under test {root}"
        )


def _patch(golden, decisions, results: dict) -> None:
    """Route the snapshot functions to full dumps and collect the snapshots."""

    def collect(relpath: str, actual) -> None:
        if relpath in results:
            sys.exit(f"routing differential: snapshot {relpath} written twice")
        results[relpath] = _full(actual)

    replacements = (
        (golden, "_r", _identity),
        (golden, "_check_golden", collect),
        (golden, "_route_snapshot", _full),
        (golden, "_switch_snapshot", _full),
        (decisions, "_route_snapshot", _full),
        (decisions, "_segment_snapshot", _segment_values),
        (decisions, "_state_snapshot", _full),
        (decisions, "_wait_info_snapshot", _full),
    )
    # A renamed helper would leave the rounding in place on both sides and
    # hide every last-bit difference, so a missing one is an error.
    for module, name, _ in replacements:
        if not callable(getattr(module, name, None)):
            sys.exit(f"routing differential: {module.__name__} has no {name}")
    for module, name, replacement in replacements:
        setattr(module, name, replacement)


def _segment_values(seg) -> list:
    """Every field of a cached segment, as the list ``_cache_snapshot`` joins."""
    return [_full(getattr(seg, f.name)) for f in dataclasses.fields(seg)]


def _run_cases(golden, decisions) -> None:
    """Every snapshot test of the two modules, against the collector."""
    decisions.test_rank_routes_snapshot()
    decisions.test_evaluate_and_reroute_snapshot()
    for history in (False, True):
        decisions.test_shared_cache_passes_snapshot(history)
    decisions.test_threshold_equality_snapshot()
    decisions.test_anchor_and_flee_snapshot()
    decisions.test_switch_label_snapshot()
    decisions.test_reference_exit_selection_snapshot()
    decisions.test_reference_exit_reroute_snapshot()
    decisions.test_agent_path_snapshot()
    for name in sorted(golden.RANK_CASES):
        golden.test_rank_routes_matches_golden(name)
    for name in sorted(golden.REROUTE_CASES):
        golden.test_evaluate_and_reroute_matches_golden(name)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else f"<git failed: {args}>"


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _meta(root: Path) -> dict:
    import jupedsim

    return {
        "checkout": str(root),
        "commit": _git(root, "rev-parse", "HEAD"),
        "dirty": _git(root, "status", "--porcelain", "--", "pyfds_evac", "tests"),
        "python": sys.version,
        "jupedsim": jupedsim.__version__,
        "hashes": {rel: _sha256(root / rel) for rel in RECORDED},
    }


def _dump(root: Path, out: Path) -> None:
    """Run the case builders of the checkout *root* and write the dump."""
    sys.path[:0] = [str(root), str(root / "tests")]
    import test_rerouting_golden as golden
    import test_routing_decisions as decisions

    import pyfds_evac

    for module in (pyfds_evac, golden, decisions):
        _check_imported_from(root, module)
    results: dict = {}
    _patch(golden, decisions, results)
    _run_cases(golden, decisions)
    record = {"meta": _meta(root), "snapshots": results}
    out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


# ── Parent: run both checkouts and compare ────────────────────────────


def _child_env(root: Path) -> dict[str, str]:
    """The environment for a child: *root* first on the path, fixed hashing."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(root), str(root / "tests"), env.get("PYTHONPATH", "")) if p
    )
    env["PYTHONHASHSEED"] = "0"
    return env


def _checkout_problem(root: Path) -> str | None:
    missing = [rel for rel in RECORDED if not (root / rel).is_file()]
    if missing:
        return f"{root} is not a pyFDS-Evac checkout: no {', '.join(missing)}"
    return None


def _run_child(root: Path, out: Path) -> None:
    subprocess.run(
        [sys.executable, __file__, "--dump", str(root), str(out)],
        check=True,
        cwd=root,
        env=_child_env(root),
        stdout=subprocess.DEVNULL,
    )


def _flatten(value, prefix: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        flat: dict[str, object] = {}
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return flat
    if isinstance(value, list):
        flat = {}
        for index, item in enumerate(value):
            flat.update(_flatten(item, f"{prefix}[{index}]"))
        if not value:
            flat[prefix] = []
        return flat
    return {prefix: value}


def _differences(base: dict, head: dict) -> list[str]:
    """Each value that differs between two dumps' snapshots, as a line.

    The serialised text decides; the flattened view only explains. Two dumps
    whose values agree but whose key order differs are reported as such.
    """
    text_a = json.dumps(base["snapshots"])
    text_b = json.dumps(head["snapshots"])
    if text_a == text_b:
        return []
    flat_a, flat_b = _flatten(base["snapshots"]), _flatten(head["snapshots"])
    lines = []
    for key in list(flat_a) + [k for k in flat_b if k not in flat_a]:
        a, b = flat_a.get(key, "<missing>"), flat_b.get(key, "<missing>")
        if a == b and type(a) is type(b):
            continue
        lines.append(f"{key}: {a!r} vs {b!r}")
    return lines or ["same values, different order of keys"]


def _print_meta(role: str, meta: dict) -> None:
    print(f"{role}  {meta['checkout']}")
    print(f"      commit {meta['commit']}, dirty: {meta['dirty'] or 'no'}")
    print(f"      python {meta['python'].split()[0]}, jupedsim {meta['jupedsim']}")


def _builders_note(base: dict, head: dict) -> list[str]:
    a, b = base["meta"]["hashes"], head["meta"]["hashes"]
    return [
        f"{rel} differs between the checkouts" for rel in BUILDERS if a[rel] != b[rel]
    ]


def compare(base_root: Path, head_root: Path, keep: Path | None = None) -> int:
    """Dump both checkouts and print their differences; non-zero if any."""
    for root in (base_root, head_root):
        problem = _checkout_problem(root)
        if problem:
            print(f"BAD   {problem}")
            return 2
    with tempfile.TemporaryDirectory() as tmp:
        folder = keep or Path(tmp)
        folder.mkdir(parents=True, exist_ok=True)
        dumps = []
        for root, name in ((base_root, "base.json"), (head_root, "head.json")):
            _run_child(root.resolve(), folder / name)
            dumps.append(json.loads((folder / name).read_text(encoding="utf-8")))
    base, head = dumps
    _print_meta("base", base["meta"])
    _print_meta("head", head["meta"])
    for note in _builders_note(base, head):
        print(f"note  {note}")
    if base["meta"]["python"] != head["meta"]["python"]:
        print("BAD   the checkouts ran under different interpreters")
        return 2
    print(f"snapshots: {len(base['snapshots'])} vs {len(head['snapshots'])}")
    lines = _differences(base, head)
    for line in lines[:MAX_REPORT]:
        print(f"DIFF  {line}")
    if len(lines) > MAX_REPORT:
        print(f"      ... and {len(lines) - MAX_REPORT} more")
    print(f"{len(lines)} differences" if lines else "identical")
    return 1 if lines else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", type=Path, nargs="?", help="Base checkout")
    parser.add_argument("head", type=Path, nargs="?", help="Head checkout")
    parser.add_argument(
        "--keep", type=Path, help="Folder to keep the two dumps in (base/head.json)"
    )
    parser.add_argument("--dump", nargs=2, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.dump:
        _dump(*args.dump)
        return 0
    if args.base is None or args.head is None:
        parser.error("give the base and the head checkout")
    return compare(args.base, args.head, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
