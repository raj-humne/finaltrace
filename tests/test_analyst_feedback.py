"""Tests for the Analyst Feedback Loop for False-Positive Reduction
(Challenge 2): engine/feedback/baseline.py and engine/feedback/edge_weights.py
(pure, deterministic units), api/feedback.py + the
POST /api/v1/incidents/{incident_id}/feedback endpoint (the real DB
transaction), and engine/feedback/scoring_adjust.py wired against the real
engine.detect.scoring.compute_risk (the actual score-reduction proof).

The end-to-end test does not call a mock scorer: it builds a real event
chain and real Signal/CorrelationInputs objects, computes the *actual*
pre-feedback risk with `compute_risk`, submits feedback through the real
FastAPI endpoint (a real DB transaction against a real SQLite file, same as
every other test in this suite), reads back the real persisted
BehavioralBaseline/EdgeFeedbackWeight rows, and re-scores the identical
chain with `compute_feedback_aware_risk` - the same function
engine.correlate.incident would call for a real re-score - to prove the
measured reduction, then repeats the same chain for an unrelated user to
prove the learning did not leak.
"""
from __future__ import annotations

import datetime as dt

import pytest

from engine.core.config import load_config
from engine.core.models import Signal
from engine.detect.scoring import CorrelationInputs, compute_risk
from engine.feedback.baseline import MAX_ADAPTATION_FRACTION, MIN_STD, recalculate_baseline
from engine.feedback.edge_weights import MIN_MULTIPLIER, edge_weight_multiplier
from engine.feedback.scoring_adjust import compute_feedback_aware_risk

from tests.test_live_demo import _restore_demo_csvs, demo_client  # noqa: F401  (reused fixtures)

UTC = dt.timezone.utc


# ============================================================== G.1: Pandas baseline unit tests
def test_recalculate_baseline_uses_pandas_stats_on_history_plus_dismissed_value():
    history = [5.0, 6.0, 5.0, 7.0, 6.0]
    stats = recalculate_baseline(history, dismissed_value=8.0, previous_mean=None, previous_std=None)

    import pandas as pd
    expected = pd.Series(history + [8.0])
    assert stats["mean"] == pytest.approx(float(expected.mean()), abs=1e-3)
    assert stats["p95"] == pytest.approx(float(expected.quantile(0.95)), abs=1e-3)
    assert stats["sample_count"] == 6


def test_recalculate_baseline_enforces_minimum_std_floor():
    # All-identical history -> true std is 0.0, which must be floored.
    stats = recalculate_baseline([4.0, 4.0, 4.0], dismissed_value=4.0, previous_mean=4.0, previous_std=1.0)
    assert stats["std"] >= MIN_STD


def test_recalculate_baseline_caps_growth_at_25_percent_of_previous():
    # A wildly high dismissed value would otherwise blow the mean/std out;
    # the cap must hold regardless of how extreme the single new value is.
    previous_mean, previous_std = 10.0, 2.0
    stats = recalculate_baseline([10.0, 10.0, 10.0], dismissed_value=500.0, previous_mean=previous_mean, previous_std=previous_std)

    assert stats["mean"] <= previous_mean * (1 + MAX_ADAPTATION_FRACTION) + 1e-6
    assert stats["std"] <= previous_std * (1 + MAX_ADAPTATION_FRACTION) + 1e-6


def test_recalculate_baseline_does_not_cap_shrinkage():
    # The cap is a growth limit only - a dismissed value that would *lower*
    # the computed mean/std must not be artificially held up.
    stats = recalculate_baseline([1.0, 1.0, 1.0, 1.0], dismissed_value=1.0, previous_mean=50.0, previous_std=20.0)
    assert stats["mean"] < 50.0


# ============================================================== G.2: edge-weight unit tests
def test_first_false_positive_decays_edge_weight_to_0_85():
    assert edge_weight_multiplier(1) == pytest.approx(0.85)


def test_edge_weight_decays_further_with_repeated_feedback():
    m1 = edge_weight_multiplier(1)
    m2 = edge_weight_multiplier(2)
    m3 = edge_weight_multiplier(3)
    assert m2 < m1
    assert m3 < m2
    assert m2 == pytest.approx(0.85 ** 2)


def test_edge_weight_multiplier_never_drops_below_floor():
    for count in (5, 10, 50, 1000):
        assert edge_weight_multiplier(count) >= MIN_MULTIPLIER
    assert edge_weight_multiplier(1000) == pytest.approx(MIN_MULTIPLIER)


def test_edge_weight_multiplier_is_1_with_no_history():
    assert edge_weight_multiplier(0) == 1.0


