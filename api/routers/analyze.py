from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.correlation import Incident
from api.models.detection import Signal, UserDayScore
from api.models.identity import User
from api.schemas.analyze import AnalyzeDailyPoint, AnalyzeRequest, AnalyzeResponse

router = APIRouter(tags=["analyze"], dependencies=[Depends(get_current_account)])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
    if db.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail=f"No user with id {payload.user_id}")

    if payload.options.force_recompute:
        # Recomputing on demand means re-running engine/detect/scoring.py
        # against the current config, per docs/05 section 9. That module is
        # Track A's and does not exist yet in this build, so honestly report
        # the dependency as unavailable rather than silently serving a cached
        # result under a "recomputed" label.
        raise HTTPException(
            status_code=503,
            detail="force_recompute requires the detection engine, which is not available in this build",
        )

    start = time.perf_counter()

    scores = db.scalars(
        select(UserDayScore)
        .where(
            UserDayScore.user_id == payload.user_id,
            UserDayScore.event_date >= payload.date_from,
            UserDayScore.event_date <= payload.date_to,
        )
        .order_by(UserDayScore.event_date)
    ).all()

    daily = []
    for score in scores:
        signal_count = db.scalar(
            select(func.count())
            .select_from(Signal)
            .where(Signal.user_id == payload.user_id, Signal.event_date == score.event_date)
        ) or 0
        daily.append(AnalyzeDailyPoint(date=score.event_date, risk=score.risk, confidence=score.confidence, signal_count=signal_count))

    incident_ids = db.scalars(
        select(Incident.incident_id).where(
            Incident.user_id == payload.user_id,
            func.date(Incident.window_start) >= payload.date_from,
            func.date(Incident.window_start) <= payload.date_to,
        )
    ).all()
    campaign_ids = sorted(
        {
            c
            for c in db.scalars(
                select(Incident.campaign_id).where(Incident.incident_id.in_(incident_ids), Incident.campaign_id.is_not(None))
            ).all()
        }
    )

    peak_risk = max((d.risk for d in daily), default=0.0)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return AnalyzeResponse(
        user_id=payload.user_id,
        window={"from": payload.date_from, "to": payload.date_to},
        computed_in_ms=round(elapsed_ms, 2),
        from_cache=True,
        peak_risk=peak_risk,
        incidents=list(incident_ids),
        campaigns=campaign_ids,
        daily=daily,
        narrative=None,
    )
