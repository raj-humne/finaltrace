from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.db.types import JSONBType


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','success','failed','partial')", name="ck_ingest_run_status"),
    )

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False)
    source_files: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    rows_accepted: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_rejected: Mapped[int] = mapped_column(BigInteger, default=0)
    reject_samples: Mapped[list | None] = mapped_column(JSONBType)
    ts_min: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ts_max: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    adapter_id: Mapped[str | None] = mapped_column(String)
    config_version: Mapped[str | None] = mapped_column(String)

    events: Mapped[list["Event"]] = relationship(back_populates="ingest_run")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("source IN ('logon','device','file','http','email')", name="ck_event_source"),
    )

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    pc_id: Mapped[str | None] = mapped_column(String)
    ip_address: Mapped[str | None] = mapped_column(String)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    attrs: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    ingest_run_id: Mapped[str] = mapped_column(ForeignKey("ingest_runs.run_id"), nullable=False)

    ingest_run: Mapped[IngestRun] = relationship(back_populates="events")
