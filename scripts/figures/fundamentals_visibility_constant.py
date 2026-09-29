# /// script
# requires-python = ">=3.11"
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
- Cheung et al. (2026), Fig. 11: the boxes mark the approximate extent of
  their data at 1, 22 and 180 lx, read from the printed axes (our reading):
  pi L_t / E about 300-50 000, 20-3000 and 2-300; sigma V 7.5-11 (§4.4),
  6-11 (§4.4) and 4.7-9.5 (§6). These span sign luminances up to
  22 500 cd/m² (§4.1); C = 11 in panel (b) is their upper end.
- Panel (b): V = C/K. Lines are solid for 5-15.5 m, the viewing distances
  of Jin's chamber (Jin 1970, 5.5, 10.5 and 15.5 m) and the range in which
  Jin (1971) states sigma V is almost constant; dashed beyond. C = 3 and 8
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
from matplotlib.patches import Rectangle


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
        0.95,
        0.6,
        "reflectance 1:\nbest placard",
        fontsize=8,
        color="dimgrey",
        ha="right",
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

    for (x0, x1, y0, y1), label in (
        ((2.0, 300.0, 4.7, 9.5), "180 lx"),
        ((20.0, 3000.0, 6.0, 11.0), "22 lx"),
        ((300.0, 5e4, 7.5, 11.0), "1 lx"),
    ):
        ax_a.add_patch(
            Rectangle(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                fill=False,
                ec=c_cheung,
                lw=1.2,
                ls="-",
                zorder=2,
            )
        )
        ax_a.text(x1 / 1.15, y0 + 0.15, label, fontsize=7.5, color=c_cheung, ha="right")
    ax_a.text(
        2.0,
        11.75,
        "Cheung et al. 2026, extent of data",
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
    v_lo, v_hi = 5.0, 15.5
    for c_lo, c_hi, col in ((2.0, 4.0, c_refl), (5.0, 10.0, c_emit)):
        lower = np.maximum(c_lo / k, v_lo)
        upper = np.minimum(c_hi / k, v_hi)
        ax_b.fill_between(
            k, lower, upper, where=upper > lower, color=col, alpha=0.12, lw=0
        )
    for c, col, lw in ((3.0, c_refl, 2.6), (8.0, c_emit, 2.6), (11.0, c_cheung, 1.2)):
        v = c / k
        inside = (v >= v_lo) & (v <= v_hi)
        ax_b.plot(k, np.where(inside, v, np.nan), color=col, lw=lw, zorder=4)
        ax_b.plot(k, np.where(~inside, v, np.nan), color=col, lw=1.2, ls="--")
    ax_b.text(0.55, 3.6, "C = 3", fontsize=9, color=c_refl, weight="semibold")
    ax_b.text(1.25, 8.4, "C = 8", fontsize=9, color=c_emit, weight="semibold")
    ax_b.text(
        2.9,
        18.0,
        "C = 11: Cheung et al., 1–22 lx,\nupper end, signs up to 22 500 cd/m²",
        fontsize=8,
        color=c_cheung,
        ha="right",
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
        "5–15.5 m:\nJin's viewing\ndistances",
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
        Line2D([], [], color="grey", lw=0.9, ls=":", label="δc k = 0.02, 0.05"),
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
