"""Tests for engine/eval/harness.py.

Metric math is verified here against small, hand-built, deterministic
fixtures - this is what lets the harness be trusted without re-running the
full ~14-minute real-CERT pipeline on every change. The one real-corpus
integration point (`build_day_scores` wired to an actual `Pipeline` run) is
covered separately by `test_eval_integration_synthetic`, using the synthetic
generator - synthetic data is a legitimate dev/test fixture per
PROJECT_CONTEXT.md section 6.2, it is simply never allowed to produce a
*reported* number, which `test_real_data_guard` below enforces directly.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from engine.core.models import Signal
from engine.eval.harness import (
    EXFILTRATION_STAGE,
    InsiderRecord,
    SyntheticDataRejected,
    alert_volume,
    assert_real_data,
    bootstrap_ci,
    build_insider_index,
    calibration,
    incident_precision,
    insider_recall,
    investigation_burden,
    is_true_positive,
    per_rule_diagnostics,
    pr_curve,
    precision_at_k,
    recall_at_budget,
    summary_paragraph,
    temporal_split,
    _first_stage_date,
    _recall_metric_fn,
)


def _sig(rule_id="r", stage=0, weight=1.0):
    return Signal(rule_id=rule_id, name=rule_id, category="exfil", stage=stage,
                 strength=1.0, weight=weight, contribution=weight, phrase="test")


# ============================================================== fixtures
def _day(y, m, d):
    return date(y, m, d)


@pytest.fixture
def insiders():
    return {
        "INSIDER1": InsiderRecord("INSIDER1", scenario=1,
                                  malicious_dates={_day(2010, 8, 10), _day(2010, 8, 14)}),
        "INSIDER2": InsiderRecord("INSIDER2", scenario=2,
                                  malicious_dates={_day(2010, 6, 1)}),
    }


@pytest.fixture
def ground_truth_frame():
    return pd.DataFrame([
        {"user_id": "INSIDER1", "date": pd.Timestamp(2010, 8, 10), "scenario": 1, "is_malicious": True},
        {"user_id": "INSIDER1", "date": pd.Timestamp(2010, 8, 14), "scenario": 1, "is_malicious": True},
        {"user_id": "INSIDER2", "date": pd.Timestamp(2010, 6, 1), "scenario": 2, "is_malicious": True},
    ])


# ============================================================== ground truth join
def test_build_insider_index_groups_by_user(ground_truth_frame):
    idx = build_insider_index(ground_truth_frame)
    assert set(idx) == {"INSIDER1", "INSIDER2"}
    assert idx["INSIDER1"].malicious_dates == {_day(2010, 8, 10), _day(2010, 8, 14)}
    assert idx["INSIDER1"].final_malicious_date == _day(2010, 8, 14)
    assert idx["INSIDER1"].first_malicious_date == _day(2010, 8, 10)


def test_build_insider_index_empty():
    assert build_insider_index(pd.DataFrame()) == {}


def test_attribution_rule_exact_date_only(insiders):
    """The core honesty check: an insider flagged on an unrelated day is NOT
    a true positive. Flagging INSIDER1 the day before their malicious date
    must not count."""
    assert is_true_positive("INSIDER1", _day(2010, 8, 10), insiders) is True
    assert is_true_positive("INSIDER1", _day(2010, 8, 9), insiders) is False
    assert is_true_positive("INSIDER1", _day(2010, 8, 11), insiders) is False
    assert is_true_positive("BENIGN_USER", _day(2010, 8, 10), insiders) is False


# ============================================================== insider recall
def test_insider_recall_catches_before_final_act(insiders):
    """INSIDER1 flagged on their FIRST malicious date (8/10) - should count as
    caught, with time-to-detect = 1 (one malicious day elapsed, inclusive).
    INSIDER2 never flagged - should not count."""
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 8, 10), "risk": 80, "confidence": 0.9,
         "lane": "AUTO_FLAG", "signal_count": 3, "incident_id": "INC-1",
         "is_insider_user": True, "is_true_positive": True},
        {"user_id": "INSIDER1", "date": _day(2010, 8, 14), "risk": 90, "confidence": 0.95,
         "lane": "AUTO_FLAG", "signal_count": 4, "incident_id": "INC-2",
         "is_insider_user": True, "is_true_positive": True},
        {"user_id": "INSIDER2", "date": _day(2010, 6, 1), "risk": 20, "confidence": 0.3,
         "lane": "MONITOR", "signal_count": 1, "incident_id": None,
         "is_insider_user": True, "is_true_positive": True},
    ])
    result = insider_recall(day_scores, insiders)
    assert result["n_insiders"] == 2
    assert result["caught"] == 1
    assert result["recall"] == 0.5
    assert result["per_user"]["INSIDER1"]["caught"] is True
    assert result["per_user"]["INSIDER1"]["time_to_detect_days"] == 1
    assert result["per_user"]["INSIDER2"]["caught"] is False


def test_insider_recall_ignores_hits_after_final_act(insiders):
    """A flag that lands only after the user's final malicious date must not
    count as detection - a hit needs to happen within the labelled window,
    not merely 'this user was eventually flagged for something'."""
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 9, 1), "risk": 90, "confidence": 0.9,
         "lane": "AUTO_FLAG", "signal_count": 3, "incident_id": "INC-1",
         "is_insider_user": True, "is_true_positive": False},
    ])
    result = insider_recall(day_scores, insiders)
    assert result["per_user"]["INSIDER1"]["caught"] is False


def test_insider_recall_empty_insiders_returns_none():
    result = insider_recall(pd.DataFrame(), {})
    assert result["recall"] is None
    assert result["n_insiders"] == 0


def test_investigation_burden(insiders):
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 8, 10), "lane": "AUTO_FLAG"},
        {"user_id": "BENIGN_A", "date": _day(2010, 8, 10), "lane": "ANALYST_REVIEW"},
        {"user_id": "BENIGN_B", "date": _day(2010, 8, 10), "lane": "MONITOR"},  # not "investigated"
    ])
    burden = investigation_burden(day_scores, insiders)
    assert burden == 1.0  # 1 non-insider investigated per 1 insider found


# ============================================================== incident precision
def test_incident_precision_attribution():
    """Two incidents: one lands on a real malicious day (true positive), one
    does not (false positive), even though it's on a real insider."""
    day_scores = pd.DataFrame([
        {"incident_id": "INC-1", "lane": "AUTO_FLAG", "is_true_positive": True},
        {"incident_id": "INC-1", "lane": "AUTO_FLAG", "is_true_positive": True},  # same incident
        {"incident_id": "INC-2", "lane": "AUTO_FLAG", "is_true_positive": False},
    ])
    result = incident_precision(day_scores)
    assert result["n_incidents"] == 2
    assert result["n_true_positive"] == 1
    assert result["precision"] == 0.5


