import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot smoke speed history CSV.")
    parser.add_argument("--input", required=True, help="Smoke history CSV path")
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument(
        "--agent-id",
        type=int,
        help="Optional agent id for a single-agent plot; defaults to aggregate plot",
    )
    return parser


def _read_rows(path: str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _plot_aggregate(rows: list[dict[str, str]], output: str) -> None:
    grouped: dict[float, list[dict[str, float]]] = defaultdict(list)
    for row in rows:
        grouped[float(row["time_s"])].append(
            {
                "desired_speed": float(row["desired_speed"]),
                "speed_factor": float(row["speed_factor"]),
                "extinction_per_m": float(row["extinction_per_m"]),
            }
        )

    times = sorted(grouped)
    mean_desired_speed = [
        sum(item["desired_speed"] for item in grouped[t]) / len(grouped[t])
        for t in times
    ]
    mean_speed = [
        sum(item["speed_factor"] for item in grouped[t]) / len(grouped[t])
        for t in times
    ]
    mean_extinction = [
        sum(item["extinction_per_m"] for item in grouped[t]) / len(grouped[t])
        for t in times
    ]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax1.plot(times, mean_desired_speed, label="Mean desired speed", color="tab:green")
    ax1.plot(times, mean_speed, label="Mean speed factor", color="tab:blue")
    ax1.set_ylabel("Speed / factor")
    ax1.legend(loc="best")

    ax2.plot(times, mean_extinction, label="Mean extinction", color="tab:red")
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Extinction K [1/m]")
    ax2.legend(loc="best")

    fig.suptitle("Smoke-speed history (aggregate)")
    fig.tight_layout()
    fig.savefig(output, dpi=200, bbox_inches="tight")


def _plot_agent(rows: list[dict[str, str]], agent_id: int, output: str) -> None:
    selected = [row for row in rows if int(row["agent_id"]) == agent_id]
    if not selected:
        raise ValueError(f"No rows found for agent_id={agent_id}")
    times = [float(row["time_s"]) for row in selected]
    desired_speed = [float(row["desired_speed"]) for row in selected]
    base_speed = [float(row["base_speed"]) for row in selected]
    speed = [float(row["speed_factor"]) for row in selected]
    extinction = [float(row["extinction_per_m"]) for row in selected]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax1.plot(times, desired_speed, label="Desired speed", color="tab:green")
    ax1.plot(times, base_speed, label="Base speed", color="tab:gray", linestyle="--")
    ax1.plot(times, speed, label="Speed factor", color="tab:blue")
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel("Speed / factor")
    ax1.legend(loc="best")

    ax2.plot(times, extinction, label="Extinction", color="tab:red")
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Extinction K [1/m]")
    ax2.legend(loc="best")

    fig.suptitle(f"Smoke-speed history (agent {agent_id})")
    fig.tight_layout()
    fig.savefig(output, dpi=200, bbox_inches="tight")


def main() -> int:
    args = _build_parser().parse_args()
    rows = _read_rows(args.input)
    if args.agent_id is None:
        _plot_aggregate(rows, args.output)
    else:
        _plot_agent(rows, args.agent_id, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
