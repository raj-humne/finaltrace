"""Tests for engine/features/baseline.py.

The MAD-robustness test is the load-bearing one: docs/03-DATA-MODEL.md
section 4.9 and ADR 0006 both justify median/MAD over mean/std on the claim
that one extreme day inside the trailing window should not meaningfully move
the baseline. This proves that claim rather than asserting it.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from engine.core.config import load_config
from engine.features.baseline import add_baselines, compute_peer_baseline, compute_self_baseline


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# --------------------------------------------------------------- MAD vs std
def test_mad_more_robust_than_std_to_one_extreme_day():
    """Injecting one extreme value shifts a MAD-based baseline far less than
    it shifts a mean/std-based one - the entire reason MAD was chosen."""
    rng = np.random.default_rng(0)
    normal_days = rng.normal(loc=10.0, scale=2.0, size=29)

    baseline_median = np.median(normal_days)
    baseline_mad = np.median(np.abs(normal_days - baseline_median))
    baseline_mean = np.mean(normal_days)
    baseline_std = np.std(normal_days)

    with_outlier = np.append(normal_days, 500.0)   # one insider-magnitude spike

    outlier_median = np.median(with_outlier)
    outlier_mad = np.median(np.abs(with_outlier - outlier_median))
    outlier_mean = np.mean(with_outlier)
    outlier_std = np.std(with_outlier)

    median_shift = abs(outlier_median - baseline_median)
    mad_shift = abs(outlier_mad - baseline_mad)
    mean_shift = abs(outlier_mean - baseline_mean)
    std_shift = abs(outlier_std - baseline_std)

    assert median_shift < mean_shift
    assert mad_shift < std_shift
    # Not just smaller - order-of-magnitude smaller, which is the actual claim.
    assert mad_shift < std_shift / 5


def test_mad_baseline_resists_one_extreme_day_end_to_end(cfg):
    """Same claim, exercised through compute_self_baseline: the z_self for a
    normal day barely moves whether or not an earlier day in the window was
    an outlier, while a mean/std z-score would move a great deal."""
    feat = "file_event_count"
    assert feat in cfg.features["baselined_features"]

    start = date(2024, 1, 1)
    days = [start + timedelta(days=i) for i in range(31)]
    rng = np.random.default_rng(1)
    values = list(rng.normal(loc=10.0, scale=1.5, size=30).clip(min=0))
    values.append(10.0)   # the scored day: an ordinary value

    clean = pd.DataFrame({
        "user_id": "U1", "date": days, feat: values,
        "cohort_key": "Engineer|Research", "department": "Research",
    })
    for other in cfg.features["baselined_features"]:
        if other not in clean.columns:
            clean[other] = 0.0

    spiked = clean.copy()
    spiked.loc[spiked.index[15], feat] = 500.0   # one extreme day mid-window

    z_clean = compute_self_baseline(clean, cfg).iloc[-1][f"{feat}__z_self"]
    z_spiked = compute_self_baseline(spiked, cfg).iloc[-1][f"{feat}__z_self"]

    # A mean/std z-score would be crushed toward zero by the spike (std
    # inflates hugely); MAD keeps the scored day's z-score close to its
    # pre-spike value.
    assert abs(z_clean - z_spiked) < 1.0


# ------------------------------------------------------------- warm-up gate
def test_baseline_immature_before_min_warmup_days(cfg):
    feat = cfg.features["baselined_features"][0]
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(20)]
    df = pd.DataFrame({
        "user_id": "U1", "date": days, feat: [1.0] * len(days),
        "cohort_key": "Engineer|Research", "department": "Research",
    })
    for other in cfg.features["baselined_features"]:
        if other not in df.columns:
            df[other] = 0.0

    out = compute_self_baseline(df, cfg)
    warmup = cfg.baseline["min_warmup_days"]
    assert not out.iloc[warmup - 1]["baseline_mature"]
    assert bool(out.iloc[-1]["baseline_mature"]) == (len(days) - 1 >= warmup)


def test_self_baseline_excludes_scored_day(cfg):
    """The scored day's own value must never leak into its own baseline -
    otherwise an insider's spike would train the very baseline meant to catch
    it (docs/02-ARCHITECTURE.md section 4)."""
    feat = cfg.features["baselined_features"][0]
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(20)]
    values = [5.0] * 19 + [5000.0]   # spike only on the scored (last) day
    df = pd.DataFrame({
        "user_id": "U1", "date": days, feat: values,
        "cohort_key": "Engineer|Research", "department": "Research",
    })
    for other in cfg.features["baselined_features"]:
        if other not in df.columns:
            df[other] = 0.0

    out = compute_self_baseline(df, cfg)
    z_last = out.iloc[-1][f"{feat}__z_self"]
    # If the spike leaked into its own baseline, z would collapse toward 0.
    assert z_last > 10


# ------------------------------------------------------------------- peer
def test_peer_baseline_falls_back_when_cohort_too_small(cfg):
    feat = cfg.features["baselined_features"][0]
    day = date(2024, 1, 1)
    # Only 2 members of Engineer|Research (below peer_min_cohort=5), but 6
    # members of the Research department overall.
    rows = []
    for i in range(2):
        rows.append(("Eng%d" % i, day, 10.0, "Engineer|Research", "Research"))
    for i in range(4):
        rows.append(("Other%d" % i, day, 10.0, "Analyst|Research", "Research"))
    df = pd.DataFrame(rows, columns=["user_id", "date", feat, "cohort_key", "department"])
    for other in cfg.features["baselined_features"]:
        if other not in df.columns:
            df[other] = 0.0

    out = compute_peer_baseline(df, cfg)
    # All 6 fell into the department-level fallback group.
    assert (out["peer_cohort_size_effective"] == 6).all()


def test_add_baselines_produces_both_z_columns(cfg):
    feat = cfg.features["baselined_features"][0]
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(20)]
    df = pd.DataFrame({
        "user_id": "U1", "date": days, feat: np.linspace(1, 20, 20),
        "cohort_key": "Engineer|Research", "department": "Research",
    })
    for other in cfg.features["baselined_features"]:
        if other not in df.columns:
            df[other] = 0.0

    out = add_baselines(df, cfg)
    assert f"{feat}__z_self" in out.columns
    assert f"{feat}__z_peer" in out.columns
    assert len(out) == len(df)