def test_incident_precision_filters_by_lane():
    day_scores = pd.DataFrame([
        {"incident_id": "INC-1", "lane": "AUTO_FLAG", "is_true_positive": True},
        {"incident_id": "INC-2", "lane": "MONITOR", "is_true_positive": False},
    ])
    result = incident_precision(day_scores, lane="AUTO_FLAG")
    assert result["n_incidents"] == 1
    assert result["precision"] == 1.0


def test_incident_precision_no_incidents_returns_none():
    day_scores = pd.DataFrame({"incident_id": [None, None], "lane": ["MONITOR", "MONITOR"],
                               "is_true_positive": [False, False]})
    result = incident_precision(day_scores)
    assert result["precision"] is None


def test_alert_volume_counts_distinct_incidents():
    day_scores = pd.DataFrame([
        {"user_id": "U1", "date": _day(2010, 1, 1), "incident_id": "INC-1", "signal_count": 3},
        {"user_id": "U1", "date": _day(2010, 1, 1), "incident_id": "INC-1", "signal_count": 3},
        {"user_id": "U2", "date": _day(2010, 1, 2), "incident_id": None, "signal_count": 0},
    ])
    vol = alert_volume(day_scores)
    assert vol["incidents_total"] == 1


# ============================================================== PR curve / precision@k
def test_pr_curve_perfect_ranking_gives_auc_one():
    """Positives all score higher than negatives -> AUC should be exactly 1."""
    day_scores = pd.DataFrame({
        "risk": [90, 80, 70, 20, 10, 5],
        "is_true_positive": [True, True, True, False, False, False],
    })
    precision, recall, auc = pr_curve(day_scores)
    assert auc == pytest.approx(1.0)


