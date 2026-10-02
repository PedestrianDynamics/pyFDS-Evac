# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Time to incapacitation by low oxygen against O2 concentration.

The curve is SFPE Handbook Ch. 70 (Purser and McAllister 2026), derived in
Eq. 70.25 and used in Eq. 70.50:

    t_IO = exp(8.13 - 0.54 (20.9 - %O2)),   t in minutes.

It is derived from the time of useful consciousness of resting humans after
sudden decompression to 20 000-40 000 ft, a sea-level equivalent of 9.6 %
down to 3.9 % O2 (Fig. 70.19, p. 2305); the curve is solid there and
dashed above. The vertical lines mark 15 % O2, down to which there is
little effect in humans (p. 2303), and 20 % O2, at or above which FDS
(``func.f90``, function ``FED``) drops the O2 term, quoted here, not
imported.

Run from the repository root::

    uv run python scripts/figures/fundamentals_fed_o2.py

Writes ``site/static/images/fundamentals/fed_o2.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def main():
    """Plot the low-oxygen time to incapacitation on a log time axis.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/fed_o2.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_ch63 = "#fc8d59"

    # --- Data ---
    def t_io(o2):
        return np.exp(8.13 - 0.54 * (20.9 - o2))

    o2_lo, o2_hi = 3.9, 9.6
    o2 = np.linspace(o2_lo, 20.9, 681)
    inside = o2 <= o2_hi
    for o0 in (3.9, 9.6, 15.0, 20.0, 20.9):
        print(f"{o0:4.1f} % O2: t_IO = {t_io(o0):8.1f} min")

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    ax.axvspan(o2_lo, o2_hi, color="lightgrey", alpha=0.35, lw=0, zorder=0)
    ax.text(
        (o2_lo + o2_hi) / 2,
        3000.0,
        "decompression data\n3.9–9.6 % O₂",
        ha="center",
        va="top",
        fontsize=8,
        color="dimgrey",
    )
    ax.plot(o2[inside], t_io(o2[inside]), color=c_ch63, lw=2.4, label="within data")
    ax.plot(
        o2[~inside],
        t_io(o2[~inside]),
        color=c_ch63,
        lw=1.4,
        ls="--",
        label="extrapolation",
    )

    for x0, text, ls, y_text in (
        (15.0, "15 %: little effect\nin humans (p. 2303)", ":", 0.45),
        (20.0, "20 %: FDS zeroes\nthe term at or above", "-.", 0.13),
    ):
        ax.axvline(x0, color="grey", lw=1.0, ls=ls, zorder=1)
        ax.plot(x0, t_io(x0), "o", color=c_ch63, ms=5, mec="white", zorder=5)
        ax.annotate(
            f"{t_io(x0):,.0f} min",
            xy=(x0, t_io(x0)),
            xytext=(-6, 4),
            textcoords="offset points",
            ha="right",
            fontsize=8,
            color="dimgrey",
        )
        ax.text(x0 - 0.2, y_text, text, ha="right", fontsize=8, color="dimgrey")

    ax.text(
        10.1,
        1.6,
        "Almost all of the O₂ range a fire simulation visits\n"
        "(above about 10 %) is extrapolation",
        fontsize=8.5,
        color="dimgrey",
    )

    ax.set_yscale("log")
    ax.set_xlim(o2_lo, 21.0)
    ax.set_ylim(0.1, 5000.0)
    ax.set_xlabel("O₂ [% by volume]", color="dimgrey")
    ax.set_ylabel("time to incapacitation $t_{IO}$ [min]", color="dimgrey")
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.0, 0.8),
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
    fig.savefig(out / "fed_o2.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
