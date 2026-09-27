# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Fridolf et al. (2019): walking speed against visibility, and in K.

Every curve is computed from constants printed in the sources:

- Fridolf, Ronchi, Nilsson and Frantzich (2019), Eq. 2: w = 0.34 x + 0.31.
  Its data span x = 0.3-3 m, with no points between about 1.17 and
  1.78 m (paper Fig. 3); x = 0 is an extrapolation. Above 3 m the paper takes
  speed to be unaffected by smoke, so Eq. 2 is not drawn there.
- Their Eq. 7, w = min(w_free, max(0.2, w_free - 0.34 (3 - x))), for the
  clear-condition speeds of Eqs. 3-6: 1.00, 1.35, 1.10 and 0.85 m/s.
- Their Eq. 1, x = A / K, with A = 2 (light-reflecting) and A = 8
  (light-emitting). It converts between the two panels.
- For comparison, Frantzich and Nilsson (2003), Eq. 3:
  v = 0.706 - 0.057 K on K = 1.9-7.4 1/m (report Fig. 9), and Purser and
  McAllister (2016), Eq. 63.10: W = -0.1364 ln K + 0.6423 on their stated
  pooled ranges, K = 0.32-0.5 and 1.9-7.5 1/m.

Panel (a) puts Frantzich and Nilsson into visibility with x = 2/K, the
constant their own report uses for lit walls and objects (report Eq. 2).
Panel (b) puts Fridolf's Eq. 2 into K with both values of A, because the
paper does not state which A it applied to which data set. As each data
set was converted with its own A, the K range of the data is unknown, so
the converted curves use one neutral style over x = 0.3-3 m.

Line rule in (a), as in the legend: thick solid within the source data,
thick dotted over the gap without data, dashed for extrapolation, thin
solid for the Eq. 7 design rule. Colours: one per source, shared
with fundamentals_speed_extinction.py.

Run from the repository root::

    uv run python scripts/figures/fundamentals_speed_visibility.py

Writes ``site/static/images/fundamentals/speed_visibility.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec
from matplotlib.lines import Line2D


