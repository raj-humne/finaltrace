from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from api.schemas.common import ApiModel

Verdict = Literal["false_positive"]
ReasonCode = Literal[
    "approved_business_activity",
    "expected_off_hours_work",
    "known_usb_workflow",
    "known_host_access",
    "expected_bulk_access",
    "test_or_training",
    "other",
]


class FeedbackRequest(ApiModel):
    verdict: Verdict
    reason_code: ReasonCode
    comment: str | None = Field(default=None, max_length=500)
    apply_to_similar: bool = True


class BaselineUpdateOut(ApiModel):
    feature_name: str
    mean_value: float
    std_value: float
    p95_value: float
    sample_count: int


class EdgeUpdateOut(ApiModel):
    source_event_type: str
    target_event_type: str
    false_positive_count: int
    original_weight: float
    current_weight: float


class ScoreImpactOut(ApiModel):
    original_risk: float
    predicted_similar_risk: float
    expected_reduction: float


class FeedbackResponse(ApiModel):
    incident_id: str
    incident_status: str
    disposition: str | None
    feedback_id: int
    updated_baselines: list[BaselineUpdateOut]
    updated_edges: list[EdgeUpdateOut]
    score_impact: ScoreImpactOut
    processed_at: dt.datetime
