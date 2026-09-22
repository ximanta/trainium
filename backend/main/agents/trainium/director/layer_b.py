from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from main.agents.trainium.director.state import PersonaState, SessionState
from main.config import settings

Action = Literal["speak", "react", "silent"]


class DirectorDecision(BaseModel):
    action: Action
    persona_id: str
    intent: str
    text: str
    urgency: int = Field(ge=1, le=5)


_PROMPT_TEMPLATE = """You are the Director of a simulated training classroom. A \
trainer is teaching live. You control which learner persona speaks next and \
exactly what they say, if anyone speaks at all.

Current objective: {current_objective}
Slide: {slide_number}
Elapsed: {elapsed_s:.0f}s
Objectives covered so far: {objectives_covered}

Trainer said recently (most recent last):
{transcript_recent}

Eligible personas (not on cooldown):
{persona_digest}

Recent classroom events: {recent_events}

Decide: should a persona speak, react non-verbally, or stay silent this turn?
If speak, pick exactly one eligible persona and write their exact spoken line, \
in character for their type and current emotional state. The line must be \
short (1-2 sentences), in a natural spoken register, no markdown, no lists, \
no meta-commentary about being an AI. Do not ask about objectives not yet \
covered. Set urgency 1-5 based on how much this needs the trainer's attention \
now versus could wait.
"""


def _format_persona_digest(personas: dict[str, PersonaState]) -> str:
    lines = []
    for p in personas.values():
        lines.append(
            f"- {p.persona_id} ({p.persona_type}): engagement={p.engagement:.2f}, "
            f"confusion={p.confusion:.2f}, knowledge_gaps={p.knowledge_gaps}"
        )
    return "\n".join(lines) if lines else "(none eligible)"


async def decide_and_speak(
    state: SessionState, eligible_persona_ids: list[str]
) -> DirectorDecision:
    """Layer B: one LLM call that both selects who speaks and generates their
    exact line. Merging these (rather than a select call then a persona call)
    removes one LLM round trip from the critical path, architecture doc §3.3.
    Uses the lite model per the M2 latency finding: this call is
    latency-critical and does not need gemini-3.8-flash's stronger reasoning
    for a short in-character line.
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    eligible_personas = {
        pid: state.persona_states[pid]
        for pid in eligible_persona_ids
        if pid in state.persona_states
    }

    prompt = _PROMPT_TEMPLATE.format(
        current_objective=state.current_objective_id or "(none set)",
        slide_number=state.slide_number,
        elapsed_s=state.elapsed_s,
        objectives_covered=state.objectives_covered,
        transcript_recent="\n".join(state.transcript_recent[-6:]) or "(nothing yet)",
        persona_digest=_format_persona_digest(eligible_personas),
        recent_events=state.recent_events,
    )

    response = client.models.generate_content(
        model=settings.gemini_model_flash_lite,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=200,
            response_mime_type="application/json",
            response_schema=DirectorDecision,
        ),
    )
    decision = DirectorDecision.model_validate_json(response.text)

    if decision.action == "speak" and decision.persona_id not in eligible_personas:
        # The model picked an ineligible persona despite the prompt listing
        # only eligible ones; fail safe to silence rather than let an
        # off-cooldown persona speak, since Layer A's guarantee is the whole
        # point of this two-layer design.
        return DirectorDecision(
            action="silent", persona_id="", intent="", text="", urgency=1
        )

    return decision
