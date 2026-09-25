from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from api.schemas.common import ApiModel


class IngestOptions(ApiModel):
    chunk_size: int = 250_000
    dry_run: bool = False


class IngestRequest(ApiModel):
    source: str
    adapter: str = "cert_r42"
    mode: str  # "file" | "inline"
    path: str | None = None
    records: list[dict[str, Any]] | None = None
    options: IngestOptions = Field(default_factory=IngestOptions)


class RejectSample(ApiModel):
    row: int
    reason: str
    raw: str


class IngestRunOut(ApiModel):
    run_id: str
    status: str
    source: str
    accepted: int
    rejected: int
    duplicates_skipped: int
    ts_range: list[dt.datetime | None]
    rejects_sample: list[RejectSample]
    links: dict[str, str]


class IngestRunSummary(ApiModel):
    run_id: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    rows_accepted: int
    rows_rejected: int
    adapter_id: str | None
