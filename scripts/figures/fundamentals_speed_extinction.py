# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Published walking-speed laws against extinction coefficient K.

Every curve and point is computed from constants printed in the sources;
nothing is digitised from a figure:

- Frantzich and Nilsson (2003), Lund report 3126, Eq. 3 and Table D2
  (model 1, lights on): v = 0.706 - 0.057 K. The lit runs span
  K = 1.9-7.4 1/m (report Fig. 9). The 95 % prediction interval at
  K = 4 1/m, "ca 0.2 och 0.7" m/s, is quoted in Sect. 3.3.2.
- Purser and McAllister (2026), SFPE Handbook Ch. 70, Eq. 70.8:
  W = -0.1364 ln K + 0.6423, fitted on Jin's irritant data
  (K = 0.32-0.5 1/m) pooled with Frantzich and Nilsson's
  (K = 1.9-7.5 1/m), as stated on pp. 2285-2286.
- Purser and McAllister's straight-line fits to Jin's data as replotted
  in their Fig. 70.10 (legend): non-irritant v = 1.0573 - 0.4326 K on
  K = 0.2-1.13 1/m, irritant v = 1.1517 - 0.9578 K on K = 0.32-0.5 1/m
  (ranges as stated on p. 2285). They are drawn solid only where Jin's
  points lie in the primary report (Jin 1976, FRI Report 42, Fig. 2):
  about 0.5-1.13 1/m non-irritant and 0.32-0.47 1/m irritant, extents read
  from the figure's axis, not digitised points; the rest of Purser's range
  is dashed. The means with their standard
  deviations (0.74 +/- 0.17 m/s at K = 0.73 1/m, non-irritant;
  0.75 +/- 0.21 m/s at K = 0.42 1/m, irritant) are quoted on
  p. 2285.

Panel (b), fractional laws (speed as a fraction of the unexposed speed):

- Purser (2003), p. 98 and Fig. 1, fitted to Jin's non-irritant data:
  F = -1.738 OD/m + 1.236 for OD/m = 0.13-0.55, normal speed below, and
  above 0.55 the speed "as in darkness at 0.3 m/s". The floor is drawn at
  the fraction the equation reaches at 0.55 (0.28), our construction;
  Purser writes 0.3 m/s (0.25 of the 1.2 m/s that SFPE Ch. 70 uses) and
  his Fig. 1 shows about 0.27. The line is solid only over Jin's
  non-irritant points (K about 0.5-1.13 1/m, FRI Report 42, Fig. 2) and
  dashed over the rest of Purser's stated range. The 0.3 m/s is Jin's
  reference value for walking in darkness, drawn as a horizontal line in FRI Report 42, Fig. 2 (p. 17; tying it to Togawa
  1969, cited on p. 14 for 0.3-0.7 m/s, is our inference),
  not a measured point.
  The fitted line starts at its computed value, 1.010 at OD/m 0.13; the
  F = 1 segment below is Purser's stated normal speed, drawn dashed. OD/m is converted to K with the
  base-10 definition of SFPE Ch. 70 (p. 2341), K = ln(10) OD/m.
- FDS+Evac (Korhonen 2021, Eq. 11): F = max(0.1, 1 + (beta/alpha) K) with
  the Frantzich-Nilsson constants.

Solid: within the source's data range. Dashed: extrapolation. Dotted: the
gap between the two pooled data sets of Eq. 70.8, where it has no data.
Colours: one per source, shared with fundamentals_speed_visibility.py.

Run from the repository root::

    uv run python scripts/figures/fundamentals_speed_extinction.py

Writes ``site/static/images/fundamentals/speed_extinction.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec
from matplotlib.lines import Line2D


