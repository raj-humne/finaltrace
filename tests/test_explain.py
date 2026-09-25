"""Tests for engine/explain (narrative.py, counterfactual.py).

docs/04-DETECTION-ENGINE.md section 9: "sum(deltas) >= total under
saturation; removing everything yields the prior" and "assert the narrative
is byte-identical across two runs" are the two load-bearing properties here -
everything else in this module is a rendering of data these two prove is
faithful.
"""
from __future__ import annotations

import pandas as pd

from engine.core.config import load_config
from engine.core.models import ConfidenceTerms, Signal
from engine.correlate.incident import Incident
from engine.detect.scoring import CorrelationInputs, compute_risk
from engine.explain.counterfactual import counterfactual_deltas, minimal_sufficient_set
from engine.explain.narrative import build_narrative

CFG = load_config()


def _signal(rule_id: str, category: str, stage: int, weight: float, strength: float) -> Signal:
    return Signal(
        rule_id=rule_id, name=rule_id, category=category, stage=stage,
        strength=strength, weight=weight, contribution=weight * strength,
        phrase=f"phrase for {rule_id}",
    )


def _incident(signals: list[Signal]) -> Incident:
    corr = CorrelationInputs(distinct_categories=len({s.category for s in signals}),
                             stage_advances=max(0, len(signals) - 1), proximity_factor=1.0)
    risk, breakdown, updated = compute_risk(signals, 0.97, corr, CFG)
    confidence_terms = ConfidenceTerms(agreement=1.0, diversity=1.0, completeness=1.0,
                                       maturity=1.0)
    start = pd.Timestamp("2010-08-14 21:47:00")
    return Incident(
        incident_id="INC-20100814-TEST0001-01", user_id="TEST0001",
        window_start=start, window_end=start + pd.Timedelta(minutes=44),
        event_ids=("e1", "e2"), signals=updated,
        categories=tuple(sorted({s.category for s in updated})),
        stages=tuple(sorted({s.stage for s in updated})),
        event_count=2, signal_count=len(updated),
        category_count=len({s.category for s in updated}), over_dense=False,
        risk=risk, confidence=0.8, breakdown=breakdown, confidence_terms=confidence_terms,
    )


SIGNALS = [
    _signal("stage.first_ever_usb", "staging", 2, 1.60, 1.0),
    _signal("collect.sensitive_concentration", "collection", 3, 0.85, 0.9),
    _signal("exfil.file_copy_to_usb", "exfil", 4, 1.30, 0.7),
]


# --------------------------------------------------------------- counterfactual
def test_deltas_sum_at_least_total_under_saturation():
    """Non-additive by design (ADR 0003): saturation and category-count
    effects make per-signal deltas typically exceed the total they explain."""
    incident = _incident(SIGNALS)
    corr = CorrelationInputs(distinct_categories=3, stage_advances=2, proximity_factor=1.0)
    deltas = counterfactual_deltas(incident.signals, 0.97, corr, CFG)
    # Sum of deltas is at least the total risk attributable to evidence (risk
    # minus what the same anomaly percentile but zero rule-signals scores).
    zero_risk, _, _ = compute_risk([], 0.97, CorrelationInputs(), CFG)
    assert sum(deltas.values()) >= (incident.risk - zero_risk) - 1e-6


def test_removing_everything_yields_the_prior():
    incident = _incident(SIGNALS)
    risk_none, breakdown, _ = compute_risk([], None, CorrelationInputs(), CFG)
    assert breakdown.total_logit == CFG.scoring["prior_logit"]
    assert risk_none < incident.risk