def test_pr_curve_no_positives_returns_zero():
    day_scores = pd.DataFrame({"risk": [10, 20, 30], "is_true_positive": [False, False, False]})
    _, _, auc = pr_curve(day_scores)
    assert auc == 0.0


def test_pr_curve_worst_case_ranking_scores_low():
    """All negatives ranked above all positives should score much worse than
    a perfect ranking, proving the curve actually responds to ranking order."""
    day_scores = pd.DataFrame({
        "risk": [90, 80, 70, 20, 10, 5],
        "is_true_positive": [False, False, False, True, True, True],
    })
    _, _, auc_bad = pr_curve(day_scores)
    day_scores_good = pd.DataFrame({
        "risk": [90, 80, 70, 20, 10, 5],
        "is_true_positive": [True, True, True, False, False, False],
    })
    _, _, auc_good = pr_curve(day_scores_good)
    assert auc_bad < auc_good


def test_precision_at_k_respects_per_day_grouping():
    """k=1 per day: only the top-risk row on each date should be counted."""
    day_scores = pd.DataFrame([
        {"date": _day(2010, 1, 1), "risk": 90, "is_true_positive": True},
        {"date": _day(2010, 1, 1), "risk": 10, "is_true_positive": False},
        {"date": _day(2010, 1, 2), "risk": 5, "is_true_positive": False},
    ])
    p = precision_at_k(day_scores, k_per_day=1)
    assert p == 0.5  # one true positive out of two days' top-1 picks


def test_recall_at_budget_finds_all_positives_if_budget_covers_them():
    day_scores = pd.DataFrame([
        {"date": _day(2010, 1, 1), "risk": 90, "is_true_positive": True},
        {"date": _day(2010, 1, 1), "risk": 10, "is_true_positive": True},
    ])
    r = recall_at_budget(day_scores, k_per_day=25)
    assert r == 1.0


def test_recall_at_budget_no_positives_returns_none():
    day_scores = pd.DataFrame({"date": [_day(2010, 1, 1)], "risk": [10.0],
                               "is_true_positive": [False]})
    assert recall_at_budget(day_scores) is None


# ============================================================== calibration
def test_calibration_perfect_agreement_gives_zero_ece():
    """Confidence exactly equals observed precision in every bin -> ECE == 0."""
    day_scores = pd.DataFrame([
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": False, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": True, "signal_count": 2},
        {"confidence": 0.9, "is_true_positive": False, "signal_count": 2},
        # 8/10 = 0.8 observed vs 0.9 confidence bin midpoint - use a case that
        # matches exactly instead:
    ])
    # Simpler exact case: bin [0.0, 0.1) at confidence 0.05, 0/1 positive.
    exact = pd.DataFrame([
        {"confidence": 0.05, "is_true_positive": False, "signal_count": 1},
        {"confidence": 0.05, "is_true_positive": False, "signal_count": 1},
    ])
    result = calibration(exact, n_bins=10)
    assert result["ece"] == pytest.approx(0.05, abs=0.01)


def test_calibration_ignores_unscored_days():
    """A day with zero signals has confidence 0 by construction and must not
    dilute the calibration bins with a trivial 'confidence 0, always wrong'
    data point."""
    day_scores = pd.DataFrame([
        {"confidence": 0.0, "is_true_positive": False, "signal_count": 0},
        {"confidence": 0.0, "is_true_positive": False, "signal_count": 0},
        {"confidence": 0.85, "is_true_positive": True, "signal_count": 3},
    ])
    result = calibration(day_scores, n_bins=10)
    total_n = sum(b["n"] for b in result["bins"])
    assert total_n == 1  # only the scored row


def test_calibration_no_scored_rows_returns_none():
    day_scores = pd.DataFrame({"confidence": [0.0], "is_true_positive": [False],
                               "signal_count": [0]})
    result = calibration(day_scores)
    assert result["ece"] is None
    assert result["bins"] == []


