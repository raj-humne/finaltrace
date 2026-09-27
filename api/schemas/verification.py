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
