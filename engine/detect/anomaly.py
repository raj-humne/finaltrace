"""Per-cohort IsolationForest anomaly detection (docs/04-DETECTION-ENGINE.md
section 5).

Two independent opinions, not one blended model (docs/04 section 1): this
model never sees ground truth, is trained strictly on data *before* the
scored month, and its output is hard-capped downstream in scoring.py so it
can support a case but never carry one alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from engine.core.config import Config


def _feature_matrix_columns(cfg: Config) -> list[str]:
    return [f"{f}__z_self" for f in cfg.features["baselined_features"]]


def _rank_transform(train: np.ndarray, apply_to: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Percentile-rank each column of `train` against itself, then place
    `apply_to` on that same scale by its position in the training
    distribution. Removes the heavy right tail that would otherwise dominate
    IsolationForest splits (docs/04 section 5) - and does so using only the
    training population, so no future information leaks into the transform."""
    n = len(train)
    train_ranked = np.empty_like(train, dtype=float)
    apply_ranked = np.empty((apply_to.shape[0], train.shape[1]), dtype=float)
    for j in range(train.shape[1]):
        col = train[:, j]
        order = np.argsort(col, kind="stable")
        sorted_col = col[order]
        ranks = np.empty(n, dtype=float)
        ranks[order] = np.arange(1, n + 1) / n
        train_ranked[:, j] = ranks
        pos = np.searchsorted(sorted_col, apply_to[:, j], side="right")
        apply_ranked[:, j] = pos / n
    return train_ranked, apply_ranked


def _percentile_of_abnormality(train_scores: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """Where a score sits in the training population's abnormality
    distribution: 1.0 means more abnormal than the entire training
    population, 0.0 means entirely unremarkable. `score_samples` runs higher
    for normal points, so this is the fraction of training scores that are
    *greater* than the scored value."""
    sorted_train = np.sort(train_scores)
    n = len(sorted_train)
    idx = np.searchsorted(sorted_train, scores, side="right")   # count <= score
    return (n - idx) / n


def _group_labels(frame: pd.DataFrame, cohort_n: pd.Series, dept_n: pd.Series,
                  min_cohort: int) -> np.ndarray:
    """Cohort if it clears `min_cohort_size` in the training window, else
    department, else global - the same fallback shape as the peer-baseline
    chain in ADR 0006, applied here to training-population size."""
    cohort_ok = frame["cohort_key"].map(cohort_n).fillna(0) >= min_cohort
    dept_ok = (~cohort_ok) & (frame["department"].map(dept_n).fillna(0) >= min_cohort)
    return np.where(
        cohort_ok, "C:" + frame["cohort_key"].astype(str),
        np.where(dept_ok, "D:" + frame["department"].astype(str), "G:global"),
    )


def score_anomaly(features: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add `anomaly_percentile` in [0, 1] (NaN where no model was available).

    Refits monthly on a trailing 90-day window strictly before that month
    (docs/04 section 5). A month with no prior history at all (the corpus's
    first ~90 days) or a group with fewer than `min_training_rows` gets NaN -
    scoring.py treats that as "anomaly model unavailable" and degrades to
    rules-only for that user-day (docs/02-ARCHITECTURE.md section 9), it
    never fails closed.
    """
    out = features.copy()
    if out.empty:
        out["anomaly_percentile"] = pd.Series(dtype=float)
        return out

    out["date"] = pd.to_datetime(out["date"])
    out["anomaly_percentile"] = np.nan

    cols = [c for c in _feature_matrix_columns(cfg) if c in out.columns]
    a = cfg.anomaly
    min_rows = a["min_training_rows"]
    min_cohort = a["min_cohort_size"]

    months = sorted(out["date"].dt.to_period("M").unique())
    for period in months:
        month_start = period.start_time
        month_end = month_start + pd.offsets.MonthBegin(1)
        window_start = month_start - pd.Timedelta(days=90)

        train_pool = out[(out["date"] >= window_start) & (out["date"] < month_start)]
        score_mask = (out["date"] >= month_start) & (out["date"] < month_end)
        if train_pool.empty or not score_mask.any():
            continue

        cohort_n = train_pool.groupby("cohort_key", observed=True)["user_id"].nunique()
        dept_n = train_pool.groupby("department", observed=True)["user_id"].nunique()

        train_group = _group_labels(train_pool, cohort_n, dept_n, min_cohort)
        score_group = _group_labels(out.loc[score_mask], cohort_n, dept_n, min_cohort)

        for group_key in sorted(set(score_group)):
            tr = train_pool.loc[train_group == group_key]
            sc_idx = out.index[score_mask][score_group == group_key]
            if len(tr) < min_rows or len(sc_idx) == 0:
                continue   # not enough history for this group yet - degrade to rules-only

            x_train_raw = tr[cols].fillna(0.0).to_numpy(dtype=float)
            x_score_raw = out.loc[sc_idx, cols].fillna(0.0).to_numpy(dtype=float)
            x_train, x_score = _rank_transform(x_train_raw, x_score_raw)

            model = IsolationForest(
                n_estimators=a["n_estimators"],
                max_samples=min(a["max_samples"], len(x_train)),
                contamination=a["contamination"],
                random_state=a["random_state"],
            )
            model.fit(x_train)
            train_scores = model.score_samples(x_train)
            scores = model.score_samples(x_score)
            out.loc[sc_idx, "anomaly_percentile"] = _percentile_of_abnormality(
                train_scores, scores)

    return out
