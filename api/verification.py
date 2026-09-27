"""Issue and verify single-use signed tokens proving a flagged incident's
report is genuine.

The signature (JWT/HS256) proves the CLAIMS in the token weren't altered
after issuance - a tampered token fails to decode at all, full stop. The
`used` flag in the database is a SEPARATE, necessary layer: a valid
signature never expires or gets consumed on its own, so single-use has to be
enforced server-side, not by the token format. Both matter; neither alone
is "prove this report is real and hasn't been replayed."

Only AUTO_FLAG incidents are eligible - a MONITOR-lane incident was never
"raised" in the sense that prompted this feature, and issuing a token for
every incident would make the eligibility check meaningless.
"""
from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

import jwt
from sqlalchemy.orm import Session

from api.models.correlation import Incident
from api.models.verification import IncidentVerificationToken
from api.security.audit import write_audit
from api.settings import settings

ALGORITHM = "HS256"


class VerificationError(Exception):
    """Base class for every reason a token check can fail - the router
    translates each subclass to a distinct HTTP status, and the response
    always says which one, never a generic 'invalid'."""


class IncidentNotFlagged(VerificationError):
    """403: only an AUTO_FLAG incident can have a token issued for it."""


class TokenMalformed(VerificationError):
    """400: not a JWT, or the wrong algorithm/claims shape."""


class TokenSignatureInvalid(VerificationError):
    """401: decodes as a JWT, but the signature doesn't match - the token
    was forged or its payload was edited after signing. This is the exact
    "identify the fake report" case."""


class TokenUnknown(VerificationError):
    """404: signature is valid, but no token with this jti was ever issued
    by this server - e.g. signed with a different server's secret, or the
    database was reset since issuance."""


class TokenAlreadyUsed(VerificationError):
    """409: signature is valid and the token was genuinely issued, but it
    has already been consumed once - single-use, exactly as requested."""


@dataclass(frozen=True)
class VerifiedReport:
    incident_id: str
    risk: float
    confidence: float
    triage_lane: str
    config_version: str
    issued_at: dt.datetime
    issued_by: str


def issue_verification_token(db: Session, incident: Incident, issued_by: str) -> str:
    if incident.triage_lane != "AUTO_FLAG":
        raise IncidentNotFlagged(
            f"incident {incident.incident_id} is not AUTO_FLAG (currently "
            f"{incident.triage_lane}) - a verification token can only be issued "
            "for a raised incident"
        )

    jti = secrets.token_urlsafe(24)
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "jti": jti,
        "incident_id": incident.incident_id,
        "risk": round(incident.risk, 2),
        "confidence": round(incident.confidence, 2),
        "triage_lane": incident.triage_lane,
        "config_version": incident.config_version,
        "iat": int(now.timestamp()),
        "iss": "sentineltrace",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)

    db.add(IncidentVerificationToken(
        jti=jti, incident_id=incident.incident_id, issued_at=now, issued_by=issued_by,
    ))
    write_audit(
        db, actor=issued_by, action="verification_token_issued",
        object_type="incident", object_id=incident.incident_id,
        after={"jti": jti},
    )
    db.commit()
    return token


def verify_and_consume_token(db: Session, token: str, used_from_ip: str | None = None) -> VerifiedReport:
    """Decoding the token proves its claims are authentic and unaltered.
    Looking up and marking the database row proves it hasn't been shown to
    anyone before. Order matters: a forged token must fail at the signature
    check (TokenSignatureInvalid), before ever touching the database, so a
    fake token can never be reported as merely 'already used'."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.InvalidSignatureError as exc:
        raise TokenSignatureInvalid(
            "signature does not match - this token was forged or its contents "
            "were edited after signing. This report cannot be verified as authentic."
        ) from exc
    except jwt.DecodeError as exc:
        raise TokenMalformed(f"not a valid token: {exc}") from exc

    jti = claims.get("jti")
    row = db.get(IncidentVerificationToken, jti) if jti else None
    if row is None:
        raise TokenUnknown(
            "this token's signature is well-formed but no matching record was "
            "ever issued by this server - it cannot be confirmed as authentic"
        )
    if row.used:
        raise TokenAlreadyUsed(
            f"this token was already used at {row.used_at.isoformat() if row.used_at else 'an earlier time'} "
            "- it is single-use and cannot verify a report a second time"
        )

    row.used = True
    row.used_at = dt.datetime.now(dt.timezone.utc)
    row.used_from_ip = used_from_ip
    write_audit(
        db, actor="(external verifier)", action="verification_token_consumed",
        object_type="incident", object_id=claims["incident_id"],
        after={"jti": jti, "used_from_ip": used_from_ip},
    )
    db.commit()

    return VerifiedReport(
        incident_id=claims["incident_id"], risk=claims["risk"], confidence=claims["confidence"],
        triage_lane=claims["triage_lane"], config_version=claims["config_version"],
        issued_at=dt.datetime.fromtimestamp(claims["iat"], tz=dt.timezone.utc),
        issued_by=row.issued_by,
    )