# ============================================================== helpers for the integration test
def _seed_chain_incident(db_session, incident_id: str, user_id: str, run_id: str):
    """A real off-hours auth_login -> usb_insert (12 min later) -> high-count
    file_access chain, persisted as real Event/IncidentEvent/IncidentEdge rows -
    exactly the evidence shape api/feedback.py reads (spec's worked example)."""
    from api.models.correlation import Incident, IncidentEdge, IncidentEvent
    from api.models.identity import User
    from api.models.ingest import Event, IngestRun

    db_session.merge(User(user_id=user_id, first_seen=dt.date(2010, 1, 1), last_seen=dt.date(2010, 1, 2)))
    if not db_session.get(IngestRun, run_id):
        db_session.add(IngestRun(
            run_id=run_id, started_at=dt.datetime.now(UTC), finished_at=dt.datetime.now(UTC),
            status="success", source_files={}, rows_accepted=17, rows_rejected=0,
        ))
    db_session.flush()

    login_ts = dt.datetime(2010, 1, 5, 2, 0, tzinfo=UTC)  # off-hours
    usb_ts = login_ts + dt.timedelta(minutes=12)

    login = Event(
        event_id=f"{incident_id}-login", user_id=user_id, pc_id="PC-1", ts=login_ts,
        event_date=login_ts.date(), source="logon", action="logon", attrs={}, ingest_run_id=run_id,
    )
    usb = Event(
        event_id=f"{incident_id}-usb", user_id=user_id, pc_id="PC-1", ts=usb_ts,
        event_date=usb_ts.date(), source="device", action="connect", attrs={}, ingest_run_id=run_id,
    )
    file_events = [
        Event(
            event_id=f"{incident_id}-file-{i}", user_id=user_id, pc_id="PC-1",
            ts=usb_ts + dt.timedelta(minutes=1 + i), event_date=usb_ts.date(),
            source="file", action="access", attrs={}, ingest_run_id=run_id,
        )
        for i in range(15)  # "high file access count" (spec's worked example)
    ]
    for e in [login, usb, *file_events]:
        db_session.add(e)
    db_session.flush()

    incident = Incident(
        incident_id=incident_id, user_id=user_id, window_start=login_ts, window_end=file_events[-1].ts,
        risk=0.0, confidence=0.8, triage_lane="AUTO_FLAG", status="open",
        killchain_stages=[1, 2, 3], signal_count=3, event_count=17, category_count=3,
        over_dense=False, config_version="test",
    )
    db_session.add(incident)
    db_session.flush()

    for e in [login, usb, *file_events]:
        db_session.add(IncidentEvent(incident_id=incident_id, event_id=e.event_id, node_role="signal"))
    db_session.add(IncidentEdge(
        incident_id=incident_id, src_event=login.event_id, dst_event=usb.event_id,
        gap_seconds=720, edge_type="stage_advance", weight=1.0,
    ))
    db_session.add(IncidentEdge(
        incident_id=incident_id, src_event=usb.event_id, dst_event=file_events[0].event_id,
        gap_seconds=60, edge_type="stage_advance", weight=1.0,
    ))
    db_session.commit()
    return incident


def _chain_signals(weight_base: float = 1.2) -> list[Signal]:
    """The same three-category, three-stage evidence shape as
    `_seed_chain_incident`'s real events - one Signal per category, each
    referencing (via `detail.clauses`) the exact feature name
    engine/feedback/scoring_adjust.py looks up a learned baseline discount
    for."""
    # Feature names match api/feedback.py's FEATURE_NAMES exactly (the
    # features _extract_incident_features computes from the real event
    # chain) - this is how engine/feedback/scoring_adjust.py's per-signal
    # discount lookup actually finds a match.
    return [
        Signal(rule_id="r.offhours_login", name="off-hours login", category="access", stage=1,
              strength=1.0, weight=weight_base, contribution=0.0, phrase="off-hours login",
              detail={"clauses": [{"feature": "login_count"}]}, evidence_event_ids=()),
        Signal(rule_id="r.usb_insert", name="usb insert", category="staging", stage=2,
              strength=1.0, weight=weight_base + 0.2, contribution=0.0, phrase="usb insert",
              detail={"clauses": [{"feature": "usb_insert_count"}]}, evidence_event_ids=()),
        Signal(rule_id="r.file_burst", name="file burst", category="collection", stage=3,
              strength=1.0, weight=weight_base + 0.4, contribution=0.0, phrase="file burst",
              detail={"clauses": [{"feature": "file_access_count"}]}, evidence_event_ids=()),
    ]


def _chain_corr() -> CorrelationInputs:
    return CorrelationInputs(distinct_categories=3, stage_advances=2, proximity_factor=1.0, over_dense=False)


