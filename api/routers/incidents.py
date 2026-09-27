from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config_snapshot import get_rule, load_detection_config
from api.deps import get_current_account, get_db
from api.models.correlation import Campaign, Incident, IncidentEdge, IncidentEvent
from api.models.detection import Signal, UserDayScore
from api.models.explain import Attribution, Narrative
from api.models.feedback import Review, Suppression
from api.models.features import UserDayFeature
from api.models.identity import User, UserOrg
from api.models.ingest import Event
from api.models.mitigation import MitigationAction
from api.assistant import AssistantUnavailable, answer_incident_question
from api.schemas.incidents import (
    AskRequest,
    AskResponse,
    AttributionItemOut,
    AttributionOut,
    CampaignRef,
    ConfidenceTerms,
    GraphEdgeOut,
    GraphNodeOut,
    GraphStats,
    IncidentDetailOut,
    IncidentGraphOut,
    IncidentListItem,
    IncidentListResponse,
    MitigationActionOut,
    NarrativeOut,
    ReviewEffects,
    ReviewOut,
    ReviewRequest,
    ReviewResponse,
    ScoreBreakdown,
    ScoreOut,
    SignalDetailOut,
    UserRef,
)
from api.security.audit import write_audit

router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(get_current_account)])


def _get_incident_or_404(db: Session, incident_id: str) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"No incident with id {incident_id}")
    return incident


def _build_score_out(db: Session, incident: Incident, signals_out: list[SignalDetailOut]) -> ScoreOut:
    """docs/04-DETECTION-ENGINE.md section 4: risk is scored per user-day, so
    the breakdown for a (typically single-day) incident is read back from that
    day's user_day_scores row. prior_logit/tau are scoring constants, not
    per-day outputs, so they come from config/detection.yaml directly.
    confidence_terms.agreement/diversity are recomputed here from the
    incident's own signal mix (docs/04 section 4.3's formula) since only the
    two baseline-derived terms are persisted per user-day; this mirrors the
    documented rule rather than re-deriving Track A's canonical confidence
    engine.
    """
    detection_cfg = load_detection_config()["scoring"]
    confidence_cfg = load_detection_config()["confidence"]

    day_score = db.get(UserDayScore, {"user_id": incident.user_id, "event_date": incident.window_start.date()})
    feature_row = db.get(UserDayFeature, {"user_id": incident.user_id, "event_date": incident.window_start.date()})

    breakdown = ScoreBreakdown(
        prior_logit=detection_cfg["prior_logit"],
        rule_points=day_score.rule_points if day_score else 0.0,
        ml_points=day_score.ml_points if day_score else 0.0,
        correlation_points=day_score.corr_points if day_score else 0.0,
        total_logit=day_score.logit if day_score else 0.0,
        tau=detection_cfg["tau"],
    )

    categories = {s.category for s in signals_out}
    has_ml = any(s.rule_id == "ml.isoforest" for s in signals_out)
    has_rule = any(s.rule_id != "ml.isoforest" for s in signals_out)
    if has_ml and has_rule:
        agreement = confidence_cfg["agreement_both"]
    elif has_rule:
        agreement = confidence_cfg["agreement_rules_only"]
    elif has_ml:
        agreement = confidence_cfg["agreement_ml_only"]
    else:
        agreement = 0.0
    diversity = min(1.0, len(categories) / confidence_cfg["diversity_target_categories"]) if categories else 0.0

    caps: list[str] = []
    maturity = feature_row.baseline_maturity if feature_row else 0.0
    if maturity < 0.5:
        caps.append("cap_immature_baseline")
    if len(signals_out) <= 1:
        caps.append("cap_single_signal")

    return ScoreOut(
        risk=incident.risk,
        confidence=incident.confidence,
        triage_lane=incident.triage_lane,
        breakdown=breakdown,
        confidence_terms=ConfidenceTerms(
            agreement=agreement,
            diversity=diversity,
            completeness=feature_row.data_completeness if feature_row else 0.0,
            maturity=maturity,
            caps_applied=caps,
        ),
    )


