# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""Heat tolerance times of ISO 13571:2012 clause 8 against SFPE Ch. 63.

Radiant (panel a), time in minutes at radiant flux q [kW/m2]:

    ISO Eq. (7), second-degree burns:  t = 6.9 q^-1.56   (§8.2)
    ISO Eq. (8), pain:                 t = 4.2 q^-1.9    (§8.2)
    SFPE Eq. 63.43:                    t = r / q^1.33, r = 1.33 (pain),
                                       4.0-12.2 (second-degree burns),
                                       16.7 (third-degree burns) (p. 2382)

Convective (panel b), time in minutes at air temperature T [deg C]:

    ISO Eq. (9), fully clothed:        t = 4.1e8 T^-3.61  (§8.3.1)
    ISO Eq. (10), unclothed or lightly
    clothed; identical to Eq. 63.44:   t = 5e7 T^-3.4     (§8.3.2; p. 2382)
    SFPE Eqs. 63.45-63.47 (tolerance, injury, fatal)      (pp. 2382-2383)

Points: Table 63.20 (p. 2383), radiant 2.5 kW/m2 -> 30 s and
10 kW/m2 -> 4 s; convective, < 10 % H2O, 100/120/140/160/180 deg C ->
12/7/4/2/1 min. Neither source states the data range of its fits; lines
are solid over the span of these tabulated points and dashed outside it.
The ISO constants are typed in here from the clause numbers above; the
script reads no standard.

Run from the repository root::

    uv run python scripts/figures/fundamentals_heat_iso.py

Writes ``site/static/images/fundamentals/heat_iso.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.ticker import FuncFormatter, NullFormatter


