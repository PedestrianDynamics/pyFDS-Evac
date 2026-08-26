"""FastHTML web GUI for pyFDS-Evac — no MonsterUI/UIKit dependency.

All visual components use plain FastHTML primitives with inline styles that
match the redesigned "Instrument" prototype exactly. All route logic, SSE
streaming and JS helpers are unchanged from the original.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

from fasthtml.common import (
    B,
    Button,
    Div,
    EventStream,
    Link,
    NotStr,
    P,
    Pre,
    Script,
    Span,
    Title,
    fast_app,
    serve,
    sse_message,
)
from starlette.requests import Request

from pyfds_evac.core import load_scenario
from pyfds_evac.core.run_config import build_run_kwargs, validate_opts

from . import docs, params, plots, theme, trajviz
from .runner import RunManager

_PLOTLY_CDN = Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js")
_HTMX_SSE = Script(src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.3/dist/sse.js")
_KATEX = (
    Link(
        rel="stylesheet",
        href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css",
    ),
    Script(src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"),
    Script(
        src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
    ),
)

# No MonsterUI/UIKit – custom theme only
app, rt = fast_app(
    hdrs=(*theme.headers(), _HTMX_SSE, _PLOTLY_CDN, *_KATEX),
    pico=False,
)
manager = RunManager()

# ── style tokens ─────────────────────────────────────────────────────────────
_CARD = "background:var(--surface-card);border:1px solid var(--hairline);border-radius:1.1rem;padding:20px;box-shadow:var(--shadow-md)"
_PANEL = "background:var(--surface-panel);border:1px solid var(--hairline);border-radius:1.25rem;padding:24px;box-shadow:var(--shadow-lg)"
_INNER = "background:var(--surface-accent);border:1px solid var(--hairline);border-radius:12px;padding:14px 16px"
_MONO = "font-family:'JetBrains Mono',monospace"
_GROTESK = "font-family:'Space Grotesk',sans-serif"
_INK = "color:var(--ink)"
_INK2 = "color:var(--ink-dim)"
_MUTED = "color:var(--ink-faint)"

_FED_LIVE_JS = """
(function () {
  // Plotly resolves no CSS variables, so the themed values are read off
  // the document and refreshed whenever the theme flips.
  function themeInk() {
    return getComputedStyle(document.documentElement)
      .getPropertyValue('--ink-dim').trim() || '#b2a9a3';
  }
  function themeGrid() {
    return document.documentElement.getAttribute('data-theme') === 'light'
      ? 'rgba(31,23,16,.13)' : 'rgba(255,255,255,.10)';
  }
  var fedLayout = {
    margin: {l: 46, r: 14, t: 14, b: 34},
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: {family: 'JetBrains Mono, monospace', color: themeInk(), size: 10},
    height: 180,
    legend: {bgcolor: 'rgba(0,0,0,0)', font: {size: 9}, orientation: 'h', y: -0.22},
    xaxis: {title: {text: 'sim time (s)', font: {size: 9}}, gridcolor: themeGrid(), tickfont: {size: 9}},
    yaxis: {title: {text: 'FED', font: {size: 9}}, gridcolor: themeGrid(), rangemode: 'tozero', tickfont: {size: 9}},
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
      fedLayout.font.color = themeInk();
      fedLayout.xaxis.gridcolor = themeGrid();
      fedLayout.yaxis.gridcolor = themeGrid();
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
  <rect x="0.5" y="0.5" width="39" height="39" rx="10.5" fill="var(--surface-page)" stroke="var(--hairline-strong)"/>
  <circle cx="20" cy="20" r="14.5" fill="none" stroke="#f4c430" stroke-width="1.6" opacity="0.55"/>
  <circle cx="20" cy="20" r="10"   fill="none" stroke="#ffb020" stroke-width="1.6" opacity="0.7"/>
  <circle cx="20" cy="20" r="5.5"  fill="none" stroke="#ff6a1a" stroke-width="1.7" opacity="0.9"/>
  <circle cx="20" cy="20" r="2.4"  fill="#e01e37"/>
  <circle cx="28.5" cy="11.5" r="2.1" fill="#f4c430"/>
</svg>
""")


def _fed_live_section() -> Div:
    return Div(
        Div(
            Div(
                "FED Exposure",
                style=f"{_MONO};font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;{_MUTED};margin-bottom:8px",
            ),
            Div(
                Div(
                    "max",
                    style=f"{_MONO};font-size:8px;letter-spacing:.06em;text-transform:uppercase;{_MUTED};margin-bottom:2px",
                ),
                Div(
                    "—",
                    id="fed-live-num",
                    style=f"{_MONO};font-size:22px;font-weight:500;color:#F4C430;transition:color .3s;line-height:1",
                ),
            ),
            style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px",
        ),
        # Bar with threshold tick at 0.3
        Div(
            Div(
                id="fed-live-bar",
                style="position:absolute;top:0;left:0;height:100%;width:0%;border-radius:99px;background:linear-gradient(90deg,#F4C430,#FFB020,#FF6A1A,#E01E37);transition:width .4s",
            ),
            # tick mark at 30%
            Div(
                style="position:absolute;top:-2px;left:30%;width:1px;height:calc(100% + 4px);background:rgba(255,176,32,.55)"
            ),
            style="position:relative;height:7px;border-radius:99px;background:var(--surface-page);border:1px solid var(--hairline);overflow:visible;margin-bottom:5px",
        ),
        # Labels pinned to exact bar positions
        Div(
            Span("0", style=f"{_MONO};font-size:8px;{_MUTED};position:absolute;left:0"),
            Span(
                "0.3",
                style=f"{_MONO};font-size:8px;color:#FFB020;position:absolute;left:30%;transform:translateX(-50%)",
            ),
            Span(
                "1.0",
                style=f"{_MONO};font-size:8px;color:#E01E37;position:absolute;right:0",
            ),
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
                Div(
                    "fire-coupled evacuation · FDS × JuPedSim × ISO 13571",
                    cls="tagline",
                ),
            ),
            cls="brand-group",
        ),
        cls="app-header rise",
    )


def _sidebar() -> Div:
    return Div(
        Div(
            Div(
                Div(
                    "Parameters",
                    style=f"{_GROTESK};font-weight:600;font-size:16px;letter-spacing:-.01em;{_INK}",
                ),
                Span(
                    "run.py",
                    style=f"{_MONO};font-size:10px;{_MUTED};padding:3px 8px;border:1px solid var(--hairline);border-radius:6px",
                ),
                style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px",
            ),
            params.build_form("/run"),
            style=f"{_PANEL};position:sticky;top:88px;display:flex;flex-direction:column;gap:14px",
        ),
        cls="rise",
        style="animation-delay:.06s",
    )


def _warnings_card(messages: list[str]) -> Div:
    """Show engine warnings above the results, or nothing when the run was clean.

    These describe runs that *succeeded* but sampled something other than what
    was asked for -- a slice at the wrong height, agents outside the FDS
    domain. The numbers below look no different either way, so the only signal
    a GUI user gets is this card.
    """

    if not messages:
        return Div()
    heading = "1 warning" if len(messages) == 1 else f"{len(messages)} warnings"
    return Div(
        Div(
            f"{heading} during this run",
            style=(
                f"{_GROTESK};font-weight:600;font-size:15px;color:#F4C430;"
                "margin-bottom:10px"
            ),
        ),
        *[
            P(
                message,
                style=f"font-size:.82rem;line-height:1.6;{_INK2};margin:0 0 8px",
            )
            for message in messages
        ],
        P(
            "The run completed, but these affect what the results describe. "
            "See docs/fds-case-requirements.md.",
            style=f"font-size:.78rem;line-height:1.6;{_INK2};margin:10px 0 0;opacity:.8",
        ),
        style=(
            "background:var(--surface-card);border:1px solid rgba(244,196,48,.35);"
            "border-radius:1.1rem;padding:20px;box-shadow:var(--shadow-md)"
        ),
    )


def _run_panel_idle_body() -> Div:
    """Standby contents of the run panel.

    Kept separate from the ``#run-panel`` wrapper because the run form and
    the cancel/clear actions swap this element's *innerHTML* -- returning the
    wrapper too would nest a second ``#run-panel`` inside the first.
    """
    return Div(
        Div(
            Div(
                _LOGO_SVG,
                style=(
                    "width:64px;height:64px;border-radius:50%;display:flex;"
                    "align-items:center;justify-content:center;"
                    "background:rgba(255,106,26,.07);margin:0 auto 20px;"
                    "animation:pulse 2.6s ease-in-out infinite"
                ),
            ),
            Div(
                Div(
                    "Choose a scenario and ",
                    B("run", style="color:#FF6A1A"),
                    style=f"{_GROTESK};font-weight:600;font-size:22px;letter-spacing:-.02em;{_INK}",
                ),
                style="max-width:46ch;text-align:center",
            ),
            cls="standby",
        ),
        style=_PANEL,
    )


def _run_panel_idle() -> Div:
    return Div(
        _run_panel_idle_body(),
        id="run-panel",
        cls="rise",
        style="animation-delay:.12s",
    )


# Output-file defaults from the selected scenario name (client-side autofill).
_AUTOFILL_JS = """
(function () {
  var OUT = {
    output_sqlite:             function (n, d) { return d + '/' + n + '.sqlite'; },
    output_smoke_history:      function (n, d) { return d + '/' + n + '_smoke_history.csv'; },
    output_fed_history:        function (n, d) { return d + '/' + n + '_fed_history.csv'; },
    output_route_history:      function (n, d) { return d + '/' + n + '_route_history.csv'; },
    output_route_cost_history: function (n, d) { return d + '/' + n + '_route_cost_history.csv'; },
    export_app_bundle:         function (n, d) { return d + '/bundle'; }
  };
  function scenarioName() {
    // The picker is a <select id="scenario">, not a wrapper around one, so
    // match on the form name -- that holds however it ends up being rendered.
    var el = document.querySelector('[name="scenario"]');
    return (el && el.value) || '';
  }
  function fdsDirValue() {
    var el = document.getElementById('fds_dir');
    return (el && el.value.trim()) || '';
  }
  function seedValue() {
    var el = document.getElementById('seed');
    return (el && el.value.trim()) || 'default';
  }
  function modeValue() {
    var el = document.querySelector('[name="incapacitation_mode"]');
    return (el && el.value) || 'probabilistic';
  }
  function clean(n) { return n.replace(/\\.json$/i, '').replace(/\\//g, '_'); }
  // The typed "Output folder", normalised. Empty means "use the derived path".
  function outputBase() {
    var el = document.getElementById('output_base');
    if (!el) return '';
    return el.value.trim().replace(/\\\\/g, '/').replace(/\\/+$/, '');
  }
  function fill(n) {
    var base = n ? clean(n) : '';
    var derived = base ? 'results/' + base + '/' + modeValue() + '/seed' + seedValue() : '';
    // Show the derived folder as a placeholder rather than a value, so an empty
    // box still tells you where output lands while a typed path clearly wins.
    var ob = document.getElementById('output_base');
    if (ob) ob.placeholder = derived || 'results/<scenario>';
    var dir = outputBase() || derived;
    Object.keys(OUT).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.dataset.userEdited) el.value = base ? OUT[id](base, dir) : '';
    });
    // Preview lines under the folder box, so the section shows the real
    // filenames instead of a literal "<run>".
    document.querySelectorAll('.artifact-preview').forEach(function (el) {
      el.textContent = (base || '<run>') + el.dataset.suffix;
    });
  }
  var last = null;
  var lastFdsDir = null;
  function fillVisCache() {
    var fdsDir = fdsDirValue();
    var el = document.getElementById('vis_cache');
    if (el && !el.dataset.userEdited) el.value = fdsDir ? fdsDir + '/vis_cache.npz' : '';
  }
  setInterval(function () {
    var k = scenarioName() + '|' + seedValue() + '|' + modeValue() + '|' + outputBase();
    if (k !== last) { last = k; fill(scenarioName()); }
    var fdsDir = fdsDirValue();
    if (fdsDir !== lastFdsDir) { lastFdsDir = fdsDir; fillVisCache(); }
  }, 250);
  document.addEventListener('input', function (e) {
    if (e.target && (OUT[e.target.id] || e.target.id === 'vis_cache')) {
      e.target.dataset.userEdited = '1';
    }
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
    "</div></div>"
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

# Reflect run state on the submit button: disable + relabel while a run is in
# flight, restore when it finishes (or fails), so a second click can't stomp
# the active run.
_RUN_BTN_JS = """
(function () {
  // Both submit buttons post to /run; either one starting a run must lock out
  // the other, so they are relabelled together.
  var LABELS = {
    'run-btn':     { idle: 'Run scenario', icon: '▶' },
    'results-btn': { idle: 'Results only', icon: '↓' }
  };
  function setRunning(on) {
    Object.keys(LABELS).forEach(function (id) {
      var b = document.getElementById(id); if (!b) return;
      b.disabled = on;
      var lbl = b.querySelector('.run-btn-label');
      var ico = b.querySelector('.run-btn-icon');
      if (lbl) lbl.textContent = on ? 'Scenario in progress…' : LABELS[id].idle;
      if (ico) ico.textContent = on ? '⏳' : LABELS[id].icon;
    });
  }
  function isRunPath(d) {
    var p = (d && d.pathInfo && (d.pathInfo.requestPath || d.pathInfo.path)) ||
            (d && d.requestConfig && d.requestConfig.path) || '';
    return p === '/run';
  }
  document.body.addEventListener('htmx:beforeRequest', function (e) {
    if (isRunPath(e.detail)) setRunning(true);
  });
  // The /run response either starts a run (its HTML contains an SSE stream)
  // or is an error/guard message — re-enable when no stream was started.
  document.body.addEventListener('htmx:afterRequest', function (e) {
    if (!isRunPath(e.detail)) return;
    var xhr = e.detail && e.detail.xhr;
    var txt = (xhr && xhr.responseText) || '';
    if (txt.indexOf('sse-connect') === -1) setRunning(false);
  });
  // Run finished: the progress stream closed (sse-close="done").
  document.body.addEventListener('htmx:sseClose', function () { setRunning(false); });
  // Cancelling swaps the whole panel away, which tears down the SSE element
  // without necessarily firing sseClose -- unlock the buttons explicitly.
  function isPath(d, want) {
    var p = (d && d.pathInfo && (d.pathInfo.requestPath || d.pathInfo.path)) ||
            (d && d.requestConfig && d.requestConfig.path) || '';
    return p === want;
  }
  document.body.addEventListener('htmx:beforeRequest', function (e) {
    if (!isPath(e.detail, '/cancel')) return;
    var c = document.getElementById('cancel-btn');
    if (c) {
      c.disabled = true;
      var cl = c.querySelector('.run-btn-label');
      if (cl) cl.textContent = 'Cancelling…';
    }
  });
  document.body.addEventListener('htmx:afterRequest', function (e) {
    if (isPath(e.detail, '/cancel') || isPath(e.detail, '/clear')) setRunning(false);
  });
  document.body.addEventListener('htmx:responseError', function (e) {
    if (isRunPath(e.detail)) setRunning(false);
  });
})();
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

  // Canvas takes literal colours only, so the theme is read here rather
  // than inherited; drawIncapDist re-runs on every theme flip.
  var _cs = getComputedStyle(document.documentElement);
  function cssVar(n, fallback) {
    return (_cs.getPropertyValue(n) || '').trim() || fallback;
  }

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
  ctx.fillStyle = cssVar('--surface-panel', '#14161b'); ctx.fillRect(0, 0, cw, ch);

  // Horizontal grid
  ctx.strokeStyle = cssVar('--hairline-soft', 'rgba(255,255,255,.04)'); ctx.lineWidth = 1;
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
  ctx.strokeStyle = cssVar('--hairline-badge', 'rgba(255,255,255,.18)'); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pL, pT); ctx.lineTo(pL, pT + ph); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(pL, pT + ph); ctx.lineTo(cw - pR, pT + ph); ctx.stroke();

  // X-axis ticks
  ctx.fillStyle = cssVar('--ink-faint', '#837a74'); ctx.font = '8px JetBrains Mono, monospace'; ctx.textAlign = 'center';
  [0, 0.3, 0.6, 0.9, 1.2, 1.5].forEach(function (v) {
    ctx.fillText(v.toFixed(1), tx(v), pT + ph + 12);
  });

  // Axis labels
  ctx.fillStyle = cssVar('--ink-faint', '#837a74'); ctx.font = '7.5px JetBrains Mono, monospace';
  ctx.textAlign = 'right'; ctx.fillText('density', pL - 2, pT + 4);
  ctx.textAlign = 'center'; ctx.fillText('FED threshold', pL + pw / 2, pT + ph + 17);

  // Annotation: σ + mode
  var mode = Math.exp(mu - sigma * sigma);
  ctx.fillStyle = cssVar('--ink-dim', '#b2a9a3'); ctx.font = '7.5px JetBrains Mono, monospace'; ctx.textAlign = 'left';
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


# Drag-and-drop onto the upload zone. A file <input> can only be populated from
# a DataTransfer, so the drop handler assigns dataTransfer.files directly rather
# than trying to read the files itself.
_UPLOAD_JS = """
(function () {
  function zone() { return document.getElementById('upload-drop'); }
  function input() { var z = zone(); return z && z.querySelector('input[type=file]'); }
  function names(list) {
    return Array.prototype.map.call(list, function (f) { return f.name; }).join(', ');
  }
  function show() {
    var i = input(), out = document.getElementById('upload-picked');
    if (!i || !out) return;
    out.textContent = i.files && i.files.length ? names(i.files) : '';
  }
  document.addEventListener('change', function (e) {
    if (e.target && e.target.matches('#upload-drop input[type=file]')) show();
  });
  ['dragenter', 'dragover'].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var z = zone(); if (!z || !z.contains(e.target)) return;
      e.preventDefault(); z.classList.add('over');
    });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var z = zone(); if (!z || !z.contains(e.target)) return;
      z.classList.remove('over');
    });
  });
  document.addEventListener('drop', function (e) {
    var z = zone(), i = input();
    if (!z || !i || !z.contains(e.target)) return;
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      i.files = e.dataTransfer.files;
      show();
    }
  });
  // A successful upload swaps in a new picker; clear the staged files so the
  // same drop can't be submitted twice by accident.
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.target && e.target.id === 'scenario-block') {
      var i = input(); if (i) { i.value = ''; show(); }
    }
  });
})();
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
        theme.switch(),
        Div(id="dir-modal"),
        theme.script(),
        Script(_AUTOFILL_JS),
        Script(_TAB_JS),
        Script(_MATH_JS),
        Script(_TENABILITY_JS),
        Script(_RUN_BTN_JS),
        Script(_UPLOAD_JS),
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
_BTN_GHOST = f"display:flex;align-items:center;gap:8px;width:100%;text-align:left;padding:10px 12px;background:transparent;border:0;border-radius:9px;{_INK};{_MONO};font-size:12.5px;cursor:pointer"


