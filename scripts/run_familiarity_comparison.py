"""Phase 2 verification: compare full vs discovery familiarity tiers.

Runs two scenarios back-to-back (same FDS data, same seed) and produces
a 3-panel comparison figure:

  Panel 1 — Exit choice split (bar chart, A vs B per tier)
  Panel 2 — Route rejections over time (visibility-gated, per tier)
  Panel 3 — Egress summary (evacuation time, agents evacuated)

Outputs:
  results/familiarity_comparison/
    full_route_costs.csv
    discovery_route_costs.csv
    full_routes.csv
    discovery_routes.csv
    comparison.png

Usage:
    uv run python scripts/run_familiarity_comparison.py \\
        --fds-dir fds_data/demo \\
        --vis-cache fds_data/demo/vismap_cache.pkl
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pyfds_evac.core import (
    ExtinctionField,
    RerouteConfig,
    RouteCostConfig,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)
from pyfds_evac.core.visibility import VisibilityModel, _extract_sign_descriptors

CONFIGS = {
    "full": Path("assets/demo/config_full.json"),
    "discovery": Path("assets/demo/config_discovery.json"),
}
FDS_DIR_DEFAULT = Path("fds_data/demo")
VIS_CACHE_DEFAULT = Path("fds_data/demo/vismap_cache.pkl")
OUT_DIR = Path("results/familiarity_comparison")
SEED = 42
REROUTE_INTERVAL_S = 10.0


def build_smoke_model(fds_dir: Path, interval_s: float, height_m: float):
    cfg = SmokeSpeedConfig(
        fds_dir=str(fds_dir),
        update_interval_s=interval_s,
        slice_height_m=height_m,
    )
    field = ExtinctionField.from_fds(str(fds_dir), slice_height_m=height_m)
    return SmokeSpeedModel(field, cfg)


def build_reroute_config(scenario_raw: dict) -> RerouteConfig:
    rp = scenario_raw.get("routing", {})
    cost = RouteCostConfig(
        w_smoke=rp.get("w_smoke", 1.0),
        w_fed=rp.get("w_fed", 10.0),
        w_queue=rp.get("w_queue", 0.0),
        fed_rejection_threshold=rp.get("fed_rejection_threshold", 1.0),
        visibility_extinction_threshold=rp.get("visibility_extinction_threshold", 0.5),
        sampling_step_m=rp.get("sampling_step_m", 2.0),
        base_speed_m_per_s=rp.get("base_speed_m_per_s", 1.3),
        default_exit_capacity=rp.get("default_exit_capacity", 1.3),
    )
    return RerouteConfig(
        reevaluation_interval_s=REROUTE_INTERVAL_S,
        cost_config=cost,
    )


def run_tier(
    label: str,
    config_path: Path,
    fds_dir: Path,
    vis_cache: Path | None,
    smoke_height_m: float,
) -> dict:
    print(f"\n{'=' * 60}")
    print(f"Running tier: {label}  ({config_path.name})")
    print(f"{'=' * 60}")

    scenario = load_scenario(str(config_path))
    smoke_model = build_smoke_model(fds_dir, REROUTE_INTERVAL_S, smoke_height_m)
    reroute_cfg = build_reroute_config(scenario.raw)

    vis_model = None
    if vis_cache is not None:
        signs = _extract_sign_descriptors(scenario.raw)
        if signs:
            vis_model = VisibilityModel(
                fds_dir=str(fds_dir),
                sign_descriptors=signs,
                cache_path=str(vis_cache),
                time_step_s=REROUTE_INTERVAL_S,
                slice_height_m=smoke_height_m,
            )

    result = run_scenario(
        scenario,
        seed=SEED,
        smoke_speed_model=smoke_model,
        reroute_config=reroute_cfg,
        collect_route_cost_history=True,
        vis_model=vis_model,
    )
    print(
        f"  Evacuated {result.agents_evacuated}/{result.total_agents} "
        f"in {result.evacuation_time:.1f} s  "
        f"({result.agents_remaining} remaining)"
    )
    return {
        "label": label,
        "evacuation_time": result.evacuation_time,
        "agents_evacuated": result.agents_evacuated,
        "total_agents": result.total_agents,
        "agents_remaining": result.agents_remaining,
        "route_cost_history": result.route_cost_history or [],
        "route_history": result.route_history or [],
    }


def save_csvs(results: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        label = r["label"]
        if r["route_cost_history"]:
            pd.DataFrame(r["route_cost_history"]).to_csv(
                out_dir / f"{label}_route_costs.csv", index=False
            )
        if r["route_history"]:
            pd.DataFrame(r["route_history"]).to_csv(
                out_dir / f"{label}_routes.csv", index=False
            )


def plot_comparison(results: list[dict], out_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fig.suptitle("Phase 2 verification: full vs discovery familiarity", fontsize=11)

    colors = {"full": "#1976D2", "discovery": "#F57C00"}

    # ── Panel 1: exit choice split ────────────────────────────────────────────
    ax = axes[0]
    exits = ["exit_A_left", "exit_B_right"]
    exit_labels = ["Exit A", "Exit B"]
    x = range(len(exits))
    width = 0.35

    for i, r in enumerate(results):
        label = r["label"]
        rc = pd.DataFrame(r["route_cost_history"])
        if rc.empty:
            counts = [0, 0]
        else:
            # Count per-agent final exit choice: last non-rejected rank-1 route
            # Use route switches if available, else first-seen exit per agent
            rh = pd.DataFrame(r["route_history"])
            if not rh.empty:
                # Last switch gives final exit choice
                final = rh.groupby("agent_id")["new_exit"].last()
            else:
                # No switches — use initial exit from cost history rank-1
                rank1 = rc[rc["route_rank"] == 1].drop_duplicates(
                    subset="agent_id", keep="first"
                )
                final = rank1.set_index("agent_id")["exit_id"]

            counts = [(final == e).sum() for e in exits]

        offset = (i - 0.5) * width
        bars = ax.bar(
            [xi + offset for xi in x],
            counts,
            width=width,
            label=label,
            color=colors.get(label, "gray"),
            alpha=0.85,
        )
        for bar, count in zip(bars, counts):
            if count > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1,
                    str(count),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

    ax.set_xticks(list(x))
    ax.set_xticklabels(exit_labels)
    ax.set_ylabel("Agents")
    ax.set_title("Exit choice split")
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0)

    # ── Panel 2: rejection events over time ───────────────────────────────────
    ax = axes[1]
    for r in results:
        rc = pd.DataFrame(r["route_cost_history"])
        if rc.empty:
            continue
        rejected = rc[
            rc["rejected"] & (rc["rejection_reason"] == "next_node_not_visible")
        ]
        if rejected.empty:
            continue
        # Count per time bin
        bins = range(0, int(rc["time_s"].max()) + 11, 10)
        ts = rejected.groupby(
            pd.cut(rejected["time_s"], bins=list(bins), right=False)
        ).size()
        ax.step(
            [iv.left for iv in ts.index],
            ts.values,
            where="post",
            label=r["label"],
            color=colors.get(r["label"], "gray"),
            lw=2,
        )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Rejection events")
    ax.set_title("Visibility-gated rejections over time")
    ax.legend(fontsize=8)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    # ── Panel 3: egress summary ───────────────────────────────────────────────
    ax = axes[2]
    labels = [r["label"] for r in results]
    evac_times = [r["evacuation_time"] for r in results]
    bar_colors = [colors.get(lbl, "gray") for lbl in labels]
    bars = ax.bar(labels, evac_times, color=bar_colors, alpha=0.85)
    for bar, t in zip(bars, evac_times):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{t:.0f} s",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylabel("Evacuation time (s)")
    ax.set_title("Total evacuation time")
    ax.set_ylim(bottom=0)
    for r in results:
        frac = (
            r["agents_evacuated"] / r["total_agents"] * 100
            if r["total_agents"] > 0
            else 0
        )
        print(
            f"  {r['label']:12s}: {r['agents_evacuated']}/{r['total_agents']} "
            f"({frac:.0f}%) evacuated in {r['evacuation_time']:.1f} s"
        )

    fig.tight_layout()
    out_path = out_dir / "comparison.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nSaved → {out_path}")
    plt.show()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fds-dir",
        default=str(FDS_DIR_DEFAULT),
        help="FDS result directory",
    )
    parser.add_argument(
        "--vis-cache",
        default=str(VIS_CACHE_DEFAULT),
        help="Vismap pickle cache path (created if missing)",
    )
    parser.add_argument(
        "--no-vis",
        action="store_true",
        help="Disable visibility model (Phase 1 off)",
    )
    parser.add_argument(
        "--smoke-height",
        type=float,
        default=2.0,
        help="FDS slice height in metres",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        default=["full", "discovery"],
        choices=["full", "discovery"],
        help="Which tiers to run",
    )
    args = parser.parse_args()

    fds_dir = Path(args.fds_dir)
    vis_cache = None if args.no_vis else Path(args.vis_cache)

    results = []
    for tier in args.tiers:
        r = run_tier(
            label=tier,
            config_path=CONFIGS[tier],
            fds_dir=fds_dir,
            vis_cache=vis_cache,
            smoke_height_m=args.smoke_height,
        )
        results.append(r)

    save_csvs(results, OUT_DIR)
    plot_comparison(results, OUT_DIR)


if __name__ == "__main__":
    main()