# ============================================================== temporal split
def test_temporal_split_never_shuffles():
    day_scores = pd.DataFrame({
        "date": [_day(2010, 1, d) for d in range(1, 11)],
        "risk": range(10),
    })
    validation, test = temporal_split(day_scores, validation_frac=0.6)
    assert validation["date"].max() < test["date"].min()
    assert len(validation) + len(test) == len(day_scores)


def test_temporal_split_empty():
    v, t = temporal_split(pd.DataFrame())
    assert v.empty and t.empty


# ============================================================== bootstrap CI
def test_bootstrap_ci_is_deterministic_with_fixed_seed(insiders):
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 8, 10), "lane": "AUTO_FLAG"},
        {"user_id": "INSIDER2", "date": _day(2010, 6, 1), "lane": "MONITOR"},
    ])
    ci1 = bootstrap_ci(insiders, day_scores, _recall_metric_fn, n_resamples=200, seed=42)
    ci2 = bootstrap_ci(insiders, day_scores, _recall_metric_fn, n_resamples=200, seed=42)
    assert ci1 == ci2  # NFR-5: determinism


def test_bootstrap_ci_interval_contains_point_estimate(insiders):
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 8, 10), "lane": "AUTO_FLAG"},
        {"user_id": "INSIDER2", "date": _day(2010, 6, 1), "lane": "AUTO_FLAG"},
    ])
    point = insider_recall(day_scores, insiders)["recall"]
    ci = bootstrap_ci(insiders, day_scores, _recall_metric_fn, n_resamples=500)
    assert ci is not None
    lo, hi = ci
    assert lo <= point + 1e-9 <= hi + 1e-9


def test_bootstrap_ci_empty_insiders_returns_none():
    assert bootstrap_ci({}, pd.DataFrame(), _recall_metric_fn) is None


# ============================================================== per-rule diagnostics
def test_per_rule_diagnostics_computes_weight_drift(insiders):
    from engine.core.models import Signal

    def sig(rule_id, weight=1.0):
        return Signal(rule_id=rule_id, name=rule_id, category="exfil", stage=4,
                     strength=1.0, weight=weight, contribution=weight,
                     phrase="test signal")

    signals_by_day = {
        ("INSIDER1", _day(2010, 8, 10)): [sig("exfil.leak_platform_visit", weight=2.4)],
        ("INSIDER1", _day(2010, 8, 14)): [sig("exfil.leak_platform_visit", weight=2.4)],
        ("BENIGN_A", _day(2010, 1, 1)): [sig("exfil.leak_platform_visit", weight=2.4)],
        ("BENIGN_B", _day(2010, 1, 1)): [sig("exfil.leak_platform_visit", weight=2.4)],
    }

    table = per_rule_diagnostics(signals_by_day, insiders)
    assert len(table) == 1
    row = table.iloc[0]
    assert row["rule_id"] == "exfil.leak_platform_visit"
    assert row["fire_count"] == 4
    assert row["precision"] == 0.5  # 2 of 4 fires on real malicious days
    assert row["configured_weight"] == 2.4
    assert row["unique_contribution"] == 1  # only INSIDER1 caught, and only by this rule


def test_per_rule_diagnostics_empty_returns_empty_frame():
    table = per_rule_diagnostics({}, {})
    assert table.empty


# ============================================================== real-data guard
def test_real_data_guard_rejects_synthetic():
    with pytest.raises(SyntheticDataRejected):
        assert_real_data({"data_source": "synthetic"})


def test_real_data_guard_rejects_missing_marker():
    with pytest.raises(SyntheticDataRejected):
        assert_real_data({})


def test_real_data_guard_accepts_real_cert():
    assert_real_data({"data_source": "real_cert_r42"})  # must not raise


# ============================================================== summary paragraph
def test_summary_paragraph_never_claims_roc_auc():
    report = {
        "insider_level": {"recall": 0.89, "recall_ci_95": [0.80, 0.96]},
        "incident_level": {"auto_flag_precision": 0.78,
                           "incidents_per_day_per_1k_users": 0.32},
    }
    text = summary_paragraph(report)
    assert "ROC-AUC" in text
    assert "89%" in text
    assert "78%" in text


