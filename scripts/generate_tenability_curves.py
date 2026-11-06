"""Generate the tenability reference figure for the paper.

Three panels:
1. Frantzich-Nilsson speed factor f(K) vs extinction coefficient K
2. Irritant speed fraction F_irr(FIC) vs FIC, Purser's Eq. 70.11 (SFPE
   Handbook 6th ed., Ch. 70), with the 0.1 floor of the combined factor
3. Combined factor ``combined_speed_factor(f(K), F_irr(FIC))``, i.e.
   f + F_irr - 1 (Eq. 70.12) with a floor of 0.1, as a 2-D heatmap on
   (K, FIC)

The Frantzich-Nilsson constants match the defaults of
:mod:`pyfds_evac.core.smoke_speed.SmokeSpeedConfig`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from pyfds_evac.core.direct_steering_runtime import (
    FIC_SPEED_FLOOR,
    combined_speed_factor,
)
from pyfds_evac.core.fed import irritant_speed_fraction

# Frantzich-Nilsson defaults (Ronchi 2013 interpretation A3)
ALPHA_K = 0.706
BETA_K = -0.057
F_MIN = 0.1


def frantzich_factor(k: np.ndarray | float) -> np.ndarray:
    """Frantzich-Nilsson speed factor f(K) clamped to the minimum floor."""
    k = np.asarray(k, dtype=float)
    raw = 1.0 + (BETA_K / ALPHA_K) * k
    return np.maximum(F_MIN, raw)


def irritant_fraction(fic: np.ndarray | float) -> np.ndarray:
    """Irritant speed fraction F_irr(FIC), Eq. 70.11."""
    return np.vectorize(irritant_speed_fraction)(np.asarray(fic, dtype=float))


def combined_factor(k: np.ndarray, fic: np.ndarray) -> np.ndarray:
    """Combined speed factor over broadcast ``k`` and ``fic`` arrays."""
    smoke = frantzich_factor(k)
    f_irr = irritant_fraction(fic)
    return np.vectorize(combined_speed_factor)(smoke, f_irr)


def _build_figure() -> plt.Figure:
    """Draw the three-panel tenability reference figure."""
    k_vals = np.linspace(0.0, 15.0, 500)
    fic_vals = np.linspace(0.0, 1.5, 500)

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    line = sns.cubehelix_palette(6, rot=-0.25, light=0.7)[5]
    fig = plt.figure(figsize=(12, 3.8), dpi=150, constrained_layout=True)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.1])
    ax_k = fig.add_subplot(gs[0, 0])
    ax_fic = fig.add_subplot(gs[0, 1])
    ax_hm = fig.add_subplot(gs[0, 2])

    # Panel 1: Frantzich
    fk = frantzich_factor(k_vals)
    ax_k.plot(k_vals, fk, color=line, linewidth=2.0)
    ax_k.axhline(F_MIN, color="grey", linestyle=":", linewidth=0.8)
    k_knee = -(1.0 - F_MIN) * ALPHA_K / BETA_K
    ax_k.axvline(k_knee, color="grey", linestyle=":", linewidth=0.8)
    ax_k.text(
        k_vals[-1],
        F_MIN - 0.03,
        rf"floor $f_\min={F_MIN}$",
        color="dimgrey",
        fontsize=9,
        ha="right",
        va="top",
    )
    ax_k.set_xlabel(r"Extinction $K$  [m$^{-1}$]", color="dimgrey")
    ax_k.set_ylabel(r"$v/v_0$", color="dimgrey")
    ax_k.set_title(
        r"$\bf{(a)}$ " + rf"$v/v_0 = \max({F_MIN},\, 1 + \beta/\alpha \cdot K)$",
        loc="left",
        fontsize=11,
    )
    ax_k.set_ylim(0, 1.05)

    # Panel 2: Eq. 70.11
    gf = irritant_fraction(fic_vals)
    ax_fic.plot(fic_vals, gf, color=line, linewidth=2.0)
    ax_fic.axhline(FIC_SPEED_FLOOR, color="grey", linestyle=":", linewidth=0.8)
    ax_fic.text(
        fic_vals[-1],
        FIC_SPEED_FLOOR + 0.03,
        rf"floor of the combined factor $={FIC_SPEED_FLOOR}$",
        color="dimgrey",
        fontsize=9,
        ha="right",
        va="bottom",
    )
    ax_fic.set_xlabel(r"FIC", color="dimgrey")
    ax_fic.set_title(
        r"$\bf{(b)}$ " + r"$F_{\mathrm{irr}}(\mathrm{FIC})$, Eq. 70.11",
        loc="left",
        fontsize=11,
    )
    ax_fic.set_ylim(0, 1.05)

    # Panel 3: 2D heatmap of the product
    k_grid = np.linspace(0.0, 15.0, 200)
    fic_grid = np.linspace(0.0, 1.5, 200)
    K2d, F2d = np.meshgrid(k_grid, fic_grid)
    combined = combined_factor(K2d, F2d)
    im = ax_hm.pcolormesh(
        k_grid,
        fic_grid,
        combined,
        cmap="inferno",
        vmin=0.0,
        vmax=1.0,
        shading="auto",
        rasterized=True,
    )
    ax_hm.set_xlabel(r"Extinction $K$  [m$^{-1}$]", color="dimgrey")
    ax_hm.set_ylabel(r"FIC", color="dimgrey")
    ax_hm.set_title(
        r"$\bf{(c)}$ " + r"$v/v_0 = f(K) + F_{\mathrm{irr}}(\mathrm{FIC}) - 1$",
        loc="left",
        fontsize=11,
    )
    cbar = fig.colorbar(im, ax=ax_hm)
    cbar.set_label(r"$v/v_0$", color="dimgrey")
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(length=0, labelcolor="dimgrey")

    # Contours of equal speed factor
    cs = ax_hm.contour(
        k_grid,
        fic_grid,
        combined,
        levels=[0.25, 0.5, 0.75],
        colors="white",
        linewidths=0.8,
        alpha=0.8,
    )
    ax_hm.clabel(cs, fmt="%.2g", fontsize=8)
    ax_hm.text(
        k_grid[-1] - 0.5,
        fic_grid[-1] - 0.05,
        f"floor {FIC_SPEED_FLOOR}",
        color="white",
        fontsize=8.5,
        ha="right",
        va="top",
    )
    ax_hm.set_xticks([0, 5, 10, 15])

    ax_hm.grid(False)
    for ax in (ax_k, ax_fic, ax_hm):
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    sns.despine(left=True, bottom=True)

    return fig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../pyFDS-Evac-paper/figs/tenability_speed_curves.png"),
        help="Output PNG path (default: ../pyFDS-Evac-paper/figs/...)",
    )
    args = parser.parse_args()

    fig = _build_figure()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=150, bbox_inches="tight")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
