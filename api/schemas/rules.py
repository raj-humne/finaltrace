from __future__ import annotations

from api.schemas.common import ApiModel


class RuleOut(ApiModel):
    id: str
    name: str
    category: str
    stage: int
    weight: float
    requires_baseline: bool
    phrase: str


class RuleStatsOut(ApiModel):
    rule_id: str
    configured_weight: float
    fire_count: int
    fire_rate_per_user_day: float
    reviewed: int
    confirmed: int
    benign: int
    inconclusive: int
    observed_precision: float | None
    measured_log_odds: float | None
    weight_drift: float | None
    recommendation: str
