"""Read-only auditability surface over automated mitigation actions
(Challenge 1). Mitigation only ever fires automatically (api/mitigation.py,
triggered when a correlated incident is finalized) - there is no manual
"trigger mitigation" or "isolate" endpoint here, since the challenge
requires automatic mitigation, not manual destructive control. Gated the
same as every other read endpoint (any authenticated account, no elevated
role required).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.mitigation import MitigationAction
from api.schemas.mitigation import MitigationActionOut, MitigationStatusOut
from api.settings import settings

router = APIRouter(prefix="/mitigation", tags=["mitigation"], dependencies=[Depends(get_current_account)])


@router.get("/status", response_model=MitigationStatusOut)
def get_status() -> MitigationStatusOut:
    return MitigationStatusOut(
        enabled=settings.mitigation_enabled,
        threshold=settings.mitigation_threat_weight_threshold,
        webhook_url=settings.mitigation_webhook_url,
        webhook_timeout_seconds=settings.mitigation_webhook_timeout_seconds,
    )


@router.get("/actions", response_model=list[MitigationActionOut])
def list_actions(incident_id: str | None = None, db: Session = Depends(get_db)) -> list[MitigationActionOut]:
    stmt = select(MitigationAction)
    if incident_id:
        stmt = stmt.where(MitigationAction.incident_id == incident_id)
    rows = db.scalars(stmt.order_by(MitigationAction.created_at.desc())).all()
    return [MitigationActionOut.model_validate(r) for r in rows]


@router.get("/actions/{mitigation_action_id}", response_model=MitigationActionOut)
def get_action(mitigation_action_id: int, db: Session = Depends(get_db)) -> MitigationActionOut:
    row = db.get(MitigationAction, mitigation_action_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No mitigation action with id {mitigation_action_id}")
    return MitigationActionOut.model_validate(row)


@router.get("/incidents/{incident_id}", response_model=MitigationActionOut)
def get_action_for_incident(incident_id: str, db: Session = Depends(get_db)) -> MitigationActionOut:
    row = db.scalar(select(MitigationAction).where(MitigationAction.incident_id == incident_id))
    if row is None:
        raise HTTPException(status_code=404, detail=f"No mitigation action recorded for incident {incident_id}")
    return MitigationActionOut.model_validate(row)