def _rule_name(rule_id: str) -> str:
    if rule_id == "ml.isoforest":
        return "Anomaly detector (IsolationForest)"
    rule = get_rule(rule_id)
    return rule["name"] if rule else rule_id


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    lane: str | None = None,
    status: str | None = None,
    min_risk: float | None = None,
    min_confidence: float | None = None,
    user_id: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    stage_max: int | None = None,
    campaign_id: str | None = None,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    stmt = select(Incident)
    if lane:
        stmt = stmt.where(Incident.triage_lane == lane)
    if status:
        stmt = stmt.where(Incident.status == status)
    if min_risk is not None:
        stmt = stmt.where(Incident.risk >= min_risk)
    if min_confidence is not None:
        stmt = stmt.where(Incident.confidence >= min_confidence)
    if user_id:
        stmt = stmt.where(Incident.user_id == user_id)
    if date_from:
        stmt = stmt.where(func.date(Incident.window_start) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(Incident.window_start) <= date_to)
    if campaign_id:
        stmt = stmt.where(Incident.campaign_id == campaign_id)

    incidents = db.scalars(stmt.order_by(Incident.risk.desc())).all()
    if stage_max is not None:
        incidents = [i for i in incidents if not i.killchain_stages or max(i.killchain_stages) <= stage_max]

    lane_facets: dict[str, int] = {}
    stage_facets: dict[str, int] = {}
    for i in incidents:
        lane_facets[i.triage_lane] = lane_facets.get(i.triage_lane, 0) + 1
        ms = max(i.killchain_stages) if i.killchain_stages else 0
        stage_facets[str(ms)] = stage_facets.get(str(ms), 0) + 1

    items: list[IncidentListItem] = []
    for incident in incidents[:limit]:
        user = db.get(User, incident.user_id)
        org = db.scalar(
            select(UserOrg)
            .where(UserOrg.user_id == incident.user_id, UserOrg.valid_from <= incident.window_start.date())
            .order_by(UserOrg.valid_from.desc())
        )
        narrative = db.get(Narrative, incident.incident_id)
        top_attr = db.scalar(
            select(Attribution)
            .where(Attribution.incident_id == incident.incident_id)
            .order_by(Attribution.rank.asc())
            .limit(1)
        )
        top_signal = None
        if top_attr is not None:
            sig = db.get(Signal, top_attr.signal_id)
            if sig is not None:
                top_signal = {"rule_id": sig.rule_id, "delta": top_attr.delta}

        items.append(
            IncidentListItem(
                incident_id=incident.incident_id,
                user_id=incident.user_id,
                user_name=(user.employee_name if user else incident.user_id) or incident.user_id,
                department=org.department if org else "",
                window={"start": incident.window_start, "end": incident.window_end},
                risk=incident.risk,
                confidence=incident.confidence,
                triage_lane=incident.triage_lane,
                status=incident.status,
                headline=narrative.headline if narrative else "",
                killchain_stages=incident.killchain_stages,
                max_stage=max(incident.killchain_stages) if incident.killchain_stages else 0,
                signal_count=incident.signal_count,
                event_count=incident.event_count,
                campaign_id=incident.campaign_id,
                top_signal=top_signal,
            )
        )

    return IncidentListResponse(
        items=items,
        next_cursor=None,
        total=len(incidents),
        facets={"lane": lane_facets, "max_stage": stage_facets},
    )


def _build_signal_out(signal: Signal) -> SignalDetailOut:
    return SignalDetailOut(
        signal_id=signal.signal_id,
        rule_id=signal.rule_id,
        name=_rule_name(signal.rule_id),
        category=signal.category,
        stage=signal.killchain_stage,
        strength=signal.strength,
        weight=signal.weight,
        contribution=signal.contribution,
        phrase=signal.phrase,
        detail=signal.detail,
        evidence_event_ids=signal.evidence_event_ids,
        references=[],
    )


