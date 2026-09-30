# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""The four t-squared growth classes, and the two study fires against them.

Panel (a) draws Q = alpha t^2 for the four classes of vfdb TB 04-01
(2020), Table 4.3, p. 60, and SFPE Handbook 5th ed., Eqs. 14.49-14.52:
alpha = 0.002931, 0.01172, 0.04689 and 0.1876 kW/s^2, with growth times
of 600, 300, 150 and 75 s to 1000 Btu/s (about 1055 kW). Each curve is
solid up to 1055 kW and dashed beyond, where fuel, ventilation or
suppression limit a real fire.

Panel (b) draws the heat release rate of the two study fires, which are
study inputs, not design fires:

- T-junction: HRRPUA and RAMP_Q read from ``assets/t_junction/t_junction.fds``
  (HRRPUA times the area of the FIRE vent, scaled by the ramp fraction).
- Schroeder et al. (2020): a constant 60 kW, the authors' value from their
  reference implementation (``docs/study-schroeder2020.md``, "The room").
  The deck is not in the repository, so the value is written here.

Run from the repository root::

    uv run python scripts/figures/fundamentals_design_fires.py

Writes ``site/static/images/fundamentals/design_fires.png``.
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import gridspec
from matplotlib.lines import Line2D


def read_tjunction_fire(deck):
    """Return the ramp times [s] and heat release rate [kW] of the deck.

    Parameters
    ----------
    deck : Path
        FDS input file with one SURF 'FIRE' (HRRPUA, RAMP_Q), one VENT
        using it, and the RAMP lines of that ramp.

    Returns
    -------
    tuple of numpy.ndarray
        Ramp times and HRR = HRRPUA * vent area * ramp fraction.
    """
    # Drop '!' comments: the deck's comments mention an older HRRPUA.
    text = "\n".join(line.split("!")[0] for line in deck.read_text().splitlines())
    hrrpua = float(re.search(r"HRRPUA\s*=\s*([\d.]+)", text).group(1))
    ramp_id = re.search(r"RAMP_Q\s*=\s*'([^']+)'", text).group(1)
    xb = re.search(r"&VENT\s+XB\s*=\s*([^/]*?)SURF_ID\s*=\s*'FIRE'", text).group(1)
    x0, x1, y0, y1 = (float(v) for v in xb.replace(" ", "").split(",")[:4])
    area = abs(x1 - x0) * abs(y1 - y0)
    pairs = re.findall(
        rf"&RAMP\s+ID\s*=\s*'{ramp_id}'\s*,\s*T\s*=\s*([\d.]+)\s*,\s*F\s*=\s*([\d.]+)",
        text,
    )
    t = np.array([float(a) for a, _ in pairs])
    f = np.array([float(b) for _, b in pairs])
    return t, hrrpua * area * f


