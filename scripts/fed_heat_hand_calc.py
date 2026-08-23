"""Closed-form heat FED reference for the fed_incap_heat_* decks.

ISO TS 13571 eq. 5 gives the convective-heat tolerance time

    t_Iconv [min] = 5e7 * T ** -3.4          (T in degrees Celsius)

so the fractional dose accumulates at the reciprocal rate and, for a field
that does not change, reaches unity at exactly t_Iconv. The decks prescribe a
uniform temperature behind adiabatic boundaries precisely so that this is the
right reference to compare a coupled run against.

Run it to regenerate the table in docs/testing-heat.md:

    uv run python scripts/fed_heat_hand_calc.py

Radiant heat is a separate ISO term and is not modelled here, so these times
are an upper bound on tolerance in a real fire.
"""

from __future__ import annotations

import argparse

TEMPERATURES_C = (100.0, 150.0, 200.0)


def heat_fed_rate_per_minute(temperature_celsius: float) -> float:
    """Fractional heat dose accumulated per minute at a fixed temperature."""
    if temperature_celsius <= 0.0:
        return 0.0
    return (temperature_celsius**3.4) / 5e7


def time_to_dose_s(temperature_celsius: float, dose: float = 1.0) -> float:
    """Seconds to reach *dose* at a constant temperature."""
    rate = heat_fed_rate_per_minute(temperature_celsius)
    if rate <= 0.0:
        return float("inf")
    return 60.0 * dose / rate


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--temperatures",
        type=float,
        nargs="+",
        default=list(TEMPERATURES_C),
        help="gas temperatures in degrees Celsius",
    )
    args = ap.parse_args()

    print(f"{'T [C]':>7} {'rate [1/min]':>14} {'FED=0.3 [s]':>13} {'FED=1.0 [s]':>13}")
    for t in args.temperatures:
        print(
            f"{t:7.1f} {heat_fed_rate_per_minute(t):14.6f} "
            f"{time_to_dose_s(t, 0.3):13.2f} {time_to_dose_s(t, 1.0):13.2f}"
        )


if __name__ == "__main__":
    main()
