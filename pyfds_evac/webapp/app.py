"""FastHTML web GUI for pyFDS-Evac — no MonsterUI/UIKit dependency.

All visual components use plain FastHTML primitives with inline styles that
match the redesigned "Instrument" prototype exactly. All route logic, SSE
streaming and JS helpers are unchanged from the original.
"""

from __future__ import annotations

import asyncio
import atexit
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

from fasthtml.common import (
    H2,
    A,
    B,
    Button,
    Code,
    Details,
    Div,
    EventStream,
    HtmxResponseHeaders,
    Link,
    NotStr,
    P,
    Pre,
    Script,
    Span,
    Style,
    Summary,
    Title,
    fast_app,
    serve,
    sse_message,
)
from starlette.requests import Request

from pyfds_evac.core import load_scenario
from pyfds_evac.core.run_config import build_run_kwargs, validate_opts

from . import docs, params, plots, pyexport, theme, trajviz
from .runner import (
    RunManager,
    code_provenance,
    make_run_spec,
    run_outcome,
    run_stamp,
    utc_now,
)

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
# The last run's temporary trajectory would otherwise outlive the server.
atexit.register(manager.reset)
# How long /cancel waits for the worker to end before answering.
_CANCEL_WAIT_S = 2.0

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
  var fedRun = (document.getElementById('fed-live-section') || {dataset: {}}).dataset.run;
  var fedEs = new EventSource('/fed-progress?run=' + encodeURIComponent(fedRun || ''));
  fedEs.addEventListener('fed', function (e) {
    try {
      var d = JSON.parse(e.data);
      if (!d.t || !d.t.length) return;
      var section = document.getElementById('fed-live-section');
      if (section) section.style.display = '';
      var traces = [
        {x: d.t, y: d.max, mode: 'lines', name: 'max FED (any agent)', line: {color: '#F4C430', width: 2}}
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
        data_run=manager.run_id,
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
                Button(
                    "Show equivalent Python",
                    type="button",
                    id="pyexport-preview-btn",
                    hx_post="/export/preview",
                    hx_include="#run-form",
                    hx_params="not files,upload_name",
                    hx_target="#pyexport",
                    hx_swap="innerHTML",
                    data_pyexport_open="1",
                    cls="pyexport-btn",
                ),
                style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px",
            ),
            params.build_form("/run"),
            cls="sidebar-panel",
            style=f"{_PANEL};display:flex;flex-direction:column;gap:14px",
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
            Span("\u26a0", aria_hidden="true", cls="state-glyph"),
            Span("Warning", cls="state-word"),
            Span(f"{heading} for run #{_run_number()}", cls="state-run"),
            cls="state-line",
            style="margin-bottom:10px;color:var(--gold-ink)",
        ),
        *[
            P(
                message,
                style=f"font-size:.82rem;line-height:1.6;{_INK2};margin:0 0 8px",
            )
            for message in messages
        ],
        P(
            "These affect what the results describe. See ",
            A(
                "FDS case requirements",
                href="https://pedestriandynamics.org/pyFDS-Evac/docs/fds-case-requirements/",
                target="_blank",
                rel="noopener",
            ),
            " and the Model tab.",
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


def _run_column() -> Div:
    """Right-hand column: form alerts, settings-changed banner, run panel.

    ``#form-status`` takes a rejected submit's error, so a validation error
    never replaces the run panel and the results in it. ``#settings-changed``
    is refreshed from the server whenever the form changes (``/form-state``).
    The panel shows whatever the server holds, so a reload or a second tab
    finds a live run, or its results, instead of the standby screen.
    """
    return Div(
        Div(id="form-status", role="alert"),
        Div(id="settings-changed", role="status"),
        Div(
            hx_post="/form-state",
            hx_include="#run-form",
            hx_params="not files,upload_name",
            hx_trigger=(
                "load, refresh, input from:#run-form delay:500ms, "
                "change from:#run-form delay:200ms"
            ),
            hx_target="#settings-changed",
            hx_swap="innerHTML",
            id="form-state",
            hidden=True,
        ),
        Div(
            _current_panel_body(),
            id="run-panel",
            cls="rise",
            style="animation-delay:.12s",
        ),
        cls="run-col",
        style="display:flex;flex-direction:column;gap:14px;min-width:0",
    )


# Preview of the output folder and file names for the selected scenario. The
# paths a run writes are derived on the server (params.form_to_opts); this only
# shows them.
_AUTOFILL_JS = """
(function () {
  function scenarioName() {
    // The picker is a <select id="scenario">, not a wrapper around one, so
    // match on the form name -- that holds however it ends up being rendered.
    var el = document.querySelector('[name="scenario"]');
    return (el && el.value) || '';
  }
  function seedValue() {
    var el = document.getElementById('seed');
    return (el && el.value.trim()) || '';
  }
  function modeValue() {
    var el = document.querySelector('[name="incapacitation_mode"]');
    return (el && el.value) || 'deterministic';
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
    // Show the derived folder as a placeholder rather than a value, so an empty
    // box still tells you where output lands while a typed path clearly wins.
    // The server adds the start time; a blank seed is the scenario's own.
    var ob = document.getElementById('output_base');
    var root = (ob && ob.dataset.resultsRoot) || 'results';
    var derived = base ? root + '/' + base + '/' + modeValue() + '/seed' +
      (seedValue() || '<scenario seed>') + '/<start time>' : '';
    if (ob) ob.placeholder = derived || root + '/<scenario>';
    // Preview lines under the folder box, so the section shows the real
    // filenames instead of a literal "<run>".
    document.querySelectorAll('.artifact-preview').forEach(function (el) {
      el.textContent = (base || '<run>') + el.dataset.suffix;
    });
  }
  var last = null;
  setInterval(function () {
    var k = scenarioName() + '|' + seedValue() + '|' + modeValue() + '|' + outputBase();
    if (k !== last) { last = k; fill(scenarioName()); }
  }, 250);
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
    '<div class="tab-nav"><div class="tab-pills" role="tablist" aria-label="Views">'
    '<button class="tab-btn active" data-tab="sim" type="button" role="tab" '
    'id="tab-btn-sim" aria-selected="true" aria-controls="tab-sim">Simulation</button>'
    '<button class="tab-btn" data-tab="model" type="button" role="tab" '
    'id="tab-btn-model" aria-selected="false" aria-controls="tab-model">Model</button>'
    "</div></div>"
)

_TAB_JS = """
document.addEventListener('click', function (e) {
  var b = e.target.closest && e.target.closest('.tab-btn');
  if (!b) return;
  var t = b.dataset.tab;
  document.querySelectorAll('.tab-btn').forEach(function (x) {
    x.classList.toggle('active', x === b);
    x.setAttribute('aria-selected', String(x === b));
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

# Reflect run state on the submit buttons. The lock follows the panel: Run and
# "Results only" stay disabled while the panel holds a live or cancelling run
# (marked data-run-live), so a reload, a cancel still unwinding, or a stream
# torn down by a swap cannot unlock them over a live worker.
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
      if (lbl) lbl.textContent = on ? 'Run in progress…' : LABELS[id].idle;
      if (ico) ico.textContent = on ? '⏳' : LABELS[id].icon;
    });
  }
  function live() { return !!document.querySelector('#run-panel [data-run-live]'); }
  function sync() {
    setRunning(live());
    // A run that has just settled may differ from the form edited meanwhile.
    if (document.querySelector('#run-panel [data-run-done]') && window.htmx) {
      htmx.trigger('#form-state', 'refresh');
    }
  }
  function path(d) {
    return (d && d.pathInfo && (d.pathInfo.requestPath || d.pathInfo.path)) ||
           (d && d.requestConfig && d.requestConfig.path) || '';
  }
  document.body.addEventListener('htmx:beforeRequest', function (e) {
    var p = path(e.detail);
    if (p === '/run') setRunning(true);
    if (p === '/cancel') {
      var c = document.getElementById('cancel-btn');
      if (c) {
        c.disabled = true;
        var cl = c.querySelector('.run-btn-label');
        if (cl) cl.textContent = 'Cancelling…';
      }
    }
  });
  ['htmx:afterSettle', 'htmx:afterRequest', 'htmx:responseError',
   'htmx:sseMessage', 'htmx:sseClose'].forEach(function (ev) {
    document.body.addEventListener(ev, function () { setTimeout(sync, 0); });
  });
  sync();
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
  var input = document.getElementById('incapacitation_mode');
  var was = input.value;
  input.value = mode;
  // A script-set value fires no event; the settings-changed check needs one.
  if (was !== mode) input.dispatchEvent(new Event('change', {bubbles: true}));
  [['btn-prob', 'probabilistic'], ['btn-det', 'deterministic']].forEach(function (p) {
    var b = document.getElementById(p[0]);
    b.classList.toggle('active', mode === p[1]);
    b.setAttribute('aria-pressed', String(mode === p[1]));
  });
  var row  = document.getElementById('sigma-row');
  var dist = document.getElementById('incap-dist');
  if (row)  row.style.display  = mode === 'deterministic' ? 'none' : '';
  if (dist) dist.style.display = mode === 'deterministic' ? 'none' : '';
  if (mode === 'probabilistic') drawIncapDist();
}

document.addEventListener('input', function (e) {
  if (e.target && e.target.id === 'susceptibility_sigma') drawIncapDist();
});
document.addEventListener('DOMContentLoaded', function () {
  var el = document.getElementById('incapacitation_mode');
  if (el) setTenabilityMode(el.value || 'deterministic');
});
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


# Keyboard behaviour shared by the form: the ? help buttons (toggle, and
# Escape to close) and the folder browser, which takes focus on open, keeps
# Tab inside, closes on Escape and returns focus to the button that opened it.
_A11Y_JS = """
(function () {
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.help-badge');
    if (!b) return;
    var w = b.closest('.lblwrap');
    if (!w) return;
    b.setAttribute('aria-expanded', String(w.classList.toggle('open')));
  });
  var opener = null;
  function modal() { return document.getElementById('dir-modal'); }
  function dialog() { var m = modal(); return m && m.querySelector('[role=dialog]'); }
  window.closeDirModal = function () {
    var m = modal(); if (m) m.innerHTML = '';
    if (opener && document.body.contains(opener)) opener.focus();
    opener = null;
  };
  document.body.addEventListener('htmx:beforeRequest', function (e) {
    var elt = e.detail && e.detail.elt;
    var m = modal();
    if (elt && m && elt.getAttribute('hx-target') === '#dir-modal' && !m.contains(elt)) {
      opener = elt;
    }
  });
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail.target !== modal()) return;
    var d = dialog(); if (!d) return;
    var first = d.querySelector('button');
    if (first) first.focus();
  });
  document.addEventListener('keydown', function (e) {
    var d = dialog();
    if (d) {
      if (e.key === 'Escape') { e.preventDefault(); window.closeDirModal(); return; }
      if (e.key === 'Tab') {
        var f = d.querySelectorAll('button, [href], input, select, [tabindex]:not([tabindex="-1"])');
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (!d.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
        else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      return;
    }
    if (e.key !== 'Escape') return;
    var a = document.activeElement;
    var w = a && a.closest && a.closest('.lblwrap.open');
    if (!w) return;
    w.classList.remove('open');
    var hb = w.querySelector('.help-badge');
    if (hb) { hb.setAttribute('aria-expanded', 'false'); hb.focus(); }
  });
})();
"""


@rt("/")
def index():
    grid = Div(
        _sidebar(),
        _run_column(),
        cls="sim-grid",
    )
    return (
        Title("pyFDS-Evac · control"),
        _header(),
        _NAV,
        Div(
            Div(grid, id="tab-sim", role="tabpanel", aria_labelledby="tab-btn-sim"),
            Div(
                docs.model_docs(),
                id="tab-model",
                cls="hidden",
                role="tabpanel",
                aria_labelledby="tab-btn-model",
            ),
        ),
        theme.switch(),
        Div(id="dir-modal"),
        NotStr(
            '<dialog id="pyexport" class="pyexport" aria-labelledby="pyexport-title">'
            "</dialog>"
        ),
        Style(_PYEXPORT_CSS),
        Script(_PYEXPORT_JS),
        theme.script(),
        Script(_AUTOFILL_JS),
        Script(_TAB_JS),
        Script(_MATH_JS),
        Script(_TENABILITY_JS),
        Script(_RUN_BTN_JS),
        Script(_UPLOAD_JS),
        Script(_A11Y_JS),
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


_CLOSE_MODAL = "window.closeDirModal()"
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
            Div(
                title_text,
                id="dir-title",
                style=f"{_GROTESK};font-weight:600;font-size:16px;{_INK}",
            ),
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
        style="width:520px;max-width:100%;background:var(--surface-panel);border:1px solid var(--hairline-strong);border-radius:18px;box-shadow:var(--shadow-lg);overflow:hidden",
        onclick="event.stopPropagation()",
        role="dialog",
        aria_modal="true",
        aria_labelledby="dir-title",
    )
    return Div(
        dialog,
        style="position:fixed;inset:0;z-index:80;display:flex;align-items:center;justify-content:center;padding:16px;background:rgba(5,6,8,.62);backdrop-filter:blur(4px)",
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
            style=f"{_MONO};font-size:10.5px;color:var(--gold-ink);margin-top:6px;line-height:1.5",
        ),
    )


# ── run routes ────────────────────────────────────────────────────────────────
class _FdsDirError(ValueError):
    """The FDS dir field does not name a folder."""


def _resolve_form(form: dict, stamp: str | None = None):
    """Resolve a submitted form into ``(scenario, opts)`` for build_run_kwargs.

    The one path from form to configuration: /run submits what this returns,
    and the Python export renders the same ``opts``. Raises on anything the
    API would reject, using the API's own checks.
    """
    scenario = load_scenario(str(params.scenario_path(form.get("scenario"))))
    opts = params.form_to_opts(form, baseseed=scenario.seed, stamp=stamp)
    # Normalise the FDS dir and fail fast on a bogus value. Without this,
    # a stale/garbage field (e.g. a pasted error string) is handed to
    # fdsreader as a path and produces a confusing nested-exception cascade.
    fds_dir = (getattr(opts, "fds_dir", None) or "").strip()
    opts.fds_dir = fds_dir or None
    if fds_dir and not Path(fds_dir).is_dir():
        shown = fds_dir if len(fds_dir) <= 80 else fds_dir[:80] + "…"
        raise _FdsDirError(f"FDS dir is not a folder: {shown}")
    # Cheap option-combination checks stay on the request thread. Only the
    # expensive half of build_run_kwargs (FDS slice parsing) is deferred to
    # the worker, so a plain misconfiguration still answers the request
    # instead of surfacing later as a failed run.
    validate_opts(opts)
    return scenario, opts


def _field_label(message: str) -> str:
    """Name the form field in an API message that starts with its dest."""
    dest, sep, rest = message.partition(": ")
    if sep and re.fullmatch(r"[a-z][a-z0-9_]*", dest):
        return f"{dest.replace('_', ' ').capitalize()}: {rest}"
    return message


def _form_error(exc: Exception | str):
    """A rejected submit, for the alert above the run panel.

    It goes to ``#form-status`` and leaves ``#run-panel`` untouched, so the
    results shown there survive; the form keeps the values that were entered.
    The API's message is the main line; the exception type sits apart.
    """
    if isinstance(exc, str):
        main, details = exc, None
    else:
        main = _field_label(str(exc)) or type(exc).__name__
        details = f"{type(exc).__name__}: {exc}"
    body = Div(
        Div(
            Span("\u26a0", aria_hidden="true", cls="state-glyph"),
            B("The run was not started. "),
            Span(main),
            cls="form-error-main",
        ),
        P(
            "Your settings are kept; correct them and run again. "
            "Results already shown are unchanged.",
            cls="form-error-hint",
        ),
        *(
            [Details(Summary("Technical details"), Pre(details, cls="tech-pre"))]
            if details
            else []
        ),
        cls="form-error",
    )
    return body, HtmxResponseHeaders(retarget="#form-status", reswap="innerHTML")


def _clear_alerts():
    """Out-of-band blanks for the form alert and the settings banner."""
    return (
        Div(id="form-status", role="alert", hx_swap_oob="true"),
        Div(id="settings-changed", role="status", hx_swap_oob="true"),
    )


@rt("/run")
async def post(request: Request):
    form = dict(await request.form())
    scenario_name = form.get("scenario")
    if not scenario_name:
        return _form_error("Select a scenario first.")

    # Guard against launching a second run over a live one. Rather than
    # crashing the active run (manager.start would raise), reconnect the
    # caller to the run already in progress so the panel stays intact.
    if manager.running:
        return _running_stream_view(cancelling=manager.status == "cancelling")

    # One start time names the output folder and the snapshot, so the two
    # agree and the exported script can be named after it.
    started_at = utc_now()
    try:
        scenario, opts = _resolve_form(form, stamp=run_stamp(started_at))
    except Exception as exc:
        return _form_error(exc)

    try:
        spec = make_run_spec(
            opts,
            scenario,
            scenario_name,
            str(params.scenario_path(scenario_name)),
            started_at=started_at,
        )
        import run as cli

        # The run is built from the snapshot, not from the handler's Namespace,
        # so what runs is exactly what the snapshot (and its export) records.
        run_opts = spec.namespace()

        def post_run(result):
            return cli.apply_outputs(result, scenario, run_opts, log=lambda _m: None)

        manager.start(
            scenario,
            lambda: build_run_kwargs(scenario, run_opts, log=print),
            scenario_name,
            post_run=post_run,
            fds_dir=run_opts.fds_dir,
            results_only=bool(form.get("results_only")),
            opts=spec.namespace(),
            spec=spec,
        )
    except Exception as exc:
        return _form_error(exc)

    return _running_stream_view(), *_clear_alerts()


# ── equivalent Python ─────────────────────────────────────────────────────────
_PYEXPORT_CSS = """
.pyexport-btn, .pyexport-act, .pyexport-close {
  padding:6px 11px;border-radius:8px;cursor:pointer;
  font-family:'JetBrains Mono',monospace;font-size:11px;
  background:transparent;color:var(--ink-dim);border:1px solid var(--hairline);
}
.pyexport-btn:focus-visible, .pyexport-act:focus-visible, .pyexport-close:focus-visible,
.pyexport-code:focus-visible, .pyexport summary:focus-visible {
  outline:2px solid var(--focus);outline-offset:2px;
}
.pyexport-act:disabled { opacity:.5;cursor:not-allowed; }
dialog.pyexport {
  width:min(920px, calc(100vw - 32px));max-width:none;max-height:90vh;
  box-sizing:border-box;padding:18px;overflow:auto;
  background:var(--surface-panel);color:var(--ink);
  border:1px solid var(--hairline-strong);border-radius:14px;
}
dialog.pyexport::backdrop { background:rgba(0,0,0,.55); }
.pyexport-head { display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:10px; }
.pyexport-head h2 {
  flex:1 1 220px;margin:0;font-family:'Space Grotesk',sans-serif;
  font-size:15px;font-weight:600;overflow-wrap:anywhere;
}
.pyexport-badge {
  font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  padding:3px 7px;border:1px solid var(--hairline-strong);border-radius:6px;
}
.pyexport-notes { font-size:12px;color:var(--ink-dim);line-height:1.45;overflow-wrap:anywhere; }
.pyexport-notes p { margin:4px 0; }
.pyexport-status { font-family:'JetBrains Mono',monospace;font-size:12px;margin:0 0 8px; }
.pyexport-code {
  margin:12px 0;padding:12px;white-space:pre;overflow-x:auto;max-height:55vh;
  font-family:'JetBrains Mono',monospace;font-size:11.5px;line-height:1.5;
  background:var(--surface-input);border:1px solid var(--hairline);border-radius:10px;
}
.pyexport-actions { display:flex;flex-wrap:wrap;align-items:center;gap:8px; }
.pyexport-error { color:#E01E37;font-size:13px; }
"""

_PYEXPORT_JS = """
(function () {
  var dlg = document.getElementById('pyexport');
  if (!dlg) return;
  var opener = null;
  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target : null;
    if (!t) return;
    var open = t.closest('[data-pyexport-open]');
    if (open) opener = open;
    if (t.closest('.pyexport-close')) dlg.close();
    var copy = t.closest('[data-pyexport-copy]');
    if (copy) copyCode(copy);
    var dl = t.closest('[data-pyexport-download]');
    if (dl) download(dl);
  });
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target === dlg) {
      if (!dlg.open) dlg.showModal();
      var first = dlg.querySelector('.pyexport-close');
      if (first) first.focus();
    } else if (dlg.open && dlg.querySelector('[data-kind="run"]') &&
               !document.querySelector('[data-pyexport-run]')) {
      dlg.close();  // cleared results take the run's code with them
    }
  });
  dlg.addEventListener('close', function () {
    if (opener && document.body.contains(opener)) opener.focus();
  });
  function code() {
    var el = dlg.querySelector('.pyexport-code');
    return el ? el.textContent : '';
  }
  function say(msg) {
    var live = dlg.querySelector('.pyexport-live');
    if (live) live.textContent = msg;
  }
  function flash(btn, label) {
    var old = btn.dataset.label || btn.textContent;
    btn.dataset.label = old;
    btn.textContent = label;
    setTimeout(function () { btn.textContent = old; }, 2000);
  }
  function selectCode() {
    var el = dlg.querySelector('.pyexport-code');
    if (!el) return;
    var r = document.createRange();
    r.selectNodeContents(el);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
    el.focus();
  }
  function copyCode(btn) {
    var fail = function () {
      selectCode();
      say('Copy failed \u2013 code selected, press Ctrl/Cmd+C');
      flash(btn, 'Copy failed');
    };
    if (!navigator.clipboard) { fail(); return; }
    navigator.clipboard.writeText(code()).then(function () {
      say('Copied');
      flash(btn, 'Copied');
    }, fail);
  }
  function download(btn) {
    var blob = new Blob([code()], {type: 'text/x-python'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = btn.dataset.filename || 'pyfds_evac.py';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }
})();
"""


def _run_code_button(label: str = "Show Python for this run"):
    """ "Show Python for this run", or nothing when no run is recorded."""
    spec = manager.spec
    if spec is None:
        return ""
    return Button(
        label,
        type="button",
        hx_post=f"/export/run?run={spec.run_id}",
        hx_include="#run-form",
        hx_params="not files,upload_name",
        hx_target="#pyexport",
        hx_swap="innerHTML",
        data_pyexport_open="1",
        data_pyexport_run=str(spec.run_id),
        cls="pyexport-btn",
    )


def _pyexport_notes(version, scenario_name: str, scenario_path: str) -> list:
    """The plain-text notices above the code, one line each."""
    notes = [
        P(
            f"Packages: needs pyfds-evac {version or '(version not recorded)'} "
            "(the one this GUI runs). Install it the same way as this GUI, e.g. "
            "`uv sync` in the repo. The GUI extra is not needed."
        ),
        P(
            "Files not included: this file contains code only. The scenario "
            "folder and FDS results are not included; copy them to the other "
            "machine."
        ),
        P(
            "Paths are from this computer. Edit the PATHS block at the top of the "
            "script: SCENARIO, FDS_DIR, VIS_CACHE (if used) and OUTPUT_DIR."
        ),
    ]
    if str(scenario_name).startswith(params.UPLOAD_PREFIX):
        notes.append(
            P(
                "This scenario was uploaded into the GUI's own folder "
                f"{scenario_path}; that folder will not exist elsewhere."
            )
        )
    notes += [
        P(
            "Outputs: the script writes to a new output folder and does not "
            "overwrite this GUI run's files."
        ),
        P(
            "Reproducibility: results can differ from the GUI run, even with "
            "the same seed. Repeated runs in one GUI session are affected too "
            "(#198). Different versions or platforms can also change results."
        ),
        Details(
            Summary("Details: what the GUI adds or leaves out"),
            P(
                "Included: route-cost history collection, as the GUI keeps it. "
                "The trajectory SQLite and its manifest are copied to OUTPUT_DIR."
            ),
            P(
                "Omitted: the live progress callback, which only drives the GUI, "
                "and the GUI's CSV histories and app bundle. Their writer lives "
                "in run.py, outside the installed package."
            ),
        ),
    ]
    return notes


def _pyexport_panel(
    title: str,
    badge: str,
    kind: str,
    script=None,
    notes: list | None = None,
    status: str | None = None,
    error: Exception | None = None,
    changed: str | None = None,
):
    """Dialog contents: heading, status, notices, code and its actions."""
    head = Div(
        Button("Close", type="button", cls="pyexport-close"),
        H2(title, id="pyexport-title"),
        Span(badge, cls="pyexport-badge"),
        cls="pyexport-head",
    )
    body = []
    if status:
        body.append(P(f"Status: {status}", cls="pyexport-status"))
    if changed:
        body.append(P(changed, cls="pyexport-status"))
    if error is not None:
        body.append(
            Div(
                P(
                    f"These settings cannot be run, so there is no code: {error}",
                    cls="pyexport-error",
                ),
                Details(
                    Summary("Details"),
                    Pre(
                        f"{type(error).__name__}: {error}", style="white-space:pre-wrap"
                    ),
                ),
            )
        )
    if notes:
        body.append(Div(*notes, cls="pyexport-notes"))
    if script is not None:
        body.append(
            Pre(
                Code(script.code),
                cls="pyexport-code",
                tabindex="0",
                aria_label="Generated Python code",
            )
        )
    disabled = {} if script is not None else {"disabled": True}
    actions = Div(
        Button(
            "Copy",
            type="button",
            cls="pyexport-act",
            data_pyexport_copy="1",
            **disabled,
        ),
        Button(
            "Download .py",
            type="button",
            cls="pyexport-act",
            data_pyexport_download="1",
            data_filename=script.filename if script is not None else "",
            **disabled,
        ),
        *(
            []
            if script is not None
            else [Span("Fix the settings to generate code", cls="pyexport-notes")]
        ),
        Span(role="status", aria_live="polite", cls="pyexport-live pyexport-notes"),
        cls="pyexport-actions",
    )
    return Div(head, *body, actions, data_kind=kind)


def _script_inputs(opts) -> dict:
    """The options the exported script uses: all but the GUI's output files."""
    return {
        k: v for k, v in dict(opts).items() if k not in pyexport.OMITTED_OUTPUT_KEYS
    }


def _form_vs_run(form: dict, spec) -> tuple[bool, Exception | None]:
    """``(changed, error)``: does the form still resolve to the run's options?

    Output paths are left out of the comparison (see ``_script_inputs``), so
    a derived folder, whose name carries the time it is resolved, is not a
    change. A form that no longer resolves counts as changed.
    """
    try:
        _scenario, opts = _resolve_form(form)
    except Exception as exc:
        return True, exc
    return _script_inputs(vars(opts)) != _script_inputs(spec.opts), None


def _form_changed_note(form: dict, spec) -> str | None:
    """Say so when the current form no longer resolves to the run's options."""
    changed, error = _form_vs_run(form, spec)
    if error is not None:
        return (
            "The form has changed since this run and does not currently "
            "resolve. This code reproduces the run, not the current form."
        )
    if not changed:
        return None
    return (
        "The form has changed since this run. This code reproduces the run, "
        "not the current form. Use Preview for the current settings."
    )


@rt("/export/preview")
async def export_preview(request: Request):
    """Code for the current form settings, resolved exactly as /run would."""
    form = dict(await request.form())
    title = "Preview: current form settings (not a run)"
    try:
        scenario, opts = _resolve_form(form)
        version, commit, dirty = code_provenance()
        path = str(params.scenario_path(form.get("scenario")))
        script = pyexport.preview_script(
            vars(opts),
            str(form.get("scenario")),
            path,
            version=version,
            commit=commit,
            dirty=dirty,
            baseseed=scenario.seed,
        )
    except Exception as exc:
        return _pyexport_panel(title, "PREVIEW", "preview", error=exc)
    notes = _pyexport_notes(version, str(form.get("scenario")), path)
    return _pyexport_panel(title, "PREVIEW", "preview", script=script, notes=notes)


@rt("/export/run")
async def export_run(request: Request, run: int | None = None):
    """Code for the recorded run, from its frozen snapshot only."""
    form = dict(await request.form())
    with manager.snapshot():
        spec = manager.spec
    if spec is None or spec.run_id != run or spec.status == "running":
        return _pyexport_panel(
            "No recorded run",
            "RUN",
            "none",
            error=ValueError("this run's settings are no longer available"),
        )
    title = f"Code for run #{spec.run_id} · {spec.scenario_name} · {spec.started_at}"
    if spec.status in ("error", "cancelled"):
        word = "failed" if spec.status == "error" else "cancelled"
        title = f"Configuration of the {word} run #{spec.run_id} · {spec.scenario_name}"
    try:
        script = pyexport.run_script(spec)
    except Exception as exc:
        return _pyexport_panel(title, f"RUN #{spec.run_id}", "run", error=exc)
    return _pyexport_panel(
        title,
        f"RUN #{spec.run_id}",
        "run",
        script=script,
        notes=_pyexport_notes(
            spec.pyfds_evac_version, spec.scenario_name, spec.scenario_path
        ),
        status=pyexport.run_status(spec),
        changed=_form_changed_note(form, spec),
    )


@rt("/cancel")
async def cancel():
    """Stop an in-flight run; on a run that has ended, change nothing.

    Cancellation is cooperative (the worker unwinds on its next progress
    tick or between phases), so wait briefly for the worker to end. The wait
    is bounded so a slow phase (FDS slice parsing, output writing) can't hang
    the request. If the worker is still unwinding when it expires, the panel
    stays on the progress stream in a "cancelling" state and Run stays
    disabled; the stream's terminal ``done`` event settles it once the
    worker has ended. A cancelled run keeps its snapshot until Clear, so its
    configuration can still be shown as code.

    A Cancel that arrives after the run finished (a stale button, a second
    tab) answers with the finished run's panel: it never discards results.
    """
    if not manager.cancel() and not manager.running:
        return _current_panel_body()
    if not await asyncio.to_thread(manager.join, _CANCEL_WAIT_S):
        return _running_stream_view(cancelling=True)
    return _current_panel_body()


@rt("/clear")
async def clear():
    """Drop a finished run from the view and return to the standby panel.

    Only the in-app view and the run's snapshot go; the files the run wrote
    stay on disk.
    """
    # A Clear left over from an earlier run must not hand back an enabled Run
    # button over a live worker.
    if manager.running:
        return _running_stream_view(cancelling=manager.status == "cancelling")
    manager.reset()
    return _run_panel_idle_body(), *_clear_alerts()


@rt("/panel")
def panel():
    """The run panel for the server's current state (see ``_run_column``)."""
    return _current_panel_body()


@rt("/form-state")
async def form_state(request: Request):
    """Banner saying the form no longer matches the results shown, or nothing.

    Evaluated on the server with the same resolution as /run and the Python
    export, so "changed" means the run would be configured differently.
    """
    form = dict(await request.form())
    with manager.snapshot():
        spec, status = manager.spec, manager.status
    if status != "done" or spec is None:
        return ""
    changed, error = _form_vs_run(form, spec)
    tag = Span(
        *(["Previous settings"] if changed else []),
        id="results-stale-tag",
        cls="state-tag" if changed else "",
        hx_swap_oob="true",
    )
    if not changed:
        return "", tag
    if error is not None:
        text = (
            f"Settings changed since run #{spec.run_id} and currently cannot be "
            f"run: {_field_label(str(error)) or type(error).__name__}"
        )
    else:
        text = (
            f"Settings changed since run #{spec.run_id}. The results below show "
            "that run's settings, not the form. Run again to get results for "
            "the current settings."
        )
    banner = Div(
        Span(Span("✎", aria_hidden="true"), " Changed", cls="state-tag is-changed"),
        Span(text),
        cls="settings-banner",
    )
    return banner, tag


_BTN_QUIET = (
    "padding:7px 13px;border-radius:9px;cursor:pointer;"
    f"{_MONO};font-size:11px;"
    "background:transparent;color:var(--ink-dim);"
    "border:1px solid var(--hairline)"
)

_DOCS_CASE_REQUIREMENTS = (
    "https://pedestriandynamics.org/pyFDS-Evac/docs/fds-case-requirements/"
)


def _run_number() -> int:
    spec = manager.spec
    return spec.run_id if spec is not None else manager.run_id


def _run_title() -> str:
    """``run #N · scenario · start time`` of the run the manager holds."""
    spec = manager.spec
    parts = [f"run #{_run_number()}", manager.scenario_name or "scenario"]
    if spec is not None:
        parts.append(spec.started_at)
    return " · ".join(parts)


def _clear_button(confirm: bool) -> Button:
    """Clear, confirmed first when it would drop results from the view."""
    extra = (
        {
            "hx_confirm": (
                f"Clear the results of run #{_run_number()} from this view? "
                "The files on disk are kept."
            )
        }
        if confirm
        else {}
    )
    return Button(
        "Clear results" if confirm else "Clear",
        type="button",
        hx_post="/clear",
        hx_target="#run-panel",
        hx_swap="innerHTML show:top",
        style=_BTN_QUIET,
        **extra,
    )


def _state_head(glyph: str, word: str, *actions, tone: str = "") -> Div:
    """Header of a settled run: state in words, run id, and its actions.

    The glyph is decorative; the state word carries the meaning, so colour
    and glyph are never the only cue.
    """
    return Div(
        Div(
            Span(glyph, aria_hidden="true", cls="state-glyph"),
            Span(word, cls="state-word"),
            Span(_run_title(), cls="state-run"),
            cls="state-line",
        ),
        Div(*actions, cls="state-actions"),
        cls=f"state-head {tone}".strip(),
    )


def _run_log() -> Details | str:
    """The run's console, collapsed, once the run has settled."""
    lines = manager.log_lines
    if not lines:
        return ""
    return Details(
        Summary(f"Run log ({len(lines)} lines)"),
        Pre("\n".join(lines[-300:]), cls="console-box run-log"),
        cls="run-log-details",
    )


def _cancelled_view() -> Div:
    """Terminal panel of a cancelled run: nothing to show but its settings."""
    return Div(
        _state_head(
            "■",
            "Cancelled",
            _run_code_button("Show configuration of this run"),
            _clear_button(False),
            tone="is-cancelled",
        ),
        P(
            f"Run #{_run_number()} was cancelled. No results were produced; "
            "files it had already written stay on disk.",
            cls="state-msg",
        ),
        style=_PANEL,
        cls="state-panel",
    )


def _superseded_view(run_id: int) -> Div:
    """Panel for a stream whose run has given way to a later one."""
    return Div(
        Div(
            Div(
                Span("↻", aria_hidden="true", cls="state-glyph"),
                Span("Ended", cls="state-word"),
                Span(f"run #{run_id}", cls="state-run"),
                cls="state-line",
            ),
            Div(
                Button(
                    "Show current run",
                    type="button",
                    hx_get="/panel",
                    hx_target="#run-panel",
                    hx_swap="innerHTML show:top",
                    style=_BTN_QUIET,
                ),
                cls="state-actions",
            ),
            cls="state-head",
        ),
        P(
            f"Run #{run_id} has ended and run #{manager.run_id} has started, "
            "possibly in another window. Its results are no longer held here.",
            cls="state-msg",
        ),
        style=_PANEL,
        cls="state-panel",
    )


def _failed_view() -> Div:
    """Terminal panel of a failed run: the message first, details apart."""
    raw = manager.error or "no message"
    _kind, sep, message = raw.partition(": ")
    return Div(
        _state_head(
            "✕",
            "Failed",
            _run_code_button("Show configuration of this run"),
            _clear_button(False),
            tone="is-failed",
        ),
        P(B("Run failed: "), message if sep else raw, cls="state-msg"),
        P(
            "Check the scenario and the FDS dir against the ",
            A(
                "FDS case requirements",
                href=_DOCS_CASE_REQUIREMENTS,
                target="_blank",
                rel="noopener",
            ),
            ", correct the settings and run again. Your settings are still "
            "in the form.",
            cls="state-hint",
        ),
        Details(Summary("Technical details"), Pre(raw, cls="tech-pre")),
        _run_log(),
        style=_PANEL,
        cls="state-panel",
    )


def _running_stream_view(cancelling: bool = False) -> Div:
    """The live run panel: progress card + console, wired to the SSE stream.

    ``cancelling`` renders the stop control disabled, for a cancel that is
    still waiting on the worker. The terminal ``done`` event replaces the
    whole view, so no stop control or live console outlives the run;
    ``data-run-live`` keeps Run locked for as long as this view is shown.
    """
    return Div(
        Div(
            # Only the dynamic half lives in the progress swap target. Cancel
            # sits outside it: #run-status is re-rendered on every progress
            # tick, and a stop control that is destroyed and rebuilt ~once a
            # second can swallow a click that lands mid-swap.
            Div(
                _running_card(None, cancelling),
                id="run-status",
                sse_swap="progress",
            ),
            Div(
                Button(
                    NotStr(
                        '<span style="font-size:9px">■</span>'
                        '<span class="run-btn-label">'
                        + ("Cancelling…" if cancelling else "Cancel run")
                        + "</span>"
                    ),
                    id="cancel-btn",
                    type="button",
                    disabled=cancelling,
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
            data_run_live="1",
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
        sse_swap="done",
        # Pinned to the current run, so a reconnect or a missed end can't
        # attach this panel to a later run.
        sse_connect=f"/progress?run={manager.run_id}",
        sse_close="done",
    )


def _console_view() -> Pre:
    text = "\n".join(manager.log_lines[-300:]) or "Waiting for output…"
    return Pre(text)


def _running_card(ev, cancelling: bool | None = None) -> Div:
    if cancelling is None:
        cancelling = manager.status == "cancelling"
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
                        f"Cancelling: {manager.scenario_name}"
                        if cancelling
                        else f"Running: {manager.scenario_name}",
                        style=f"{_GROTESK};font-weight:600;font-size:17px;{_INK}",
                    ),
                    Div(
                        f"run #{manager.run_id} · waiting for the current step "
                        "to finish"
                        if cancelling
                        else f"run #{manager.run_id} · coupled FDS × JuPedSim "
                        "step loop",
                        style=f"{_MONO};font-size:11px;{_MUTED};margin-top:2px",
                    ),
                ),
                style="display:flex;align-items:center;gap:12px",
            ),
            Div(
                f"{pct}%",
                style=f"{_GROTESK};font-weight:700;font-size:30px;letter-spacing:-.02em;color:var(--gold-ink)",
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
    """Header over a finished run: which run it is, and its actions.

    Results always carry their run id and start time, never the current
    form's scenario, and say that a new run replaces them in this view.
    """
    return Div(
        Div(
            Div(
                Span("Results", cls="state-word"),
                Span(_run_title(), cls="state-run"),
                *(
                    [Span("Results only: viewer not built", cls="state-tag")]
                    if manager.results_only
                    else []
                ),
                Span(id="results-stale-tag"),
                cls="state-line",
            ),
            Div(_run_code_button(), _clear_button(True), cls="state-actions"),
            cls="state-head",
        ),
        P(
            "Starting a new run replaces these results in this view; the files "
            "on disk are kept.",
            cls="state-hint",
        ),
        data_run_done="1",
    )


_MODELS_FED = "https://pedestriandynamics.org/pyFDS-Evac/models/fed/"
_MODELS_HEAT = "https://pedestriandynamics.org/pyFDS-Evac/models/heat/"
# Outcome glyphs are decorative; the outcome text always says it in words.
_OUTCOME_GLYPH = {True: "\u2713", False: "\u26a0", None: "?"}
_OUTCOME_TONE = {True: "is-complete", False: "is-incomplete", None: ""}


def _tile(label: str, value: str, accent: str) -> Div:
    return Div(
        Div(label, cls="kpi-label"),
        Div(value, cls="kpi-value"),
        cls="kpi-tile",
        style=f"border-top-color:{accent}",
    )


def _tenability_line(metrics: dict) -> Div | str:
    """Peak doses the run reported, only for the dose models it ran.

    ``fed_max`` and ``heat_fed_max`` are the highest cumulative dose any
    agent reached. Under probabilistic incapacitation each agent has its own
    threshold, so no threshold claim is attached. Incapacitation counts are
    not reported by the engine yet (#141) and are not computed here.
    """
    doses = []
    if "fed_max" in metrics:
        doses.append(
            Div(
                Span("Peak gas FED", cls="kpi-label"),
                Span(f"{metrics['fed_max']:.3f}", cls="dose-value"),
                Span(
                    "highest cumulative toxic-gas dose of any agent (dimensionless). ",
                    A("Gas FED", href=_MODELS_FED, target="_blank", rel="noopener"),
                    cls="dose-note",
                ),
                cls="dose-row",
            )
        )
    if "heat_fed_max" in metrics:
        doses.append(
            Div(
                Span("Peak heat FED", cls="kpi-label"),
                Span(f"{metrics['heat_fed_max']:.3f}", cls="dose-value"),
                Span(
                    "highest cumulative heat dose of any agent (dimensionless). ",
                    A("Heat FED", href=_MODELS_HEAT, target="_blank", rel="noopener"),
                    cls="dose-note",
                ),
                cls="dose-row",
            )
        )
    if not doses:
        return ""
    return Div(
        *doses,
        Div(
            Span("Incapacitated", cls="kpi-label"),
            Span("not reported by this version", cls="dose-note"),
            cls="dose-row",
        ),
        cls="dose-card",
    )


def _kpi_tiles(result) -> Div:
    """Outcome, headline numbers and doses, shared by both finished views.

    The outcome comes from ``all_evacuated`` (see ``run_outcome``) and is
    stated in words with a glyph, so colour is never the only cue.
    """
    spec = manager.spec
    time_limit = (
        spec.time_limit
        if spec is not None
        else getattr(manager.scenario, "max_simulation_time", None)
    )
    outcome = run_outcome(
        result.metrics.get("all_evacuated"),
        result.agents_remaining,
        result.total_agents,
        result.evacuation_time,
        time_limit,
    )
    seed = spec.seed_used if spec is not None else None
    if seed is None:
        seed = result.metrics.get("seed")
    tiles = [
        _tile(outcome.time_label, f"{result.evacuation_time:.1f} s", "#F4C430"),
        _tile(
            "Evacuated",
            f"{result.agents_evacuated} / {result.total_agents} agents",
            "#3B82F6",
        ),
        _tile("Remaining", f"{result.agents_remaining} agents", "#E01E37"),
        _tile("Seed used", "not recorded" if seed is None else str(seed), "#837A74"),
    ]
    return Div(
        Div(
            Span(
                _OUTCOME_GLYPH[outcome.complete],
                aria_hidden="true",
                cls="state-glyph",
            ),
            Span(outcome.label),
            cls=f"outcome-line {_OUTCOME_TONE[outcome.complete]}".strip(),
        ),
        Div(*tiles, cls="kpi-grid"),
        _tenability_line(result.metrics),
        style="display:flex;flex-direction:column;gap:12px",
    )


def _finished_view() -> Div:
    result = manager.result
    scenario = manager.scenario

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
        _run_log(),
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
            detail, colour, mark = (
                f"written · {path} · {_fmt_size(path)}",
                "var(--ink-dim)",
                "#F4C430",
            )
        elif not produced:
            detail, colour, mark = (
                f"not produced: {_missing_reason(field, opts)}",
                "var(--ink-faint)",
                "var(--surface-raised)",
            )
        else:
            detail, colour, mark = (
                "not written",
                "var(--ink-faint)",
                "var(--surface-raised)",
            )

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
                style=f"{_GROTESK};font-weight:600;font-size:14px;color:var(--gold-ink);margin-bottom:6px",
            ),
            P(
                "The trajectory animation and the FED / smoke / cognitive-map plots "
                "were not built for this run. Run the same scenario with "
                "“Run scenario” to see them.",
                style=f"font-size:.82rem;line-height:1.6;{_INK2};margin:0",
            ),
            style=_CARD,
        ),
        _run_log(),
        style="display:flex;flex-direction:column;gap:18px",
    )


