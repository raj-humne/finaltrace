"""Live-injection demo (api/live_demo.py). Any authenticated account may call
this - it's a staged demo mechanism against a small dedicated synthetic
dataset (data/demo_live/), not a governance-sensitive action, so it needs no
elevated role the way suppression activation does.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.live_demo import ACTIONS, UnknownDemoAction, inject_and_rescore, reset_demo_events
from api.schemas.live_demo import LiveDemoInjectRequest, LiveDemoInjectResponse

router = APIRouter(prefix="/live-demo", tags=["live-demo"], dependencies=[Depends(get_current_account)])


@router.get("/actions")
def list_actions() -> dict[str, list[str]]:
    return {"actions": sorted(ACTIONS)}


@router.post("/inject", response_model=LiveDemoInjectResponse)
def inject(payload: LiveDemoInjectRequest, db: Session = Depends(get_db)) -> LiveDemoInjectResponse:
    if not payload.scenario and not payload.actions:
        raise HTTPException(status_code=400, detail="pass either scenario=true or a non-empty actions list")
    try:
        result = inject_and_rescore(payload.actions, payload.scenario, db)
    except UnknownDemoAction as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LiveDemoInjectResponse(**result)


@router.post("/reset", status_code=204)
def reset(db: Session = Depends(get_db)) -> None:
    reset_demo_events(db)
