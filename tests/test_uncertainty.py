# Bootstrap confidence intervals: they should contain the average, widen with fewer or more
# scattered events, and give the same answer every time.

import numpy as np
import pytest

from uncertainty import bootstrap_ci, paired_gap_ci, share_ci


def test_interval_contains_the_average():
    values = [1.0, 4.0, -2.0, 3.0, 0.5, 6.0, -1.0]
    low, high = bootstrap_ci(values)
    assert low < np.mean(values) < high


def test_identical_values_have_no_uncertainty():
    assert bootstrap_ci([2.5] * 10) == pytest.approx((2.5, 2.5))


def test_more_events_give_a_narrower_interval():
    rng = np.random.default_rng(1)
    few = rng.normal(0, 5, 8)
    many = rng.normal(0, 5, 200)
    width = lambda ci: ci[1] - ci[0]
    assert width(bootstrap_ci(many)) < width(bootstrap_ci(few))


def test_same_data_same_interval():
    values = [3.0, -1.0, 7.0, 2.0]
    assert bootstrap_ci(values) == bootstrap_ci(values)


def test_too_few_values_and_gaps_are_handled():
    assert bootstrap_ci([]) is None
    assert bootstrap_ci([5.0]) is None
    assert bootstrap_ci([1.0, float("nan"), None]) is None  # only one real value
    assert bootstrap_ci([1.0, float("nan"), 3.0]) is not None


def test_share_ci_is_in_percent():
    low, high = share_ci([1, 1, 0, 1, 0, 1, 1, 0, 1, 1])  # 70% right
    assert 0 <= low < 70 < high <= 100


def test_paired_gap_is_tighter_than_separate_intervals():
    """When engine and baseline agree on most events, their gap is far more certain than either rate."""
    rng = np.random.default_rng(2)
    baseline = rng.integers(0, 2, 100)
    engine = baseline.copy()
    engine[:5] = 1 - engine[:5]  # disagree on only 5 events
    gap_low, gap_high = paired_gap_ci(engine, baseline)
    rate_low, rate_high = share_ci(engine)
    assert gap_high - gap_low < (rate_high - rate_low) / 2
