from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class CampaignListItem(ApiModel):
    campaign_id: str
    user_id: str
    first_seen: dt.date
    last_seen: dt.date
    incident_count: int
    max_stage: int
    peak_risk: float


class CampaignListResponse(ApiModel):
    items: list[CampaignListItem]
    total: int


class StageProgressionPoint(ApiModel):
    date: dt.date
    stage: int
    incident_id: str
    risk: float
    headline: str


class CampaignDetailOut(ApiModel):
    campaign_id: str
    user_id: str
    first_seen: dt.date
    last_seen: dt.date
    incident_count: int
    peak_risk: float
    campaign_risk: float
    max_stage: int
    stage_progression: list[StageProgressionPoint]
    narrative: str
