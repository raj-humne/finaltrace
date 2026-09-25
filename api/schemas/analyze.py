from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class AnalyzeOptions(ApiModel):
    include_graph: bool = False
    force_recompute: bool = False


class AnalyzeRequest(ApiModel):
    user_id: str
    date_from: dt.date
    date_to: dt.date
    options: AnalyzeOptions = AnalyzeOptions()


class AnalyzeDailyPoint(ApiModel):
    date: dt.date
    risk: float
    confidence: float
    signal_count: int


class AnalyzeResponse(ApiModel):
    user_id: str
    window: dict[str, dt.date]
    computed_in_ms: float
    from_cache: bool
    peak_risk: float
    incidents: list[str]
    campaigns: list[str]
    daily: list[AnalyzeDailyPoint]
    narrative: str | None
