from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import SmallIntArrayType


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    first_seen: Mapped[dt.date] = mapped_column(nullable=False)
    last_seen: Mapped[dt.date] = mapped_column(nullable=False)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    peak_risk: Mapped[float] = mapped_column(nullable=False)
    stage_progression: Mapped[list[int]] = mapped_column(SmallIntArrayType, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "triage_lane IN ('AUTO_FLAG','ANALYST_REVIEW','MONITOR','SUPPRESSED')", name="ck_incident_lane"
        ),
        CheckConstraint("status IN ('open','in_review','closed')", name="ck_incident_status"),
    )

    incident_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk: Mapped[float] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    triage_lane: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    killchain_stages: Mapped[list[int]] = mapped_column(SmallIntArrayType, nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    category_count: Mapped[int] = mapped_column(Integer, nullable=False)
    over_dense: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.campaign_id"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    config_version: Mapped[str] = mapped_column(String, nullable=False)


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    __table_args__ = (CheckConstraint("node_role IN ('signal','context')", name="ck_incident_event_role"),)

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(ForeignKey("events.event_id"), primary_key=True)
    node_role: Mapped[str] = mapped_column(String, nullable=False)


class IncidentEdge(Base):
    __tablename__ = "incident_edges"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), primary_key=True
    )
    src_event: Mapped[str] = mapped_column(String, primary_key=True)
    dst_event: Mapped[str] = mapped_column(String, primary_key=True)
    gap_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_type: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(nullable=False)
