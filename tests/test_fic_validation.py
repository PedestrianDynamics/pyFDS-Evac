"""Range checks of ``fic_min_factor`` and ``fic_alpha`` (#404).

The irritant factor is ``g = max(fic_min_factor, 1 - fic_alpha * FIC)``, so a
floor outside (0, 1] or a negative slope makes ``g`` zero, negative or above
one. ``TenabilityConfig`` rejects such values; the CLI rejects them at parse
time.
"""

from __future__ import annotations

import math

import pytest

import run
from pyfds_evac.core.fed import TenabilityConfig

BAD_FLOORS = [0, 0.0, 1.0000001, 2.0, -0.1, math.nan, math.inf, -math.inf, True]
GOOD_FLOORS = [1, 1.0, 1e-9, 0.3, 0.5]
BAD_ALPHAS = [-0.1, -1.0, math.nan, math.inf, -math.inf, True, False]
GOOD_ALPHAS = [0, 0.0, 0.7, 1.2, 5]


@pytest.mark.parametrize("value", BAD_FLOORS, ids=repr)
def test_min_factor_outside_unit_interval_rejected(value):
    with pytest.raises(ValueError, match="fic_min_factor"):
        TenabilityConfig(fic_min_factor=value)


@pytest.mark.parametrize("value", GOOD_FLOORS, ids=repr)
def test_min_factor_in_unit_interval_accepted(value):
    assert TenabilityConfig(fic_min_factor=value).fic_min_factor == value


@pytest.mark.parametrize("value", BAD_ALPHAS, ids=repr)
def test_alpha_negative_or_non_finite_rejected(value):
    with pytest.raises(ValueError, match="fic_alpha"):
        TenabilityConfig(fic_alpha=value)


@pytest.mark.parametrize("value", GOOD_ALPHAS, ids=repr)
def test_alpha_non_negative_accepted(value):
    assert TenabilityConfig(fic_alpha=value).fic_alpha == value


@pytest.mark.parametrize("value", ["0.3", None])
def test_non_numeric_rejected(value):
    with pytest.raises(ValueError, match="fic_min_factor"):
        TenabilityConfig(fic_min_factor=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fic_alpha"):
        TenabilityConfig(fic_alpha=value)  # type: ignore[arg-type]


def test_defaults_unchanged():
    config = TenabilityConfig()
    assert (config.fic_alpha, config.fic_min_factor) == (0.7, 0.3)


def _parse(*argv):
    return run._build_parser().parse_args(["--scenario", "x", *argv])


@pytest.mark.parametrize("text", ["0", "1.0000001", "-0.1", "nan", "inf", "abc"])
def test_cli_rejects_bad_min_factor(text, capsys):
    with pytest.raises(SystemExit) as exc:
        _parse("--fic-min-factor", text)
    assert exc.value.code == 2
    assert "--fic-min-factor" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["1", "1e-9", "0.3"])
def test_cli_accepts_good_min_factor(text):
    assert _parse("--fic-min-factor", text).fic_min_factor == float(text)


@pytest.mark.parametrize("text", ["-0.1", "nan", "inf", "abc"])
def test_cli_rejects_bad_alpha(text, capsys):
    with pytest.raises(SystemExit) as exc:
        _parse("--fic-alpha", text)
    assert exc.value.code == 2
    assert "--fic-alpha" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["0", "0.7"])
def test_cli_accepts_good_alpha(text):
    assert _parse("--fic-alpha", text).fic_alpha == float(text)
