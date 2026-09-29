"""The ISO 2.5 kW/m2 radiant threshold of the total-flux heat dose.

Panel (a): the radiant term of Eq. 63.49, eps sigma (T^4 - T_s^4) / 1000
[kW/m2], against the source temperature for eps = 1 (also a black layer
with phi eps_L = 1), 0.5 (the default) and 0.05 (clear air), with
T_s = 35 deg C. Below 2.5 kW/m2 it counts as zero in the dose
(ISO 13571:2012 §8.2, §8.4).

Panel (b): time to heat FED = 1 [min] in a uniform room at the defaults
of ``--heat-fed-method total-flux`` (eps 0.5, h 5, T_s 35 deg C, fatal
D = 16.7), with the threshold (the code) and with the radiant term always
counted, next to ISO Eq. (9), the default convective law. The endpoints
differ: ISO Eq. (9) is a time to prevention of escape, D = 16.7 the
Handbook's fatal dose.

Every value is computed through ``pyfds_evac`` (``DefaultHeatFedModel``
and the constants of ``pyfds_evac.core.fed``), so the figure follows the
code's defaults.

Run from the repository root::

    uv run python scripts/figures/heat_radiant_threshold.py

Writes ``site/static/images/concepts/heat_radiant_threshold.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from pyfds_evac.core.fed import (
    DEFAULT_HEAT_SKIN_TEMPERATURE_C,
    HEAT_CLOTHING_LAWS,
    HEAT_ENDPOINTS,
    ISO_RADIANT_THRESHOLD_KW_M2,
    DefaultFedConfig,
    DefaultHeatFedModel,
    total_flux_heat_fed_rate_per_minute,
    total_heat_flux_kw_m2,
)

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"


def radiant_term(t_c, emissivity):
    """Radiant term of Eq. 63.49 [kW/m2] at gas temperature t_c [deg C]."""
    return total_heat_flux_kw_m2(
        t_c,
        emissivity=emissivity,
        convective_coefficient=0.0,
        skin_temperature_celsius=DEFAULT_HEAT_SKIN_TEMPERATURE_C,
    )


def crossing(emissivity):
    """Temperature [deg C] at which the radiant term reaches 2.5 (bisection)."""
    lo, hi = DEFAULT_HEAT_SKIN_TEMPERATURE_C, 2000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if radiant_term(mid, emissivity) < ISO_RADIANT_THRESHOLD_KW_M2:
            lo = mid
        else:
            hi = mid
    return hi


def main():
    """Render heat_radiant_threshold.png into site/static/images/concepts.

    Parameters
    ----------
    None

    Saves
    -----
    site/static/images/concepts/heat_radiant_threshold.png
        150 dpi PNG.
    """
    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    pal = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
    red, orange = "#d73027", "#fc8d59"
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Data ---
    model = DefaultHeatFedModel(None, DefaultFedConfig(), method="total-flux")
    dose = HEAT_ENDPOINTS["fatal"].radiant_dose
    thr = ISO_RADIANT_THRESHOLD_KW_M2

    def minutes(t_c, counted):
        q = model.heat_flux_kw_m2(t_c, radiant_threshold=counted)
        return 1.0 / total_flux_heat_fed_rate_per_minute(q, dose)

    t_a = np.linspace(40.0, 750.0, 7101)
    emissivities = [
        (1.0, r"ε = 1 (or $\varphi\,\varepsilon_L$ = 1)", pal[5], "-"),
        (model.emissivity, f"ε = {model.emissivity:g} (default)", red, "--"),
        (0.05, "ε = 0.05 (clear air)", orange, ":"),
    ]

    t_b = np.linspace(100.0, 400.0, 3001)
    with_thr = np.array([minutes(t, True) for t in t_b])
    without_thr = np.array([minutes(t, False) for t in t_b])
    a_iso, b_iso = HEAT_CLOTHING_LAWS["clothed"]
    iso9 = a_iso * t_b**-b_iso
    t_step = crossing(model.emissivity)

    # --- Plot ---
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.4))

    ax_a.axhspan(0.0, thr, color="lightgrey", alpha=0.35, lw=0, zorder=0)
    ax_a.axhline(thr, color="dimgrey", lw=0.9)
    ax_a.text(
        400,
        2.05,
        "counted as zero",
        color="dimgrey",
        fontsize=9,
        va="center",
        ha="left",
    )
    offsets = {1.0: (-52, 8), model.emissivity: (6, -16), 0.05: (-52, 8)}
    for eps, label, colour, style in emissivities:
        q = np.array([radiant_term(t, eps) for t in t_a])
        ax_a.plot(t_a, q, color=colour, ls=style, lw=2, label=label)
        t_c = crossing(eps)
        ax_a.plot(t_c, thr, "o", color=colour, ms=6, zorder=5)
        ax_a.annotate(
            f"{t_c:.0f} °C",
            (t_c, thr),
            xytext=offsets[eps],
            textcoords="offset points",
            color="dimgrey",
            fontsize=9,
        )
    ax_a.set_ylim(0, 10)
    ax_a.set_xlim(40, 750)
    ax_a.set_xlabel("Source temperature [°C]", color="dimgrey")
    ax_a.set_ylabel("Radiant term of q [kW/m²]", color="dimgrey")
    ax_a.set_title(
        "(a) Where the radiant term starts to count", loc="left", fontsize=11
    )
    ax_a.legend(
        loc="upper left",
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=9,
    )

    ax_b.plot(
        t_b,
        without_thr,
        color=pal[3],
        ls="--",
        lw=1.6,
        label="total flux, radiant term always counted",
    )
    ax_b.plot(
        t_b,
        with_thr,
        color=red,
        lw=2.2,
        label=f"total flux, radiant term from {thr:g} kW/m² (code)",
    )
    ax_b.plot(
        t_b,
        iso9,
        color="grey",
        ls=":",
        lw=1.6,
        label="ISO Eq. (9), convective default (other endpoint)",
    )
    for t_c in (200.0,):
        y1, y0 = minutes(t_c, True), minutes(t_c, False)
        ax_b.plot([t_c, t_c], [y0, y1], "o", color="dimgrey", ms=5, zorder=5)
        ax_b.annotate(
            f"{t_c:.0f} °C: {y1:.1f} min\n(not counted: {y0:.1f} min)",
            (t_c, y1),
            xytext=(8, 4),
            textcoords="offset points",
            color="dimgrey",
            fontsize=9,
        )
    y_hi, y_lo = minutes(t_step - 1e-6, True), minutes(t_step, True)
    ax_b.annotate(
        f"step at {t_step:.0f} °C:\n{y_hi:.1f} → {y_lo:.1f} min",
        (t_step, y_lo),
        xytext=(18, 26),
        textcoords="offset points",
        color="dimgrey",
        fontsize=9,
        arrowprops={"arrowstyle": "-", "color": "dimgrey", "lw": 0.8},
    )
    ax_b.set_yscale("log")
    ax_b.set_xlim(100, 400)
    ax_b.set_ylim(0.3, 200)
    ax_b.set_xlabel("Gas temperature at the head [°C]", color="dimgrey")
    ax_b.set_ylabel("Time to heat FED = 1 [min]", color="dimgrey")
    ax_b.set_title(
        "(b) Time to FED = 1 at the total-flux defaults", loc="left", fontsize=11
    )
    ax_b.legend(
        loc="upper right",
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=9,
    )

    for ax in (ax_a, ax_b):
        sns.despine(ax=ax, left=True, bottom=True)
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    fig.tight_layout()

    # --- Save ---
    fig.savefig(OUT / "heat_radiant_threshold.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
