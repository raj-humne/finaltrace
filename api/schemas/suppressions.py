from __future__ import annotations

import datetime as dt

from api.schemas.common import ApiModel


class SuppressionOut(ApiModel):
    suppression_id: int
    scope: str
    user_id: str | None
    cohort_key: str | None
    rule_id: str | None
    reason: str
    source_review: int | None
    status: str
    created_by: str
    created_at: dt.datetime
    expires_at: dt.datetime | None
