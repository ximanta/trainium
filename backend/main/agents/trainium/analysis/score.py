"""Scoring: turn gathered evidence into numbers against the rubric anchors.

This call never sees the transcript or the video, only the moments already
extracted. That is the point: it cannot form a view from the raw material and
then pick supporting quotes, because the quotes are all it has.
"""

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from main.config import settings


class ScoredCompetency(BaseModel):
    competency_key: str
    # Scale bounds are enforced here rather than trusted: an unconstrained
    # trailing int is where the decoder tends to wander.
    score: int = Field(ge=1, le=5)
    rationale: str


class ScoringResult(BaseModel):
    scores: list[ScoredCompetency] = Field(default_factory=list)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


_PROMPT = """You are scoring a training session against a rubric, using only \
the evidence gathered from it.

The rubric:
{rubric}

The evidence, grouped by competency:
{evidence}

Score each competency in the rubric against its anchors. Then write a short \
summary of the session, two or three specific strengths, and two or three \
specific things to improve.

Rules:
- Score only from the evidence above. You have not seen the session itself.
- Where a competency has no evidence, score it 3 and say plainly in the \
rationale that there was nothing in this session to judge it on. Do not \
invent a reason to go higher or lower.
- The rationale must refer to the actual evidence, not restate the anchor.
- Strengths and improvements must be specific to this session and actionable. \
"Engage learners more" is useless; "you answered Arjun's question but did not \
check whether Kavya followed it" is useful.
- Address the trainer as "you". This is read by the person who taught it.
"""


def _format_rubric(competencies: list[dict]) -> str:
    lines = []
    for c in competencies:
        lines.append(f"- {c['key']} ({c['label']}):")
        for level, text in sorted(c.get("anchors", {}).items()):
            lines.append(f"    {level}: {text}")
    return "\n".join(lines)


def _format_evidence(evidence: list[dict], competencies: list[dict]) -> str:
    by_key: dict[str, list[dict]] = {c["key"]: [] for c in competencies}
    for e in evidence:
        by_key.setdefault(e["competency_key"], []).append(e)

    lines = []
    for key, items in by_key.items():
        lines.append(f"\n{key}:")
        if not items:
            lines.append("  (no evidence found in this session)")
            continue
        for e in items:
            mark = "good" if e.get("positive") else "poor"
            when = f"{int(e.get('ts_start', 0)) // 60}:{int(e.get('ts_start', 0)) % 60:02d}"
            body = e.get("quote") or e.get("observation", "")
            lines.append(f'  [{mark} at {when}] "{body}"')
    return "\n".join(lines)


async def score_competencies(
    evidence: list[dict], competencies: list[dict]
) -> ScoringResult:
    """Score a rubric from evidence alone."""
    if not competencies:
        return ScoringResult()

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _PROMPT.format(
        rubric=_format_rubric(competencies),
        evidence=_format_evidence(evidence, competencies),
    )

    response = await client.aio.models.generate_content(
        model=settings.gemini_model_analysis,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ScoringResult,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    result = response.parsed or ScoringResult()

    # Guarantee one score per competency whatever came back, so a report can
    # never silently omit a criterion the rubric promised to assess.
    returned = {s.competency_key: s for s in result.scores}
    result.scores = [
        returned.get(
            c["key"],
            ScoredCompetency(
                competency_key=c["key"],
                score=3,
                rationale="No evidence was found in this session for this competency.",
            ),
        )
        for c in competencies
    ]
    return result
