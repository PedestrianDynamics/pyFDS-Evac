"""Model documentation rendered in the GUI — warm-paper minimal layout.

Full-page overlay with its own sticky nav (back button fires the tab JS).
No MonsterUI/UIKit dependency — plain FastHTML + inline styles only.
Equation strings use $$ … $$ / $ … $; KaTeX auto-render handles them.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H1, A, Button, Code, Div, NotStr, P, Span

# ── style tokens ──────────────────────────────────────────────────────────────
_MONO = "font-family:'JetBrains Mono',monospace"
_PRESS = "font-family:'Press Start 2P',monospace"
_BG = "var(--ink)"
_INK = "#17150F"
_INK2 = "#3a362c"
_MUTED = "var(--ink-faint)"
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
    "b.classList.toggle('active',b.dataset.tab==='sim');"
    "b.setAttribute('aria-selected',String(b.dataset.tab==='sim'))});"
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


_DOCS = "https://pedestriandynamics.org/pyFDS-Evac/"
_ROW_KEY = (
    f"{_MONO};font-size:11px;letter-spacing:.12em;text-transform:uppercase;"
    f"color:{_MUTED};min-width:110px"
)
_ROW_VAL = f"{_MONO};font-size:14px;line-height:1.6;color:{_INK2}"
_TAG = (
    f"{_MONO};font-size:12px;font-weight:600;letter-spacing:.08em;"
    f"padding:2px 8px;border:1px solid {_BORDER};border-radius:6px;color:{_INK}"
)


def _link(text: str, path: str) -> Any:
    return A(
        text, href=_DOCS + path, target="_blank", rel="noopener", style=f"color:{_BLUE}"
    )


def _row(key: str, *value: Any) -> Any:
    return Div(
        Span(key, style=_ROW_KEY),
        Div(*value, style=_ROW_VAL),
        style="display:flex;flex-wrap:wrap;gap:4px 14px;margin:8px 0",
    )


def _controls(*pairs: tuple[str, str]) -> Any:
    """GUI field labels with their run.py flags."""
    items = []
    for label, flag in pairs:
        if items:
            items.append("; ")
        items += [f"“{label}” (", Code(flag), ")"]
    return _row("Control", *items)


def _mech(
    num: str,
    title: str,
    what: list[Any],
    default: str,
    controls: Any,
    equation: Any | None,
    more: Any,
) -> Any:
    """One mechanism: what it does, default, control, equation, read more."""
    body = [*what, _row("Default", Span(default, style=_TAG)), controls]
    if equation is not None:
        body.append(equation)
    body.append(_row("Read more", more))
    return _sec(num, title, *body)


def model_docs() -> Any:
    """Return the full-page Model documentation overlay.

    Every statement here follows the code and the Models pages of the
    documentation site; defaults are those of run.py, which the GUI uses.
    """
    from .runner import code_provenance

    version = code_provenance()[0] or "version not recorded"
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
        cls="doc-nav",
    )

    hero = Div(
        Div(
            f"pyFDS-Evac {version}",
            style=f"{_MONO};font-size:11px;letter-spacing:.3em;text-transform:uppercase;"
            f"color:{_MUTED};margin-bottom:22px",
        ),
        H1(
            "How the model works in this version",
            style=(
                f"{_MONO};font-size:clamp(30px,5vw,52px);font-weight:700;"
                f"line-height:1.05;letter-spacing:-.02em;color:{_INK};margin:0;"
                f"background:none"
            ),
        ),
        _p(
            "pyFDS-Evac couples a precomputed Fire Dynamics Simulator run to a "
            "JuPedSim pedestrian model. At each update it samples the fire fields "
            "at every agent's position; smoke sets walking speed and route choice, "
            "and the doses can incapacitate agents. Which mechanisms run depends on "
            "the settings below and on the slices in the FDS output. A default is "
            "not a claim that a setting suits every case.",
            style=f"{_MONO};font-size:16px;line-height:1.7;color:{_INK2};"
            f"max-width:680px;margin:30px 0 0",
        ),
        _p(
            "The full specification, with sources and limitations, is on the ",
            _link("Models pages", "models/"),
            ".",
            style=f"{_MONO};font-size:14px;color:{_INK2};margin:14px 0 0",
        ),
        style="padding:64px 0 26px",
    )

    sections = Div(
        _mech(
            "01",
            "Smoke and walking speed",
            [
                _p(
                    "Smoke slows walking. The extinction coefficient $K$ [1/m] at "
                    "the agent's position, read from the FDS SOOT EXTINCTION "
                    "COEFFICIENT slice or set as a constant, reduces the clear-air "
                    "speed $v_0$ by the Frantzich–Nilsson (Lund) factor:"
                ),
            ],
            "On with an FDS dir or a constant extinction",
            _controls(
                ("FDS dir", "--fds-dir"),
                ("Constant extinction", "--constant-extinction"),
                ("Smoke update interval", "--smoke-update-interval"),
            ),
            Div(
                _eq(
                    r"$$ f(K) = \min\!\left(1,\ \max\!\left(f_{\min},\ "
                    r"1 + \tfrac{\beta}{\alpha}\,K\right)\right), "
                    r"\qquad v = v_0\, f(K) $$"
                ),
                _p(
                    r"with $\alpha = 0.706$ m/s, $\beta = -0.057$ m²/s, "
                    r"$f_{\min} = 0.1$. Another law (Fridolf) and other "
                    r"coefficients are set from Python, not in the GUI."
                ),
            ),
            _link("Smoke-speed model", "models/smoke-speed/"),
        ),
        _mech(
            "02",
            "Sampling the fire fields",
            [
                _p(
                    "Walking speed, route smoke and the gas and heat doses read "
                    "the horizontal FDS slice nearest the slice height, an absolute "
                    "z in the FDS domain, not a height above each floor. If the "
                    "nearest slice is more than 0.5 m away, the run logs a warning "
                    "and carries on at that slice's height."
                ),
            ],
            "1.6 m, as FDS+Evac (HUMAN_SMOKE_HEIGHT)",
            _controls(("Smoke slice height", "--smoke-slice-height")),
            None,
            _link("FDS slice sampling", "docs/fds-sampling/"),
        ),
        _mech(
            "03",
            "Toxic gas: Fractional Effective Dose (FED)",
            [
                _p(
                    "Each agent accumulates a gas FED from CO, cyanide and NOₓ, "
                    "irritants and oxygen depletion, accelerated by CO₂-driven "
                    "hyperventilation, as in FDS+Evac. It needs CO, CO₂ and O₂ "
                    "slices; the other species count when present."
                ),
                _p(
                    "When an agent's FED reaches its threshold, the agent stops "
                    "and stays in place as an obstacle. By default every agent "
                    "has the same threshold, 1.0. In probabilistic mode each "
                    r"agent draws its own, $D_i = D\,e^{\sigma Z_i}$ with "
                    r"$Z_i \sim \mathcal{N}(0,1)$ and $\sigma = 0.94$ by default. "
                    "“Disable tenability” stops nobody; the dose is still "
                    "computed. FED 1 describes the median occupant, not whether "
                    "a design is acceptable."
                ),
            ],
            "On when the case has CO, CO₂ and O₂ slices; deterministic",
            _controls(
                ("Fed threshold", "--fed-threshold"),
                ("Incapacitation Mode", "--incapacitation-mode"),
                ("Susceptibility σ", "--susceptibility-sigma"),
                ("O2 threshold percent", "--o2-threshold-percent"),
                ("Disable tenability", "--disable-tenability"),
            ),
            _eq(
                r"$$ \dot{D} = \left(\dot{D}_{\mathrm{CO}} + "
                r"\dot{D}_{\mathrm{CN}} + \dot{D}_{\mathrm{NO_x}} + "
                r"\dot{D}_{\mathrm{irr}}\right) HV_{\mathrm{CO_2}} + "
                r"\dot{D}_{\mathrm{O_2}} \quad [1/\mathrm{min}] $$"
            ),
            _link("Fractional effective dose", "models/fed/"),
        ),
        _mech(
            "04",
            "Irritant slowdown (FIC)",
            [
                _p(
                    "Optional. The instantaneous Fractional Irritant Concentration "
                    "slows the agent on top of the smoke factor. FDS+Evac has no "
                    "irritant slowdown; the rule is a pyFDS-Evac assumption with "
                    "no known source (#147)."
                ),
            ],
            "Off",
            _controls(
                ("Enable fic speed", "--enable-fic-speed"),
                ("Fic alpha", "--fic-alpha"),
                ("Fic min factor", "--fic-min-factor"),
            ),
            _eq(
                r"$$ \mathrm{FIC} = \sum_i \frac{C_i}{F_{\mathrm{FIC},i}}, "
                r"\qquad v = v_0\, f(K)\, "
                r"\max\!\left(\mu,\; 1 - \alpha_{\mathrm{FIC}}\,\mathrm{FIC}\right) $$"
            ),
            _link(
                "Tenability: irritant slowdown and incapacitation",
                "models/fed/#tenability-irritant-slowdown-and-incapacitation",
            ),
        ),
        _mech(
            "05",
            "Heat dose",
            [
                _p(
                    "Optional. A convective heat dose from the FDS TEMPERATURE "
                    "slice, kept apart from the gas FED; it can incapacitate an "
                    "agent by itself. Heat does not slow agents and plays no part "
                    "in route choice. The default law is ISO 13571:2012 Eq. (9), "
                    "fully clothed, with $T$ in °C; “Heat clothing” selects the "
                    "unclothed law. The SFPE endpoints and the total-flux method "
                    "are under Other."
                ),
            ],
            "Off; when on: clothed, deterministic",
            _controls(
                ("Enable heat fed", "--enable-heat-fed"),
                ("Heat clothing", "--heat-clothing"),
                ("Heat incapacitation mode", "--heat-incapacitation-mode"),
            ),
            _eq(
                r"$$ \dot{D}_{\mathrm{heat}} = T^{3.61} / (4.1 \times 10^{8}) "
                r"\quad [1/\mathrm{min}] $$"
            ),
            _link("Heat", "models/heat/"),
        ),
        _mech(
            "06",
            "One threshold for gas and heat",
            [
                _p(
                    "The heat dose uses the gas threshold, as ISO 13571:2012 asks "
                    "for one threshold for FED and FEC (§5.4). Setting a separate "
                    "heat threshold departs from ISO; the run logs a warning and "
                    "the manifest records the override."
                ),
            ],
            "Heat threshold = Fed threshold",
            _controls(("Heat fed threshold", "--heat-fed-threshold")),
            None,
            _link("Heat › Incapacitation", "models/heat/#incapacitation"),
        ),
        _mech(
            "07",
            "Route choice",
            [
                _p(
                    "Agents re-evaluate their route at the reroute interval. With "
                    "the default gate cost model a route's optical depth "
                    r"$\tau = \bar{K} L$, the mean extinction along the route times "
                    r"the distance still to walk, refuses routes above "
                    r"$\tau_{\max} = 6$ (0.8 $\tau_{\max}$ for a switch to "
                    "another exit) and orders the rest, with travel time breaking "
                    "ties; in clear air that is the nearest exit. With the gas FED "
                    "model loaded, a route whose projected FED exceeds 1.0 is also "
                    "refused (0.9 of that for another exit). The cost model and "
                    "its weights are set in the scenario's routing block."
                ),
            ],
            "On, every 1 s",
            _controls(
                ("Enable rerouting", "--enable-rerouting"),
                ("Reroute interval", "--reroute-interval"),
            ),
            None,
            _link("Dynamic route rerouting", "models/routing/"),
        ),
        _mech(
            "08",
            "Wayfinding",
            [
                _p(
                    "Agents not fully familiar with the building learn exits from "
                    "signs; whether a sign is legible through the smoke between "
                    "agent and sign decides which exits they know. Familiarity "
                    "and signs are set in the scenario; the GUI has no control "
                    "for them. “Vis cache” (--vis-cache) only stores the "
                    "sign-visibility map between runs."
                ),
            ],
            "From the scenario",
            _row("Control", "none in the GUI"),
            None,
            _link("Wayfinding", "models/wayfinding/"),
        ),
    )

    return Div(
        nav,
        Div(
            hero,
            sections,
            cls="doc-body",
            style="max-width:980px;margin:0 auto;padding:0 40px 90px",
        ),
    )
