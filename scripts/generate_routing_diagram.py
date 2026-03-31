"""Generate a routing model flowchart for the pyFDS-Evac paper.

Shows the full rank_routes decision pipeline:
  inputs → subgraph restriction → Phase 1 edge weights →
  Phase 2 Dijkstra → Phase 3 composite cost →
  rejection filters → fallback → selected route.

Usage:
    uv run python scripts/generate_routing_diagram.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT_PATH = Path("../pyFDS-Evac-paper/figs/routing_diagram.png")

# ── colours ───────────────────────────────────────────────────────────
C_INPUT = "#E3F2FD"      # light blue  – inputs
C_PHASE = "#E8F5E9"      # light green – processing phases
C_REJECT = "#FFF3E0"     # light orange – rejection filters
C_FALLBACK = "#FCE4EC"   # light red   – fallback
C_OUTPUT = "#F3E5F5"     # light purple – output
C_BORDER = "#455A64"     # dark grey
C_ARROW = "#37474F"
C_REJECT_BORDER = "#E65100"
C_PHASE_BORDER = "#2E7D32"
C_INPUT_BORDER = "#1565C0"
C_OUT_BORDER = "#6A1B9A"


def _box(ax, x, y, w, h, text, facecolor, edgecolor, fontsize=8.5, bold=False):
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle="round,pad=0.04",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.4,
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
        wrap=True,
    )


def _arrow(ax, x0, y0, x1, y1, label="", color=C_ARROW):
    ax.annotate(
        "",
        xy=(x1, y1),
        xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=1.3,
            mutation_scale=12,
        ),
        zorder=5,
    )
    if label:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx + 0.03, my, label, fontsize=7, color=color, va="center", zorder=6)


def _hline(ax, x0, x1, y, color=C_ARROW, lw=1.1):
    ax.plot([x0, x1], [y, y], color=color, lw=lw, zorder=2)


def _vline(ax, x, y0, y1, color=C_ARROW, lw=1.1):
    ax.plot([x, x], [y0, y1], color=color, lw=lw, zorder=2)


def main():
    fig, ax = plt.subplots(figsize=(7.5, 12))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ── column centres ────────────────────────────────────────────────
    CX = 0.5   # main spine x
    BW = 0.52  # default box width
    BH = 0.045 # default box height

    # ── rows (top → bottom) ───────────────────────────────────────────
    Y_IN1  = 0.965
    Y_IN2  = 0.900
    Y_SUB  = 0.830
    Y_PH1  = 0.758
    Y_PH2  = 0.678
    Y_PH3  = 0.598
    Y_RLAB = 0.530   # "rejection filters" label
    Y_R1   = 0.490
    Y_R2   = 0.435
    Y_R3   = 0.380
    Y_ALL  = 0.318
    Y_FB   = 0.268
    Y_SORT = 0.210
    Y_OUT  = 0.150

    # ── INPUT ROW ─────────────────────────────────────────────────────
    # Three input boxes side by side
    iw, ih = 0.26, 0.042
    xs = [0.18, 0.50, 0.82]
    labels_in = [
        "Agent state\n$(t,\\,\\mathbf{x}_i,\\,D_i,\\,N_k)$",
        "FDS fields\n$(K(\\mathbf{x},t),\\;\\dot{D}(\\mathbf{x},t))$",
        "Cognitive map\n$(\\text{full} \\mid \\text{discovery})$",
    ]
    for xi, lab in zip(xs, labels_in):
        _box(ax, xi, Y_IN1, iw, ih, lab, C_INPUT, C_INPUT_BORDER, fontsize=7.5)

    # arrows from inputs down to a merge line, then to subgraph box
    merge_y = Y_IN1 - ih / 2 - 0.018
    for xi in xs:
        _arrow(ax, xi, Y_IN1 - ih / 2, xi, merge_y + 0.005)
    _hline(ax, xs[0], xs[-1], merge_y)
    _vline(ax, CX, merge_y, Y_SUB + BH / 2)
    ax.annotate(
        "",
        xy=(CX, Y_SUB + BH / 2),
        xytext=(CX, merge_y),
        arrowprops=dict(arrowstyle="-|>", color=C_ARROW, lw=1.3, mutation_scale=12),
        zorder=5,
    )

    # ── SUBGRAPH RESTRICTION ──────────────────────────────────────────
    _box(
        ax, CX, Y_SUB, BW, BH,
        "Restrict graph to cognitive subgraph\n"
        "(discovery agents only; full agents: no change)",
        C_PHASE, C_PHASE_BORDER, fontsize=8,
    )
    _arrow(ax, CX, Y_SUB - BH / 2, CX, Y_PH1 + BH / 2)

    # ── PHASE 1 ───────────────────────────────────────────────────────
    _box(
        ax, CX, Y_PH1, BW, BH,
        "Phase 1 — dynamic edge weights\n"
        "$w_{uv} = L_{uv}(1+w_\\sigma\\bar{K}_{uv}) + w_F\\,\\Delta D_{uv}$",
        C_PHASE, C_PHASE_BORDER, fontsize=8,
    )
    _arrow(ax, CX, Y_PH1 - BH / 2, CX, Y_PH2 + BH / 2)

    # ── PHASE 2 ───────────────────────────────────────────────────────
    _box(
        ax, CX, Y_PH2, BW, BH,
        "Phase 2 — Dijkstra\n"
        "one shortest path per reachable exit",
        C_PHASE, C_PHASE_BORDER, fontsize=8,
    )
    _arrow(ax, CX, Y_PH2 - BH / 2, CX, Y_PH3 + BH / 2)

    # ── PHASE 3 ───────────────────────────────────────────────────────
    _box(
        ax, CX, Y_PH3, BW, BH,
        "Phase 3 — route-level composite cost\n"
        "$\\mathcal{C}_k = L_k(1+w_\\sigma\\bar{K}_k)"
        "+ w_F D^{\\max}_k + w_q v_0 N_k/c_k$",
        C_PHASE, C_PHASE_BORDER, fontsize=8,
    )
    _arrow(ax, CX, Y_PH3 - BH / 2, CX, Y_RLAB + 0.018)

    # ── REJECTION LABEL ───────────────────────────────────────────────
    ax.text(
        CX, Y_RLAB + 0.01,
        "Rejection filters (per route)",
        ha="center", va="center", fontsize=8.5, fontweight="bold",
        color=C_REJECT_BORDER, zorder=4,
    )

    # ── REJECTION BOXES ───────────────────────────────────────────────
    rw, rh = 0.56, 0.038
    reject_items = [
        (Y_R1, "$D^{\\max}_k > D_{\\mathrm{thresh}}$\n"
               "agent incapacitated before reaching exit"),
        (Y_R2, "All segments $\\bar{K}_{uv}\\geq K_{\\mathrm{vis}}$"
               " AND another route is clear\n(relative smoke filter)"),
        (Y_R3, "Next-node sign not visible from $\\mathbf{x}_i$\n"
               "(unconditional — per route, independent)"),
    ]
    for yr, txt in reject_items:
        _box(ax, CX, yr, rw, rh, txt, C_REJECT, C_REJECT_BORDER, fontsize=7.5)
        _arrow(ax, CX, yr - rh / 2, CX, yr - rh / 2 - 0.008,
               color=C_REJECT_BORDER)

    # connect last reject to "all rejected?" diamond
    _arrow(ax, CX, Y_R3 - rh / 2, CX, Y_ALL + 0.022, color=C_REJECT_BORDER)

    # ── ALL REJECTED? ─────────────────────────────────────────────────
    # draw diamond manually
    dx, dy = 0.11, 0.025
    diamond = plt.Polygon(
        [[CX, Y_ALL + dy], [CX + dx, Y_ALL],
         [CX, Y_ALL - dy], [CX - dx, Y_ALL]],
        closed=True, facecolor=C_FALLBACK, edgecolor=C_REJECT_BORDER,
        linewidth=1.4, zorder=3,
    )
    ax.add_patch(diamond)
    ax.text(CX, Y_ALL, "All routes\nrejected?", ha="center", va="center",
            fontsize=7.5, zorder=4)

    # "Yes" branch → fallback box to the right
    _arrow(ax, CX + dx, Y_ALL, 0.82, Y_ALL, color=C_REJECT_BORDER)
    ax.text(0.72, Y_ALL + 0.012, "Yes", fontsize=7.5, color=C_REJECT_BORDER)
    _box(ax, 0.82, Y_ALL, 0.22, 0.038,
         "Fallback: un-reject\nleast-cost route",
         C_FALLBACK, C_REJECT_BORDER, fontsize=7.5)
    # fallback reconnects back to main spine
    _vline(ax, 0.82, Y_ALL - 0.019, Y_SORT + 0.005, color=C_REJECT_BORDER)
    _hline(ax, CX, 0.82, Y_SORT + 0.005, color=C_REJECT_BORDER)

    # "No" branch → straight down
    _arrow(ax, CX, Y_ALL - dy, CX, Y_SORT + BH / 2)
    ax.text(CX + 0.04, (Y_ALL - dy + Y_SORT + BH / 2) / 2, "No",
            fontsize=7.5, color=C_ARROW)

    # ── SORT ──────────────────────────────────────────────────────────
    _box(ax, CX, Y_SORT, BW, BH,
         "Sort non-rejected routes by $\\mathcal{C}_k$ (ascending)",
         C_PHASE, C_PHASE_BORDER, fontsize=8)
    _arrow(ax, CX, Y_SORT - BH / 2, CX, Y_OUT + BH / 2)

    # ── OUTPUT ────────────────────────────────────────────────────────
    _box(ax, CX, Y_OUT, BW, BH,
         "Selected route: best exit $k^*$ + path\n"
         "(agent reroutes if $k^* \\neq$ current exit)",
         C_OUTPUT, C_OUT_BORDER, fontsize=8, bold=True)

    # ── LEGEND ────────────────────────────────────────────────────────
    legend_patches = [
        mpatches.Patch(facecolor=C_INPUT,   edgecolor=C_INPUT_BORDER,  label="Inputs"),
        mpatches.Patch(facecolor=C_PHASE,   edgecolor=C_PHASE_BORDER,  label="Processing"),
        mpatches.Patch(facecolor=C_REJECT,  edgecolor=C_REJECT_BORDER, label="Rejection / fallback"),
        mpatches.Patch(facecolor=C_OUTPUT,  edgecolor=C_OUT_BORDER,    label="Output"),
    ]
    ax.legend(
        handles=legend_patches,
        loc="lower left",
        fontsize=7.5,
        frameon=True,
        framealpha=0.9,
        bbox_to_anchor=(0.01, 0.01),
    )

    fig.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=180, bbox_inches="tight")
    print(f"Saved → {OUT_PATH}")
    plt.show()


if __name__ == "__main__":
    main()
