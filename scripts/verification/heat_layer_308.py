"""Layer regime of the heat model against FDS gauges, geometric phi (#308).

``--heat-regime layer`` takes one view factor phi per run, but the FDS gauges
of ``assets/heat_radiometer/heat_radiometer_layer_308.fds`` differ in
position and orientation, so phi differs too
(``heat_layer_view_factor.py``: closed-form view factor from a gauge to the
base of the layer). The script therefore runs the CLI once per
(orientation, x) with that phi, on the scenario in
``assets/heat_radiometer_layer_308`` (seven stationary agents on the device
line), reads the agent at the device x, and compares its ``heat_flux_kw_m2``
with the FDS ``GAUGE HEAT FLUX GAS`` device of the same orientation and x at
t = 3, 6, 9 s. The compared band is |q_model / q_FDS - 1| <= 0.30 (the
radiant band of docs/testing-heat.md); a miss is a result, not a reason to
change phi, eps_L or the band.

Run from the repository root::

    python scripts/verification/heat_layer_308.py --fds-dir DIR --out OUT

``DIR`` is the FDS output of the deck (default
``$HEAT_RADIOMETER_DATA/layer_308``), ``OUT`` receives one FED history per
run, ``commands.txt`` and ``ratios.csv``.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import subprocess
import sys
from pathlib import Path

import heat_layer_view_factor as vf

from pyfds_evac.core.fed import STEFAN_BOLTZMANN_W_M2_K4 as SIGMA_MODEL

REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "assets" / "heat_radiometer_layer_308"
TIMES_S = (3.0, 6.0, 9.0)
BAND = 0.30
LAYER_HEIGHT_M = 2.5
HEAD_HEIGHT_M = 1.6
SEED = 42
EXIT_INCOMPLETE = 2  # pyfds_evac.cli: time limit reached, agents stationary
T_TOL = 0.02  # slice against device, as in test_heat_integrated_intensity_coupled
HAND_TOL = 1e-6  # kW/m2, model flux against the hand formula from its samples
COLUMNS = (
    "orientation x_m t_s phi q_expected_kw q_model_kw q_fds_kw ratio within_band rad_fds_kw "
    "phi_eff t_layer_model_c t_layer_devc_c t_gas_model_c t_gas_devc_c "
    "hand_diff_kw"
).split()


def cli_args(fds_dir: Path, history: Path, phi: float) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pyfds_evac.cli",
        "--scenario",
        str(SCENARIO),
        "--seed",
        str(SEED),
        "--fds-dir",
        str(fds_dir),
        "--enable-heat-fed",
        "--heat-fed-method",
        "total-flux",
        "--heat-regime",
        "layer",
        "--heat-layer-height",
        str(LAYER_HEIGHT_M),
        "--heat-view-factor",
        f"{phi:.10f}",
        "--heat-layer-emissivity",
        str(vf.EPS_L),
        "--heat-convective-coefficient",
        str(vf.H_W_M2K),
        "--heat-skin-temperature",
        str(vf.T_SKIN_C),
        "--output-fed-history",
        str(history),
    ]


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def read_devc(path: Path) -> dict[str, list[float]]:
    """FDS ``_devc.csv`` (units row, then names) as columns."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    names = rows[1]
    cols = list(zip(*rows[2:]))
    return {n: [float(v) for v in c] for n, c in zip(names, cols)}


def devc_at(dev: dict[str, list[float]], name: str, t_s: float) -> float:
    times = dev["Time"]
    for i in range(1, len(times)):
        if times[i] >= t_s:
            w = (t_s - times[i - 1]) / (times[i] - times[i - 1])
            return dev[name][i - 1] + w * (dev[name][i] - dev[name][i - 1])
    raise ValueError(f"t={t_s} s is past the device record ({times[-1]} s)")


def agent_rows(history: Path, x_m: float) -> dict[float, dict[str, float]]:
    """Rows of the agent nearest x_m at t = 0, keyed by time."""
    header, rows = read_csv(history)
    col = {n: i for i, n in enumerate(header)}
    first: dict[str, float] = {}
    for r in rows:
        first.setdefault(r[col["agent_id"]], float(r[col["x"]]))
    agent = min(first, key=lambda a: abs(first[a] - x_m))
    if abs(first[agent] - x_m) > 0.05:
        raise ValueError(f"no agent within 0.05 m of x={x_m} in {history}")
    out = {}
    for r in rows:
        if r[col["agent_id"]] != agent:
            continue
        out[float(r[col["time_s"]])] = {
            "q": float(r[col["heat_flux_kw_m2"]]),
            "t_layer": float(r[col["heat_layer_temperature_c"]]),
            "t_gas": float(r[col["temperature_celsius"]]),
        }
    return out


