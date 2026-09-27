from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class IssueTokenResponse(ApiModel):
    incident_id: str
    token: str
    issued_at: dt.datetime
    note: str = "Single-use. This token can verify the report exactly once."


class VerifyTokenRequest(ApiModel):
    token: str


class VerifyTokenResponse(ApiModel):
    valid: bool
    incident_id: str
    risk: float
    confidence: float
    triage_lane: str
    config_version: str
    issued_at: dt.datetime
    issued_by: str
    verified_at: dt.datetime
    # Proof the flagged user actually did something, not just a score.
    user_id: str
    window_start: dt.datetime
    window_end: dt.datetime
    headline: str
    summary: str
    evidence: list[str]
