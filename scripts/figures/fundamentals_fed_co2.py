# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""CO2 hyperventilation factor VCO2 against CO2 concentration.

The curves are SFPE Handbook Ch. 70 (Purser and McAllister 2026,
pp. 2306-2307):

    Eq. 70.32  VCO2 = exp(0.2496 %CO2 + 1.9086) / 6.8
    Eq. 70.33  VCO2 = exp(%CO2 / 4)
    Eq. 70.34  VCO2 = exp(0.1903 %CO2 + 2.0004) / 7.1
    Eq. 70.35  VCO2 = exp(%CO2 / 5)

Eq. 70.34 is the form FDS and FDS+Evac use (FDS User's Guide and
Korhonen 2021); Eq. 70.35 is the one in Eq. 70.38. The points are
the VCO2 values of the worked example, Table 70.14 (p. 2311): 1.442,
2.376 and 4.434 at 1.5, 3.5 and 6 % CO2. The cap is Purser's limiting
value of 70 L/min for V_E x VCO2 (p. 2343), at V_E = 25 L/min.

Run from the repository root::

    uv run python scripts/figures/fundamentals_fed_co2.py

Writes ``site/static/images/fundamentals/fed_co2.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def main():
    """Plot Eqs. 70.32-70.35, the Table 70.14 points and the 70 L/min cap.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/fed_co2.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    c_fit, c_ch63, c_fds = "#d73027", "#fc8d59", "#4575b4"

    # --- Data ---
    co2 = np.linspace(0.0, 10.0, 401)
    curves = [
        (
            "Eq. 70.32 (regression)",
            np.exp(0.2496 * co2 + 1.9086) / 6.8,
            dict(color=c_fit, lw=1.8, ls="-", marker="o"),
        ),
        (
            "Eq. 70.33 = exp(%CO₂/4)",
            np.exp(co2 / 4.0),
            dict(color=c_fit, lw=1.4, ls=":", marker=None),
        ),
        (
            "Eq. 70.34 (FDS, FDS+Evac)",
            np.exp(0.1903 * co2 + 2.0004) / 7.1,
            dict(color=c_fds, lw=1.8, ls="-", marker="s"),
        ),
        (
            "Eq. 70.35 = exp(%CO₂/5), in Eq. 70.38",
            np.exp(co2 / 5.0),
            dict(color=c_ch63, lw=1.8, ls="-.", marker=None),
        ),
    ]
    table_co2 = np.array([1.5, 3.5, 6.0])
    table_v = np.array([1.442, 2.376, 4.434])
    cap = 70.0 / 25.0
    for label, v, _ in curves:
        print(f"{label}: cap {cap:.1f} crossed at {np.interp(cap, v, co2):.2f} %")
    print("Eq. 70.32 at table points:", np.exp(0.2496 * table_co2 + 1.9086) / 6.8)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    for label, v, style in curves:
        ax.plot(co2, v, label=label, markevery=40, ms=4.5, mec="white", **style)
    ax.plot(
        table_co2,
        table_v,
        "D",
        color="#1f253f",
        ms=6,
        mec="white",
        zorder=5,
        label="Table 70.14 worked example",
    )
    ax.axhline(cap, color="grey", lw=1.0, ls=(0, (1, 2)), zorder=1)
    ax.text(
        9.9,
        cap - 0.2,
        "cap 2.8: V_E·VCO₂ ≤ 70 L/min\nat V_E = 25 L/min",
        fontsize=8,
        color="dimgrey",
        ha="right",
        va="top",
    )
    ax.text(
        0.15,
        12.3,
        "Eqs. 70.34 and 70.35 nearly coincide and reach the cap near 5 %;\n"
        "the worked example follows the steeper Eq. 70.32",
        fontsize=8.5,
        color="dimgrey",
        va="top",
    )

    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 12.5)
    ax.set_xlabel("CO₂ [% by volume]", color="dimgrey")
    ax.set_ylabel("VCO₂ [-]", color="dimgrey")
    ax.legend(
        loc="center left",
        bbox_to_anchor=(0.0, 0.55),
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
    fig.savefig(out / "fed_co2.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
