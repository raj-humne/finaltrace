"""Evaluation harness (docs/07-EVALUATION.md).

Computes the metric suite against real CMU CERT ground truth. This module
does not run the pipeline itself - it consumes what `engine.run.Pipeline`
already produced (features, signals_by_day, incidents) plus a ground-truth
frame from `engine.ingest.ground_truth.load_ground_truth`, and reports.

Two things this file is deliberately strict about, because getting them wrong
silently produces a flattering but meaningless number:

1. ATTRIBUTION RULE (docs/07 section 5): an incident or a flagged user-day is
   only a true positive if it falls inside that specific user's *own* labelled
   malicious date range. Flagging a real insider on an unrelated day is a
   false positive, not a lucky hit. Skipping this check is the single most
   common way an insider-threat eval quietly cheats.

2. REAL-DATA GUARD: `run_from_pipeline` and the CLI refuse to write a report
   unless the input is stamped as real CERT data. The synthetic generator is a
   dev fixture; it must never be able to produce a number that looks like a
   result.

Deliberately NOT computed: ROC-AUC. At CERT's real base rate (~0.3%) it
flatters every detector - a do-nothing classifier scores ~0.5 and a mediocre
one scores >0.9, because the metric is dominated by an enormous true-negative
count. PR-AUC and precision@k are reported instead, and this omission is
itself part of the printed report so the absence reads as a choice.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date as date_type

import numpy as np
import pandas as pd

from engine.core.config import Config
from engine.correlate.incident import Incident

# ---------------------------------------------------------------- constants
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 42
CALIBRATION_BINS = 10
K_VALUES = (5, 10, 25, 50)
BUDGET_PER_DAY = 25


# ================================================================ ground truth join
@dataclass
class InsiderRecord:
    user_id: str
    scenario: int
    malicious_dates: set[date_type]

    @property
    def first_malicious_date(self) -> date_type:
        return min(self.malicious_dates)

    @property
    def final_malicious_date(self) -> date_type:
        return max(self.malicious_dates)


def build_insider_index(ground_truth: pd.DataFrame) -> dict[str, InsiderRecord]:
    """One record per insider, listing every date they actually appear
    maliciously (per docs/07 section 1.1: record dates, never the
    [start, end] window from insiders.csv, which over-covers)."""
    if ground_truth.empty:
        return {}
    out: dict[str, InsiderRecord] = {}
    for user_id, grp in ground_truth.groupby("user_id", sort=True, observed=True):
        dates = {pd.Timestamp(d).date() for d in grp["date"]}
        scenario = int(grp["scenario"].iloc[0])
        out[user_id] = InsiderRecord(user_id, scenario, dates)
    return out


def is_true_positive(user_id: str, on_date: date_type,
                     insiders: dict[str, InsiderRecord]) -> bool:
    """The attribution rule. A hit only counts if it lands on that specific
    user's own labelled malicious date - not merely "this user is an insider
    at some point in the corpus"."""
    rec = insiders.get(user_id)
    return rec is not None and on_date in rec.malicious_dates


# ================================================================ user-day scores
@dataclass
class DayScore:
    user_id: str
    date: date_type
    risk: float
    confidence: float
    lane: str
    signal_count: int
    incident_id: str | None
    is_insider_user: bool
    is_true_positive: bool


