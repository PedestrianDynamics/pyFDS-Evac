# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Jin's visibility law: where the constant C comes from, and V = C/K.

Every curve is computed from equations and constants printed in the sources:

- Jin (1970), Eq. (4): sigma V = ln(B_E0 / (delta_c k L)), with
  delta_c = 0.01 and k = 1 for nearly white smoke (abstract and Fig. 11).
  B_E0 / L is Jin's "dimensionless brightness", written pi L_t / E by
  Cheung et al. (2026). Jin's Fig. 11 spans B_E0 / L of about 0.1-50
  (placards below 1, lit signs above), so the curve is solid there and
  dashed beyond. delta_c k = 0.02 and 0.05 are the upper values of the
  ranges given by Jin (1971, Fig. 8) and Jin and Yamada (1985, p. 80).
- Jin (1970), p. 1: visibility (2-4)/sigma for placards and (5-10)/sigma
  for lit signs.
- Cheung et al. (2026), Fig. 11: the shaded bands lie between the
  bounding curves they publish, sigma V = ln(pi L_t / E / (delta_c alpha)),
  with delta_c alpha = 0.0025-0.025 at 180 lx and 0.1-1 at 1 lx, drawn over
  the approximate extent of their data there (pi L_t / E about 2-300 and
  300-50 000; our reading of the axes). The 22 and 60 lx pairs are given
  in the page text.
- Panel (b): V = C/K. Lines are solid for 5.5-15.5 m, the viewing
  distances of Jin's chamber (Jin 1970); dashed beyond. Cheung et al.'s
  top value, sigma V of about 11, occurs only at 5.5 m (their Fig. 11a-b),
  so it is drawn as one point. C = 3 and 8
  are the values of Mulholland (2002, Eqs. 14-15) and the FDS User's Guide
  (Eq. 22.23); 30 m is the FDS default MAXIMUM_VISIBILITY.

Run from the repository root::

    uv run python scripts/figures/fundamentals_visibility_constant.py

Writes ``site/static/images/fundamentals/visibility_constant.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec
from matplotlib.lines import Line2D


