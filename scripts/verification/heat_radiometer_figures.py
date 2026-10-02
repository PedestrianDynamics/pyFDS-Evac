# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "seaborn",
# ]
# ///
"""Figure for the verification page "Heat radiometer reference decks".

Plots, for the three decks of ``assets/heat_radiometer`` at z = 1.6 m,
where the incident flux q to a plate sits between U/4 and U for each
facing: q/U (filled) and the share above ambient,
(q - sigma Ta^4) / (U - 4 sigma Ta^4) (open). Dots are the median over the
points, bars the range over the points, each point a time mean over
t >= 1 s. The numbers come from ``heat_radiometer.summarize``.

Run from the repository root::

    uv run python scripts/verification/heat_radiometer_figures.py --data DIR

``DIR`` is as for ``heat_radiometer.py``. Writes ``heat_radiometer_ratio.png``
and ``.pdf`` to ``site/static/images/verification/`` (git ignores the PDF).
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heat_radiometer import CASES, DATA, read_devc, summarize  # noqa: E402

OUT = Path("site/static/images/verification")
LABELS = {"up": "up", "px": "+x", "mx": "−x", "dn": "down"}
TITLES = {
    "uniform": "Uniform hot room",
    "layer": "Hot layer above 2 m",
    "burner": "Burner (+x faces the flame)",
}


def _plot_row(ax, i, ratio, excess, color):
    """One facing: q/U (filled) above, share above ambient (open) below."""
    for arr, dy, filled in ((ratio, 0.13, True), (excess, -0.13, False)):
        y = i + dy
        ax.hlines(y, arr.min(), arr.max(), color="grey", alpha=0.4, lw=3)
        label = ("q/U" if filled else "above ambient") if i == 0 else None
        ax.scatter(
            np.median(arr),
            y,
            s=60,
            color=color if filled else "white",
            edgecolors=color,
            linewidths=1.5,
            zorder=3,
            label=label,
        )


def _decorate(ax, case, rows):
    for ref, txt in ((0.25, "U/4"), (0.5, "U/2"), (1.0, "U")):
        ax.axvline(ref, color="dimgrey", lw=0.8, ls=":")
        ax.text(ref, -0.6, txt, ha="center", va="center", color="dimgrey")
    ax.set_yticks(range(len(rows)), [LABELS[r[1]] for r in rows])
    ax.set_xlim(-0.03, 1.05)
    ax.set_ylim(3.5, -0.8)
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.set_title(TITLES[case], loc="left", color="dimgrey", pad=4)
    ax.set_xlabel("share of U", color="dimgrey")


def main():
    """Draw q/U per facing for the three decks.

    Parameters
    ----------
    --data : path
        Folder with ``heat_radiometer_<case>_devc.csv``.

    Saves
    -----
    site/static/images/verification/heat_radiometer_ratio.png (and .pdf,
    which git ignores)
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)

    # --- Plot ---
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), dpi=150, sharey=True)
    for ax, case in zip(axes, CASES, strict=True):
        path = sorted(args.data.rglob(f"heat_radiometer_{case}_devc.csv"))[0]
        rows = [r for r in summarize(read_devc(path)) if r[0] == 1.6]
        for i, (_, _, ratio, excess) in enumerate(rows):
            _plot_row(ax, i, ratio, excess, pal[5])
        _decorate(ax, case, rows)
    axes[0].set_ylabel("plate facing", color="dimgrey")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=2,
        bbox_to_anchor=(0.5, -0.06),
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    sns.despine(left=True, bottom=True)
    fig.tight_layout()

    # --- Save ---
    args.out.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(
            args.out / f"heat_radiometer_ratio.{ext}", dpi=150, bbox_inches="tight"
        )


if __name__ == "__main__":
    main()
