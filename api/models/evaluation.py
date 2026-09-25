from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


class GroundTruth(Base):
    """Never joined in the serving path — evaluation only."""

    __tablename__ = "ground_truth"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    scenario: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_malicious: Mapped[bool] = mapped_column(Boolean, nullable=False)
