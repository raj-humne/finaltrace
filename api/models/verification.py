"""Single-use, signed verification tokens for flagged incidents.

Judge-requested capability: once an incident is raised (AUTO_FLAG), anyone
holding a token issued for it - an auditor, HR, a judge, someone with no
SentinelTrace login at all - can independently verify the report is genuine
and unaltered, without trusting "the dashboard says so." The signature
(api/verification.py, JWT/HS256) proves the token's claims weren't tampered
with; this table is what makes it single-use - a signature alone never
expires or gets consumed, so replay protection has to live in the database,
not the token.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


class IncidentVerificationToken(Base):
    __tablename__ = "incident_verification_tokens"

    jti: Mapped[str] = mapped_column(String, primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), nullable=False, index=True
    )
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_by: Mapped[str] = mapped_column(String, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    used_from_ip: Mapped[str | None] = mapped_column(String)
