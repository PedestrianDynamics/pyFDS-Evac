# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""FDS+Evac's fractional speed law against the absolute Frantzich-Nilsson law.

- Frantzich and Nilsson (2003), Lund report 3126, Eq. 3 and Table D2
  (model 1, lights on): v = alpha + beta K, alpha = 0.706 m/s,
  beta = -0.057 m^2/s. The lit runs span K = 1.9-7.4 1/m (report Fig. 9).
- FDS+Evac (Korhonen 2021, Eq. 11): v = max(0.1 v0, v0 (1 + (beta/alpha) K)),
  with the default floor 0.1 v0.

Panel (a) shows the factor F(K) = max(0.1, 1 + (beta/alpha) K). Panel (b)
shows the absolute law and the fractional reading for three example
unimpeded speeds v0. Solid: within the lit runs. Dashed: extrapolation.
The colour of the Frantzich-Nilsson and FDS+Evac curves is the one of
fundamentals_speed_extinction.py.

Run from the repository root::

    uv run python scripts/figures/fundamentals_speed_fractional.py

Writes ``site/static/images/fundamentals/speed_fractional.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec

ALPHA = 0.706
BETA = -0.057
FLOOR = 0.1
K_DATA = (1.9, 7.4)
K_MAX = 13.0
V0_EXAMPLES = (0.706, 1.0, 1.3)


def factor(k):
    """FDS+Evac speed factor, Korhonen (2021) Eq. 11."""
    return np.maximum(FLOOR, 1.0 + BETA / ALPHA * k)


def absolute(k):
    """Frantzich-Nilsson Eq. 3, stopped at zero speed."""
    return np.maximum(0.0, ALPHA + BETA * k)


def plot_ranged(ax, fn, colour, lw_in=2.6, lw_out=1.4, k_end=K_MAX, **kw):
    """Plot ``fn`` solid over the data range and dashed outside it."""
    for lo, hi, lw, ls in (
        (0.0, K_DATA[0], lw_out, "--"),
        (K_DATA[0], K_DATA[1], lw_in, "-"),
        (K_DATA[1], k_end, lw_out, "--"),
    ):
        k = np.linspace(lo, hi, 200)
        ax.plot(k, fn(k), color=colour, lw=lw, ls=ls, **kw)


def style(ax, letter, title, ylabel):
    """Apply the shared axis style."""
    ax.set_xlim(0.0, K_MAX)
    ax.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax.set_ylabel(ylabel, color="dimgrey")
    ax.set_title(rf"$\bf{{({letter})}}$ {title}", loc="left", fontsize=12)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)


def shade_data(ax, y_text):
    """Shade the K range of the lit runs."""
    ax.axvspan(*K_DATA, color="#f2f2f2", zorder=0)
    ax.text(
        sum(K_DATA) / 2,
        y_text,
        "lit runs\nK = 1.9–7.4 1/m",
        ha="center",
        va="top",
        fontsize=8,
        color="dimgrey",
    )


def main():
    """Plot the factor and the speeds, and save the PNG."""
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_fn = "#4575b4"
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    c_v0 = {0.706: pal[5], 1.0: pal[3], 1.3: pal[1]}
    k_floor = (FLOOR - 1.0) * ALPHA / BETA
    k_zero = -ALPHA / BETA

    fig = plt.figure(figsize=(12.5, 4.9), dpi=150)
    gs = gridspec.GridSpec(1, 2)
    gs.update(wspace=0.18, left=0.06, right=0.99, top=0.9, bottom=0.12)
    ax_f = plt.subplot(gs[0, 0])
    ax_v = plt.subplot(gs[0, 1])

    # (a) the factor
    shade_data(ax_f, 1.12)
    plot_ranged(ax_f, factor, c_fn, k_end=k_floor)
    ax_f.plot([k_floor, K_MAX], [FLOOR, FLOOR], color=c_fn, lw=1.4, ls="-.")
    ax_f.text(
        k_floor - 0.1,
        FLOOR + 0.05,
        r"FDS+Evac floor, $0.1\,v^0$" + f"\nfrom K = {k_floor:.2f} 1/m",
        fontsize=9,
        color="dimgrey",
        ha="left",
    )
    ax_f.annotate(
        "F = 1 at K = 0: the divisor\n0.706 m/s is an extrapolation",
        xy=(0.0, 1.0),
        xytext=(0.9, 0.28),
        fontsize=9,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax_f.text(
        5.6,
        factor(5.6) + 0.06,
        r"$F = 1 + (\beta/\alpha)\,K = 1 - 0.0807\,K$",
        fontsize=10,
        color=c_fn,
        weight="semibold",
    )
    ax_f.set_ylim(0.0, 1.15)
    style(ax_f, "a", "FDS+Evac speed factor", "fraction of unimpeded speed F [-]")

    # (b) absolute against fractional speeds
    shade_data(ax_v, 1.47)
    plot_ranged(ax_v, absolute, c_fn, lw_in=4.0, lw_out=2.2, alpha=0.45)
    ax_v.text(
        2.0,
        0.30,
        "absolute law,\nFrantzich–Nilsson Eq. 3",
        fontsize=9,
        color=c_fn,
        weight="semibold",
    )
    ax_v.plot(k_zero, 0.0, marker="o", ms=5, color=c_fn, alpha=0.6, clip_on=False)
    for v0 in V0_EXAMPLES:
        plot_ranged(
            ax_v, lambda k, v0=v0: v0 * factor(k), c_v0[v0], lw_in=1.8, lw_out=1.1
        )
        ax_v.text(
            0.15,
            v0 + 0.035,
            rf"$v^0$ = {v0:g} m/s",
            fontsize=9,
            color=c_v0[v0],
            weight="semibold",
        )
    ax_v.text(
        12.9,
        0.37,
        r"fractional: floors at $0.1\,v^0$"
        + f"\nabsolute: 0 at K = {k_zero:.1f} (dot)",
        fontsize=8,
        color="dimgrey",
        ha="right",
    )
    ax_v.text(
        6.9,
        1.02,
        "fractional reading, FDS+Evac Eq. 11,\nfor three example speeds $v^0$;\n"
        "at $v^0$ = 0.706 m/s it follows the\nabsolute law up to K = 11.15 1/m",
        fontsize=8,
        color="dimgrey",
        va="top",
    )
    ax_v.set_ylim(0.0, 1.5)
    style(ax_v, "b", "absolute and fractional readings", "walking speed v [m/s]")
    sns.despine(left=True, bottom=True)

    # --- Save ---
    fig.savefig(out / "speed_fractional.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
