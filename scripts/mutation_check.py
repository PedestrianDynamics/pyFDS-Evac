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
    "heat": Area(
        module="pyfds_evac/core/fed.py",
        tests=(
            "tests/test_heat_endpoint.py",
            "tests/test_heat_endpoint_docs.py",
            "tests/test_heat_integrated_intensity.py",
            "tests/test_heat_iso_clothing.py",
            "tests/test_heat_layer_flux.py",
            "tests/test_heat_only_case.py",
            "tests/test_heat_radiant_threshold.py",
            "tests/test_heat_sigma_225.py",
            "tests/test_heat_total_flux.py",
            "tests/verification/test_heat_endpoint_coupled.py",
            "tests/verification/test_heat_endpoint_outputs.py",
            "tests/verification/test_heat_fed_verif.py",
            "tests/verification/test_heat_flame_pass_reference.py",
            "tests/verification/test_heat_integrated_intensity_coupled.py",
            "tests/verification/test_heat_layer_flux_coupled.py",
            "tests/verification/test_heat_radiometer.py",
            "tests/verification/test_heat_room_decks.py",
            "tests/verification/test_heat_total_flux_coupled.py",
            "tests/verification/test_s6_heat_fed.py",
        ),
        mutants=(
            Mutant(
                "convective_law_in_kelvin",
                "unit conversion",
                "return (temperature_celsius**b) / a",
                "return ((temperature_celsius + 273.15) ** b) / a",
            ),
            Mutant(
                "accumulate_heat_seconds_as_minutes",
                "unit conversion",
                "duration_min = max(0.0, float(duration_s)) / _SECONDS_PER_MINUTE\n    rate = default_heat_fed_rate_per_minute",
                "duration_min = max(0.0, float(duration_s))\n    rate = default_heat_fed_rate_per_minute",
            ),
            Mutant(
                "heat_model_step_seconds_as_minutes",
                "unit conversion",
                '"""Advance cumulative heat FED by one simulation interval."""\n        inputs, rate_per_min = self.sample_rate(time_s, x, y)\n        updated = (\n            float(current_fed)\n            + rate_per_min * max(0.0, float(dt_s)) / _SECONDS_PER_MINUTE',
                '"""Advance cumulative heat FED by one simulation interval."""\n        inputs, rate_per_min = self.sample_rate(time_s, x, y)\n        updated = (\n            float(current_fed)\n            + rate_per_min * max(0.0, float(dt_s))',
            ),
            Mutant(
                "total_flux_gas_without_kelvin",
                "unit conversion",
                "    t_gas = gas_temperature_celsius + _KELVIN\n",
                "    t_gas = gas_temperature_celsius\n",
            ),
            Mutant(
                "total_flux_radiant_in_w",
                "unit conversion",
                "return (radiant + convective) / 1000.0 + external_flux_kw_m2",
                "return radiant + convective / 1000.0 + external_flux_kw_m2",
            ),
            Mutant(
                "layer_flux_in_w",
                "unit conversion",
                "return view_factor * layer_emissivity * radiant / 1000.0",
                "return view_factor * layer_emissivity * radiant",
            ),
            Mutant(
                "iso_threshold_lt_to_le",
                "reversed comparison",
                "if radiant_kw_m2 < ISO_RADIANT_THRESHOLD_KW_M2:",
                "if radiant_kw_m2 <= ISO_RADIANT_THRESHOLD_KW_M2:",
            ),
            Mutant(
                "validity_gt_to_ge",
                "reversed comparison",
                "return temperature_celsius > HEAT_CONVECTIVE_VALIDITY_MAX_C",
                "return temperature_celsius >= HEAT_CONVECTIVE_VALIDITY_MAX_C",
            ),
            Mutant(
                "u_factor_range_le_to_lt",
                "reversed comparison",
                "math.isfinite(u_factor) and low <= u_factor <= high",
                "math.isfinite(u_factor) and low < u_factor < high",
            ),
            Mutant(
                "drop_endpoint_second_term",
                "removed term",
                "endpoint.a1 * temperature_celsius**-endpoint.b1\n            + endpoint.a2 * temperature_celsius**-endpoint.b2\n",
                "endpoint.a1 * temperature_celsius**-endpoint.b1\n",
            ),
            Mutant(
                "drop_flux_exponent",
                "removed term",
                "return float(q_kw_m2**HEAT_FLUX_EXPONENT / dose)",
                "return float(q_kw_m2 / dose)",
            ),
            Mutant(
                "drop_iso_threshold_in_dose",
                "removed term",
                "integrated_intensity_kw_m2=inputs.integrated_intensity_kw_m2,\n            radiant_threshold=True,",
                "integrated_intensity_kw_m2=inputs.integrated_intensity_kw_m2,\n            radiant_threshold=False,",
            ),
            Mutant(
                "drop_skin_emission_from_u",
                "removed term",
                "radiant_flux_from_integrated_intensity_kw_m2(u - u_skin, self.u_factor)",
                "radiant_flux_from_integrated_intensity_kw_m2(u, self.u_factor)",
            ),
            Mutant(
                "drop_view_factor",
                "removed term",
                "return view_factor * layer_emissivity * radiant / 1000.0",
                "return layer_emissivity * radiant / 1000.0",
            ),
            Mutant(
                "drop_convection_in_model_flux",
                "removed term",
                "            emissivity=0.0,\n            convective_coefficient=self.convective_coefficient,",
                "            emissivity=0.0,\n            convective_coefficient=0.0,",
            ),
        ),
    ),
    "smoke_speed": Area(
        module="pyfds_evac/core/smoke_speed.py",
        tests=(
            "tests/test_smoke_speed.py",
            "tests/test_smoke_speed_widget.py",
            "tests/test_speed_update_pin.py",
            "tests/test_speed_update_skip.py",
            "tests/test_iso_table21_coupled.py",
            "tests/test_model_speed_attrs.py",
            "tests/verification/test_smoke_speed_verif.py",
            "tests/verification/test_s2_corridor_speed.py",
            "tests/verification/test_speed_update_coupling.py",
            "tests/verification/test_fds_evac_guide_cases.py",
        ),
        mutants=(
            Mutant(
                "soot_mg_as_g",
                "unit conversion",
                "* soot_density * 1.0e-6",
                "* soot_density * 1.0e-3",
            ),
            Mutant(
                "visibility_k_over_c",
                "unit conversion",
                "visibility = visibility_factor_c / extinction_per_m",
                "visibility = extinction_per_m / visibility_factor_c",
            ),
            Mutant(
                "fridolf_absolute_speed_as_factor",
                "unit conversion",
                "return float(speed / free_speed)",
                "return float(speed)",
            ),
            Mutant(
                "fridolf_reduction_sign",
                "reversed comparison",
                "reduced = free_speed - slope * (visibility_threshold_m - visibility)",
                "reduced = free_speed - slope * (visibility - visibility_threshold_m)",
            ),
            Mutant(
                "fridolf_free_speed_le_to_lt",
                "reversed comparison",
                "if extinction_per_m == 0.0 or free_speed <= 0.0:",
                "if extinction_per_m == 0.0 or free_speed < 0.0:",
            ),
            Mutant(
                "lund_drop_alpha",
                "removed term",
                "factor = 1.0 + (beta * extinction_per_m) / alpha",
                "factor = 1.0 + beta * extinction_per_m",
            ),
            Mutant(
                "lund_drop_min_clamp",
                "removed term",
                "return float(np.clip(factor, min_speed_factor, 1.0))",
                "return float(min(factor, 1.0))",
            ),
            Mutant(
                "fridolf_drop_floor",
                "removed term",
                "speed = min(free_speed, max(min_speed_m_per_s, reduced))",
                "speed = min(free_speed, reduced)",
            ),
            Mutant(
                "fridolf_drop_cap",
                "removed term",
                "speed = min(free_speed, max(min_speed_m_per_s, reduced))",
                "speed = max(min_speed_m_per_s, reduced)",
            ),
            Mutant(
                "model_ignores_free_speed",
                "removed term",
                "                    else free_speed_m_per_s\n",
                "                    else FRIDOLF_DEFAULT_FREE_SPEED_M_PER_S\n",
            ),
        ),
    ),
}


def _run_tests(python: str, tests: tuple[str, ...]) -> tuple[bool, list[str]]:
    """Run the tests; return (all passed, ids of failed tests)."""
    proc = subprocess.run(
        [
            python,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-rf",
            "-m",
            "not external_data",
            *tests,
        ],
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
