"""Denominators of the irritant criteria, per gas, for four endpoint sets.

Values [ppm] from SFPE Handbook Ch. 70, Table 70.4 (Purser and McAllister
2026, p. 2288): SFPE escape impairment, SFPE incapacitation and AEGL-2 for
10 min; and ISO 13571:2012, §6.2.1, Eq. (4), p. 7, whose F values equal the
ISO column of Table 70.4. NO is left out: it has no escape-impairment value,
its incapacitation value is given only as ">1000", and it is not in the
FIC sum (Eq. 70.9).

Run from the repository root::

    uv run python scripts/figures/fundamentals_fic_denominators.py

Writes ``site/static/images/fundamentals/fic_denominators.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def main():
    """Plot the FIC and FEC denominators per gas on a log axis.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/fic_denominators.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data ---
    gases = ["HCl", "HBr", "HF", "SO₂", "NO₂", "acrolein", "formaldehyde"]
    sets = [
        ("SFPE escape impairment", [200, 200, 200, 24, 70, 4, 6], "#fc8d59", "o"),
        ("SFPE incapacitation", [900, 900, 900, 120, 350, 20, 30], "#d73027", "s"),
        ("ISO 13571", [1000, 1000, 500, 150, 250, 30, 250], "#4575b4", "D"),
        ("AEGL-2, 10 min", [100, 100, 95, 0.75, 20, 0.44, 14], "#7f7f7f", "^"),
    ]
    y = np.arange(len(gases))[::-1]
    offsets = np.linspace(0.24, -0.24, len(sets))

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=150)
    for i, gas_y in enumerate(y):
        values = [vals[i] for _, vals, _, _ in sets]
        ax.plot(
            [min(values), max(values)],
            [gas_y, gas_y],
            color="lightgrey",
            lw=1.0,
            zorder=0,
        )
    for (label, vals, color, marker), dy in zip(sets, offsets, strict=True):
        ax.scatter(
            vals,
            y + dy,
            color=color,
            marker=marker,
            s=42,
            edgecolor="white",
            linewidth=0.6,
            label=label,
            zorder=3,
        )
    for x0 in (900, 1000):
        ax.axvline(x0, color="dimgrey", lw=0.8, ls=":", zorder=1)
    ax.text(
        870,
        y[0] + 0.55,
        "HCl: 900 (SFPE) | 1000 ppm (ISO, Fig. 70.11)",
        fontsize=8,
        color="dimgrey",
        ha="right",
    )

    ax.set_xscale("log")
    ax.set_xlim(0.3, 3000)
    ax.set_ylim(-0.6, len(gases) - 0.2)
    ax.set_yticks(y, gases)
    ax.set_xlabel("denominator concentration [ppm], log scale", color="dimgrey")
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    ax.grid(axis="x", which="major", color="#eeeeee", lw=0.8)
    sns.despine(left=True, bottom=True)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=4,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        edgecolor="lightgrey",
    )

    # --- Save ---
    fig.savefig(out / "fic_denominators.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