def _nav_row(label: str, target: Path, mode: str, field: str):
    href = f"/browse-dir?path={quote(str(target))}&mode={mode}&field={field}"
    return Button(
        NotStr(
            '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 4.5h12v7a1 1 0 01-1 1H2a1 1 0 01-1-1v-7zm0 0V3.5a1 1 0 011-1h3l1.5 1.5H12a1 1 0 011 1V4.5" stroke="#F6C544" stroke-width="1.2" stroke-linejoin="round"/></svg>'
        ),
        label,
        type="button",
        hx_get=href,
        hx_target="#dir-modal",
        hx_swap="innerHTML",
        style=_BTN_GHOST,
    )


def _file_row(target: Path, field: str):
    pick = f"document.getElementById({json.dumps(field)}).value={json.dumps(str(target))};{_CLOSE_MODAL}"
    return Button(
        NotStr(
            '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 1.5h7l3 3v8a1 1 0 01-1 1H2a1 1 0 01-1-1v-10a1 1 0 011-1zm7 0v3h3" stroke="#3B82F6" stroke-width="1.2" stroke-linejoin="round"/></svg>'
        ),
        target.name,
        type="button",
        onclick=pick,
        style=_BTN_GHOST,
    )


@rt("/browse-dir")
def browse_dir(path: str = "", mode: str = "dir", field: str = "fds_dir"):
    current = _safe_dir(path)
    try:
        entries = list(current.iterdir())
    except (PermissionError, OSError):
        entries = []
    subdirs = sorted(
        (e for e in entries if e.is_dir() and not e.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )
    rows = []
    if current != _DIR_ROOT:
        rows.append(_nav_row("..", current.parent, mode, field))
    rows.extend(_nav_row(d.name, d, mode, field) for d in subdirs)
    if mode == "file":
        files = sorted(
            (e for e in entries if e.is_file() and not e.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
        rows.extend(_file_row(f, field) for f in files)
    if not rows:
        rows.append(P("Empty folder.", style=f"font-size:.85rem;{_MUTED};padding:8px"))

    title_text = "Select a folder" if mode == "dir" else "Select a file"
    footer_btns = [
        Button(
            "Cancel",
            type="button",
            onclick=_CLOSE_MODAL,
            style=f"background:var(--surface-raised);border:1px solid var(--hairline-strong);border-radius:9px;padding:8px 16px;{_INK2};{_GROTESK};font-size:13px;cursor:pointer",
        ),
    ]
    if mode == "dir":
        use = f"document.getElementById({json.dumps(field)}).value={json.dumps(str(current))};{_CLOSE_MODAL}"
        footer_btns.append(
            Button(
                "Use this folder",
                type="button",
                onclick=use,
                style=f"background:linear-gradient(180deg,#FFC24D,#E8590C);border:0;border-radius:9px;padding:8px 16px;color:var(--on-heat);{_GROTESK};font-size:13px;font-weight:600;cursor:pointer",
            ),
        )

    dialog = Div(
        Div(
            Div(title_text, style=f"{_GROTESK};font-weight:600;font-size:16px;{_INK}"),
            P(
                str(current),
                style=f"{_MONO};font-size:11.5px;{_MUTED};margin-top:4px;word-break:break-all",
            ),
            style="padding:18px 20px;border-bottom:1px solid var(--hairline)",
        ),
        Div(*rows, style="max-height:340px;overflow:auto;padding:8px"),
        Div(
            *footer_btns,
            style="display:flex;justify-content:flex-end;gap:10px;padding:14px 20px;border-top:1px solid var(--hairline)",
        ),
        style="width:520px;max-width:92vw;background:var(--surface-panel);border:1px solid var(--hairline-strong);border-radius:18px;box-shadow:var(--shadow-lg);overflow:hidden",
        onclick="event.stopPropagation()",
    )
    return Div(
        dialog,
        style="position:fixed;inset:0;z-index:80;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(5,6,8,.62);backdrop-filter:blur(4px)",
        onclick=_CLOSE_MODAL,
    )


# ── scenario upload ───────────────────────────────────────────────────────────
_UPLOAD_MAX_BYTES = 25 * 1024 * 1024
_UPLOAD_SUFFIXES = {".json", ".wkt"}


def _slugify(raw: str) -> str:
    """Filesystem-safe directory name. Never trust a client-supplied path."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (raw or "").strip()).strip("-._")
    return cleaned[:64] or "scenario"


def _unique_dir(root: Path, slug: str) -> Path:
    candidate = root / slug
    n = 2
    while candidate.exists():
        candidate = root / f"{slug}-{n}"
        n += 1
    return candidate


def _extract_zip(blob: bytes, dest: Path) -> list[str]:
    """Extract the .json/.wkt members of a zip flat into *dest*.

    zipfile does not sanitise member names, so an archive can carry '../' or an
    absolute path and write outside the target ("zip slip"). Such members are
    rejected outright; ordinary nested ones ("t_junction/config.json", the
    shape you get zipping a scenario folder) keep just their basename.
    """
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            raw = info.filename.replace("\\", "/")
            parts = [p for p in raw.split("/") if p not in ("", ".")]
            # Drop traversal and absolute members outright rather than
            # flattening them to a basename: a '../' entry is malformed at
            # best, and flattening would quietly add a stray .json that the
            # picker would then offer as an alternate config.
            if not parts or ".." in parts or raw.startswith("/") or ":" in parts[0]:
                continue
            # A zip of a folder ("t_junction/config.json") is the normal case,
            # so a nested member keeps its basename.
            name = parts[-1]
            if Path(name).suffix.lower() not in _UPLOAD_SUFFIXES:
                continue
            target = (dest / name).resolve()
            if dest.resolve() not in target.parents:  # defence in depth
                continue
            if info.file_size > _UPLOAD_MAX_BYTES:
                raise ValueError(f"{name} is too large.")
            target.write_bytes(zf.read(info))
            written.append(name)
    return written


def _upload_error(message: str, selected: str | None = None):
    return params.scenario_block(
        selected,
        note=Div(
            message,
            style=(
                f"{_MONO};font-size:10.5px;color:#E01E37;margin-top:6px;line-height:1.5"
            ),
        ),
    )


@rt("/upload-scenario")
async def upload_scenario(request: Request):
    form = await request.form()
    current = str(form.get("scenario") or "") or None
    uploads = [f for f in form.getlist("files") if getattr(f, "filename", "")]
    if not uploads:
        return _upload_error(
            "Pick a config JSON + geometry WKT, or a .zip bundle.", current
        )

    blobs: list[tuple[str, bytes]] = []
    total = 0
    for item in uploads:
        data = await item.read()
        total += len(data)
        if total > _UPLOAD_MAX_BYTES:
            return _upload_error("Upload is over the 25 MB limit.", current)
        blobs.append((Path(item.filename).name, data))

    allowed = _UPLOAD_SUFFIXES | {".zip"}
    accepted = [(n, d) for n, d in blobs if Path(n).suffix.lower() in allowed]
    ignored = [n for n, _ in blobs if Path(n).suffix.lower() not in allowed]
    if not accepted:
        return _upload_error(
            "Nothing usable here. Expected .json / .wkt files, or a .zip bundle.",
            current,
        )

    name_field = str(form.get("upload_name") or "").strip()
    fallback = next(
        (Path(n).stem for n, _ in accepted if Path(n).suffix.lower() != ".wkt"),
        Path(accepted[0][0]).stem,
    )
    params._UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    dest = _unique_dir(params._UPLOAD_ROOT, _slugify(name_field or fallback))
    dest.mkdir(parents=True)

    try:
        written: list[str] = []
        for filename, data in accepted:
            if Path(filename).suffix.lower() == ".zip":
                written += _extract_zip(data, dest)
            else:
                (dest / Path(filename).name).write_bytes(data)
                written.append(Path(filename).name)
        if not written:
            raise ValueError("The archive held no .json or .wkt files.")
        # The one real check: if load_scenario accepts it, the run will too.
        # Cheaper and more honest than re-implementing format validation.
        load_scenario(str(dest))
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        return _upload_error(
            f"Could not load that scenario. {type(exc).__name__}: {exc}", current
        )

    value = f"{params.UPLOAD_PREFIX}{dest.name}"
    summary = f"Added “{dest.name}” · {', '.join(sorted(written))}"
    if ignored:
        summary += f" · ignored {', '.join(sorted(ignored))}"
    return params.scenario_block(
        value,
        note=Div(
            summary,
            style=f"{_MONO};font-size:10.5px;color:#F4C430;margin-top:6px;line-height:1.5",
        ),
    )


# ── run routes ────────────────────────────────────────────────────────────────
@rt("/run")
async def post(request: Request):
    form = dict(await request.form())
    scenario_name = form.get("scenario")
    if not scenario_name:
        return Div(
            "Select a scenario first.",
            style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px",
        )

    # Guard against launching a second run over a live one. Rather than
    # crashing the active run (manager.start would raise), reconnect the
    # caller to the run already in progress so the panel stays intact.
    if manager.running:
        return _running_stream_view()

    try:
        scenario = load_scenario(str(params.scenario_path(scenario_name)))
        opts = params.form_to_opts(form)
        # Normalise the FDS dir and fail fast on a bogus value. Without this,
        # a stale/garbage field (e.g. a pasted error string) is handed to
        # fdsreader as a path and produces a confusing nested-exception cascade.
        fds_dir = (getattr(opts, "fds_dir", None) or "").strip()
        opts.fds_dir = fds_dir or None
        if fds_dir and not Path(fds_dir).is_dir():
            shown = fds_dir if len(fds_dir) <= 80 else fds_dir[:80] + "…"
            return Div(
                f"FDS dir is not a folder: {shown}",
                style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px",
            )
        # Cheap option-combination checks stay on the request thread. Only the
        # expensive half of build_run_kwargs (FDS slice parsing) is deferred to
        # the worker, so a plain misconfiguration still answers the request
        # instead of surfacing later as a failed run.
        validate_opts(opts)
        import run as cli

        def post_run(result):
            return cli.apply_outputs(result, scenario, opts, log=lambda _m: None)

        manager.start(
            scenario,
            lambda: build_run_kwargs(scenario, opts, log=print),
            scenario_name,
            post_run=post_run,
            fds_dir=getattr(opts, "fds_dir", None),
            results_only=bool(form.get("results_only")),
            opts=opts,
        )
    except Exception as exc:
        return Div(
            f"{type(exc).__name__}: {exc}",
            style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px",
        )

    return _running_stream_view()


@rt("/cancel")
async def cancel():
    """Stop an in-flight run and hand the panel back in its standby state.

    Cancellation is cooperative (the worker unwinds on its next progress
    tick), so wait briefly for the run to actually let go before resetting.
    Without that wait the manager can still report ``running`` when the user
    immediately clicks Run again, and ``/run``'s guard would reconnect them
    to the run they just stopped. The wait is bounded so a scenario with slow
    ticks can't hang the request.
    """
    manager.cancel()
    deadline = time.monotonic() + 2.0
    while manager.running and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    manager.reset()
    return _run_panel_idle_body()


@rt("/clear")
async def clear():
    """Discard a finished run's results and return to the standby panel."""
    manager.reset()
    return _run_panel_idle_body()


def _running_stream_view() -> Div:
    """The live run panel: progress card + console, wired to the SSE stream."""
    return Div(
        Div(
            # Only the dynamic half lives in the SSE swap target. Cancel sits
            # outside it: #run-status is re-rendered on every progress tick,
            # and a stop control that is destroyed and rebuilt ~once a second
            # can swallow a click that lands mid-swap.
            Div(_running_card(None), id="run-status", sse_swap="progress,done"),
            Div(
                Button(
                    NotStr(
                        '<span style="font-size:9px">■</span>'
                        '<span class="run-btn-label">Cancel scenario</span>'
                    ),
                    id="cancel-btn",
                    type="button",
                    hx_post="/cancel",
                    hx_target="#run-panel",
                    hx_swap="innerHTML show:top",
                    style=(
                        "display:inline-flex;align-items:center;gap:7px;"
                        "padding:9px 16px;border-radius:10px;cursor:pointer;"
                        f"{_GROTESK};font-size:13px;font-weight:600;"
                        "background:transparent;color:#E01E37;"
                        "border:1px solid #E01E37"
                    ),
                ),
                style="display:flex;justify-content:flex-end;margin-top:18px",
            ),
            style=_PANEL,
        ),
        Div(
            Div(
                Div(
                    NotStr(
                        '<span style="display:flex;gap:6px">'
                        '<span style="width:10px;height:10px;border-radius:99px;background:#E01E37"></span>'
                        '<span style="width:10px;height:10px;border-radius:99px;background:#F4C430"></span>'
                        '<span style="width:10px;height:10px;border-radius:99px;background:#FF6A1A"></span>'
                        "</span>"
                    ),
                    Span(
                        "console",
                        style=f"{_MONO};font-size:11px;{_MUTED};margin-left:6px",
                    ),
                    style="display:flex;align-items:center;gap:9px;padding:14px 20px;border-bottom:1px solid var(--hairline)",
                ),
                Pre(
                    "Waiting for output…",
                    id="console-log",
                    cls="console-box",
                    sse_swap="console",
                    **{"hx-on:htmx:after-swap": "this.scrollTop = this.scrollHeight"},
                ),
            ),
            style=_PANEL + ";margin-top:18px",
        ),
        hx_ext="sse",
        sse_connect="/progress",
        sse_close="done",
    )


def _console_view() -> Pre:
    text = "\n".join(manager.log_lines[-300:]) or "Waiting for output…"
    return Pre(text)


def _running_card(ev) -> Div:
    line = (
        f"evacuated {ev.evacuated}/{ev.total} · sim {ev.sim_time:.1f}s · "
        f"wall {ev.wall_time:.0f}s · {ev.pct}%"
        if ev
        else "Initialising…"
    )
    pct = ev.pct if ev else 0
    return Div(
        Div(
            Div(
                Span(
                    style="width:9px;height:9px;border-radius:99px;background:#FF7A45;animation:pulse 1.6s infinite;display:block"
                ),
                Div(
                    Div(
                        f"Running: {manager.scenario_name}",
                        style=f"{_GROTESK};font-weight:600;font-size:17px;{_INK}",
                    ),
                    Div(
                        "coupled FDS × JuPedSim step loop",
                        style=f"{_MONO};font-size:11px;{_MUTED};margin-top:2px",
                    ),
                ),
                style="display:flex;align-items:center;gap:12px",
            ),
            Div(
                f"{pct}%",
                style=f"{_GROTESK};font-weight:700;font-size:30px;letter-spacing:-.02em;color:#F4C430",
            ),
            style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px",
        ),
        Div(
            Div(
                style=f"height:100%;width:{max(pct, 3)}%;border-radius:99px;background:linear-gradient(90deg,#F4C430,#FFB020,#FF6A1A);transition:width .35s cubic-bezier(.4,0,.2,1)"
            ),
            style="height:10px;border-radius:99px;background:var(--surface-page);border:1px solid var(--hairline);overflow:hidden;margin-bottom:18px",
        ),
        Div(line, style=f"{_MONO};font-size:.82rem;{_INK2}"),
    )


def _clear_run_bar() -> Div:
    """Header strip over a finished run, with the way back to standby.

    Without this a completed run is a dead end: the panel keeps showing the
    old results and there is no way to dismiss them short of reloading.
    """
    return Div(
        Div(
            f"Results · {manager.scenario_name or 'run'}",
            style=f"{_MONO};font-size:11px;letter-spacing:.06em;text-transform:uppercase;{_MUTED}",
        ),
        Button(
            "Clear results",
            type="button",
            hx_post="/clear",
            hx_target="#run-panel",
            hx_swap="innerHTML show:top",
            style=(
                "padding:7px 13px;border-radius:9px;cursor:pointer;"
                f"{_MONO};font-size:11px;"
                "background:transparent;color:var(--ink-dim);"
                "border:1px solid var(--hairline)"
            ),
        ),
        style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px",
    )


def _kpi_tiles(result) -> Div:
    """The four headline numbers, shared by both finished views."""
    status = "finished" if result.agents_remaining == 0 else "stopped"
    metrics = [
        ("Status", f"{status} ({result.metrics.get('success')})"),
        ("Evacuation time", f"{result.evacuation_time:.1f} s"),
        ("Evacuated", f"{result.agents_evacuated}/{result.total_agents}"),
        ("Remaining", f"{result.agents_remaining}"),
    ]
    accents = ["#F4C430", "#F4C430", "#3B82F6", "#E01E37"]
    return Div(
        *[
            Div(
                Div(
                    k,
                    style=f"{_MONO};font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;{_MUTED}",
                ),
                Div(
                    v,
                    style=f"{_MONO};font-size:19px;font-weight:500;margin-top:7px;{_INK}",
                ),
                style=f"background:var(--surface-panel);border:1px solid var(--hairline);border-top:2px solid {a};border-radius:14px;padding:15px 16px",
            )
            for (k, v), a in zip(metrics, accents)
        ],
        style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px",
    )


def _finished_view() -> Div:
    result = manager.result
    scenario = None
    try:
        scenario = load_scenario(str(params.scenario_path(manager.scenario_name)))
    except Exception:
        pass

    kpi_tiles = _kpi_tiles(result)
    if manager.artifacts:
        art = Div(
            Div(
                "Artifacts written",
                style=f"{_MONO};font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;{_MUTED};margin-bottom:4px",
            ),
            *[Div(a, cls="artifact") for a in manager.artifacts],
            style="margin-top:12px",
        )
    else:
        art = Div()

    def plot_card(title, fig, div_id):
        return Div(
            Div(
                title,
                style=f"{_GROTESK};font-weight:600;font-size:15px;{_INK};margin-bottom:10px",
            ),
            plots.figure_html(fig, div_id),
            style=_CARD,
        )

    return Div(
        _clear_run_bar(),
        kpi_tiles,
        _warnings_card(manager.warnings),
        art,
        trajviz.trajectory_component(result, scenario, fds_dir=manager.fds_dir),
        plot_card("Smoke", plots.smoke_figure(result), "fig-smoke"),
        plot_card(
            "Cognitive map growth", plots.cognitive_map_figure(result), "fig-cogmap"
        ),
        cls="space-y-6",
        style="display:flex;flex-direction:column;gap:18px",
    )


def _fmt_size(path: Path) -> str:
    """Human byte count for a file, or the summed contents of a directory."""
    try:
        if path.is_dir():
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        else:
            total = path.stat().st_size
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return f"{total:.0f} {unit}" if unit == "B" else f"{total:.1f} {unit}"
        total /= 1024.0
    return "?"


# Every artifact apply_outputs can write: the opts attribute holding its path,
# a label, and the RunResult field it is gated on (None = always written).
_ARTIFACT_SPECS = [
    ("output_sqlite", "Trajectory SQLite", "sqlite_file"),
    ("output_smoke_history", "Smoke history CSV", "smoke_history"),
    ("output_fed_history", "FED history CSV", "fed_history"),
    ("output_route_history", "Route switch CSV", "route_history"),
    ("output_route_cost_history", "Route cost CSV", "route_cost_history"),
    ("export_app_bundle", "Scenario bundle", None),
]


def _missing_reason(field: str, opts) -> str:
    """Why a writer produced nothing -- these are settings, not failures."""
    if field in ("smoke_history", "fed_history"):
        no_smoke = not getattr(opts, "fds_dir", None) and not getattr(
            opts, "constant_extinction", None
        )
        if no_smoke:
            return "no smoke source: set an FDS dir or a constant extinction"
        if field == "fed_history" and getattr(opts, "disable_tenability", False):
            return "tenability disabled for this run"
        return "the model recorded no samples"
    if field in ("route_history", "route_cost_history"):
        if not getattr(opts, "enable_rerouting", False):
            return "rerouting disabled for this run"
        return "no agent ever switched route"
    if field == "sqlite_file":
        return "no trajectory file was produced"
    return "not produced by this run"


def _artifact_rows(result, opts) -> Div:
    rows = []
    for attr, label, field in _ARTIFACT_SPECS:
        raw = getattr(opts, attr, None) if opts is not None else None
        produced = field is None or getattr(result, field, None) is not None
        path = Path(raw) if raw else None
        exists = bool(path and path.exists())

        if exists:
            detail, colour, mark = f"{path} · {_fmt_size(path)}", "var(--ink-dim)", "#F4C430"
        elif not produced:
            detail, colour, mark = _missing_reason(field, opts), "var(--ink-faint)", "var(--surface-raised)"
        else:
            detail, colour, mark = "not written", "var(--ink-faint)", "var(--surface-raised)"

        rows.append(
            Div(
                Div(
                    style=f"width:6px;height:6px;border-radius:99px;background:{mark};flex:none;margin-top:6px"
                ),
                Div(
                    Div(label, style=f"{_GROTESK};font-size:12.5px;{_INK}"),
                    Div(
                        detail,
                        style=f"{_MONO};font-size:10.5px;color:{colour};margin-top:3px;word-break:break-all",
                    ),
                ),
                style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--hairline-soft)",
            )
        )
    return Div(*rows, style="display:flex;flex-direction:column")


def _results_only_view() -> Div:
    """Finished panel for a results-only run: numbers and files, no viewer."""
    result = manager.result
    opts = manager.opts
    return Div(
        _clear_run_bar(),
        _kpi_tiles(result),
        _warnings_card(manager.warnings),
        Div(
            Div(
                "Output files",
                style=f"{_GROTESK};font-weight:600;font-size:15px;{_INK};margin-bottom:4px",
            ),
            Div(
                "Same artifacts as a uv run of run.py.",
                style=f"{_MONO};font-size:10.5px;{_MUTED};margin-bottom:10px",
            ),
            _artifact_rows(result, opts),
            style=_CARD,
        ),
        Div(
            Div(
                "Viewer skipped",
                style=f"{_GROTESK};font-weight:600;font-size:14px;color:#F4C430;margin-bottom:6px",
            ),
            P(
                "The trajectory animation and the FED / smoke / cognitive-map plots "
                "were not built for this run. Run the same scenario with "
                "“Run scenario” to see them.",
                style=f"font-size:.82rem;line-height:1.6;{_INK2};margin:0",
            ),
            style=_CARD,
        ),
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
                payload = json.dumps(
                    {
                        "t": [s[0] for s in snaps],
                        "max": [s[1] for s in snaps],
                        "mean": [s[2] for s in snaps],
                    }
                )
                yield sse_message(payload, event="fed")
            if manager.status in ("done", "error", "idle", "cancelled"):
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
                    finished = (
                        _results_only_view()
                        if manager.results_only
                        else _finished_view()
                    )
                except Exception as exc:
                    import traceback

                    err = traceback.format_exc()
                    finished = Div(
                        Div(
                            f"Results error: {type(exc).__name__}: {exc}",
                            style="color:#E01E37;font-family:'JetBrains Mono',monospace;font-size:.8rem;margin-bottom:8px",
                        ),
                        Pre(
                            err,
                            style="color:var(--ink-dim);font-family:'JetBrains Mono',monospace;font-size:.72rem;white-space:pre-wrap;overflow:auto;max-height:300px",
                        ),
                        style="background:var(--surface-panel);border:1px solid #E01E37;border-radius:12px;padding:16px",
                    )
                yield sse_message(finished, event="done")
                return
            if status == "error":
                yield sse_message(
                    Div(
                        f"Run failed: {manager.error}",
                        style="color:#E01E37;padding:12px;border:1px solid #E01E37;border-radius:9px",
                    ),
                    event="done",
                )
                return
            # Cancelled and idle both just close the stream: /cancel has
            # already swapped the whole panel back to its standby state, so
            # emitting anything here would fight that swap.
            if status in ("cancelled", "idle"):
                return
            ev = manager.last_event
            if ev is not None and ev != last:
                last = ev
                yield sse_message(_running_card(ev), event="progress")
            await asyncio.sleep(0.1)

    return EventStream(gen())


if __name__ == "__main__":
    serve()
