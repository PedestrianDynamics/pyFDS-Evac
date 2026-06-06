"""Visual theme for the pyFDS-Evac GUI: "Thermal Control Room".

A dark charcoal instrument panel. Ember-orange is the primary accent and the
FED tenability tiers (Safe/Alert/Critical/Severe) are the semantic colour
system. Retheming is done by overriding franken-ui's shadcn-style CSS
variables on <html>, so every component inherits the palette; the rest adds
typography (Archivo display, IBM Plex Mono telemetry, IBM Plex Sans body),
chrome, texture, and load motion.
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

_CSS = """
:root, html.uk-theme-blue {
  --background: 222 16% 5%;
  --foreground: 42 22% 88%;
  --card: 220 14% 8%;
  --card-foreground: 42 22% 88%;
  --popover: 220 16% 7%;
  --popover-foreground: 42 22% 88%;
  --primary: 28 96% 54%;
  --primary-foreground: 28 70% 7%;
  --secondary: 220 12% 14%;
  --secondary-foreground: 42 18% 86%;
  --muted: 220 12% 12%;
  --muted-foreground: 215 9% 58%;
  --accent: 26 88% 14%;
  --accent-foreground: 30 96% 72%;
  --destructive: 4 84% 57%;
  --destructive-foreground: 0 0% 98%;
  --border: 218 13% 15%;
  --input: 218 13% 19%;
  --ring: 28 96% 54%;
  --radius: .5rem;

  --font-display: 'Archivo', system-ui, sans-serif;
  --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;

  --ember: #fb8b1e;
  --tier-safe: #46c463;
  --tier-alert: #e8c14a;
  --tier-critical: #fb8b1e;
  --tier-severe: #f0473b;
}
html.uk-theme-blue { color-scheme: dark; }

html, body { background: hsl(var(--background)); }
body {
  font-family: var(--font-sans);
  color: hsl(var(--foreground));
  background:
    radial-gradient(1200px 520px at 78% -160px, hsl(28 96% 52% / .14), transparent 62%),
    radial-gradient(900px 520px at -5% -8%, hsl(4 78% 42% / .10), transparent 56%),
    hsl(var(--background));
  background-attachment: fixed;
  min-height: 100vh;
}
/* atmosphere: faint engineering grid + film grain */
body::before {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    linear-gradient(hsl(42 22% 88% / .025) 1px, transparent 1px),
    linear-gradient(90deg, hsl(42 22% 88% / .025) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(120% 90% at 50% 0%, #000 35%, transparent 100%);
}
body::after {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  opacity: .04; mix-blend-mode: overlay;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
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
.uk-input, .uk-select, input, .uk-toggle-switch + * { font-family: var(--font-mono); }
.uk-input { font-size: .82rem; }
.uk-input::placeholder { color: hsl(var(--muted-foreground) / .6); }
::selection { background: hsl(28 96% 54% / .28); color: #fff; }

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
  text-shadow: 0 0 26px hsl(28 96% 54% / .25);
}
.brand b { color: var(--ember); font-weight: 700; }
.brand .tick { color: hsl(var(--muted-foreground)); font-weight: 500; }
.status {
  display: inline-flex; align-items: center; gap: .45rem;
  font-family: var(--font-mono); font-size: .6rem; letter-spacing: .22em;
  text-transform: uppercase; color: hsl(var(--muted-foreground));
  padding: .15rem .55rem; border: 1px solid hsl(var(--border)); border-radius: 99px;
}
.status .dot {
  width: 7px; height: 7px; border-radius: 99px; background: var(--tier-safe);
  box-shadow: 0 0 0 0 hsl(140 50% 52% / .6); animation: pulse 2.4s infinite;
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 hsl(140 50% 52% / .55); }
  70% { box-shadow: 0 0 0 7px hsl(140 50% 52% / 0); }
  100% { box-shadow: 0 0 0 0 hsl(140 50% 52% / 0); }
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
  box-shadow: 0 0 9px -1px currentColor;
}
.tier.safe .sw { background: var(--tier-safe); color: var(--tier-safe); }
.tier.alert .sw { background: var(--tier-alert); color: var(--tier-alert); }
.tier.critical .sw { background: var(--tier-critical); color: var(--tier-critical); }
.tier.severe .sw { background: var(--tier-severe); color: var(--tier-severe); }

/* ---- cards / surfaces ---- */
.uk-card {
  background: hsl(var(--card) / .72);
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius);
  backdrop-filter: blur(8px) saturate(1.1);
  box-shadow: 0 1px 0 hsl(42 22% 88% / .03) inset, 0 24px 60px -36px #000;
}
.uk-card-title, .uk-card h3 {
  font-family: var(--font-display); font-weight: 600; letter-spacing: -.01em;
}

/* ---- accordion as instrument modules ---- */
.uk-accordion-title {
  background: hsl(var(--secondary) / .5) !important;
  color: hsl(var(--foreground)) !important;
  font-family: var(--font-mono) !important;
  text-transform: uppercase; letter-spacing: .14em; font-size: .68rem; font-weight: 600;
  padding: .62rem .8rem; border-radius: .4rem;
  border: 1px solid hsl(var(--border)); border-left: 2px solid hsl(var(--primary));
  transition: border-color .2s, background .2s;
}
.uk-accordion-title:hover { background: hsl(var(--accent) / .35) !important; }
.uk-open > .uk-accordion-title { border-left-color: var(--ember); }

/* ---- buttons ---- */
.uk-btn {
  font-family: var(--font-mono); text-transform: uppercase;
  letter-spacing: .12em; font-weight: 500; font-size: .7rem;
  border-radius: .4rem; transition: filter .15s, box-shadow .2s, transform .05s;
}
.uk-btn:active { transform: translateY(1px); }
.uk-btn-primary {
  background: linear-gradient(180deg, hsl(30 98% 58%), hsl(26 95% 50%));
  color: hsl(var(--primary-foreground));
  box-shadow: 0 0 0 1px hsl(28 96% 54% / .35), 0 10px 30px -12px hsl(28 96% 54% / .7);
}
.uk-btn-primary:hover {
  filter: brightness(1.07);
  box-shadow: 0 0 0 1px hsl(28 96% 60% / .5), 0 0 26px -2px hsl(28 96% 54% / .65);
}
.uk-btn-secondary {
  background: hsl(var(--secondary) / .7); color: hsl(var(--secondary-foreground));
  border: 1px solid hsl(var(--border));
}
.uk-btn-secondary:hover { border-color: hsl(var(--primary) / .6); color: var(--ember); }
.uk-btn-ghost:hover { background: hsl(var(--accent) / .4); color: var(--ember); }

/* ---- run panel: telemetry ---- */
.telemetry { font-family: var(--font-mono); letter-spacing: .02em; }
.report-line { font-family: var(--font-mono); font-size: .82rem; }
.report-line b { color: var(--ember); }

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
  width: 7px; height: 7px; border-radius: 99px; background: var(--ember);
  box-shadow: 0 0 12px 1px hsl(28 96% 54% / .7); animation: pulse 2.4s infinite;
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
@media (prefers-reduced-motion: reduce) { .rise, .status .dot { animation: none; } }
"""


def headers() -> List[Any]:
    """Return the <head> elements that apply the theme (after franken-ui)."""
    return [_FONTS, Style(_CSS)]
