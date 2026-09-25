"""Robust self and peer baselines.

Self-baseline: trailing calendar-day window, computed strictly from days
*before* the scored day - no leakage, same principle as the anomaly model's
training hygiene (docs/04-DETECTION-ENGINE.md section 5). 14-day minimum
warm-up: fewer prior observed days than that and the baseline is immature,
which suppresses `requires_baseline` rules (engine/detect/rules.py) and caps
confidence (engine/detect/scoring.py).

Peer baseline: cross-sectional over the user's (role, department) cohort on
the *same* date, not trailing - the point is that an organisation-wide shift
(a deadline, a holiday) moves every cohort member's baseline together instead
of reading as individual anomalies (docs/02-ARCHITECTURE.md section 4,
docs/adr/0006). Cohorts below `peer_min_cohort` fall back to department, then
to global, so a lone cohort member still gets a usable comparison.

Median and MAD, not mean and standard deviation, throughout: a single large
insider day inside the trailing window inflates a standard deviation enough
to hide the next one (docs/03-DATA-MODEL.md section 4.9).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.core.config import Config


def _mad(x: np.ndarray) -> float:
    med = np.median(x)
    return float(np.median(np.abs(x - med)))


def compute_self_baseline(feats: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add `{feature}__z_self` plus `baseline_days` and `baseline_maturity`.

    One row per (user_id, date), same shape as the input. Each z-score is
    computed from a rolling window that excludes the scored day itself.
    """
    b = cfg.baseline
    window = f"{b['self_window_days']}D"
    mad_scale = b["mad_scale"]
    eps = b["epsilon"]
    features = cfg.features["baselined_features"]

    out = feats.sort_values(["user_id", "date"], kind="stable").reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"])

    for feat in features:
        out[f"{feat}__z_self"] = np.nan

    maturity_parts: list[pd.Series] = []
    for _, grp in out.groupby("user_id", sort=False):
        ts_index = pd.DatetimeIndex(grp["date"].to_numpy())
        for feat in features:
            s = pd.Series(grp[feat].to_numpy(dtype=float), index=ts_index)
            med = s.rolling(window, closed="left").median()
            mad = s.rolling(window, closed="left").apply(_mad, raw=True)
            z = (s.to_numpy() - med.to_numpy()) / (mad_scale * mad.to_numpy() + eps)
            out.loc[grp.index, f"{feat}__z_self"] = z
        cnt = pd.Series(np.ones(len(grp)), index=ts_index).rolling(
            window, closed="left").count()
        maturity_parts.append(pd.Series(cnt.to_numpy(), index=grp.index))

    baseline_days = pd.concat(maturity_parts).sort_index()
    out["baseline_days"] = baseline_days.fillna(0).astype(int)
    out["baseline_maturity"] = (
        out["baseline_days"] / b["maturity_full_days"]).clip(upper=1.0)
    out["baseline_mature"] = out["baseline_days"] >= b["min_warmup_days"]
    return out


def compute_peer_baseline(feats: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add `{feature}__z_peer` and `peer_cohort_size_effective`.

    Cross-sectional over (cohort_key, date). Falls back to (department, date)
    then to (date) alone when the cohort is too small to give a stable
    median/MAD - never to a demographic attribute (01-PRD section 9.5).
    """
    b = cfg.baseline
    mad_scale = b["mad_scale"]
    eps = b["epsilon"]
    min_cohort = b["peer_min_cohort"]
    features = cfg.features["baselined_features"]

    out = feats.copy()
    out["date"] = pd.to_datetime(out["date"])
    date_str = out["date"].dt.strftime("%Y-%m-%d")

    cohort_size = out.groupby(["cohort_key", "date"])["user_id"].transform("nunique")
    dept_size = out.groupby(["department", "date"])["user_id"].transform("nunique")

    use_cohort = cohort_size >= min_cohort
    use_dept = (~use_cohort) & (dept_size >= min_cohort)

    group_key = np.where(
        use_cohort, "C:" + out["cohort_key"].astype(str) + "|" + date_str,
        np.where(use_dept, "D:" + out["department"].astype(str) + "|" + date_str,
                 "G:" + date_str),
    )
    out["_peer_group"] = group_key

    for feat in features:
        grouped = out.groupby("_peer_group")[feat]
        median = grouped.transform("median")
        mad = grouped.transform(lambda s: _mad(s.to_numpy(dtype=float)))
        out[f"{feat}__z_peer"] = (out[feat] - median) / (mad_scale * mad + eps)

    out["peer_cohort_size_effective"] = out.groupby("_peer_group")["user_id"].transform(
        "nunique")
    out = out.drop(columns=["_peer_group"])
    return out


def add_baselines(feats: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Self then peer baseline, in the order features.yaml declares them."""
    if feats.empty:
        return feats
    out = compute_self_baseline(feats, cfg)
    out = compute_peer_baseline(out, cfg)
    return out.sort_values(["user_id", "date"], kind="stable").reset_index(drop=True)
