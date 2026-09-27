"""Analyst Feedback Loop for False-Positive Reduction (Challenge 2).

Four new, additive tables. Nothing here mutates `events`, `signals`, or
`attributions` — the dismissed incident's original evidence stays exactly as
detected; these tables only record what an analyst decided about it and what
the system learned (a bounded, user-scoped tolerance adjustment) as a result.

Distinct from `Review`/`Suppression` (api/models/feedback.py): those are the
general SOC disposition workflow (confirmed_threat/benign/inconclusive,
optional rule suppression) and never touch behavioral baselines or
correlation-edge weights. Only a `false_positive` `AnalystFeedback` row drives
learning, via api/feedback.py::submit_feedback.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base
from api.db.types import big_serial

REASON_CODES = (
    "approved_business_activity",
    "expected_off_hours_work",
    "known_usb_workflow",
    "known_host_access",
    "expected_bulk_access",
    "test_or_training",
    "other",
)


class AnalystFeedback(Base):
    """One analyst's false-positive verdict on one incident (spec A.1).
    Append-only, like `Review` and `MitigationAction`: the audit trail is
    never edited, only ever added to."""

    __tablename__ = "analyst_feedback"
    __table_args__ = (
        CheckConstraint("verdict IN ('false_positive')", name="ck_analyst_feedback_verdict"),
        CheckConstraint(
            "reason_code IN ("
            "'approved_business_activity','expected_off_hours_work','known_usb_workflow',"
            "'known_host_access','expected_bulk_access','test_or_training','other')",
            name="ck_analyst_feedback_reason_code",
        ),
    )

    id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), nullable=False)
    analyst_id: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[str | None] = mapped_column(String)
    apply_to_similar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )


class BehavioralBaseline(Base):
    """Pandas-recomputed per-(entity, feature) tolerance (spec C). `entity_type`
    exists so a cohort/org-scoped row could exist later without a schema
    change, but api/feedback.py only ever writes `entity_type='user'` today —
    "scope learned suppression to the specific user by default, not
    globally" is enforced by the write path, not by this table alone.
    `feedback_adjustment` is the cumulative, capped fraction (spec's 25%-per-
    event rule) by which this feature's tolerance has widened due to
    dismissed incidents, kept for explainability (engine/explain metadata)."""

    __tablename__ = "behavioral_baselines"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "feature_name", name="uq_behavioral_baseline_entity_feature"),
    )

    id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    feature_name: Mapped[str] = mapped_column(String, nullable=False)
    mean_value: Mapped[float] = mapped_column(Float, nullable=False)
    std_value: Mapped[float] = mapped_column(Float, nullable=False)
    p95_value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )


class EdgeFeedbackWeight(Base):
    """Per-(event-type pair, context) learned decay (spec D). `context_key` is
    `"user:{user_id}"` by default, which is what keeps this scoped to the
    specific user rather than a global rule change — a lookup for a
    different user's identical (source_event_type, target_event_type) pair
    with a *different* context_key simply misses this row and falls back to
    the default weight (engine/feedback/edge_weights.py)."""

    __tablename__ = "edge_feedback_weights"
    __table_args__ = (
        UniqueConstraint(
            "source_event_type", "target_event_type", "context_key",
            name="uq_edge_feedback_weight_pair_context",
        ),
    )

    id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    source_event_type: Mapped[str] = mapped_column(String, nullable=False)
    target_event_type: Mapped[str] = mapped_column(String, nullable=False)
    context_key: Mapped[str] = mapped_column(String, nullable=False)
    original_weight: Mapped[float] = mapped_column(Float, nullable=False)
    current_weight: Mapped[float] = mapped_column(Float, nullable=False)
    false_positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_feedback_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )


class FeatureObservation(Base):
    """Immutable per-observation ledger feeding `BehavioralBaseline` recompute
    (spec A.4). Every dismissed incident's own feature values are recorded
    here regardless of `apply_to_similar` (complete audit trail per the
    brief's constraints), but only rows with `is_trusted=True` are ever read
    back by engine/feedback/baseline.py into a new Pandas baseline recompute -
    an analyst declining "learn from this" still gets a permanent record,
    it just never feeds future tolerance."""

    __tablename__ = "feature_observations"

    id: Mapped[int] = mapped_column(big_serial(), primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    feature_name: Mapped[str] = mapped_column(String, nullable=False)
    feature_value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.incident_id"))
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
