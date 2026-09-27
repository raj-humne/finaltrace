from __future__ import annotations

import datetime as dt
from typing import Any

from api.schemas.common import ApiModel


class GraphSummaryOut(ApiModel):
    node_count: int
    edge_count: int
    categories: int
    stages: list[int]


class RemediationPayload(ApiModel):
    """The structured JSON body sent to the (mock) remediation webhook, and
    stored verbatim in `MitigationAction.payload` for auditability."""

    incident_id: str
    threat_weight: float
    threshold: float
    user_id: str
    flagged_ip: str | None
    action: str
    target_type: str
    target: str | None
    graph_summary: GraphSummaryOut
    nodes: list[dict[str, Any]]
    reason: str
    evidence: list[str]
    timestamp: dt.datetime


class MitigationActionOut(ApiModel):
    mitigation_action_id: int
    incident_id: str
    user_id: str
    flagged_ip: str | None
    threat_weight: float
    threshold: float
    action_type: str
    target_type: str
    target_value: str | None
    status: str
    webhook_url: str
    webhook_status_code: int | None
    webhook_response: str | None
    isolation_status: str
    reason: str
    error_message: str | None
    payload: dict[str, Any]
    created_at: dt.datetime
    completed_at: dt.datetime | None


class MitigationStatusOut(ApiModel):
    """GET /mitigation/status - a safe, non-secret probe of the pipeline's
    current configuration, for the dashboard and for demo verification."""

    enabled: bool
    threshold: float
    webhook_url: str
    webhook_timeout_seconds: float
