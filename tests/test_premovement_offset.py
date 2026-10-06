"""``premovement_offset_s``: a fixed delay added to every pre-movement draw.

Absent, nothing changes. Present, it must be a finite number >= 0 and
needs ``use_premovement: true``, or set-up stops with a ValueError that
names the distribution.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyfds_evac.core.simulation_init import (
    _offset_times,
    _premovement_offset,
    _premovement_offset_unused,
)


def test_absent_offset_leaves_the_draw_untouched():
    times = np.array([1.0, 2.5])
    assert _offset_times(times, {}, "d") is times


def test_offset_is_added_to_every_draw():
    shifted = _offset_times(np.array([1.0, 2.5]), {"premovement_offset_s": 5}, "d")
    assert shifted.tolist() == [6.0, 7.5]


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "5", True])
def test_bad_offset_is_an_error_naming_the_distribution(bad):
    with pytest.raises(ValueError, match="'room'.*premovement_offset_s"):
        _premovement_offset({"premovement_offset_s": bad}, "room")


def test_offset_without_premovement_is_an_error():
    with pytest.raises(ValueError, match="'room'.*use_premovement"):
        _premovement_offset_unused({"premovement_offset_s": 2.0}, "room")
    _premovement_offset_unused({}, "room")
