"""Inject representative defects into a model module and record which tests fail.

Each mutant replaces one exact source snippet (a unit conversion, a
threshold comparison or an equation term), runs the area's tests and
restores the file. A mutant that no test kills is a gap in the suite, not
a defect in the code (docs/TESTING_GUIDELINES.md §4, issue #816).

Run by hand from a clean checkout, never in the shared working tree of a
running agent::

    python scripts/mutation_check.py fed [--python .venv/bin/python]

The module is restored from memory after each mutant and checked against
its original text at the end. Exit status is 0 if every mutant is killed,
1 otherwise.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutant:
    name: str
    kind: str
    old: str
    new: str


@dataclass(frozen=True)
class Area:
    module: str
    tests: tuple[str, ...]
    mutants: tuple[Mutant, ...]


AREAS: dict[str, Area] = {
    "fed": Area(
        module="pyfds_evac/core/fed.py",
        tests=(
            "tests/test_fed.py",
            "tests/test_fed_rate_memo.py",
            "tests/test_fic_vs_fed_speed.py",
            "tests/test_fed_margin_deck.py",
            "tests/verification/test_fed_verif.py",
            "tests/verification/test_fed_fic_all_zones.py",
            "tests/verification/test_fed_slice_height.py",
            "tests/verification/test_s1_corridor_fed.py",
        ),
        mutants=(
            Mutant(
                "co_percent_to_ppm_x1000",
                "unit conversion",
                "co_volume_fraction_percent)) * 10000.0",
                "co_volume_fraction_percent)) * 1000.0",
            ),
            Mutant(
                "accumulate_seconds_as_minutes",
                "unit conversion",
                "duration_min = max(0.0, float(duration_s)) / _SECONDS_PER_MINUTE\n"
                "    return float(initial_fed) + default_fed_rate_per_minute",
                "duration_min = max(0.0, float(duration_s))\n"
                "    return float(initial_fed) + default_fed_rate_per_minute",
            ),
            Mutant(
                "model_step_seconds_as_minutes",
                "unit conversion",
                '"""Advance cumulative FED by one simulation interval."""\n'
                "        inputs, rate_per_min = self.sample_rate(time_s, x, y)\n"
                "        updated = (\n"
                "            float(current_fed)\n"
                "            + rate_per_min * max(0.0, float(dt_s)) / _SECONDS_PER_MINUTE",
                '"""Advance cumulative FED by one simulation interval."""\n'
                "        inputs, rate_per_min = self.sample_rate(time_s, x, y)\n"
                "        updated = (\n"
                "            float(current_fed)\n"
                "            + rate_per_min * max(0.0, float(dt_s))",
            ),
            Mutant(
                "model_components_seconds_as_minutes",
                "unit conversion",
                "* max(0.0, float(dt_s))\n"
                "            / _SECONDS_PER_MINUTE\n"
                "        )\n        return inputs, components, updated",
                "* max(0.0, float(dt_s))\n"
                "        )\n        return inputs, components, updated",
            ),
            Mutant(
                "o2_threshold_ge_to_gt",
                "reversed comparison",
                "if float(o2_percent) >= float(threshold_percent):",
                "if float(o2_percent) > float(threshold_percent):",
            ),
            Mutant(
                "hv_zero_co2_le_to_lt",
                "reversed comparison",
                "if not math.isfinite(co2_percent) or co2_percent <= 0.0:",
                "if not math.isfinite(co2_percent) or co2_percent < 0.0:",
            ),
            Mutant(
                "time_to_threshold_le_to_lt",
                "reversed comparison",
                "remaining = float(threshold) - float(initial_fed)\n"
                "    if remaining <= 0.0:\n"
                "        return 0.0\n"
                "    rate_per_min = default_fed_rate_per_minute(inputs)",
                "remaining = float(threshold) - float(initial_fed)\n"
                "    if remaining < 0.0:\n"
                "        return 0.0\n"
                "    rate_per_min = default_fed_rate_per_minute(inputs)",
            ),
            Mutant(
                "drop_nox_term",
                "removed term",
                "+ self.cn_rate_per_min\n            + self.nox_rate_per_min\n",
                "+ self.cn_rate_per_min\n",
            ),
            Mutant(
                "drop_hv_multiplier",
                "removed term",
                "return narcotic_sum * self.hv_co2 + self.o2_rate_per_min",
                "return narcotic_sum + self.o2_rate_per_min",
            ),
            Mutant(
                "drop_nox_protection_in_cn",
                "removed term",
                "c_cn = max(0.0, float(hcn_ppm) - c_nox)",
                "c_cn = max(0.0, float(hcn_ppm))",
            ),
            Mutant(
                "drop_hv_offset",
                "removed term",
                "math.exp(0.1903 * float(co2_percent) + 2.0004) / 7.1",
                "math.exp(0.1903 * float(co2_percent)) / 7.1",
            ),
            Mutant(
                "drop_cn_minus_one",
                "removed term",
                "rate = (math.exp(c_cn / 43.0) - 1.0) / 220.0",
                "rate = math.exp(c_cn / 43.0) / 220.0",
            ),
        ),
    ),
}


def _run_tests(python: str, tests: tuple[str, ...]) -> tuple[bool, list[str]]:
    """Run the tests; return (all passed, ids of failed tests)."""
    proc = subprocess.run(
        [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *tests],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    failed = [
        line.removeprefix("FAILED ").split(" - ")[0]
        for line in proc.stdout.splitlines()
        if line.startswith("FAILED ")
    ]
    return proc.returncode == 0, failed


def _check_mutant(
    m: Mutant, path: Path, original: str, python: str, tests: tuple[str, ...]
) -> bool:
    """Apply one mutant, run the tests, restore; return True if it survived."""
    path.write_text(original.replace(m.old, m.new))
    try:
        ok, failed = _run_tests(python, tests)
    finally:
        path.write_text(original)
    status = "SURVIVED" if ok else f"killed by {len(failed)}"
    print(f"{m.name:32s} {m.kind:20s} {status}")
    for test_id in failed:
        print(f"    {test_id}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("area", choices=sorted(AREAS))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    area = AREAS[args.area]
    path = REPO / area.module
    original = path.read_text()

    for m in area.mutants:
        if original.count(m.old) != 1:
            print(f"{m.name}: snippet not found exactly once")
            return 2

    ok, failed = _run_tests(args.python, area.tests)
    if not ok:
        print(f"baseline fails, not mutating: {failed}")
        return 2

    survivors = [
        m.name
        for m in area.mutants
        if _check_mutant(m, path, original, args.python, area.tests)
    ]

    assert path.read_text() == original
    print(f"\n{len(area.mutants) - len(survivors)}/{len(area.mutants)} killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
