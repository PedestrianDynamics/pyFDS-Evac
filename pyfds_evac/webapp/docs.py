"""Model documentation rendered in the GUI.

Prose plus the governing equations (KaTeX), summarising the model described in
the companion paper: FDS-coupled smoke-speed reduction, ISO 13571 FED dose,
FIC tenability, and the composite route-choice cost. Equation strings use
``$$ … $$`` (display) and ``$ … $`` (inline); KaTeX auto-render turns them into
math at load. Raw strings keep the LaTeX backslashes intact.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div, P
from monsterui.all import Card, H3, H4


def _eq(latex: str) -> Any:
    return Div(latex, cls="eq")


def _section(title: str, *body: Any) -> Any:
    return Card(H3(title), *body, cls="doc-card")


def model_docs() -> Any:
    """Return the Model documentation panel."""
    return Div(
        P(
            "pyFDS-Evac couples a pre-computed Fire Dynamics Simulator (FDS) "
            "run to a JuPedSim pedestrian model through a routing layer. Each "
            "step samples the fire fields at every agent's position and updates "
            "three things: walking speed (smoke), cumulative toxic dose (FED), "
            "and route choice. The colour tiers above — Safe, Alert, Critical, "
            "Severe — are FED dose bands.",
            cls="doc-intro",
        ),
        _section(
            "Smoke and walking speed",
            P(
                "Smoke slows walking. The default Frantzich–Nilsson (Lund) law "
                "reduces the clear-air speed $v_0$ by a factor of the local "
                "extinction coefficient $K$ [m⁻¹]:"
            ),
            _eq(
                r"$$ f(K) = \max\!\left(f_{\min},\; 1 + \tfrac{\beta}{\alpha}\,K\right), "
                r"\qquad v = v_0\, f(K) $$"
            ),
            P(
                r"with $\alpha = 0.706$, $\beta = -0.057$, $f_{\min} = 0.1$. "
                r"Extinction comes from FDS soot density $\rho_s$ [mg/m³]:"
            ),
            _eq(
                r"$$ K = \kappa_m\,\rho_s\times 10^{-6}, \qquad "
                r"\kappa_m = 8700\ \mathrm{m^2/kg}. $$"
            ),
            P(
                r"An optional non-linear law (Fridolf) uses visibility "
                r"$V = C/K$ (Jin), asymptoting to zero without a hard floor:"
            ),
            _eq(r"$$ f(V) = \frac{V}{V + 2}. $$"),
        ),
        _section(
            "Toxic dose — Fractional Effective Dose (ISO 13571)",
            P(
                "Each agent accumulates a Fractional Effective Dose from carbon "
                "monoxide, cyanides/NOₓ, irritants and oxygen depletion, all "
                "accelerated by CO₂-driven hyperventilation:"
            ),
            _eq(
                r"$$ \dot{D}_{\mathrm{tot}} = \left(\dot{D}_{\mathrm{CO}} + "
                r"\dot{D}_{\mathrm{CN}} + \dot{D}_{\mathrm{NO_x}} + "
                r"\dot{D}_{\mathrm{irr}}\right) HV_{\mathrm{CO_2}} + "
                r"\dot{D}_{\mathrm{O_2}} $$"
            ),
            _eq(
                r"$$ \dot{D}_{\mathrm{CO}} = 2.764\times 10^{-5}\,"
                r"C_{\mathrm{CO}}^{\,1.036}, \qquad "
                r"HV_{\mathrm{CO_2}} = \frac{\exp(0.1903\,C_{\mathrm{CO_2}} + "
                r"2.0004)}{7.1} $$"
            ),
            P(r"The rate $\dot{D}$ is in min⁻¹; it is integrated each step:"),
            _eq(
                r"$$ D_i(t + \Delta t) = D_i(t) + \dot{D}_{\mathrm{tot}}\,"
                r"\frac{\Delta t}{60}. $$"
            ),
            P(
                r"$D = 0.3$ marks incapacitation onset for susceptible people "
                r"(Alert→Critical); $D = 1$ marks ~50 % incapacitation "
                r"(Severe / untenable)."
            ),
        ),
        _section(
            "Tenability",
            P(
                "Beyond cumulative dose, an instantaneous Fractional Irritant "
                "Concentration (FIC) captures sensory irritation and slows the "
                "agent further:"
            ),
            _eq(
                r"$$ \mathrm{FIC} = \sum_i \frac{C_i}{F_{\mathrm{FIC},i}}, "
                r"\qquad v_i = v_0\, f(K)\, "
                r"\max\!\left(\mu,\; 1 - \alpha_{\mathrm{FIC}}\,\mathrm{FIC}\right) $$"
            ),
            P(
                r"with $\alpha_{\mathrm{FIC}} = 0.7$ and a floor $\mu = 0.3$. "
                r"Unlike FED, FIC is not integrated, so an agent leaving the "
                r"plume recovers speed at once. At full dose it stops:"
            ),
            _eq(r"$$ D_i \ge 1 \;\Rightarrow\; v_i = 0. $$"),
            P(
                "This split — speed reduced by smoke and irritants, dose acting "
                "only as a binary stop — follows Purser & McAllister (SFPE "
                "Handbook): asphyxiants cause physiological collapse, while "
                "visibility and irritancy cause recoverable functional "
                "impairment.",
                cls="doc-foot",
            ),
        ),
        _section(
            "Route choice",
            P(
                "Each candidate exit route is scored by a composite cost that "
                "trades path length against smoke, projected dose and queueing:"
            ),
            _eq(
                r"$$ \mathcal{C}_k = L_k\!\left(1 + w_\sigma\,\bar{K}_k\right) + "
                r"w_F\,D_k^{\max} + w_q\,v_0\,\frac{N_k}{c_k}, $$"
            ),
            P(
                r"where $L_k$ is path length, $\bar{K}_k$ the path-mean "
                r"extinction, $D_k^{\max}$ the dose projected at arrival, and "
                r"$N_k/c_k$ the queue at exit $k$ (occupancy over capacity). "
                r"Agents periodically re-evaluate and switch to the cheapest "
                r"tenable exit; the weights $w_\sigma, w_F, w_q$ are configurable."
            ),
        ),
        _section(
            "Tier thresholds",
            Div(
                Div(H4("Safe", cls="m-0"), P("D = 0", cls="m-0"), cls="tier-card safe"),
                Div(
                    H4("Alert", cls="m-0"),
                    P("0 < D < 0.3", cls="m-0"),
                    cls="tier-card alert",
                ),
                Div(
                    H4("Critical", cls="m-0"),
                    P("0.3 ≤ D < 1", cls="m-0"),
                    cls="tier-card critical",
                ),
                Div(
                    H4("Severe", cls="m-0"),
                    P("D ≥ 1", cls="m-0"),
                    cls="tier-card severe",
                ),
                cls="tier-grid",
            ),
            P(
                "These are population bands (NIST high-rise tenability, TN 1797): "
                "≈11 % of occupants incapacitated by D = 0.3, ≈50 % by D = 1, "
                "≈89 % by D = 3. The simulation currently applies D ≥ 1 uniformly "
                "to every agent — the median endpoint; per-agent susceptibility "
                "is planned.",
                cls="doc-foot",
            ),
        ),
        P(
            "Full derivations, the 12-species FED table and validation are in "
            "the companion paper (pyFDS-Evac). See also the project README and "
            "docs/ for configuration.",
            cls="doc-foot",
        ),
        cls="space-y-5",
    )
