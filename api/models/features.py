from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import JSONBType


class UserDayFeature(Base):
    __tablename__ = "user_day_features"
    __table_args__ = (
        CheckConstraint("data_completeness BETWEEN 0 AND 1", name="ck_udf_completeness"),
        CheckConstraint("baseline_maturity BETWEEN 0 AND 1", name="ck_udf_maturity"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    event_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    cohort_key: Mapped[str] = mapped_column(String, nullable=False)
    features: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    z_self: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    z_peer: Mapped[dict] = mapped_column(JSONBType, nullable=False)
    data_completeness: Mapped[float] = mapped_column(nullable=False)
    baseline_maturity: Mapped[float] = mapped_column(nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    config_version: Mapped[str] = mapped_column(String, nullable=False)
