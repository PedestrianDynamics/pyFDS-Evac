"""Where the incident flux q sits between U/4 and U in the #224 decks.

The decks in ``assets/heat_radiometer`` put skin radiometers (FDS
``RADIOMETER GAS``, gauge at 35 C, emissivity 1) and ``INTEGRATED
INTENSITY`` devices at the same points, at z = 1.6 and 1.8 m, facing up
(``up``), sideways (``px`` = +x, ``mx`` = -x) and down (``dn``). FDS User's
Guide 6.10.1, Eq. 22.36 with emissivity 1:

    radiometer = q_inc - sigma T_gauge^4,

so q_inc = radiometer + sigma T_gauge^4. U = integral of I over all
directions. A flat plate gets q/U = 1/4 in an isotropic field, 1/2 facing
a uniform upper hemisphere with nothing below, and up to 1 facing a compact
source.

The table gives, per deck, height and orientation, the time mean over
t >= 1 s of q/U at each point (min, median and max over the points), and
the same for the part above the ambient field, (q - sigma Ta^4) /
(U - 4 sigma Ta^4), with Ta = 20 C.

Run from the repository root::

    python scripts/verification/heat_radiometer.py --data DIR

``DIR`` holds ``heat_radiometer_<case>_devc.csv`` for case in layer,
uniform, burner, in any subfolder. It defaults to the maintainer's sciebo
``fds-evac-data/heat_radiometer`` folder.
"""

import argparse
import csv
import re
from pathlib import Path

import numpy as np

SIGMA = 5.670374419e-8  # W m^-2 K^-4, CODATA 2018
T_GAUGE_C = 35.0  # GAUGE_TEMPERATURE of the decks
T_AMBIENT_C = 20.0  # TMPA of the decks
T_SETTLE = 1.0  # s; FDS writes the first radiation solution after t = 0
CASES = ("uniform", "layer", "burner")
FACES = ("up", "px", "mx", "dn")
DATA = Path(
    "/Users/chraibi/sciebo - ped23 (ped23.pbox@fz-juelich.de)"
    "@fz-juelich.sciebo.de/fds-evac-data/heat_radiometer"
)


def black_kw(t_c):
    """sigma T^4 in kW/m2 for T in C."""
    return SIGMA * (np.asarray(t_c) + 273.15) ** 4 / 1000.0


def flux_ratio(radiometer_kw, integrated_intensity_kw, gauge_temperature_c):
    """q/U: invert Eq. 22.36 (emissivity 1) for q_inc and divide by U."""
    q_inc = radiometer_kw + black_kw(gauge_temperature_c)
    return q_inc / integrated_intensity_kw


def excess_ratio(radiometer_kw, integrated_intensity_kw, gauge_temperature_c):
    """(q - sigma Ta^4) / (U - 4 sigma Ta^4): the share above ambient."""
    q_inc = radiometer_kw + black_kw(gauge_temperature_c)
    q_amb = black_kw(T_AMBIENT_C)
    return (q_inc - q_amb) / (integrated_intensity_kw - 4 * q_amb)


def read_devc(path):
    with path.open() as f:
        rows = list(csv.reader(f))
    ids = [c.strip().strip('"') for c in rows[1]]
    data = np.array([[float(x) for x in r] for r in rows[2:] if r])
    keep = data[:, 0] >= T_SETTLE
    return {k: data[keep, j] for j, k in enumerate(ids)}


def _columns(dev, prefix):
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    cols = [(int(m.group(1)), c) for c in dev if (m := pat.match(c))]
    return [c for _, c in sorted(cols)]


def summarize(dev):
    """Rows (height, face, q/U stats, excess stats) of one run."""
    rows = []
    for tag, z in (("z16", 1.6), ("z18", 1.8)):
        u_cols = _columns(dev, f"U_{tag}")
        for face in FACES:
            r_cols = _columns(dev, f"RAD_{tag}_{face}")
            ratio = [
                flux_ratio(dev[r], dev[u], T_GAUGE_C).mean()
                for r, u in zip(r_cols, u_cols, strict=True)
            ]
            excess = [
                excess_ratio(dev[r], dev[u], T_GAUGE_C).mean()
                for r, u in zip(r_cols, u_cols, strict=True)
            ]
            rows.append((z, face, np.array(ratio), np.array(excess)))
    return rows


def _stats(a):
    return f"{a.min():.3f} / {np.median(a):.3f} / {a.max():.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()
    print(
        "| case | z (m) | facing | q/U min / median / max | excess min / median / max |"
    )
    print("|---|---|---|---|---|")
    for case in CASES:
        found = sorted(args.data.rglob(f"heat_radiometer_{case}_devc.csv"))
        if not found:
            print(f"| {case} | | | no output under {args.data} | |")
            continue
        for z, face, ratio, excess in summarize(read_devc(found[0])):
            print(f"| {case} | {z} | {face} | {_stats(ratio)} | {_stats(excess)} |")


if __name__ == "__main__":
    main()
