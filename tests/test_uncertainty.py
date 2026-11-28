# Bootstrap confidence intervals: they should contain the average, widen with fewer or more
# scattered events, and give the same answer every time.

import numpy as np
import pytest

from uncertainty import bootstrap_ci, groups_differ_p, paired_gap_ci, share_ci


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


def test_clearly_different_groups_have_a_small_p_value():
    rng = np.random.default_rng(3)
    values = np.concatenate([rng.normal(-5, 1, 15), rng.normal(0, 1, 15), rng.normal(5, 1, 15)])
    labels = ["a"] * 15 + ["b"] * 15 + ["c"] * 15
    assert groups_differ_p(values, labels, shuffles=999) < 0.01


def test_groups_from_the_same_distribution_usually_look_alike():
    """With no real differences, p-values are spread evenly: most runs are far from tiny."""
    rng = np.random.default_rng(4)
    p_values = [groups_differ_p(rng.normal(0, 1, 40), ["a", "b", "c", "d"] * 10, shuffles=199, seed=s)
                for s in range(30)]
    assert np.mean(np.array(p_values) < 0.05) < 0.2
    assert 0.3 < np.median(p_values) < 0.7


def test_fast_spread_matches_the_plain_formula():
    from uncertainty import _spreads, spread_between_groups
    values = np.array([1.0, 2.0, 6.0, 7.0, 3.0])
    labels = np.array(["x", "x", "y", "y", "z"])
    groups = np.eye(3)[np.unique(labels, return_inverse=True)[1]]
    assert _spreads(values[None, :], groups)[0] == pytest.approx(spread_between_groups(values, labels))


def test_one_group_or_missing_values():
    assert groups_differ_p([1.0, 2.0, 3.0], ["a", "a", "a"]) is None
    assert groups_differ_p([1.0, float("nan"), 3.0, 4.0], ["a", "a", "b", "b"], shuffles=99) is not None


def test_window_clusters_chain_events_that_overlap():
    from uncertainty import window_clusters
    # positions in trading days; unsorted on purpose
    ids = window_clusters([100, 5, 10, 60, 28, 200], gap=20)
    assert ids[1] == ids[2] == ids[4]          # 5, 10, 28: each within 20 days of the previous
    assert len({ids[0], ids[3], ids[5], ids[1]}) == 4
    assert sorted(set(ids)) == [0, 1, 2, 3]


def test_cluster_bootstrap_is_wider_when_events_are_copies():
    """Ten events that are really two clusters of near-copies carry little information."""
    values = np.array([5.0] * 5 + [-5.0] * 5) + np.linspace(0, 0.1, 10)
    clusters = [0] * 5 + [1] * 5
    plain = bootstrap_ci(values)
    clustered = bootstrap_ci(values, clusters=clusters)
    assert clustered[1] - clustered[0] > 1.5 * (plain[1] - plain[0])
    assert bootstrap_ci([1.0, 2.0, 3.0], clusters=[0, 0, 0]) is None  # one cluster: no range


def test_cluster_bootstrap_matches_plain_when_every_event_is_its_own_cluster():
    rng = np.random.default_rng(5)
    values = rng.normal(0, 2, 60)
    a = bootstrap_ci(values)
    b = bootstrap_ci(values, clusters=np.arange(60))
    assert abs((a[1] - a[0]) - (b[1] - b[0])) < 0.2
