from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from api.schemas.common import ApiModel
from api.schemas.mitigation import MitigationActionOut


class IncidentListItem(ApiModel):
    incident_id: str
    user_id: str
    user_name: str
    department: str
    window: dict[str, dt.datetime]
    risk: float
    confidence: float
    triage_lane: str
    status: str
    headline: str
    killchain_stages: list[int]
    max_stage: int
    signal_count: int
    event_count: int
    campaign_id: str | None
    top_signal: dict[str, Any] | None


class IncidentListResponse(ApiModel):
    items: list[IncidentListItem]
    next_cursor: str | None
    total: int
    facets: dict[str, dict[str, int]]


class ScoreBreakdown(ApiModel):
    prior_logit: float
    rule_points: float
    ml_points: float
    correlation_points: float
    total_logit: float
    tau: float


class ConfidenceTerms(ApiModel):
    agreement: float
    diversity: float
    completeness: float
    maturity: float
    caps_applied: list[str]


class ScoreOut(ApiModel):
    risk: float
    confidence: float
    triage_lane: str
    breakdown: ScoreBreakdown
    confidence_terms: ConfidenceTerms


class NarrativeOut(ApiModel):
    headline: str
    summary: str
    detail_bullets: list[str]
    template_ids: list[str]


class SignalDetailOut(ApiModel):
    signal_id: int
    rule_id: str
    name: str
    category: str
    stage: int
    strength: float
    weight: float
    contribution: float
    phrase: str
    detail: dict[str, Any]
    evidence_event_ids: list[str]
    references: list[str] = Field(default_factory=list)


class AttributionItemOut(ApiModel):
    signal_id: int
    rule_id: str
    risk_without: float
    delta: float
    rank: int
    in_minimal_set: bool


class AttributionOut(ApiModel):
    note: str
    items: list[AttributionItemOut]
    minimal_sufficient_set: list[str]
    alert_threshold: float


class CampaignRef(ApiModel):
    campaign_id: str
    incident_count: int
    first_seen: dt.date
    last_seen: dt.date
    stage_progression: list[int]


class UserRef(ApiModel):
    user_id: str
    name: str
    role: str
    department: str
    cohort_size: int


class ReviewOut(ApiModel):
    review_id: int
    verdict: str
    note: str | None
    analyst_id: str
    reviewed_at: dt.datetime


class IncidentDetailOut(ApiModel):
    incident_id: str
    user: UserRef
    window: dict[str, Any]
    score: ScoreOut
    narrative: NarrativeOut
    signals: list[SignalDetailOut]
    attribution: AttributionOut
    campaign: CampaignRef | None
    status: str
    disposition: str | None = None
    review: ReviewOut | None
    mitigations: list[MitigationActionOut]
    config_version: str
    links: dict[str, str]


class GraphNodeOut(ApiModel):
    id: str
    ts: dt.datetime
    source: str
    action: str
    label: str
    stage: int | None
    risk_contribution: float
    has_signal: bool
    pc_id: str | None
    user_id: str


class GraphEdgeOut(ApiModel):
    source: str
    target: str
    gap_seconds: int
    gap_label: str
    type: str
    weight: float


class GraphStats(ApiModel):
    node_count: int
    edge_count: int
    component_diameter: int


class IncidentGraphOut(ApiModel):
    incident_id: str
    over_dense: bool
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    layout_hint: str
    stats: GraphStats


class ProposeSuppression(ApiModel):
    scope: str
    user_id: str | None = None
    cohort_key: str | None = None
    rule_id: str | None = None
    expires_at: dt.datetime | None = None


class ReviewRequest(ApiModel):
    verdict: str
    note: str | None = None
    analyst_id: str
    time_to_triage_sec: int | None = None
    propose_suppression: ProposeSuppression | None = None


class ReviewEffects(ApiModel):
    rule_stats_updated: list[str]
    user_risk_ewma_adjusted: bool


class ReviewResponse(ApiModel):
    review_id: int
    incident_id: str
    verdict: str
    reviewed_at: dt.datetime
    incident_status: str
    suppression: dict[str, Any] | None
    effects: ReviewEffects


class AskRequest(ApiModel):
    question: str = Field(min_length=1, max_length=2000)


class AskResponse(ApiModel):
    answer: str
    disclaimer: str = (
        "AI assistant - grounded only in this incident's stored evidence. "
        "Not the audited record; see the narrative above for that."
    )
