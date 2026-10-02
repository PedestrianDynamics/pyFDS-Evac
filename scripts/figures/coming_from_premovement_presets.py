# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "seaborn",
#     "numpy",
# ]
# ///
"""The first four pre-movement presets as probability densities.

Each panel shows one preset of ``PREMOVEMENT_PRESETS`` in the order of the
table on the "Coming from FDS+Evac" page (gamma, log-normal, Weibull,
uniform):

- the closed-form probability density with the preset's (a, b), in the
  convention of the code (gamma: shape, scale; log-normal: mean and SD of
  ln t; Weibull: scale, shape; uniform: bounds);
- a histogram of draws made through ``create_premovement_distribution``,
  which checks that the code's parameter convention matches the density;
- the median and the 95th percentile of the density, from its cumulative
  integral on a fine grid.

The x axis is shared (0-600 s); the y axes are not, since the uniform
density would flatten the other three.

Run from the repository root::

    uv run python scripts/figures/coming_from_premovement_presets.py

Writes ``site/static/images/getting-started/premovement_presets.png``.
"""

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from pyfds_evac.core.premovement_distributions import (
    PREMOVEMENT_PRESETS,
    create_premovement_distribution,
)

T_MAX = 600.0
N_HIST = 10_000
SEED = 1


def gamma_pdf(t, a, b):
    """Gamma density with shape ``a`` and scale ``b`` [s]."""
    return t ** (a - 1) * np.exp(-t / b) / (math.gamma(a) * b**a)


def lognormal_pdf(t, a, b):
    """Log-normal density; ``a`` and ``b`` are the mean and SD of ln t."""
    return np.exp(-((np.log(t) - a) ** 2) / (2 * b**2)) / (
        t * b * math.sqrt(2 * math.pi)
    )


def weibull_pdf(t, a, b):
    """Weibull density with scale ``a`` [s] and shape ``b``."""
    return (b / a) * (t / a) ** (b - 1) * np.exp(-((t / a) ** b))


def uniform_pdf(t, a, b):
    """Uniform density on [a, b] [s]."""
    return np.where((t >= a) & (t <= b), 1.0 / (b - a), 0.0)


def quantiles(pdf, a, b):
    """Median, 95th percentile and mass beyond ``T_MAX`` of a density."""
    t = np.linspace(1e-6, 50_000.0, 2_000_001)
    y = pdf(t, a, b)
    cdf = np.concatenate(([0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))))
    med, p95 = np.interp([0.5, 0.95], cdf, t)
    return med, p95, 1.0 - np.interp(T_MAX, t, cdf)


PANELS = [
    ("gamma", gamma_pdf, "gamma", "shape {a:g}, scale {b:g} s"),
    (
        "lognormal",
        lognormal_pdf,
        "log-normal",
        r"$\mu$ = {a:g}, $\sigma$ = {b:g} (of ln t)",
    ),
    ("weibull", weibull_pdf, "Weibull", "scale {a:g} s, shape {b:g}"),
    ("uniform", uniform_pdf, "uniform", "{a:g} to {b:g} s"),
]

NOTES = [
    None,
    None,
    None,
    "RiMEA 'speedy evacuation'\nsensitivity scenario",
]


def draw_panel(ax, letter, name, pdf, label, param_fmt, colour, note=None):
    """Draw one preset: histogram of draws, density, median and p95."""
    p = PREMOVEMENT_PRESETS[name]
    a, b = p["a"], p["b"]
    hist = create_premovement_distribution(name, p, seed=SEED).sample(N_HIST)
    med, p95, beyond = quantiles(pdf, a, b)

    bins = np.arange(0.0, T_MAX + 10.0, 10.0)
    ax.hist(hist, bins=bins, density=True, color="lightgrey", edgecolor="white", lw=0.5)
    t = np.linspace(0.5, T_MAX, 1200)
    y = pdf(t, a, b)
    ax.plot(t, y, color=colour, lw=2.4)

    y_top = 1.18 * max(y.max(), np.histogram(hist, bins=bins, density=True)[0].max())
    ax.set_ylim(0.0, y_top)
    for x, style in ((med, "-"), (p95, "--")):
        ax.axvline(x, color="dimgrey", lw=1.0, ls=style)
    if p95 - med < 100.0:
        ax.text(
            p95 + 12,
            0.93 * y_top,
            f"median {med:.0f} s (solid)\n95th pct. {p95:.0f} s (dashed)",
            fontsize=9,
            color="dimgrey",
            va="top",
        )
    else:
        for x, text in ((med, "median"), (p95, "95th pct.")):
            ax.text(
                x + 6,
                0.93 * y_top,
                f"{text}\n{x:.0f} s",
                fontsize=9,
                color="dimgrey",
                va="top",
            )
    if beyond > 0.001:
        ax.text(
            p95 - 10,
            0.62 * y_top,
            f"{100 * beyond:.1f} % of the\ndistribution lies\nbeyond {T_MAX:.0f} s",
            fontsize=9,
            color="dimgrey",
            ha="right",
            va="center",
        )
    if note:
        ax.text(
            0.55 * T_MAX,
            0.5 * y_top,
            note,
            fontsize=9,
            color="dimgrey",
            ha="center",
            va="center",
        )

    ax.set_title(
        rf"$\bf{{({letter})}}$ {label}: " + param_fmt.format(a=a, b=b),
        loc="left",
        fontsize=11,
    )
    ax.set_xlim(0.0, T_MAX)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)
    return med, p95, beyond


def main():
    """Plot the four presets in a 2x2 grid and save the PNG."""
    out = Path(__file__).resolve().parents[2] / "site/static/images/getting-started"
    out.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    colour = sns.cubehelix_palette(6, rot=-0.25, light=0.7)[4]

    # --- Plot ---
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), dpi=150, sharex=True)
    for i, (ax, (name, pdf, label, fmt), note) in enumerate(
        zip(axes.flat, PANELS, NOTES)
    ):
        med, p95, beyond = draw_panel(
            ax, chr(ord("a") + i), name, pdf, label, fmt, colour, note
        )
        print(
            f"{name}: median {med:.1f} s, p95 {p95:.1f} s, beyond {T_MAX:.0f} s {100 * beyond:.2f} %"
        )
    for ax in axes[1]:
        ax.set_xlabel("pre-movement time t [s]", color="dimgrey")
    for ax in axes[:, 0]:
        ax.set_ylabel("probability density [1/s]", color="dimgrey")
    sns.despine(left=True, bottom=True)
    fig.tight_layout(h_pad=1.2, w_pad=1.5)

    # --- Save ---
    fig.savefig(out / "premovement_presets.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
