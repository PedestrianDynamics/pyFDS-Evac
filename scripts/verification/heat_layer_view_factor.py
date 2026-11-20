"""Geometric view factor from a skin gauge to the base of the hot layer (#308).

The gauge is a differential element at the device position, facing up
(``up``), +x (``px``) or -x (``mx``). The layer base is the rectangle at
z = layer base over the room footprint. The view factor is the closed form
for a differential element and a rectangle (Howell, *A Catalog of Radiation
Heat Transfer Configurations*, https://www.thermalradiation.net, entries
C-11 and C-14; the same forms are in Incropera, *Fundamentals of Heat and
Mass Transfer*, Table 13.1 and Fig. 13.4), summed over the sub-rectangles
with a corner at the foot point of the element. It is a geometric
calculation; it is not fitted to FDS.

With c the distance of the element from the plane of the rectangle, X = a/c,
Y = b/c, rectangle sides a, b with a corner at the foot of the element:

- C-11, element parallel to the rectangle (``up``):
  F = 1/(2 pi) [ X/sqrt(1+X^2) atan(Y/sqrt(1+X^2))
               + Y/sqrt(1+Y^2) atan(X/sqrt(1+Y^2)) ]
- C-14, element perpendicular to the rectangle, its normal along side a
  (``px``, ``mx``), written with the side b as length scale (X' = a/b,
  Y' = c/b):
  F = 1/(2 pi) [ atan(1/Y') - Y'/sqrt(X'^2+Y'^2) atan(1/sqrt(X'^2+Y'^2)) ]

A part of the layer base behind the element (x on the far side of the
element plane for ``px`` / ``mx``) contributes zero.

Run from the repository root::

    python scripts/verification/heat_layer_view_factor.py

prints phi per gauge position and orientation and the predeclared flux.
"""

from __future__ import annotations

from math import atan, pi, sqrt

SIGMA = 5.670374419e-8  # W m^-2 K^-4, CODATA 2018
KELVIN = 273.15
ROOM_X_M = 4.0
ROOM_Y_M = 4.0
LAYER_BASE_M = 2.0  # deck: hot layer from 2.0 m
GAUGE_Z_M = 1.6
GAUGE_Y_M = 2.05
GAUGE_X_M = tuple(0.45 + 0.5 * k for k in range(7))
ORIENTATIONS = ("up", "px", "mx")
T_LAYER_C = 300.0  # deck: initial layer temperature
T_SKIN_C = 35.0
H_W_M2K = 8.0
EPS_L = 1.0


def _c11(a: float, b: float, c: float) -> float:
    x, y = a / c, b / c
    s1, s2 = sqrt(1 + x * x), sqrt(1 + y * y)
    return (x / s1 * atan(y / s1) + y / s2 * atan(x / s2)) / (2 * pi)


def _c14(a: float, b: float, c: float) -> float:
    """Normal along side a, rectangle sides a (from the foot) and b."""
    s = sqrt(a * a + c * c)
    return (atan(b / c) - c / s * atan(b / s)) / (2 * pi)


def view_factor(x_m: float, orientation: str) -> float:
    """Gauge at (x_m, GAUGE_Y_M, GAUGE_Z_M) to the layer base."""
    c = LAYER_BASE_M - GAUGE_Z_M
    if c <= 0:
        raise ValueError(f"gauge at z={GAUGE_Z_M} m is not below the layer base")
    xs = (x_m, ROOM_X_M - x_m)  # extents to the -x and +x walls
    ys = (GAUGE_Y_M, ROOM_Y_M - GAUGE_Y_M)
    if orientation == "up":
        return sum(_c11(a, b, c) for a in xs for b in ys)
    if orientation == "px":
        return sum(_c14(xs[1], b, c) for b in ys)
    if orientation == "mx":
        return sum(_c14(xs[0], b, c) for b in ys)
    raise ValueError(f"orientation must be one of {ORIENTATIONS}, got {orientation!r}")


def radiant_kw(
    t_layer_c: float, t_skin_c: float = T_SKIN_C, sigma: float = SIGMA
) -> float:
    return sigma * ((t_layer_c + KELVIN) ** 4 - (t_skin_c + KELVIN) ** 4) / 1000.0


def flux_kw(
    phi: float,
    t_gas_c: float,
    t_layer_c: float = T_LAYER_C,
    sigma: float = SIGMA,
) -> float:
    """q = h (T_g - T_s) / 1000 + phi eps_L sigma (T_L^4 - T_s^4) / 1000."""
    conv = H_W_M2K * (t_gas_c - T_SKIN_C) / 1000.0
    return conv + phi * EPS_L * radiant_kw(t_layer_c, sigma=sigma)


def main() -> None:
    print("x_m   " + "  ".join(f"phi_{o}" for o in ORIENTATIONS))
    for x in GAUGE_X_M:
        print(
            f"{x:.2f}  " + "  ".join(f"{view_factor(x, o):.4f}" for o in ORIENTATIONS)
        )


if __name__ == "__main__":
    main()