def main():
    """Plot the t-squared classes (a) and the study fires against them (b).

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/fundamentals/design_fires.png
        150 dpi PNG.
    """
    root = Path(__file__).resolve().parents[2]
    out = root / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    c_classes = [pal[1], pal[2], pal[4], pal[5]]
    c_tj, c_room = "#d73027", "#fc8d59"

    # --- Data ---
    q_ref = 1055.0
    classes = (
        ("slow", 0.002931, 600),
        ("medium", 0.01172, 300),
        ("fast", 0.04689, 150),
        ("ultra-fast", 0.1876, 75),
    )
    t_tj, q_tj = read_tjunction_fire(root / "assets/t_junction/t_junction.fds")
    i = np.searchsorted(q_tj, q_ref)
    t_cross = t_tj[i - 1] + (q_ref - q_tj[i - 1]) * (t_tj[i] - t_tj[i - 1]) / (
        q_tj[i] - q_tj[i - 1]
    )

    # --- Plot ---
    fig = plt.figure(figsize=(12.0, 5.0), dpi=150)
    gs = gridspec.GridSpec(1, 2)
    gs.update(wspace=0.16, left=0.06, right=0.99, top=0.9, bottom=0.12)
    ax_a = plt.subplot(gs[0, 0])
    ax_b = plt.subplot(gs[0, 1])

    # (a) the four classes
    t_max_a, q_max_a = 700.0, 3000.0
    for (name, alpha, t_g), col in zip(classes, c_classes):
        t_in = np.linspace(0.0, t_g, 200)
        t_out = np.linspace(t_g, min(t_max_a, np.sqrt(q_max_a / alpha)), 200)
        ax_a.plot(t_in, alpha * t_in**2, color=col, lw=2.4, zorder=4)
        ax_a.plot(t_out, alpha * t_out**2, color=col, lw=1.3, ls="--", zorder=3)
        ax_a.plot(t_g, q_ref, "o", color=col, ms=6, mec="white", zorder=5)
        # ultra-fast is labelled above-left, the others below-right
        above = t_g < 100
        ax_a.text(
            t_g - 10 if above else t_g + 8,
            q_ref + 90 if above else q_ref - 120,
            f"{name}\n{t_g} s",
            fontsize=8.5,
            color=col,
            weight="semibold",
            ha="right" if above else "left",
            va="bottom" if above else "top",
        )
    ax_a.axhline(q_ref, color="grey", lw=0.8, ls=":", zorder=1)
    ax_a.text(
        420,
        q_ref + 60,
        "1055 kW = 1000 Btu/s\n(1000 kW is 5.5 % lower)",
        fontsize=8,
        color="dimgrey",
        ha="left",
        va="bottom",
    )
    ax_a.text(
        510,
        2650,
        "dashed: extrapolated;\na real fire is limited\nby fuel, ventilation\n"
        "or suppression",
        fontsize=8,
        color="dimgrey",
        ha="left",
        va="top",
    )
    ax_a.set_xlim(0, t_max_a)
    ax_a.set_ylim(0, q_max_a)
    ax_a.set_xlabel("time since established burning  t [s]", color="dimgrey")
    ax_a.set_ylabel("heat release rate  Q [kW]", color="dimgrey")
    ax_a.set_title(
        r"$\bf{(a)}$" + " Q = α t², four growth classes",
        loc="left",
        fontsize=12,
    )

    # (b) the study fires against the fast and ultra-fast classes
    t_b = np.linspace(0.0, 300.0, 400)
    for (name, alpha, t_g), col in zip(classes[2:], c_classes[2:]):
        q = alpha * t_b**2
        ax_b.plot(t_b, np.where(q <= 2500, q, np.nan), color=col, lw=1.2, ls="--")
    ax_b.text(215, 2350, "fast", fontsize=8.5, color=c_classes[2], ha="right")
    ax_b.text(104, 2350, "ultra-fast", fontsize=8.5, color=c_classes[3], ha="right")
    ax_b.plot(t_tj, q_tj, color=c_tj, lw=2.6, marker="s", ms=5, mec="white", zorder=5)
    ax_b.text(
        212,
        q_tj[-1] - 80,
        "T-junction:\nramp from the deck,\n2 MW from 90 s",
        fontsize=8.5,
        color=c_tj,
        weight="semibold",
        va="top",
    )
    ax_b.plot([0, 300], [60, 60], color=c_room, lw=2.6, zorder=5)
    ax_b.text(
        75,
        130,
        "Schröder et al. (2020): constant 60 kW (authors' value)",
        fontsize=8.5,
        color=c_room,
        weight="semibold",
    )
    ax_b.axhline(q_ref, color="grey", lw=0.8, ls=":", zorder=1)
    ax_b.plot(t_cross, q_ref, "o", color=c_tj, ms=7, mec="white", zorder=6)
    ax_b.annotate(
        f"1055 kW at {t_cross:.0f} s,\nultra-fast needs 75 s",
        xy=(t_cross, q_ref),
        xytext=(105, 620),
        fontsize=8,
        color="dimgrey",
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax_b.set_xlim(0, 300)
    ax_b.set_ylim(0, 2500)
    ax_b.set_xlabel("time since ignition in the deck  t [s]", color="dimgrey")
    ax_b.set_ylabel("heat release rate  Q [kW]", color="dimgrey")
    ax_b.set_title(
        r"$\bf{(b)}$" + " study inputs, not design fires",
        loc="left",
        fontsize=12,
    )

    for ax in (ax_a, ax_b):
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.grid(False)
    sns.despine(left=True, bottom=True)
    for ax in (ax_a, ax_b):
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)

    handles = [
        Line2D([], [], color="grey", lw=2.4, label="t² class up to its growth time"),
        Line2D([], [], color="grey", lw=1.3, ls="--", label="t² class, extrapolated"),
    ]
    ax_a.legend(
        handles=handles,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8,
        loc="upper left",
    )

    # --- Save ---
    fig.savefig(out / "design_fires.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
