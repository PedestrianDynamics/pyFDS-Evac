# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib", "seaborn", "numpy"]
# ///
"""Figures for the G1 pass-1 profiling runs (read-only on results/summary.csv).

Saves
-----
results/figures/fig_g1_w1_wall.{png,pdf}
results/figures/fig_g1_scaling.{png,pdf}
results/figures/fig_g1_w3_cache.{png,pdf}
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.lines import Line2D


def load_rows(path):
    """Measured, non-warm-up rows of summary.csv with typed fields."""
    rows = []
    with open(path) as fh:
        records = list(csv.DictReader(fh))
    for r in records:
        if r["measurement_status"] != "measured" or r["role"] == "warmup":
            continue
        if "warmup" in r["run_id"]:
            continue
        r["wall_s"] = float(r["wall_s"])
        r["contaminated"] = r["contaminated"] == "True"
        r["total"] = int(r["total"] or 0)
        # instrument level is not a column: derived from the run_id infix
        rid = r["run_id"]
        r["level"] = (
            "detail" if "_det_" in rid else "counters" if "_ctr_" in rid else "plain"
        )
        rows.append(r)
    return rows


def select(rows, block, **kw):
    return [
        r for r in rows if r["block"] == block and all(r[k] == v for k, v in kw.items())
    ]


def strip(ax, x, runs, color, marker, rng, width=0.13):
    """Individual runs: filled = clean, hollow = host-contaminated; bar = median."""
    for r in runs:
        xj = x + rng.uniform(-width, width)
        if r["contaminated"]:
            ax.scatter(
                xj,
                r["wall_s"],
                s=46,
                marker=marker,
                facecolors="white",
                edgecolors=color,
                linewidths=1.5,
                zorder=4,
            )
        else:
            ax.scatter(
                xj,
                r["wall_s"],
                s=46,
                marker=marker,
                facecolors=color,
                edgecolors="white",
                linewidths=0.6,
                zorder=4,
            )
    med = np.median([r["wall_s"] for r in runs])
    ax.plot(
        [x - 0.3, x + 0.3],
        [med, med],
        color="dimgrey",
        lw=2.2,
        zorder=5,
        solid_capstyle="butt",
    )


def style_axis(ax, title=None):
    ax.grid(False)
    ax.grid(axis="y", alpha=0.7, linewidth=1)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    if title:
        ax.set_title(title, loc="left", fontsize=11, pad=7, color="dimgrey")


def legend_handles(markers=None):
    h = [
        Line2D(
            [],
            [],
            marker="o",
            ls="",
            mfc="white",
            mec="dimgrey",
            mew=1.5,
            ms=7,
            label="host-contaminated run (hollow)",
        ),
        Line2D(
            [],
            [],
            marker="o",
            ls="",
            mfc="dimgrey",
            mec="white",
            ms=7,
            label="clean run (filled)",
        ),
        Line2D([], [], color="dimgrey", lw=2.2, label="median of the group"),
    ]
    for name, m in (markers or {}).items():
        h.append(
            Line2D(
                [],
                [],
                marker=m,
                ls="",
                mfc="lightgrey",
                mec="dimgrey",
                ms=7,
                label=name,
            )
        )
    return h


def legend(ax, handles, **kw):
    ax.legend(
        handles=handles,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=9,
        **kw,
    )


TITLE = "G1 pass 1, commit 8f7d29a2, host-contamination flags shown"
YLABEL = "wall-clock per run [s]"


def xlabels(ax, labels, size=9):
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=size)


def fig_w1(rows, out, rng):
    pal = sns.color_palette("colorblind")
    mk = {"plain": "o", "counters": "s", "detail": "^"}
    groups = [
        ("G1base\nO_study s1", select(rows, "G1base"), pal[0], "plain"),
        ("G1seeds\ns2", select(rows, "G1seeds", seed="2"), pal[0], "plain"),
        ("G1seeds\ns3", select(rows, "G1seeds", seed="3"), pal[0], "plain"),
        ("G1ovh\nplain", select(rows, "G1ovh", level="plain"), pal[1], "plain"),
        (
            "G1ovh\ncounters",
            select(rows, "G1ovh", level="counters"),
            pal[1],
            "counters",
        ),
        ("G1ovhD\nplain", select(rows, "G1ovhD", level="plain"), pal[2], "plain"),
        (
            "G1ovhD\ncounters",
            select(rows, "G1ovhD", level="counters"),
            pal[2],
            "counters",
        ),
        ("G1ovhD\ndetail", select(rows, "G1ovhD", level="detail"), pal[2], "detail"),
        ("G1out\nO_study", select(rows, "G1out", variant="O_study"), pal[4], "plain"),
        ("G1out\nO_norc", select(rows, "G1out", variant="O_norc"), pal[4], "plain"),
        ("G1out\nO_min", select(rows, "G1out", variant="O_min"), pal[4], "plain"),
    ]
    fig, ax = plt.subplots(figsize=(13, 6), dpi=150)
    for i, (_, runs, c, lv) in enumerate(groups):
        strip(ax, i, runs, c, mk[lv], rng)
    xlabels(ax, [g[0] for g in groups])
    ax.set_ylabel(YLABEL, fontsize=12, color="dimgrey", labelpad=10)
    ax.set_title(TITLE, loc="left", fontsize=13, pad=26, color="dimgrey")
    style_axis(ax)
    ax.text(
        0,
        1.02,
        "W1 family, one point per run: detail instrumentation far above plain, O_norc and O_min "
        "far below O_study (y-axis does not start at zero)",
        transform=ax.transAxes,
        fontsize=9.5,
        color="dimgrey",
        va="bottom",
    )
    legend(
        ax,
        legend_handles({"plain": "o", "counters": "s", "detail": "^"}),
        loc="upper left",
    )

    sns.despine(left=True, bottom=True)
    return fig


def fig_scaling(rows, out, rng):
    pal = sns.color_palette("colorblind")
    sets = [
        select(rows, "G1scale100"),
        select(rows, "G1base"),
        select(rows, "G1scale400"),
    ]
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    meds = []
    for runs in sets:
        n = runs[0]["total"]
        xs = n + rng.uniform(-4, 4, len(runs))
        ys = [r["wall_s"] for r in runs]
        ax.scatter(
            xs,
            ys,
            s=50,
            facecolors=["white" if r["contaminated"] else pal[0] for r in runs],
            edgecolors=pal[0],
            linewidths=1.5,
            zorder=4,
        )
        meds.append((n, np.median(ys)))
    ax.plot(*zip(*meds), color="dimgrey", lw=2.2, marker="_", ms=18, mew=2.2, zorder=3)
    n0, m0 = meds[1]
    xr = np.array([0, 420])
    ax.plot(xr, m0 * xr / n0, ls="--", color=pal[3], lw=1.6, zorder=2)
    ax.set_xlim(0, 420)
    ax.set_ylim(0, None)
    ax.set_xticks([100, 200, 400])
    ax.set_xticklabels(["100\nW1_n100", "200\nW1", "400\nW1_n400"])
    ax.set_xlabel("number of agents", fontsize=12, color="dimgrey", labelpad=10)
    ax.set_ylabel(YLABEL, fontsize=12, color="dimgrey", labelpad=10)
    ax.set_title(TITLE, loc="left", fontsize=12, pad=7, color="dimgrey")
    style_axis(ax)
    ax.grid(axis="x", alpha=0.7, linewidth=1)
    ax.annotate(
        "data rise faster than the dashed\nreference proportional to N",
        xy=(400, meds[2][1]),
        xytext=(215, meds[2][1] * 0.88),
        color="dimgrey",
        fontsize=10,
        arrowprops={"arrowstyle": "-", "color": "lightgrey"},
    )
    h = legend_handles()[:3]
    h.append(
        Line2D(
            [],
            [],
            color=pal[3],
            ls="--",
            lw=1.6,
            label="proportional to N through the\n200-agent median",
        )
    )
    legend(ax, h, loc="upper left")
    sns.despine(left=True, bottom=True)
    return fig


def fig_w3(rows, out, rng):
    pal = sns.color_palette("colorblind")
    mk = {"plain": "o", "counters": "s"}
    a = [
        ("G1w3first\nfirst_use", select(rows, "G1w3first"), pal[0], "plain"),
        ("G1w3rep\nrepeated_use", select(rows, "G1w3rep"), pal[1], "plain"),
        ("G1w3noflag\nnoflag", select(rows, "G1w3noflag"), pal[2], "plain"),
        ("G1ovhW3\nplain", select(rows, "G1ovhW3", level="plain"), pal[1], "plain"),
        (
            "G1ovhW3\ncounters",
            select(rows, "G1ovhW3", level="counters"),
            pal[1],
            "counters",
        ),
    ]
    b = [
        ("G1w3bfirst\nfirst_use", select(rows, "G1w3bfirst"), pal[0], "plain"),
        ("G1w3brep\nrepeated_use", select(rows, "G1w3brep"), pal[1], "plain"),
    ]
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(12, 5.5),
        dpi=150,
        gridspec_kw={"width_ratios": [5, 2.4], "wspace": 0.18},
    )
    for ax, grp, ttl in (
        (axes[0], a, r"$\bf{(a)}$ W3 (vis_cache setting and plain vs counters)"),
        (axes[1], b, r"$\bf{(b)}$ W3b_cmm"),
    ):
        for i, (_, runs, c, lv) in enumerate(grp):
            strip(ax, i, runs, c, mk[lv], rng)
        xlabels(ax, [g[0] for g in grp])
        ax.set_xlim(-0.6, len(grp) - 0.4)
        style_axis(ax, ttl)
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    axes[1].text(
        0.5,
        0.5,
        "first_use above repeated_use\n(y-axes do not start at zero)",
        transform=axes[1].transAxes,
        ha="center",
        va="center",
        fontsize=9,
        color="dimgrey",
    )
    axes[0].set_ylabel(YLABEL, fontsize=12, color="dimgrey", labelpad=10)
    axes[1].set_ylabel(YLABEL, fontsize=12, color="dimgrey", labelpad=10)
    fig.suptitle(TITLE, x=0.125, ha="left", fontsize=13, color="dimgrey", y=1.0)
    legend(axes[0], legend_handles({"plain": "o", "counters": "s"}), loc="upper right")
    sns.despine(left=True, bottom=True)
    return fig


def main():
    """Build the three G1 pass-1 figures from results/summary.csv."""
    here = Path(__file__).resolve().parent
    out = here / "results" / "figures"
    out.mkdir(exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data ---
    rows = load_rows(here / "results" / "summary.csv")
    rng = np.random.default_rng(0)  # jitter only; does not touch values

    # --- Plot & Save ---
    for name, fn in (
        ("fig_g1_w1_wall", fig_w1),
        ("fig_g1_scaling", fig_scaling),
        ("fig_g1_w3_cache", fig_w3),
    ):
        fig = fn(rows, out, rng)
        for ext in ("png", "pdf"):
            fig.savefig(out / f"{name}.{ext}", dpi=150, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
