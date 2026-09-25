from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.correlation import Incident
from api.models.detection import Signal, UserDayScore
from api.models.identity import User, UserOrg
from api.models.ingest import Event
from api.schemas.users import (
    BaselineOut,
    IncidentCounts,
    PeerBandPoint,
    RiskSeriesPoint,
    RiskSummary,
    TimelineEvent,
    TimelineResponse,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
    UserOrgOut,
    UserRiskResponse,
)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_account)])


def _current_org(db: Session, user_id: str, as_of: dt.date | None = None) -> UserOrg | None:
    as_of = as_of or dt.date.today()
    return db.scalar(
        select(UserOrg)
        .where(UserOrg.user_id == user_id, UserOrg.valid_from <= as_of, UserOrg.valid_to > as_of)
        .order_by(UserOrg.valid_from.desc())
    )


def _latest_score(db: Session, user_id: str) -> UserDayScore | None:
    return db.scalar(
        select(UserDayScore).where(UserDayScore.user_id == user_id).order_by(UserDayScore.event_date.desc())
    )


def _trend(scores: list[UserDayScore]) -> str:
    if len(scores) < 2:
        return "stable"
    delta = scores[-1].risk - scores[-2].risk
    if delta > 5:
        return "rising"
    if delta < -5:
        return "falling"
    return "stable"


def _incident_counts_by_lane(db: Session, user_id: str) -> IncidentCounts:
    """Lifetime count of this user's incidents per triage lane (all statuses).
    Distinct from the queue-facing `open_incidents` count, which is status-filtered."""
    rows = db.execute(
        select(Incident.triage_lane, func.count())
        .where(Incident.user_id == user_id)
        .group_by(Incident.triage_lane)
    ).all()
    counts = IncidentCounts()
    for lane, n in rows:
        setattr(counts, lane, n)
    return counts


@router.get("", response_model=UserListResponse)
def list_users(
    q: str | None = None,
    department: str | None = None,
    role: str | None = None,
    min_risk: float | None = None,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
) -> UserListResponse:
    users = db.scalars(select(User).order_by(User.user_id)).all()
    items: list[UserListItem] = []
    for user in users:
        org = _current_org(db, user.user_id, user.last_seen)
        if org is None:
            continue
        if department and org.department != department:
            continue
        if role and org.role != role:
            continue
        if q and q.lower() not in (user.employee_name or "").lower() and q.lower() not in user.user_id.lower():
            continue

        scores = db.scalars(
            select(UserDayScore).where(UserDayScore.user_id == user.user_id).order_by(UserDayScore.event_date)
        ).all()
        current_risk = scores[-1].risk if scores else 0.0
        if min_risk is not None and current_risk < min_risk:
            continue
        risk_ewma = scores[-1].risk_ewma if scores and scores[-1].risk_ewma is not None else current_risk
        open_incidents = db.scalar(
            select(func.count()).select_from(Incident).where(Incident.user_id == user.user_id, Incident.status != "closed")
        ) or 0
        departing_in_days = None
        if user.departure_date:
            departing_in_days = (user.departure_date - user.last_seen).days

        items.append(
            UserListItem(
                user_id=user.user_id,
                name=user.employee_name or user.user_id,
                role=org.role,
                department=org.department,
                cohort_key=org.cohort_key,
                current_risk=current_risk,
                risk_ewma=risk_ewma,
                trend=_trend(scores),
                open_incidents=open_incidents,
                departing_in_days=departing_in_days,
            )
        )
        if len(items) >= limit:
            break

    return UserListResponse(items=items, next_cursor=None, total=len(items))


@router.get("/{user_id}", response_model=UserDetailResponse)
def get_user(user_id: str, db: Session = Depends(get_db)) -> UserDetailResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"No user with id {user_id}")
    org = _current_org(db, user_id, user.last_seen)
    if org is None:
        raise HTTPException(status_code=404, detail=f"No org record for user {user_id}")

    cohort_size = db.scalar(select(func.count()).select_from(UserOrg).where(UserOrg.cohort_key == org.cohort_key)) or 0

    scores = db.scalars(
        select(UserDayScore).where(UserDayScore.user_id == user_id).order_by(UserDayScore.event_date)
    ).all()
    current_risk = scores[-1].risk if scores else 0.0
    risk_ewma = scores[-1].risk_ewma if scores and scores[-1].risk_ewma is not None else current_risk

    days_available = len(scores)
    # 14-day warm-up per FR-2.2; maturity is 0 below that, ramps to 1.0 at 30d.
    maturity = max(0.0, min(1.0, (days_available - 14) / 16)) if days_available >= 14 else 0.0

    return UserDetailResponse(
        user_id=user.user_id,
        name=user.employee_name or user.user_id,
        email=user.email,
        org=UserOrgOut(role=org.role, department=org.department, team=org.team, supervisor=org.supervisor, cohort_size=cohort_size),
        tenure_days=(user.last_seen - user.first_seen).days,
        departure_date=user.departure_date,
        first_seen=user.first_seen,
        last_seen=user.last_seen,
        baseline=BaselineOut(days_available=days_available, maturity=maturity, working_window=None),
        current_risk=current_risk,
        risk_ewma=risk_ewma,
        incident_counts=_incident_counts_by_lane(db, user_id),
    )


