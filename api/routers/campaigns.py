from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.correlation import Campaign, Incident
from api.models.explain import Narrative
from api.schemas.campaigns import (
    CampaignDetailOut,
    CampaignListItem,
    CampaignListResponse,
    StageProgressionPoint,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"], dependencies=[Depends(get_current_account)])

_STAGE_NAMES = {0: "context", 1: "recon", 2: "staging", 3: "collection", 4: "exfiltration", 5: "evasion"}


@router.get("", response_model=CampaignListResponse)
def list_campaigns(
    user_id: str | None = None, min_stage: int | None = None, limit: int = 50, db: Session = Depends(get_db)
) -> CampaignListResponse:
    stmt = select(Campaign)
    if user_id:
        stmt = stmt.where(Campaign.user_id == user_id)
    if min_stage is not None:
        stmt = stmt.where(Campaign.max_stage >= min_stage)
    rows = db.scalars(stmt.order_by(Campaign.last_seen.desc()).limit(limit)).all()
    items = [
        CampaignListItem(
            campaign_id=c.campaign_id, user_id=c.user_id, first_seen=c.first_seen, last_seen=c.last_seen,
            incident_count=c.incident_count, max_stage=c.max_stage, peak_risk=c.peak_risk,
        )
        for c in rows
    ]
    return CampaignListResponse(items=items, total=len(items))


def _campaign_risk(campaign: Campaign) -> float:
    """No Track A campaign-risk formula exists yet. This is Track B's
    documented placeholder pending it: peak_risk plus a small bonus per extra
    kill-chain stage the campaign spans, reflecting that a progression
    covering more stages is more concerning than a single spike, capped at
    100."""
    distinct_stages = len(set(campaign.stage_progression))
    return min(100.0, campaign.peak_risk + 2.0 * max(0, distinct_stages - 1))


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)) -> CampaignDetailOut:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"No campaign with id {campaign_id}")

    incidents = db.scalars(
        select(Incident).where(Incident.campaign_id == campaign_id).order_by(Incident.window_start.asc())
    ).all()
    progression: list[StageProgressionPoint] = []
    for incident in incidents:
        narrative = db.get(Narrative, incident.incident_id)
        progression.append(
            StageProgressionPoint(
                date=incident.window_start.date(),
                stage=max(incident.killchain_stages) if incident.killchain_stages else 0,
                incident_id=incident.incident_id,
                risk=incident.risk,
                headline=narrative.headline if narrative else "",
            )
        )

    span_days = (campaign.last_seen - campaign.first_seen).days
    stage_names = [_STAGE_NAMES.get(s, str(s)) for s in campaign.stage_progression]
    if len(stage_names) >= 2:
        narrative_text = (
            f"Over {span_days} days this user progressed from {stage_names[0]} through "
            f"{', '.join(stage_names[1:-1]) + ' ' if len(stage_names) > 2 else ''}to {stage_names[-1]} "
            f"across {campaign.incident_count} incidents. No single day exceeded the alert threshold "
            f"before {campaign.last_seen.isoformat()}; the progression did."
        )
    else:
        narrative_text = f"This user has one incident on record with no multi-stage progression yet."

    return CampaignDetailOut(
        campaign_id=campaign.campaign_id,
        user_id=campaign.user_id,
        first_seen=campaign.first_seen,
        last_seen=campaign.last_seen,
        incident_count=campaign.incident_count,
        peak_risk=campaign.peak_risk,
        campaign_risk=_campaign_risk(campaign),
        max_stage=campaign.max_stage,
        stage_progression=progression,
        narrative=narrative_text,
    )
