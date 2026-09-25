"""Suppression governance. FR-6.4: a benign verdict may PROPOSE a suppression
(see routers/incidents.py POST /incidents/{id}/review), but it only takes
effect once a detection_engineer activates it here — an analyst cannot
silence a rule alone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db, require_detection_engineer
from api.models.feedback import Suppression
from api.models.identity import Account
from api.schemas.suppressions import SuppressionOut
from api.security.audit import write_audit

router = APIRouter(prefix="/suppressions", tags=["suppressions"], dependencies=[Depends(get_current_account)])


def _get_or_404(db: Session, suppression_id: int) -> Suppression:
    row = db.get(Suppression, suppression_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No suppression with id {suppression_id}")
    return row


@router.get("", response_model=list[SuppressionOut])
def list_suppressions(status: str | None = None, db: Session = Depends(get_db)) -> list[SuppressionOut]:
    stmt = select(Suppression)
    if status:
        stmt = stmt.where(Suppression.status == status)
    rows = db.scalars(stmt.order_by(Suppression.created_at.desc())).all()
    return [SuppressionOut.model_validate(r) for r in rows]


@router.post("/{suppression_id}/activate", response_model=SuppressionOut)
def activate_suppression(
    suppression_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(require_detection_engineer),
) -> SuppressionOut:
    row = _get_or_404(db, suppression_id)
    if row.status != "proposed":
        raise HTTPException(status_code=409, detail=f"suppression is '{row.status}', not 'proposed'")
    before = {"status": row.status}
    row.status = "active"
    write_audit(
        db, actor=account.username, action="suppression_activated",
        object_type="suppression", object_id=str(row.suppression_id),
        before=before, after={"status": row.status},
    )
    db.commit()
    db.refresh(row)
    return SuppressionOut.model_validate(row)


@router.post("/{suppression_id}/revoke", response_model=SuppressionOut)
def revoke_suppression(
    suppression_id: int,
    db: Session = Depends(get_db),
    account: Account = Depends(require_detection_engineer),
) -> SuppressionOut:
    row = _get_or_404(db, suppression_id)
    if row.status == "revoked":
        raise HTTPException(status_code=409, detail="suppression already revoked")
    before = {"status": row.status}
    row.status = "revoked"
    write_audit(
        db, actor=account.username, action="suppression_revoked",
        object_type="suppression", object_id=str(row.suppression_id),
        before=before, after={"status": row.status},
    )
    db.commit()
    db.refresh(row)
    return SuppressionOut.model_validate(row)
