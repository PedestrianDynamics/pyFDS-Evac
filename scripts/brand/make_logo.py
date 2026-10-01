"""Generate the pyFDS-Evac logo SVGs (standard library only).

Writes the full mark, the small mark (navbar, 32/48 px favicons), the
hand-set 16 px favicon glyph and the light/dark lockups.

The mark: a smoke field in the inferno colour map, clipped to a disc,
a wall with a door gap across its lower part, and agents (black
ellipses, white outline) crowding through the door. The wordmark is
Inter ExtraBold (SIL Open Font License) converted to outlines, so the
lockup does not depend on installed fonts.

Usage: python scripts/brand/make_logo.py [OUTPUT_DIR]
"""

import sys
from pathlib import Path

INK = "#1a1a1a"
RIM = "#ffffff"
RED = "#e4634a"
ORANGE = "#e8900a"
TEXT_LIGHT = "#111111"
TEXT_DARK = "#f3eee6"
# inferno colour map sampled at 0, 0.2, 0.4, 0.6, 0.8, 1
INFERNO = ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"]

# Agents traced from the hand-drawn draft (cx, cy, rx, ry, rotation),
# in draft pixels; the draft's smoke square spans x 52-962, y 97-1070.
AGENTS = [
    (147, 332, 58, 63, -15),
    (282, 322, 54, 72, 15),
    (512, 283, 58, 68, 22),
    (866, 280, 58, 52, -12),
    (734, 343, 55, 67, 28),
    (335, 466, 50, 61, 0),
    (458, 450, 51, 73, 8),
    (606, 418, 55, 78, 14),
    (727, 534, 60, 78, 8),
    (388, 620, 50, 81, 5),
    (578, 652, 56, 88, 10),
    (414, 828, 55, 85, 5),
    (563, 852, 58, 96, 0),
]
SX, SY = 1000 / 910, 1000 / 973
C, R = 500, 488  # disc centre and radius in the 1000-unit view box
K, CY, DY = 0.84, 470, 30  # pull the crowd towards the centre of the disc

# Small mark on a 32-unit grid: agents and a 10-unit door (x 11-21).
SMALL_AGENTS = [(8, 10), (15.5, 5.5), (22.5, 9.5), (12.5, 15), (16, 21), (15, 27.5)]

