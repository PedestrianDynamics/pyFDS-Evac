"""Manufactured smoke fields for SPEC 012 Tier A verification (fields F0-F4).

Each field is a lightweight "extinction sampler" exposing the duck-typed
``sample_extinction(time_s, x, y) -> float`` interface consumed by
``integrated_extinction_along_los`` and ``SmokeSpeedModel``'s extinction
field. No FDS dependency; values are exact and hand-computable so model
outputs can be checked against closed forms.

Fields
------
- F0 ``ZeroField``      : K = 0 everywhere (null case).
- F1 ``UniformField``   : K = k0 everywhere.
- F2 ``LinearField``    : K = a * x (linear ramp; mean along ray == midpoint).
- F3 ``BandField``      : K = k_hi inside [x_lo, x_hi], 0 outside.
- F4 ``TwoZoneField``   : K = 0 for x < x_split, k0 for x >= x_split.
"""


class ZeroField:
    """F0: zero extinction everywhere."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return 0.0 for any point and time."""
        del time_s, x, y
        return 0.0


class UniformField:
    """F1: constant extinction k0 everywhere."""

    def __init__(self, k0: float):
        """Store the uniform extinction coefficient k0 in 1/m."""
        self.k0 = float(k0)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return k0 for any point and time."""
        del time_s, x, y
        return self.k0


class LinearField:
    """F2: extinction ramps linearly with x as K = a * x."""

    def __init__(self, a: float):
        """Store the ramp slope a in 1/m per metre."""
        self.a = float(a)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return a * x, independent of y and time."""
        del time_s, y
        return self.a * x


class BandField:
    """F3: extinction k_hi inside a thin x-band, 0 elsewhere."""

    def __init__(self, k_hi: float, x_lo: float, x_hi: float):
        """Store the band height k_hi and its x extent [x_lo, x_hi]."""
        self.k_hi = float(k_hi)
        self.x_lo = float(x_lo)
        self.x_hi = float(x_hi)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return k_hi when x_lo <= x <= x_hi, else 0.0."""
        del time_s, y
        if self.x_lo <= x <= self.x_hi:
            return self.k_hi
        return 0.0


class TwoZoneField:
    """F4: clear left half (x < x_split), smoky right half (x >= x_split)."""

    def __init__(self, k0: float, x_split: float):
        """Store the right-zone extinction k0 and the split position x_split."""
        self.k0 = float(k0)
        self.x_split = float(x_split)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        """Return 0.0 for x < x_split, k0 for x >= x_split."""
        del time_s, y
        if x < self.x_split:
            return 0.0
        return self.k0
