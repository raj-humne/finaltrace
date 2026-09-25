from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import StringArrayType


class Narrative(Base):
    __tablename__ = "narratives"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), primary_key=True
    )
    headline: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    template_ids: Mapped[list[str]] = mapped_column(StringArrayType, nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )


class Attribution(Base):
    __tablename__ = "attributions"

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), primary_key=True
    )
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.signal_id"), primary_key=True)
    points: Mapped[float] = mapped_column(nullable=False)
    risk_without: Mapped[float] = mapped_column(nullable=False)
    delta: Mapped[float] = mapped_column(nullable=False)
    in_minimal_set: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
