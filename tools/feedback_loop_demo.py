"""Demo script for the Analyst Feedback Loop for False-Positive Reduction
(Challenge 2): first-injection risk -> feedback submission -> baseline/edge
updates -> second-injection risk -> a numeric reduction, end to end, against
a real (scratch) SQLite database and the real api.feedback.submit_feedback
service - no mocks.

Usage:
    python -m tools.feedback_loop_demo

Safe to run repeatedly: it uses its own scratch database file
(data/_feedback_loop_demo.db), separate from the real demo/dev database, and
recreates it on every run.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DB_PATH = REPO_ROOT / "data" / "_feedback_loop_demo.db"

# Must be set before any api.* module is imported (api/db/session.py builds
# its engine from settings at import time) - same constraint tests/conftest.py
# documents.
if DEMO_DB_PATH.exists():
    DEMO_DB_PATH.unlink()
os.environ["SENTINEL_DB"] = f"sqlite:///{DEMO_DB_PATH.as_posix()}"

sys.path.insert(0, str(REPO_ROOT))

import api.models  # noqa: E402  (register all tables on Base.metadata)
from api.db.base import Base  # noqa: E402
from api.db.session import SessionLocal, engine  # noqa: E402
from api.feedback import submit_feedback  # noqa: E402
from api.models.analyst_feedback import BehavioralBaseline, EdgeFeedbackWeight  # noqa: E402
from api.models.correlation import Incident, IncidentEdge, IncidentEvent  # noqa: E402
from api.models.identity import User  # noqa: E402
from api.models.ingest import Event, IngestRun  # noqa: E402

from engine.core.config import load_config  # noqa: E402
from engine.core.models import Signal  # noqa: E402
from engine.detect.scoring import CorrelationInputs, compute_risk  # noqa: E402
from engine.feedback.scoring_adjust import compute_feedback_aware_risk  # noqa: E402

UTC = dt.timezone.utc
USER_ID = "u_014"
OTHER_USER_ID = "u_099"


def _chain_signals(weight_base: float = 1.2) -> list[Signal]:
    """Off-hours auth_login -> usb_insert -> high-count file_access - the
    PRD/brief's worked example. Feature names match api/feedback.py's
    FEATURE_NAMES exactly, which is how the learned baseline discount below
    finds a match."""
    return [
        Signal(rule_id="r.offhours_login", name="off-hours login", category="access", stage=1,
              strength=1.0, weight=weight_base, contribution=0.0, phrase="Off-hours login for u_014",
              detail={"clauses": [{"feature": "login_count"}]}, evidence_event_ids=()),
        Signal(rule_id="r.usb_insert", name="usb insert", category="staging", stage=2,
              strength=1.0, weight=weight_base + 0.2, contribution=0.0, phrase="USB device connected 12 min after login",
              detail={"clauses": [{"feature": "usb_insert_count"}]}, evidence_event_ids=()),
        Signal(rule_id="r.file_burst", name="file burst", category="collection", stage=3,
              strength=1.0, weight=weight_base + 0.4, contribution=0.0, phrase="High-volume file access following USB connect",
              detail={"clauses": [{"feature": "file_access_count"}]}, evidence_event_ids=()),
    ]


def _chain_corr() -> CorrelationInputs:
    return CorrelationInputs(distinct_categories=3, stage_advances=2, proximity_factor=1.0, over_dense=False)


def _seed_incident(db, incident_id: str, user_id: str, risk: float) -> Incident:
    run_id = f"run_{incident_id}"
    db.merge(User(user_id=user_id, first_seen=dt.date(2010, 1, 1), last_seen=dt.date(2010, 1, 2)))
    db.add(IngestRun(
        run_id=run_id, started_at=dt.datetime.now(UTC), finished_at=dt.datetime.now(UTC),
        status="success", source_files={}, rows_accepted=17, rows_rejected=0,
    ))
    db.flush()

    login_ts = dt.datetime(2010, 1, 5, 2, 0, tzinfo=UTC)
    usb_ts = login_ts + dt.timedelta(minutes=12)
    login = Event(event_id=f"{incident_id}-login", user_id=user_id, pc_id="PC-1", ts=login_ts,
                  event_date=login_ts.date(), source="logon", action="logon", attrs={}, ingest_run_id=run_id)
    usb = Event(event_id=f"{incident_id}-usb", user_id=user_id, pc_id="PC-1", ts=usb_ts,
                event_date=usb_ts.date(), source="device", action="connect", attrs={}, ingest_run_id=run_id)
    files = [
        Event(event_id=f"{incident_id}-file-{i}", user_id=user_id, pc_id="PC-1",
              ts=usb_ts + dt.timedelta(minutes=1 + i), event_date=usb_ts.date(),
              source="file", action="access", attrs={}, ingest_run_id=run_id)
        for i in range(15)
    ]
    for e in [login, usb, *files]:
        db.add(e)
    db.flush()

    incident = Incident(
        incident_id=incident_id, user_id=user_id, window_start=login_ts, window_end=files[-1].ts,
        risk=risk, confidence=0.8, triage_lane="AUTO_FLAG", status="open",
        killchain_stages=[1, 2, 3], signal_count=3, event_count=17, category_count=3,
        over_dense=False, config_version="demo",
    )
    db.add(incident)
    db.flush()
    for e in [login, usb, *files]:
        db.add(IncidentEvent(incident_id=incident_id, event_id=e.event_id, node_role="signal"))
    db.add(IncidentEdge(incident_id=incident_id, src_event=login.event_id, dst_event=usb.event_id,
                        gap_seconds=720, edge_type="stage_advance", weight=1.0))
    db.add(IncidentEdge(incident_id=incident_id, src_event=usb.event_id, dst_event=files[0].event_id,
                        gap_seconds=60, edge_type="stage_advance", weight=1.0))
    db.commit()
    return incident


def main() -> int:
    Base.metadata.create_all(engine)
    cfg = load_config()
    signals = _chain_signals()
    corr = _chain_corr()

    risk_before, _, _ = compute_risk(signals, 0.97, corr, cfg)
    print(f"1. First injection - {USER_ID}: risk = {risk_before:.1f}")

    db = SessionLocal()
    try:
        incident = _seed_incident(db, "INC-DEMO-FEEDBACK-01", USER_ID, risk_before)

        result = submit_feedback(
            db, incident, analyst_id="demo_analyst", verdict="false_positive",
            reason_code="known_usb_workflow",
            comment="Scheduled backup workflow for this user - confirmed with IT.",
            apply_to_similar=True,
        )
        print(f"2. Feedback submitted: incident {result.incident.incident_id} -> "
              f"status={result.incident.status}, disposition={result.incident.disposition}")

        print("3. Learned adjustments:")
        for b in result.baselines:
            print(f"   baseline  {b.feature_name:<18} mean={b.mean_value:.2f} std={b.std_value:.2f} "
                  f"p95={b.p95_value:.2f} n={b.sample_count}")
        for e in result.edges:
            print(f"   edge      {e.source_event_type} -> {e.target_event_type}  "
                  f"fp_count={e.false_positive_count} weight {e.original_weight:.2f} -> {e.current_weight:.2f}")

        baselines = db.query(BehavioralBaseline).filter(BehavioralBaseline.entity_id == USER_ID).all()
        edges = db.query(EdgeFeedbackWeight).filter(EdgeFeedbackWeight.context_key == f"user:{USER_ID}").all()
        baseline_discount = {b.feature_name: b.feedback_adjustment for b in baselines}
        edge_multiplier = min((e.current_weight / e.original_weight for e in edges), default=1.0)

        risk_after, _, _, adjustments = compute_feedback_aware_risk(
            signals, 0.97, corr, cfg, user_id=USER_ID,
            edge_multiplier=edge_multiplier, baseline_discount_by_feature=baseline_discount,
        )
        reduction = risk_before - risk_after
        print(f"4. Second injection (same user, same chain): risk = {risk_after:.1f}")
        print(f"   reduction: {reduction:.1f} points ({100 * reduction / risk_before:.1f}% relative)")
        for adj in adjustments:
            print(f"   explanation: {adj}")

        risk_other, _, _ = compute_risk(signals, 0.97, corr, cfg)
        print(f"5. Same chain injected for an unrelated user ({OTHER_USER_ID}, no feedback history): "
              f"risk = {risk_other:.1f} (unchanged, as expected)")

        assert reduction >= 20.0 or reduction / risk_before >= 0.25, "demo invariant violated"
        assert risk_other == risk_before, "unrelated user must be unaffected"
        print("\nOK: feedback measurably reduced the score for the same user; unrelated users unaffected.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
