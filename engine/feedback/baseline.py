"""Pandas-based behavioral-baseline recalculation (Challenge 2, spec C).

Triggered once per `false_positive` analyst feedback event
(api/feedback.py::_update_baselines), for each of the numeric features
extracted from the dismissed incident's own event chain
(file_access_count, event_count, unique_hosts, usb_insert_count,
login_count - at minimum; any additional numeric feature name works the
same way, this module has no hard-coded feature list).

Guardrails (both required by the brief, enforced here rather than trusted to
the caller):
  - `MIN_STD`: a baseline can never be tighter than this - without it, a user
    whose history happens to be near-constant would find almost any future
    value "anomalous by construction", which is the opposite of what
    dismissing a false positive is supposed to achieve.
  - `MAX_ADAPTATION_FRACTION`: a single feedback event can widen the stored
    mean or std by at most 25% over its previous value. This is what keeps
    one analyst decision from being able to blank out a whole baseline in
    one shot - repeated genuine false positives still compound the effect
    over several events, just never faster than 25% per event.
"""
from __future__ import annotations

import pandas as pd

MIN_STD = 1.0
MAX_ADAPTATION_FRACTION = 0.25


def recalculate_baseline(
    historical_feature_values: list[float],
    dismissed_value: float,
    previous_mean: float | None,
    previous_std: float | None,
) -> dict[str, float]:
    """Pandas mean/std/p95/sample_count over trusted history plus the
    dismissed incident's own observation, then clamp to the guardrails above.

    Deterministic and pure - no DB access, no I/O - so it is directly
    unit-testable (tests/test_baseline_feedback.py) independent of the API
    layer that calls it.
    """
    values = pd.Series([*historical_feature_values, dismissed_value], dtype=float)

    mean = float(values.mean())
    # Population std (ddof=0): with a single observation this is exactly 0.0,
    # which the MIN_STD floor below then corrects to 1.0 - no NaN branch
    # needed, unlike pandas' default ddof=1 sample std on a length-1 series.
    std = float(values.std(ddof=0))
    p95 = float(values.quantile(0.95))
    sample_count = int(len(values))

    if previous_mean is not None and previous_mean > 0 and mean > previous_mean:
        mean = min(mean, previous_mean * (1 + MAX_ADAPTATION_FRACTION))
    if previous_std is not None and previous_std > 0 and std > previous_std:
        std = min(std, previous_std * (1 + MAX_ADAPTATION_FRACTION))

    std = max(std, MIN_STD)

    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "p95": round(p95, 4),
        "sample_count": sample_count,
    }
