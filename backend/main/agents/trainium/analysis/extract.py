"""Evidence extraction: find the moments, before anything is scored.

Deliberately separate from scoring. Asking one call to score and justify at
once lets the model settle on a number and then hunt for quotes that fit it,
which produces confident citations for a conclusion it reached another way.
Extracting first, then scoring only from what was extracted, is what makes
"every score traces back to a moment" true rather than a claim.
"""

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from main.config import settings


class ExtractedMoment(BaseModel):
    # Which competency this speaks to, as a key from the rubric.
    competency_key: str
    # Verbatim from the transcript, so the report can be checked against it.
    quote: str
    # The segment this came from, which carries the real timestamps.
    segment_id: str
    positive: bool
    # Why this moment matters for that competency, one short sentence.
    note: str


class ExtractionResult(BaseModel):
    moments: list[ExtractedMoment] = Field(default_factory=list)


_PROMPT = """You are reviewing a transcript of a training session to find \
concrete moments that show how the trainer performed.

The competencies being assessed:
{competency_list}

The transcript, one line per segment, as [segment_id] speaker: text
{transcript}

Find the moments that genuinely evidence one of these competencies, good or \
bad. For each, give the competency key exactly as listed, the segment_id it \
came from, a short verbatim quote from that segment, whether it shows the \
competency being done well (positive) or poorly, and one sentence on why.

Rules:
- Quote verbatim from the segment. Never paraphrase or invent wording.
- Only cite the trainer's own turns, not what the learners said, except where \
a learner's reaction is itself the evidence (for example a learner saying they \
are still confused after an explanation).
- A moment can only evidence a competency in the list above.
- Prefer a smaller number of clear, specific moments over many weak ones. If a \
competency genuinely has no evidence in this transcript, return nothing for it \
rather than stretching to fill it.
- Do not judge delivery, body language or tone of voice: this is a transcript, \
none of that is visible here.
"""


def _format_competencies(competencies: list[dict]) -> str:
    lines = []
    for c in competencies:
        anchors = c.get("anchors", {})
        best = anchors.get(str(c.get("scale_max", 5)), "")
        lines.append(f"- {c['key']} ({c['label']}): strong looks like, {best}")
    return "\n".join(lines)


def _format_transcript(segments: list[dict]) -> str:
    return "\n".join(
        f"[{s['id']}] {s.get('speaker', '?')}: {s.get('text', '')}" for s in segments
    )


async def extract_moments(
    segments: list[dict], competencies: list[dict]
) -> list[ExtractedMoment]:
    """Pull evidence moments out of a transcript.

    Returns an empty list rather than raising when the transcript is too thin
    to say anything: a session where nobody spoke has no evidence, which is a
    real answer, not a failure.
    """
    if not segments:
        return []

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _PROMPT.format(
        competency_list=_format_competencies(competencies),
        transcript=_format_transcript(segments),
    )

    response = await client.aio.models.generate_content(
        model=settings.gemini_model_analysis,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractionResult,
            # Structured output on this model loops if the thinking trace is
            # allowed to leak into the JSON.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    result = response.parsed
    if result is None:
        return []

    # Drop anything citing a segment or competency that does not exist. The
    # model occasionally invents an id, and an unverifiable citation is worse
    # than no citation in a report that claims every score is traceable.
    valid_segments = {s["id"] for s in segments}
    valid_keys = {c["key"] for c in competencies}
    return [
        m
        for m in result.moments
        if m.segment_id in valid_segments and m.competency_key in valid_keys
    ]
