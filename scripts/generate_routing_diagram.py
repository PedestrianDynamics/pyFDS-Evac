from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

OUT_PATH = Path("routing_diagram_final_result.png")

# --- Colors ---
# Shared palette of the concept figures: chosen route blue, refused route red
# (dashed), stages in the map dark slate, neutral inputs grey.
C_INPUT = "#f7f7f7"  # neutral input
C_PHASE = "#e3e7ee"  # routing step, tint of the known-stage slate
C_REJECT = "#fbe3e1"  # tint of the refused-route red
C_FALLBACK = "#fbe3e1"
C_OUTPUT = "#dde6f3"  # tint of the chosen-route blue
C_ARROW = "dimgrey"
C_REJECT_BORDER = "#d73027"
C_PHASE_BORDER = "#324465"
C_INPUT_BORDER = "#969696"
C_OUT_BORDER = "#4575b4"


def draw_box(ax, x, y, w, h, text, facecolor, edgecolor, fontsize=8, bold=False):
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.01",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.2,
        zorder=3,
    )
    ax.add_patch(box)
    weight = "bold" if bold else "normal"
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight=weight,
        zorder=4,
        linespacing=1.2,
    )


def draw_circle(ax, x, y, r, text, facecolor, edgecolor, fontsize=8):
    circle = Circle(
        (x, y), r, facecolor=facecolor, edgecolor=edgecolor, linewidth=1.2, zorder=3
    )
    ax.add_patch(circle)
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        zorder=4,
        linespacing=1.2,
    )


def draw_arrow(
    ax,
    x0,
    y0,
    x1,
    y1,
    label="",
    color=C_ARROW,
    label_pos=0.5,
    shrink=0,
    connectionstyle=None,
    linestyle="-",
):
    arrow_props = dict(
        arrowstyle="-|>",
        color=color,
        lw=1.2,
        linestyle=linestyle,
        mutation_scale=12,
        shrinkA=shrink,
        shrinkB=shrink,
    )
    if connectionstyle:
        arrow_props["connectionstyle"] = connectionstyle
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=arrow_props, zorder=5)
    if label:
        mx, my = x0 + (x1 - x0) * label_pos, y0 + (y1 - y0) * label_pos
        ax.text(
            mx + 0.01,
            my,
            label,
            fontsize=8,
            color=color,
            fontweight="bold",
            va="center",
            bbox=dict(fc="white", ec="none", pad=1.0),
            zorder=6,
        )


