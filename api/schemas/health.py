from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class HealthData(ApiModel):
    ts_min: dt.datetime | None
    ts_max: dt.datetime | None
    users: int
    events: int
    last_pipeline_run: dt.datetime | None


class HealthEngine(ApiModel):
    rules_loaded: int
    cohort_models: int
    mode: str


class HealthResponse(ApiModel):
    status: str
    config_version: str
    data: HealthData
    engine: HealthEngine
