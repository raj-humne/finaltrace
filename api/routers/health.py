from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config_snapshot import config_version, load_rules
from api.deps import get_db
from api.models.identity import User
from api.models.ingest import Event, IngestRun
from api.schemas.health import HealthData, HealthEngine, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    users = db.scalar(select(func.count()).select_from(User)) or 0
    events = db.scalar(select(func.count()).select_from(Event)) or 0
    ts_min = db.scalar(select(func.min(Event.ts)))
    ts_max = db.scalar(select(func.max(Event.ts)))
    last_run = db.scalar(
        select(IngestRun.finished_at).where(IngestRun.finished_at.is_not(None)).order_by(IngestRun.finished_at.desc())
    )

    latest_run_config = db.scalar(
        select(IngestRun.config_version)
        .where(IngestRun.config_version.is_not(None))
        .order_by(IngestRun.started_at.desc())
    )

    return HealthResponse(
        status="ok",
        config_version=latest_run_config or config_version(),
        data=HealthData(ts_min=ts_min, ts_max=ts_max, users=users, events=events, last_pipeline_run=last_run),
        engine=HealthEngine(rules_loaded=len(load_rules()), cohort_models=0, mode="batch"),
    )
