"""Measure the smoke contrast between the near and far route of l_corridor.

The asset exists to give a smoke-aware router a *reason* to take the long way
round: the near route (junction -> exit A, ~11 m) must be measurably smokier
than the far route (junction -> up the leg -> exit B, ~58 m) for long enough
that a route decision taken anywhere in that window flips.

The shared prefix -- the junction square itself, x in [10, 13] -- is excluded
from both polylines on purpose.  It is common to both routes, so its
extinction enters both costs identically and cannot discriminate between them;
including it would make the far route's *worst* K equal the near route's by
construction, hiding a contrast that is really there.

Extinction is read through ``pyfds_evac.core.fds_sampling``, the same path the
smoke-speed model uses, so the numbers reported here are the numbers the router
would see -- including FDS's quirk of recording the field under the name
``SOOT EXTINCTION COEFFICIENT`` while accepting ``EXTINCTION COEFFICIENT`` as
the input keyword.
"""

from __future__ import annotations

import argparse
import math

from pyfds_evac.core.fds_sampling import load_slice_sampler

EXTINCTION_QUANTITY = "SOOT EXTINCTION COEFFICIENT"
SLICE_HEIGHT_M = 2.0
SAMPLE_STEP_M = 0.5

# Jin's proportionality constant for a light-reflecting sign: S = C / K.
JIN_C = 3.0

NEAR_ROUTE = [(10.0, 1.5), (0.5, 1.5)]
FAR_ROUTE = [(11.5, 3.25), (11.5, 26.5), (44.5, 26.5)]


def polyline_points(vertices, step_m=SAMPLE_STEP_M):
    """Return points spaced ~step_m along a polyline, endpoints included."""
    points = [vertices[0]]
    for (x0, y0), (x1, y1) in zip(vertices, vertices[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(round(length / step_m)))
        for i in range(1, n + 1):
            f = i / n
            points.append((x0 + f * (x1 - x0), y0 + f * (y1 - y0)))
    return points


def sighting_distance(k):
    """Jin sighting distance S = C / K, capped where the air is effectively clear."""
    if k <= 1e-6:
        return math.inf
    return JIN_C / k


def route_stats(sampler, points, time_s):
    """Return (mean K, p90 K, worst K) along one route at one time.

    p90 is reported alongside the worst because the two routes are sampled over
    very different lengths (9.5 m near, 56.5 m far).  A max over 113 samples is
    far likelier to catch a single transient cell of ceiling-jet spill than a
    max over 20, so a worst-case ratio can fail on one outlier while the
    sustained gradient is intact.  p90 says which of the two happened.
    """
    values = sorted(sampler.sample(time_s, x, y) for x, y in points)
    p90 = values[min(len(values) - 1, int(0.9 * len(values)))]
    return sum(values) / len(values), p90, values[-1]


def _fmt_s(s):
    return "  inf" if math.isinf(s) else f"{s:5.2f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fds_dir", help="FDS case directory for l_corridor")
    parser.add_argument("--t-start", type=float, default=0.0)
    parser.add_argument("--t-end", type=float, default=400.0)
    parser.add_argument("--dt", type=float, default=30.0)
    args = parser.parse_args()

    sampler = load_slice_sampler(
        args.fds_dir, EXTINCTION_QUANTITY, slice_height_m=SLICE_HEIGHT_M
    )
    near = polyline_points(NEAR_ROUTE)
    far = polyline_points(FAR_ROUTE)

    print(f"near route: {len(near)} samples, {NEAR_ROUTE}")
    print(f"far  route: {len(far)} samples, {FAR_ROUTE}")
    print()
    header = (
        "|  t [s] | near mean K | near p90 K | near worst K | near S=3/K | "
        "far mean K | far p90 K | far worst K | far S=3/K | far/near worst | window |"
    )
    print(header)
    print("|" + "|".join("-" * (len(c)) for c in header.split("|")[1:-1]) + "|")

    rows = []
    t = args.t_start
    while t <= args.t_end + 1e-9:
        nm, np90, nw = route_stats(sampler, near, t)
        fm, fp90, fw = route_stats(sampler, far, t)
        ratio = fw / nw if nw > 1e-9 else math.inf
        # The success criterion: far route's worst K under half the near
        # route's, near route already degraded (S < 10 m), far route still
        # usable (S >= 3 m, roughly one sign-spacing of sighting distance).
        ok = (
            ratio < 0.5
            and sighting_distance(nw) < 10.0
            and sighting_distance(fw) >= 3.0
        )
        rows.append((t, nm, np90, nw, fm, fp90, fw, ratio, ok))
        print(
            f"| {t:6.0f} | {nm:11.3f} | {np90:10.3f} | {nw:12.3f} "
            f"| {_fmt_s(sighting_distance(nw)):>10} "
            f"| {fm:10.3f} | {fp90:9.3f} | {fw:11.3f} "
            f"| {_fmt_s(sighting_distance(fw)):>9} "
            f"| {ratio:14.2f} | {'YES' if ok else '-':>6} |"
        )
        t += args.dt

    print()
    best_start, best_len = None, 0.0
    run_start = None
    for t, *_rest, ok in rows:
        if ok and run_start is None:
            run_start = t
        elif not ok and run_start is not None:
            if t - run_start > best_len:
                best_start, best_len = run_start, t - run_start
            run_start = None
    if run_start is not None and rows[-1][0] - run_start > best_len:
        best_start, best_len = run_start, rows[-1][0] - run_start
    if best_start is None:
        print("VERDICT: no contrast window found.")
    else:
        print(
            f"VERDICT: contrast window {best_start:.0f}-{best_start + best_len:.0f} s "
            f"({best_len:.0f} s long; the criterion asks for >= 60 s)."
        )


if __name__ == "__main__":
    main()
