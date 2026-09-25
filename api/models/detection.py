from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import JSONBType, StringArrayType, big_serial


class ConfigVersion(Base):
    __tablename__ = "config_versions"

    config_version: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    note: Mapped[str | None] = mapped_column(String)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint("strength BETWEEN 0 AND 1", name="ck_signal_strength"),
    )

    signal_id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    killchain_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    strength: Mapped[float] = mapped_column(nullable=False)
    weight: Mapped[float] = mapped_column(nullable=False)
    contribution: Mapped[float] = mapped_column(nullable=False)
    evidence_event_ids: Mapped[list[str]] = mapped_column(StringArrayType, nullable=False)
    phrase: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    config_version: Mapped[str] = mapped_column(ForeignKey("config_versions.config_version"), nullable=False)


class UserDayScore(Base):
    __tablename__ = "user_day_scores"
    __table_args__ = (
        CheckConstraint("risk BETWEEN 0 AND 100", name="ck_uds_risk"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_uds_confidence"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    event_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    risk: Mapped[float] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    logit: Mapped[float] = mapped_column(nullable=False)
    rule_points: Mapped[float] = mapped_column(nullable=False)
    ml_points: Mapped[float] = mapped_column(nullable=False)
    corr_points: Mapped[float] = mapped_column(nullable=False)
    anomaly_pctl: Mapped[float | None] = mapped_column()
    risk_ewma: Mapped[float | None] = mapped_column()
    config_version: Mapped[str] = mapped_column(String, nullable=False)