def main():
    """Plot the published speed laws against K on a linear axis.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/speed_extinction.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_jin, c_purser, c_fn = "#d73027", "#fc8d59", "#4575b4"

    # --- Data ---
    def fn(k):
        return 0.706 - 0.057 * k

    def purser(k):
        return -0.1364 * np.log(k) + 0.6423

    def jin_ni(k):
        return 1.0573 - 0.4326 * k

    def jin_i(k):
        return 1.1517 - 0.9578 * k

    k_irr = (0.32, 0.5)
    k_nonirr = (0.2, 1.13)
    k_jin_ni_pts = (0.5, 1.13)
    k_jin_i_pts = (0.32, 0.47)
    k_fn = (1.9, 7.4)
    k_pooled_fn = (1.9, 7.5)
    k_max = 8.0

    # --- Plot ---
    fig = plt.figure(figsize=(13.0, 5.0), dpi=150)
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.6, 1.0])
    gs.update(wspace=0.12, left=0.06, right=0.99, top=0.9, bottom=0.12)
    ax = plt.subplot(gs[0, 0])
    ax_f = plt.subplot(gs[0, 1])

    # Frantzich-Nilsson, Eq. 3
    for lo, hi in ((0.0, k_fn[0]), (k_fn[1], k_max)):
        k = np.linspace(lo, hi, 100)
        ax.plot(k, fn(k), color=c_fn, lw=1.4, ls="--")
    k = np.linspace(*k_fn, 100)
    ax.plot(k, fn(k), color=c_fn, lw=2.6)
    ax.errorbar(
        4.0,
        0.45,
        yerr=0.25,
        fmt="none",
        ecolor=c_fn,
        elinewidth=1.0,
        capsize=4,
    )
    ax.text(
        4.12,
        0.2,
        "95 % prediction\ninterval at K = 4\n(0.2–0.7 m/s)",
        fontsize=8,
        color="dimgrey",
        va="bottom",
    )
    ax.text(
        5.6,
        fn(5.6) + 0.07,
        "Frantzich–Nilsson, Eq. 3",
        fontsize=9,
        color=c_fn,
        weight="semibold",
        ha="center",
    )
    ax.annotate(
        "intercept 0.706 m/s is an\nextrapolation to K = 0",
        xy=(1.2, fn(1.2)),
        xytext=(1.25, 0.95),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )

    # Purser Eq. 70.8
    for lo, hi in ((0.1, k_irr[0]), (k_pooled_fn[1], k_max)):
        k = np.linspace(lo, hi, 200)
        ax.plot(k, purser(k), color=c_purser, lw=1.4, ls="--")
    for lo, hi in (k_irr, k_pooled_fn):
        k = np.linspace(lo, hi, 200)
        ax.plot(k, purser(k), color=c_purser, lw=2.6)
    k = np.linspace(k_irr[1], k_pooled_fn[0], 200)
    ax.plot(k, purser(k), color=c_purser, lw=1.8, ls=":")
    ax.text(
        1.6,
        0.5,
        "Eq. 70.8:\nno data 0.5–1.9",
        fontsize=8,
        color="dimgrey",
        ha="center",
        va="top",
    )
    ax.text(
        3.0,
        purser(3.0) - 0.09,
        "Purser, Eq. 70.8",
        fontsize=9,
        color=c_purser,
        weight="semibold",
        ha="center",
    )

    # Jin, Purser's straight-line fits over the range of Jin's points
    # Solid over the range of Jin's points (FRI Report 42, Fig. 2),
    # dashed over the rest of Purser's stated ranges.
    k = np.linspace(k_nonirr[0], k_jin_ni_pts[0], 20)
    ax.plot(k, jin_ni(k), color=c_jin, lw=1.4, ls="--")
    k = np.linspace(*k_jin_ni_pts, 50)
    ax.plot(k, jin_ni(k), color=c_jin, lw=2.6)
    k = np.linspace(k_jin_i_pts[1], k_irr[1], 5)
    ax.plot(k, jin_i(k), color=c_jin, lw=1.4, ls="--")
    k = np.linspace(*k_jin_i_pts, 20)
    ax.plot(k, jin_i(k), color=c_jin, lw=2.6)
    ax.errorbar(
        0.73, 0.74, yerr=0.17, fmt="o", color=c_jin, ms=6, capsize=3, mec="white"
    )
    ax.errorbar(
        0.42, 0.75, yerr=0.21, fmt="s", color=c_jin, ms=6, capsize=3, mec="white"
    )
    ax.text(
        0.9,
        jin_ni(0.9) + 0.08,
        "Jin, non-irritant",
        fontsize=9,
        color=c_jin,
        weight="semibold",
    )
    ax.text(
        0.36,
        0.5,
        "Jin,\nirritant",
        fontsize=9,
        color=c_jin,
        weight="semibold",
        ha="center",
        va="top",
    )

    ax.set_xlim(0.0, k_max)
    ax.set_ylim(0.0, 1.2)
    ax.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax.set_ylabel("walking speed v [m/s]", color="dimgrey")
    ax.set_title(r"$\bf{(a)}$" + " absolute laws", loc="left", fontsize=12)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(left=True, bottom=True)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)

    handles = [
        Line2D([], [], color="grey", lw=2.6, label="within source data"),
        Line2D([], [], color="grey", lw=1.4, ls="--", label="extrapolation"),
        Line2D([], [], color="grey", lw=1.8, ls=":", label="between pooled sets"),
        Line2D(
            [], [], color=c_jin, marker="o", ls="", label="Jin non-irritant, mean ± SD"
        ),
        Line2D([], [], color=c_jin, marker="s", ls="", label="Jin irritant, mean ± SD"),
    ]
    ax.legend(
        handles=handles,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8,
        loc="upper right",
    )

    # (b) fractional laws
    ln10 = np.log(10.0)
    k_p03 = (0.13 * ln10, 0.55 * ln10)

    def purser03(k):
        return -1.738 * k / ln10 + 1.236

    ax_f.plot([0.0, k_p03[0]], [1.0, 1.0], color=c_purser, lw=1.4, ls="--")
    for lo, hi in ((k_p03[0], k_jin_ni_pts[0]), (k_jin_ni_pts[1], k_p03[1])):
        k = np.linspace(lo, hi, 20)
        ax_f.plot(k, purser03(k), color=c_purser, lw=1.4, ls="--")
    k = np.linspace(*k_jin_ni_pts, 50)
    ax_f.plot(k, purser03(k), color=c_purser, lw=2.6)
    f_floor = purser03(k_p03[1])
    ax_f.plot([k_p03[1], k_max], [f_floor, f_floor], color=c_purser, lw=1.4, ls="--")
    ax_f.text(
        2.0,
        f_floor + 0.03,
        "Purser 2003: 'as in darkness', Jin's reference\nline for darkness, not measured",
        fontsize=8,
        color="dimgrey",
    )
    ax_f.text(
        1.45,
        0.48,
        "Purser 2003,\nfit to Jin\n(OD/m 0.13–0.55)",
        fontsize=9,
        color=c_purser,
        weight="semibold",
    )

    def fds_evac(k):
        return np.maximum(0.1, 1.0 - 0.057 / 0.706 * k)

    k = np.linspace(0.0, k_fn[0], 100)
    ax_f.plot(k, fds_evac(k), color=c_fn, lw=1.4, ls="--")
    k = np.linspace(*k_fn, 100)
    ax_f.plot(k, fds_evac(k), color=c_fn, lw=2.6)
    k = np.linspace(k_fn[1], k_max, 50)
    ax_f.plot(k, fds_evac(k), color=c_fn, lw=1.4, ls="--")
    ax_f.text(
        3.9,
        fds_evac(3.9) + 0.05,
        "FDS+Evac Eq. 11\n(Frantzich–Nilsson / 0.706)",
        fontsize=9,
        color=c_fn,
        weight="semibold",
    )
    ax_f.set_xlim(0.0, k_max)
    ax_f.set_ylim(0.0, 1.1)
    ax_f.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax_f.set_ylabel("fraction of unexposed speed [-]", color="dimgrey")
    ax_f.set_title(r"$\bf{(b)}$" + " fractional laws", loc="left", fontsize=12)
    ax_f.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax_f.grid(False)
    sns.despine(left=True, bottom=True)
    ax_f.patch.set_edgecolor("lightgrey")
    ax_f.patch.set_linewidth(0.8)

    # --- Save ---
    fig.savefig(out / "speed_extinction.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
