"""Property test for the Python export round trip (#836).

Kind: property or invariant. For any option values the exporter accepts,
reading ``OPTIONS`` back out of the generated script, without running it,
gives the options it was asked to write: same keys in the same order, and
the same values with the same types (``repr`` tells ``-0.0`` from ``0.0``
and ``1`` from ``True``). Text is hostile on purpose: quotes, backslashes,
comment marks, line and paragraph separators, ``\\x85``.
"""

import argparse
import math

import pytest
from _round_trip import script_literals
from hypothesis import given, settings
from hypothesis import strategies as st

from pyfds_evac.cli import _build_parser
from pyfds_evac.config.script import ExportError, export_options, python_script

# Fixed examples so CI runs are reproducible; no example database on disk.
_SETTINGS = settings(derandomize=True, database=None, max_examples=100)

_HOSTILE = ["'", '"', "\\", "#", "\n", "\r", "\x85", " ", " ", " ", "%s"]
_text = st.one_of(
    st.text(max_size=20),
    st.lists(st.sampled_from(_HOSTILE), max_size=8).map("".join),
)
_floats = st.floats(allow_nan=False, allow_infinity=False)
_ints = st.integers(min_value=-(10**30), max_value=10**30)

# One option of each kind: float, int, text, switch, unset.
_values = st.fixed_dictionaries(
    {
        "fic_alpha": _floats,
        "heat_skin_temperature": st.one_of(_floats, st.just(-0.0)),
        "seed": st.one_of(st.none(), _ints),
        "reroute_interval": st.one_of(_floats, _ints),
        "heat_fed_method": _text,
        "heat_clothing": st.one_of(st.none(), _text),
        "debug": st.booleans(),
    }
)


def _namespace(values):
    base = vars(_build_parser().parse_args(["--scenario", "scenario.json"]))
    return argparse.Namespace(**{**base, **values})


@_SETTINGS
@given(values=_values)
def test_options_round_trip_through_the_script(values):
    ns = _namespace(values)
    expected = export_options(vars(ns), ns.seed)
    read = script_literals(python_script(ns))["OPTIONS"]
    assert list(read) == list(expected)
    assert repr(read) == repr(expected)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_numbers_are_refused(value):
    with pytest.raises(ExportError, match="fic_alpha"):
        python_script(_namespace({"fic_alpha": value}))
