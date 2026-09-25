from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProblemDetail(ApiModel):
    """RFC 7807 error envelope (docs/05-API-SPEC.md section 0)."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    trace_id: str
