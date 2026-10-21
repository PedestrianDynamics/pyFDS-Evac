"""Inject representative defects into a model module and record which tests fail.

Each mutant replaces one exact source snippet (a unit conversion, a
threshold comparison or an equation term), runs the area's tests and
restores the file. A mutant that no test kills is a gap in the suite, not
a defect in the code (docs/TESTING_GUIDELINES.md §4, issue #816).

Run by hand from a clean checkout, never in the shared working tree of a
running agent::

    python scripts/mutation_check.py fed [--python .venv/bin/python]

The module is restored from memory after each mutant and checked against
its original text at the end. A mutant counts as killed only when tests
fail; a pytest run that errors without a failed test (an import or syntax
error, a collection error) is reported as invalid. Exit status is 0 if
every mutant is killed, 1 otherwise.
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
    module: str | None = None  # defaults to the area's module


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
    "routing_cost": Area(
        module="pyfds_evac/core/route_graph.py",
        tests=(
            "tests/test_route_smoke_integral.py",
            "tests/test_route_grid_sampling.py",
            "tests/test_foresight_arrival_time.py",
            "tests/test_route_assessment.py",
            "tests/test_walk_dose.py",
            "tests/test_fds_horizon.py",
            "tests/test_rerouting_hand_checks.py",
            "tests/test_route_cost_hand_values.py",
            "tests/test_route_graph.py::TestSegmentCost",
            "tests/test_route_graph.py::TestRouteCost",
            "tests/test_route_graph.py::TestPositionAwareRouting",
            "tests/test_route_graph.py::TestIntegratedExtinctionAlongLos",
            "tests/test_route_graph.py::TestPolylineSampling",
            "tests/test_route_graph.py::TestFedRateAdapter",
            "tests/test_route_graph.py::TestWalkableRemainingDistance",
            "tests/test_routing_decisions.py::test_ramp_tau_matches_hand_value",
        ),
        mutants=(
            Mutant(
                "tau_from_k_max",
                "removed term",
                "tau_route = k_ave * effective_length",
                "tau_route = k_max * effective_length",
            ),
            Mutant(
                "tau_from_k_leg_max",
                "removed term",
                "tau_route = k_ave * effective_length",
                "tau_route = k_leg_max * effective_length",
            ),
            Mutant(
                "tau_without_length",
                "removed term",
                "tau_route = k_ave * effective_length",
                "tau_route = k_ave",
            ),
            Mutant(
                "tau_from_path_length",
                "removed term",
                "tau_route = k_ave * effective_length",
                "tau_route = k_ave * path_length",
            ),
            Mutant(
                "segment_speed_ignores_smoke",
                "removed term",
                "    effective_speed = config.base_speed_m_per_s * sf\n"
                "    travel_time = length / effective_speed",
                "    effective_speed = config.base_speed_m_per_s\n"
                "    travel_time = length / effective_speed",
            ),
            Mutant(
                "leg_speed_ignores_smoke",
                "removed term",
                "    effective_speed = config.base_speed_m_per_s * sf\n"
                "    travel_time = length_m / effective_speed",
                "    effective_speed = config.base_speed_m_per_s\n"
                "    travel_time = length_m / effective_speed",
            ),
            Mutant(
                "fed_rate_at_decision_time",
                "removed term",
                "fed_rate_sampler.sample_fed_rate(arrival_time_s, mid_x, mid_y)",
                "fed_rate_sampler.sample_fed_rate(time_s, mid_x, mid_y)",
            ),
            Mutant(
                "segment_dose_seconds_as_minutes",
                "unit conversion",
                "fed_growth = fed_rate * travel_time / _SECONDS_PER_MINUTE",
                "fed_growth = fed_rate * travel_time",
            ),
            Mutant(
                "dose_seconds_as_minutes",
                "unit conversion",
                "return fed_rate_per_min * travel_time_s / _SECONDS_PER_MINUTE",
                "return fed_rate_per_min * travel_time_s",
            ),
            Mutant(
                "fds_end_cap_removed",
                "removed term",
                "    if t_foreseen <= cap:\n        return t_foreseen",
                "    if True:\n        return t_foreseen",
            ),
            Mutant(
                "fds_end_cap_ignores_decision_time",
                "reversed comparison",
                "    cap = max(time_s, end_s)\n    if t_foreseen <= cap:",
                "    cap = min(time_s, end_s)\n    if t_foreseen <= cap:",
            ),
            Mutant(
                "clock_at_many_uncapped",
                "removed term",
                "        return np.minimum(t, cap)",
                "        return t",
            ),
            Mutant(
                "length_weighting_dropped",
                "removed term",
                "    weighted = sum(mean * length for mean, length in segment_means)\n"
                "    total_length = sum(length for _, length in segment_means)",
                "    weighted = sum(mean for mean, length in segment_means)\n"
                "    total_length = float(len(segment_means))",
            ),
            Mutant(
                "arrival_horizon_cap_dropped",
                "removed term",
                "return time_s + min(walked_m / speed, config.foresight_horizon_s)",
                "return time_s + walked_m / speed",
            ),
            Mutant(
                "arrival_ignores_anticipate",
                "reversed comparison",
                "    if not config.anticipate:\n        return time_s\n    speed =",
                "    if config.anticipate:\n        return time_s\n    speed =",
            ),
            Mutant(
                "arrival_distance_as_time",
                "unit conversion",
                "return time_s + min(walked_m / speed, config.foresight_horizon_s)",
                "return time_s + min(walked_m, config.foresight_horizon_s)",
            ),
            Mutant(
                "visible_lt_to_le",
                "reversed comparison",
                "visible = k_avg < config.visibility_extinction_threshold",
                "visible = k_avg <= config.visibility_extinction_threshold",
            ),
            Mutant(
                "fed_violation_gt_to_ge",
                "reversed comparison",
                "    if fed_max > fed_threshold:",
                "    if fed_max >= fed_threshold:",
            ),
            Mutant(
                "step_samples_drop_far_end",
                "removed term",
                "n_samples = max(2, int(math.ceil(length / step_m)) + 1)",
                "n_samples = max(2, int(math.ceil(length / step_m)))",
            ),
            Mutant(
                "position_length_ignores_agent_walk",
                "removed term",
                "path_length - first_length_m + remaining,",
                "path_length + remaining,",
            ),
            Mutant(
                "excess_time_not_prorated",
                "removed term",
                "excess_time = walk_time_s * (excess / remaining)",
                "excess_time = walk_time_s",
            ),
            Mutant(
                "clock_ignores_walked_offset",
                "removed term",
                "t = min(self.t0 + (self.d0 + d) / self.speed, self.horizon_end_s)",
                "t = min(self.t0 + d / self.speed, self.horizon_end_s)",
            ),
            Mutant(
                "horizon_measured_from_zero",
                "unit conversion",
                "horizon_end_s=time_s + config.foresight_horizon_s,\n"
                "        decision_time_s=time_s,",
                "horizon_end_s=config.foresight_horizon_s,\n"
                "        decision_time_s=time_s,",
            ),
        ),
    ),
    "routing_graph": Area(
        module="pyfds_evac/core/route_graph.py",
        tests=(
            "tests/test_route_graph_hand_values.py",
            "tests/test_route_graph.py::TestGraphConstruction",
            "tests/test_route_graph.py::TestDijkstra",
            "tests/test_route_graph.py::TestEdgeCases",
            "tests/test_route_graph.py::TestDynamicDijkstra",
            "tests/test_route_graph.py::TestStaggeredScheduling",
            "tests/test_scheduled_exits.py::test_unscheduled_exits_are_always_open",
            "tests/test_scheduled_exits.py::test_schedule_window_is_half_open",
        ),
        mutants=(
            Mutant(
                "open_from_lt_to_le",
                "reversed comparison",
                "time_s < self.open_from_s",
                "time_s <= self.open_from_s",
            ),
            Mutant(
                "closed_after_lt_to_le",
                "reversed comparison",
                "time_s < self.closed_after_s",
                "time_s <= self.closed_after_s",
            ),
            Mutant(
                "closed_down_ge_to_gt",
                "reversed comparison",
                "and time_s >= node.closed_after_s",
                "and time_s > node.closed_after_s",
            ),
            Mutant(
                "closed_target_edges_kept",
                "removed term",
                "if e.target not in closed",
                "if True",
            ),
            Mutant(
                "closed_source_edges_kept",
                "removed term",
                "if src not in closed",
                "if True",
            ),
            Mutant(
                "first_hops_back_edge_into_source",
                "removed term",
                "if first_hops is not None and edge.target == source:",
                "if False:",
            ),
            Mutant(
                "first_hops_seed_source",
                "removed term",
                "node in dist and node != source and cost < dist[node]",
                "node in dist and cost < dist[node]",
            ),
            Mutant(
                "dynamic_weights_ignored",
                "removed term",
                "w = dynamic_weights.get((edge.source, edge.target), edge.weight)",
                "w = edge.weight",
            ),
            Mutant(
                "relax_lt_to_le",
                "reversed comparison",
                "if alt < dist[edge.target]:",
                "if alt <= dist[edge.target] and edge.target != u:",
            ),
            Mutant(
                "exits_keep_infinite_cost",
                "removed term",
                "if exit_id in dist and math.isfinite(dist[exit_id]):",
                "if exit_id in dist:",
            ),
            Mutant(
                "path_to_keeps_infinite_cost",
                "removed term",
                "if target not in dist or not math.isfinite(dist[target]):",
                "if target not in dist:",
            ),
            Mutant(
                "reconstruct_no_source_stop",
                "removed term",
                "            if cur == source:\n                break\n",
                "",
            ),
        ),
    ),
    "routing_policy": Area(
        module="pyfds_evac/core/route_graph.py",
        tests=(
            "tests/test_route_policy_hand_values.py",
            "tests/test_route_gate.py",
            "tests/test_fallback_hold.py",
            "tests/test_fallback_tau_hold.py",
            "tests/test_gate_exit_pricing.py",
        ),
        mutants=(
            Mutant(
                "tau_refusal_gt_to_ge",
                "reversed comparison",
                "if tau_route > budget:",
                "if tau_route >= budget:",
            ),
            Mutant(
                "deadband_gt_to_ge",
                "reversed comparison",
                "if delta > margin:",
                "if delta >= margin:",
            ),
            Mutant(
                "deadband_lt_to_le",
                "reversed comparison",
                "if delta < -margin:",
                "if delta <= -margin:",
            ),
            Mutant(
                "deadband_zero",
                "removed term",
                "margin = cost_config.tau_max * cost_config.tau_deadband",
                "margin = 0.0",
            ),
            # The missing refusal half was the oscillation bug (_tau_band).
            Mutant(
                "deadband_refusal_removed",
                "changed constant",
                "            return -1\n",
                "            return 0\n",
            ),
            Mutant(
                "additive_fed_term_dropped",
                "removed term",
                "+ config.w_fed * seg.fed_growth",
                "+ 0.0",
            ),
            Mutant(
                "fed_violation_gt_to_ge",
                "reversed comparison",
                "if fed_max > fed_threshold:",
                "if fed_max >= fed_threshold:",
            ),
            Mutant(
                "fed_max_without_current_fed",
                "removed term",
                "fed_max = current_fed + fed_growth",
                "fed_max = fed_growth",
            ),
            Mutant(
                "fallback_hold_ignored",
                "removed term",
                'if config.fallback_rule == "hold":',
                "if False:",
            ),
            Mutant(
                "fallback_margin_lt_to_le",
                "reversed comparison",
                "return rival.tau_route < current.tau_route * margin",
                "return rival.tau_route <= current.tau_route * margin",
            ),
            Mutant(
                "taus_tie_le_to_lt",
                "reversed comparison",
                "return abs(a - b) <= EPS_TAU",
                "return abs(a - b) < EPS_TAU",
            ),
        ),
    ),
    "routing_reroute": Area(
        module="pyfds_evac/core/route_graph.py",
        tests=(
            "tests/test_route_reroute_hand_values.py",
            "tests/test_rerouting_hand_checks.py",
            "tests/test_routing_decisions.py",
            "tests/test_switch_reasons.py",
            "tests/test_no_known_exit.py",
            # Needs the webapp extra and exercises none of the mutated lines.
            "--deselect=tests/test_no_known_exit.py::TestRunModes::test_the_gui_refuses_the_form",
            "tests/test_flow_spawn_errors.py",
            "tests/test_flow_spawn_spacing.py",
            "tests/test_look_before_wander.py",
            "tests/test_scheduled_exits.py",
            "tests/test_fallback_hold.py",
            "tests/test_fallback_tau_hold.py",
        ),
        mutants=(
            Mutant(
                "reeval_interval_ge_to_gt",
                "reversed comparison",
                "return current_time_s - state.last_eval_time_s >= interval_s",
                "return current_time_s - state.last_eval_time_s > interval_s",
            ),
            Mutant(
                "reeval_offset_ge_to_gt",
                "reversed comparison",
                "return current_time_s >= state.eval_offset_s",
                "return current_time_s > state.eval_offset_s",
            ),
            Mutant(
                "reeval_disabled_le_to_lt",
                "reversed comparison",
                "    if interval_s <= 0:\n        return False\n",
                "    if interval_s < 0:\n        return False\n",
            ),
            Mutant(
                "refused_best_not_returned",
                "removed term",
                "if best.rejected and best.rejection_reason and not _is_fallback(best):",
                "if False:",
            ),
            Mutant(
                "same_exit_idle_ignored",
                "removed term",
                'if old_exit == best.exit_id and wait_info.get("state") != "idle":',
                "if old_exit == best.exit_id:",
            ),
            Mutant(
                "no_exit_last_eval_unset",
                "removed term",
                "        route_state.last_eval_time_s = current_time_s\n"
                "        _remember_known(route_state, cognitive_map)\n"
                "        if cognitive_map is None:",
                "        _remember_known(route_state, cognitive_map)\n"
                "        if cognitive_map is None:",
            ),
            Mutant(
                "last_eval_unset_after_choice",
                "removed term",
                "    route_state.last_eval_time_s = current_time_s\n"
                "    _remember_known(route_state, cognitive_map)\n\n"
                "    # An idle",
                "    _remember_known(route_state, cognitive_map)\n\n    # An idle",
            ),
            Mutant(
                "closed_default_route_old_exit_dropped",
                "removed term",
                "decision = replace(decision, old_exit=reference.counted)",
                "pass",
            ),
            Mutant(
                "exit_closed_reason_dropped",
                "removed term",
                'decision = replace(decision, switch_reason="exit_closed")',
                "pass",
            ),
            Mutant(
                "reevaluate_fed_zero",
                "removed term",
                'current_fed = fed_state.get(agent_id, {}).get("cumulative", 0.0)',
                "current_fed = 0.0",
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "reevaluate_counts_not_moved",
                "removed term",
                "_move_count(exit_counts, _counted_before, rs.counted_exit)",
                "pass",
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "arrive_looked_node_kept",
                "removed term",
                'if wait_info.get("looked_node") not in (None, arrived):',
                "if False:",
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "flow_spawn_decision_skipped",
                "removed term",
                "if reroute_config is None or stage_graph is None or chosen is not None:",
                "if True:",
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "flow_spawn_position_stale",
                "removed term",
                'wait_info["current_position"] = extract_agent_xy(simulation.agent(agent_id))',
                "pass",
                module="pyfds_evac/core/scenario.py",
            ),
        ),
    ),
    "routing_cognitive_map": Area(
        module="pyfds_evac/core/cognitive_map.py",
        tests=(
            "tests/test_cognitive_map_hand_values.py",
            "tests/test_cognitive_map_history.py",
            "tests/test_cognitive_map_memory.py",
            "tests/test_scalar_familiarity.py",
            "tests/test_familiarity_routing.py",
            "tests/test_familiarity_no_journey.py",
            "tests/test_initial_exit_from_cognitive_map.py",
            "tests/test_initial_exit_per_agent.py",
            "tests/test_blind_spawn_discovery.py",
            "tests/test_no_known_exit.py",
            # Needs the webapp extra and exercises none of the mutated lines.
            "--deselect=tests/test_no_known_exit.py::TestRunModes::test_the_gui_refuses_the_form",
            "tests/verification/test_cognitive_map_verif.py",
        ),
        mutants=(
            Mutant(
                "expand_skips_visibility",
                "removed term",
                "            and not vis_model.node_is_visible(time_s, ax, ay, edge.target)\n",
                "",
            ),
            Mutant(
                "visibility_always_true",
                "removed term",
                "if vis_model.node_is_visible(time_s, ax, ay, tgt):",
                "if True:",
            ),
            Mutant(
                "familiarity_always_one",
                "removed term",
                "probability = familiarity_probability(familiarity)",
                "probability = 1.0",
            ),
            Mutant(
                "full_threshold_ge_to_gt",
                "reversed comparison",
                "if probability >= 1.0:",
                "if probability > 1.0:",
            ),
            Mutant(
                "arrival_full_return_dropped",
                "removed term",
                '    if cmap.familiarity == "full":\n'
                "        return\n"
                "    cmap.known_nodes.add(arrived_node)",
                "    cmap.known_nodes.add(arrived_node)",
            ),
            Mutant(
                "visibility_full_return_dropped",
                "removed term",
                '    if cmap.familiarity == "full":\n'
                "        return\n"
                "    _expand_visible",
                "    _expand_visible",
            ),
            Mutant(
                "subgraph_full_return_dropped",
                "removed term",
                '    if cmap.familiarity == "full":\n        return graph\n',
                "",
            ),
            Mutant(
                "familiarity_range_lower_open",
                "reversed comparison",
                "if not 0.0 <= probability <= 1.0:",
                "if not 0.0 < probability <= 1.0:",
            ),
            Mutant(
                "familiarity_range_upper_open",
                "reversed comparison",
                "if not 0.0 <= probability <= 1.0:",
                "if not 0.0 <= probability < 1.0:",
            ),
            Mutant(
                "draw_needs_positive_probability",
                "reversed comparison",
                "if rng is not None and probability > 0.0:",
                "if rng is not None and probability > 0.5:",
            ),
            Mutant(
                "draw_reversed",
                "reversed comparison",
                "and rng.random() < probability:",
                "and rng.random() > probability:",
            ),
            Mutant(
                "entrance_not_learned",
                "removed term",
                "if entrance is not None and entrance in graph.nodes:",
                "if False:",
            ),
            Mutant(
                "walked_leg_never_learned",
                "removed term",
                "if _has_edge(graph, from_node, arrived_node):",
                "if False:",
            ),
            Mutant(
                "reverse_edge_not_learned",
                "removed term",
                "if any(edge.target == source for edge in graph.edges.get(target, [])):",
                "if False:",
            ),
            Mutant(
                "initial_exit_map_ignored",
                "removed term",
                "        cognitive_map=cmap,\n        agent_position=agent_position,",
                "        cognitive_map=None,\n        agent_position=agent_position,",
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "initial_exit_familiarity_full",
                "removed term",
                'wait_info.get("familiarity", "full"),',
                '"full",',
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "initial_exit_position_dropped",
                "removed term",
                "        cognitive_map=cmap,\n        agent_position=agent_position,",
                "        cognitive_map=cmap,\n        agent_position=None,",
                module="pyfds_evac/core/scenario.py",
            ),
            Mutant(
                "initial_exit_map_not_stored",
                "removed term",
                "        cognitive_maps[agent_id] = cmap\n",
                "",
                module="pyfds_evac/core/scenario.py",
            ),
        ),
    ),
}


def _run_tests(python: str, tests: tuple[str, ...]) -> tuple[int, list[str]]:
    """Run the tests; return (pytest exit code, ids of failed tests)."""
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
    return proc.returncode, failed


def _outcome(returncode: int, failed: list[str]) -> str:
    """Classify a mutant's test run as survived, killed or invalid."""
    if returncode == 0:
        return "survived"
    if returncode == 1 and failed:
        return "killed"
    return "invalid"


