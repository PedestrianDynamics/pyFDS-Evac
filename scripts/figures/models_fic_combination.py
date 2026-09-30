"""Coded irritant slowdown against Purser's curve and additive combination.

Panel (a): the speed factor against FIC. SFPE Handbook Ch. 63, Eq. 63.13
(Purser and McAllister 2016, p. 2344),

    F_wvirr = (exp(-(1000 x / b)^2) + (-0.2 x + 0.2)) / 1.2,
    b = 160, x = FIC,

drawn thin (a concept curve, no walking data) and dotted beyond FIC = 1,
where it is outside its range and turns negative. Against it, the coded
factor g = max(fic_min_factor, 1 - fic_alpha * FIC), dashed.

Panel (b): the walking-speed fraction for smoke fractions F_s = 1, 0.75
and 0.5. Published: Eq. 63.14, F_wv = 1 - (1 - F_s) - (1 - F_wvirr), with
Eq. 63.13, solid. Coded: F_s * g (``set_agent_fic_factor``), dashed. The
region where the additive sum is at most 0, which neither source clips, is
shaded.

The coded constants are read from ``TenabilityConfig()``, so the figure
follows the code's defaults.

Run from the repository root::

    uv run python scripts/figures/models_fic_combination.py

Writes ``site/static/images/models/fic_combination.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.lines import Line2D

from pyfds_evac.core.fed import TenabilityConfig


def main():
    """Plot the coded irritant factor against Eqs. 63.13 and 63.14.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/models/fic_combination.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/models"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_purser = "#fc8d59"
    c_code = "#4575b4"
    smoke_colors = {1.0: "#1b9e77", 0.75: "#7570b3", 0.5: "#e7298a"}

    # --- Data ---
    cfg = TenabilityConfig()
    alpha = float(cfg.fic_alpha)
    floor = float(cfg.fic_min_factor)

    def eq_63_13(fic, b=160.0):
        return (np.exp(-((1000.0 * fic / b) ** 2)) + (-0.2 * fic + 0.2)) / 1.2

    def coded_g(fic):
        return np.maximum(floor, 1.0 - alpha * fic)

    fic = np.linspace(0.0, 1.0, 801)
    fic_out = np.linspace(1.0, 1.2, 101)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12.0, 4.6), dpi=150)

    # --- Plot (a) ---
    ax_a.plot(fic, eq_63_13(fic), color=c_purser, lw=1.4)
    ax_a.plot(fic_out, eq_63_13(fic_out), color=c_purser, lw=1.4, ls=":")
    ax_a.plot(
        np.concatenate([fic, fic_out]),
        coded_g(np.concatenate([fic, fic_out])),
        color=c_code,
        lw=2.0,
        ls="--",
    )
    ax_a.axhline(0.0, color="lightgrey", lw=0.8, zorder=0)
    ax_a.text(
        0.24,
        0.40,
        "Eq. 63.13 (Purser)",
        fontsize=9,
        color=c_purser,
    )
    ax_a.text(
        0.42,
        0.78,
        f"pyFDS-Evac g, no source\nmax({floor:g}, 1 − {alpha:g}·FIC)",
        fontsize=9,
        color=c_code,
    )
    ax_a.annotate(
        "0 at FIC = 1: incapacitation in the sources",
        xy=(1.0, 0.0),
        xytext=(0.36, -0.105),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax_a.annotate(
        f"code: floor {floor:g},\nagent keeps walking",
        xy=(1.06, floor),
        xytext=(0.86, 0.46),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax_a.set_xlim(0.0, 1.21)
    ax_a.set_ylim(-0.13, 1.05)
    ax_a.set_xlabel("fractional irritant concentration FIC [-]", color="dimgrey")
    ax_a.set_ylabel("irritant speed factor [-]", color="dimgrey")
    ax_a.set_title(r"$\bf{(a)}$" + " the curve", loc="left", fontsize=12)

    # --- Plot (b) ---
    for fs, color in smoke_colors.items():
        additive = 1.0 - (1.0 - fs) - (1.0 - eq_63_13(fic))
        product = fs * coded_g(fic)
        ax_b.plot(fic, additive, color=color, lw=1.4)
        ax_b.plot(fic, product, color=color, lw=2.0, ls="--")
        ax_b.text(
            1.02,
            product[-1],
            f"$F_s$ = {fs:g}",
            fontsize=8.5,
            color=color,
            va="center",
        )
    ax_b.axhspan(-0.6, 0.0, color="lightgrey", alpha=0.35, lw=0, zorder=0)
    ax_b.axhline(0.0, color="grey", lw=0.8, zorder=1)
    ax_b.text(
        0.34,
        -0.56,
        "additive sum ≤ 0:\nunclipped in source",
        fontsize=8.5,
        color="dimgrey",
    )
    ax_b.set_xlim(0.0, 1.12)
    ax_b.set_ylim(-0.6, 1.05)
    ax_b.set_xlabel("fractional irritant concentration FIC [-]", color="dimgrey")
    ax_b.set_ylabel("walking-speed fraction $F_{wv}$ [-]", color="dimgrey")
    ax_b.set_title(r"$\bf{(b)}$" + " combined with smoke", loc="left", fontsize=12)
    handles = [
        Line2D([], [], color="grey", lw=1.4, label="Eq. 63.14 + Eq. 63.13 (additive)"),
        Line2D([], [], color="grey", lw=2.0, ls="--", label="pyFDS-Evac, $F_s$·g"),
    ]
    ax_b.legend(
        handles=handles,
        loc="upper right",
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        edgecolor="lightgrey",
    )

    for ax in (ax_a, ax_b):
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.grid(False)
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    sns.despine(left=True, bottom=True)
    fig.tight_layout()

    # --- Save ---
    fig.savefig(out / "fic_combination.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
