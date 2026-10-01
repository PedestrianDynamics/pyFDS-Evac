# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Time to incapacitation by HCN: Ch. 70 power law against the FDS form.

The curves are

    Eq. 70.18 (Ch. 70, p. 2301)  t_ICN = 1.2e6 / [CN]^2.36
    FDS form                     t_ICN = 220 / (exp([CN]/43) - 1)

with t in minutes and [CN] in ppm. The FDS form inverts the rate
exp(C/43)/220 - 1/220 of FDS ``func.f90`` (function ``FED``), whose offset
is 0.00454545 = 1/220; the manuals print 0.0045.

Eq. 70.18 is fitted to resting primates; the primate points of
Ch. 70 Fig. 70.18 span about 85 to 250 ppm. Both curves are solid there
and dashed outside. The shaded band is the critical range of about 80 to
180 ppm (p. 2301).

Run from the repository root::

    uv run python scripts/figures/fundamentals_fed_hcn.py

Writes ``site/static/images/fundamentals/fed_hcn.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def main():
    """Plot Eq. 70.18 and the FDS exponential form on a log time axis.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/fed_hcn.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_ch63, c_fds = "#fc8d59", "#4575b4"

    # --- Data ---
    def eq_63_20(c):
        return 1.2e6 / c**2.36

    def fds_form(c):
        return 220.0 / (np.exp(c / 43.0) - 1.0)

    c_lo, c_hi = 85.0, 250.0
    cn = np.linspace(20.0, 300.0, 561)
    inside = (cn >= c_lo) & (cn <= c_hi)
    for c0 in (100.0, 150.0, 200.0, 250.0):
        ratio = eq_63_20(c0) / fds_form(c0)
        print(
            f"{c0:.0f} ppm: {eq_63_20(c0):.2f} vs {fds_form(c0):.2f} min, {ratio:.2f}x"
        )

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    ax.axvspan(80.0, 180.0, color="lightgrey", alpha=0.35, lw=0, zorder=0)
    ax.text(
        130.0,
        0.13,
        "critical range\n80–180 ppm",
        ha="center",
        fontsize=8,
        color="dimgrey",
    )
    for fn, color, marker, ms, label in (
        (fds_form, c_fds, "s", 7, "FDS form: 220 / (exp(C/43) − 1)"),
        (eq_63_20, c_ch63, "o", 5, "Eq. 70.18: 1.2·10⁶ / C^2.36"),
    ):
        t = fn(cn)
        ax.plot(cn[inside], t[inside], color=color, lw=2.2, label=label)
        for seg in (cn < c_lo, cn > c_hi):
            ax.plot(cn[seg], t[seg], color=color, lw=1.4, ls="--")
        marks = np.array([100.0, 250.0])
        ax.plot(marks, fn(marks), marker, color=color, ms=ms, mec="white", zorder=5)

    ax.annotate(
        "at 250 ppm: 2.6 vs 0.66 min,\nthe FDS form 4× faster",
        xy=(250.0, fds_form(250.0)),
        xytext=(186.0, 0.13),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax.text(
        0.98,
        0.97,
        "Near 70–115 ppm the curves agree within 6 %;\n"
        "above 150 ppm they diverge: 2.1× at 200, 4× at 250 ppm",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color="dimgrey",
    )

    ax.set_yscale("log")
    ax.set_xlim(20.0, 300.0)
    ax.set_ylim(0.1, 5000.0)
    ax.set_xlabel("HCN [ppm]", color="dimgrey")
    ax.set_ylabel("time to incapacitation [min]", color="dimgrey")
    ax.legend(
        loc="center right",
        fontsize=8,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(left=True, bottom=True)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)

    # --- Save ---
    fig.savefig(out / "fed_hcn.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
