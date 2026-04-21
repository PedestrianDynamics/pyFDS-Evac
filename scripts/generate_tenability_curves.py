"""Generate the tenability reference figure for the paper.

Three panels:
1. Frantzich-Nilsson speed factor vs extinction coefficient K
2. FIC speed factor vs FIC
3. Combined product f(K) * g(FIC) as a 2-D heatmap on (K, FIC)

The constants match the defaults of :mod:`pyfds_evac.core.fed.TenabilityConfig`
and :mod:`pyfds_evac.core.smoke_speed.SmokeSpeedConfig`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# Frantzich-Nilsson defaults (Ronchi 2013 interpretation A3)
ALPHA_K = 0.706
BETA_K = -0.057
F_MIN = 0.1

# Purser FIC defaults (TenabilityConfig)
ALPHA_FIC = 0.7
MU = 0.3


def frantzich_factor(k: np.ndarray | float) -> np.ndarray:
    """Frantzich-Nilsson speed factor f(K) clamped to the minimum floor."""
    k = np.asarray(k, dtype=float)
    raw = 1.0 + (BETA_K / ALPHA_K) * k
    return np.maximum(F_MIN, raw)


def fic_factor(fic: np.ndarray | float) -> np.ndarray:
    """FIC speed factor g(FIC) clamped to the irritant minimum floor."""
    fic = np.asarray(fic, dtype=float)
    raw = 1.0 - ALPHA_FIC * fic
    return np.maximum(MU, raw)


def _build_figure() -> plt.Figure:
    """Draw the three-panel tenability reference figure."""
    k_vals = np.linspace(0.0, 15.0, 500)
    fic_vals = np.linspace(0.0, 1.5, 500)

    fig = plt.figure(figsize=(12, 3.8), constrained_layout=True)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.1])
    ax_k = fig.add_subplot(gs[0, 0])
    ax_fic = fig.add_subplot(gs[0, 1])
    ax_hm = fig.add_subplot(gs[0, 2])

    # Panel 1: Frantzich
    fk = frantzich_factor(k_vals)
    ax_k.plot(k_vals, fk, color="#1f77b4", linewidth=2.0)
    ax_k.axhline(
        F_MIN,
        color="#888",
        linestyle=":",
        linewidth=0.8,
        label=f"floor $f_\\min={F_MIN}$",
    )
    k_knee = -(1.0 - F_MIN) * ALPHA_K / BETA_K
    ax_k.axvline(k_knee, color="#888", linestyle=":", linewidth=0.8)
    ax_k.set_xlabel(r"Extinction $K$  [m$^{-1}$]")
    ax_k.set_ylabel(r"$v/v_0$")
    ax_k.set_title(rf"Frantzich: $v/v_0 = \max({F_MIN},\, 1 + \beta/\alpha \cdot K)$")
    ax_k.set_ylim(0, 1.05)
    ax_k.grid(True, alpha=0.3)
    ax_k.legend(loc="upper right", fontsize=8)

    # Panel 2: FIC
    gf = fic_factor(fic_vals)
    ax_fic.plot(fic_vals, gf, color="#d62728", linewidth=2.0)
    ax_fic.axhline(
        MU, color="#888", linestyle=":", linewidth=0.8, label=rf"floor $\mu={MU}$"
    )
    fic_knee = (1.0 - MU) / ALPHA_FIC
    ax_fic.axvline(fic_knee, color="#888", linestyle=":", linewidth=0.8)
    ax_fic.set_xlabel(r"FIC")
    ax_fic.set_ylabel(r"$v/v_0$")
    ax_fic.set_title(
        rf"FIC: $v/v_0 = \max({MU},\, 1 - \alpha_{{\mathrm{{FIC}}}}\cdot \mathrm{{FIC}})$"
    )
    ax_fic.set_ylim(0, 1.05)
    ax_fic.grid(True, alpha=0.3)
    ax_fic.legend(loc="upper right", fontsize=8)

    # Panel 3: 2D heatmap of the product
    k_grid = np.linspace(0.0, 15.0, 200)
    fic_grid = np.linspace(0.0, 1.5, 200)
    K2d, F2d = np.meshgrid(k_grid, fic_grid)
    combined = frantzich_factor(K2d) * fic_factor(F2d)
    im = ax_hm.pcolormesh(
        k_grid,
        fic_grid,
        combined,
        cmap="viridis",
        vmin=0.0,
        vmax=1.0,
        shading="auto",
    )
    ax_hm.set_xlabel(r"Extinction $K$  [m$^{-1}$]")
    ax_hm.set_ylabel(r"FIC")
    ax_hm.set_title(r"Combined: $v/v_0 = f(K)\,\cdot\,g(\mathrm{FIC})$")
    cbar = fig.colorbar(im, ax=ax_hm)
    cbar.set_label(r"$v/v_0$")

    # Overlay floor product dashed contour
    floor = F_MIN * MU
    ax_hm.contour(
        k_grid,
        fic_grid,
        combined,
        levels=[floor, 0.25, 0.5, 0.75],
        colors="white",
        linewidths=0.8,
        alpha=0.6,
    )

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
    fig.savefig(args.output, dpi=160, bbox_inches="tight")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
