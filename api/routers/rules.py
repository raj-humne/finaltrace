from __future__ import annotations

import datetime as dt
import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config_snapshot import get_rule, load_rules
from api.deps import get_current_account, get_db
from api.models.detection import Signal, UserDayScore
from api.models.explain import Attribution
from api.models.feedback import Review
from api.schemas.rules import RuleOut, RuleStatsOut

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(get_current_account)])

# How far configured weight may drift from the measured log-odds before it's
# flagged for a detection engineer to look at (docs/05 section 7's
# `weight_drift` / `recommendation` fields). Not yet calibrated against real
# data by Track D; kept as an explicit, named constant so it's one place to
# retune rather than a buried magic number.
_DRIFT_TOLERANCE = 0.5


@router.get("", response_model=list[RuleOut])
def list_rules() -> list[RuleOut]:
    return [
        RuleOut(
            id=r["id"], name=r["name"], category=r["category"], stage=r["stage"], weight=r["weight"],
            requires_baseline=r["requires_baseline"], phrase=r["phrase"],
        )
        for r in load_rules()
    ]


@router.get("/{rule_id}/stats", response_model=RuleStatsOut)
def rule_stats(
    rule_id: str,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    db: Session = Depends(get_db),
) -> RuleStatsOut:
    rule = get_rule(rule_id)
    if rule is None and rule_id != "ml.isoforest":
        raise HTTPException(status_code=404, detail=f"No rule with id {rule_id}")
    configured_weight = rule["weight"] if rule else 0.0

    stmt = select(Signal).where(Signal.rule_id == rule_id)
    if date_from:
        stmt = stmt.where(Signal.event_date >= date_from)
    if date_to:
        stmt = stmt.where(Signal.event_date <= date_to)
    signals = db.scalars(stmt).all()
    fire_count = len(signals)

    total_user_days = db.scalar(select(func.count()).select_from(UserDayScore)) or 0
    fire_rate = fire_count / total_user_days if total_user_days else 0.0

    incident_ids = set(
        db.scalars(
            select(Attribution.incident_id).where(Attribution.signal_id.in_([s.signal_id for s in signals]))
        ).all()
    )
    verdict_counts = {"confirmed_threat": 0, "benign": 0, "inconclusive": 0}
    if incident_ids:
        rows = db.execute(
            select(Review.verdict, func.count())
            .where(Review.incident_id.in_(incident_ids))
            .group_by(Review.verdict)
        ).all()
        for verdict, n in rows:
            verdict_counts[verdict] = n
    reviewed = sum(verdict_counts.values())
    confirmed = verdict_counts["confirmed_threat"]
    benign = verdict_counts["benign"]
    inconclusive = verdict_counts["inconclusive"]

    observed_precision = None
    measured_log_odds = None
    weight_drift = None
    recommendation = "insufficient_data"
    decided = confirmed + benign
    if decided > 0:
        # Laplace-smoothed so a rule with 100% or 0% observed precision still
        # yields a finite log-odds instead of +/-inf.
        p = (confirmed + 0.5) / (decided + 1.0)
        observed_precision = confirmed / decided
        measured_log_odds = math.log(p / (1 - p))
        weight_drift = configured_weight - measured_log_odds
        recommendation = "within_tolerance" if abs(weight_drift) <= _DRIFT_TOLERANCE else "review_weight"

    return RuleStatsOut(
        rule_id=rule_id,
        configured_weight=configured_weight,
        fire_count=fire_count,
        fire_rate_per_user_day=fire_rate,
        reviewed=reviewed,
        confirmed=confirmed,
        benign=benign,
        inconclusive=inconclusive,
        observed_precision=observed_precision,
        measured_log_odds=measured_log_odds,
        weight_drift=weight_drift,
        recommendation=recommendation,
    )
