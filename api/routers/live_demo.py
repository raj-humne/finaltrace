"""Live-injection demo (api/live_demo.py). Any authenticated account may call
this - it's a staged demo mechanism against a small dedicated synthetic
dataset (data/demo_live/), not a governance-sensitive action, so it needs no
elevated role the way suppression activation does.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.live_demo import ACTIONS, UnknownDemoAction, inject_and_rescore, reset_demo_events
from api.live_demo_console import CONSOLE_HTML
from api.schemas.live_demo import LiveDemoInjectRequest, LiveDemoInjectResponse

router = APIRouter(prefix="/live-demo", tags=["live-demo"])

# The console page must be reachable with NO session cookie yet - it's the
# page someone opens to log in from a browser that has never talked to this
# API before. Every other route below still requires a real session, via a
# router-level dependency scoped to just those routes (APIRouter itself has
# no per-route dependency removal, so this one is registered on a
# sub-router instead of the top-level one).
_auth_router = APIRouter(dependencies=[Depends(get_current_account)])


@router.get("/console", response_class=HTMLResponse, include_in_schema=False)
def console() -> str:
    return CONSOLE_HTML


@_auth_router.get("/actions")
def list_actions() -> dict[str, list[str]]:
    return {"actions": sorted(ACTIONS)}


@_auth_router.post("/inject", response_model=LiveDemoInjectResponse)
def inject(payload: LiveDemoInjectRequest, db: Session = Depends(get_db)) -> LiveDemoInjectResponse:
    if not payload.scenario and not payload.actions:
        raise HTTPException(status_code=400, detail="pass either scenario=true or a non-empty actions list")
    try:
        result = inject_and_rescore(payload.actions, payload.scenario, db)
    except UnknownDemoAction as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LiveDemoInjectResponse(**result)


@_auth_router.post("/reset", status_code=204)
def reset(db: Session = Depends(get_db)) -> None:
    reset_demo_events(db)


router.include_router(_auth_router)
