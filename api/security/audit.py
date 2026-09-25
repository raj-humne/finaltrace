from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.models.identity import AuditLog


def write_audit(
    db: Session,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Every login, logout, failure, and privileged action appends here (B2).
    Append-only: callers never update or delete a row."""
    row = AuditLog(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
    )
    db.add(row)
    db.flush()
    return row
