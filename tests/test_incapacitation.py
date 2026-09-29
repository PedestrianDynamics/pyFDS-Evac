"""Tests for FED incapacitation thresholds.

By default every agent stops at ``fed_threshold`` (the FDS+Evac rule). The
opt-in probabilistic mode treats incapacitation as a population endpoint: each
agent draws its own threshold from a log-normal calibrated to the NIST TN 1797
/ Purser bands (~11/50/89 % incapacitated at FED 0.3/1/3).
"""

import random

from pyfds_evac.core.fed import TenabilityConfig, sample_incapacitation_threshold


def test_defaults_are_deterministic():
    cfg = TenabilityConfig()
    assert cfg.incapacitation_mode == "deterministic"
    assert cfg.susceptibility_sigma == 0.94
    assert cfg.fed_threshold == 1.0


def test_probabilistic_thresholds_reproduce_nist_bands():
    cfg = TenabilityConfig(incapacitation_mode="probabilistic")  # median 1, sigma 0.94
    rng = random.Random(20240607)
    n = 200_000
    draws = [sample_incapacitation_threshold(cfg, rng) for _ in range(n)]

    frac = lambda x: sum(d <= x for d in draws) / n  # noqa: E731
    # NIST TN 1797 bands: 0.3 -> ~11 %, 1.0 -> 50 %, 3.0 -> ~89 %.
    # sigma=0.94 gives ~10/50/88 %; allow a small Monte-Carlo tolerance.
    assert abs(frac(0.3) - 0.10) < 0.02
    assert abs(frac(1.0) - 0.50) < 0.02
    assert abs(frac(3.0) - 0.88) < 0.02
    # median sits at fed_threshold
    draws.sort()
    assert abs(draws[n // 2] - 1.0) < 0.02


def test_median_scales_with_fed_threshold():
    cfg = TenabilityConfig(
        incapacitation_mode="probabilistic", fed_threshold=0.3
    )  # sensitive-population design limit
    rng = random.Random(1)
    draws = sorted(sample_incapacitation_threshold(cfg, rng) for _ in range(50_000))
    assert abs(draws[len(draws) // 2] - 0.3) < 0.01


def test_deterministic_mode_is_uniform():
    cfg = TenabilityConfig(incapacitation_mode="deterministic", fed_threshold=1.0)
    rng = random.Random(0)
    vals = {sample_incapacitation_threshold(cfg, rng) for _ in range(1000)}
    assert vals == {1.0}


def test_reproducible_with_seed():
    cfg = TenabilityConfig(incapacitation_mode="probabilistic")
    a = [sample_incapacitation_threshold(cfg, random.Random(7)) for _ in range(5)]
    b = [sample_incapacitation_threshold(cfg, random.Random(7)) for _ in range(5)]
    assert a == b


def test_cli_exposes_incapacitation_flags():
    import run

    defaults = vars(run._build_parser().parse_args(["--scenario", "x"]))
    assert defaults["incapacitation_mode"] == "deterministic"
    assert defaults["susceptibility_sigma"] == 0.94


def test_webapp_defaults_to_deterministic():
    from pyfds_evac.webapp.params import default_output_base, form_to_opts

    opts = form_to_opts({"scenario": "t_junction", "seed": "1"})
    assert opts.incapacitation_mode == "deterministic"
    assert "/deterministic/" in default_output_base("t_junction", None, None)
