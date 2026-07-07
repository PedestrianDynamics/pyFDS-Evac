"""FastHTML web GUI for pyFDS-Evac — no MonsterUI/UIKit dependency.

All visual components use plain FastHTML primitives with inline styles that
match the redesigned "Instrument" prototype exactly. All route logic, SSE
streaming and JS helpers are unchanged from the original.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import quote

from fasthtml.common import (
    B, Button, Div, EventStream, Form, H3, I, Input, Link,
    NotStr, Option, P, Pre, Script, Select, Span, Title,
    fast_app, serve, sse_message,
)
from starlette.requests import Request

from pyfds_evac.core import load_scenario
from pyfds_evac.core.run_config import build_run_kwargs

from . import docs, params, plots, theme, trajviz
from .runner import RunManager

_PLOTLY_CDN = Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js")
_HTMX_SSE  = Script(src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.3/dist/sse.js")
_KATEX = (
    Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"),
    Script(src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"),
    Script(src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"),
)

# No MonsterUI/UIKit – custom theme only
app, rt = fast_app(
    hdrs=(*theme.headers(), _HTMX_SSE, _PLOTLY_CDN, *_KATEX),
    pico=False,
)
manager = RunManager()

_TIERS = [("safe","Safe"),("alert","Alert"),("critical","Critical"),("severe","Severe")]

# ── style tokens ─────────────────────────────────────────────────────────────
_CARD   = "background:#2A262A;border:1px solid rgba(255,255,255,.07);border-radius:1.1rem;padding:20px;box-shadow:0 8px 24px rgba(0,0,0,.45)"
_PANEL  = "background:#14161B;border:1px solid rgba(255,255,255,.07);border-radius:1.25rem;padding:24px;box-shadow:0 18px 50px rgba(0,0,0,.35)"
_INNER  = "background:#252127;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:14px 16px"
_MONO   = "font-family:'JetBrains Mono',monospace"
_GROTESK= "font-family:'Space Grotesk',sans-serif"
_INK    = "color:#F2EDE9"
_INK2   = "color:#B2A9A3"
_MUTED  = "color:#837A74"

_FED_LIVE_JS = """
(function () {
  var fedLayout = {
    margin: {l: 46, r: 14, t: 14, b: 34},
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: {family: 'JetBrains Mono, monospace', color: '#B2A9A3', size: 10},
    height: 180,
    legend: {bgcolor: 'rgba(0,0,0,0)', font: {size: 9}, orientation: 'h', y: -0.22},
    xaxis: {title: {text: 'sim time (s)', font: {size: 9}}, gridcolor: 'rgba(255,255,255,.06)', tickfont: {size: 9}},
    yaxis: {title: {text: 'FED', font: {size: 9}}, gridcolor: 'rgba(255,255,255,.06)', rangemode: 'tozero', tickfont: {size: 9}},
    shapes: [
      {type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 0.3, y1: 0.3,
       line: {color: 'rgba(255,176,32,.55)', dash: 'dot', width: 1}},
      {type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 1.0, y1: 1.0,
       line: {color: 'rgba(224,30,55,.55)', dash: 'dot', width: 1}}
    ]
  };
  var fedChartReady = false;
  function fedColor(v) {
    return v >= 1.0 ? '#E01E37' : v >= 0.6 ? '#FF6A1A' : v >= 0.3 ? '#FFB020' : '#F4C430';
  }
  var fedEs = new EventSource('/fed-progress');
  fedEs.addEventListener('fed', function (e) {
    try {
      var d = JSON.parse(e.data);
      if (!d.t || !d.t.length) return;
      var section = document.getElementById('fed-live-section');
      if (section) section.style.display = '';
      var traces = [
        {x: d.t, y: d.max, mode: 'lines', name: 'max FED', line: {color: '#F4C430', width: 2}},
        {x: d.t, y: d.mean, mode: 'lines', name: 'mean FED', line: {color: '#FF8A3D', width: 1.5, dash: 'dot'}}
      ];
      if (!fedChartReady) {
        Plotly.newPlot('fed-live-chart', traces, fedLayout, {displayModeBar: false, responsive: true});
        fedChartReady = true;
      } else {
        Plotly.react('fed-live-chart', traces, fedLayout, {displayModeBar: false, responsive: true});
      }
      var last = d.max[d.max.length - 1];
      var numEl = document.getElementById('fed-live-num');
      if (numEl) { numEl.textContent = last.toFixed(4); numEl.style.color = fedColor(last); }
      var barEl = document.getElementById('fed-live-bar');
      if (barEl) barEl.style.width = Math.min(100, last * 100) + '%';
    } catch (err) { console.warn('FED chart update failed:', err); }
  });
  fedEs.addEventListener('close', function () { fedEs.close(); });
  fedEs.onerror = function () { fedEs.close(); };
})();
"""

# ── logo ─────────────────────────────────────────────────────────────────────
_LOGO_SVG = NotStr("""
<svg class="app-logo" viewBox="0 0 40 40" width="40" height="40" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
  <rect x="0.5" y="0.5" width="39" height="39" rx="10.5" fill="#211e20" stroke="rgba(255,255,255,0.10)"/>
  <circle cx="20" cy="20" r="14.5" fill="none" stroke="#f4c430" stroke-width="1.6" opacity="0.55"/>
  <circle cx="20" cy="20" r="10"   fill="none" stroke="#ffb020" stroke-width="1.6" opacity="0.7"/>
  <circle cx="20" cy="20" r="5.5"  fill="none" stroke="#ff6a1a" stroke-width="1.7" opacity="0.9"/>
  <circle cx="20" cy="20" r="2.4"  fill="#e01e37"/>
  <circle cx="28.5" cy="11.5" r="2.1" fill="#f4c430"/>
