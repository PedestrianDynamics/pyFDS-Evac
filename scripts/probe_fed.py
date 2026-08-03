"""Probe FED accumulation at fixed points of an FDS case.

Integrate the ISO 13571 FED model at one or more ``(x, y)`` probes over
the FDS simulation's time axis.  Useful as a sanity check before
running evacuation simulations: answers "if an agent stood still at
this point the whole time, what FED would it accumulate?".

Examples::

    # Peak FED and time-to-incapacitation at a single junction point
    uv run python scripts/probe_fed.py \\
        --fds-dir fds_directory/demo --point 17,12

    # Multi-point probe with CSV timeseries and PNG plot
    uv run python scripts/probe_fed.py --fds-dir fds_directory/demo \\
        --point 17,12 --point 20,12 --point 22,1 \\
        --output probe_fed.csv --plot probe_fed.png
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from pyfds_evac.core import DefaultFedConfig, DefaultFedModel, FdsFedField
from pyfds_evac.core.fed import default_fic


def _parse_point(raw: str) -> tuple[float, float]:
    """Parse a 'x,y' string into a float tuple."""
    parts = raw.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Point must be 'x,y', got {raw!r}")
    return float(parts[0]), float(parts[1])


def _fds_time_axis(field: FdsFedField) -> tuple[float, float]:
    """Return (t_min, t_max) from the CO slice's native time points."""
    slice_obj = field._co._slice  # one required sampler; all share the axis
    times = slice_obj.times
    return float(times[0]), float(times[-1])


def _probe(
    field: FdsFedField,
    model: DefaultFedModel,
    *,
    x: float,
    y: float,
    t_start: float,
    t_end: float,
    dt: float,
) -> list[dict[str, float]]:
    """Integrate FED at one probe point and return one row per sample."""
    rows: list[dict[str, float]] = []
    t = float(t_start)
    cumulative = 0.0
    while t <= t_end + 1e-9:
        try:
            inputs, components, cumulative = model.advance_with_components(
                t, x, y, dt_s=dt, current_fed=cumulative
            )
        except ValueError:
            t += dt
            continue
        rows.append(
            {
                "time_s": t,
                "x": x,
                "y": y,
                "co_ppm": 10000.0 * inputs.co_volume_fraction_percent,
                "co2_percent": inputs.co2_volume_fraction_percent,
                "o2_percent": inputs.o2_volume_fraction_percent,
                "hcn_ppm": inputs.hcn_ppm,
                "fed_rate_per_min": components.total_rate_per_min,
                "fed_cumulative": cumulative,
                "fic": default_fic(inputs),
            }
        )
        t += dt
    return rows


def _summarise(rows: list[dict[str, float]], threshold: float) -> dict[str, float]:
    """Reduce a probe's timeseries to peak FED, time-to-threshold, peak rate."""
    if not rows:
        return {
            "samples": 0,
            "peak_fed": 0.0,
            "peak_rate_per_min": 0.0,
            "t_to_threshold_s": float("inf"),
        }
    peak_fed = max(r["fed_cumulative"] for r in rows)
    peak_rate = max(r["fed_rate_per_min"] for r in rows)
    t_to_threshold = float("inf")
    for r in rows:
        if r["fed_cumulative"] >= threshold:
            t_to_threshold = r["time_s"]
            break
    return {
        "samples": len(rows),
        "peak_fed": peak_fed,
        "peak_rate_per_min": peak_rate,
        "t_to_threshold_s": t_to_threshold,
    }


def _write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    """Write all probe rows to a single CSV (concatenated, point in columns)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _plot(path: Path, per_point: dict[str, list[dict[str, float]]]) -> None:
    """Save a two-panel plot: cumulative FED (top) and rate (bottom) per probe."""
    import matplotlib.pyplot as plt

    fig, (ax_cum, ax_rate) = plt.subplots(
        2, 1, sharex=True, figsize=(9, 6), constrained_layout=True
    )
    for label, rows in per_point.items():
        t = [r["time_s"] for r in rows]
        ax_cum.plot(t, [r["fed_cumulative"] for r in rows], label=label, linewidth=1.2)
        ax_rate.plot(
            t, [r["fed_rate_per_min"] for r in rows], label=label, linewidth=1.2
        )
    ax_cum.axhline(1.0, color="#c0392b", linestyle="--", linewidth=1.0, label="FED=1")
    ax_cum.set_ylabel("Cumulative FED")
    ax_cum.grid(True, alpha=0.3)
    ax_cum.legend(loc="upper left", fontsize=9)
    ax_rate.set_ylabel("FED rate (1/min)")
    ax_rate.set_xlabel("time (s)")
    ax_rate.grid(True, alpha=0.3)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fds-dir", required=True, help="FDS case directory")
    parser.add_argument(
        "--point",
        action="append",
        required=True,
        type=_parse_point,
        metavar="X,Y",
        help="Probe point (repeatable)",
    )
    parser.add_argument(
        "--dt", type=float, default=1.0, help="Integration step in seconds (default 1)"
    )
    parser.add_argument("--t-start", type=float, default=None)
    parser.add_argument("--t-end", type=float, default=None)
    parser.add_argument(
        "--slice-height", type=float, default=2.0, help="Slice height in metres"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="FED threshold for time-to-incapacitation reporting",
    )
    parser.add_argument("--output", type=Path, help="Write per-sample CSV here")
    parser.add_argument("--plot", type=Path, help="Write a PNG plot here")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    field = FdsFedField.from_fds(args.fds_dir)
    model = DefaultFedModel(
        field,
        DefaultFedConfig(fds_dir=args.fds_dir, slice_height_m=args.slice_height),
    )

    t_min, t_max = _fds_time_axis(field)
    t_start = args.t_start if args.t_start is not None else t_min
    t_end = args.t_end if args.t_end is not None else t_max
    print(
        f"FDS time axis: [{t_min:.1f}, {t_max:.1f}] s (probing {t_start:.1f}-{t_end:.1f})"
    )

    all_rows: list[dict[str, float]] = []
    per_point: dict[str, list[dict[str, float]]] = {}
    print(
        f"{'point':>12}  {'peak FED':>10}  {'peak rate':>11}  {'t(FED=threshold)':>18}"
    )
    for x, y in args.point:
        rows = _probe(field, model, x=x, y=y, t_start=t_start, t_end=t_end, dt=args.dt)
        summary = _summarise(rows, threshold=args.threshold)
        label = f"({x:g}, {y:g})"
        per_point[label] = rows
        all_rows.extend(rows)
        t_str = (
            f"{summary['t_to_threshold_s']:.1f} s"
            if summary["t_to_threshold_s"] != float("inf")
            else "not reached"
        )
        print(
            f"{label:>12}  {summary['peak_fed']:10.4f}  "
            f"{summary['peak_rate_per_min']:11.4f}  {t_str:>18}"
        )

    if args.output:
        _write_csv(args.output, all_rows)
        print(f"Wrote {len(all_rows)} rows to {args.output}")
    if args.plot:
        _plot(args.plot, per_point)
        print(f"Wrote {args.plot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
