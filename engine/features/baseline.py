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

import warnings

import numpy as np
import pandas as pd

from engine.core.config import Config


def _mad(x: np.ndarray) -> float:
    med = np.median(x)
    return float(np.median(np.abs(x - med)))


def _rolling_median_mad_trailing(values: np.ndarray, day_num: np.ndarray,
                                 window_days: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised trailing calendar-window median, MAD and count.

    Equivalent to `pd.Series(values, index=dates).rolling(f"{window_days}D",
    closed="left")` paired with `.median()` / `.apply(_mad)` / `.count()`, but
    computed without a Python callback per row: pandas' `.rolling().apply()`
    invokes `_mad` once per (user, feature, day) - for the full corpus that is
    on the order of 1000 users x 22 baselined features x ~370 days each,
    i.e. several million individual Python calls, which is what made a single
    baseline pass take upwards of an hour. Every row's trailing window here
    holds at most `window_days` observed days (since `values`/`day_num` are
    one row per day with activity, never a dense daily calendar), so all
    windows fit in one small (n, W) matrix and are reduced with two
    vectorised `np.nanmedian` calls instead of n per-row Python calls.

    `values`, `day_num` must already be sorted ascending by date.
    """
    n = len(values)
    if n == 0:
        empty = np.array([])
        return empty, empty, empty

    cutoff = day_num - window_days
    lo = np.searchsorted(day_num, cutoff, side="left")
    hi = np.arange(n)  # window excludes the current row itself (closed="left")
    counts = hi - lo
    width = int(counts.max()) if n else 0
    if width == 0:
        nan_arr = np.full(n, np.nan)
        return nan_arr, nan_arr, counts.astype(float)

    mat = np.full((n, width), np.nan)
    for w in range(width):
        idx = hi - 1 - w
        valid = idx >= lo
        mat[valid, w] = values[idx[valid]]

    with warnings.catch_warnings():
        # Rows with zero prior days (warm-up) are all-NaN by construction;
        # NaN out is correct there, same as the pandas .rolling().median()
        # this replaces - just without numpy's per-call warning noise.
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        med = np.nanmedian(mat, axis=1)
        mad = np.nanmedian(np.abs(mat - med[:, None]), axis=1)
    return med, mad, counts.astype(float)


def compute_self_baseline(feats: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add `{feature}__z_self` plus `baseline_days` and `baseline_maturity`.

    One row per (user_id, date), same shape as the input. Each z-score is
    computed from a rolling window that excludes the scored day itself.
    """
    b = cfg.baseline
    window_days = int(b["self_window_days"])
    mad_scale = b["mad_scale"]
    eps = b["epsilon"]
    features = cfg.features["baselined_features"]

    out = feats.sort_values(["user_id", "date"], kind="stable").reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"])

    for feat in features:
        out[f"{feat}__z_self"] = np.nan

    maturity_parts: list[pd.Series] = []
    for _, grp in out.groupby("user_id", sort=False, observed=True):
        day_num = grp["date"].to_numpy().astype("datetime64[D]").astype(np.int64)
        for feat in features:
            vals = grp[feat].to_numpy(dtype=float)
            med, mad, _ = _rolling_median_mad_trailing(vals, day_num, window_days)
            z = (vals - med) / (mad_scale * mad + eps)
            out.loc[grp.index, f"{feat}__z_self"] = z
        _, _, cnt = _rolling_median_mad_trailing(
            np.zeros(len(grp)), day_num, window_days)
        maturity_parts.append(pd.Series(cnt, index=grp.index))

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

    cohort_size = out.groupby(["cohort_key", "date"], observed=True)["user_id"].transform("nunique")
    dept_size = out.groupby(["department", "date"], observed=True)["user_id"].transform("nunique")

    use_cohort = cohort_size >= min_cohort
    use_dept = (~use_cohort) & (dept_size >= min_cohort)

    group_key = np.where(
        use_cohort, "C:" + out["cohort_key"].astype(str) + "|" + date_str,
        np.where(use_dept, "D:" + out["department"].astype(str) + "|" + date_str,
                 "G:" + date_str),
    )
    out["_peer_group"] = group_key

    for feat in features:
        grouped = out.groupby("_peer_group", observed=True)[feat]
        median = grouped.transform("median")
        # MAD = median(|x - group median|). Both steps use pandas' built-in
        # (C-level) "median" transform rather than a custom Python lambda -
        # same result, no per-group Python callback.
        mad = (out[feat] - median).abs().groupby(
            out["_peer_group"], observed=True).transform("median")
        out[f"{feat}__z_peer"] = (out[feat] - median) / (mad_scale * mad + eps)

    out["peer_cohort_size_effective"] = out.groupby("_peer_group", observed=True)["user_id"].transform(
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
