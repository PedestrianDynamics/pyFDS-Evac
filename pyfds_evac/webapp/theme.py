"""Visual theme for the pyFDS-Evac GUI: "Warm Paper Lab".

A warm cream instrument panel in the spirit of anthropic.com: ivory paper
(#FAF9F5) ground, warm near-black ink, and a single clay/terracotta accent
(#CC785C). The FED tenability tiers (Safe/Alert/Critical/Severe) remain the
semantic colour system, harmonised to sit on cream and always paired with a
text label (colour is never the sole cue).

Retheming is done by overriding franken-ui's shadcn-style CSS variables on
<html>, so every component inherits the palette; the rest adds typography
(Archivo display, IBM Plex Mono labels, IBM Plex Sans body), chrome, a soft
paper texture, warm shadows, and load motion.
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

# Palette (sRGB hex, for reference):
#   ground   ivory   #FAF9F5   surface  cloud  #F4F2EA   ink   #141413
#   accent   clay    #CC785C   muted-ink       #75726A   line  #E4DECF
#   tiers  safe #3F8F57  alert #D19A2E  critical #D2722B  severe #C23B2E
_CSS = """
:root, html.uk-theme-blue {
  --background: 48 33% 97%;
  --foreground: 60 4% 9%;
  --card: 48 29% 95%;
  --card-foreground: 60 4% 9%;
  --popover: 48 33% 98%;
  --popover-foreground: 60 4% 9%;
  --primary: 16 52% 58%;
  --primary-foreground: 30 30% 12%;
  --secondary: 47 28% 90%;
  --secondary-foreground: 40 6% 16%;
  --muted: 47 28% 91%;
  --muted-foreground: 40 5% 42%;
  --accent: 22 48% 90%;
  --accent-foreground: 16 48% 34%;
  --destructive: 5 58% 49%;
  --destructive-foreground: 48 33% 97%;
  --border: 46 24% 84%;
  --input: 45 22% 80%;
  --ring: 16 52% 56%;
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
  --shadow-warm: 30 25% 22%;
}
html.uk-theme-blue { color-scheme: light; }

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
    linear-gradient(hsl(60 4% 9% / .035) 1px, transparent 1px),
    linear-gradient(90deg, hsl(60 4% 9% / .035) 1px, transparent 1px);
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
.uk-input { font-size: .82rem; background: hsl(48 36% 98%); }
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
    0 1px 0 hsl(0 0% 100% / .6) inset,
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
  background: hsl(48 30% 96%); color: hsl(var(--secondary-foreground));
  border: 1px solid hsl(var(--border));
}
.uk-btn-secondary:hover { border-color: hsl(var(--primary) / .6); color: var(--clay); }
.uk-btn-ghost:hover { background: hsl(var(--accent) / .7); color: hsl(16 48% 34%); }

/* ---- run panel: telemetry ---- */
.telemetry { font-family: var(--font-mono); letter-spacing: .02em; }
.report-line { font-family: var(--font-mono); font-size: .82rem; }
.report-line b { color: var(--clay); }

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