</svg>
""")


def _legend() -> Div:
    return Div(
        Div("Tenability tiers", cls="legend-label"),
        Div(*[Div(I(cls="sw"), label, cls=f"tier {name}") for name, label in _TIERS], cls="tier-row"),
        cls="tier-legend",
    )


def _fed_live_section() -> Div:
    return Div(
        Div(
            Div("FED Exposure", style=f"{_MONO};font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;{_MUTED};margin-bottom:8px"),
            Div(
                Div("max", style=f"{_MONO};font-size:8px;letter-spacing:.06em;text-transform:uppercase;{_MUTED};margin-bottom:2px"),
                Div("—", id="fed-live-num", style=f"{_MONO};font-size:22px;font-weight:500;color:#F4C430;transition:color .3s;line-height:1"),
            ),
            style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px",
        ),
        # Bar with threshold tick at 0.3
        Div(
            Div(id="fed-live-bar",
                style="position:absolute;top:0;left:0;height:100%;width:0%;border-radius:99px;background:linear-gradient(90deg,#F4C430,#FFB020,#FF6A1A,#E01E37);transition:width .4s"),
            # tick mark at 30%
            Div(style="position:absolute;top:-2px;left:30%;width:1px;height:calc(100% + 4px);background:rgba(255,176,32,.55)"),
            style="position:relative;height:7px;border-radius:99px;background:#1F1C1F;border:1px solid rgba(255,255,255,.06);overflow:visible;margin-bottom:5px",
        ),
        # Labels pinned to exact bar positions
        Div(
            Span("0",    style=f"{_MONO};font-size:8px;{_MUTED};position:absolute;left:0"),
            Span("0.3",  style=f"{_MONO};font-size:8px;color:#FFB020;position:absolute;left:30%;transform:translateX(-50%)"),
            Span("1.0",  style=f"{_MONO};font-size:8px;color:#E01E37;position:absolute;right:0"),
            style="position:relative;height:12px;margin-bottom:8px",
        ),
        Div(id="fed-live-chart"),
        style=_PANEL + ";width:220px;flex:none",
        id="fed-live-section",
    )

def _header() -> Div:
    return Div(
        Div(
            _LOGO_SVG,
            Div(
                Div("pyFDS", B("·EVAC", style="color:#FF6A1A"), cls="brand"),
                Div("fire-coupled evacuation · FDS × JuPedSim × ISO 13571", cls="tagline"),
            ),
            cls="brand-group",
        ),
        cls="app-header rise",
    )


def _sidebar() -> Div:
    return Div(
        Div(
            Div(
                Div("Parameters", style=f"{_GROTESK};font-weight:600;font-size:16px;letter-spacing:-.01em;{_INK}"),
                Span("run.py", style=f"{_MONO};font-size:10px;{_MUTED};padding:3px 8px;border:1px solid rgba(255,255,255,.08);border-radius:6px"),
                style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px",
            ),
            params.build_form("/run"),
            style=f"{_PANEL};position:sticky;top:88px;display:flex;flex-direction:column;gap:14px",
        ),
        cls="rise",
        style="animation-delay:.06s",
    )


def _run_panel_idle() -> Div:
    return Div(
        Div(
            Div(
                Div(I(cls="dot"), "Standby", cls="standby-label"),
                Div(
                    Div("Configure a scenario, then run.", style=f"{_GROTESK};font-weight:600;font-size:22px;letter-spacing:-.02em;{_INK};margin-bottom:10px"),
                    P("Live telemetry streams as the coupled fire–pedestrian model steps. When it settles you'll explore agent trajectories, FED dose, smoke and route cost — all interactive.",
                      style=f"font-size:.85rem;line-height:1.7;{_INK2};margin:0"),
                    style="max-width:46ch",
                ),
                _legend(),
                cls="standby",
            ),
            style=_PANEL,
        ),
        id="run-panel",
        cls="rise",
        style="animation-delay:.12s",
    )


# Output-file defaults from the selected scenario name (client-side autofill).
_AUTOFILL_JS = """
(function () {
  var OUT = {
    output_sqlite:             function (n) { return 'results/' + clean(n) + '/' + clean(n) + '.sqlite'; },
    output_smoke_history:      function (n) { return 'results/' + clean(n) + '/' + clean(n) + '_smoke_history.csv'; },
    output_fed_history:        function (n) { return 'results/' + clean(n) + '/' + clean(n) + '_fed_history.csv'; },
    output_route_history:      function (n) { return 'results/' + clean(n) + '/' + clean(n) + '_route_history.csv'; },
    output_route_cost_history: function (n) { return 'results/' + clean(n) + '/' + clean(n) + '_route_cost_history.csv'; }
  };
  function scenarioName() {
    var inp = document.querySelector('input[name="scenario"]');
    var sel = document.querySelector('#scenario select');
    return (inp && inp.value) || (sel && sel.value) || '';
  }
  function clean(n) { return n.replace(/\\.json$/i, '').replace(/\\//g, '_'); }
  function fill(n) {
    var base = n ? clean(n) : '';
    Object.keys(OUT).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.dataset.userEdited) el.value = base ? OUT[id](base) : '';
    });
  }
  var last = null;
  setInterval(function () { var n = scenarioName(); if (n !== last) { last = n; fill(n); } }, 250);
  document.addEventListener('input', function (e) {
    if (e.target && OUT[e.target.id]) e.target.dataset.userEdited = '1';
  });
  // Strip surrounding quotes from path inputs on blur
  document.addEventListener('blur', function (e) {
    var el = e.target;
    if (!el || el.tagName !== 'INPUT' || el.type === 'hidden' || el.type === 'checkbox') return;
    var v = el.value;
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      el.value = v.slice(1, -1);
      el.dispatchEvent(new Event('input'));
    }
  }, true);
})();
"""

_NAV = NotStr(
    '<div class="tab-nav"><div class="tab-pills">'
    '<button class="tab-btn active" data-tab="sim" type="button">Simulation</button>'
    '<button class="tab-btn" data-tab="model" type="button">Model</button>'
    '</div></div>'
)

_TAB_JS = """
document.addEventListener('click', function (e) {
  var b = e.target.closest && e.target.closest('.tab-btn');
  if (!b) return;
  var t = b.dataset.tab;
  document.querySelectorAll('.tab-btn').forEach(function (x) {
    x.classList.toggle('active', x === b);
  });
  document.getElementById('tab-sim').classList.toggle('hidden', t !== 'sim');
  document.getElementById('tab-model').classList.toggle('hidden', t !== 'model');
  var hdr = document.querySelector('.app-header');
  if (hdr) hdr.style.display = (t === 'model') ? 'none' : '';
  var nav = document.querySelector('.tab-nav');
  if (nav) nav.style.display = (t === 'model') ? 'none' : '';
  if (t === 'model' && window._renderMath) window._renderMath();
});
"""

_TENABILITY_JS = """
function drawIncapDist() {
  var canvas = document.getElementById('incap-canvas');
  var dist   = document.getElementById('incap-dist');
  if (!canvas || !dist || dist.style.display === 'none') return;

  var sigmaEl = document.getElementById('susceptibility_sigma');
  var sigma = sigmaEl ? (parseFloat(sigmaEl.value) || 0.94) : 0.94;
  var mu = Math.log(0.3);  // median incapacitation at FED = 0.3

  var dpr = window.devicePixelRatio || 1;
  var cw = canvas.clientWidth, ch = canvas.clientHeight;
  if (!cw || !ch) { setTimeout(drawIncapDist, 80); return; }
  canvas.width = cw * dpr; canvas.height = ch * dpr;
  var ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cw, ch);

  var pL = 28, pR = 10, pT = 18, pB = 18;
  var pw = cw - pL - pR, ph = ch - pT - pB;
  var fedMax = 1.8, N = 400;

  // Compute log-normal PDF: f(x) = 1/(x*σ*√2π) * exp(-(ln(x)-μ)²/(2σ²))
  var pts = [], yMax = 0;
  for (var i = 1; i <= N; i++) {
    var fed = (i / N) * fedMax;
    var z = (Math.log(fed) - mu) / sigma;
    var pdf = Math.exp(-0.5 * z * z) / (fed * sigma * Math.sqrt(2 * Math.PI));
    pts.push([fed, pdf]);
    if (pdf > yMax) yMax = pdf;
  }
  yMax *= 1.18;

  function tx(v) { return pL + (v / fedMax) * pw; }
  function ty(v) { return pT + (1 - v / yMax) * ph; }

  // Background
  ctx.fillStyle = '#131113'; ctx.fillRect(0, 0, cw, ch);

  // Horizontal grid
  ctx.strokeStyle = 'rgba(255,255,255,.05)'; ctx.lineWidth = 1;
  [0.25, 0.5, 0.75, 1.0].forEach(function (f) {
    ctx.beginPath(); ctx.moveTo(pL, pT + (1 - f) * ph); ctx.lineTo(cw - pR, pT + (1 - f) * ph); ctx.stroke();
  });

  // Shaded fill — horizontal gradient through FED tiers
  var gFill = ctx.createLinearGradient(tx(0), 0, tx(fedMax), 0);
  gFill.addColorStop(0,            'rgba(244,196,48,.28)');
  gFill.addColorStop(0.3  / 1.8,  'rgba(255,176,32,.28)');
  gFill.addColorStop(0.6  / 1.8,  'rgba(255,106,26,.28)');
  gFill.addColorStop(1.0  / 1.8,  'rgba(224,30,55,.28)');
  gFill.addColorStop(1,            'rgba(224,30,55,.10)');
  ctx.beginPath();
  ctx.moveTo(tx(pts[0][0]), pT + ph);
  pts.forEach(function (p) { ctx.lineTo(tx(p[0]), ty(p[1])); });
  ctx.lineTo(tx(pts[pts.length - 1][0]), pT + ph);
  ctx.closePath(); ctx.fillStyle = gFill; ctx.fill();

  // Curve line — same gradient
  var gLine = ctx.createLinearGradient(tx(0), 0, tx(fedMax), 0);
  gLine.addColorStop(0,           '#F4C430');
  gLine.addColorStop(0.3  / 1.8, '#FFB020');
  gLine.addColorStop(0.6  / 1.8, '#FF6A1A');
  gLine.addColorStop(1.0  / 1.8, '#E01E37');
  gLine.addColorStop(1,          '#E01E37');
  ctx.beginPath();
  pts.forEach(function (p, i) {
    i === 0 ? ctx.moveTo(tx(p[0]), ty(p[1])) : ctx.lineTo(tx(p[0]), ty(p[1]));
  });
  ctx.strokeStyle = gLine; ctx.lineWidth = 1.8; ctx.stroke();

  // Threshold verticals
  ctx.setLineDash([3, 3]);
  [[0.3, 'rgba(255,176,32,.6)', '0.3'], [1.0, 'rgba(224,30,55,.6)', '1.0']].forEach(function (th) {
    ctx.strokeStyle = th[1]; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(tx(th[0]), pT); ctx.lineTo(tx(th[0]), pT + ph); ctx.stroke();
    ctx.fillStyle = th[1]; ctx.font = '7.5px JetBrains Mono, monospace';
    ctx.textAlign = 'left'; ctx.fillText(th[2], tx(th[0]) + 2, pT + 8);
  });
  ctx.setLineDash([]);

  // Axes
  ctx.strokeStyle = 'rgba(255,255,255,.18)'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pL, pT); ctx.lineTo(pL, pT + ph); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(pL, pT + ph); ctx.lineTo(cw - pR, pT + ph); ctx.stroke();

  // X-axis ticks
  ctx.fillStyle = '#837A74'; ctx.font = '8px JetBrains Mono, monospace'; ctx.textAlign = 'center';
  [0, 0.3, 0.6, 0.9, 1.2, 1.5].forEach(function (v) {
    ctx.fillText(v.toFixed(1), tx(v), pT + ph + 12);
  });

  // Axis labels
  ctx.fillStyle = '#837A74'; ctx.font = '7.5px JetBrains Mono, monospace';
  ctx.textAlign = 'right'; ctx.fillText('density', pL - 2, pT + 4);
  ctx.textAlign = 'center'; ctx.fillText('FED threshold', pL + pw / 2, pT + ph + 17);

  // Annotation: σ + mode
  var mode = Math.exp(mu - sigma * sigma);
  ctx.fillStyle = '#B2A9A3'; ctx.font = '7.5px JetBrains Mono, monospace'; ctx.textAlign = 'left';
  ctx.fillText('σ=' + sigma.toFixed(2) + '  mode≈' + mode.toFixed(2), pL + 2, pT - 5);
}

