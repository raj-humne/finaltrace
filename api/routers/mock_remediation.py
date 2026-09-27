"""Mock remediation service (Challenge 1, Phase 6).

Stands in for a real SOAR/firewall/IAM remediation vendor: it receives the
structured JSON payload api/mitigation.py dispatches, validates it, "logs"
the request, and returns a simulated isolation result. No dependency on our
own session auth - a real remediation vendor's webhook receiver would not
hold our analysts' session cookies, so this endpoint is intentionally
unauthenticated, exactly like an inbound webhook target normally is.

IMPORTANT: this never performs a real action. It never disables an OS
account, blocks a real network interface, changes a firewall rule, or
touches any real infrastructure - every response is clearly labeled
simulated, per the hackathon's explicit "no destructive actions" rule.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from api.schemas.mitigation import RemediationPayload

logger = logging.getLogger("sentinel.mock_remediation")

router = APIRouter(prefix="/mock-remediation", tags=["mock-remediation"])


@router.post("/isolate")
def isolate(payload: RemediationPayload) -> dict:
    logger.info(
        "SIMULATED_ISOLATION request incident_id=%s target_type=%s target=%s threat_weight=%.1f",
        payload.incident_id, payload.target_type, payload.target, payload.threat_weight,
    )
    return {
        "success": True,
        "simulated": True,
        "action": payload.action,
        "target_type": payload.target_type,
        "target": payload.target,
        "status": "ISOLATED",
    }