def build_day_scores(features: pd.DataFrame,
                     signals_by_day: dict[tuple[str, date_type], list],
                     incidents: list[Incident],
                     insiders: dict[str, InsiderRecord],
                     cfg: Config) -> pd.DataFrame:
    """One row per (user, date) with activity, carrying whichever score
    applies: an incident's score if the day belongs to a correlated
    incident, else the standalone rules-only score for that day (matching
    the CLI's `print_day` behaviour), else zero with no signals.

    This is the user-day granularity docs/07 section 3.3 evaluates - PR-AUC
    and precision@k need a full score series, not just the days that
    happened to form a multi-event incident.
    """
    from engine.detect.scoring import CorrelationInputs, compute_confidence, compute_risk
    from engine.route.triage import route

    incident_by_day: dict[tuple[str, date_type], Incident] = {}
    for inc in incidents:
        d = inc.window_start.date()
        while d <= inc.window_end.date():
            incident_by_day[(inc.user_id, d)] = inc
            d += pd.Timedelta(days=1)

    rows = []
    for feat_row in features.itertuples(index=False):
        user_id = feat_row.user_id
        d = pd.Timestamp(feat_row.date).date()
        is_ins = user_id in insiders

        inc = incident_by_day.get((user_id, d))
        if inc is not None:
            risk, confidence = inc.risk, inc.confidence
            lane = inc.triage_lane or "MONITOR"
            n_signals = inc.signal_count
            inc_id = inc.incident_id
        else:
            # Score every day through compute_risk/compute_confidence even
            # with zero rule signals - an anomaly-only day (no rule fired,
            # but the ML term is non-zero) must still be rankable for
            # PR-AUC/precision@k, and must be representable at all for the
            # "ML only" ablation row (docs/07-EVALUATION.md section 4), where
            # signals_by_day is empty for every day by construction there.
            # compute_risk/compute_confidence both already handle an empty
            # signal list correctly (rule_points=0, ml_points from the
            # anomaly percentile alone) - this branch previously
            # short-circuited straight to a hard zero and silently discarded
            # that whenever no rule fired.
            day_signals = signals_by_day.get((user_id, d), [])
            anomaly_pctl = getattr(feat_row, "anomaly_percentile", None)
            corr = CorrelationInputs()
            risk, _, updated = compute_risk(day_signals, anomaly_pctl, corr, cfg)
            confidence, _ = compute_confidence(
                updated, anomaly_pctl,
                getattr(feat_row, "data_completeness", 1.0),
                getattr(feat_row, "baseline_maturity", 0.0), cfg)
            lane = route(risk, confidence, cfg).lane
            n_signals = len(updated)
            inc_id = None

        rows.append(DayScore(
            user_id=user_id, date=d, risk=risk, confidence=confidence,
            lane=lane, signal_count=n_signals, incident_id=inc_id,
            is_insider_user=is_ins,
            is_true_positive=is_true_positive(user_id, d, insiders),
        ))

    return pd.DataFrame([{
        "user_id": r.user_id, "date": r.date, "risk": r.risk,
        "confidence": r.confidence, "lane": r.lane,
        "signal_count": r.signal_count, "incident_id": r.incident_id,
        "is_insider_user": r.is_insider_user, "is_true_positive": r.is_true_positive,
    } for r in rows])


