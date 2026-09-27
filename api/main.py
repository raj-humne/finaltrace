from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_error_handlers
from api.routers import (
    analyze,
    auth,
    campaigns,
    detection_health,
    eval as eval_router,
    health,
    incidents,
    ingest,
    live_demo,
    mitigation,
    mock_remediation,
    rules,
    suppressions,
    users,
    verification,
)
from api.settings import settings

app = FastAPI(title="SentinelTrace API", version="1.0.0", openapi_url="/api/v1/openapi.json", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

api_v1 = "/api/v1"
app.include_router(health.router, prefix=api_v1)
app.include_router(auth.router, prefix=api_v1)
app.include_router(suppressions.router, prefix=api_v1)
app.include_router(users.router, prefix=api_v1)
app.include_router(incidents.router, prefix=api_v1)
app.include_router(campaigns.router, prefix=api_v1)
app.include_router(rules.router, prefix=api_v1)
app.include_router(detection_health.router, prefix=api_v1)
app.include_router(eval_router.router, prefix=api_v1)
app.include_router(analyze.router, prefix=api_v1)
app.include_router(ingest.router, prefix=api_v1)
app.include_router(live_demo.router, prefix=api_v1)
app.include_router(mitigation.router, prefix=api_v1)
app.include_router(mock_remediation.router, prefix=api_v1)
app.include_router(verification.router, prefix=api_v1)
