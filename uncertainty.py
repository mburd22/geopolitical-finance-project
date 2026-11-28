# How sure can we be of an average from a handful of events? Bootstrap confidence intervals.
#
# The idea: we only have, say, 9 elections. Pretend those 9 ARE the whole world, and draw
# 9 at random from them WITH replacement (so some appear twice, some not at all). Work out
# the average of that made-up sample. Do it thousands of times. The middle 90% of those
# averages is the 90% confidence interval: the range the true average plausibly sits in.
# With few events, or events that disagree, the range is wide, which is the honest answer.

import numpy as np

RESAMPLES = 4000
LEVEL = 0.90  # a 90% interval: 5% chance the truth is below it, 5% above


# Events close together in time aren't independent: their 20-day windows overlap, so they
# share the same market moves (Russia's invasion and Germany's defense fund three days later,
# say). Counting them as separate draws makes the ranges too narrow. So events whose
# reaction days are within CLUSTER_GAP trading days of the previous event are chained into
# one cluster, and the bootstrap resamples whole clusters instead of single events.
CLUSTER_GAP = 20


def window_clusters(positions, gap=CLUSTER_GAP):
    """Cluster number for each event, from its reaction day's position in the trading calendar.

    Sorted by time, a new cluster starts whenever an event's window starts more than `gap`
    trading days after the previous event's. Returns ids in the same order as `positions`.
    """
    positions = np.asarray(positions)
    order = np.argsort(positions, kind="stable")
    starts = np.r_[True, np.diff(positions[order]) > gap]
    ids = np.empty(len(positions), dtype=int)
    ids[order] = np.cumsum(starts) - 1
    return ids


def bootstrap_ci(values, statistic=np.mean, resamples=RESAMPLES, level=LEVEL, seed=0, clusters=None):
    """(low, high) confidence interval for `statistic` of `values`, or None with fewer than 2 values.

    A fixed seed means the same data always gives the same interval (no flicker between page loads).
    `statistic` must accept axis=1, like np.mean and np.median do.
    clusters: optional cluster id per value (see window_clusters). Then whole clusters are
    resampled, which is only supported for the average (the statistic is ignored).
    """
    values = np.asarray(values, dtype=float)
    keep = ~np.isnan(values)
    values = values[keep]
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    if clusters is not None:
        stats = _cluster_means(values, np.asarray(clusters)[keep], rng, resamples)
        if stats is None:
            return None
    else:
        # Each row of `picks` is one made-up sample: len(values) random positions, repeats allowed.
        picks = rng.integers(0, len(values), size=(resamples, len(values)))
        stats = statistic(values[picks], axis=1)
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(stats, [tail, 100 - tail])
    return float(low), float(high)


def _cluster_means(values, clusters, rng, resamples):
    """Averages of made-up samples built from whole clusters drawn with replacement."""
    names, codes = np.unique(clusters, return_inverse=True)
    if len(names) < 2:
        return None  # one cluster: no way to tell how much the average could vary
    totals = np.bincount(codes, weights=values)
    sizes = np.bincount(codes)
    picks = rng.integers(0, len(names), size=(resamples, len(names)))
    return totals[picks].sum(axis=1) / sizes[picks].sum(axis=1)


def share_ci(hits, **kwargs):
    """Interval for a percentage, like a hit rate. hits: 1 for right, 0 for wrong. Returns percentages."""
    ci = bootstrap_ci(hits, **kwargs)
    return None if ci is None else (ci[0] * 100, ci[1] * 100)


def paired_gap_ci(a, b, **kwargs):
    """Interval for the average of a - b, resampling PAIRS so each event keeps both its scores.

    Used for "engine hit rate minus baseline hit rate" on the same events: much tighter, and
    fairer, than comparing two separate intervals. Returns percentage points.
    """
    gaps = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    ci = bootstrap_ci(gaps, **kwargs)
    return None if ci is None else (ci[0] * 100, ci[1] * 100)


def spread_between_groups(values, labels):
    """How far apart the group averages are: each group's squared distance from the overall
    average, weighted by its size (the "between-group sum of squares" from an ANOVA)."""
    overall = values.mean()
    return sum((labels == g).sum() * (values[labels == g].mean() - overall) ** 2 for g in np.unique(labels))


def _spreads(value_rows, groups):
    """spread_between_groups for many shuffles at once. value_rows: one shuffled copy of the
    values per row; groups: a 0/1 table saying which group each position belongs to.
    Uses: sum over groups of n * (group mean - overall)^2 = sum(group total^2 / n) - N * overall^2."""
    totals = value_rows @ groups                       # each row: the total of each group
    sizes = groups.sum(axis=0)
    overall = value_rows.mean(axis=1)
    return (totals ** 2 / sizes).sum(axis=1) - len(groups) * overall ** 2


def groups_differ_p(values, labels, shuffles=5000, seed=0):
    """Do the groups really differ, or could the spread between their averages be luck?

    With nine event types, some average will look big just by chance. This shuffles the
    labels at random (so any real link between type and outcome is destroyed) and counts how
    often the shuffled groups spread out at least as much as the real ones. A small answer
    (say under 0.05) means event type matters; a large one means the differences are within
    what chance produces. Returns that share, a p-value between 0 and 1.
    """
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels)
    keep = ~np.isnan(values)
    values, labels = values[keep], labels[keep]
    if len(np.unique(labels)) < 2:
        return None
    names, codes = np.unique(labels, return_inverse=True)
    groups = np.eye(len(names))[codes]                 # row i has a 1 in the column of event i's group
    observed = _spreads(values[None, :], groups)[0]
    rng = np.random.default_rng(seed)
    # Shuffling the values against fixed labels is the same as shuffling the labels.
    shuffled = rng.permuted(np.tile(values, (shuffles, 1)), axis=1)
    at_least = int((_spreads(shuffled, groups) >= observed - 1e-9).sum())
    return (at_least + 1) / (shuffles + 1)  # +1s: the real labelling counts as one of the shuffles
