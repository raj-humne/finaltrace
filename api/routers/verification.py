"""Single-use incident verification tokens.

Issuing a token requires a real SentinelTrace login (only an authenticated
analyst can vouch that this incident was genuinely raised). Verifying a
token deliberately does NOT - the entire point is that HR, a judge, an
external auditor, anyone handed a token, can confirm a report is authentic
without needing a SentinelTrace account at all.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.identity import Account
from api.routers.incidents import _get_incident_or_404
from api.schemas.verification import IssueTokenResponse, VerifyTokenRequest, VerifyTokenResponse
from api.verification import (
    IncidentNotFlagged,
    TokenAlreadyUsed,
    TokenMalformed,
    TokenSignatureInvalid,
    TokenUnknown,
    issue_verification_token,
    verify_and_consume_token,
)

router = APIRouter(tags=["verification"])


@router.post(
    "/incidents/{incident_id}/verification-token",
    response_model=IssueTokenResponse,
    status_code=201,
    dependencies=[Depends(get_current_account)],
)
def issue_token(
    incident_id: str, account: Account = Depends(get_current_account), db: Session = Depends(get_db)
) -> IssueTokenResponse:
    incident = _get_incident_or_404(db, incident_id)
    try:
        token = issue_verification_token(db, incident, issued_by=account.username)
    except IncidentNotFlagged as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return IssueTokenResponse(
        incident_id=incident_id, token=token, issued_at=dt.datetime.now(dt.timezone.utc)
    )


@router.post("/verify-token", response_model=VerifyTokenResponse)
def verify_token(payload: VerifyTokenRequest, request: Request, db: Session = Depends(get_db)) -> VerifyTokenResponse:
    """Deliberately outside get_current_account - see module docstring."""
    try:
        result = verify_and_consume_token(db, payload.token, used_from_ip=request.client.host if request.client else None)
    except TokenSignatureInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except TokenMalformed as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TokenUnknown as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TokenAlreadyUsed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return VerifyTokenResponse(
        valid=True, incident_id=result.incident_id, risk=result.risk, confidence=result.confidence,
        triage_lane=result.triage_lane, config_version=result.config_version,
        issued_at=result.issued_at, issued_by=result.issued_by,
        verified_at=dt.datetime.now(dt.timezone.utc),
        user_id=result.user_id, window_start=result.window_start, window_end=result.window_end,
        headline=result.headline, summary=result.summary, evidence=result.evidence,
    )
