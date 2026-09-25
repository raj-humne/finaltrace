"""GET /eval/report proxies the artifact Track D's engine/eval/harness.py
writes (docs/07-EVALUATION.md section 8). Track B does not compute these
numbers — D5 in PROMPTS.md requires the harness itself to refuse to emit a
report without a real-CERT provenance marker, so fabricating one here would
defeat that guard. Until the harness has run, this honestly 404s.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_account

router = APIRouter(prefix="/eval", tags=["eval"], dependencies=[Depends(get_current_account)])

_REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "artifacts" / "eval_report.json"


@router.get("/report")
def get_eval_report(config_version: str | None = Query(default=None)) -> dict[str, Any]:
    if not _REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No evaluation report has been generated yet. Run engine/eval/harness.py first.",
        )
    report = json.loads(_REPORT_PATH.read_text(encoding="utf-8"))
    if config_version and report.get("config_version") != config_version:
        raise HTTPException(
            status_code=404,
            detail=f"No evaluation report for config_version {config_version}",
        )
    return report