@rt("/fed-progress")
async def fed_progress(run: int | None = None):
    run_id = manager.run_id if run is None else run

    async def gen():
        last_count = 0
        while True:
            # One snapshot per poll: nothing after a yield reads the manager.
            with manager.snapshot():
                current = manager.run_id == run_id
                status = manager.status
                snaps = list(manager.fed_snapshots)
            if not current:
                yield sse_message("{}", event="close")
                return
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
            if status in ("done", "error", "idle", "cancelled"):
                yield sse_message("{}", event="close")
                return
            await asyncio.sleep(0.5)

    return EventStream(gen())


def _render_error_view(exc: Exception) -> Div:
    """The run finished but its results view could not be built."""
    import traceback

    written = [Div(a, cls="artifact") for a in manager.artifacts]
    return Div(
        _state_head(
            "\u26a0",
            "Results not displayed",
            _run_code_button(),
            _clear_button(False),
            tone="is-failed",
        ),
        P(
            f"Run #{_run_number()} finished, but its results could not be displayed.",
            cls="state-msg",
        ),
        *(
            [
                P("The run wrote these files:", cls="state-hint"),
                Div(*written),
            ]
            if written
            else []
        ),
        Details(
            Summary("Technical details"),
            Pre(
                f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
                cls="tech-pre",
            ),
        ),
        _run_log(),
        style=_PANEL,
        cls="state-panel",
    )


