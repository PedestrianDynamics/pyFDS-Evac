"""Inspect an FDS simulation directory and report quantities relevant to evacuation.

Checks availability and time-series statistics for:
  - Soot extinction coefficient  (drives smoke-speed model)
  - Visibility                   (drives route rejection)
  - CO, CO2, O2                  (required for FED)
  - HCN, HCl                     (optional FED species)

Usage:
    uv run python scripts/inspect_fds.py fds_data/demo
    uv run python scripts/inspect_fds.py fds_data/demo --plot
    uv run python scripts/inspect_fds.py fds_data/demo --height 2.0 --plot
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np

try:
    from fdsreader import Simulation
except ModuleNotFoundError:
    print("ERROR: fdsreader is not installed. Run: uv add fdsreader")
    sys.exit(1)


# Quantities relevant for evacuation, with display info
QUANTITIES = [
    {
        "fds_name": "Soot extinction coefficient",
        "label": "Extinction K",
        "unit": "1/m",
        "threshold": 0.5,
        "threshold_label": "visibility threshold (K=0.5)",
        "color": "gray",
    },
    {
        "fds_name": "Visibility",
        "label": "Visibility",
        "unit": "m",
        "threshold": None,
        "color": "steelblue",
    },
    {
        "fds_name": "Carbon monoxide volume fraction",
        "label": "CO",
        "unit": "% vol",
        "scale": 100.0,
        "threshold": 0.014,
        "threshold_label": "IDLH (0.014%)",
        "color": "tab:red",
    },
    {
        "fds_name": "Carbon dioxide volume fraction",
        "label": "CO₂",
        "unit": "% vol",
        "scale": 100.0,
        "threshold": 5.0,
        "threshold_label": "IDLH (5%)",
        "color": "tab:orange",
    },
    {
        "fds_name": "Oxygen volume fraction",
        "label": "O₂",
        "unit": "% vol",
        "scale": 100.0,
        "threshold": 16.0,
        "threshold_label": "impairment (<16%)",
        "color": "tab:green",
        "invert": True,  # danger is low O2
    },
    {
        "fds_name": "Hydrogen cyanide volume fraction",
        "label": "HCN",
        "unit": "ppm",
        "scale": 1e6,
        "threshold": 50,
        "threshold_label": "IDLH (50 ppm)",
        "color": "tab:purple",
    },
    {
        "fds_name": "Hydrogen chloride volume fraction",
        "label": "HCl",
        "unit": "ppm",
        "scale": 1e6,
        "threshold": 50,
        "threshold_label": "IDLH (50 ppm)",
        "color": "tab:brown",
    },
]


@dataclass
class QuantityStats:
    name: str
    label: str
    unit: str
    times: np.ndarray
    peak: np.ndarray  # max over spatial domain at each time step
    mean: np.ndarray  # mean over spatial domain at each time step
    global_max: float
    global_mean_at_peak: float
    scale: float = 1.0


def _load_quantity(sim, fds_name: str, height: float | None) -> object | None:
    """Return the best matching slice object, or None if not found."""
    try:
        matches = sim.slices.filter_by_quantity(fds_name)
    except Exception:
        return None
    if not matches:
        return None
    if height is not None and len(matches) > 1:
        return min(
            matches,
            key=lambda s: abs((s.extent.z_start + s.extent.z_end) / 2 - height),
        )
    return matches[0]


def _extract_stats(slice_obj, scale: float) -> QuantityStats | None:
    """Compute peak and mean over the spatial domain for each time step."""
    try:
        subslices = list(slice_obj.subslices)
        times = np.array(slice_obj.times, dtype=float)
        n_times = len(times)

        peak = np.zeros(n_times)
        mean_vals = np.zeros(n_times)

        for t_idx in range(n_times):
            all_values = []
            for sub in subslices:
                data = sub.data[t_idx]  # shape: (i, j)
                all_values.append(data.ravel())
            flat = np.concatenate(all_values) * scale
            peak[t_idx] = flat.max()
            mean_vals[t_idx] = flat.mean()

        global_max = float(peak.max())
        peak_t_idx = int(peak.argmax())
        global_mean_at_peak = float(mean_vals[peak_t_idx])

        return times, peak, mean_vals, global_max, global_mean_at_peak
    except Exception as e:
        print(f"  Warning: could not extract stats: {e}")
        return None


def inspect(fds_dir: str, height: float = 2.0, plot: bool = False) -> None:
    print(f"\nLoading FDS simulation: {fds_dir}")
    sim = Simulation(fds_dir)

    # Show all available slice quantities
    try:
        all_quantities = sorted(
            {str(getattr(q, "name", q)) for q in getattr(sim.slices, "quantities", [])}
        )
    except Exception:
        all_quantities = []

    print(f"\nAvailable slice quantities ({len(all_quantities)}):")
    for q in all_quantities:
        print(f"  - {q}")

    print(f"\nAnalysing key quantities at z ≈ {height} m:")
    print(
        f"{'Quantity':<12} {'Unit':<8} {'Global max':>12} {'Mean@peak':>12} {'Status'}"
    )
    print("-" * 60)

    results: list[tuple[dict, QuantityStats]] = []

    for qinfo in QUANTITIES:
        label = qinfo["label"]
        unit = qinfo["unit"]
        scale = qinfo.get("scale", 1.0)

        slice_obj = _load_quantity(sim, qinfo["fds_name"], height)
        if slice_obj is None:
            print(f"  {label:<12} {'':>8} {'':>12} {'':>12}  NOT FOUND")
            continue

        out = _extract_stats(slice_obj, scale)
        if out is None:
            print(f"  {label:<12} {'':>8} {'':>12} {'':>12}  ERROR")
            continue

        times, peak, mean_vals, global_max, global_mean_at_peak = out

        # Status assessment
        threshold = qinfo.get("threshold")
        invert = qinfo.get("invert", False)
        if threshold is not None:
            if invert:
                danger = global_max < threshold  # low O2 is dangerous
            else:
                danger = global_max > threshold
            status = "⚠  exceeds threshold" if danger else "ok (below threshold)"
        else:
            status = "ok"

        if global_max < 1e-9:
            status = "✗  zero / no data"

        stats = QuantityStats(
            name=qinfo["fds_name"],
            label=label,
            unit=unit,
            times=times,
            peak=peak,
            mean=mean_vals,
            global_max=global_max,
            global_mean_at_peak=global_mean_at_peak,
            scale=scale,
        )
        results.append((qinfo, stats))

        print(
            f"  {label:<12} {unit:<8} {global_max:>12.4f} {global_mean_at_peak:>12.4f}  {status}"
        )

    # FED readiness summary
    print("\nFED readiness:")
    co_ok = any(r[1].global_max > 1e-9 for r in results if r[0]["label"] == "CO")
    co2_ok = any(r[1].global_max > 1e-9 for r in results if r[0]["label"] == "CO₂")
    o2_ok = any(r[1].global_max > 1e-9 for r in results if r[0]["label"] == "O₂")

    if co_ok and co2_ok and o2_ok:
        print("  ✓ CO / CO2 / O2 all present and non-zero → default FED model will run")
    else:
        missing = [
            name
            for name, ok in [("CO", co_ok), ("CO2", co2_ok), ("O2", o2_ok)]
            if not ok
        ]
        print(f"  ✗ Missing or zero: {', '.join(missing)} → FED will be negligible")

    smoke_ok = any(
        r[1].global_max > 1e-9 for r in results if r[0]["label"] == "Extinction K"
    )
    print(
        f"  {'✓' if smoke_ok else '✗'} Extinction coefficient → smoke-speed model {'will' if smoke_ok else 'will NOT'} run"
    )

    if not plot:
        return

    import matplotlib.pyplot as plt

    n = len(results)
    if n == 0:
        print("No data to plot.")
        return

    cols = 2
    rows = (n + 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(12, 3 * rows), sharex=False)
    axes = np.array(axes).ravel()

    for ax, (qinfo, stats) in zip(axes, results):
        color = qinfo.get("color", "tab:blue")
        ax.plot(stats.times, stats.peak, color=color, lw=2, label="spatial max")
        ax.fill_between(stats.times, stats.mean, stats.peak, alpha=0.2, color=color)
        ax.plot(
            stats.times, stats.mean, color=color, lw=1, ls="--", label="spatial mean"
        )

        threshold = qinfo.get("threshold")
        if threshold is not None:
            ax.axhline(
                threshold,
                color="red",
                lw=1,
                ls=":",
                label=qinfo.get("threshold_label", f"threshold={threshold}"),
            )

        ax.set_title(f"{stats.label} [{stats.unit}]")
        ax.set_xlabel("Time (s)")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    # hide unused axes
    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle(f"FDS inspection: {fds_dir}", fontsize=11)
    fig.tight_layout()

    import pathlib

    out_path = pathlib.Path(fds_dir) / "fds_inspection.png"
    fig.savefig(out_path, dpi=150)
    print(f"\nPlot saved: {out_path}")
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("fds_dir", help="Path to FDS simulation directory")
    parser.add_argument(
        "--height",
        type=float,
        default=2.0,
        help="Slice height in metres (default: 2.0)",
    )
    parser.add_argument("--plot", action="store_true", help="Generate and save plots")
    args = parser.parse_args()

    inspect(args.fds_dir, height=args.height, plot=args.plot)


if __name__ == "__main__":
    main()
