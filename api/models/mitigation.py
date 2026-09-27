"""Automated mitigation actions (Challenge 1: automated threat mitigation
pipeline). Append-only, like `AuditLog` (api/models/identity.py): every
threshold check that fires - whether the remediation webhook succeeded or
failed - gets a permanent row here, so an analyst can always answer "what
did the system do automatically, and when" regardless of the mock
remediation service's availability at the time.

`incident_id` is UNIQUE: at most one mitigation action is ever recorded per
incident (idempotency - api/mitigation.py checks for an existing row before
dispatching, so re-processing the same incident never re-fires the webhook
or creates a second row).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import JSONBType


class MitigationAction(Base):
    __tablename__ = "mitigation_actions"
    __table_args__ = (
        UniqueConstraint("incident_id", name="uq_mitigation_action_incident"),
        CheckConstraint("status IN ('SUCCESS','FAILED')", name="ck_mitigation_action_status"),
        CheckConstraint(
            "isolation_status IN ('SIMULATED_ISOLATED','NOT_ISOLATED')", name="ck_mitigation_action_isolation"
        ),
        Index("ix_mitigation_actions_user_id", "user_id"),
        Index("ix_mitigation_actions_status", "status"),
    )

    mitigation_action_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    flagged_ip: Mapped[str | None] = mapped_column(String)
    threat_weight: Mapped[float] = mapped_column(nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False, default="ISOLATE")
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_value: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    webhook_url: Mapped[str] = mapped_column(String, nullable=False)
    webhook_status_code: Mapped[int | None] = mapped_column(Integer)
    webhook_response: Mapped[str | None] = mapped_column(String)
    isolation_status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