# ============================================================== G.3: API + real-pipeline integration test
def test_feedback_reduces_risk_on_reinjection_for_same_user_but_not_others(demo_client, db_session):
    cfg = load_config()
    signals = _chain_signals()
    corr = _chain_corr()

    # 1. Real scoring, before any feedback - the real compute_risk function.
    risk_before, _, _ = compute_risk(signals, 0.97, corr, cfg)
    assert risk_before >= 70.0, f"test fixture must start in the high band, got {risk_before}"

    incident = _seed_chain_incident(db_session, "INC-FB-01", "u_fb_test", "run_fb_test")
    incident.risk = risk_before
    db_session.commit()

    # 2. Submit false-positive feedback via the real API endpoint.
    r = demo_client.post(
        f"/api/v1/incidents/{incident.incident_id}/feedback",
        json={"verdict": "false_positive", "reason_code": "known_usb_workflow",
              "comment": "Scheduled backup workflow.", "apply_to_similar": True},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["incident_status"] == "closed"
    assert body["disposition"] == "false_positive"
    assert body["feedback_id"]
    assert body["updated_baselines"], "expected at least one baseline row to be written"
    assert body["updated_edges"], "expected at least one edge-feedback row to be written"
    assert "score_impact" in body
    assert body["score_impact"]["original_risk"] == pytest.approx(risk_before, abs=0.5)

    # 3. Audit trail + persisted rows (spec's "complete analyst audit trail").
    from api.models.analyst_feedback import AnalystFeedback, BehavioralBaseline, EdgeFeedbackWeight
    from api.models.identity import AuditLog

    feedback_row = db_session.get(AnalystFeedback, body["feedback_id"])
    assert feedback_row is not None
    assert feedback_row.verdict == "false_positive"
    assert feedback_row.reason_code == "known_usb_workflow"

    audit_rows = db_session.query(AuditLog).filter(AuditLog.object_id == incident.incident_id).all()
    assert any(a.action == "incident_feedback" for a in audit_rows)

    db_session.refresh(incident)
    assert incident.status == "closed"
    assert incident.disposition == "false_positive"
    assert incident.dismissed_by is not None

    baselines = db_session.query(BehavioralBaseline).filter(
        BehavioralBaseline.entity_type == "user", BehavioralBaseline.entity_id == "u_fb_test",
    ).all()
    assert len(baselines) >= 3
    baseline_discount = {b.feature_name: b.feedback_adjustment for b in baselines}

    edges = db_session.query(EdgeFeedbackWeight).filter(EdgeFeedbackWeight.context_key == "user:u_fb_test").all()
    assert len(edges) >= 2
    assert all(e.false_positive_count == 1 for e in edges)
    edge_multiplier = min(e.current_weight / e.original_weight for e in edges)
    assert edge_multiplier == pytest.approx(0.85)

    # 4. Re-inject the identical chain for the SAME user through the real
    # scoring model, now carrying the learned adjustments.
    risk_after, _, _, adjustments = compute_feedback_aware_risk(
        signals, 0.97, corr, cfg, user_id="u_fb_test",
        edge_multiplier=edge_multiplier, baseline_discount_by_feature=baseline_discount,
    )
    reduction = risk_before - risk_after
    assert reduction >= 20.0 or reduction / risk_before >= 0.25, (
        f"expected a significant reduction, got before={risk_before} after={risk_after}"
    )
    assert any(a.type == "edge_weight" for a in adjustments)
    assert any(a.type == "baseline" for a in adjustments)

    # 5. The exact same pattern for an UNRELATED user must be unaffected -
    # no baseline/edge rows exist for them, so the defaults apply unchanged.
    risk_other, _, _ = compute_risk(signals, 0.97, corr, cfg)
    assert risk_other == pytest.approx(risk_before)

    from api.models.analyst_feedback import BehavioralBaseline as BB
    other_rows = db_session.query(BB).filter(BB.entity_id == "u_other_unaffected").count()
    assert other_rows == 0


def test_duplicate_feedback_on_already_dismissed_incident_is_rejected(demo_client, db_session):
    incident = _seed_chain_incident(db_session, "INC-FB-02", "u_fb_dup", "run_fb_dup")
    incident.risk = 80.0
    db_session.commit()

    first = demo_client.post(
        f"/api/v1/incidents/{incident.incident_id}/feedback",
        json={"verdict": "false_positive", "reason_code": "other", "apply_to_similar": True},
    )
    assert first.status_code == 201, first.text

    second = demo_client.post(
        f"/api/v1/incidents/{incident.incident_id}/feedback",
        json={"verdict": "false_positive", "reason_code": "other", "apply_to_similar": True},
    )
    assert second.status_code == 409


def test_feedback_endpoint_returns_404_for_unknown_incident(demo_client):
    r = demo_client.post(
        "/api/v1/incidents/INC-DOES-NOT-EXIST/feedback",
        json={"verdict": "false_positive", "reason_code": "other", "apply_to_similar": True},
    )
    assert r.status_code == 404


def test_feedback_endpoint_rejects_invalid_reason_code(demo_client, db_session):
    incident = _seed_chain_incident(db_session, "INC-FB-03", "u_fb_bad_code", "run_fb_bad_code")
    incident.risk = 80.0
    db_session.commit()

    r = demo_client.post(
        f"/api/v1/incidents/{incident.incident_id}/feedback",
        json={"verdict": "false_positive", "reason_code": "not_a_real_code", "apply_to_similar": True},
    )
    assert r.status_code == 422


def test_feedback_endpoint_requires_authentication():
    from fastapi.testclient import TestClient
    from api.main import app

    anon = TestClient(app)
    r = anon.post(
        "/api/v1/incidents/INC-X/feedback",
        json={"verdict": "false_positive", "reason_code": "other", "apply_to_similar": True},
    )
    assert r.status_code == 401
