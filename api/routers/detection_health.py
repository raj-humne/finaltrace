from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.correlation import Incident
from api.models.detection import Signal
from api.models.explain import Attribution
from api.models.feedback import Review
from api.models.identity import User
from api.schemas.detection_health import (
    AlertVolume,
    Calibration,
    CalibrationBin,
    Compression,
    DetectionHealthOut,
    TopFiringRule,
)

router = APIRouter(prefix="/detection", tags=["detection-health"], dependencies=[Depends(get_current_account)])

_N_BINS = 10
_LOW_PRECISION_WARNING_THRESHOLD = 0.2
_LOW_PRECISION_MIN_REVIEWS = 5


def _rule_precision(db: Session, rule_id: str) -> tuple[int, float | None]:
    incident_ids = db.scalars(
        select(Attribution.incident_id)
        .join(Signal, Signal.signal_id == Attribution.signal_id)
        .where(Signal.rule_id == rule_id)
    ).all()
    if not incident_ids:
        return 0, None
    rows = db.execute(
        select(Review.verdict, func.count())
        .where(Review.incident_id.in_(set(incident_ids)))
        .group_by(Review.verdict)
    ).all()
    counts = dict(rows)
    decided = counts.get("confirmed_threat", 0) + counts.get("benign", 0)
    precision = counts.get("confirmed_threat", 0) / decided if decided else None
    return sum(counts.values()), precision


@router.get("/health", response_model=DetectionHealthOut)
def detection_health(db: Session = Depends(get_db)) -> DetectionHealthOut:
    incidents = db.scalars(select(Incident)).all()
    users_total = db.scalar(select(func.count()).select_from(User)) or 0

    if incidents:
        dates = [i.window_start.date() for i in incidents]
        window_from, window_to = min(dates), max(dates)
        days_spanned = max(1, (window_to - window_from).days + 1)
    else:
        window_from = window_to = dt.date.today()
        days_spanned = 1

    incidents_per_day = len(incidents) / days_spanned
    per_1k = incidents_per_day / (users_total / 1000) if users_total else 0.0

    lane_mix: dict[str, int] = {}
    for i in incidents:
        lane_mix[i.triage_lane] = lane_mix.get(i.triage_lane, 0) + 1

    signals_mean = sum(i.signal_count for i in incidents) / len(incidents) if incidents else 0.0
    events_mean = sum(i.event_count for i in incidents) / len(incidents) if incidents else 0.0

    # Calibration: bin incidents by their own confidence score, and check how
    # often a *reviewed* incident in that bin was actually confirmed —
    # exactly the ECE definition in docs/05 section 7 / docs/07.
    bins: list[CalibrationBin] = []
    ece_numerator = 0.0
    for b in range(_N_BINS):
        lo, hi = b / _N_BINS, (b + 1) / _N_BINS
        bucket = [i for i in incidents if lo <= i.confidence < hi or (b == _N_BINS - 1 and i.confidence == 1.0)]
        if not bucket:
            continue
        incident_ids = {i.incident_id for i in bucket}
        rows = db.execute(
            select(Review.verdict, func.count()).where(Review.incident_id.in_(incident_ids)).group_by(Review.verdict)
        ).all()
        counts = dict(rows)
        decided = counts.get("confirmed_threat", 0) + counts.get("benign", 0)
        observed = counts.get("confirmed_threat", 0) / decided if decided else None
        bins.append(CalibrationBin(confidence_range=[lo, hi], n=len(bucket), observed_precision=observed))
        if observed is not None:
            midpoint = (lo + hi) / 2
            ece_numerator += (len(bucket) / len(incidents)) * abs(observed - midpoint)

    rule_fire_counts: dict[str, int] = {}
    for rule_id in db.scalars(select(Signal.rule_id)).all():
        rule_fire_counts[rule_id] = rule_fire_counts.get(rule_id, 0) + 1
    top_rule_ids = sorted(rule_fire_counts, key=lambda r: rule_fire_counts[r], reverse=True)[:10]

    top_firing: list[TopFiringRule] = []
    warnings: list[str] = []
    for rule_id in top_rule_ids:
        reviewed, precision = _rule_precision(db, rule_id)
        top_firing.append(TopFiringRule(rule_id=rule_id, count=rule_fire_counts[rule_id], observed_precision=precision))
        if precision is not None and reviewed >= _LOW_PRECISION_MIN_REVIEWS and precision < _LOW_PRECISION_WARNING_THRESHOLD:
            warnings.append(f"{rule_id} has low standalone precision — intended as a supporting signal only")

    return DetectionHealthOut(
        window={"from": window_from, "to": window_to},
        alert_volume=AlertVolume(incidents_per_day=incidents_per_day, per_1k_users_per_day=per_1k),
        lane_mix=lane_mix,
        compression=Compression(signals_per_incident_mean=signals_mean, events_per_incident_mean=events_mean),
        calibration=Calibration(bins=bins, ece=ece_numerator),
        top_firing_rules=top_firing,
        warnings=warnings,
    )