# "pyFDS-Evac" in Inter ExtraBold at 16 px, baseline at y = 0.
WORDMARK = "M0.9 3.27V-8.73H3.59V-7.23H3.69Q3.85 -7.63 4.17 -8Q4.48 -8.37 4.97 -8.61Q5.46 -8.84 6.16 -8.84Q7.08 -8.84 7.87 -8.36Q8.66 -7.88 9.15 -6.89Q9.64 -5.89 9.64 -4.36Q9.64 -2.88 9.17 -1.88Q8.7 -0.88 7.91 -0.38Q7.11 0.12 6.14 0.12Q5.48 0.12 4.99 -0.1Q4.5 -0.32 4.18 -0.67Q3.86 -1.02 3.69 -1.41H3.62V3.27ZM5.21 -2Q5.73 -2 6.1 -2.29Q6.46 -2.59 6.65 -3.12Q6.84 -3.66 6.84 -4.36Q6.84 -5.07 6.65 -5.6Q6.46 -6.12 6.1 -6.42Q5.74 -6.71 5.21 -6.71Q4.69 -6.71 4.32 -6.43Q3.95 -6.14 3.76 -5.61Q3.56 -5.09 3.56 -4.36Q3.56 -3.65 3.76 -3.12Q3.95 -2.59 4.32 -2.29Q4.7 -2 5.21 -2ZM11.08 3.06 11.69 1.07 12.03 1.16Q12.52 1.29 12.89 1.23Q13.27 1.18 13.46 0.96Q13.66 0.74 13.64 0.38L13.63 0.02L10.38 -8.73H13.25L14.55 -4.46Q14.82 -3.59 14.97 -2.7Q15.12 -1.82 15.34 -0.8H14.77Q14.98 -1.82 15.2 -2.71Q15.41 -3.6 15.68 -4.46L17.08 -8.73H19.92L16.26 0.92Q15.99 1.62 15.56 2.17Q15.13 2.71 14.46 3.02Q13.8 3.33 12.81 3.33Q12.31 3.33 11.85 3.25Q11.38 3.18 11.08 3.06ZM21 0V-11.64H28.91V-9.39H23.76V-6.44H28.41V-4.23H23.76V0ZM34.65 0H31.55V-2.36H34.53Q35.53 -2.36 36.22 -2.7Q36.91 -3.03 37.27 -3.8Q37.62 -4.56 37.62 -5.82Q37.62 -7.08 37.26 -7.84Q36.9 -8.6 36.21 -8.94Q35.52 -9.28 34.49 -9.28H31.5V-11.64H34.65Q36.42 -11.64 37.7 -10.94Q38.98 -10.24 39.68 -8.94Q40.38 -7.63 40.38 -5.82Q40.38 -4.01 39.68 -2.7Q38.99 -1.39 37.71 -0.7Q36.42 0 34.65 0ZM33.12 -11.64V0H30.37V-11.64ZM46.42 0.16Q44.97 0.16 43.89 -0.28Q42.81 -0.72 42.21 -1.61Q41.61 -2.5 41.59 -3.84H44.23Q44.27 -3.28 44.54 -2.9Q44.81 -2.52 45.29 -2.32Q45.76 -2.13 46.39 -2.13Q46.96 -2.13 47.38 -2.29Q47.79 -2.45 48.01 -2.73Q48.23 -3.01 48.23 -3.38Q48.23 -3.72 48.03 -3.95Q47.82 -4.19 47.41 -4.37Q46.99 -4.55 46.35 -4.69L45.12 -4.98Q43.61 -5.32 42.75 -6.1Q41.89 -6.88 41.89 -8.2Q41.89 -9.27 42.48 -10.09Q43.06 -10.9 44.08 -11.35Q45.1 -11.8 46.42 -11.8Q47.77 -11.8 48.77 -11.34Q49.76 -10.88 50.3 -10.07Q50.85 -9.25 50.87 -8.17H48.22Q48.16 -8.8 47.7 -9.16Q47.24 -9.51 46.41 -9.51Q45.87 -9.51 45.49 -9.36Q45.12 -9.22 44.93 -8.96Q44.74 -8.71 44.74 -8.38Q44.74 -8.02 44.95 -7.78Q45.16 -7.53 45.55 -7.37Q45.95 -7.2 46.46 -7.09L47.47 -6.85Q48.31 -6.67 48.97 -6.36Q49.63 -6.05 50.09 -5.62Q50.55 -5.2 50.79 -4.63Q51.02 -4.07 51.02 -3.38Q51.02 -2.27 50.47 -1.48Q49.92 -0.69 48.89 -0.27Q47.87 0.16 46.42 0.16ZM58.04 -5.77V-3.66H52.67V-5.77ZM60.03 0V-11.64H68.11V-9.39H62.79V-6.98H67.69V-4.78H62.79V-2.25H68.1V0ZM72.22 0 69.05 -8.73H71.93L73.23 -4.46Q73.5 -3.6 73.7 -2.7Q73.89 -1.8 74.09 -0.8H73.59Q73.79 -1.8 73.98 -2.7Q74.17 -3.59 74.43 -4.46L75.71 -8.73H78.55L75.38 0ZM82.07 0.16Q81.23 0.16 80.58 -0.13Q79.93 -0.41 79.56 -0.99Q79.2 -1.56 79.2 -2.42Q79.2 -3.15 79.45 -3.65Q79.7 -4.15 80.16 -4.46Q80.61 -4.77 81.2 -4.94Q81.78 -5.1 82.45 -5.16Q83.19 -5.22 83.64 -5.29Q84.09 -5.37 84.3 -5.52Q84.52 -5.66 84.52 -5.93V-5.96Q84.52 -6.27 84.38 -6.48Q84.23 -6.69 83.97 -6.8Q83.7 -6.91 83.33 -6.91Q82.95 -6.91 82.66 -6.8Q82.37 -6.69 82.18 -6.48Q81.99 -6.28 81.91 -6.01L79.45 -6.33Q79.62 -7.08 80.12 -7.64Q80.62 -8.21 81.44 -8.53Q82.26 -8.84 83.35 -8.84Q84.16 -8.84 84.87 -8.65Q85.58 -8.46 86.11 -8.09Q86.64 -7.72 86.94 -7.18Q87.23 -6.63 87.23 -5.93V0H84.67V-1.23H84.6Q84.37 -0.77 84 -0.47Q83.64 -0.16 83.16 -0Q82.68 0.16 82.07 0.16ZM82.9 -1.65Q83.36 -1.65 83.73 -1.84Q84.1 -2.02 84.32 -2.35Q84.54 -2.68 84.54 -3.11V-3.95Q84.42 -3.88 84.25 -3.83Q84.07 -3.77 83.86 -3.73Q83.65 -3.69 83.44 -3.65Q83.23 -3.62 83.03 -3.59Q82.63 -3.53 82.35 -3.4Q82.07 -3.27 81.92 -3.05Q81.77 -2.84 81.77 -2.55Q81.77 -2.26 81.92 -2.06Q82.07 -1.86 82.32 -1.75Q82.57 -1.65 82.9 -1.65ZM93.09 0.16Q91.73 0.16 90.74 -0.4Q89.76 -0.97 89.23 -1.98Q88.7 -2.99 88.7 -4.34Q88.7 -5.69 89.23 -6.7Q89.76 -7.71 90.74 -8.28Q91.73 -8.84 93.09 -8.84Q93.93 -8.84 94.62 -8.62Q95.32 -8.41 95.84 -8Q96.37 -7.6 96.69 -7.03Q97.02 -6.45 97.12 -5.74L94.6 -5.32Q94.54 -5.66 94.41 -5.93Q94.28 -6.2 94.1 -6.38Q93.91 -6.57 93.67 -6.66Q93.42 -6.76 93.12 -6.76Q92.6 -6.76 92.23 -6.47Q91.87 -6.19 91.68 -5.64Q91.48 -5.1 91.48 -4.35Q91.48 -3.6 91.68 -3.05Q91.87 -2.51 92.23 -2.21Q92.6 -1.92 93.12 -1.92Q93.43 -1.92 93.67 -2.02Q93.91 -2.12 94.11 -2.31Q94.3 -2.5 94.43 -2.78Q94.55 -3.05 94.61 -3.41L97.12 -3Q97.02 -2.27 96.7 -1.68Q96.38 -1.1 95.85 -0.69Q95.33 -0.27 94.63 -0.05Q93.93 0.16 93.09 0.16Z"
WORDMARK_WIDTH = 97.66


