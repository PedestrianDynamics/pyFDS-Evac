"""Model documentation rendered in the GUI — warm-paper minimal layout.

Full-page overlay with its own sticky nav (back button fires the tab JS).
No MonsterUI/UIKit dependency — plain FastHTML + inline styles only.
Equation strings use $$ … $$ / $ … $; KaTeX auto-render handles them.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H1, Button, Div, NotStr, P, Span

# ── style tokens ──────────────────────────────────────────────────────────────
_MONO = "font-family:'JetBrains Mono',monospace"
_PRESS = "font-family:'Press Start 2P',monospace"
_BG = "#ECE8DF"
_INK = "#17150F"
_INK2 = "#3a362c"
_MUTED = "#6b655c"
_BLUE = "#1B17FF"
_BORDER = "rgba(0,0,0,.13)"

_NAV_STYLE = (
    f"position:sticky;top:0;z-index:6;display:flex;align-items:center;"
    f"justify-content:space-between;padding:16px 40px;"
    f"background:rgba(236,232,223,.88);backdrop-filter:blur(10px);"
    f"-webkit-backdrop-filter:blur(10px);"
    f"border-bottom:1px solid {_BORDER}"
)
_BACK_JS = (
    "document.querySelectorAll('.tab-btn').forEach(function(b){"
    "b.classList.toggle('active',b.dataset.tab==='sim')});"
    "document.getElementById('tab-sim').classList.remove('hidden');"
    "document.getElementById('tab-model').classList.add('hidden');"
    "var h=document.querySelector('.app-header');if(h)h.style.display='';"
    # Entering the model view hid the tab nav (which holds both tab buttons);
    # restore it on the way back so the Model/Simulation buttons reappear.
    "var n=document.querySelector('.tab-nav');if(n)n.style.display='';"
)
_P_STYLE = f"{_MONO};font-size:15px;line-height:1.72;color:{_INK2};margin:0 0 4px"
_EQ_STYLE = (
    f"margin:18px 0;padding:2px 0 2px 20px;border-left:2px solid {_BLUE};"
    f"overflow-x:auto"
)
_SEC_BORDER = f"border-top:1px solid {_BORDER};padding:34px 0"
_LABEL_STYLE = (
    f"{_MONO};font-size:12px;font-weight:600;letter-spacing:.22em;"
    f"text-transform:uppercase;color:{_INK}"
)
_NUM_STYLE = f"{_MONO};font-size:12px;color:{_BLUE}"


def _eq(latex: str) -> Any:
    return Div(latex, style=_EQ_STYLE)


def _sec(num: str, title: str, *body: Any) -> Any:
    return Div(
        Div(
            Span(num, style=_NUM_STYLE),
            Span(title, style=_LABEL_STYLE),
            style="display:flex;gap:16px;align-items:baseline;margin-bottom:18px",
        ),
        Div(*body, style="max-width:760px"),
        style=_SEC_BORDER,
    )


def _p(*args, **kw) -> Any:
    kw.setdefault("style", _P_STYLE)
    return P(*args, **kw)


def _tier(dot: str, name: str, rng: str) -> Any:
    return Div(
        Div(
            NotStr(
                f'<span style="width:8px;height:8px;border-radius:99px;'
                f'background:{dot};display:inline-block"></span>'
            ),
            Span(
                name,
                style=f"{_MONO};font-size:12px;font-weight:600;"
                f"letter-spacing:.1em;text-transform:uppercase;color:{_INK}",
            ),
            style="display:flex;align-items:center;gap:8px",
        ),
        Div(rng, style=f"{_MONO};font-size:13px;color:{_MUTED};padding-left:16px"),
        style="display:flex;flex-direction:column;gap:8px",
    )


def model_docs() -> Any:
    """Return the full-page Model documentation overlay."""
    nav = Div(
        NotStr(
            f'<div style="{_PRESS};font-size:8px;letter-spacing:.06em;color:{_INK}">'
            f'pyFDS-EVAC <span style="color:{_BLUE}">&#9656;</span> MODEL.SYS</div>'
        ),
        Button(
            "← Back to simulation",
            type="button",
            onclick=_BACK_JS,
            style=(
                f"background:none;border:0;cursor:pointer;{_MONO};"
                f"font-size:12px;letter-spacing:.08em;text-transform:uppercase;"
                f"color:{_BLUE};padding:6px 2px"
            ),
        ),
        style=_NAV_STYLE,
    )

    hero = Div(
        Div(
            "Technical reference — v2.4",
            style=f"{_MONO};font-size:11px;letter-spacing:.3em;text-transform:uppercase;"
            f"color:{_MUTED};margin-bottom:22px",
        ),
        H1(
            "THE MODEL.",
            style=(
                f"{_MONO};font-size:clamp(42px,7vw,72px);font-weight:700;"
                f"line-height:.96;letter-spacing:-.03em;color:{_INK};margin:0;"
                f"background:none"
            ),
        ),
        _p(
            "pyFDS-Evac couples a precomputed Fire Dynamics Simulator run to a "
            "JuPedSim pedestrian model through a routing layer. Each step samples "
            "the fire fields at every agent's position and updates walking speed "
            "(smoke), cumulative toxic dose (FED), and route choice.",
            style=f"{_MONO};font-size:16px;line-height:1.7;color:{_INK2};"
            f"max-width:680px;margin:30px 0 0",
        ),
        style="padding:64px 0 26px",
    )

    sections = Div(
        _sec(
            "01",
            "Smoke & Speed",
            _p(
                "Smoke slows walking. The Frantzich–Nilsson (Lund) law reduces "
                "clear-air speed $v_0$ by a factor of the local extinction "
                "coefficient $K$ [m⁻¹]:"
            ),
            _eq(
                r"$$ f(K) = \max\!\left(f_{\min},\; 1 + \tfrac{\beta}{\alpha}\,K\right), "
                r"\qquad v = v_0\, f(K) $$"
            ),
            _p(
                r"with $\alpha = 0.706$, $\beta = -0.057$, $f_{\min} = 0.1$. "
                r"Extinction comes from FDS soot density $\rho_s$ [mg/m³]:"
            ),
            _eq(
                r"$$ K = \kappa_m\,\rho_s\times 10^{-6}, \qquad "
                r"\kappa_m = 8700\ \mathrm{m^2/kg}. $$"
            ),
        ),
        _sec(
            "02",
            "FED Dose — ISO 13571",
            _p(
                "Each agent accumulates a Fractional Effective Dose from CO, "
                "cyanides/NOₓ, irritants and oxygen depletion, accelerated by "
                "CO₂-driven hyperventilation:"
            ),
            _eq(
                r"$$ \dot{D}_{\mathrm{tot}} = \left(\dot{D}_{\mathrm{CO}} + "
                r"\dot{D}_{\mathrm{CN}} + \dot{D}_{\mathrm{NO_x}} + "
                r"\dot{D}_{\mathrm{irr}}\right) HV_{\mathrm{CO_2}} + "
                r"\dot{D}_{\mathrm{O_2}} $$"
            ),
            _p(
                r"$D = 0.3$ marks incapacitation onset; $D = 1$ marks ~50% "
                r"incapacitation (untenable)."
            ),
        ),
        _sec(
            "03",
            "Tenability — FIC",
            _p(
                "An instantaneous Fractional Irritant Concentration captures "
                "sensory irritation and slows the agent further:"
            ),
            _eq(
                r"$$ \mathrm{FIC} = \sum_i \frac{C_i}{F_{\mathrm{FIC},i}}, "
                r"\qquad v_i = v_0\, f(K)\, "
                r"\max\!\left(\mu,\; 1 - \alpha_{\mathrm{FIC}}\,\mathrm{FIC}\right) $$"
            ),
            _p(
                r"At its incapacitation threshold the agent stops: "
                r"$D_i \ge D_{\mathrm{incap},i} \Rightarrow v_i = 0$, with "
                r"$D_{\mathrm{incap},i} = D_{50}\,e^{\sigma Z_i}$, "
                r"$Z_i \sim \mathcal{N}(0,1)$."
            ),
        ),
        _sec(
            "04",
            "Route Choice",
            _p(
                "Each candidate route is scored by a composite cost trading "
                "path length against smoke, projected dose and queueing:"
            ),
            _eq(
                r"$$ \mathcal{C}_k = L_k\!\left(1 + w_\sigma\,\bar{K}_k\right) + "
                r"w_F\,D_k^{\max} + w_q\,v_0\,\frac{N_k}{c_k} $$"
            ),
            _p(
                r"Agents periodically re-evaluate and switch to the cheapest "
                r"tenable exit; the weights $w_\sigma, w_F, w_q$ are configurable."
            ),
        ),
        # Tier table
        Div(
            Div(
                Span("05", style=_NUM_STYLE),
                Span("Tenability Tiers", style=_LABEL_STYLE),
                style="display:flex;gap:16px;align-items:baseline;margin-bottom:22px",
            ),
            Div(
                _tier("#3a9d6e", "Safe", "D = 0"),
                _tier("#d6a51f", "Alert", "0 < D < 0.3"),
                _tier("#e8590c", "Critical", "0.3 ≤ D < 1"),
                _tier("#cc2030", "Severe", "D ≥ 1"),
                style="display:grid;grid-template-columns:repeat(4,1fr);gap:22px;max-width:760px",
            ),
            _p(
                "Population bands (NIST TN 1797): ≈11% incapacitated by D = 0.3, "
                "≈50% by D = 1, ≈89% by D = 3. Each agent draws its own threshold "
                "from the log-normal above (median D₅₀ = 1, σ = 0.94).",
                style=f"{_MONO};font-size:14px;color:{_INK2};max-width:760px;margin-top:24px",
            ),
            style=_SEC_BORDER,
        ),
        # Footer
        Div(
            Div(
                "© 2024 pyFDS-EVAC — companion paper + docs/",
                style=f"{_MONO};font-size:11px;letter-spacing:.06em;color:{_MUTED}",
            ),
            NotStr(
                f'<div style="{_PRESS};font-size:7px;letter-spacing:.08em;color:#9a9488">EST. MMXXIV</div>'
            ),
            style=(
                f"border-top:1px solid {_BORDER};padding-top:26px;"
                f"display:flex;justify-content:space-between;align-items:center;"
                f"flex-wrap:wrap;gap:12px"
            ),
        ),
    )

    return Div(
        nav,
        Div(hero, sections, style="max-width:980px;margin:0 auto;padding:0 40px 90px"),
    )
