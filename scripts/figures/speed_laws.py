"""Speed factor against extinction: Frantzich–Nilsson (Lund) and Fridolf et al. (2019).

The curves are computed through the public API (``SmokeSpeedModel`` on a
``ConstantExtinctionField``), so the figure follows the code's defaults.

Run from the repository root::

    .venv/bin/python scripts/figures/speed_laws.py

Writes ``site/static/images/concepts/speed_laws.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pyfds_evac import ConstantExtinctionField, SmokeSpeedConfig, SmokeSpeedModel

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"


def style(ax):
    """Despine, no grid, dimgrey ticks."""
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")


def speed_factors(k_values, config):
    """Speed factor v/v0 at each extinction K [1/m] for one configuration."""
    return np.array(
        [
            SmokeSpeedModel(ConstantExtinctionField(float(k)), config).speed_factor(
                0.0, 0.0, 0.0
            )
            for k in k_values
        ]
    )


def main():
    """Render speed_laws.png into site/static/images/concepts."""
    plt.rcParams["font.family"] = "DejaVu Sans"
    blue, orange, grey = "#023d6b", "#e4661b", "#9aa5b1"
    OUT.mkdir(parents=True, exist_ok=True)

    lund_cfg = SmokeSpeedConfig()
    k = np.linspace(0.0, 12.0, 481)
    lund = speed_factors(k, lund_cfg)
    frid3 = speed_factors(
        k, SmokeSpeedConfig(speed_law="fridolf", visibility_factor_c=3.0)
    )
    frid8 = speed_factors(
        k, SmokeSpeedConfig(speed_law="fridolf", visibility_factor_c=8.0)
    )
    fmin = lund_cfg.min_speed_factor
    ksat = lund_cfg.alpha * (1 - fmin) / (-lund_cfg.beta)

    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=120)
    style(ax)
    ax.plot(k, lund, color=blue, lw=2.6, label="Frantzich–Nilsson (default)")
    ax.plot(k, frid3, color=orange, lw=2.0, label="Fridolf, C = 3 (reflective sign)")
    ax.plot(
        k,
        frid8,
        color=orange,
        lw=2.0,
        ls="--",
        label="Fridolf, C = 8 (light-emitting sign)",
    )
    ax.axhline(fmin, color=grey, lw=1, ls=":")
    ax.axvline(ksat, color=grey, lw=1, ls=":")
    ax.text(
        ksat - 0.15,
        0.62,
        f"floor f_min = {fmin:g}\nreached at\nK = {ksat:.1f} m⁻¹",
        fontsize=8.5,
        color="dimgrey",
        va="center",
        ha="right",
    )
    ax.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax.set_ylabel("speed factor v / v₀ [-]", color="dimgrey")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 1.05)
    ax.legend(
        frameon=True,
        facecolor="white",
        framealpha=0.9,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8.5,
        loc="upper right",
    )
    fig.savefig(OUT / "speed_laws.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
