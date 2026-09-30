# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""The egress timeline of ISO/TR 16738:2009, Eqs. 1-2, as a schematic.

The symbols are those of ISO/TR 16738 as the Fundamentals page writes them:
t_det, t_warn, t_pre, t_trav, t_evac = t_pre + t_trav, t_RSET, t_ASET and
t_marg = t_ASET - t_RSET. Each occupant has their own t_pre,i and t_trav,i,
drawn as one row that starts at the general alarm. t_RSET is drawn at the
exit of the last occupant, the maximum of the individual evacuation times as
RiMEA 4.1.1 (§2.13) defines the evacuation time.

All times are illustrative; the time axis carries no numbers. The layout is
inspired by RiMEA 4.1.1, Fig. 2 (p. 9).

Run from the repository root::

    uv run python scripts/figures/fundamentals_aset_rset_timeline.py

Writes ``site/static/images/fundamentals/aset_rset_timeline.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns

# Illustrative times [arbitrary units]
T_DET = 38.0
T_WARN = 30.0
PRE = [20.0, 45.0, 32.0, 70.0, 55.0, 88.0]
TRAV = [58.0, 40.0, 78.0, 45.0, 75.0, 52.0]
T_ASET = 262.0

C_DET = "#fc8d59"
C_WARN = "#fee090"
C_TRAV = "#4575b4"
C_PRE = "#c6d6ea"
C_ASET = "#d73027"
BAR_H = 0.56


def bracket(ax, x0, x1, y, text, colour="dimgrey", above=True):
    """Draw a thin horizontal bracket from ``x0`` to ``x1`` with a label."""
    ax.annotate(
        "",
        xy=(x0, y),
        xytext=(x1, y),
        arrowprops=dict(arrowstyle="|-|,widthA=0.25,widthB=0.25", color=colour, lw=1.0),
    )
    ax.text(
        0.5 * (x0 + x1),
        y + (0.14 if above else -0.14),
        text,
        ha="center",
        va="bottom" if above else "top",
        fontsize=11,
        color=colour,
    )


def main():
    """Draw the timeline and save the PNG."""
    out = Path(__file__).resolve().parents[2] / "site/static/images/fundamentals"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data ---
    t_alarm = T_DET + T_WARN
    rows = sorted(zip(PRE, TRAV), key=lambda p: p[0] + p[1])
    exits = [t_alarm + p + t for p, t in rows]
    t_rset = max(exits)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(10.5, 5.2), dpi=150)
    y_band = len(rows) + 0.9

    ax.barh(y_band, T_DET, left=0.0, height=BAR_H, color=C_DET)
    ax.barh(y_band, T_WARN, left=T_DET, height=BAR_H, color=C_WARN)
    ax.text(
        T_DET / 2, y_band, r"$t_{\mathrm{det}}$", ha="center", va="center", fontsize=12
    )
    ax.text(
        T_DET + T_WARN / 2,
        y_band,
        r"$t_{\mathrm{warn}}$",
        ha="center",
        va="center",
        fontsize=12,
    )

    for i, ((pre, trav), t_exit) in enumerate(zip(rows, exits)):
        y = len(rows) - i - 0.3
        ax.barh(y, pre, left=t_alarm, height=BAR_H, color=C_PRE)
        ax.barh(y, trav, left=t_alarm + pre, height=BAR_H, color=C_TRAV)
        ax.plot(t_exit, y, marker="o", ms=4, color="dimgrey", zorder=3)
        if i == len(rows) - 1:
            ax.text(
                t_alarm + pre / 2,
                y,
                r"$t_{\mathrm{pre},i}$",
                ha="center",
                va="center",
                fontsize=12,
            )
            ax.text(
                t_alarm + pre + trav / 2,
                y,
                r"$t_{\mathrm{trav},i}$",
                ha="center",
                va="center",
                fontsize=12,
                color="white",
            )
            bracket(
                ax,
                t_alarm,
                t_exit,
                y - 0.46,
                r"$t_{\mathrm{evac},i} = t_{\mathrm{pre},i} + t_{\mathrm{trav},i}$",
                above=False,
            )

    # Event markers
    y_top = y_band + 0.55
    for x, text, ha in (
        (0.0, "ignition", "left"),
        (T_DET, "detection", "center"),
        (t_alarm, "general alarm", "left"),
    ):
        ax.plot([x, x], [-0.5, y_top], color="lightgrey", lw=0.9, ls=":", zorder=0)
        ax.text(x, y_top + 0.05, text, ha=ha, va="bottom", fontsize=9, color="dimgrey")

    # RSET and ASET
    ax.plot([t_rset, t_rset], [-0.5, y_top], color="dimgrey", lw=1.4)
    ax.text(
        t_rset,
        y_top + 0.05,
        r"$t_{\mathrm{RSET}}$" + "\nlast occupant out",
        ha="center",
        va="bottom",
        fontsize=10,
        color="dimgrey",
    )
    ax.plot([T_ASET, T_ASET], [-0.5, y_top], color=C_ASET, lw=1.4, ls="--")
    ax.text(
        T_ASET,
        y_top + 0.05,
        r"$t_{\mathrm{ASET}}$" + "\nuntenable",
        ha="center",
        va="bottom",
        fontsize=10,
        color=C_ASET,
    )
    bracket(ax, t_rset, T_ASET, 3.2, r"$t_{\mathrm{marg}}$")

    # Legend by direct labels, left of the occupant rows
    ax.text(
        t_alarm - 3,
        len(rows) - 0.3,
        "occupants,\nsorted by\nexit time",
        ha="right",
        va="top",
        fontsize=9,
        color="dimgrey",
    )
    ax.annotate(
        "",
        xy=(T_ASET + 12, -0.75),
        xytext=(0.0, -0.75),
        arrowprops=dict(arrowstyle="-|>", color="dimgrey", lw=0.9),
    )
    ax.text(T_ASET + 14, -0.75, "time", va="center", fontsize=10, color="dimgrey")

    ax.set_xlim(-4.0, T_ASET + 30.0)
    ax.set_ylim(-1.0, y_top + 0.9)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    sns.despine(left=True, bottom=True)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")

    # --- Save ---
    fig.savefig(out / "aset_rset_timeline.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