@router.get("/{incident_id}", response_model=IncidentDetailOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> IncidentDetailOut:
    incident = _get_incident_or_404(db, incident_id)
    user = db.get(User, incident.user_id)
    org = db.scalar(
        select(UserOrg)
        .where(UserOrg.user_id == incident.user_id, UserOrg.valid_from <= incident.window_start.date())
        .order_by(UserOrg.valid_from.desc())
    )
    cohort_size = 0
    if org is not None:
        cohort_size = db.scalar(
            select(func.count()).select_from(UserOrg).where(UserOrg.cohort_key == org.cohort_key)
        ) or 0

    narrative = db.get(Narrative, incident_id)
    attributions = db.scalars(
        select(Attribution).where(Attribution.incident_id == incident_id).order_by(Attribution.rank.asc())
    ).all()
    signal_by_id = {
        s.signal_id: s
        for s in db.scalars(
            select(Signal).where(Signal.signal_id.in_([a.signal_id for a in attributions]))
        ).all()
    }

    signals_out = [_build_signal_out(signal_by_id[a.signal_id]) for a in attributions if a.signal_id in signal_by_id]
    attribution_items = [
        AttributionItemOut(
            signal_id=a.signal_id,
            rule_id=signal_by_id[a.signal_id].rule_id if a.signal_id in signal_by_id else "",
            risk_without=a.risk_without,
            delta=a.delta,
            rank=a.rank,
            in_minimal_set=a.in_minimal_set,
        )
        for a in attributions
    ]
    minimal_set = [item.rule_id for item in attribution_items if item.in_minimal_set]

    campaign_ref = None
    if incident.campaign_id:
        campaign = db.get(Campaign, incident.campaign_id)
        if campaign is not None:
            campaign_ref = CampaignRef(
                campaign_id=campaign.campaign_id,
                incident_count=campaign.incident_count,
                first_seen=campaign.first_seen,
                last_seen=campaign.last_seen,
                stage_progression=campaign.stage_progression,
            )

    latest_review = db.scalar(
        select(Review).where(Review.incident_id == incident_id).order_by(Review.reviewed_at.desc())
    )

    mitigations_out = [
        MitigationActionOut.model_validate(m)
        for m in db.scalars(
            select(MitigationAction)
            .where(MitigationAction.incident_id == incident_id)
            .order_by(MitigationAction.created_at.desc())
        ).all()
    ]

    return IncidentDetailOut(
        incident_id=incident.incident_id,
        user=UserRef(
            user_id=incident.user_id,
            name=(user.employee_name if user else incident.user_id) or incident.user_id,
            role=org.role if org else "",
            department=org.department if org else "",
            cohort_size=cohort_size,
        ),
        window={
            "start": incident.window_start,
            "end": incident.window_end,
            "duration_min": round((incident.window_end - incident.window_start).total_seconds() / 60, 1),
        },
        score=_build_score_out(db, incident, signals_out),
        narrative=NarrativeOut(
            headline=narrative.headline if narrative else "",
            summary=narrative.summary if narrative else "",
            detail_bullets=narrative.detail.split("\n") if narrative and narrative.detail else [],
            template_ids=narrative.template_ids if narrative else [],
        ),
        signals=signals_out,
        attribution=AttributionOut(
            note="Contributions overlap due to category saturation and the correlation bonus; they do not sum to the total.",
            items=attribution_items,
            minimal_sufficient_set=minimal_set,
            alert_threshold=40.0,
        ),
        campaign=campaign_ref,
        status=incident.status,
        review=ReviewOut(
            review_id=latest_review.review_id, verdict=latest_review.verdict, note=latest_review.note,
            analyst_id=latest_review.analyst_id, reviewed_at=latest_review.reviewed_at,
        ) if latest_review else None,
        mitigations=mitigations_out,
        config_version=incident.config_version,
        links={
            "graph": f"/api/v1/incidents/{incident_id}/graph",
            "export": f"/api/v1/incidents/{incident_id}/export",
        },
    )


@router.get("/{incident_id}/graph", response_model=IncidentGraphOut)
def get_incident_graph(incident_id: str, db: Session = Depends(get_db)) -> IncidentGraphOut:
    incident = _get_incident_or_404(db, incident_id)
    links = db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == incident_id)).all()
    events = {
        e.event_id: e
        for e in db.scalars(select(Event).where(Event.event_id.in_([link.event_id for link in links]))).all()
    }
    signals = db.scalars(select(Signal).where(Signal.user_id == incident.user_id)).all()
    signaled_event_ids: set[str] = set()
    for s in signals:
        signaled_event_ids.update(s.evidence_event_ids)

    nodes = [
        GraphNodeOut(
            id=event.event_id,
            ts=event.ts,
            source=event.source,
            action=event.action,
            label=f"{event.action} {event.pc_id or ''}".strip(),
            stage=None,
            risk_contribution=0.0,
            has_signal=event.event_id in signaled_event_ids,
            pc_id=event.pc_id,
            user_id=event.user_id,
        )
        for event in sorted(events.values(), key=lambda e: e.ts)
    ]

    edges_rows = db.scalars(select(IncidentEdge).where(IncidentEdge.incident_id == incident_id)).all()
    edges = [
        GraphEdgeOut(
            source=edge.src_event,
            target=edge.dst_event,
            gap_seconds=edge.gap_seconds,
            gap_label=f"{edge.gap_seconds // 60} min" if edge.gap_seconds >= 60 else f"{edge.gap_seconds} s",
            type=edge.edge_type,
            weight=edge.weight,
        )
        for edge in edges_rows
    ]

    return IncidentGraphOut(
        incident_id=incident_id,
        over_dense=incident.over_dense,
        nodes=nodes,
        edges=edges,
        layout_hint="temporal_left_to_right",
        stats=GraphStats(node_count=len(nodes), edge_count=len(edges), component_diameter=0),
    )