def _done_view() -> Div:
    """Finished panel, or a plain message if building it fails."""
    try:
        return _results_only_view() if manager.results_only else _finished_view()
    except Exception as exc:
        return _render_error_view(exc)


def _terminal_view(status: str) -> Div | None:
    """The panel that settles a run in ``status``, or None while it runs."""
    if status == "done":
        return _done_view()
    if status == "error":
        return _failed_view()
    # Cancelled and idle still end with a terminal ``done``: a stream that
    # just closes is reopened by EventSource, so another tab, or a cancel
    # that outlived /cancel's wait, would never settle. Idle means the run
    # was cleared elsewhere.
    if status == "cancelled":
        return _cancelled_view()
    if status == "idle":
        return _run_panel_idle_body()
    return None


def _current_panel_body():
    """Contents of ``#run-panel`` for the state the server holds now."""
    status = manager.status
    if status in ("running", "cancelling"):
        return _running_stream_view(cancelling=status == "cancelling")
    return _terminal_view(status) or _run_panel_idle_body()


def _progress_step(run_id: int, last, last_log: int):
    """Render one /progress poll from a single run's state.

    Called under the manager's state lock and before any yield, so every
    message it returns describes run ``run_id``. Returns the messages, the
    updated cursors and whether the stream ends.
    """
    if manager.run_id != run_id:
        # This stream's run has ended and another has started; its
        # outcome is gone, so settle the panel instead of following.
        view = _superseded_view(run_id)
        return [sse_message(view, event="done")], last, last_log, True
    msgs = []
    n = len(manager.log_lines)
    if n != last_log:
        last_log = n
        msgs.append(sse_message(_console_view(), event="console"))
    final = _terminal_view(manager.status)
    if final is not None:
        msgs.append(sse_message(final, event="done"))
        return msgs, last, last_log, True
    ev = manager.last_event
    if ev is not None and ev != last:
        last = ev
        msgs.append(sse_message(_running_card(ev), event="progress"))
    return msgs, last, last_log, False


@rt("/progress")
async def progress(run: int | None = None):
    run_id = manager.run_id if run is None else run

    async def gen():
        last = None
        last_log = -1
        while True:
            # Render the whole poll first: after a yield the manager may
            # hold another run, so nothing is read from it until the next.
            with manager.snapshot():
                msgs, last, last_log, end = _progress_step(run_id, last, last_log)
            for msg in msgs:
                yield msg
            if end:
                return
            await asyncio.sleep(0.1)

    return EventStream(gen())


if __name__ == "__main__":
    serve()
