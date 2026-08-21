"""Visual theme for the pyFDS-Evac GUI: an "Instrument" UI with a fire palette.

Two grounds share one ink system and one heat ramp:

* **dark** (default) — smoky warm-grey ground, warm off-white ink.
* **light** — warm paper, which is the look the Model tab already used, so
  the two tabs stop disagreeing with each other when light is selected.

The heat ramp (gold -> amber -> orange -> crimson) is deliberately *identical*
in both. It encodes tenability tiers, so it is data rather than chrome, and a
screenshot taken in one theme has to stay comparable with one taken in the
other. Everything else is expressed as a token and redefined under
``html[data-theme="light"]``.

The selected theme is stored in ``localStorage`` under ``pyfds-theme``, and
falls back to the reader's OS preference while no choice has been made.
:func:`boot_script` resolves it before first paint so a light-mode reader
never sees a dark flash.

All class names the app emits are preserved; only the visual values change.
"""

from __future__ import annotations

from typing import Any, List

from fasthtml.common import Button, Div, Link, NotStr, Script, Span, Style

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
/* ------------------------------------------------------------------ */
/*  Tokens.                                                            */
/*                                                                     */
/*  Two grounds, one ink system, one heat ramp.  The heat ramp is the  */
/*  only part that does NOT flip between themes: gold/amber/orange/    */
/*  crimson encode tenability tiers, so they are data, not chrome, and */
/*  a reader must be able to compare a screenshot of one theme against */
/*  a screenshot of the other.  Everything below the ramp is chrome    */
/*  and is redefined for light.                                        */
/*                                                                     */
/*  Anything with a literal colour in a rule further down is a bug     */
/*  waiting for the next theme: put it here instead.                   */
/* ------------------------------------------------------------------ */
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

  /* heat ramp — identical in both themes, see note above */
  --ember:  #ff6a1a;
  --gold:   #f4c430;
  --tier-safe:     #f4c430;
  --tier-alert:    #ffb020;
  --tier-critical: #ff6a1a;
  --tier-severe:   #e01e37;

  /* surfaces */
  --surface-page:    #211e20;
  --surface-card:    #2a262a;
  --surface-panel:   #14161b;
  --surface-input:   #2e2a2e;
  --surface-raised:  #3a343a;
  --surface-accent:  #322e32;
  --surface-sunken:  #211e21;
  --surface-canvas:  #1c191c;
  --surface-tooltip: #0d0c0e;
  --tooltip-ink:     #f2ede9;

  /* the console keeps a dark ground in both themes: it is terminal
     output, and inverting it makes streamed FDS logs harder to scan */
  --surface-console: #131113;
  --ink-console:     #d7cfca;

  /* ink */
  --ink:       #f2ede9;
  --ink-dim:   #b2a9a3;
  --ink-faint: #837a74;

  /* hairlines, from softest to strongest */
  --hairline-soft:   rgba(255,255,255,.04);
  --hairline:        rgba(255,255,255,.07);
  --hairline-strong: rgba(255,255,255,.10);
  --hairline-badge:  rgba(255,255,255,.18);

  /* ink that sits on top of a heat-ramp fill */
  --on-heat: #2a1606;

  /* active tab pill inverts the ground */
  --pill-active-bg: #f2ede9;
  --pill-active-fg: #211e20;

  /* the two warm washes behind the page */
  --glow-warm: rgba(255,90,31,.10);
  --glow-gold: rgba(244,196,48,.06);

  --shadow-sm:  0 1px 3px rgba(0,0,0,.4),  0 1px 2px rgba(0,0,0,.3);
  --shadow-md:  0 8px 24px rgba(0,0,0,.45), 0 2px 6px rgba(0,0,0,.3);
  --shadow-lg:  0 18px 50px rgba(0,0,0,.55), 0 4px 12px rgba(0,0,0,.35);
}
html.uk-theme-blue { color-scheme: dark; }

