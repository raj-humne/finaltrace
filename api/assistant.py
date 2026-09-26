"""Grounded incident Q&A assistant.

This is deliberately NOT the authoritative explanation path - that stays the
deterministic template grammar in engine/explain/narrative.py (ADR 0004: no
LLM in the record). This module is the "optional v2 gloss" ADR 0004 itself
names as the natural next step: a chat surface that can only answer using
the evidence already computed and stored for one specific incident, never
inventing a new claim about the user, the company, or security practice in
general. The UI must label every answer as an assistant, not the record.
"""
from __future__ import annotations

import groq

from api.schemas.incidents import IncidentDetailOut
from api.settings import settings

MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 1024
REQUEST_TIMEOUT_SECONDS = 20.0

SYSTEM_PROMPT = """\
You are a grounded assistant embedded in a security incident detail page. \
You are shown the complete stored evidence for exactly one incident: its \
narrative, its risk/confidence breakdown, every contributing signal, and \
the counterfactual attribution for each one.

Hard rules:
1. Answer ONLY using the evidence given below. Never use outside knowledge \
about this specific person, this company, or add details not present in \
the evidence.
2. If the question cannot be answered from the given evidence, say so \
plainly ("the evidence for this incident doesn't cover that") instead of \
guessing or generalizing.
3. You are a decision-support aid for a human analyst, not the authoritative \
record and not a decision-maker. Never suggest or imply an automated action \
(disabling access, contacting HR, etc.) - that is always a human's call.
4. Be concise: 2-4 sentences unless the analyst asks for more detail.
5. When you cite a number (risk, confidence, a signal's contribution), use \
the exact value from the evidence, not an approximation.
"""


class AssistantUnavailable(RuntimeError):
    """Raised when the assistant cannot answer - missing key, API error, or
    timeout. Callers turn this into a graceful degraded response, never a
    crash of the incident page the rest of the demo depends on."""


def _evidence_block(incident: IncidentDetailOut) -> str:
    lines = [
        f"INCIDENT {incident.incident_id}",
        f"User: {incident.user.name} ({incident.user.role}, {incident.user.department}, "
        f"peer cohort size {incident.user.cohort_size})",
        f"Window: {incident.window['start']} to {incident.window['end']} "
        f"({incident.window.get('duration_min', '?')} min)",
        f"Risk: {incident.score.risk:.1f}/100  Confidence: {incident.score.confidence:.2f}  "
        f"Triage lane: {incident.score.triage_lane}",
        f"Confidence terms: agreement={incident.score.confidence_terms.agreement:.2f}, "
        f"diversity={incident.score.confidence_terms.diversity:.2f}, "
        f"completeness={incident.score.confidence_terms.completeness:.2f}, "
        f"maturity={incident.score.confidence_terms.maturity:.2f}, "
        f"caps_applied={incident.score.confidence_terms.caps_applied}",
        "",
        f"HEADLINE: {incident.narrative.headline}",
        f"SUMMARY: {incident.narrative.summary}",
        "",
        "SIGNALS (rule, category, stage, contribution, phrase):",
    ]
    for s in incident.signals:
        lines.append(f"  - [{s.category}/stage {s.stage}] {s.rule_id}: "
                     f"+{s.contribution:.2f} pts - \"{s.phrase}\"")

    lines.append("")
    lines.append("COUNTERFACTUAL ATTRIBUTION (delta if this signal were removed):")
    for item in incident.attribution.items:
        flag = " [in minimal sufficient set]" if item.in_minimal_set else ""
        lines.append(f"  - {item.rule_id}: delta={item.delta:.2f} pts, "
                     f"risk_without={item.risk_without:.1f}{flag}")
    lines.append(f"Minimal sufficient set: {incident.attribution.minimal_sufficient_set}")
    lines.append(f"Alert threshold: {incident.attribution.alert_threshold}")

    if incident.campaign:
        lines.append("")
        lines.append(f"CAMPAIGN: {incident.campaign.campaign_id} - "
                     f"{incident.campaign.incident_count} incidents, "
                     f"{incident.campaign.first_seen} to {incident.campaign.last_seen}, "
                     f"stage progression {incident.campaign.stage_progression}")

    if incident.review:
        lines.append("")
        lines.append(f"ANALYST REVIEW: verdict={incident.review.verdict} "
                     f"by {incident.review.analyst_id} at {incident.review.reviewed_at}"
                     + (f" - note: {incident.review.note}" if incident.review.note else ""))

    return "\n".join(lines)


def answer_incident_question(incident: IncidentDetailOut, question: str) -> str:
    if not settings.groq_api_key:
        raise AssistantUnavailable("GROQ_API_KEY is not configured on the server")

    client = groq.Groq(api_key=settings.groq_api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    evidence = _evidence_block(incident)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=MAX_TOKENS,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"EVIDENCE FOR THIS INCIDENT:\n\n{evidence}\n\n"
                               f"ANALYST QUESTION: {question}",
                },
            ],
        )
    except groq.APIError as exc:
        raise AssistantUnavailable(f"assistant request failed: {exc}") from exc

    choice = response.choices[0] if response.choices else None
    content = choice.message.content if choice and choice.message else None
    if not content:
        raise AssistantUnavailable("assistant returned no text")
    return content
