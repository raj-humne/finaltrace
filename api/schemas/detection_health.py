from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class AlertVolume(ApiModel):
    incidents_per_day: float
    per_1k_users_per_day: float


class Compression(ApiModel):
    signals_per_incident_mean: float
    events_per_incident_mean: float


class CalibrationBin(ApiModel):
    confidence_range: list[float]
    n: int
    observed_precision: float | None


class Calibration(ApiModel):
    bins: list[CalibrationBin]
    ece: float


class TopFiringRule(ApiModel):
    rule_id: str
    count: int
    observed_precision: float | None


class DetectionHealthOut(ApiModel):
    window: dict[str, dt.date]
    alert_volume: AlertVolume
    lane_mix: dict[str, int]
    compression: Compression
    calibration: Calibration
    top_firing_rules: list[TopFiringRule]
    warnings: list[str]