def _table(channel):
    return " ".join(
        f"{int(h[1 + 2 * channel : 3 + 2 * channel], 16) / 255:.3f}" for h in INFERNO
    )


def _square(x, y):
    return (x - 52) * SX, (y - 97) * SY


def _pull(x, y):
    return round(C + (x - C) * K, 1), round(CY + (y - CY) * K + DY, 1)


def full_mark():
    """Textured smoke disc with wall, door gap and agents (1000 x 1000)."""
    y0 = _pull(0, _square(0, 683)[1])[1]
    y1 = _pull(0, _square(0, 772)[1])[1]
    xl = _pull(_square(345, 0)[0], 0)[0]
    xr = _pull(_square(632, 0)[0], 0)[0]
    h = round(y1 - y0, 1)
    k = (SX + SY) / 2 * 0.9
    agents = ""
    for x, y, a, b, r in AGENTS:
        cx, cy = _pull(*_square(x, y))
        agents += (
            f'<ellipse cx="{cx}" cy="{cy}" rx="{round(a * k, 1)}" ry="{round(b * k, 1)}" '
            f'transform="rotate({r} {cx} {cy})"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000" role="img" aria-label="pyFDS-Evac">
<title>pyFDS-Evac</title>
<defs>
<linearGradient id="fm-g" x1="52" y1="97" x2="962" y2="1070" gradientUnits="userSpaceOnUse">
<stop offset="0" stop-color="#7c7c7c"/><stop offset=".45" stop-color="#acacac"/><stop offset="1" stop-color="#e6e6e6"/>
</linearGradient>
<filter id="fm-b" x="-1" y="-1" width="3" height="3"><feGaussianBlur stdDeviation="38"/></filter>
<filter id="fm-s" x="52" y="97" width="910" height="973" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
<feTurbulence type="fractalNoise" baseFrequency=".0055" numOctaves="4" seed="11" result="n"/>
<feColorMatrix in="n" values="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 0 1" result="g"/>
<feComposite in="SourceGraphic" in2="g" operator="arithmetic" k2="1" k3=".62" k4="-.22"/>
<feComponentTransfer>
<feFuncR type="table" tableValues="{_table(0)}"/>
<feFuncG type="table" tableValues="{_table(1)}"/>
<feFuncB type="table" tableValues="{_table(2)}"/>
</feComponentTransfer>
</filter>
<clipPath id="fm-c"><circle cx="{C}" cy="{C}" r="{R}"/></clipPath>
</defs>
<circle cx="{C}" cy="{C}" r="{R + 6}" fill="{RIM}"/>
<g clip-path="url(#fm-c)"><g transform="scale({SX:.5f} {SY:.5f}) translate(-52 -97)" filter="url(#fm-s)">
<rect x="52" y="97" width="910" height="973" fill="url(#fm-g)"/>
<g filter="url(#fm-b)">
<ellipse cx="190" cy="520" rx="95" ry="80" fill="#000"/>
<ellipse cx="110" cy="210" rx="80" ry="110" fill="#3a3a3a"/>
<ellipse cx="330" cy="150" rx="120" ry="60" fill="#444"/>
<ellipse cx="220" cy="950" rx="140" ry="90" fill="#555"/>
<ellipse cx="820" cy="170" rx="90" ry="60" fill="#8a8a8a"/>
<ellipse cx="800" cy="980" rx="170" ry="110" fill="#eee"/>
</g>
</g></g>
<g clip-path="url(#fm-c)"><g fill="{INK}" stroke="{RIM}" stroke-width="12">
<rect x="0" y="{y0}" width="{xl}" height="{h}"/><rect x="{xr}" y="{y0}" width="{1000 - xr}" height="{h}"/>
</g></g>
<g fill="{INK}" stroke="{RIM}" stroke-width="11">{agents}</g>
</svg>
"""


def _small_body(prefix):
    agents = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="2.5" ry="3.1"/>' for x, y in SMALL_AGENTS
    )
    return f"""<defs>
<linearGradient id="{prefix}-g" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
<stop offset=".42" stop-color="{RED}"/><stop offset=".42" stop-color="{ORANGE}"/>
</linearGradient>
<clipPath id="{prefix}-w"><circle cx="16" cy="16" r="14.8"/></clipPath>
</defs>
<circle cx="16" cy="16" r="16" fill="url(#{prefix}-g)"/>
<g clip-path="url(#{prefix}-w)" fill="{INK}"><rect x="0" y="19" width="11" height="4"/><rect x="21" y="19" width="11" height="4"/></g>
<g fill="{INK}">{agents}</g>"""


def small_mark():
    """Flat two-tone disc for 28-48 px: six agents, one in the door."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" role="img" aria-label="pyFDS-Evac">
<title>pyFDS-Evac</title>
{_small_body("sm")}
</svg>
"""


def favicon16():
    """Glyph on the 16 px grid: 2 px wall, 5 px door with a 3x3 agent, one agent above, one below."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
<defs><clipPath id="f16-c"><circle cx="8" cy="8" r="8"/></clipPath></defs>
<g clip-path="url(#f16-c)">
<rect width="16" height="16" fill="{ORANGE}"/>
<path d="M0 0H10V1H9V2H8V3H7V4H6V5H5V6H4V7H3V8H2V9H1V10H0Z" fill="{RED}"/>
<g fill="{INK}" shape-rendering="crispEdges"><rect x="1" y="10" width="5" height="2"/><rect x="11" y="10" width="4" height="2"/>
<rect x="7" y="9" width="3" height="3"/><rect x="5" y="3" width="3" height="3"/><rect x="7" y="13" width="3" height="2"/></g>
</g>
</svg>
"""


def lockup(dark):
    """Small mark plus the outlined wordmark, 8 units apart as in the site navbar."""
    width = round(40 + WORDMARK_WIDTH + 2)
    fill = TEXT_DARK if dark else TEXT_LIGHT
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 32" width="{width}" height="32" role="img" aria-label="pyFDS-Evac">
<title>pyFDS-Evac</title>
{_small_body("lk")}
<path transform="translate(40 22)" fill="{fill}" d="{WORDMARK}"/>
</svg>
"""


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "logo-full.svg": full_mark(),
        "logo-mark.svg": small_mark(),
        "favicon-16.svg": favicon16(),
        "lockup.svg": lockup(False),
        "lockup-dark.svg": lockup(True),
    }
    for name, src in files.items():
        (out / name).write_text(src)
        print(f"{name}: {len(src.encode())} bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site/static/images/brand"))
