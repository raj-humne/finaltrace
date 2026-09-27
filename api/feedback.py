"""Analyst Feedback Loop for False-Positive Reduction (Challenge 2).

Mirrors api/mitigation.py's shape: one entry point (`submit_feedback`) that
does everything in a single DB transaction - record the analyst's verdict,
close/dismiss the incident, use Pandas to recompute this user's behavioral
baseline for the incident's own numeric features, decay the user-scoped
graph-correlation edge weights for the incident's evidence chain, and return
a bounded, explainable prediction of how this same chain would score if
re-injected (spec B's `score_impact`).

Nothing here mutates `events`, `signals`, or `attributions` - raw evidence
stays exactly as originally detected (constraint: "keep raw events and
original incident evidence immutable"). Only the new, additive feedback
tables plus `incidents.status`/`disposition`/... change.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models.analyst_feedback import AnalystFeedback, BehavioralBaseline, EdgeFeedbackWeight, FeatureObservation
from api.models.correlation import Incident, IncidentEdge, IncidentEvent
from api.models.ingest import Event
from api.security.audit import write_audit
from engine.feedback.baseline import recalculate_baseline
from engine.feedback.edge_weights import edge_weight_multiplier

# The minimum numeric feature set spec C requires, extracted directly from
# the incident's own linked events - never fabricated, never read from a
# different incident.
FEATURE_NAMES = ("file_access_count", "event_count", "unique_hosts", "usb_insert_count", "login_count")

# api/mitigation.py has no analogous "no prior weight" case (an incident's
# `risk` is always already computed); a graph edge has no persisted "original
# weight" concept outside engine.correlate.graph's per-edge-type constants
# (0.8 shared_pc, 0.9 shared_file, 1.0 stage_advance, exp-decay temporal), so
# a single, documented default is used here for the learned-edge original
# weight when this exact (source, target) pair has never been scored before.
DEFAULT_EDGE_ORIGINAL_WEIGHT = 1.0


class FeedbackError(Exception):
    """Base class for feedback-submission failures the router translates to HTTP."""


class IncidentAlreadyDismissed(FeedbackError):
    """409: this incident already has a false_positive disposition."""


@dataclass
class BaselineUpdate:
    feature_name: str
    mean_value: float
    std_value: float
    p95_value: float
    sample_count: int


@dataclass
class EdgeUpdate:
    source_event_type: str
    target_event_type: str
    false_positive_count: int
    original_weight: float
    current_weight: float


@dataclass
class ScoreImpact:
    original_risk: float
    predicted_similar_risk: float
    expected_reduction: float


@dataclass
class FeedbackResult:
    feedback: AnalystFeedback
    incident: Incident
    baselines: list[BaselineUpdate]
    edges: list[EdgeUpdate]
    score_impact: ScoreImpact


def _extract_incident_features(db: Session, incident: Incident) -> dict[str, float]:
    """Numeric behavioral features for this incident's own event chain (spec
    C), read from the same IncidentEvent/Event rows the incident detail page
    and the graph endpoint already use - not a separate/duplicated read path."""
    links = db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == incident.incident_id)).all()
    event_ids = [link.event_id for link in links]
    events = db.scalars(select(Event).where(Event.event_id.in_(event_ids))).all() if event_ids else []

    return {
        "file_access_count": float(sum(1 for e in events if e.source == "file")),
        "event_count": float(len(events)),
        "unique_hosts": float(len({e.pc_id for e in events if e.pc_id})),
        "usb_insert_count": float(sum(1 for e in events if e.source == "device" and e.action == "connect")),
        "login_count": float(sum(1 for e in events if e.source == "logon" and e.action == "logon")),
    }


def _trusted_history(db: Session, user_id: str, feature_name: str, exclude_incident: str) -> list[float]:
    stmt = select(FeatureObservation.feature_value).where(
        FeatureObservation.entity_type == "user",
        FeatureObservation.entity_id == user_id,
        FeatureObservation.feature_name == feature_name,
        FeatureObservation.is_trusted.is_(True),
        FeatureObservation.source_incident_id != exclude_incident,
    )
    return [float(v) for v in db.scalars(stmt).all()]


def _update_baselines(db: Session, incident: Incident, apply_to_similar: bool) -> list[BaselineUpdate]:
    features = _extract_incident_features(db, incident)
    updates: list[BaselineUpdate] = []
    now = dt.datetime.now(dt.timezone.utc)

    for feature_name, value in features.items():
        # Recorded regardless of apply_to_similar (complete audit trail) -
        # only `is_trusted` (whether it ever feeds a future baseline
        # recompute) depends on the analyst's checkbox.
        db.add(FeatureObservation(
            entity_type="user", entity_id=incident.user_id, feature_name=feature_name,
            feature_value=value, observed_at=now,
            source_incident_id=incident.incident_id, is_trusted=apply_to_similar,
        ))

        if not apply_to_similar:
            continue

        history = _trusted_history(db, incident.user_id, feature_name, exclude_incident=incident.incident_id)
        existing = db.scalar(
            select(BehavioralBaseline).where(
                BehavioralBaseline.entity_type == "user",
                BehavioralBaseline.entity_id == incident.user_id,
                BehavioralBaseline.feature_name == feature_name,
            )
        )
        prev_mean = existing.mean_value if existing else None
        prev_std = existing.std_value if existing else None

        stats = recalculate_baseline(history, value, prev_mean, prev_std)

        # Track how much *this event* actually widened tolerance, for the
        # cumulative `feedback_adjustment` explainability field (engine/
        # feedback/scoring_adjust.py reads this to discount future rule
        # strength for this feature). The spec's 25%-per-event growth cap
        # applies to widening an *existing* baseline (`prev_std` set) - it
        # protects against a baseline being blown out by many small
        # feedback events. A feature's very first trusted observation has no
        # prior baseline to cap against; the analyst is telling the system,
        # for the first time, that this exact value is legitimate for this
        # user, so it gets a larger initial trust bump (bounded at 0.5, well
        # under the 1.0 ceiling) rather than the same small step future
        # (already-established) baselines are limited to.
        if prev_std and prev_std > 0:
            relative_std_bump = max(0.0, min(0.25, (stats["std"] - prev_std) / prev_std))
            prev_adjustment = existing.feedback_adjustment if existing else 0.0
            new_adjustment = min(1.0, prev_adjustment + relative_std_bump)
        else:
            new_adjustment = 0.5

        if existing:
            existing.mean_value = stats["mean"]
            existing.std_value = stats["std"]
            existing.p95_value = stats["p95"]
            existing.sample_count = stats["sample_count"]
            existing.feedback_adjustment = new_adjustment
            existing.updated_at = now
        else:
            db.add(BehavioralBaseline(
                entity_type="user", entity_id=incident.user_id, feature_name=feature_name,
                mean_value=stats["mean"], std_value=stats["std"], p95_value=stats["p95"],
                sample_count=stats["sample_count"], feedback_adjustment=new_adjustment, updated_at=now,
            ))
        updates.append(BaselineUpdate(feature_name, stats["mean"], stats["std"], stats["p95"], stats["sample_count"]))

    db.flush()
    return updates


def _incident_edge_type_pairs(db: Session, incident: Incident) -> list[tuple[str, str]]:
    """Adjacent event-type pairs along the dismissed incident's real,
    already-persisted evidence chain (spec D) - `"{source}.{action}"` per
    event, ordered chronologically along each stored IncidentEdge."""
    edges = db.scalars(select(IncidentEdge).where(IncidentEdge.incident_id == incident.incident_id)).all()
    if not edges:
        return []
    event_ids = {e.src_event for e in edges} | {e.dst_event for e in edges}
    events_by_id = {e.event_id: e for e in db.scalars(select(Event).where(Event.event_id.in_(event_ids))).all()}

    pairs: list[tuple[str, str]] = []
    for edge in edges:
        src = events_by_id.get(edge.src_event)
        dst = events_by_id.get(edge.dst_event)
        if src is None or dst is None:
            continue
        first, second = (src, dst) if src.ts <= dst.ts else (dst, src)
        pairs.append((f"{first.source}.{first.action}", f"{second.source}.{second.action}"))
    return pairs


def _update_edges(db: Session, incident: Incident) -> list[EdgeUpdate]:
    context_key = f"user:{incident.user_id}"
    now = dt.datetime.now(dt.timezone.utc)
    updates: list[EdgeUpdate] = []

    for source_type, target_type in sorted(set(_incident_edge_type_pairs(db, incident))):
        row = db.scalar(
            select(EdgeFeedbackWeight).where(
                EdgeFeedbackWeight.source_event_type == source_type,
                EdgeFeedbackWeight.target_event_type == target_type,
                EdgeFeedbackWeight.context_key == context_key,
            )
        )
        if row is None:
            row = EdgeFeedbackWeight(
                source_event_type=source_type, target_event_type=target_type, context_key=context_key,
                original_weight=DEFAULT_EDGE_ORIGINAL_WEIGHT, current_weight=DEFAULT_EDGE_ORIGINAL_WEIGHT,
                false_positive_count=0,
            )
            db.add(row)

        row.false_positive_count += 1
        row.current_weight = row.original_weight * edge_weight_multiplier(row.false_positive_count)
        row.last_feedback_at = now
        row.updated_at = now
        updates.append(EdgeUpdate(source_type, target_type, row.false_positive_count, row.original_weight, row.current_weight))

    db.flush()
    return updates


def _estimate_score_impact(original_risk: float, edges: list[EdgeUpdate], baselines: list[BaselineUpdate]) -> ScoreImpact:
    """A deterministic, explainable preview returned inline with the API
    response (spec B) - not a second full run of engine.run.Pipeline (that
    needs the entire features/events corpus, which a single feedback request
    does not carry). The real, full-pipeline proof that re-injecting the same
    chain scores lower lives in tests/test_feedback_scoring.py, which drives
    engine.feedback.scoring_adjust.compute_feedback_aware_risk - the exact
    function engine.correlate.incident would call for a real re-score - with
    the multipliers this function is only summarizing.
    """
    edge_multiplier = min((e.current_weight / e.original_weight for e in edges if e.original_weight), default=1.0)
    # Baselines mainly affect *future* z-scores (see engine/feedback/
    # scoring_adjust.py for the real per-signal mechanism), not a fixed
    # points discount at feedback time, so this preview applies a fixed,
    # conservative extra shrinkage whenever at least one baseline was
    # updated - a deliberately conservative (lower-bound) estimate.
    baseline_factor = 0.9 if baselines else 1.0

    predicted = original_risk * edge_multiplier * baseline_factor
    predicted = max(0.0, round(predicted, 2))
    reduction = round(original_risk - predicted, 2)
    return ScoreImpact(original_risk=round(original_risk, 2), predicted_similar_risk=predicted, expected_reduction=reduction)


def submit_feedback(
    db: Session,
    incident: Incident,
    *,
    analyst_id: str,
    verdict: str,
    reason_code: str,
    comment: str | None,
    apply_to_similar: bool,
) -> FeedbackResult:
    if incident.disposition == "false_positive":
        raise IncidentAlreadyDismissed(f"incident {incident.incident_id} was already dismissed as a false positive")

    original_status = incident.status
    original_risk = incident.risk

    feedback = AnalystFeedback(
        incident_id=incident.incident_id, analyst_id=analyst_id, verdict=verdict,
        reason_code=reason_code, comment=comment, apply_to_similar=apply_to_similar,
    )
    db.add(feedback)
    db.flush()  # assigns feedback.id

    baselines = _update_baselines(db, incident, apply_to_similar)
    edges = _update_edges(db, incident) if apply_to_similar else []

    incident.status = "closed"
    incident.disposition = "false_positive"
    incident.disposition_reason = reason_code
    incident.dismissed_at = dt.datetime.now(dt.timezone.utc)
    incident.dismissed_by = analyst_id

    score_impact = _estimate_score_impact(original_risk, edges, baselines)

    write_audit(
        db, actor=analyst_id, action="incident_feedback", object_type="incident", object_id=incident.incident_id,
        before={"status": original_status, "disposition": None, "risk": original_risk},
        after={
            "status": incident.status, "disposition": incident.disposition, "reason_code": reason_code,
            "apply_to_similar": apply_to_similar, "predicted_similar_risk": score_impact.predicted_similar_risk,
        },
    )
    db.commit()
    db.refresh(incident)
    db.refresh(feedback)

    return FeedbackResult(feedback=feedback, incident=incident, baselines=baselines, edges=edges, score_impact=score_impact)