@router.get("/{user_id}/risk", response_model=UserRiskResponse)
def get_user_risk(
    user_id: str,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    db: Session = Depends(get_db),
) -> UserRiskResponse:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail=f"No user with id {user_id}")

    stmt = select(UserDayScore).where(UserDayScore.user_id == user_id)
    if date_from:
        stmt = stmt.where(UserDayScore.event_date >= date_from)
    if date_to:
        stmt = stmt.where(UserDayScore.event_date <= date_to)
    scores = db.scalars(stmt.order_by(UserDayScore.event_date)).all()

    series: list[RiskSeriesPoint] = []
    for score in scores:
        signal_count = db.scalar(
            select(func.count()).select_from(Signal).where(Signal.user_id == user_id, Signal.event_date == score.event_date)
        ) or 0
        incident_ids = db.scalars(
            select(Incident.incident_id).where(
                Incident.user_id == user_id,
                func.date(Incident.window_start) <= score.event_date,
                func.date(Incident.window_end) >= score.event_date,
            )
        ).all()
        series.append(
            RiskSeriesPoint(
                date=score.event_date,
                risk=score.risk,
                confidence=score.confidence,
                risk_ewma=score.risk_ewma,
                signal_count=signal_count,
                incident_ids=list(incident_ids),
            )
        )

    org = _current_org(db, user_id)
    peer_band: list[PeerBandPoint] = []
    if org is not None:
        peer_ids = db.scalars(select(UserOrg.user_id).where(UserOrg.cohort_key == org.cohort_key)).all()
        for score in scores:
            peer_scores = db.scalars(
                select(UserDayScore.risk).where(
                    UserDayScore.user_id.in_(peer_ids), UserDayScore.event_date == score.event_date
                )
            ).all()
            if not peer_scores:
                continue
            sorted_risks = sorted(peer_scores)
            peer_band.append(
                PeerBandPoint(
                    date=score.event_date,
                    p50=_percentile(sorted_risks, 0.50),
                    p90=_percentile(sorted_risks, 0.90),
                    p99=_percentile(sorted_risks, 0.99),
                )
            )

    if series:
        peak = max(series, key=lambda p: p.risk)
        summary = RiskSummary(
            peak_risk=peak.risk,
            peak_date=peak.date,
            days_above_threshold=sum(1 for p in series if p.risk >= 40.0),
            trend=_trend(list(scores)),
        )
    else:
        summary = RiskSummary(peak_risk=0.0, peak_date=None, days_above_threshold=0, trend="stable")

    window = {
        "from": date_from or (series[0].date if series else dt.date.today()),
        "to": date_to or (series[-1].date if series else dt.date.today()),
    }
    return UserRiskResponse(user_id=user_id, window=window, series=series, peer_band=peer_band, summary=summary)


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(p * (len(sorted_values) - 1))))
    return sorted_values[idx]


@router.get("/{user_id}/timeline", response_model=TimelineResponse)
def get_user_timeline(user_id: str, date: dt.date, db: Session = Depends(get_db)) -> TimelineResponse:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail=f"No user with id {user_id}")

    day_start = dt.datetime.combine(date, dt.time.min, tzinfo=dt.timezone.utc)
    day_end = dt.datetime.combine(date, dt.time.max, tzinfo=dt.timezone.utc)
    events = db.scalars(
        select(Event)
        .where(Event.user_id == user_id, Event.ts >= day_start, Event.ts <= day_end)
        .order_by(Event.ts)
    ).all()
    signals = db.scalars(select(Signal).where(Signal.user_id == user_id, Signal.event_date == date)).all()

    signals_by_event: dict[str, list[int]] = {}
    for sig in signals:
        for eid in sig.evidence_event_ids:
            signals_by_event.setdefault(eid, []).append(sig.signal_id)

    score = db.get(UserDayScore, {"user_id": user_id, "event_date": date})

    out_events = [
        TimelineEvent(
            event_id=e.event_id,
            ts=e.ts,
            source=e.source,
            action=e.action,
            pc_id=e.pc_id,
            attrs=e.attrs,
            signal_ids=signals_by_event.get(e.event_id, []),
            risk_after=None,
            stage=None,
        )
        for e in events
    ]

    return TimelineResponse(
        date=date,
        events=out_events,
        working_window=None,
        final_risk=score.risk if score else None,
    )