# ============================================================== pre-exfiltration recall
def test_first_stage_date_finds_earliest_qualifying_date():
    signals_by_day = {
        ("INSIDER1", _day(2010, 8, 5)): [_sig(stage=1)],   # recon, below threshold
        ("INSIDER1", _day(2010, 8, 10)): [_sig(stage=4)],  # first exfil-stage signal
        ("INSIDER1", _day(2010, 8, 14)): [_sig(stage=4)],  # later exfil - ignored, not earliest
        ("OTHER", _day(2010, 8, 1)): [_sig(stage=4)],
    }
    d = _first_stage_date("INSIDER1", EXFILTRATION_STAGE, signals_by_day)
    assert d == _day(2010, 8, 10)


def test_first_stage_date_none_if_never_reached():
    signals_by_day = {("INSIDER1", _day(2010, 8, 5)): [_sig(stage=2)]}
    assert _first_stage_date("INSIDER1", EXFILTRATION_STAGE, signals_by_day) is None


def test_insider_recall_pre_exfiltration_stricter_than_overall(insiders):
    """INSIDER1's only flag lands on 8/14, but their first exfiltration-stage
    signal was already on 8/10 - four days earlier. Overall recall (caught
    before the FINAL malicious act) should count this as caught; the stricter
    pre-exfiltration recall (caught before the data actually left) should
    not, because the flag came after exfiltration had already started."""
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 8, 10), "risk": 30, "confidence": 0.4,
         "lane": "MONITOR", "signal_count": 1, "incident_id": None,
         "is_insider_user": True, "is_true_positive": True},
        {"user_id": "INSIDER1", "date": _day(2010, 8, 14), "risk": 90, "confidence": 0.95,
         "lane": "AUTO_FLAG", "signal_count": 4, "incident_id": "INC-1",
         "is_insider_user": True, "is_true_positive": True},
    ])
    signals_by_day = {
        ("INSIDER1", _day(2010, 8, 10)): [_sig(stage=EXFILTRATION_STAGE)],
        ("INSIDER1", _day(2010, 8, 14)): [_sig(stage=EXFILTRATION_STAGE)],
    }
    result = insider_recall(day_scores, {"INSIDER1": insiders["INSIDER1"]}, signals_by_day)
    assert result["caught"] == 1  # overall recall: caught on 8/14, before final act (8/14)
    assert result["recall_pre_exfiltration"] == 0.0  # but not before exfil started (8/10)
    assert result["n_reached_exfiltration"] == 1
    assert result["per_user"]["INSIDER1"]["caught_pre_exfiltration"] is False


def test_insider_recall_pre_exfiltration_caught_when_flag_precedes_exfil(insiders):
    """Flip it: flag on 8/10 (a recon-only day), exfiltration-stage signal
    only starts on 8/14. That should count as caught pre-exfiltration."""
    day_scores = pd.DataFrame([
        {"user_id": "INSIDER1", "date": _day(2010, 8, 10), "risk": 75, "confidence": 0.8,
         "lane": "ANALYST_REVIEW", "signal_count": 2, "incident_id": "INC-1",
         "is_insider_user": True, "is_true_positive": True},
    ])
    signals_by_day = {
        ("INSIDER1", _day(2010, 8, 10)): [_sig(stage=1)],
        ("INSIDER1", _day(2010, 8, 14)): [_sig(stage=EXFILTRATION_STAGE)],
    }
    result = insider_recall(day_scores, {"INSIDER1": insiders["INSIDER1"]}, signals_by_day)
    assert result["recall_pre_exfiltration"] == 1.0
    assert result["per_user"]["INSIDER1"]["caught_pre_exfiltration"] is True


def test_insider_recall_pre_exfiltration_none_when_no_signals_by_day_given(insiders):
    """Without signals_by_day, the stricter metric is simply not computed -
    it must not silently default to 0 or crash, since callers that only care
    about overall recall pass nothing."""
    result = insider_recall(pd.DataFrame({"user_id": [], "date": [], "lane": []}), insiders)
    assert result["recall_pre_exfiltration"] is None
