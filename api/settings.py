"""Runtime settings, read from environment only. Nothing sensitive is committed."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_cookie_name: str
    session_ttl_minutes: int
    session_idle_ttl_minutes: int
    cookie_secure: bool
    lockout_threshold: int
    lockout_base_seconds: float
    lockout_max_seconds: float
    cors_origins: tuple[str, ...]
    demo_data_path: Path
    groq_api_key: str | None
    mitigation_enabled: bool
    mitigation_threat_weight_threshold: float
    mitigation_webhook_url: str
    mitigation_webhook_timeout_seconds: float
    mitigation_payload_dir: Path


def get_settings() -> Settings:
    db_url = os.environ.get("SENTINEL_DB", f"sqlite:///{(REPO_ROOT / 'data' / 'demo.db').as_posix()}")
    return Settings(
        database_url=db_url,
        session_cookie_name=os.environ.get("SENTINEL_SESSION_COOKIE", "st_session"),
        session_ttl_minutes=int(os.environ.get("SENTINEL_SESSION_TTL_MIN", "480")),
        session_idle_ttl_minutes=int(os.environ.get("SENTINEL_SESSION_IDLE_TTL_MIN", "30")),
        cookie_secure=os.environ.get("SENTINEL_COOKIE_SECURE", "false").lower() == "true",
        lockout_threshold=int(os.environ.get("SENTINEL_LOCKOUT_THRESHOLD", "5")),
        lockout_base_seconds=float(os.environ.get("SENTINEL_LOCKOUT_BASE_SECONDS", "1.0")),
        lockout_max_seconds=float(os.environ.get("SENTINEL_LOCKOUT_MAX_SECONDS", "900.0")),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("SENTINEL_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        ),
        demo_data_path=REPO_ROOT / "data",
        groq_api_key=os.environ.get("GROQ_API_KEY"),
        mitigation_enabled=os.environ.get("MITIGATION_ENABLED", "true").lower() == "true",
        mitigation_threat_weight_threshold=float(os.environ.get("MITIGATION_THREAT_WEIGHT_THRESHOLD", "70")),
        mitigation_webhook_url=os.environ.get(
            "MITIGATION_WEBHOOK_URL", "http://localhost:8000/api/v1/mock-remediation/isolate"
        ),
        mitigation_webhook_timeout_seconds=float(os.environ.get("MITIGATION_WEBHOOK_TIMEOUT_SECONDS", "5")),
        mitigation_payload_dir=Path(
            os.environ.get("MITIGATION_PAYLOAD_DIR", str(REPO_ROOT / "data" / "mitigation_payloads"))
        ),
    )


settings = get_settings()
