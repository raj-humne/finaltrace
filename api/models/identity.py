"""Reference / identity tables (docs/03-DATA-MODEL.md section 5) plus the
analyst-authentication tables the API track adds.

Naming note: the DDL's `users` table is the population being *monitored*
(CERT employees). Analyst/engineer login identities are a distinct concept —
reusing `users` for both would collide two unrelated entities under one name,
so analyst accounts live in `accounts` instead. This is additive; nothing in
docs/03 is changed.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.db.types import JSONBType


class User(Base):
    """A monitored employee (CERT identity), not a login account."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    employee_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    first_seen: Mapped[dt.date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[dt.date] = mapped_column(Date, nullable=False)
    departure_date: Mapped[dt.date | None] = mapped_column(Date)

    org_history: Mapped[list["UserOrg"]] = relationship(back_populates="user")


class UserOrg(Base):
    __tablename__ = "user_org"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    valid_to: Mapped[dt.date] = mapped_column(Date, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, nullable=False)
    team: Mapped[str | None] = mapped_column(String)
    supervisor: Mapped[str | None] = mapped_column(String)
    cohort_key: Mapped[str] = mapped_column(String, nullable=False)

    user: Mapped[User] = relationship(back_populates="org_history")


ACCOUNT_ROLES = ("analyst", "detection_engineer")


class Account(Base):
    """A login identity for an analyst or detection engineer. FR-6, B2."""

    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("role IN ('analyst','detection_engineer')", name="ck_account_role"),)

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )

    sessions: Mapped[list["SessionToken"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class SessionToken(Base):
    """Server-side session record backing the httpOnly session cookie."""

    __tablename__ = "sessions"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="sessions")


class AuditLog(Base):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    object_type: Mapped[str] = mapped_column(String, nullable=False)
    object_id: Mapped[str] = mapped_column(String, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
