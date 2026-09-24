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


class UndeterminedCompetency(BaseModel):
    """A competency the session gave no basis to judge.

    Kept distinct from a score of 3. Folding "nothing happened" into the middle
    of the scale makes it indistinguishable from genuinely average performance,
    so a trainer cannot tell whether they were assessed and found middling or
    never assessed at all.
    """

    competency_key: str
    reason: str


class ScoringResult(BaseModel):
    scores: list[ScoredCompetency] = Field(default_factory=list)
    undetermined: list[UndeterminedCompetency] = Field(default_factory=list)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


_PROMPT = """You are scoring a training session against a rubric, using only \
the evidence gathered from it.

The rubric:
{rubric}

What happened in the session:
{session_facts}

The evidence, grouped by competency:
{evidence}

Score each competency in the rubric against its anchors. Then write a short \
summary of the session, what genuinely worked, and what to work on.

Write the summary last, after you have scored everything, and let the scores \
decide its tone. A session that scored badly must read as a session that went \
badly. Lead with what dominated it, not with the most flattering thing you can \
find: a trainer who explained one concept well but covered a fraction of the \
material had a poor session, and a summary that opens on the explanation is \
misleading. Be direct and factual, never harsh, and never soften a real \
problem into a trailing clause.

Strengths are optional. List only things that actually happened and actually \
helped, at most three. If the session has none worth naming, return an empty \
list rather than inventing one: manufactured praise in a bad report teaches \
the trainer nothing and costs you their trust in the rest of it.

Rules:
- Score only from the evidence and the session facts above. You have not seen \
the session itself.
- The session facts are measured, not inferred. Treat them as true. They are \
the basis for judging pacing and coverage, which no quote can show.
- Where a competency has no evidence, do NOT score it. Put it in undetermined \
instead, with a one-line reason saying what was absent, for example "no demo \
was run in this session" or "no lab exercise took place". Never assign a \
middling score to stand in for an absence.
- Every competency must appear exactly once, either in scores or in \
undetermined, never both and never neither.
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
    evidence: list[dict],
    competencies: list[dict],
    session_facts: str = "",
    fact_backed_keys: frozenset[str] = frozenset(),
) -> ScoringResult:
    """Score a rubric from evidence and measured session facts.

    `fact_backed_keys` names competencies that the facts alone can support, so
    they stay scorable without a quote. Time Management is the case this exists
    for: pacing is never something anybody says, it is measured.
    """
    if not competencies:
        return ScoringResult()

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _PROMPT.format(
        rubric=_format_rubric(competencies),
        session_facts=session_facts or "(nothing measured for this session)",
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

    # A score is only admissible where there is something to score from.
    # Checked here rather than trusted to the prompt, because a model told not
    # to score an empty competency will still occasionally do it. Fact-backed
    # competencies count as supported when facts were actually measured.
    with_evidence = {e["competency_key"] for e in evidence}
    if session_facts:
        with_evidence |= set(fact_backed_keys)

    # Every competency must land in exactly one bucket, so a report can never
    # silently omit a criterion the rubric promised to assess. Anything the
    # model left out entirely is undetermined rather than invented as a score:
    # a number nobody produced is worse than an honest gap.
    scored = {s.competency_key: s for s in result.scores if s.competency_key in with_evidence}
    undetermined = {u.competency_key: u for u in result.undetermined}

    result.scores = [scored[c["key"]] for c in competencies if c["key"] in scored]
    result.undetermined = [
        undetermined.get(
            c["key"],
            UndeterminedCompetency(
                competency_key=c["key"],
                reason="Nothing in this session provided a basis to judge this.",
            ),
        )
        for c in competencies
        if c["key"] not in scored
    ]
    return result