def main():
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(10, 11))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    CX = 0.5
    BW_STD, BH_STD = 0.28, 0.08
    XS_STD = [0.18, 0.5, 0.82]

    # --- Y-coordinates ---
    Y_INPUT, Y_RESTRICT, Y_PHASES = 0.92, 0.82, 0.71
    Y_REJ_TITLE, Y_REJECTS, Y_DIAMOND = 0.61, 0.52, 0.39
    Y_SORT, Y_OUTPUT = 0.27, 0.14

    # 1. Inputs (3 Blue Boxes)
    labels_in = [
        "Agent state\n$(t, \\mathbf{x}_i, D_i, N_k)$",
        "FDS fields\n$(K, \\dot{D})$",
        "Cognitive map\n(full | discovery)",
    ]
    for x, txt in zip(XS_STD, labels_in):
        draw_box(ax, x, Y_INPUT, BW_STD, BH_STD, txt, C_INPUT, C_INPUT_BORDER)
    draw_arrow(ax, CX, Y_INPUT - BH_STD / 2, CX, Y_RESTRICT + 0.03)

    # 2. Restrict Graph (Green Box)
    draw_box(
        ax,
        CX,
        Y_RESTRICT,
        0.6,
        0.06,
        "Restrict graph to cognitive subgraph\n(discovery agents only; full agents: no change)",
        C_PHASE,
        C_PHASE_BORDER,
    )

    # 3. Phases (Floating circular nodes)
    labels_phase = [
        "Phase 1\nDynamic\nWeights",
        "Phase 2\nDijkstra\nShortest Path",
        "Phase 3\nComposite\nCost",
    ]
    for x, txt in zip([0.25, 0.5, 0.75], labels_phase):
        draw_circle(ax, x, Y_PHASES, 0.055, txt, C_PHASE, C_PHASE_BORDER)

    # 4. Rejection Filters (3 Orange Boxes - aligned with inputs)
    ax.text(
        CX,
        Y_REJ_TITLE,
        "REJECTION FILTERS (per route)",
        ha="center",
        fontweight="bold",
        color=C_REJECT_BORDER,
        fontsize=9,
    )
    labels_rej = [
        "$D^{\\max}_k > D_{\\text{thresh}}$\nAgent incapacitated\nbefore exit",
        "Relative Smoke Filter\n$\\bar{K}_{uv} \\geq K_{\\text{vis}}$",
        "Visibility Filter\nNext-node sign\nnot visible from $\\mathbf{x}_i$",
    ]
    for x, txt in zip(XS_STD, labels_rej):
        draw_box(ax, x, Y_REJECTS, BW_STD, BH_STD, txt, C_REJECT, C_REJECT_BORDER)

    # Arrow to Decision Diamond from the middle filter
    draw_arrow(
        ax,
        XS_STD[1],
        Y_REJECTS - BH_STD / 2,
        CX,
        Y_DIAMOND + 0.04,
        color=C_REJECT_BORDER,
        linestyle="--",
    )

    # 5. Decision Diamond & Fallback
    diamond = Polygon(
        [
            [CX, Y_DIAMOND + 0.04],
            [CX + 0.09, Y_DIAMOND],
            [CX, Y_DIAMOND - 0.04],
            [CX - 0.09, Y_DIAMOND],
        ],
        facecolor=C_FALLBACK,
        edgecolor=C_REJECT_BORDER,
        lw=1.5,
        zorder=3,
    )
    ax.add_patch(diamond)
    ax.text(
        CX,
        Y_DIAMOND,
        "All routes\nrejected?",
        ha="center",
        va="center",
        fontsize=8.5,
        fontweight="bold",
    )

    X_FALL, W_FALL, BW_SORT = 0.12, 0.2, 0.5
    draw_arrow(
        ax,
        CX - 0.09,
        Y_DIAMOND,
        X_FALL + W_FALL / 2,
        Y_DIAMOND,
        label="Yes",
        color=C_REJECT_BORDER,
        label_pos=0.6,
        linestyle="--",
    )
    draw_box(
        ax,
        X_FALL,
        Y_DIAMOND,
        W_FALL,
        0.08,
        "Fallback:\nUn-reject\nleast-cost route",
        C_FALLBACK,
        C_REJECT_BORDER,
    )

    # Rerouted Fallback arrow to Side of Sort box
    draw_arrow(
        ax,
        X_FALL,
        Y_DIAMOND - 0.04,
        CX - BW_SORT / 2,
        Y_SORT + 0.01,
        color=C_REJECT_BORDER,
        connectionstyle="angle,angleA=-90,angleB=180,rad=5",
        linestyle="--",
    )

    # 6. Sort & Output
    draw_arrow(ax, CX, Y_DIAMOND - 0.04, CX, Y_SORT + 0.03, label="No", label_pos=0.4)
    draw_box(
        ax,
        CX,
        Y_SORT,
        BW_SORT,
        0.06,
        "Sort non-rejected routes by $\\mathcal{C}_k$ (ascending)",
        C_PHASE,
        C_PHASE_BORDER,
    )
    draw_arrow(ax, CX, Y_SORT - 0.03, CX, Y_OUTPUT + 0.045, color=C_OUT_BORDER)
    draw_box(
        ax,
        CX,
        Y_OUTPUT,
        0.6,
        0.09,
        "SELECTED ROUTE:\nBest exit $k^*$ + path\n(Agent reroutes if $k^* \\neq$ current exit)",
        C_OUTPUT,
        C_OUT_BORDER,
        bold=True,
        fontsize=9.5,
    )
    ax.text(
        CX,
        0.06,
        "Red dashed: the rejection path. If every route is rejected, the "
        "least-cost one is reinstated, so an agent always has a target",
        ha="center",
        va="center",
        fontsize=8.5,
        color="dimgrey",
        style="italic",
    )

    plt.savefig(OUT_PATH, dpi=300, bbox_inches="tight")
    plt.show()


if __name__ == "__main__":
    main()
