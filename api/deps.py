from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.db.session import SessionLocal
from api.models.identity import Account
from api.security.auth_service import resolve_session
from api.security.exceptions import SessionInvalid
from api.settings import settings


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_account(request: Request, db: Session = Depends(get_db)) -> Account:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        return resolve_session(db, raw_token)
    except SessionInvalid:
        raise HTTPException(status_code=401, detail="session expired or invalid")


class RequireRole:
    """FastAPI dependency: enforce RBAC on the route, never in the frontend (B2)."""

    def __init__(self, role: str) -> None:
        self.role = role

    def __call__(self, account: Account = Depends(get_current_account)) -> Account:
        if account.role != self.role:
            raise HTTPException(status_code=403, detail=f"requires role '{self.role}'")
        return account


require_detection_engineer = RequireRole("detection_engineer")
