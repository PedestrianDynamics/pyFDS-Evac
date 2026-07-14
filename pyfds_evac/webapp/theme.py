"""Visual theme for the pyFDS-Evac GUI: dark "Instrument" UI with a fire palette.

Smoky warm-grey ground (#211e20), warm off-white ink (#f2ede9), and a molten
heat ramp — gold -> amber -> orange -> crimson — for fire-simulation context.
The Model tab is intentionally a different world: a cyberpunk / early-2000s
retro terminal (Press Start 2P + VT323, scanlines, neon, green-on-black math),
scoped under ``#tab-model`` so the Simulation tab stays clean.

Drop-in replacement for the original ``theme.py`` — all class names the app
emits are preserved; only the visual values change.
"""

from __future__ import annotations

from typing import Any, List

from fasthtml.common import Link, Style

_FONTS = Link(
    rel="stylesheet",
    href=(
        "https://fonts.googleapis.com/css2?"
        "family=Space+Grotesk:wght@400;500;600;700&"
        "family=Hanken+Grotesk:wght@400;500;600&"
        "family=JetBrains+Mono:wght@400;500&"
        # retro faces used only by the Model tab
        "family=Press+Start+2P&"
        "family=VT323&display=swap"
    ),
)

# Palette
#   ground   #211e20   panel #2a262a   input #2e2a2e   ink #f2ede9
#   muted    #b2a9a3   border rgba(255,255,255,.10)
#   heat ramp  safe #f4c430  alert #ffb020  critical #ff6a1a  severe #e01e37
#   molten primary  gold #ffc24d -> burnt orange #e8590c
#   retro/cyber (model only)  cyan #18e0ff  magenta #ff2d9b  green #39ff14  amber #ffb000
_CSS = """
:root, html.uk-theme-blue {
  --background: 320 4% 12%;
  --foreground: 27 30% 93%;
  --card: 300 4% 16%;
  --card-foreground: 27 30% 93%;
  --popover: 300 5% 14%;
  --popover-foreground: 27 30% 93%;
  --primary: 22 100% 55%;
  --primary-foreground: 25 80% 8%;
  --secondary: 300 4% 22%;
  --secondary-foreground: 27 20% 88%;
  --muted: 300 4% 22%;
  --muted-foreground: 27 10% 67%;
  --accent: 22 90% 20%;
  --accent-foreground: 38 95% 62%;
  --destructive: 350 79% 53%;
  --destructive-foreground: 0 0% 100%;
  --border: 30 4% 30%;
  --input: 300 4% 18%;
  --ring: 38 95% 57%;
  --radius: .8rem;

  --font-display: 'Space Grotesk', system-ui, sans-serif;
  --font-sans:    'Hanken Grotesk', system-ui, sans-serif;
  --font-mono:    'JetBrains Mono', ui-monospace, monospace;

  --ember:  #ff6a1a;
  --gold:   #f4c430;
  --tier-safe:     #f4c430;
  --tier-alert:    #ffb020;
  --tier-critical: #ff6a1a;
  --tier-severe:   #e01e37;

  --shadow-sm:  0 1px 3px rgba(0,0,0,.4),  0 1px 2px rgba(0,0,0,.3);
  --shadow-md:  0 8px 24px rgba(0,0,0,.45), 0 2px 6px rgba(0,0,0,.3);
  --shadow-lg:  0 18px 50px rgba(0,0,0,.55), 0 4px 12px rgba(0,0,0,.35);
}
html.uk-theme-blue { color-scheme: dark; }

html, body { background: #211e20; }
body {
  font-family: var(--font-sans);
  color: hsl(var(--foreground));
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
  background:
    radial-gradient(120% 80% at 85% -10%, rgba(255,90,31,.10), transparent 55%),
    radial-gradient(90% 70% at 5% 0%,     rgba(244,196,48,.06), transparent 50%),
    #211e20;
}
.uk-container, .app-header { position: relative; z-index: 1; }

/* ---- typography ---- */
h1, h2, h3, h4, .uk-card-title, .uk-h1, .uk-h2, .uk-h3 {
  font-family: var(--font-display);
  font-weight: 600;
  letter-spacing: -.02em;
  color: hsl(var(--foreground));
}
.uk-form-label {
  font-family: var(--font-display);
  font-size: .7rem;
  font-weight: 500;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: hsl(var(--muted-foreground));
}
.uk-input, .uk-select, input, select, textarea {
  font-family: var(--font-mono);
  font-size: .85rem;
  background: #2e2a2e;
  color: hsl(var(--foreground));
  border: 1px solid rgba(255,255,255,.10);
  border-radius: .55rem;
  transition: border-color .15s, box-shadow .15s;
}
.uk-input:focus, .uk-select:focus, input:focus, select:focus {
  border-color: var(--gold);
  box-shadow: 0 0 0 3px rgba(244,196,48,.18);
  outline: none;
}
.uk-input::placeholder { color: hsl(var(--muted-foreground) / .5); }
::selection { background: rgba(255,106,26,.32); color: #fff; }

/* inline help badge + in-flow help block */
/* The tip is a normal-flow block (not absolutely positioned), so it's bounded
   by the field width and can never overflow or be clipped by the sidebar. */
.lbl-line { display: inline-flex; align-items: center; gap: .35rem; }
.help-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 15px; height: 15px; border-radius: 99px;
  border: 1px solid rgba(255,255,255,.18); color: hsl(var(--muted-foreground));
  font-size: .58rem; font-weight: 700; cursor: pointer;
  transition: color .12s, border-color .12s; user-select: none;
}
.lblwrap { display: flex; flex-direction: column; gap: 6px; }
.lblwrap.open .help-badge { color: var(--gold); border-color: var(--gold); }
.badge-tip {
  display: none;
  background: #0d0c0e; color: #f2ede9;
  font-size: .72rem; font-weight: 400; line-height: 1.5;
  text-transform: none; letter-spacing: normal;
  padding: .5rem .65rem; border-radius: .5rem; border: 1px solid rgba(255,255,255,.14);
  white-space: normal; box-shadow: var(--shadow-md);
}
.lblwrap.open .badge-tip { display: block; }

/* run button running-state */
.run-btn:disabled { cursor: progress; filter: saturate(.5) brightness(.92); opacity: .9; }
.run-btn:disabled .run-btn-icon { animation: pulse 1.3s ease-in-out infinite; }

/* ---- header ---- */
.app-header {
  display: flex; align-items: center; justify-content: center;
  padding: 1rem 2rem;
  background: rgba(33,30,32,.72);
  backdrop-filter: saturate(150%) blur(18px);
  -webkit-backdrop-filter: saturate(150%) blur(18px);
  border-bottom: 1px solid rgba(255,255,255,.07);
  position: sticky; top: 0; z-index: 50;
}
.brand-group { display: flex; align-items: center; gap: 1rem; }
.app-logo { flex: none; }
.brand {
  font-family: var(--font-display); font-weight: 600; font-size: 1.3rem;
  letter-spacing: -.02em; color: hsl(var(--foreground));
}
.brand b { color: var(--ember); }
.tagline {
  font-family: var(--font-mono);
  font-size: .68rem; letter-spacing: .01em;
  color: hsl(var(--muted-foreground)); margin-top: .25rem;
}

/* ---- tier legend (run panel) ---- */
.tier-legend {
  margin-top: 1.25rem; padding: .9rem 1.25rem; border-radius: .9rem;
  background: #252127; border: 1px solid rgba(255,255,255,.08);
  width: 100%; max-width: 28rem;
}
.legend-label {
  font-family: var(--font-mono);
  font-size: .62rem; font-weight: 500; text-transform: uppercase;
  letter-spacing: .12em; color: hsl(var(--muted-foreground));
  text-align: center; margin-bottom: .7rem;
}
.tier-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; }
.tier {
  display: flex; flex-direction: column; align-items: center; gap: .4rem;
  font-family: var(--font-display); font-size: .72rem; font-weight: 600;
  color: hsl(var(--foreground));
}
.tier .sw { width: 10px; height: 10px; border-radius: 3px; display: inline-block; flex: none; }
.tier.safe .sw     { background: var(--tier-safe); }
.tier.alert .sw    { background: var(--tier-alert); }
.tier.critical .sw { background: var(--tier-critical); }
.tier.severe .sw   { background: var(--tier-severe); }
@media (max-width: 420px) { .tier-row { grid-template-columns: repeat(2, 1fr); row-gap: .75rem; } }
@keyframes pulse {
  0%   { box-shadow: 0 0 0 0   rgba(255,90,31,.5); }
  70%  { box-shadow: 0 0 0 7px rgba(255,90,31,0);  }
  100% { box-shadow: 0 0 0 0   rgba(255,90,31,0);  }
}

/* ---- cards ---- */
.uk-card {
  background: #2a262a;
  border: 1px solid rgba(255,255,255,.07);
  border-radius: 1.1rem;
  box-shadow: var(--shadow-md);
  transition: box-shadow .2s, border-color .2s;
}
.uk-card:hover { box-shadow: var(--shadow-lg); }
.uk-card-title, .uk-card h3 {
  font-family: var(--font-display); font-weight: 600; letter-spacing: -.018em;
}

/* ---- sidebar ---- */
.sidebar-title {
  font-size: 1.05rem !important; font-weight: 600 !important;
  letter-spacing: -.02em !important; margin-bottom: .25rem;
}
.scenario-field, .scenario-field > div { width: 100%; }
.scenario-field .uk-select, .scenario-field select { width: 100%; min-width: 0; border-radius: .6rem; }

/* ---- accordion ---- */
.uk-accordion-title {
  background: #322e32 !important;
  color: hsl(var(--foreground)) !important;
  font-family: var(--font-display) !important;
  font-weight: 600; font-size: .95rem !important; letter-spacing: -.01em;
  padding: .7rem 1rem; border-radius: .7rem;
  border: 1px solid rgba(255,255,255,.07); border-left: 2px solid var(--ember);
  transition: border-color .15s, background .15s;
}
.uk-accordion-title:hover { background: #3a343a !important; }
.uk-open > .uk-accordion-title { border-left-color: var(--gold); background: #3a343a !important; }

/* ---- buttons ---- */
.uk-btn {
  font-family: var(--font-display); font-weight: 600; font-size: .875rem;
  letter-spacing: -.005em; border-radius: .65rem;
  transition: filter .12s, box-shadow .15s, transform .06s;
}
.uk-btn:active { transform: scale(.98); }
.uk-btn-primary {
  background: linear-gradient(180deg, #ffc24d, #e8590c);
  color: #2a1606;
  box-shadow: 0 6px 20px rgba(232,89,12,.3);
}
.uk-btn-primary:hover { filter: brightness(1.06); box-shadow: 0 8px 26px rgba(232,89,12,.4); }
.uk-btn-secondary {
  background: #3a343a; color: hsl(var(--foreground));
  border: 1px solid rgba(255,255,255,.1);
}
.uk-btn-secondary:hover { border-color: var(--gold); color: var(--gold); }
.uk-btn-ghost:hover { background: #3a343a; color: var(--gold); }

/* ---- incapacitation mode toggle ---- */
.mode-toggle {
  display: flex; max-width: 17rem;
  background: #2e2a2e; border: 1px solid rgba(255,255,255,.08);
  border-radius: .65rem; padding: 4px; gap: 4px;
}
.mode-btn {
  flex: 1; padding: .5rem .6rem;
  font-family: var(--font-display); font-size: .78rem; font-weight: 500;
  letter-spacing: -.01em; cursor: pointer;
  background: transparent; color: hsl(var(--muted-foreground));
  border: 0; border-radius: .48rem;
  transition: background .15s, color .15s, box-shadow .15s;
}
.mode-btn.active { background: var(--gold); color: #2a1606; box-shadow: var(--shadow-sm); }
.mode-btn:hover:not(.active) { color: hsl(var(--foreground)); }

/* ---- run panel ---- */
.telemetry, .report-line { font-family: var(--font-mono); font-size: .82rem; }
.report-line b { color: var(--ember); }
.metrics-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 2rem; margin-top: .5rem;
}
.metric-cell {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 1rem; padding: .45rem 0; border-bottom: 1px solid rgba(255,255,255,.07);
}
.metric-k {
  font-family: var(--font-mono);
  font-size: .68rem; font-weight: 500; text-transform: uppercase; letter-spacing: .05em;
  color: hsl(var(--muted-foreground));
}
.metric-v { font-family: var(--font-mono); font-size: .9rem; font-weight: 500; color: hsl(var(--foreground)); }
.artifact {
  font-family: var(--font-mono); font-size: .68rem; line-height: 1.75;
  color: hsl(var(--muted-foreground)); word-break: break-all;
}
@media (max-width: 640px) { .metrics-grid { grid-template-columns: 1fr; } }

/* ---- tabs ---- */
.tab-nav { display: flex; align-items: center; justify-content: center; padding: 1rem 1.5rem .5rem; }
.tab-pills {
  display: flex; gap: 3px; padding: 3px; width: fit-content; margin: 0 auto;
  background: rgba(255,255,255,.04); border-radius: .7rem; border: 1px solid rgba(255,255,255,.07);
}
.tab-btn {
  font-family: var(--font-display);
  font-size: .82rem; font-weight: 500; letter-spacing: -.012em;
  padding: .4rem 1.1rem; background: transparent; border: 0;
  border-radius: .55rem; color: hsl(var(--muted-foreground));
  cursor: pointer; transition: background .15s, color .15s, box-shadow .15s;
}
.tab-btn:hover:not(.active) { color: hsl(var(--foreground)); background: rgba(255,255,255,.04); }
.tab-btn.active { background: #f2ede9; color: #211e20; box-shadow: var(--shadow-sm); }

/* ---- trajectory canvas ---- */
.traj-wrap { margin-top: .6rem; }
.traj-canvas {
  width: 100%; height: 460px; display: block;
  border: 1px solid rgba(255,255,255,.08); border-radius: .9rem; background: #1c191c;
}
.traj-controls { display: flex; align-items: center; gap: .8rem; margin-top: .7rem; }
.traj-play {
  width: 2.2rem; height: 2.2rem; flex: none; border-radius: 99px;
  border: 1px solid rgba(255,255,255,.12); background: #322e32;
  color: hsl(var(--foreground)); cursor: pointer; font-size: .8rem;
  display: inline-flex; align-items: center; justify-content: center;
  box-shadow: var(--shadow-sm); transition: border-color .12s, color .12s;
}
.traj-play:hover { border-color: var(--ember); color: var(--ember); }
.traj-slider { flex: 1; accent-color: var(--ember); cursor: pointer; }
.traj-time {
  font-family: var(--font-mono); font-size: .72rem; min-width: 6ch;
  color: hsl(var(--muted-foreground)); text-align: right;
}
.traj-color { display: inline-flex; align-items: center; gap: .35rem; }
.traj-color-lbl { font-family: var(--font-mono); font-size: .62rem; font-weight: 500; text-transform: uppercase; color: hsl(var(--muted-foreground)); }
.cmode {
  font-family: var(--font-display);
  font-size: .72rem; font-weight: 500; padding: .28rem .65rem; cursor: pointer;
  border: 1px solid rgba(255,255,255,.1); border-radius: .45rem;
  background: #2e2a2e; color: hsl(var(--muted-foreground));
  transition: border-color .12s, color .12s, background .12s;
}
.cmode.active { border-color: var(--ember); color: var(--ember); background: rgba(255,106,26,.12); }

/* ---- console ---- */
.console-box {
  max-height: 20rem; overflow: auto;
  background: #131113 !important; border: 1px solid rgba(255,255,255,.07);
  border-radius: .9rem; padding: .9rem 1.1rem;
}
.console-box pre {
  font-family: var(--font-mono); font-size: .75rem; line-height: 1.7;
  color: #d7cfca !important; background: transparent !important;
  border: 0 !important; padding: 0 !important; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}

/* ---- standby ---- */
.standby { min-height: 58vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1.1rem; text-align: center; }
.standby-label {
  display: inline-flex; align-items: center; gap: .5rem;
  font-family: var(--font-mono);
  font-size: .68rem; letter-spacing: .04em; text-transform: uppercase;
  color: hsl(var(--muted-foreground));
  padding: .45rem 1rem; border: 1px solid rgba(255,255,255,.1);
  border-radius: 99px; background: rgba(255,255,255,.02);
}
.standby-label .dot { width: 7px; height: 7px; border-radius: 99px; background: var(--ember); animation: pulse 2.4s infinite; }
.standby-hint { font-size: .85rem; line-height: 1.7; color: hsl(var(--muted-foreground)); max-width: 40ch; }

/* ---- utility ---- */
.hidden { display: none !important; }

/* ---- number input spinners ---- */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  appearance: none;
  background: #3A343A;
  border-left: 1px solid rgba(255,255,255,.09);
  border-radius: 0 9px 9px 0;
  opacity: 1;
  cursor: pointer;
  width: 22px;
}
input[type="number"] { -moz-appearance: textfield; }

/* ---- scrollbar ---- */
* { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,.14) transparent; }
*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-thumb { background: rgba(255,255,255,.14); border-radius: 99px; }
*::-webkit-scrollbar-thumb:hover { background: var(--ember); }

/* ---- load motion ---- */
/* ---- accordion chevron ---- */
details summary .chevron { transition: transform .2s ease; display: block; flex: none; }
details[open] summary .chevron { transform: rotate(180deg); }

@keyframes shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}
@keyframes riseIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.rise { animation: riseIn .35s cubic-bezier(.2,.8,.2,1) both; }
@media (prefers-reduced-motion: reduce) { .rise, .standby-label .dot { animation: none; } }


/* =================================================================== */
/*  MODEL TAB  ·  minimal warm-paper technical reference (scoped)        */
/*  NOTE: to fully hide the global header on this tab, app.py's tab JS    */
/*  toggles .app-header display — see the updated _TAB_JS.                */
/* =================================================================== */
@keyframes blink { 0%,49% { opacity: 1 } 50%,100% { opacity: 0 } }

#tab-model {
  background: #ece8df;
  color: #17150f;
  font-family: var(--font-mono);
  padding: 18px 40px 90px;
  margin: 0 calc(50% - 50vw);          /* break out to full viewport width */
  width: 100vw; max-width: 100vw;
}
#tab-model h3, #tab-model h4 {
  font-family: var(--font-mono); color: #17150f;
  letter-spacing: .2em; text-transform: uppercase;
}
#tab-model .doc-intro {
  font-family: var(--font-mono); font-size: 1rem; line-height: 1.7;
  color: #3a362c; max-width: 720px;
}
#tab-model .doc-intro::before { content: ">_ "; color: #1b17ff; }
#tab-model .doc-foot { font-family: var(--font-mono); font-size: .9rem; color: #6b655c; max-width: 760px; }

#tab-model .doc-card {
  background: transparent !important; box-shadow: none !important;
  border: 0 !important; border-top: 1px solid rgba(0,0,0,.13) !important;
  border-radius: 0 !important; max-width: 820px; margin: 0 auto;
  padding: 32px 0 !important;
}
#tab-model .doc-card > h3 { font-size: .72rem; letter-spacing: .22em; margin: 0 0 1rem; }
#tab-model .doc-card > h3::before { content: "— "; color: #1b17ff; }
#tab-model .doc-card p {
  font-family: var(--font-mono); font-size: .95rem; line-height: 1.72;
  color: #3a362c; max-width: 760px;
}
#tab-model .eq {
  background: transparent !important; border: 0 !important;
  border-left: 2px solid #1b17ff !important; border-radius: 0 !important;
  margin: 18px 0; padding: 2px 0 2px 20px;
}
#tab-model .katex { color: #17150f !important; }
#tab-model .katex .mord, #tab-model .katex .mbin, #tab-model .katex .mrel,
#tab-model .katex .mopen, #tab-model .katex .mclose, #tab-model .katex .mpunct { color: #17150f !important; }

#tab-model .tier-grid { max-width: 820px; margin: 1rem auto; gap: 22px; }
#tab-model .tier-card {
  background: transparent !important; box-shadow: none !important;
  border: 0 !important; border-top: 1px solid rgba(0,0,0,.13) !important;
  border-radius: 0 !important; padding: 14px 0 0;
}
#tab-model .tier-card h4 { font-size: .72rem; letter-spacing: .12em; }
#tab-model .tier-card.safe h4     { color: #3a9d6e; }
#tab-model .tier-card.alert h4    { color: #d6a51f; }
#tab-model .tier-card.critical h4 { color: #e8590c; }
#tab-model .tier-card.severe h4   { color: #cc2030; }
#tab-model .tier-card p { font-family: var(--font-mono); color: #6b655c; }
@media (max-width: 640px) { #tab-model .tier-grid { grid-template-columns: repeat(2, 1fr); } }
"""


def headers() -> List[Any]:
    """Return the <head> elements that apply the theme (after franken-ui)."""
    return [_FONTS, Style(_CSS)]
