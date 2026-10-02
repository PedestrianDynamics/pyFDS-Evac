# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""CO FED rate against CO concentration for three activity levels and ISO.

The Stewart form is SFPE Handbook Ch. 70, Eq. 70.16 (Purser and McAllister
2026, p. 2297), as a rate per minute:

    dF_ICO/dt = 3.317e-5 [CO]^1.036 V_E / D,

with (V_E [L/min], D [% COHb]) = (8.5, 40) at rest, (25, 30) for light work
and (50, 20) for heavy work (table under Eq. 70.16, p. 2298; V_E from the
table beside Eq. 70.48, p. 2343). The ISO 13571 CO term is the dose
35 000 ppm min, i.e. the rate [CO] / 35 000, which Ch. 70 equates to light
work at about 20 L/min (Note 2 to Eq. 70.16, p. 2344).

Run from the repository root::

    uv run python scripts/figures/fundamentals_fed_co.py

Writes ``site/static/images/fundamentals/fed_co.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def main():
    """Plot the CO FED rate on log-log axes, Stewart form against ISO.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/fed_co.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    c_iso = "#d73027"

    # --- Data ---
    def stewart(c, v_e, d):
        return 3.317e-5 * c**1.036 * v_e / d

    co = np.logspace(2.0, 4.0, 201)
    levels = [
        ("heavy work: V_E 50 L/min, D 20 %", 50.0, 20.0, pal[5], "^"),
        ("light work: V_E 25 L/min, D 30 %", 25.0, 30.0, pal[3], "o"),
        ("rest: V_E 8.5 L/min, D 40 %", 8.5, 40.0, pal[1], "s"),
    ]
    iso = co / 35000.0
    for label, v_e, d, _, _ in levels:
        print(f"{label}: {stewart(1000.0, v_e, d):.4f} /min at 1000 ppm")
    print(f"ISO: {1000.0 / 35000.0:.4f} /min at 1000 ppm")
    ratio = stewart(1000.0, 50.0, 20.0) / stewart(1000.0, 8.5, 40.0)
    print(f"heavy / rest = {ratio:.2f}")
    for c0 in (100.0, 1000.0, 10000.0):
        v_match = (c0 / 35000.0) / stewart(c0, 1.0, 30.0)
        print(f"ISO = Stewart (D 30 %) at V_E {v_match:.1f} L/min, {c0:.0f} ppm")

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    for label, v_e, d, color, marker in levels:
        ax.plot(
            co,
            stewart(co, v_e, d),
            color=color,
            lw=1.8,
            marker=marker,
            markevery=25,
            ms=5,
            mec="white",
            label=label,
        )
    ax.plot(co, iso, color=c_iso, lw=1.4, ls="-.", label="ISO 13571: C / 35 000")

    ax.annotate(
        "",
        xy=(3000.0, stewart(3000.0, 50.0, 20.0)),
        xytext=(3000.0, stewart(3000.0, 8.5, 40.0)),
        arrowprops=dict(arrowstyle="<->", color="dimgrey", lw=0.8),
    )
    ax.text(
        3300.0,
        0.22,
        f"× {ratio:.0f}",
        va="center",
        fontsize=8.5,
        color="dimgrey",
    )
    ax.text(
        0.02,
        0.97,
        f"Activity changes the rate about {ratio:.0f}-fold;\n"
        "ISO's dose sits near light work at about 20 L/min",
        transform=ax.transAxes,
        va="top",
        fontsize=8.5,
        color="dimgrey",
    )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(100.0, 10000.0)
    ax.set_xlabel("CO [ppm]", color="dimgrey")
    ax.set_ylabel("CO FED rate [1/min]", color="dimgrey")
    ax.legend(
        loc="lower right",
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
    fig.savefig(out / "fed_co.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