/* ---- light ground: warm paper, matching the Model tab's reference look --- */
html[data-theme="light"] {
  color-scheme: light;

  --background: 36 30% 97%;
  --foreground: 24 14% 13%;
  --card: 0 0% 100%;
  --card-foreground: 24 14% 13%;
  --popover: 0 0% 100%;
  --popover-foreground: 24 14% 13%;
  --primary: 22 100% 45%;
  --primary-foreground: 0 0% 100%;
  --secondary: 32 20% 92%;
  --secondary-foreground: 24 14% 20%;
  --muted: 32 20% 92%;
  --muted-foreground: 25 8% 40%;
  --accent: 38 90% 92%;
  --accent-foreground: 22 80% 32%;
  --destructive: 350 72% 45%;
  --destructive-foreground: 0 0% 100%;
  --border: 30 12% 84%;
  --input: 0 0% 100%;
  --ring: 22 90% 48%;

  --surface-page:    #faf7f2;
  --surface-card:    #fffdfa;
  --surface-panel:   #ffffff;
  --surface-input:   #ffffff;
  --surface-raised:  #efe9e0;
  --surface-accent:  #f4efe7;
  --surface-sunken:  #f4efe7;
  --surface-canvas:  #f3eee6;
  --surface-tooltip: #2a262a;
  --tooltip-ink:     #f2ede9;

  --ink:       #241f1c;
  --ink-dim:   #5c534c;
  --ink-faint: #857b72;

  --hairline-soft:   rgba(31,23,16,.045);
  --hairline:        rgba(31,23,16,.10);
  --hairline-strong: rgba(31,23,16,.15);
  --hairline-badge:  rgba(31,23,16,.24);

  --pill-active-bg: #241f1c;
  --pill-active-fg: #faf7f2;

  --glow-warm: rgba(255,106,26,.07);
  --glow-gold: rgba(244,196,48,.10);

  --shadow-sm:  0 1px 2px rgba(60,45,30,.07);
  --shadow-md:  0 6px 18px rgba(60,45,30,.09), 0 1px 3px rgba(60,45,30,.06);
  --shadow-lg:  0 16px 40px rgba(60,45,30,.13), 0 3px 8px rgba(60,45,30,.07);
}

/* On light, a flat gold fill under near-black text is louder than the
   design wants for a *secondary* control, so the ramp is used as an
   outline there instead of a fill.  Primary actions keep the fill. */
html[data-theme="light"] .mode-btn.active { background: var(--gold); color: var(--on-heat); }

html, body { background: var(--surface-page); }
body {
  font-family: var(--font-sans);
  color: hsl(var(--foreground));
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
  background:
    radial-gradient(120% 80% at 85% -10%, var(--glow-warm), transparent 55%),
    radial-gradient(90% 70% at 5% 0%,     var(--glow-gold), transparent 50%),
    var(--surface-page);
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
  background: var(--surface-input);
  color: hsl(var(--foreground));
  border: 1px solid var(--hairline-strong);
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
  border: 1px solid var(--hairline-badge); color: hsl(var(--muted-foreground));
  font-size: .58rem; font-weight: 700; cursor: pointer;
  transition: color .12s, border-color .12s; user-select: none;
}
.lblwrap { display: flex; flex-direction: column; gap: 6px; }
.lblwrap.open .help-badge { color: var(--gold); border-color: var(--gold); }
.badge-tip {
  display: none;
  background: var(--surface-tooltip); color: var(--ink);
  font-size: .72rem; font-weight: 400; line-height: 1.5;
  text-transform: none; letter-spacing: normal;
  padding: .5rem .65rem; border-radius: .5rem; border: 1px solid var(--hairline-badge);
  white-space: normal; box-shadow: var(--shadow-md);
}
.lblwrap.open .badge-tip { display: block; }

/* run button running-state */
.run-btn:disabled { cursor: progress; filter: saturate(.5) brightness(.92); opacity: .9; }
.run-btn:disabled .run-btn-icon { animation: pulse 1.3s ease-in-out infinite; }
.results-btn:hover:not(:disabled) { background: rgba(244,196,48,.10); }

/* ---- scenario upload (sits under the picker, inside Core) ---- */
.upload-block {
  display: flex; flex-direction: column; gap: 8px;
  border-top: 1px dashed var(--hairline-strong); margin-top: 4px; padding-top: 11px;
}
.upload-title {
  font-family: 'Space Grotesk', sans-serif; font-size: 10.5px; font-weight: 500;
  letter-spacing: .07em; text-transform: uppercase; color: var(--ink-faint);
}
.upload-name {
  background: var(--surface-input); border: 1px solid var(--hairline); border-radius: 9px;
  padding: 9px 11px; color: var(--ink); font-family: 'JetBrains Mono', monospace;
  font-size: 12px; outline: none; width: 100%; box-sizing: border-box;
}
.upload-drop {
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 16px 12px; cursor: pointer; text-align: center;
  border: 1px dashed var(--hairline-badge); border-radius: 10px;
  background: var(--surface-sunken); transition: border-color .12s, background .12s;
}
.upload-drop:hover, .upload-drop.over {
  border-color: var(--gold); background: rgba(244,196,48,.06);
}
.upload-drop-title {
  font-family: 'Space Grotesk', sans-serif; font-size: 12px; color: var(--ink);
}
.upload-drop-sub, .upload-hint {
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: var(--ink-faint);
  line-height: 1.5;
}
.upload-picked {
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: var(--gold);
  word-break: break-all;
}
.upload-picked:empty { display: none; }
.upload-btn {
  display: flex; align-items: center; justify-content: center; gap: .35rem;
  width: 100%; padding: 9px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--hairline-strong); background: var(--surface-raised); color: var(--ink);
  font-family: 'Space Grotesk', sans-serif; font-size: 12.5px; font-weight: 500;
}
.upload-btn:hover { border-color: var(--gold); color: var(--gold); }
.upload-busy { display: none; }
.upload-busy.htmx-request { display: inline; animation: pulse 1.3s ease-in-out infinite; }

