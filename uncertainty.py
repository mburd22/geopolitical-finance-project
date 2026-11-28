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


def bootstrap_ci(values, statistic=np.mean, resamples=RESAMPLES, level=LEVEL, seed=0):
    """(low, high) confidence interval for `statistic` of `values`, or None with fewer than 2 values.

    A fixed seed means the same data always gives the same interval (no flicker between page loads).
    `statistic` must accept axis=1, like np.mean and np.median do.
    """
    values = np.asarray([v for v in values if v is not None and not np.isnan(v)], dtype=float)
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    # Each row of `picks` is one made-up sample: len(values) random positions, repeats allowed.
    picks = rng.integers(0, len(values), size=(resamples, len(values)))
    stats = statistic(values[picks], axis=1)
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(stats, [tail, 100 - tail])
    return float(low), float(high)


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
