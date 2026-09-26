"""Speed factor against extinction: Frantzich–Nilsson (Lund) and the `fridolf` option.

The `fridolf` option computes V/(V+2); its attribution to Fridolf et al.
(2019) is unverified (issue #146), so the figure does not name it after them.

The curves are computed through the public API (``SmokeSpeedModel`` on a
``ConstantExtinctionField``), so the figure follows the code's defaults.

Run from the repository root::

    uv run --group docs python scripts/figures/speed_laws.py

Writes ``site/static/images/concepts/speed_laws.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from pyfds_evac import ConstantExtinctionField, SmokeSpeedConfig, SmokeSpeedModel

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"


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
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    blue, red, orange = pal[5], "#d73027", "#fc8d59"
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

    gap = np.abs(lund - frid3)
    i = int(np.argmax(gap))

    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=150)
    ax.plot(k, lund, color=blue, lw=2.6, label="Frantzich–Nilsson (default)")
    ax.plot(
        k,
        frid3,
        color=red,
        lw=2.0,
        ls="--",
        label="fridolf option, C = 3 (reflective)",
    )
    ax.plot(
        k,
        frid8,
        color=orange,
        lw=2.0,
        ls="-.",
        label="fridolf option, C = 8 (emitting)",
    )
    ax.axhline(fmin, color="grey", lw=0.8, ls=":", zorder=1)
    ax.axvline(ksat, color="grey", lw=0.8, ls=":", zorder=1)
    ax.text(
        ksat - 0.15,
        fmin - 0.02,
        f"floor {fmin:g} from K = {ksat:.1f} m⁻¹",
        fontsize=8.5,
        color="dimgrey",
        ha="right",
        va="top",
    )
    ax.annotate(
        "",
        xy=(k[i], frid3[i]),
        xytext=(k[i], lund[i]),
        arrowprops=dict(arrowstyle="<->", color="dimgrey", lw=0.8),
    )
    ax.text(
        k[i] + 0.2,
        lund[i] + 0.04,
        f"largest gap {gap[i]:.2f} at K = {k[i]:.1f} m⁻¹\n"
        f"({lund[i]:.2f} vs {frid3[i]:.2f} with C = 3)",
        fontsize=8.5,
        color="dimgrey",
        ha="left",
        va="bottom",
    )
    ax.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax.set_ylabel("speed factor v / v₀ [-]", color="dimgrey")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 1.05)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    sns.despine(left=True, bottom=True)
    ax.legend(
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8.5,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        ncol=2,
    )
    fig.savefig(OUT / "speed_laws.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