# ================================================================ temporal split
def temporal_split(day_scores: pd.DataFrame,
                   validation_frac: float = 0.6) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validation on the first `validation_frac` of the date range, test on
    the rest. Never shuffled - shuffling would leak the future into the past
    (docs/07 section 5)."""
    if day_scores.empty:
        return day_scores, day_scores
    dates = pd.to_datetime(day_scores["date"]).sort_values().unique()
    cut_idx = int(len(dates) * validation_frac)
    cut_date = pd.Timestamp(dates[min(cut_idx, len(dates) - 1)]).date()
    ts = pd.to_datetime(day_scores["date"]).dt.date
    return day_scores[ts <= cut_date].copy(), day_scores[ts > cut_date].copy()


# ================================================================ insider-level
EXFILTRATION_STAGE = 4  # engine.core.models.Stage.EXFILTRATION


def _first_stage_date(user_id: str, min_stage: int,
                      signals_by_day: dict[tuple[str, date_type], list]
                      ) -> date_type | None:
    """Earliest date this user has any signal at stage >= `min_stage`."""
    dates = [d for (u, d), sigs in signals_by_day.items()
            if u == user_id and any(s.stage >= min_stage for s in sigs)]
    return min(dates) if dates else None


def insider_recall(day_scores: pd.DataFrame,
                   insiders: dict[str, InsiderRecord],
                   signals_by_day: dict[tuple[str, date_type], list] | None = None
                   ) -> dict:
    """Fraction of insiders flagged (lane in {AUTO_FLAG, ANALYST_REVIEW}) at
    least once before their own final malicious act. Also reports median
    time-to-detect, and - when `signals_by_day` is supplied - the stricter
    pre-exfiltration recall (docs/07-EVALUATION.md section 3.1): flagged
    before this user's own first EXFILTRATION-stage (>=4) signal, not merely
    before their last malicious day. That is the harder and more valuable
    claim, since it is the only version of "caught" where the data has not
    already left."""
    if not insiders:
        return {"recall": None, "n_insiders": 0, "caught": 0,
                "median_time_to_detect_days": None,
                "recall_pre_exfiltration": None, "per_user": {}}

    flagged_lanes = {"AUTO_FLAG", "ANALYST_REVIEW"}
    caught, ttd_days, per_user = 0, [], {}
    pre_exfil_caught, pre_exfil_eligible = 0, 0

    for user_id, rec in insiders.items():
        user_days = day_scores[
            (day_scores["user_id"] == user_id)
            & (day_scores["date"] <= rec.final_malicious_date)
        ].sort_values("date")
        hits = user_days[user_days["lane"].isin(flagged_lanes)
                         & user_days["date"].isin(rec.malicious_dates)]
        was_caught = not hits.empty
        per_user[user_id] = {
            "scenario": rec.scenario, "caught": was_caught,
            "malicious_days": len(rec.malicious_dates),
        }
        if was_caught:
            caught += 1
            first_hit = hits["date"].min()
            active_before = sorted(d for d in rec.malicious_dates if d <= first_hit)
            ttd_days.append(len(active_before))
            per_user[user_id]["time_to_detect_days"] = len(active_before)

        if signals_by_day is not None:
            exfil_date = _first_stage_date(user_id, EXFILTRATION_STAGE, signals_by_day)
            if exfil_date is not None:
                pre_exfil_eligible += 1
                pre_hits = hits[hits["date"] < exfil_date]
                if not pre_hits.empty:
                    pre_exfil_caught += 1
                per_user[user_id]["caught_pre_exfiltration"] = not pre_hits.empty
                per_user[user_id]["first_exfiltration_date"] = exfil_date.isoformat()

    recall_pre_exfil = (pre_exfil_caught / pre_exfil_eligible
                        if pre_exfil_eligible else None)

    return {
        "recall": caught / len(insiders),
        "n_insiders": len(insiders),
        "caught": caught,
        "median_time_to_detect_days": (
            float(np.median(ttd_days)) if ttd_days else None),
        "recall_pre_exfiltration": recall_pre_exfil,
        "n_reached_exfiltration": pre_exfil_eligible,
        "per_user": per_user,
    }


def investigation_burden(day_scores: pd.DataFrame,
                         insiders: dict[str, InsiderRecord]) -> float | None:
    """Non-insiders flagged per insider actually found - the cost side of
    recall. AUTO_FLAG + ANALYST_REVIEW lanes only (MONITOR is not "an
    investigation")."""
    flagged = day_scores[day_scores["lane"].isin({"AUTO_FLAG", "ANALYST_REVIEW"})]
    flagged_users = set(flagged["user_id"])
    n_insiders_found = len(flagged_users & set(insiders))
    n_noninsiders_flagged = len(flagged_users - set(insiders))
    if n_insiders_found == 0:
        return None
    return n_noninsiders_flagged / n_insiders_found


# ================================================================ incident-level
def incident_precision(day_scores: pd.DataFrame, lane: str | None = None) -> dict:
    """Of distinct incidents emitted (optionally restricted to one lane),
    the fraction that trace to a real insider's own malicious day."""
    rows = day_scores[day_scores["incident_id"].notna()]
    if lane:
        rows = rows[rows["lane"] == lane]
    if rows.empty:
        return {"precision": None, "n_incidents": 0, "n_true_positive": 0}

    per_incident = rows.groupby("incident_id", observed=True)["is_true_positive"].any()
    n = len(per_incident)
    tp = int(per_incident.sum())
    return {"precision": tp / n, "n_incidents": n, "n_true_positive": tp}


def alert_volume(day_scores: pd.DataFrame) -> dict:
    n_users = day_scores["user_id"].nunique()
    n_days = day_scores["date"].nunique()
    n_incidents = day_scores["incident_id"].nunique()
    per_1k_per_day = (n_incidents / max(1, n_days)) / max(1, n_users) * 1000
    signals_per_incident = (
        day_scores.loc[day_scores["incident_id"].notna(), "signal_count"]
        .groupby(day_scores["incident_id"], observed=True).max().mean()
        if day_scores["incident_id"].notna().any() else None
    )
    return {
        "incidents_total": int(n_incidents),
        "incidents_per_day_per_1k_users": float(per_1k_per_day),
        "signals_per_incident_mean": (
            float(signals_per_incident) if signals_per_incident is not None
            and not math.isnan(signals_per_incident) else None),
    }


# ================================================================ user-day granularity
def pr_curve(day_scores: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, float]:
    """Precision-recall curve and its area, at user-day granularity, scored
    by risk. This is the metric that survives CERT's extreme imbalance -
    ROC-AUC does not (see module docstring)."""
    y = day_scores["is_true_positive"].to_numpy(dtype=bool)
    scores = day_scores["risk"].to_numpy(dtype=float)
    if y.sum() == 0:
        return np.array([]), np.array([]), 0.0

    order = np.argsort(-scores, kind="stable")
    y_sorted = y[order]
    tp_cum = np.cumsum(y_sorted)
    fp_cum = np.cumsum(~y_sorted)
    precision = tp_cum / np.maximum(tp_cum + fp_cum, 1)
    recall = tp_cum / y.sum()

    # Trapezoidal AUC over recall, precision monotone-adjusted to the
    # standard "interpolated precision" envelope. Anchored at (recall=0,
    # precision=prec_env[0]): without this point the integral silently
    # drops the area under the first segment (recall 0 -> first threshold),
    # which for a perfect ranking is the difference between AUC 0.67 and the
    # correct 1.0.
    prec_env = np.maximum.accumulate(precision[::-1])[::-1]
    recall_ext = np.concatenate(([0.0], recall))
    prec_ext = np.concatenate((prec_env[:1], prec_env))
    auc = float(np.trapz(prec_ext, recall_ext))
    return precision, recall, auc


def precision_at_k(day_scores: pd.DataFrame, k_per_day: int) -> float | None:
    """Precision if only the top-k risk scores per day were ever surfaced -
    directly answers 'if an analyst can work k alerts a day, what do they get'."""
    if day_scores.empty:
        return None
    top = (day_scores.sort_values("risk", ascending=False)
           .groupby("date", group_keys=False, observed=True)
           .head(k_per_day))
    if top.empty:
        return None
    return float(top["is_true_positive"].mean())


def recall_at_budget(day_scores: pd.DataFrame, k_per_day: int = BUDGET_PER_DAY) -> float | None:
    total_positive = int(day_scores["is_true_positive"].sum())
    if total_positive == 0:
        return None
    top = (day_scores.sort_values("risk", ascending=False)
           .groupby("date", group_keys=False, observed=True)
           .head(k_per_day))
    return float(top["is_true_positive"].sum() / total_positive)


# ================================================================ calibration
def calibration(day_scores: pd.DataFrame, n_bins: int = CALIBRATION_BINS) -> dict:
    """Expected Calibration Error: does 'confidence 0.8' actually mean
    right-about-80%-of-the-time? Only over days where something fired -
    an unscored day (confidence 0 by construction) would otherwise dominate
    every bin and make the number meaningless."""
    scored = day_scores[day_scores["signal_count"] > 0]
    if scored.empty:
        return {"ece": None, "bins": []}

    edges = np.linspace(0, 1, n_bins + 1)
    bins = []
    ece = 0.0
    n = len(scored)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (scored["confidence"] >= lo) & (scored["confidence"] < hi if hi < 1
                                               else scored["confidence"] <= hi)
        chunk = scored[mask]
        if chunk.empty:
            continue
        obs = float(chunk["is_true_positive"].mean())
        mean_conf = float(chunk["confidence"].mean())
        bins.append({"confidence_range": [round(float(lo), 2), round(float(hi), 2)],
                     "n": int(len(chunk)), "observed_precision": round(obs, 4),
                     "mean_confidence": round(mean_conf, 4)})
        ece += (len(chunk) / n) * abs(obs - mean_conf)

    return {"ece": round(ece, 4), "bins": bins}


# ================================================================ bootstrap CIs
def bootstrap_ci(insiders: dict[str, InsiderRecord], day_scores: pd.DataFrame,
                 metric_fn, n_resamples: int = BOOTSTRAP_RESAMPLES,
                 seed: int = BOOTSTRAP_SEED) -> tuple[float, float] | None:
    """95% CI over resamples at the USER level (docs/07 section 6): user-days
    within one insider are correlated, so resampling user-days independently
    would understate the true interval. `metric_fn(subset_insiders, day_scores)`
    must return a single float or None."""
    if not insiders:
        return None
    rng = random.Random(seed)
    user_ids = sorted(insiders)
    values = []
    for _ in range(n_resamples):
        sample_ids = [rng.choice(user_ids) for _ in user_ids]
        subset = {uid: insiders[uid] for uid in set(sample_ids)}
        # Re-weight by resampled multiplicity so a user drawn twice counts twice.
        counts = {}
        for uid in sample_ids:
            counts[uid] = counts.get(uid, 0) + 1
        v = metric_fn(subset, day_scores, counts)
        if v is not None:
            values.append(v)
    if not values:
        return None
    lo, hi = np.percentile(values, [2.5, 97.5])
    return float(lo), float(hi)


def _recall_metric_fn(subset: dict[str, InsiderRecord], day_scores: pd.DataFrame,
                      counts: dict[str, int]) -> float | None:
    if not subset:
        return None
    flagged_lanes = {"AUTO_FLAG", "ANALYST_REVIEW"}
    total_weight, caught_weight = 0, 0
    for uid, rec in subset.items():
        w = counts.get(uid, 1)
        total_weight += w
        user_days = day_scores[(day_scores["user_id"] == uid)
                               & (day_scores["date"] <= rec.final_malicious_date)]
        hit = user_days["lane"].isin(flagged_lanes).any() and \
            user_days[user_days["lane"].isin(flagged_lanes)]["date"].isin(
                rec.malicious_dates).any()
        if hit:
            caught_weight += w
    return caught_weight / total_weight if total_weight else None


# ================================================================ per-rule diagnostics
def per_rule_diagnostics(signals_by_day: dict[tuple[str, date_type], list],
                         insiders: dict[str, InsiderRecord]) -> pd.DataFrame:
    """Fire count, standalone vs in-context precision, measured log-odds vs
    the configured weight, and unique contribution - the concrete answer to
    'how did you pick your weights' (docs/07 section 7)."""
    fires: list[dict] = []
    base_rate_num, base_rate_den = 0, 0

    for (user_id, d), signals in signals_by_day.items():
        tp = is_true_positive(user_id, d, insiders)
        base_rate_den += 1
        base_rate_num += int(tp)
        rule_ids = {s.rule_id for s in signals}
        for s in signals:
            fires.append({
                "rule_id": s.rule_id, "user_id": user_id, "date": d,
                "is_true_positive": tp, "alone": len(rule_ids) == 1,
                "weight": s.weight,
            })

    if not fires:
        return pd.DataFrame()

    df = pd.DataFrame(fires)
    base_rate = base_rate_num / max(1, base_rate_den)
    base_odds = base_rate / max(1e-9, 1 - base_rate)

    rows = []
    for rule_id, grp in df.groupby("rule_id", observed=True):
        fire_count = len(grp)
        precision = float(grp["is_true_positive"].mean())
        alone = grp[grp["alone"]]
        standalone_precision = (float(alone["is_true_positive"].mean())
                                if not alone.empty else None)
        in_context = grp[~grp["alone"]]
        in_context_precision = (float(in_context["is_true_positive"].mean())
                                if not in_context.empty else None)

        odds_given_fired = precision / max(1e-9, 1 - precision) if precision < 1 else None
        measured_log_odds = (math.log(odds_given_fired / base_odds)
                             if odds_given_fired and base_odds > 0 else None)
        configured_weight = float(grp["weight"].iloc[0])
        drift = (configured_weight - measured_log_odds
                if measured_log_odds is not None else None)

        unique_users = set(grp.loc[grp["is_true_positive"], "user_id"])
        other_rules_users = set(
            df.loc[(df["rule_id"] != rule_id) & df["is_true_positive"], "user_id"])
        unique_contribution = len(unique_users - other_rules_users)

        rows.append({
            "rule_id": rule_id, "fire_count": fire_count,
            "precision": round(precision, 4),
            "standalone_precision": (round(standalone_precision, 4)
                                     if standalone_precision is not None else None),
            "in_context_precision": (round(in_context_precision, 4)
                                     if in_context_precision is not None else None),
            "configured_weight": configured_weight,
            "measured_log_odds": (round(measured_log_odds, 4)
                                  if measured_log_odds is not None else None),
            "weight_drift": round(drift, 4) if drift is not None else None,
            "unique_contribution": unique_contribution,
        })

    return pd.DataFrame(rows).sort_values("fire_count", ascending=False).reset_index(drop=True)


# ================================================================ real-data guard
class SyntheticDataRejected(RuntimeError):
    """Raised when the harness is asked to report on anything but real CERT."""


def assert_real_data(dataset_profile: dict) -> None:
    source = dataset_profile.get("data_source")
    if source != "real_cert_r42":
        raise SyntheticDataRejected(
            f"refusing to emit an evaluation report from data_source={source!r}. "
            "Only real_cert_r42 may produce a reported number (docs/07-EVALUATION "
            "section 9; PROJECT_CONTEXT.md section 6.2)."
        )


# ================================================================ top-level report
def build_report(day_scores: pd.DataFrame, signals_by_day: dict,
                 insiders: dict[str, InsiderRecord], cfg: Config,
                 dataset_profile: dict, config_version: str) -> dict:
    assert_real_data(dataset_profile)

    validation, test = temporal_split(day_scores)

    ins_recall = insider_recall(test, insiders, signals_by_day)
    ci = bootstrap_ci(insiders, test, _recall_metric_fn)

    inc_prec = incident_precision(test)
    auto_prec = incident_precision(test, lane="AUTO_FLAG")

    _, _, pr_auc = pr_curve(test)
    p_at_k = {str(k): precision_at_k(test, k) for k in K_VALUES}
    recall_25 = recall_at_budget(test, BUDGET_PER_DAY)

    calib = calibration(test)
    burden = investigation_burden(test, insiders)
    vol = alert_volume(test)
    rules_table = per_rule_diagnostics(signals_by_day, insiders)

    per_scenario = {}
    for scen in sorted({rec.scenario for rec in insiders.values()}):
        subset = {u: r for u, r in insiders.items() if r.scenario == scen}
        r = insider_recall(test, subset, signals_by_day)
        per_scenario[str(scen)] = {
            "insiders": r["n_insiders"], "recall": r["recall"],
            "median_time_to_detect_days": r["median_time_to_detect_days"],
            "recall_pre_exfiltration": r["recall_pre_exfiltration"],
        }

    return {
        "data_source": dataset_profile.get("data_source"),
        "config_version": config_version,
        "split": {
            "validation_days": int(validation["date"].nunique()) if not validation.empty else 0,
            "test_days": int(test["date"].nunique()) if not test.empty else 0,
        },
        "insider_level": {
            "recall": ins_recall["recall"],
            "recall_ci_95": list(ci) if ci else None,
            "n_insiders": ins_recall["n_insiders"],
            "caught": ins_recall["caught"],
            "median_time_to_detect_days": ins_recall["median_time_to_detect_days"],
            "recall_pre_exfiltration": ins_recall["recall_pre_exfiltration"],
            "n_reached_exfiltration": ins_recall["n_reached_exfiltration"],
            "investigation_burden": burden,
        },
        "incident_level": {
            "precision": inc_prec["precision"],
            "n_incidents": inc_prec["n_incidents"],
            "auto_flag_precision": auto_prec["precision"],
            "n_auto_flag_incidents": auto_prec["n_incidents"],
            **vol,
        },
        "user_day_level": {
            "pr_auc": pr_auc,
            "precision_at_k": p_at_k,
            f"recall_at_{BUDGET_PER_DAY}_per_day": recall_25,
            "note": "ROC-AUC intentionally not reported - flatters every "
                    "detector at this base rate (see module docstring).",
        },
        "calibration": calib,
        "per_scenario": per_scenario,
        "per_rule": rules_table.to_dict("records"),
    }


def summary_paragraph(report: dict) -> str:
    ins = report["insider_level"]
    inc = report["incident_level"]
    recall_pct = f"{ins['recall'] * 100:.0f}%" if ins["recall"] is not None else "n/a"
    ci = ins.get("recall_ci_95")
    ci_txt = f" [{ci[0]*100:.0f}%, {ci[1]*100:.0f}%]" if ci else ""
    auto_pct = (f"{inc['auto_flag_precision'] * 100:.0f}%"
               if inc.get("auto_flag_precision") is not None else "n/a")
    vol = inc.get("incidents_per_day_per_1k_users")
    vol_txt = f"{vol:.2f}" if vol is not None else "n/a"

    return (
        f"Against real CMU CERT r4.2, SentinelTrace identified {recall_pct}{ci_txt} "
        f"of labelled insiders before their final malicious act, at {vol_txt} "
        f"incidents/day/1000 users. Of AUTO_FLAG incidents, {auto_pct} traced to a "
        f"real insider. ROC-AUC is not reported: at this base rate it flatters "
        f"every detector. We do not claim a fixed user-day precision target, "
        f"because at any workable alert volume that number is capped low by the "
        f"base rate itself, for any detector, including a perfect one."
    )
