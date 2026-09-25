from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class UserListItem(ApiModel):
    user_id: str
    name: str
    role: str
    department: str
    cohort_key: str
    current_risk: float
    risk_ewma: float
    trend: str
    open_incidents: int
    departing_in_days: int | None


class UserListResponse(ApiModel):
    items: list[UserListItem]
    next_cursor: str | None
    total: int


class UserOrgOut(ApiModel):
    role: str
    department: str
    team: str | None
    supervisor: str | None
    cohort_size: int


class BaselineOut(ApiModel):
    days_available: int
    maturity: float
    working_window: dict[str, int] | None


class IncidentCounts(ApiModel):
    AUTO_FLAG: int = 0
    ANALYST_REVIEW: int = 0
    MONITOR: int = 0
    SUPPRESSED: int = 0


class UserDetailResponse(ApiModel):
    user_id: str
    name: str
    email: str | None
    org: UserOrgOut
    tenure_days: int
    departure_date: dt.date | None
    first_seen: dt.date
    last_seen: dt.date
    baseline: BaselineOut
    current_risk: float
    risk_ewma: float
    incident_counts: IncidentCounts


class RiskSeriesPoint(ApiModel):
    date: dt.date
    risk: float
    confidence: float
    risk_ewma: float | None
    signal_count: int
    incident_ids: list[str]


class PeerBandPoint(ApiModel):
    date: dt.date
    p50: float
    p90: float
    p99: float


class RiskSummary(ApiModel):
    peak_risk: float
    peak_date: dt.date | None
    days_above_threshold: int
    trend: str


class UserRiskResponse(ApiModel):
    user_id: str
    window: dict[str, dt.date]
    series: list[RiskSeriesPoint]
    peer_band: list[PeerBandPoint]
    summary: RiskSummary


class TimelineEvent(ApiModel):
    event_id: str
    ts: dt.datetime
    source: str
    action: str
    pc_id: str | None
    attrs: dict
    signal_ids: list[int]
    risk_after: float | None
    stage: int | None


class TimelineResponse(ApiModel):
    date: dt.date
    events: list[TimelineEvent]
    working_window: dict[str, int] | None
    final_risk: float | None
