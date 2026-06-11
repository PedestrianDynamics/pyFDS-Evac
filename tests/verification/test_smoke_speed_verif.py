"""SPEC 012 Tier A verification tests for the smoke-speed reduction model.

These pin the deterministic transforms in ``core/smoke_speed.py`` and the
line-of-sight path-mean operator in ``core/route_graph.py`` against closed
forms, using the manufactured fields F0-F4 from ``fields``.
"""

import math

from fields import LinearField, UniformField, ZeroField

from pyfds_evac.core.route_graph import integrated_extinction_along_los
from pyfds_evac.core.smoke_speed import (
    speed_factor_from_extinction,
    speed_factor_from_extinction_fridolf,
)

ALPHA = 0.706
BETA = -0.057


def test_a1_1_lund_uniform_factor_exact():
    """A1.1: F1, Lund. K0=alpha => factor = 1 + beta = 0.943 exactly."""
    k0 = 0.706
    expected = 1.0 + BETA * k0 / ALPHA
    assert math.isclose(expected, 0.943, abs_tol=1e-9)
    factor = speed_factor_from_extinction(k0, alpha=ALPHA, beta=BETA)
    assert math.isclose(factor, 0.943, abs_tol=1e-9)


def test_a1_2_fridolf_uniform_factor_exact():
    """A1.2: F1, Fridolf. V = c/K, factor = V/(V+2) for clean V values."""
    # c=3, K=3 => V=1 => 1/(1+2) = 1/3
    factor = speed_factor_from_extinction_fridolf(3.0, visibility_factor_c=3.0)
    assert math.isclose(factor, 1.0 / 3.0, abs_tol=1e-9)
    # c=3, K=1.5 => V=2 => 2/(2+2) = 0.5
    factor = speed_factor_from_extinction_fridolf(1.5, visibility_factor_c=3.0)
    assert math.isclose(factor, 0.5, abs_tol=1e-9)


def test_a1_3_clamp_edges_laws_differ():
    """A1.3: Lund hard-clamps at min_speed_factor; Fridolf decays to 0."""
    # Clear air: both laws give 1.0.
    assert math.isclose(speed_factor_from_extinction(0.0), 1.0, abs_tol=1e-9)
    assert math.isclose(speed_factor_from_extinction_fridolf(0.0), 1.0, abs_tol=1e-9)
    # Very large K: Lund saturates at the floor.
    lund_floor = 0.1
    assert math.isclose(
        speed_factor_from_extinction(100.0, min_speed_factor=lund_floor),
        lund_floor,
        abs_tol=1e-9,
    )
    # Very large K: Fridolf approaches 0 with no hard clamp; the two laws
    # differ because Fridolf drops strictly below the Lund floor.
    fridolf = speed_factor_from_extinction_fridolf(100.0)
    assert fridolf < 0.05
    assert fridolf < lund_floor


def test_a1_4_linear_field_path_mean_is_midpoint():
    """A1.4 (key): F2 linear ramp. Path-mean K over [0, L] equals a*L/2 exactly.

    This is the test that distinguishes a path *mean* from local or max
    sampling: for K(x) = a*x the discrete mean over uniformly spaced
    samples (both endpoints included) is the midpoint value a*L/2 for any
    step_m / sample count.
    """
    a = 0.5
    for length in (1.0, 5.0, 13.7, 40.0):
        for step_m in (0.5, 1.0, 2.0, 7.0):
            mean_k = integrated_extinction_along_los(
                0.0, 0.0, length, 0.0, 0.0, LinearField(a), step_m=step_m
            )
            assert math.isclose(mean_k, a * length / 2.0, abs_tol=1e-9)


def test_a1_5_zero_field_null_case():
    """A1.5: F0 null. Path-mean K = 0 and both speed factors = 1.0."""
    mean_k = integrated_extinction_along_los(
        0.0, 0.0, 10.0, 5.0, 0.0, ZeroField(), step_m=2.0
    )
    assert math.isclose(mean_k, 0.0, abs_tol=1e-9)
    assert math.isclose(speed_factor_from_extinction(mean_k), 1.0, abs_tol=1e-9)
    assert math.isclose(speed_factor_from_extinction_fridolf(mean_k), 1.0, abs_tol=1e-9)


def test_a1_uniform_field_decouples_los_from_path():
    """F1 cross-check: path-mean of a uniform field equals k0 for any ray."""
    k0 = 0.706
    mean_k = integrated_extinction_along_los(
        0.0, 0.0, 17.0, 9.0, 0.0, UniformField(k0), step_m=3.0
    )
    assert math.isclose(mean_k, k0, abs_tol=1e-9)