def main():
    """Plot radiant and convective tolerance times, ISO against SFPE.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/heat_iso.png
        150 dpi PNG.
    """
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    c_iso = "#d73027"
    c_iso2 = "#fc8d59"

    # --- Data ---
    def split(x, lo, hi):
        inside = (x >= lo) & (x <= hi)
        return np.where(inside, x, np.nan), np.where(inside, np.nan, x)

    q = np.logspace(np.log10(2.5), np.log10(20.0), 301)
    q_in, _ = split(q, 2.5, 10.0)
    q_out = np.where(q >= 10.0, q, np.nan)
    rad = [
        ("ISO Eq. (7), 2nd-degree burns", lambda x: 6.9 * x**-1.56, c_iso, "-", "o"),
        ("ISO Eq. (8), pain", lambda x: 4.2 * x**-1.9, c_iso2, "-", "s"),
        (
            "SFPE Eq. 63.43, r = 16.7 (3rd-degree)",
            lambda x: 16.7 / x**1.33,
            pal[5],
            "--",
            None,
        ),
        (
            "SFPE Eq. 63.43, r = 1.33 (pain)",
            lambda x: 1.33 / x**1.33,
            pal[2],
            "--",
            None,
        ),
    ]
    band = (4.0 / q**1.33, 12.2 / q**1.33)

    temp = np.linspace(60.0, 250.0, 400)
    t_in, _ = split(temp, 100.0, 180.0)
    t_lo = np.where(temp <= 100.0, temp, np.nan)
    t_hi = np.where(temp >= 180.0, temp, np.nan)
    conv = [
        ("ISO Eq. (9), fully clothed", lambda x: 4.1e8 * x**-3.61, c_iso, "-", "o"),
        ("ISO Eq. (10) = SFPE Eq. 63.44", lambda x: 5e7 * x**-3.4, c_iso2, "-", "s"),
        (
            "SFPE Eq. 63.47, fatal",
            lambda x: 2e18 * x**-9.0403 + 1e8 * x**-3.10898,
            pal[5],
            "--",
            None,
        ),
        (
            "SFPE Eq. 63.46, injury",
            lambda x: 5e22 * x**-11.783 + 3e7 * x**-2.9636,
            pal[3],
            "--",
            None,
        ),
        (
            "SFPE Eq. 63.45, tolerance",
            lambda x: 2e31 * x**-16.963 + 4e8 * x**-3.7561,
            pal[1],
            "--",
            None,
        ),
    ]

    for q0 in (2.5, 10.0):
        print(
            f"q={q0}: Eq7 {6.9 * q0**-1.56 * 60:.1f} s, Eq8 {4.2 * q0**-1.9 * 60:.1f} s,"
            f" r(Eq7) {6.9 * q0**-1.56 * q0**1.33:.2f},"
            f" r(Eq8) {4.2 * q0**-1.9 * q0**1.33:.2f}"
        )
    for t0 in (100.0, 180.0):
        print(f"T={t0}: Eq9 {4.1e8 * t0**-3.61:.1f} min, Eq10 {5e7 * t0**-3.4:.2f} min")

    # --- Plot ---
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), dpi=150)
    ax = axes[0]
    ax.fill_between(q, *band, color=pal[3], alpha=0.18, lw=0)
    ax.text(
        14.0,
        0.24,
        "SFPE 2nd-degree\nband, r = 4.0–12.2",
        fontsize=8,
        color="dimgrey",
        va="center",
        ha="center",
    )
    for label, f, color, ls, marker in rad:
        ax.plot(
            q_in,
            f(q_in),
            color=color,
            lw=1.8,
            ls=ls,
            marker=marker,
            markevery=40,
            ms=5,
            mec="white",
            label=label,
        )
        ax.plot(q_out, f(q_out), color=color, lw=1.0, ls=":")
    ax.scatter(
        [2.5, 10.0],
        [0.5, 4.0 / 60.0],
        marker="D",
        s=40,
        color="black",
        zorder=5,
        label="Table 63.20",
    )
    ax.text(
        0.97,
        0.97,
        "ISO pain ≈ SFPE pain;\nISO burns at the low end\nof the SFPE band",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color="dimgrey",
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(2.3, 21.0)
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks([2.5, 5, 10, 20])
    ax.set_xticklabels(["2.5", "5", "10", "20"])
    ax.set_xlabel("Radiant heat flux q [kW/m²]", color="dimgrey")
    ax.set_ylabel("Time to endpoint [min]", color="dimgrey")
    ax.set_title(r"$\bf{(a)}$" + " Radiant heat", loc="left", fontsize=11, pad=7)

    ax = axes[1]
    for label, f, color, ls, marker in conv:
        ax.plot(
            t_in,
            f(t_in),
            color=color,
            lw=1.8,
            ls=ls,
            marker=marker,
            markevery=40,
            ms=5,
            mec="white",
            label=label,
        )
        ax.plot(t_lo, f(t_lo), color=color, lw=1.0, ls=":")
        ax.plot(t_hi, f(t_hi), color=color, lw=1.0, ls=":")
    ax.scatter(
        [100, 120, 140, 160, 180],
        [12, 7, 4, 2, 1],
        marker="D",
        s=40,
        color="black",
        zorder=5,
        label="Table 63.20",
    )
    ax.text(
        0.97,
        0.97,
        "Clothed (Eq. 9) tolerates\nabout 3× longer than\nunclothed (Eq. 10)",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color="dimgrey",
    )
    ax.set_yscale("log")
    ax.set_xlim(60.0, 250.0)
    ax.set_xlabel("Air temperature T [°C], < 10 % water vapour", color="dimgrey")
    ax.set_ylabel("Time to endpoint [min]", color="dimgrey")
    ax.set_title(r"$\bf{(b)}$" + " Convective heat", loc="left", fontsize=11, pad=7)

    for ax in axes:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.plot([], [], color="grey", lw=1.0, ls=":", label="outside Table 63.20 span")
        ax.legend(
            loc="lower left",
            fontsize=7.5,
            frameon=True,
            facecolor="white",
            framealpha=0.8,
            edgecolor="lightgrey",
            labelcolor="dimgrey",
        )
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.grid(False)
    sns.despine(left=True, bottom=True)
    for ax in axes:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    fig.tight_layout()

    # --- Save ---
    fig.savefig(out / "heat_iso.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