def _check_mutant(
    m: Mutant, path: Path, original: str, python: str, tests: tuple[str, ...]
) -> str:
    """Apply one mutant, run the tests, restore; return the outcome."""
    path.write_text(original.replace(m.old, m.new))
    try:
        returncode, failed = _run_tests(python, tests)
    finally:
        path.write_text(original)
    outcome = _outcome(returncode, failed)
    status = {
        "survived": "SURVIVED",
        "killed": f"killed by {len(failed)}",
        "invalid": f"INVALID (pytest exit {returncode})",
    }[outcome]
    print(f"{m.name:32s} {m.kind:20s} {status}")
    for test_id in failed:
        print(f"    {test_id}")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("area", choices=sorted(AREAS))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    area = AREAS[args.area]
    paths = {m.name: REPO / (m.module or area.module) for m in area.mutants}
    originals = {path: path.read_text() for path in set(paths.values())}

    for m in area.mutants:
        if originals[paths[m.name]].count(m.old) != 1:
            print(f"{m.name}: snippet not found exactly once")
            return 2

    returncode, failed = _run_tests(args.python, area.tests)
    if returncode != 0:
        print(f"baseline fails, not mutating: {failed}")
        return 2

    outcomes = [
        _check_mutant(
            m, paths[m.name], originals[paths[m.name]], args.python, area.tests
        )
        for m in area.mutants
    ]

    for path, original in originals.items():
        assert path.read_text() == original
    killed = outcomes.count("killed")
    invalid = outcomes.count("invalid")
    print(f"\n{killed}/{len(area.mutants)} killed, {invalid} invalid")
    return 0 if killed == len(area.mutants) else 1


if __name__ == "__main__":
    sys.exit(main())