function setTenabilityMode(mode) {
  document.getElementById('incapacitation_mode').value = mode;
  document.getElementById('btn-prob').classList.toggle('active', mode === 'probabilistic');
  document.getElementById('btn-det').classList.toggle('active', mode === 'deterministic');
  var row  = document.getElementById('sigma-row');
  var dist = document.getElementById('incap-dist');
  if (row)  row.style.display  = mode === 'deterministic' ? 'none' : '';
  if (dist) dist.style.display = mode === 'deterministic' ? 'none' : '';
  if (mode === 'probabilistic') drawIncapDist();
}

document.addEventListener('input', function (e) {
  if (e.target && e.target.id === 'susceptibility_sigma') drawIncapDist();
});
document.addEventListener('DOMContentLoaded', function () { drawIncapDist(); });
setTimeout(drawIncapDist, 150);
"""

_MATH_JS = """
window._renderMath = function () {
  if (!window.renderMathInElement) return;
  renderMathInElement(document.getElementById('tab-model') || document.body, {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$',  right: '$',  display: false }
    ],
    throwOnError: false
  });
};
window._renderMath();
document.addEventListener('DOMContentLoaded', window._renderMath);
"""


@rt("/")
def index():
    grid = Div(
        _sidebar(),
        _run_panel_idle(),
        style="display:grid;grid-template-columns:340px 1fr;gap:20px;max-width:1480px;margin:0 auto;padding:24px 26px 60px",
    )
    return (
        Title("pyFDS-Evac · control"),
        _header(),
        _NAV,
        Div(
            Div(grid, id="tab-sim"),
            Div(docs.model_docs(), id="tab-model", cls="hidden"),
        ),
        Div(id="dir-modal"),
        Script(_AUTOFILL_JS),
        Script(_TAB_JS),
        Script(_MATH_JS),
        Script(_TENABILITY_JS),
    )


# ── directory browser ─────────────────────────────────────────────────────────
_DIR_ROOT = Path.home()


def _safe_dir(path: str) -> Path:
    candidate = Path(path) if path else params._REPO_ROOT
    try:
        resolved = candidate.resolve()
    except Exception:
        return _DIR_ROOT
    if resolved != _DIR_ROOT and _DIR_ROOT not in resolved.parents:
        return _DIR_ROOT
    return resolved if resolved.is_dir() else _DIR_ROOT


_CLOSE_MODAL = "document.getElementById('dir-modal').innerHTML=''"
_BTN_GHOST   = f"display:flex;align-items:center;gap:8px;width:100%;text-align:left;padding:10px 12px;background:transparent;border:0;border-radius:9px;{_INK};{_MONO};font-size:12.5px;cursor:pointer"


def _nav_row(label: str, target: Path, mode: str, field: str):
    href = f"/browse-dir?path={quote(str(target))}&mode={mode}&field={field}"
    return Button(
        NotStr('<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 4.5h12v7a1 1 0 01-1 1H2a1 1 0 01-1-1v-7zm0 0V3.5a1 1 0 011-1h3l1.5 1.5H12a1 1 0 011 1V4.5" stroke="#F6C544" stroke-width="1.2" stroke-linejoin="round"/></svg>'),
        label, type="button",
        hx_get=href, hx_target="#dir-modal", hx_swap="innerHTML",
        style=_BTN_GHOST,
    )


def _file_row(target: Path, field: str):
    pick = f"document.getElementById({json.dumps(field)}).value={json.dumps(str(target))};{_CLOSE_MODAL}"
    return Button(
        NotStr('<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 1.5h7l3 3v8a1 1 0 01-1 1H2a1 1 0 01-1-1v-10a1 1 0 011-1zm7 0v3h3" stroke="#3B82F6" stroke-width="1.2" stroke-linejoin="round"/></svg>'),
        target.name, type="button", onclick=pick, style=_BTN_GHOST,
    )


@rt("/browse-dir")
def browse_dir(path: str = "", mode: str = "dir", field: str = "fds_dir"):
    current = _safe_dir(path)
    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        entries = []
    subdirs = sorted((e for e in entries if e.is_dir() and not e.name.startswith(".")), key=lambda p: p.name.lower())
    rows = []
    if current != _DIR_ROOT:
        rows.append(_nav_row("..", current.parent, mode, field))
    rows.extend(_nav_row(d.name, d, mode, field) for d in subdirs)
    if mode == "file":
        files = sorted((e for e in entries if e.is_file() and not e.name.startswith(".")), key=lambda p: p.name.lower())
        rows.extend(_file_row(f, field) for f in files)
    if not rows:
        rows.append(P("Empty folder.", style=f"font-size:.85rem;{_MUTED};padding:8px"))

    title_text = "Select a folder" if mode == "dir" else "Select a file"
    footer_btns = [
        Button("Cancel", type="button", onclick=_CLOSE_MODAL,
               style=f"background:#3A343A;border:1px solid rgba(255,255,255,.1);border-radius:9px;padding:8px 16px;{_INK2};{_GROTESK};font-size:13px;cursor:pointer"),
    ]
    if mode == "dir":
        use = f"document.getElementById({json.dumps(field)}).value={json.dumps(str(current))};{_CLOSE_MODAL}"
        footer_btns.append(
            Button("Use this folder", type="button", onclick=use,
                   style=f"background:linear-gradient(180deg,#FFC24D,#E8590C);border:0;border-radius:9px;padding:8px 16px;color:#2A1606;{_GROTESK};font-size:13px;font-weight:600;cursor:pointer"),
        )

    dialog = Div(
        Div(
            Div(title_text, style=f"{_GROTESK};font-weight:600;font-size:16px;{_INK}"),
            P(str(current), style=f"{_MONO};font-size:11.5px;{_MUTED};margin-top:4px;word-break:break-all"),
            style="padding:18px 20px;border-bottom:1px solid rgba(255,255,255,.07)",
        ),
        Div(*rows, style="max-height:340px;overflow:auto;padding:8px"),
        Div(*footer_btns, style="display:flex;justify-content:flex-end;gap:10px;padding:14px 20px;border-top:1px solid rgba(255,255,255,.07)"),
        style=f"width:520px;max-width:92vw;background:#14161B;border:1px solid rgba(255,255,255,.10);border-radius:18px;box-shadow:0 30px 80px rgba(0,0,0,.6);overflow:hidden",
        onclick="event.stopPropagation()",
    )
    return Div(
        dialog,
        style="position:fixed;inset:0;z-index:80;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(5,6,8,.62);backdrop-filter:blur(4px)",
        onclick=_CLOSE_MODAL,
    )


# ── run routes ────────────────────────────────────────────────────────────────
@rt("/run")
async def post(request: Request):
    form = dict(await request.form())
    scenario_name = form.get("scenario")
    if not scenario_name:
        return Div("Select a scenario first.", style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px")

    try:
        scenario   = load_scenario(f"assets/{scenario_name}")
        opts       = params.form_to_opts(form)
        run_kwargs = build_run_kwargs(scenario, opts)
        import run as cli
        def post_run(result):
            return cli.apply_outputs(result, scenario, opts, log=lambda _m: None)
        manager.start(
            scenario, run_kwargs, scenario_name,
            post_run=post_run, fds_dir=getattr(opts, "fds_dir", None),
        )
    except Exception as exc:
        return Div(f"{type(exc).__name__}: {exc}", style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px")

    return Div(
        Div(_running_card(None), id="run-status", sse_swap="progress,done"),
        Div(
            Div(
                Div(
                    NotStr(
                        '<span style="display:flex;gap:6px">'
                        '<span style="width:10px;height:10px;border-radius:99px;background:#E01E37"></span>'
                        '<span style="width:10px;height:10px;border-radius:99px;background:#F4C430"></span>'
                        '<span style="width:10px;height:10px;border-radius:99px;background:#FF6A1A"></span>'
                        '</span>'
                    ),
                    Span("console", style=f"{_MONO};font-size:11px;{_MUTED};margin-left:6px"),
                    style="display:flex;align-items:center;gap:9px;padding:14px 20px;border-bottom:1px solid rgba(255,255,255,.06)",
                ),
                Pre("Waiting for output…", id="console-log", cls="console-box",
                    sse_swap="console",
                    **{"hx-on:htmx:after-swap": "this.scrollTop = this.scrollHeight"}),
            ),
            style=_PANEL + ";margin-top:18px",
        ),
        hx_ext="sse", sse_connect="/progress", sse_close="done",
    )


def _console_view() -> Pre:
    text = "\n".join(manager.log_lines[-300:]) or "Waiting for output…"
    return Pre(text)


def _running_card(ev) -> Div:
    line = (
        f"evacuated {ev.evacuated}/{ev.total} · sim {ev.sim_time:.1f}s · "
        f"wall {ev.wall_time:.0f}s · {ev.pct}%"
        if ev else "Initialising…"
    )
    pct = ev.pct if ev else 0
    return Div(
        Div(
            Div(
                Span(style="width:9px;height:9px;border-radius:99px;background:#FF7A45;animation:pulse 1.6s infinite;display:block"),
                Div(
                    Div(f"Running: {manager.scenario_name}", style=f"{_GROTESK};font-weight:600;font-size:17px;{_INK}"),
                    Div("coupled FDS × JuPedSim step loop", style=f"{_MONO};font-size:11px;{_MUTED};margin-top:2px"),
                ),
                style="display:flex;align-items:center;gap:12px",
            ),
            Div(f"{pct}%", style=f"{_GROTESK};font-weight:700;font-size:30px;letter-spacing:-.02em;color:#F4C430"),
            style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px",
        ),
        Div(
            Div(style=f"height:100%;width:{max(pct,3)}%;border-radius:99px;background:linear-gradient(90deg,#F4C430,#FFB020,#FF6A1A);transition:width .35s cubic-bezier(.4,0,.2,1)"),
            style="height:10px;border-radius:99px;background:#1F1C1F;border:1px solid rgba(255,255,255,.06);overflow:hidden;margin-bottom:18px",
        ),
        Div(line, style=f"{_MONO};font-size:.82rem;{_INK2}"),
        style=_PANEL,
    )


def _finished_view() -> Div:
    result   = manager.result
    scenario = None
    try:
        scenario = load_scenario(f"assets/{manager.scenario_name}")
    except Exception:
        pass

    status  = "finished" if result.agents_remaining == 0 else "stopped"
    metrics = [
        ("Status",         f"{status} ({result.metrics.get('success')})"),
        ("Evacuation time", f"{result.evacuation_time:.1f} s"),
        ("Evacuated",       f"{result.agents_evacuated}/{result.total_agents}"),
        ("Remaining",       f"{result.agents_remaining}"),
    ]
    accents = ["#F4C430","#F4C430","#3B82F6","#E01E37"]

    kpi_tiles = Div(
        *[
            Div(
                Div(k, style=f"{_MONO};font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;{_MUTED}"),
                Div(v, style=f"{_MONO};font-size:19px;font-weight:500;margin-top:7px;{_INK}"),
                style=f"background:#14161B;border:1px solid rgba(255,255,255,.07);border-top:2px solid {a};border-radius:14px;padding:15px 16px",
            )
            for (k, v), a in zip(metrics, accents)
        ],
        style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px",
    )
    if manager.artifacts:
        art = Div(
            Div("Artifacts written", style=f"{_MONO};font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;{_MUTED};margin-bottom:4px"),
            *[Div(a, cls="artifact") for a in manager.artifacts],
            style="margin-top:12px",
        )
    else:
        art = Div()

    def plot_card(title, fig, div_id):
        return Div(
            Div(title, style=f"{_GROTESK};font-weight:600;font-size:15px;{_INK};margin-bottom:10px"),
            plots.figure_html(fig, div_id),
            style=_CARD,
        )

    return Div(
        kpi_tiles, art,
        trajviz.trajectory_component(result, scenario, fds_dir=manager.fds_dir),
        plot_card("Cumulative FED", plots.fed_figure(result), "fig-fed"),
        plot_card("Smoke",          plots.smoke_figure(result), "fig-smoke"),
        plot_card("Route cost",     plots.route_cost_figure(result), "fig-route"),
        cls="space-y-6",
        style="display:flex;flex-direction:column;gap:18px",
    )


@rt("/fed-progress")
async def fed_progress():
    async def gen():
        last_count = 0
        while True:
            snaps = manager.fed_snapshots
            if len(snaps) > last_count:
                last_count = len(snaps)
                payload = json.dumps({
                    "t":    [s[0] for s in snaps],
                    "max":  [s[1] for s in snaps],
                    "mean": [s[2] for s in snaps],
                })
                yield sse_message(payload, event="fed")
            if manager.status in ("done", "error", "idle"):
                yield sse_message("{}", event="close")
                return
            await asyncio.sleep(0.5)
    return EventStream(gen())


@rt("/progress")
async def progress():
    async def gen():
        last = None
        last_log = -1
        while True:
            n = len(manager.log_lines)
            if n != last_log:
                last_log = n
                yield sse_message(_console_view(), event="console")
            status = manager.status
            if status == "done":
                try:
                    finished = _finished_view()
                except Exception as exc:
                    import traceback
                    err = traceback.format_exc()
                    finished = Div(
                        Div(f"Results error: {type(exc).__name__}: {exc}",
                            style="color:#E01E37;font-family:'JetBrains Mono',monospace;font-size:.8rem;margin-bottom:8px"),
                        Pre(err, style="color:#B2A9A3;font-family:'JetBrains Mono',monospace;font-size:.72rem;white-space:pre-wrap;overflow:auto;max-height:300px"),
                        style="background:#14161B;border:1px solid #E01E37;border-radius:12px;padding:16px",
                    )
                yield sse_message(finished, event="done")
                return
            if status == "error":
                yield sse_message(
                    Div(f"Run failed: {manager.error}",
                        style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px"),
                    event="done",
                )
                return
            if status == "idle":
                return
            ev = manager.last_event
            if ev is not None and ev != last:
                last = ev
                yield sse_message(_running_card(ev), event="progress")
            await asyncio.sleep(0.1)
    return EventStream(gen())


if __name__ == "__main__":
    serve()
