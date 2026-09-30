# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Purser's fractional walking speed in irritant smoke against FIC.

The curve is SFPE Handbook Ch. 70, Eq. 70.11 (Purser and McAllister 2026,
p. 2289):

    F_wvirr = (exp(-(1000 x / b)^2) + (-0.2 x + 0.2)) / 1.2,
    b = 160, x = FIC.

It reproduces Ch. 70 Fig. 70.11 and Purser (2003) Fig. 1. The form printed
in Purser (2003, p. 100),
1 - ((1 - exp(-(x/b)^a)) + (-0.2 x + 0.2)/1.2) with a = 2, b = 160,
gives 0.83 at FIC = 0 for every scaling of x, because the linear term
alone fixes that value. With x unscaled it rises to 1 at FIC = 1; with
x scaled by 1000 in the exponent only it ends at 0 but dips to -0.10 in
between. It does not reproduce that paper's own Fig. 1 and is not drawn.

Ch. 70 calls the curve an "estimated relationship" based on a concept
(Fig. 70.11 and its text, p. 2289), and Purser (2003, p. 94) says it was "fitted between
these two extremes" (no effect at low FIC, no movement at FIC = 1). That
no walking data lie behind it is our reading, so it is drawn in the thin
style used for design rules on the other figures, not the heavy
"within source data" style. Beyond FIC = 1, outside the curve's range, it
is continued dotted to FIC = 1.2 to show where it turns negative.

Run from the repository root::

    uv run python scripts/figures/fundamentals_irritant_speed.py

Writes ``site/static/images/fundamentals/irritant_speed.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def main():
    """Plot Eq. 70.11, fractional walking speed against FIC.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/irritant_speed.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_purser = "#fc8d59"

    # --- Data ---
    def eq_63_13(fic, b=160.0):
        return (np.exp(-((1000.0 * fic / b) ** 2)) + (-0.2 * fic + 0.2)) / 1.2

    fic = np.linspace(0.0, 1.0, 501)
    fic_out = np.linspace(1.0, 1.2, 101)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=150)
    ax.plot(fic, eq_63_13(fic), color=c_purser, lw=1.4)
    ax.plot(fic_out, eq_63_13(fic_out), color=c_purser, lw=1.4, ls=":")
    ax.axhline(0.0, color="lightgrey", lw=0.8, zorder=0)
    ax.text(
        1.19,
        -0.105,
        "beyond FIC = 1: outside the range, negative",
        fontsize=8,
        color="dimgrey",
        ha="right",
    )
    for x0 in (0.1, 0.2, 0.5):
        ax.plot(x0, eq_63_13(x0), "o", color=c_purser, ms=5, mec="white")
        ax.text(
            x0 + 0.02,
            eq_63_13(x0) + 0.03,
            f"{eq_63_13(x0):.2f} at FIC = {x0:g}",
            fontsize=8,
            color="dimgrey",
        )
    ax.annotate(
        "0 at FIC = 1\n(incapacitation)",
        xy=(1.0, 0.0),
        xytext=(0.78, 0.25),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax.text(
        0.45,
        0.8,
        "Eq. 70.11, an 'estimated relationship' (Ch. 70);\n"
        "no walking data behind it (our reading)",
        fontsize=8.5,
        color="dimgrey",
    )

    ax.set_xlim(0.0, 1.21)
    ax.set_ylim(-0.13, 1.05)
    ax.set_xlabel("fractional irritant concentration FIC [-]", color="dimgrey")
    ax.set_ylabel("fractional walking speed [-]", color="dimgrey")
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(left=True, bottom=True)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)

    # --- Save ---
    fig.savefig(out / "irritant_speed.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