def main():
    """Plot Fridolf's laws against visibility (a) and extinction (b).

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/speed_visibility.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_fridolf = sns.cubehelix_palette(6, rot=-0.25, light=0.7)[5]
    c_purser, c_fn = "#fc8d59", "#4575b4"

    # --- Data ---
    def eq2(x):
        return 0.34 * x + 0.31

    def eq7(x, w_free):
        return np.minimum(w_free, np.maximum(0.2, w_free - 0.34 * (3.0 - x)))

    def fn(k):
        return 0.706 - 0.057 * k

    def purser(k):
        return -0.1364 * np.log(k) + 0.6423

    x_data, x_gap = (0.3, 3.0), (1.17, 1.78)
    k_fn = (1.9, 7.4)
    designs = [(1.35, "1.35 (Eq. 4)"), (1.10, "1.10 (Eq. 5)")]
    designs += [(1.00, "1.00 (Eq. 3)"), (0.85, "0.85 (Eq. 6)")]

    def eq2_segments(ax, to_x, lw):
        """Draw Eq. 2 solid, dotted over the data gap, dashed below 0.3 m."""
        for (lo, hi), ls in (
            ((0.0, x_data[0]), "--"),
            ((x_data[0], x_gap[0]), "-"),
            (x_gap, ":"),
            ((x_gap[1], x_data[1]), "-"),
        ):
            x = np.linspace(max(lo, 0.01), hi, 200)
            ax.plot(
                to_x(x),
                eq2(x),
                color=c_fridolf,
                lw=lw if ls != "--" else 1.4,
                ls=ls,
                zorder=4,
            )

    # --- Plot ---
    fig = plt.figure(figsize=(11.0, 4.8), dpi=150)
    gs = gridspec.GridSpec(1, 2)
    gs.update(wspace=0.08, left=0.08, right=0.99, top=0.9, bottom=0.12)
    ax_x = plt.subplot(gs[0, 0])
    ax_k = plt.subplot(gs[0, 1], sharey=ax_x)

    # (a) against visibility
    ax_x.axhline(0.2, color="grey", lw=0.8, ls=":", zorder=1)
    ax_x.text(0.05, 0.17, "floor 0.2 m/s", fontsize=8, color="dimgrey", va="top")
    ax_x.axvline(3.0, color="lightgrey", lw=0.8, zorder=1)
    ax_x.text(
        3.05,
        0.05,
        "above 3 m: no\nslowing (Fridolf)",
        fontsize=8,
        color="dimgrey",
    )

    x = np.linspace(0.0, 6.0, 601)
    for w_free, label in designs:
        ax_x.plot(x, eq7(x, w_free), color=c_fridolf, lw=0.9, alpha=0.6, zorder=2)
        ax_x.text(
            5.95,
            w_free + 0.02,
            label,
            fontsize=8,
            color="dimgrey",
            ha="right",
            va="bottom",
        )
    ax_x.text(
        5.95,
        1.47,
        "Eq. 7, w_smoke-free =",
        fontsize=8,
        color="dimgrey",
        ha="right",
        va="bottom",
    )

    eq2_segments(ax_x, lambda xv: xv, 3.0)
    ax_x.text(
        0.1,
        1.12,
        "Fridolf Eq. 2:\nw = 0.34 x + 0.31",
        fontsize=9,
        color=c_fridolf,
        weight="semibold",
    )
    ax_x.text(
        1.45, eq2(1.45) + 0.12, "no data", fontsize=8, color="dimgrey", ha="right"
    )

    xs = np.linspace(2.0 / k_fn[1], 2.0 / k_fn[0], 100)
    ax_x.plot(xs, fn(2.0 / xs), color=c_fn, lw=2.6, zorder=3)
    ax_x.annotate(
        "Frantzich–Nilsson,\nx = 2/K",
        xy=(0.6, fn(2.0 / 0.6)),
        xytext=(0.1, 0.8),
        fontsize=9,
        color=c_fn,
        weight="semibold",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )

    ax_x.set_xlim(0.0, 6.0)
    ax_x.set_ylim(0.0, 1.7)
    ax_x.set_xlabel("visibility x [m]", color="dimgrey")
    ax_x.set_ylabel("walking speed w [m/s]", color="dimgrey")
    ax_x.set_title(r"$\bf{(a)}$" + " against visibility", loc="left", fontsize=12)

    # (b) against extinction coefficient
    k_max = 8.0
    k = np.linspace(*k_fn, 100)
    ax_k.plot(k, fn(k), color=c_fn, lw=2.0, alpha=0.7)
    ax_k.text(6.0, fn(6.0) - 0.09, "Frantzich–Nilsson", fontsize=8.5, color=c_fn)
    for lo, hi in ((0.32, 0.5), (1.9, 7.5)):
        k = np.linspace(lo, hi, 100)
        ax_k.plot(k, purser(k), color=c_purser, lw=2.0, alpha=0.7)
    ax_k.text(6.0, purser(6.0) + 0.04, "Purser", fontsize=8.5, color=c_purser)

    for a, label, xy in (
        (2.0, "A = 2 (reflecting)", (1.0, 1.35)),
        (8.0, "A = 8 (emitting)", (4.3, 1.35)),
    ):
        xv = np.linspace(*x_data, 300)
        ax_k.plot(a / xv, eq2(xv), color=c_fridolf, lw=1.8, zorder=4)
        ax_k.plot(a / 3.0, eq2(3.0), "o", color=c_fridolf, ms=5, mec="white")
        ax_k.text(*xy, label, fontsize=9, color=c_fridolf, weight="semibold")
    ax_k.text(
        0.15,
        1.6,
        "Fridolf Eq. 2 converted with x = A/K over x = 0.3–3 m;\n"
        "dots mark x = 3 m. The K range of the data is unknown.",
        fontsize=8,
        color="dimgrey",
    )

    ax_k.set_xlim(0.0, k_max)
    ax_k.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax_k.set_title(r"$\bf{(b)}$" + " Eq. 2 in terms of K", loc="left", fontsize=12)

    for ax in (ax_x, ax_k):
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.grid(False)
    ax_k.tick_params(labelleft=False)
    sns.despine(left=True, bottom=True)
    for ax in (ax_x, ax_k):
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)

    handles = [
        Line2D([], [], color="grey", lw=3.0, label="within source data"),
        Line2D([], [], color="grey", lw=3.0, ls=":", label="no data (gap)"),
        Line2D([], [], color="grey", lw=1.4, ls="--", label="extrapolation"),
        Line2D([], [], color="grey", lw=0.9, label="design rule (Eq. 7)"),
    ]
    ax_x.legend(
        handles=handles,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8,
        loc="lower right",
        bbox_to_anchor=(1.0, 0.22),
    )

    # --- Save ---
    fig.savefig(out / "speed_visibility.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
