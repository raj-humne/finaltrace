from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import big_serial


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("verdict IN ('confirmed_threat','benign','inconclusive')", name="ck_review_verdict"),
    )

    review_id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(String)
    analyst_id: Mapped[str] = mapped_column(String, nullable=False)
    reviewed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    time_to_triage_sec: Mapped[int | None] = mapped_column(Integer)


class Suppression(Base):
    __tablename__ = "suppressions"
    __table_args__ = (
        CheckConstraint("scope IN ('user','cohort','rule','user_rule')", name="ck_suppression_scope"),
        CheckConstraint("status IN ('proposed','active','revoked')", name="ck_suppression_status"),
    )

    suppression_id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String)
    cohort_key: Mapped[str | None] = mapped_column(String)
    rule_id: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    source_review: Mapped[int | None] = mapped_column(ForeignKey("reviews.review_id"), index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed")
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
