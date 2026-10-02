# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Jin and Yamada (1985): reading a sign through irritant smoke.

Every curve is computed from equations and constants printed in the source:

- Jin and Yamada (1985), Eq. 3 (p. 86): relative visual acuity
  S = 0.133 - 1.47 log10 K for K >= 0.25 1/m, fitted to Fig. 8. The log is
  base 10 in our reading: S(0.25) is then 1.02, continuous with S = 1 below
  0.25 1/m, and Fig. 8 is drawn on a log axis. Its points span about
  K = 0.24-0.55 1/m (our reading of Fig. 8), so the fit is solid there;
  S = 1 below 0.25 1/m is solid too, as Fig. 6 has measured ratios near 1
  at K of about 0-0.24 1/m.
- Their Eqs. 4-5 (p. 86): V1 = C/K for 0.1 <= K < 0.25 (non-irritant region)
  and V2 = (C/K) S for K >= 0.25 (irritant region), with C = 6 to match the
  legibility data of their Fig. 2 (p. 87). They state the equations do not
  apply for K < 0.1 or where V2 < 0; V2 reaches zero at K = 10**(0.133/1.47),
  about 1.23 1/m (our arithmetic).
- The line C/K with C = 6 is drawn solid over the non-irritant legibility
  points, about K = 0.53-0.70 1/m in their Fig. 2 and up to about
  1.05 1/m with the blackout runs of Jin (1972, Fig. 5) (our reading), and
  the irritant V2 over the irritant legibility points of Fig. 2, about
  0.40-0.55 1/m.

Run from the repository root::

    uv run python scripts/figures/fundamentals_visibility_irritant.py

Writes ``site/static/images/fundamentals/visibility_irritant.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec
from matplotlib.lines import Line2D


def main():
    """Plot Jin and Yamada's acuity factor (a) and legibility distance (b).

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/visibility_irritant.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_non, c_irr = "#4575b4", "#d73027"

    # --- Data ---
    c = 6.0
    k_zero = 10 ** (0.133 / 1.47)

    def acuity(k):
        return np.where(k < 0.25, 1.0, 0.133 - 1.47 * np.log10(k))

    def segments(ax, f, spans, color):
        for (lo, hi), ls in spans:
            k = np.geomspace(lo, hi, 200)
            lw = 2.6 if ls == "-" else 1.4
            ax.plot(k, f(k), color=color, lw=lw, ls=ls, zorder=4)

    s_spans = [((0.1, 0.25), "-"), ((0.25, 0.55), "-"), ((0.55, k_zero), "--")]
    v_spans = [((0.1, 0.4), "--"), ((0.4, 0.55), "-"), ((0.55, k_zero), "--")]

    # --- Plot ---
    fig = plt.figure(figsize=(11.0, 4.6), dpi=150)
    gs = gridspec.GridSpec(1, 2)
    gs.update(wspace=0.16, left=0.07, right=0.99, top=0.9, bottom=0.13)
    ax_s = plt.subplot(gs[0, 0])
    ax_v = plt.subplot(gs[0, 1])

    # (a) relative visual acuity
    segments(ax_s, acuity, s_spans, c_irr)
    ax_s.axvline(0.25, color="lightgrey", lw=0.8, zorder=1)
    ax_s.text(
        0.24,
        0.08,
        "0.25 1/m:\nacuity ratio\nstarts to fall\n(p. 85)",
        fontsize=8,
        color="dimgrey",
        ha="right",
    )
    ax_s.text(
        0.3,
        0.95,
        "S = 0.133 − 1.47 log₁₀ K\n(Eq. 3, fit to Fig. 8)",
        fontsize=9,
        color=c_irr,
        weight="semibold",
    )
    ax_s.plot(k_zero, 0.0, "o", color=c_irr, ms=6, mec="white", zorder=5)
    ax_s.text(
        k_zero,
        0.07,
        "S = 0 at\n1.23 1/m",
        fontsize=8,
        color="dimgrey",
        ha="center",
    )
    ax_s.set_ylim(0.0, 1.15)
    ax_s.set_ylabel("relative visual acuity S [–]", color="dimgrey")
    ax_s.set_title(
        r"$\bf{(a)}$" + " eyes lose acuity in irritant smoke", loc="left", fontsize=12
    )

    # (b) legibility distance
    segments(
        ax_v,
        lambda k: c / k,
        [((0.1, 0.53), "--"), ((0.53, 1.05), "-"), ((1.05, 2.0), "--")],
        c_non,
    )
    segments(ax_v, lambda k: c / k * acuity(k), v_spans, c_irr)
    ax_v.text(
        0.75, 10.5, "non-irritant: V = 6/K", fontsize=9, color=c_non, weight="semibold"
    )
    ax_v.text(
        0.13,
        5.0,
        "irritant:\nV = (6/K) S",
        fontsize=9,
        color=c_irr,
        weight="semibold",
    )
    ax_v.annotate(
        "at 0.5 1/m: 12 m without\nirritation, 6.9 m with it",
        xy=(0.5, c / 0.5 * float(acuity(np.array(0.5)))),
        xytext=(0.62, 20.0),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax_v.set_ylim(0.0, 40.0)
    ax_v.set_ylabel("distance at which the words can be read [m]", color="dimgrey")
    ax_v.set_title(
        r"$\bf{(b)}$" + " legibility of an exit sign, C = 6", loc="left", fontsize=12
    )

    for ax in (ax_s, ax_v):
        ax.set_xscale("log")
        ax.set_xlim(0.1, 2.0)
        ax.set_xticks([0.1, 0.2, 0.3, 0.5, 1.0, 2.0])
        ax.set_xticklabels(["0.1", "0.2", "0.3", "0.5", "1", "2"])
        ax.set_xlabel("extinction coefficient K [1/m]", color="dimgrey")
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.grid(False)
    sns.despine(left=True, bottom=True)
    for ax in (ax_s, ax_v):
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)

    handles = [
        Line2D([], [], color="grey", lw=2.6, label="within source data"),
        Line2D([], [], color="grey", lw=1.4, ls="--", label="extrapolation"),
    ]
    ax_v.legend(
        handles=handles,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8,
        loc="upper right",
    )

    # --- Save ---
    fig.savefig(out / "visibility_irritant.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
