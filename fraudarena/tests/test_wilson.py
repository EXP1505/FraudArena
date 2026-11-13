"""Owner: M4. Wilson interval against known values."""
from __future__ import annotations

import pytest

from fa.verify.wilson import wilson_interval, wilson_upper


def test_zero_successes_known_value():
    lo, hi = wilson_interval(0, 100)
    assert lo == 0.0
    assert hi == pytest.approx(0.0370, abs=1e-4)


def test_ten_of_hundred_known_value():
    lo, hi = wilson_interval(10, 100)
    assert lo == pytest.approx(0.0552, abs=1e-4)
    assert hi == pytest.approx(0.1744, abs=1e-4)


def test_no_trials_is_uninformative():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_symmetry():
    lo, hi = wilson_interval(3, 50)
    lo2, hi2 = wilson_interval(47, 50)
    assert lo == pytest.approx(1 - hi2)
    assert hi == pytest.approx(1 - lo2)


def test_interval_contains_point_estimate_and_shrinks_with_n():
    lo, hi = wilson_interval(20, 200)
    assert lo < 0.1 < hi
    lo2, hi2 = wilson_interval(200, 2000)
    assert (hi2 - lo2) < (hi - lo)


def test_upper_helper_and_bad_input():
    assert wilson_upper(0, 100) == wilson_interval(0, 100)[1]
    with pytest.raises(ValueError):
        wilson_interval(5, 3)
    with pytest.raises(ValueError):
        wilson_interval(-1, 3)
