from __future__ import annotations

from api.schemas.common import ApiModel


class LiveDemoInjectRequest(ApiModel):
    actions: list[str] | None = None   # named steps, e.g. ["offhours_logon", "usb_connect_foreign"]
    scenario: bool = False             # True: run the full staged 5-step PRD scenario instead


class LiveDemoIncidentOut(ApiModel):
    incident_id: str
    risk: float
    confidence: float
    triage_lane: str
    signal_count: int
    event_count: int
    categories: list[str]
    stages: list[int]


class LiveDemoInjectResponse(ApiModel):
    user_id: str
    injected_through: str
    incidents_today: list[LiveDemoIncidentOut]
    total_incidents_for_user: int
