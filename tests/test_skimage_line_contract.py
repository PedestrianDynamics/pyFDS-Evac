"""Contract of the scikit-image ray functions that fdsvismap casts sight lines with.

fdsvismap requires scikit-image ~= 0.23.2, which has no wheels for Python 3.13
and 3.14; pyproject.toml overrides it with 0.26 there (``[tool.uv]``). fdsvismap
uses only ``skimage.draw.line`` and ``line_aa``. The expected cells and
anti-aliasing weights below are the output of scikit-image 0.23.2, so every
Python version must trace the same rays. Remove this test with the override
once an fdsvismap release allows 0.26.
"""

import numpy as np
import pytest
from skimage.draw import line, line_aa

LINE_CASES = [
    ((0, 0, 0, 0), [0], [0]),
    ((0, 0, 4, 0), [0, 1, 2, 3, 4], [0, 0, 0, 0, 0]),
    ((1, 2, 6, 4), [1, 2, 3, 4, 5, 6], [2, 2, 3, 3, 4, 4]),
    ((6, 4, 1, 2), [6, 5, 4, 3, 2, 1], [4, 4, 3, 3, 2, 2]),
    ((0, 0, 3, 3), [0, 1, 2, 3], [0, 1, 2, 3]),
    ((2, 7, 0, 1), [2, 2, 1, 1, 1, 0, 0], [7, 6, 5, 4, 3, 2, 1]),
]

_W1, _W2, _W3, _W4 = (
    0.07152330911474059,
    0.6286093236458963,
    0.25721864729179256,
    0.4429139854688444,
)
_W5 = 0.8143046618229481
_D = 0.2928932188134524

LINE_AA_CASES = [
    ((0, 0, 0, 0), [0], [0], [1.0]),
    (
        (1, 2, 6, 4),
        [1, 1, 2, 3, 2, 3, 4, 4, 5, 6, 5, 6],
        [2, 3, 2, 2, 3, 3, 3, 4, 3, 3, 4, 4],
        [1.0, _W1, _W2, _W3, _W4, _W5, _W5, _W3, _W4, _W1, _W2, 1.0],
    ),
    (
        (0, 0, 3, 3),
        [0, 1, 0, 1, 2, 1, 2, 3, 2, 3],
        [0, 0, 1, 1, 1, 2, 2, 2, 3, 3],
        [1.0, _D, _D, 1.0, _D, _D, 1.0, _D, _D, 1.0],
    ),
]


@pytest.mark.parametrize(("ends", "rows", "cols"), LINE_CASES)
def test_line_traces_the_same_cells(ends, rows, cols):
    rr, cc = line(*ends)
    assert rr.dtype == cc.dtype == np.int64
    assert rr.tolist() == rows
    assert cc.tolist() == cols


@pytest.mark.parametrize(("ends", "rows", "cols", "weights"), LINE_AA_CASES)
def test_line_aa_traces_the_same_cells_and_weights(ends, rows, cols, weights):
    rr, cc, val = line_aa(*ends)
    assert rr.dtype == cc.dtype == np.int64
    assert val.dtype == np.float64
    assert rr.tolist() == rows
    assert cc.tolist() == cols
    assert val.tolist() == weights