def main():
    """Plot Jin's contrast model (a) and V = C/K with its constants (b).

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/visibility_constant.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    c_jin, c_refl, c_emit = pal[5], "#4575b4", "#d73027"
    c_cheung = "#fc8d59"

    # --- Data ---
    def sigma_v(b_over_l, dk):
        return np.log(b_over_l / dk)

    b_data = (0.1, 50.0)

    # --- Plot ---
    fig = plt.figure(figsize=(12.0, 5.0), dpi=150)
    gs = gridspec.GridSpec(1, 2)
    gs.update(wspace=0.18, left=0.06, right=0.99, top=0.9, bottom=0.12)
    ax_a = plt.subplot(gs[0, 0])
    ax_b = plt.subplot(gs[0, 1])

    # (a) Jin's contrast model
    ax_a.axhspan(2.0, 4.0, color=c_refl, alpha=0.12, lw=0)
    ax_a.axhspan(5.0, 10.0, color=c_emit, alpha=0.10, lw=0)
    ax_a.text(0.035, 3.0, "placards\n2–4", fontsize=8.5, color=c_refl, va="center")
    ax_a.text(0.035, 9.0, "lit signs\n5–10", fontsize=8.5, color=c_emit, va="center")
    ax_a.axvline(1.0, color="lightgrey", lw=0.8, zorder=1)
    ax_a.text(
        1.1,
        0.3,
        "reflectance 1:\nbest placard",
        fontsize=8,
        color="dimgrey",
        ha="left",
    )

    for lo, hi, ls, lw in (
        (0.03, b_data[0], "--", 1.4),
        (*b_data, "-", 2.6),
        (b_data[1], 5e4, "--", 1.4),
    ):
        b = np.geomspace(lo, hi, 200)
        ax_a.plot(b, sigma_v(b, 0.01), color=c_jin, lw=lw, ls=ls, zorder=4)
    for dk in (0.02, 0.05):
        b = np.geomspace(0.03, 5e4, 200)
        ax_a.plot(b, sigma_v(b, dk), color=c_jin, lw=0.9, ls=":", zorder=3)
        ax_a.text(
            0.2,
            sigma_v(0.2, dk) - 0.15,
            f"{dk:g}",
            fontsize=7.5,
            color="dimgrey",
            ha="left",
            va="top",
        )
    ax_a.annotate(
        "Jin 1970, Eq. 4, δc k = 0.01",
        xy=(3.0, sigma_v(3.0, 0.01)),
        xytext=(0.04, 11.3),
        fontsize=9,
        color=c_jin,
        weight="semibold",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    for c, col in ((3.0, c_refl), (8.0, c_emit)):
        b = 0.01 * np.exp(c)
        ax_a.plot(b, c, "o", color=col, ms=7, mec="white", zorder=5)
    ax_a.annotate(
        "",
        xy=(0.01 * np.exp(8.0), 8.0),
        xytext=(0.01 * np.exp(3.0), 3.0),
        arrowprops=dict(arrowstyle="->", color="dimgrey", lw=0.9),
    )
    ax_a.text(
        0.04,
        6.3,
        "C = 3 → 8 on this curve:\nabout 150× the\nsign-to-light ratio",
        fontsize=8,
        color="dimgrey",
        ha="left",
    )

    for (lo_dk, hi_dk, b0, b1), label, ytxt in (
        ((0.0025, 0.025, 2.0, 300.0), "Cheung 180 lx", (2.2, 3.7, "left")),
        ((0.1, 1.0, 300.0, 5e4), "Cheung 1 lx", (4.5e4, 8.9, "right")),
    ):
        b = np.geomspace(b0, b1, 100)
        ax_a.fill_between(
            b,
            sigma_v(b, hi_dk),
            sigma_v(b, lo_dk),
            color=c_cheung,
            alpha=0.25,
            lw=0,
            zorder=2,
        )
        for dk in (lo_dk, hi_dk):
            ax_a.plot(b, sigma_v(b, dk), color=c_cheung, lw=1.0, zorder=2)
        ax_a.text(ytxt[0], ytxt[1], label, fontsize=8, color=c_cheung, ha=ytxt[2])
    ax_a.text(
        2.0,
        11.75,
        "Cheung et al. 2026, published bounds",
        fontsize=8,
        color=c_cheung,
    )

    ax_a.set_xscale("log")
    ax_a.set_xlim(0.03, 5e4)
    ax_a.set_ylim(0.0, 12.5)
    ax_a.set_xlabel("sign-to-light ratio  B/L = π Lₜ / E  [–]", color="dimgrey")
    ax_a.set_ylabel("C = K V at the obscuration threshold [–]", color="dimgrey")
    ax_a.set_title(
        r"$\bf{(a)}$" + " the constant follows the log of brightness",
        loc="left",
        fontsize=12,
    )

    # (b) V = C / K
    k = np.geomspace(0.05, 3.0, 400)
    v_lo, v_hi = 5.5, 15.5
    for c_lo, c_hi, col in ((2.0, 4.0, c_refl), (5.0, 10.0, c_emit)):
        lower = np.maximum(c_lo / k, v_lo)
        upper = np.minimum(c_hi / k, v_hi)
        ax_b.fill_between(
            k, lower, upper, where=upper > lower, color=col, alpha=0.12, lw=0
        )
    for c, col, lw in ((3.0, c_refl, 2.6), (8.0, c_emit, 2.6)):
        v = c / k
        inside = (v >= v_lo) & (v <= v_hi)
        ax_b.plot(k, np.where(inside, v, np.nan), color=col, lw=lw, zorder=4)
        ax_b.plot(k, np.where(~inside, v, np.nan), color=col, lw=1.2, ls="--")
    ax_b.text(0.55, 3.6, "C = 3", fontsize=9, color=c_refl, weight="semibold")
    ax_b.text(1.25, 8.4, "C = 8", fontsize=9, color=c_emit, weight="semibold")
    ax_b.plot(11.0 / 5.5, 5.5, "D", color=c_cheung, ms=7, mec="white", zorder=5)
    ax_b.annotate(
        "C ≈ 11: Cheung et al., 1–22 lx,\nonly at 5.5 m, signs up to 22 500 cd/m²",
        xy=(2.0, 5.5),
        xytext=(2.9, 2.2),
        fontsize=8,
        color=c_cheung,
        ha="right",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax_b.text(0.06, 21.0, "placards 2–4", fontsize=8, color=c_refl)
    ax_b.text(0.33, 36.0, "lit signs 5–10", fontsize=8, color=c_emit)

    ax_b.axhline(30.0, color="grey", lw=0.8, ls=":", zorder=1)
    ax_b.text(2.9, 31.5, "FDS cap, 30 m", fontsize=8, color="dimgrey", ha="right")
    for v in (v_lo, v_hi):
        ax_b.axhline(v, color="lightgrey", lw=0.8, zorder=1)
    ax_b.text(
        0.055,
        9.0,
        "5.5–15.5 m:\nJin's viewing\ndistances",
        fontsize=8,
        color="dimgrey",
        va="center",
    )

    ax_b.set_xscale("log")
    ax_b.set_yscale("log")
    ax_b.set_xlim(0.05, 3.0)
    ax_b.set_ylim(1.0, 60.0)
    ax_b.set_yticks([1, 2, 5, 10, 20, 30, 50])
    ax_b.set_yticklabels(["1", "2", "5", "10", "20", "30", "50"])
    ax_b.set_xticks([0.05, 0.1, 0.2, 0.5, 1.0, 2.0])
    ax_b.set_xticklabels(["0.05", "0.1", "0.2", "0.5", "1", "2"])
    ax_b.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
    ax_b.set_ylabel("visibility V [m]", color="dimgrey")
    ax_b.set_title(r"$\bf{(b)}$" + " V = C / K", loc="left", fontsize=12)

    for ax in (ax_a, ax_b):
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.grid(False)
    sns.despine(left=True, bottom=True)
    for ax in (ax_a, ax_b):
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)

    handles = [
        Line2D([], [], color="grey", lw=2.6, label="within source data"),
        Line2D([], [], color="grey", lw=1.4, ls="--", label="extrapolation"),
        Line2D([], [], color="grey", lw=0.9, ls=":", label="δc k = 0.02, 0.05 (Jin)"),
    ]
    ax_a.legend(
        handles=handles,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8,
        loc="lower right",
    )

    # --- Save ---
    fig.savefig(out / "visibility_constant.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
