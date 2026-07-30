"""Visual theme for the pyFDS-Evac GUI: "Warm Dark Lab".

A warm dark instrument panel: near-black warm ground, warm off-white ink, and
a single clay/terracotta accent (#CC785C). The FED tenability tiers
(Safe/Alert/Critical/Severe) remain the semantic colour system and are always
paired with a text label (colour is never the sole cue).

Retheming is done by overriding franken-ui's shadcn-style CSS variables on
<html>, so every component inherits the palette; the rest adds typography
(Archivo display, IBM Plex Mono labels, IBM Plex Sans body), chrome, a faint
engineering grid, warm shadows, and load motion.
"""

from __future__ import annotations

from typing import Any, List

from fasthtml.common import Link, Style

_FONTS = Link(
    rel="stylesheet",
    href=(
        "https://fonts.googleapis.com/css2?"
        "family=Archivo:wght@500;600;700;800&"
        "family=IBM+Plex+Mono:wght@400;500;600&"
        "family=IBM+Plex+Sans:wght@400;500;600&display=swap"
    ),
)

# Palette (HSL tokens; warm dark):
#   ground   40 6% 10%   surface/card  40 5% 14%   ink  45 20% 91%
#   accent   clay #CC785C   muted-ink  43 8% 62%   line  40 5% 26%
#   tiers  safe #3F8F57  alert #D19A2E  critical #D2722B  severe #C23B2E
_CSS = """
:root, html.uk-theme-blue {
  --background: 40 6% 10%;
  --foreground: 45 20% 91%;
  --card: 40 5% 14%;
  --card-foreground: 45 20% 91%;
  --popover: 40 5% 13%;
  --popover-foreground: 45 20% 91%;
  --primary: 16 55% 60%;
  --primary-foreground: 30 30% 10%;
  --secondary: 40 4% 20%;
  --secondary-foreground: 45 15% 85%;
  --muted: 40 4% 20%;
  --muted-foreground: 43 8% 62%;
  --accent: 20 30% 24%;
  --accent-foreground: 22 55% 72%;
  --destructive: 5 62% 55%;
  --destructive-foreground: 45 20% 95%;
  --border: 40 5% 26%;
  --input: 40 5% 22%;
  --ring: 16 55% 58%;
  --radius: .5rem;

  --font-display: 'Archivo', system-ui, sans-serif;
  --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;

  --clay: #cc785c;
  --tier-safe: #3f8f57;
  --tier-alert: #d19a2e;
  --tier-critical: #d2722b;
  --tier-severe: #c23b2e;

  /* warm, hue-shifted shadow (not pure black) */
  --shadow-warm: 20 14% 3%;
}
html.uk-theme-blue { color-scheme: dark; }

html, body { background: hsl(var(--background)); }
body {
  font-family: var(--font-sans);
  color: hsl(var(--foreground));
  background:
    radial-gradient(1100px 460px at 82% -160px, hsl(16 52% 58% / .07), transparent 60%),
    radial-gradient(820px 460px at -5% -8%, hsl(40 40% 70% / .14), transparent 58%),
    hsl(var(--background));
  background-attachment: fixed;
  min-height: 100vh;
}
/* atmosphere: faint engineering grid + paper grain on warm ink */
body::before {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    linear-gradient(hsl(45 20% 90% / .04) 1px, transparent 1px),
    linear-gradient(90deg, hsl(45 20% 90% / .04) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(120% 90% at 50% 0%, #000 30%, transparent 100%);
}
body::after {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  opacity: .5; mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.035'/%3E%3C/svg%3E");
}
.uk-container, .app-header { position: relative; z-index: 1; }

/* ---- typography ---- */
h1, h2, h3, h4, .uk-card-title, .uk-h1, .uk-h2, .uk-h3 {
  font-family: var(--font-display);
  letter-spacing: -.012em;
  color: hsl(var(--foreground));
}
.uk-form-label {
  font-family: var(--font-mono);
  text-transform: uppercase;
  font-size: .64rem;
  letter-spacing: .16em;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}
.uk-input, .uk-select, input { font-family: var(--font-mono); }
.uk-input { font-size: .82rem; background: hsl(var(--input)); }

/* inline help badge next to a field label */
.lbl-help { display: inline-flex; align-items: center; }
.help-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; margin-left: .45rem; border-radius: 99px;
  border: 1px solid hsl(var(--border)); color: hsl(var(--muted-foreground));
  font-size: .58rem; font-weight: 700; line-height: 1; cursor: help;
  transition: color .15s, border-color .15s, background .15s;
}
.help-badge:hover {
  color: var(--clay); border-color: hsl(var(--primary) / .6);
  background: hsl(var(--accent) / .6);
}
.uk-input::placeholder { color: hsl(var(--muted-foreground) / .6); }
::selection { background: hsl(16 52% 58% / .22); color: hsl(var(--foreground)); }

/* ---- header chrome ---- */
.app-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 1.5rem; flex-wrap: wrap;
  max-width: 80rem; margin: 0 auto; padding: 2rem 1.5rem 1.25rem;
  border-bottom: 1px solid hsl(var(--border));
}
.brand-line { display: flex; align-items: baseline; gap: .55rem; }
.brand {
  font-family: var(--font-mono); font-weight: 700; font-size: 1.5rem;
  letter-spacing: .12em; color: hsl(var(--foreground));
}
.brand b { color: var(--clay); font-weight: 700; }
.brand .tick { color: hsl(var(--muted-foreground)); font-weight: 500; }
.status {
  display: inline-flex; align-items: center; gap: .45rem;
  font-family: var(--font-mono); font-size: .6rem; letter-spacing: .22em;
  text-transform: uppercase; color: hsl(var(--muted-foreground));
  padding: .15rem .55rem; border: 1px solid hsl(var(--border)); border-radius: 99px;
}
.status .dot {
  width: 7px; height: 7px; border-radius: 99px; background: var(--tier-safe);
  box-shadow: 0 0 0 0 hsl(140 38% 44% / .5); animation: pulse 2.4s infinite;
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 hsl(140 38% 44% / .45); }
  70% { box-shadow: 0 0 0 7px hsl(140 38% 44% / 0); }
  100% { box-shadow: 0 0 0 0 hsl(140 38% 44% / 0); }
}
.tagline {
  font-family: var(--font-mono); font-size: .68rem; letter-spacing: .04em;
  color: hsl(var(--muted-foreground)); margin-top: .35rem;
}
.tier-legend { display: flex; gap: .9rem; align-items: center; }
.tier {
  display: inline-flex; align-items: center; gap: .4rem;
  font-family: var(--font-mono); font-size: .58rem; letter-spacing: .14em;
  text-transform: uppercase; color: hsl(var(--muted-foreground));
}
.tier .sw {
  width: 9px; height: 9px; border-radius: 2px; display: inline-block; flex: none;
}
.tier.safe .sw { background: var(--tier-safe); }
.tier.alert .sw { background: var(--tier-alert); }
.tier.critical .sw { background: var(--tier-critical); }
.tier.severe .sw { background: var(--tier-severe); }

/* ---- cards / surfaces ---- */
.uk-card {
  background: hsl(var(--card) / .82);
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius);
  backdrop-filter: blur(6px) saturate(1.05);
  box-shadow:
    0 1px 0 hsl(0 0% 100% / .06) inset,
    0 18px 48px -34px hsl(var(--shadow-warm) / .5);
}
.uk-card-title, .uk-card h3 {
  font-family: var(--font-display); font-weight: 600; letter-spacing: -.01em;
}

/* ---- accordion as instrument modules ---- */
.uk-accordion-title {
  background: hsl(var(--secondary) / .7) !important;
  color: hsl(var(--foreground)) !important;
  font-family: var(--font-mono) !important;
  text-transform: uppercase; letter-spacing: .14em; font-size: .68rem; font-weight: 600;
  padding: .62rem .8rem; border-radius: .4rem;
  border: 1px solid hsl(var(--border)); border-left: 2px solid hsl(var(--primary));
  transition: border-color .2s, background .2s;
}
.uk-accordion-title:hover { background: hsl(var(--accent) / .6) !important; }
.uk-open > .uk-accordion-title { border-left-color: var(--clay); }

/* ---- buttons ---- */
.uk-btn {
  font-family: var(--font-mono); text-transform: uppercase;
  letter-spacing: .12em; font-weight: 500; font-size: .7rem;
  border-radius: .4rem; transition: filter .15s, box-shadow .2s, transform .05s;
}
.uk-btn:active { transform: translateY(1px); }
.uk-btn-primary {
  background: linear-gradient(180deg, hsl(18 56% 62%), hsl(15 50% 54%));
  color: hsl(var(--primary-foreground));
  box-shadow: 0 1px 0 hsl(0 0% 100% / .25) inset,
              0 10px 26px -12px hsl(16 52% 40% / .6);
}
.uk-btn-primary:hover {
  filter: brightness(1.04);
  box-shadow: 0 1px 0 hsl(0 0% 100% / .25) inset,
              0 0 0 1px hsl(16 52% 50% / .4), 0 12px 26px -10px hsl(16 52% 40% / .55);
}
.uk-btn-secondary {
  background: hsl(var(--secondary)); color: hsl(var(--secondary-foreground));
  border: 1px solid hsl(var(--border));
}
.uk-btn-secondary:hover { border-color: hsl(var(--primary) / .6); color: var(--clay); }
/* base ghost: transparent on the theme surface (overrides pico's blue button) */
.uk-btn-ghost {
  background: transparent; color: hsl(var(--foreground)); border-color: transparent;
}
.uk-btn-ghost:hover { background: hsl(var(--accent) / .7); color: var(--clay); }

/* ---- run panel: telemetry ---- */
.telemetry { font-family: var(--font-mono); letter-spacing: .02em; }
.report-line { font-family: var(--font-mono); font-size: .82rem; }
.report-line b { color: var(--clay); }

/* finished report: left-aligned, two-column metric grid */
.metrics-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1.6rem; margin-top: .4rem;
}
.metric-cell {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 1rem; padding: .32rem 0; border-bottom: 1px dashed hsl(var(--border));
}
.metric-k {
  font-family: var(--font-mono); color: hsl(var(--muted-foreground));
  text-transform: uppercase; font-size: .6rem; letter-spacing: .12em;
}
.metric-v { font-family: var(--font-mono); font-size: .85rem; font-weight: 600; }
.artifact {
  font-family: var(--font-mono); font-size: .68rem; line-height: 1.75;
  color: hsl(var(--muted-foreground)); word-break: break-all;
}
@media (max-width: 640px) { .metrics-grid { grid-template-columns: 1fr; } }

/* ---- tabs (Simulation / Model) ---- */
.tab-nav {
  max-width: 80rem; margin: 0 auto; padding: .9rem 1.5rem 0;
  display: flex; gap: .3rem; position: relative; z-index: 1;
  border-bottom: 1px solid hsl(var(--border));
}
.tab-btn {
  font-family: var(--font-mono); text-transform: uppercase; letter-spacing: .12em;
  font-size: .66rem; font-weight: 600; padding: .55rem .95rem;
  background: transparent; border: 0; border-bottom: 2px solid transparent;
  color: hsl(var(--muted-foreground)); cursor: pointer; margin-bottom: -1px;
  transition: color .15s, border-color .15s;
}
.tab-btn:hover { color: hsl(var(--foreground)); }
.tab-btn.active { color: var(--clay); border-bottom-color: var(--clay); }

/* ---- model documentation ---- */
.doc-intro, .doc-foot {
  font-family: var(--font-sans); color: hsl(var(--muted-foreground));
  line-height: 1.75; max-width: 72ch;
}
.doc-card p { line-height: 1.75; max-width: 74ch; }
.eq {
  margin: .75rem 0; padding: .65rem 1rem; overflow-x: auto;
  background: hsl(var(--card)); border: 1px solid hsl(var(--border));
  border-left: 2px solid var(--clay); border-radius: .4rem;
}
.eq .katex { font-size: 1.05em; }
.tier-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: .7rem; margin-top: .4rem;
}
.tier-card {
  padding: .7rem .85rem; border-radius: .4rem;
  border: 1px solid hsl(var(--border)); border-top: 3px solid;
}
.tier-card h4 {
  font-family: var(--font-mono); text-transform: uppercase;
  font-size: .66rem; letter-spacing: .1em;
}
.tier-card p {
  font-family: var(--font-mono); font-size: .74rem;
  color: hsl(var(--muted-foreground)); margin-top: .2rem;
}
.tier-card.safe { border-top-color: var(--tier-safe); }
.tier-card.alert { border-top-color: var(--tier-alert); }
.tier-card.critical { border-top-color: var(--tier-critical); }
.tier-card.severe { border-top-color: var(--tier-severe); }
@media (max-width: 640px) { .tier-grid { grid-template-columns: repeat(2, 1fr); } }

/* ---- canvas trajectory animation ---- */
.traj-wrap { margin-top: .6rem; }
.traj-canvas {
  width: 100%; height: 440px; display: block;
  border: 1px solid hsl(var(--border)); border-radius: .4rem;
  background:
    radial-gradient(120% 120% at 50% 0%, hsl(40 5% 15%), hsl(40 6% 11%));
}
.traj-controls {
  display: flex; align-items: center; gap: .8rem; margin-top: .6rem;
}
.traj-play {
  width: 2.1rem; height: 2.1rem; flex: none; border-radius: 99px;
  border: 1px solid hsl(var(--border)); background: hsl(48 30% 97%);
  color: hsl(var(--foreground)); cursor: pointer; font-size: .8rem;
  display: inline-flex; align-items: center; justify-content: center;
  transition: border-color .15s, color .15s;
}
.traj-play:hover { border-color: hsl(var(--primary) / .6); color: var(--clay); }
.traj-slider { flex: 1; accent-color: var(--clay); cursor: pointer; }
.traj-time {
  font-family: var(--font-mono); font-size: .7rem; min-width: 6ch;
  color: hsl(var(--muted-foreground)); text-align: right;
}
.traj-color { display: inline-flex; align-items: center; gap: .35rem; }
.traj-color-lbl {
  font-family: var(--font-mono); font-size: .56rem; letter-spacing: .14em;
  text-transform: uppercase; color: hsl(var(--muted-foreground));
}
.cmode {
  font-family: var(--font-mono); font-size: .58rem; letter-spacing: .1em;
  text-transform: uppercase; padding: .25rem .5rem; cursor: pointer;
  border: 1px solid hsl(var(--border)); border-radius: .3rem;
  background: hsl(48 30% 97%); color: hsl(var(--muted-foreground));
}
.cmode.active {
  border-color: hsl(var(--primary) / .6); color: var(--clay);
  background: hsl(var(--accent) / .6);
}

/* ---- FED live dose panel ---- */
.fed-panel {
  margin-top: .9rem; padding: .8rem 1rem;
  border: 1px solid hsl(var(--border)); border-radius: .5rem;
  background: hsl(var(--card));
}
.fed-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: .6rem;
}
.fed-title {
  font-family: var(--font-mono); font-size: .56rem; letter-spacing: .14em;
  text-transform: uppercase; color: hsl(var(--muted-foreground));
}
.fed-legend { display: flex; gap: .7rem; }
.fed-leg { font-family: var(--font-mono); font-size: .55rem; letter-spacing: .04em; }
.fed-leg::before { content: "\2022  "; }
.fed-leg.safe { color: var(--tier-safe); }
.fed-leg.alert { color: var(--tier-alert); }
.fed-leg.critical { color: var(--tier-critical); }
.fed-leg.severe { color: var(--tier-severe); }
.fed-stats {
  display: flex; gap: 1.5rem; align-items: baseline; margin-bottom: .7rem;
}
.fed-stat-lbl {
  font-family: var(--font-mono); font-size: .55rem; letter-spacing: .06em;
  text-transform: uppercase; color: hsl(var(--muted-foreground)); margin-bottom: .1rem;
}
.fed-val {
  font-family: var(--font-mono); font-size: 1.5rem; font-weight: 500;
  color: var(--tier-safe); transition: color .3s;
}
.fed-bar {
  position: relative; height: 6px; border-radius: 99px;
  background: hsl(var(--secondary)); border: 1px solid hsl(var(--border));
  overflow: hidden; margin-bottom: .3rem;
}
.fed-bar-fill {
  position: absolute; inset: 0; width: 0%; border-radius: 99px;
  transition: width .15s;
  background: linear-gradient(90deg,
    var(--tier-safe), var(--tier-alert), var(--tier-critical), var(--tier-severe));
}
.fed-scale {
  display: flex; justify-content: space-between; margin-bottom: .6rem;
  font-family: var(--font-mono); font-size: .55rem; color: hsl(var(--muted-foreground));
}
.fed-spark { width: 100%; height: 60px; display: block; }

/* ---- streaming console (warm-dark inset terminal) ---- */
.console-box {
  max-height: 20rem; overflow: auto;
  background: #1e1c19 !important; border: 1px solid hsl(30 12% 22%);
  border-radius: .4rem; padding: .7rem .85rem;
  box-shadow: inset 0 2px 14px -8px #000;
}
/* franken-ui gives <pre> a light code-block background; override it so the
   bright text sits on the dark inset, not on light-on-light. */
.console-box pre {
  font-family: var(--font-mono); font-size: .72rem; line-height: 1.55;
  color: #eee7d8 !important; background: transparent !important;
  border: 0 !important; padding: 0 !important; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}
.console-box::-webkit-scrollbar-thumb { background: hsl(30 8% 38%); }

/* standby (idle) screen */
.standby {
  min-height: 58vh; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: .85rem; text-align: center;
}
.standby-label {
  display: inline-flex; align-items: center; gap: .5rem;
  font-family: var(--font-mono); text-transform: uppercase;
  letter-spacing: .42em; font-size: .66rem; color: hsl(var(--muted-foreground));
  padding: .4rem 1rem .4rem .85rem; border: 1px solid hsl(var(--border));
  border-radius: 99px;
}
.standby-label .dot {
  width: 7px; height: 7px; border-radius: 99px; background: var(--clay);
  box-shadow: 0 0 10px 0 hsl(16 52% 58% / .55); animation: pulse 2.4s infinite;
}
.standby-hint {
  font-family: var(--font-mono); font-size: .74rem; line-height: 1.7;
  color: hsl(var(--muted-foreground)); max-width: 38ch;
}

/* ---- scrollbar ---- */
* { scrollbar-width: thin; scrollbar-color: hsl(var(--border)) transparent; }
*::-webkit-scrollbar { width: 9px; height: 9px; }
*::-webkit-scrollbar-thumb { background: hsl(var(--border)); border-radius: 99px; }
*::-webkit-scrollbar-thumb:hover { background: hsl(var(--primary) / .6); }

/* ---- load motion ---- */
@keyframes riseIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
.rise { animation: riseIn .6s cubic-bezier(.2,.7,.2,1) both; }
@media (prefers-reduced-motion: reduce) { .rise, .status .dot, .standby-label .dot { animation: none; } }
"""


def headers() -> List[Any]:
    """Return the <head> elements that apply the theme (after franken-ui)."""
    return [_FONTS, Style(_CSS)]