def compare_run(history: Path, dev: dict, orientation: str, k: int) -> list[dict]:
    x = vf.GAUGE_X_M[k - 1]
    phi = vf.view_factor(x, orientation)
    rows = agent_rows(history, x)
    out = []
    for t in TIMES_S:
        m = rows[min(rows, key=lambda s: abs(s - t))]
        q_fds = devc_at(dev, f"GAUGE_z16_{orientation}-{k}", t)
        rad = vf.radiant_kw(m["t_layer"], sigma=SIGMA_MODEL)
        conv = vf.H_W_M2K * (m["t_gas"] - vf.T_SKIN_C) / 1000.0
        ratio = m["q"] / q_fds
        out.append(
            {
                "orientation": orientation,
                "x_m": x,
                "t_s": t,
                "phi": phi,
                "q_expected_kw": vf.flux_kw(phi, devc_at(dev, f"T_z16-{k}", t)),
                "q_model_kw": m["q"],
                "q_fds_kw": q_fds,
                "ratio": ratio,
                "within_band": abs(ratio - 1.0) <= BAND,
                "rad_fds_kw": devc_at(dev, f"RAD_z16_{orientation}-{k}", t),
                "phi_eff": (q_fds - conv) / (vf.EPS_L * rad),
                "t_layer_model_c": m["t_layer"],
                "t_layer_devc_c": devc_at(dev, f"T_z25-{k}", t),
                "t_gas_model_c": m["t_gas"],
                "t_gas_devc_c": devc_at(dev, f"T_z16-{k}", t),
                "hand_diff_kw": m["q"]
                - vf.flux_kw(phi, m["t_gas"], m["t_layer"], SIGMA_MODEL),
            }
        )
    return out


def run_all(fds_dir: Path, out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = read_devc(fds_dir / "heat_radiometer_layer_308_devc.csv")
    results, commands = [], []
    for orientation in vf.ORIENTATIONS:
        for k, x in enumerate(vf.GAUGE_X_M, start=1):
            history = out_dir / f"fed_{orientation}_k{k}.csv"
            args = cli_args(fds_dir, history, vf.view_factor(x, orientation))
            commands.append(" ".join(args))
            done = subprocess.run(args, capture_output=True, text=True, cwd=REPO)
            if done.returncode not in (0, EXIT_INCOMPLETE):
                raise RuntimeError(
                    f"pyfds-evac exited {done.returncode} for {orientation} k={k}: "
                    f"{done.stderr[-500:]}"
                )
            results += compare_run(history, dev, orientation, k)
    (out_dir / "commands.txt").write_text("\n".join(commands) + "\n")
    with open(out_dir / "ratios.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in results:
            w.writerow(
                {c: (f"{v:.6g}" if isinstance(v, float) else v) for c, v in r.items()}
            )
    return results


def summarize(results: list[dict]) -> str:
    lines = ["orientation  t_s  n  within_band  ratio min / median / max"]
    for o in vf.ORIENTATIONS:
        for t in TIMES_S:
            sel = sorted(
                r["ratio"] for r in results if r["orientation"] == o and r["t_s"] == t
            )
            ok = sum(abs(v - 1) <= BAND for v in sel)
            lines.append(
                f"{o:>11}  {t:3.0f}  {len(sel)}  {ok}/{len(sel)}  "
                f"{sel[0]:.3f} / {sel[len(sel) // 2]:.3f} / {sel[-1]:.3f}"
            )
    return "\n".join(lines)


def main() -> None:
    default = Path(os.environ.get("HEAT_RADIOMETER_DATA", "")) / "layer_308"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fds-dir", type=Path, default=default)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    results = run_all(args.fds_dir, args.out)
    print(summarize(results))
    print(
        "worst hand-formula difference [kW/m2]:",
        max(abs(r["hand_diff_kw"]) for r in results),
    )
    print(
        "worst T_layer rel diff:",
        max(abs(r["t_layer_model_c"] / r["t_layer_devc_c"] - 1) for r in results),
    )
    print(
        "worst T_gas rel diff:",
        max(abs(r["t_gas_model_c"] / r["t_gas_devc_c"] - 1) for r in results),
    )
    if not all(math.isfinite(r["ratio"]) for r in results):
        raise SystemExit("non-finite ratio")


if __name__ == "__main__":
    main()