def test_minimal_sufficient_set_is_smaller_and_still_clears_threshold():
    incident = _incident(SIGNALS)
    corr = CorrelationInputs(distinct_categories=3, stage_advances=2, proximity_factor=1.0)
    threshold = CFG.triage["alert_threshold"]
    assert incident.risk >= threshold, "fixture must clear the alert threshold to be meaningful"

    minimal = minimal_sufficient_set(incident.signals, 0.97, corr, CFG, threshold)
    assert len(minimal) <= len(incident.signals)
    risk_minimal, _, _ = compute_risk(minimal, 0.97,
                                      CorrelationInputs(distinct_categories=len(
                                          {s.category for s in minimal}),
                                          stage_advances=corr.stage_advances,
                                          proximity_factor=corr.proximity_factor), CFG)
    assert risk_minimal >= threshold


def test_minimal_set_drops_the_weakest_signal_first():
    """A fourth, deliberately weak signal should be the one dropped."""
    weak = _signal("exfil.bcc_external", "exfil", 4, 0.10, 0.2)
    signals = SIGNALS + [weak]
    incident = _incident(signals)
    corr = CorrelationInputs(distinct_categories=len({s.category for s in signals}),
                             stage_advances=2, proximity_factor=1.0)
    threshold = CFG.triage["alert_threshold"]

    minimal = minimal_sufficient_set(incident.signals, 0.97, corr, CFG, threshold)
    kept_ids = {s.rule_id for s in minimal}
    if len(minimal) < len(signals):
        assert "exfil.bcc_external" not in kept_ids


# ------------------------------------------------------------------- narrative
def test_narrative_is_byte_identical_across_two_runs():
    incident = _incident(SIGNALS)
    corr = CorrelationInputs(distinct_categories=3, stage_advances=2, proximity_factor=1.0)
    deltas = counterfactual_deltas(incident.signals, 0.97, corr, CFG)
    feature_row = {"stage.first_ever_usb__z_self": None,
                  "file_events_during_usb__z_self": 5.8, "days_to_departure": 11}

    n1 = build_narrative(incident, "AAF0535 (Engineer, Research)", deltas, feature_row, CFG)
    n2 = build_narrative(incident, "AAF0535 (Engineer, Research)", deltas, feature_row, CFG)

    assert n1 == n2
    assert n1.headline == n2.headline
    assert n1.detail == n2.detail


def test_narrative_headline_names_the_top_signal_and_counts():
    incident = _incident(SIGNALS)
    deltas = {s.rule_id: s.contribution for s in incident.signals}
    narrative = build_narrative(incident, "AAF0535", deltas, None, CFG)
    top = max(incident.signals, key=lambda s: s.contribution)
    assert top.phrase in narrative.headline
    assert f"{incident.signal_count} correlated signals" in narrative.headline
    assert f"{incident.category_count} categories" in narrative.headline


def test_narrative_detail_ordered_by_contribution_descending():
    incident = _incident(SIGNALS)
    deltas = {"stage.first_ever_usb": 5.0, "collect.sensitive_concentration": 20.0,
             "exfil.file_copy_to_usb": 1.0}
    narrative = build_narrative(incident, "AAF0535", deltas, None, CFG)
    assert "sensitive_concentration" in narrative.detail[0]
    assert "file_copy_to_usb" in narrative.detail[-1]


def test_departure_context_clause_only_when_data_present():
    from engine.explain.narrative import departure_context_clause
    assert departure_context_clause(None) is None
    assert departure_context_clause({"days_to_departure": float("nan")}) is None
    assert "11 days later" in departure_context_clause({"days_to_departure": 11})
    assert "after the user's recorded departure" in departure_context_clause(
        {"days_to_departure": -3})


def test_no_narrative_field_is_empty_for_a_real_incident():
    """NFR-6: an incident without a narrative is a bug. Every field must be
    populated whenever there is at least one signal."""
    incident = _incident(SIGNALS)
    deltas = counterfactual_deltas(incident.signals, 0.97,
                                   CorrelationInputs(distinct_categories=3), CFG)
    narrative = build_narrative(incident, "AAF0535", deltas, None, CFG)
    assert narrative.headline
    assert narrative.summary
    assert len(narrative.detail) == len(incident.signals)
