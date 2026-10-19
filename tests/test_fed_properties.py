"""Property tests for the gas FED equations (#816).

Kind: property or invariant. Each relation follows from the structure of
the Purser sum, FED = (CO + CN + NOx + FLD) * HV_CO2 + O2, with every term
non-negative; none of them checks a coefficient. The concentration ranges
bound the search, they are not the validity range of the equations.

NO and NO2 are left out of the monotonicity test on purpose: they lower
the CN term (C_CN = C_HCN - C_NO - C_NO2), so the total rate may fall as
they rise when HCN is present.
"""

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pyfds_evac.core.fed import (
    _O2_HYPOXIA_THRESHOLD_PERCENT,
    DefaultFedInputs,
    accumulate_default_fed,
    default_fed_rate_per_minute,
    time_to_fed_threshold_s,
)

# Fixed examples so CI runs are reproducible; no example database on disk.
_SETTINGS = settings(derandomize=True, database=None, max_examples=200)

# Upper bounds per field: well above lethal levels, below exp() overflow in
# the CN term (C_HCN / 43 stays far below 709).
_BOUNDS = {
    "co_volume_fraction_percent": 10.0,
    "co2_volume_fraction_percent": 20.0,
    "hcn_ppm": 2000.0,
    "no_ppm": 2000.0,
    "no2_ppm": 2000.0,
    "hcl_ppm": 5000.0,
    "hbr_ppm": 5000.0,
    "hf_ppm": 5000.0,
    "so2_ppm": 5000.0,
    "acrolein_ppm": 1000.0,
    "formaldehyde_ppm": 1000.0,
}
_INCREASING = sorted(set(_BOUNDS) - {"no_ppm", "no2_ppm"})


def _conc(field: str):
    return st.floats(min_value=0.0, max_value=_BOUNDS[field], allow_nan=False)


_inputs = st.builds(
    DefaultFedInputs,
    o2_volume_fraction_percent=st.floats(
        min_value=5.0, max_value=20.9, allow_nan=False
    ),
    **{field: _conc(field) for field in _BOUNDS},
)
_durations = st.floats(min_value=0.0, max_value=3600.0, allow_nan=False)


@_SETTINGS
@given(inputs=_inputs)
def test_rate_is_non_negative(inputs):
    """Every term is non-negative, so the total is."""
    assert default_fed_rate_per_minute(inputs) >= 0.0


@_SETTINGS
@given(inputs=_inputs, field=st.sampled_from(_INCREASING), data=st.data())
def test_rate_is_non_decreasing_in_each_toxicant_and_co2(inputs, field, data):
    """Raising CO, CO2, HCN or an irritant never lowers the rate."""
    higher = data.draw(
        st.floats(min_value=getattr(inputs, field), max_value=_BOUNDS[field])
    )
    raised = replace(inputs, **{field: higher})
    assert default_fed_rate_per_minute(raised) >= default_fed_rate_per_minute(inputs)


@_SETTINGS
@given(inputs=_inputs, data=st.data())
def test_rate_is_non_increasing_in_o2(inputs, data):
    """More O2 never raises the rate; the hypoxia term falls with O2."""
    o2 = inputs.o2_volume_fraction_percent
    higher = data.draw(st.floats(min_value=o2, max_value=20.9))
    raised = replace(inputs, o2_volume_fraction_percent=higher)
    assert default_fed_rate_per_minute(raised) <= default_fed_rate_per_minute(inputs)


@_SETTINGS
@given(o2=st.floats(min_value=_O2_HYPOXIA_THRESHOLD_PERCENT, max_value=25.0))
def test_rate_is_zero_without_toxicants_at_or_above_o2_threshold(o2):
    """Clean air at or above the O2 threshold accumulates no dose."""
    inputs = DefaultFedInputs(o2_volume_fraction_percent=o2)
    assert default_fed_rate_per_minute(inputs) == 0.0


@_SETTINGS
@given(inputs=_inputs, first=_durations, second=_durations)
def test_accumulation_is_additive_in_duration(inputs, first, second):
    """Under constant exposure, two intervals add up to their sum."""
    split = accumulate_default_fed(
        inputs,
        duration_s=second,
        initial_fed=accumulate_default_fed(inputs, duration_s=first),
    )
    whole = accumulate_default_fed(inputs, duration_s=first + second)
    assert split == pytest.approx(whole, rel=1e-12, abs=1e-15)


@_SETTINGS
@given(inputs=_inputs)
def test_threshold_time_reaches_the_threshold(inputs):
    """Consistency check: accumulating for the threshold time gives FED 1.

    Both functions share ``default_fed_rate_per_minute``, so this checks
    the time conversion between them, not the rate.
    """
    t = time_to_fed_threshold_s(inputs)
    if t == float("inf"):
        assert default_fed_rate_per_minute(inputs) == 0.0
        return
    assert accumulate_default_fed(inputs, duration_s=t) == pytest.approx(1.0, rel=1e-12)