/* ---- header ---- */
.app-header {
  display: flex; align-items: center; justify-content: center;
  padding: 1rem 2rem;
  background: color-mix(in srgb, var(--surface-page) 78%, transparent);
  backdrop-filter: saturate(150%) blur(18px);
  -webkit-backdrop-filter: saturate(150%) blur(18px);
  border-bottom: 1px solid var(--hairline);
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

@media (max-width: 420px) { .tier-row { grid-template-columns: repeat(2, 1fr); row-gap: .75rem; } }
@keyframes pulse {
  0%   { box-shadow: 0 0 0 0   rgba(255,90,31,.5); }
  70%  { box-shadow: 0 0 0 7px rgba(255,90,31,0);  }
  100% { box-shadow: 0 0 0 0   rgba(255,90,31,0);  }
}

/* ---- cards ---- */
.uk-card {
  background: var(--surface-card);
  border: 1px solid var(--hairline);
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
  background: var(--surface-accent) !important;
  color: hsl(var(--foreground)) !important;
  font-family: var(--font-display) !important;
  font-weight: 600; font-size: .95rem !important; letter-spacing: -.01em;
  padding: .7rem 1rem; border-radius: .7rem;
  border: 1px solid var(--hairline); border-left: 2px solid var(--ember);
  transition: border-color .15s, background .15s;
}
.uk-accordion-title:hover { background: var(--surface-raised) !important; }
.uk-open > .uk-accordion-title { border-left-color: var(--gold); background: var(--surface-raised) !important; }

/* ---- buttons ---- */
.uk-btn {
  font-family: var(--font-display); font-weight: 600; font-size: .875rem;
  letter-spacing: -.005em; border-radius: .65rem;
  transition: filter .12s, box-shadow .15s, transform .06s;
}
.uk-btn:active { transform: scale(.98); }
.uk-btn-primary {
  background: linear-gradient(180deg, #ffc24d, #e8590c);
  color: var(--on-heat);
  box-shadow: 0 6px 20px rgba(232,89,12,.3);
}
.uk-btn-primary:hover { filter: brightness(1.06); box-shadow: 0 8px 26px rgba(232,89,12,.4); }
.uk-btn-secondary {
  background: var(--surface-raised); color: hsl(var(--foreground));
  border: 1px solid var(--hairline-strong);
}
.uk-btn-secondary:hover { border-color: var(--gold); color: var(--gold); }
.uk-btn-ghost:hover { background: var(--surface-raised); color: var(--gold); }

/* ---- incapacitation mode toggle ---- */
.mode-toggle {
  display: flex; max-width: 17rem;
  background: var(--surface-input); border: 1px solid var(--hairline-strong);
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
.mode-btn.active { background: var(--gold); color: var(--on-heat); box-shadow: var(--shadow-sm); }
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
  gap: 1rem; padding: .45rem 0; border-bottom: 1px solid var(--hairline);
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
  background: var(--hairline-soft); border-radius: .7rem; border: 1px solid var(--hairline);
}
.tab-btn {
  font-family: var(--font-display);
  font-size: .82rem; font-weight: 500; letter-spacing: -.012em;
  padding: .4rem 1.1rem; background: transparent; border: 0;
  border-radius: .55rem; color: hsl(var(--muted-foreground));
  cursor: pointer; transition: background .15s, color .15s, box-shadow .15s;
}
.tab-btn:hover:not(.active) { color: hsl(var(--foreground)); background: var(--hairline-soft); }
.tab-btn.active { background: var(--pill-active-bg); color: var(--pill-active-fg); box-shadow: var(--shadow-sm); }

/* ---- trajectory canvas ---- */
.traj-wrap { margin-top: .6rem; }
.traj-canvas {
  width: 100%; height: 460px; display: block;
  border: 1px solid var(--hairline-strong); border-radius: .9rem; background: var(--surface-canvas);
}
.traj-controls { display: flex; align-items: center; gap: .8rem; margin-top: .7rem; }
.traj-play {
  width: 2.2rem; height: 2.2rem; flex: none; border-radius: 99px;
  border: 1px solid var(--hairline-strong); background: var(--surface-accent);
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
  border: 1px solid var(--hairline-strong); border-radius: .45rem;
  background: var(--surface-input); color: hsl(var(--muted-foreground));
  transition: border-color .12s, color .12s, background .12s;
}
.cmode.active { border-color: var(--ember); color: var(--ember); background: rgba(255,106,26,.12); }
.speed-custom {
  width: 4.2rem; font-family: var(--font-mono); font-size: .68rem;
  padding: .28rem .5rem; border: 1px solid var(--hairline-strong); border-radius: .45rem;
  background: var(--surface-input); color: hsl(var(--foreground));
}
.speed-custom.active { border-color: var(--ember); box-shadow: 0 0 0 1px var(--ember) inset; }
.speed-custom::-webkit-inner-spin-button, .speed-custom::-webkit-outer-spin-button { margin-left: .2rem; }

/* ---- console ---- */
.console-box {
  max-height: 20rem; overflow: auto;
  background: var(--surface-console) !important; border: 1px solid var(--hairline);
  border-radius: .9rem; padding: .9rem 1.1rem;
}
.console-box pre {
  font-family: var(--font-mono); font-size: .75rem; line-height: 1.7;
  color: var(--ink-console) !important; background: transparent !important;
  border: 0 !important; padding: 0 !important; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}

/* ---- standby ---- */
.standby { min-height: 58vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1.1rem; text-align: center; }
.standby-hint { font-size: .85rem; line-height: 1.7; color: hsl(var(--muted-foreground)); max-width: 40ch; }

/* ---- utility ---- */
.hidden { display: none !important; }

/* ---- number input spinners ---- */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  appearance: none;
  background: var(--surface-raised);
  border-left: 1px solid var(--hairline);
  border-radius: 0 9px 9px 0;
  opacity: 1;
  cursor: pointer;
  width: 22px;
}
input[type="number"] { -moz-appearance: textfield; }

/* ---- scrollbar ---- */
* { scrollbar-width: thin; scrollbar-color: var(--hairline-badge) transparent; }
*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-thumb { background: var(--hairline-badge); border-radius: 99px; }
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
@media (prefers-reduced-motion: reduce) { .rise { animation: none; } }


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

/* =================================================================== */
/*  Theme switch — page footer                                          */
/* =================================================================== */
.theme-foot {
  display: flex; align-items: center; justify-content: center; gap: .75rem;
  padding: 0 26px 34px; margin: 0 auto; max-width: 1480px;
}
.theme-foot::before, .theme-foot::after {
  content: ""; flex: 1; height: 1px; background: var(--hairline);
}
.theme-switch {
  display: inline-flex; align-items: center; gap: 2px; flex: none;
  padding: 3px; border-radius: 99px;
  background: var(--surface-input);
  border: 1px solid var(--hairline-strong);
  box-shadow: var(--shadow-sm);
}
.theme-opt {
  display: inline-flex; align-items: center; gap: .4rem;
  padding: .34rem .8rem; border: 0; border-radius: 99px; cursor: pointer;
  background: transparent; color: var(--ink-faint);
  font-family: var(--font-display); font-size: .74rem; font-weight: 500;
  letter-spacing: -.005em; line-height: 1;
  transition: color .15s, background .15s;
}
.theme-opt:hover { color: var(--ink); }
.theme-opt svg { width: 13px; height: 13px; display: block; }
/* The selected side carries the ramp, so the control reads as part of the
   fire palette rather than as a generic OS switch. */
.theme-opt[aria-pressed="true"] {
  background: var(--gold); color: var(--on-heat);
  box-shadow: var(--shadow-sm);
}
.theme-opt[aria-pressed="true"]:hover { color: var(--on-heat); }
.theme-foot-note {
  flex: none; font-family: var(--font-mono); font-size: .62rem;
  letter-spacing: .04em; text-transform: uppercase; color: var(--ink-faint);
}

/* Suppress transitions during the flip so 40-odd panels do not each run
   their own colour animation at slightly different speeds. */
html.theme-switching, html.theme-switching * {
  transition: none !important; animation: none !important;
}
"""

# Applied before first paint, so a light-mode reader never sees a dark
# flash.  Inlined in <head> rather than deferred for exactly that reason.
_THEME_BOOT_JS = """
(function () {
  try {
    var saved = localStorage.getItem('pyfds-theme');
    var mode = saved
      || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    if (mode === 'light') document.documentElement.setAttribute('data-theme', 'light');
  } catch (e) { /* private mode: fall through to dark */ }
})();
"""

# Wired up after the footer exists.  Also re-styles the Plotly figures and
# the trajectory canvas, neither of which is reachable from CSS.
_THEME_JS = """
(function () {
  var root = document.documentElement;

  function current() {
    return root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function paintButtons() {
    var mode = current();
    document.querySelectorAll('.theme-opt').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
    });
  }

  // Plotly bakes its font and grid colours into the figure at render time,
  // so a CSS variable cannot reach them; restyle every plot in place.
  function repaintPlots() {
    if (!window.Plotly) return;
    var css = getComputedStyle(root);
    var ink = css.getPropertyValue('--ink-dim').trim();
    var line = current() === 'light' ? 'rgba(31,23,16,.13)' : 'rgba(255,255,255,.10)';
    document.querySelectorAll('.js-plotly-plot').forEach(function (gd) {
      try {
        window.Plotly.relayout(gd, {
          'font.color': ink,
          'xaxis.gridcolor': line, 'yaxis.gridcolor': line,
          'xaxis.linecolor': line, 'yaxis.linecolor': line,
          'xaxis.zerolinecolor': line, 'yaxis.zerolinecolor': line,
          'legend.font.color': ink
        });
      } catch (e) { /* figure not ready yet */ }
    });
  }

  function apply(mode, persist) {
    root.classList.add('theme-switching');
    if (mode === 'light') root.setAttribute('data-theme', 'light');
    else root.removeAttribute('data-theme');
    if (persist) {
      try { localStorage.setItem('pyfds-theme', mode); } catch (e) {}
    }
    paintButtons();
    repaintPlots();
    // The trajectory canvas paints from CSS variables it read at draw time.
    if (typeof window.trajRepaint === 'function') { try { window.trajRepaint(); } catch (e) {} }
    if (typeof window.drawIncapDist === 'function') { try { window.drawIncapDist(); } catch (e) {} }
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { root.classList.remove('theme-switching'); });
    });
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.theme-opt');
    if (!btn) return;
    apply(btn.dataset.mode, true);
  });

  // Follow the OS only while the reader has not made a choice of their own.
  var mq = window.matchMedia('(prefers-color-scheme: light)');
  var onSystem = function (e) {
    var saved = null;
    try { saved = localStorage.getItem('pyfds-theme'); } catch (err) {}
    if (!saved) apply(e.matches ? 'light' : 'dark', false);
  };
  if (mq.addEventListener) mq.addEventListener('change', onSystem);
  else if (mq.addListener) mq.addListener(onSystem);

  paintButtons();
  // Plotly figures arrive with the results panel, well after this runs.
  document.body.addEventListener('htmx:afterSwap', function () {
    window.setTimeout(repaintPlots, 0);
  });
  window.setTimeout(repaintPlots, 0);
})();
"""

_SUN = NotStr(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="4.2"/>'
    '<path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22'
    'M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M19.1 4.9l-1.7 1.7M6.6 17.4l-1.7 1.7"/>'
    "</svg>"
)
_MOON = NotStr(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a6.8 6.8 0 0 0 10.7 10.7Z"/>'
    "</svg>"
)


def boot_script() -> Any:
    """Pre-paint theme resolution. Must go in <head>, before any body CSS."""
    return Script(_THEME_BOOT_JS)


def switch() -> Any:
    """The light/dark control that sits at the foot of the page."""
    return Div(
        Div(
            Button(
                _MOON,
                Span("Dark"),
                cls="theme-opt",
                data_mode="dark",
                type="button",
                aria_pressed="true",
                title="Use the dark instrument theme",
            ),
            Button(
                _SUN,
                Span("Light"),
                cls="theme-opt",
                data_mode="light",
                type="button",
                aria_pressed="false",
                title="Use the light warm-paper theme",
            ),
            cls="theme-switch",
            role="group",
            aria_label="Colour theme",
        ),
        Span("appearance", cls="theme-foot-note"),
        cls="theme-foot",
    )


def script() -> Any:
    """Behaviour for :func:`switch`. Emit once, after the footer."""
    return Script(_THEME_JS)


def headers() -> List[Any]:
    """Return the <head> elements that apply the theme (after franken-ui)."""
    return [_FONTS, Style(_CSS), boot_script()]