@router.post("/{incident_id}/ask", response_model=AskResponse)
def ask_about_incident(incident_id: str, payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    """Grounded Q&A over one incident's already-computed evidence (ADR 0004's
    "optional v2 gloss" - never the authoritative record, which stays the
    deterministic narrative). Failures degrade to a clear 503, never a 500 -
    a flaky external call must not take down the incident page the rest of
    the demo depends on."""
    detail = get_incident(incident_id, db)
    try:
        answer = answer_incident_question(detail, payload.question)
    except AssistantUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"assistant unavailable: {exc}")
    return AskResponse(answer=answer)


@router.get("/{incident_id}/export")
def export_incident(incident_id: str, format: str = "json", db: Session = Depends(get_db)):
    if format != "json":
        raise HTTPException(status_code=400, detail="only format=json is implemented")
    detail = get_incident(incident_id, db)
    return {
        "incident": detail.model_dump(mode="json"),
        "watermark": {"exported_at": dt.datetime.now(dt.timezone.utc).isoformat(), "exported_by": "system"},
    }


@router.post("/{incident_id}/review", response_model=ReviewResponse, status_code=201)
def review_incident(
    incident_id: str,
    payload: ReviewRequest,
    force: bool = False,
    db: Session = Depends(get_db),
) -> ReviewResponse:
    incident = _get_incident_or_404(db, incident_id)
    if incident.status == "closed" and not force:
        raise HTTPException(status_code=409, detail="incident is already closed")

    review = Review(
        incident_id=incident_id,
        verdict=payload.verdict,
        note=payload.note,
        analyst_id=payload.analyst_id,
        time_to_triage_sec=payload.time_to_triage_sec,
    )
    db.add(review)
    db.flush()  # assigns review.review_id, needed below for suppressions.source_review

    incident.status = "closed" if payload.verdict != "inconclusive" else "in_review"

    suppression_out = None
    if payload.verdict == "benign" and payload.propose_suppression is not None:
        prop = payload.propose_suppression
        suppression = Suppression(
            scope=prop.scope,
            user_id=prop.user_id,
            cohort_key=prop.cohort_key,
            rule_id=prop.rule_id,
            reason=f"Proposed from incident {incident_id} review by {payload.analyst_id}",
            source_review=review.review_id,
            created_by=payload.analyst_id,
            expires_at=prop.expires_at,
        )
        db.add(suppression)
        db.flush()
        suppression_out = {"suppression_id": suppression.suppression_id, "status": suppression.status}

    write_audit(
        db, actor=payload.analyst_id, action="incident_review", object_type="incident", object_id=incident_id,
        after={"verdict": payload.verdict, "status": incident.status},
    )
    db.commit()
    db.refresh(review)

    rule_ids = db.scalars(
        select(Signal.rule_id)
        .join(Attribution, Attribution.signal_id == Signal.signal_id)
        .where(Attribution.incident_id == incident_id)
    ).all()

    return ReviewResponse(
        review_id=review.review_id,
        incident_id=incident_id,
        verdict=review.verdict,
        reviewed_at=review.reviewed_at,
        incident_status=incident.status,
        suppression=suppression_out,
        effects=ReviewEffects(rule_stats_updated=sorted(set(rule_ids)), user_risk_ewma_adjusted=False),
    )
