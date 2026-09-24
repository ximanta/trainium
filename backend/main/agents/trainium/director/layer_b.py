from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from main.agents.trainium.director.state import PersonaState, SessionState
from main.agents.trainium.models import describe_trainer
from main.config import settings

Action = Literal["speak", "react", "silent"]


class DirectorDecision(BaseModel):
    action: Action
    persona_id: str
    intent: str
    text: str
    urgency: int = Field(ge=1, le=5)
    # True when the persona is interrupting with something off the current
    # thread and should wait to be called on. False when they are answering
    # the trainer directly, which in a real classroom needs no hand raise.
    needs_hand_raise: bool = False


# Trainium's primary cohort. Admins can override this per session, but the
# default has to be a real audience rather than a generic "learner", or the
# personas drift into sounding like senior consultants reviewing the material.
DEFAULT_AUDIENCE = (
    "Fresh engineering graduates from tier-2 Indian colleges, in their first "
    "corporate training programme. They are bright and motivated but new to "
    "the subject and to professional settings. They ask basic, practical, "
    "sometimes naive questions, worry about syntax and tooling, relate things "
    "to college projects or placement prep, and are unsure whether their "
    "question sounds silly. They do not critique the material like an "
    "architect would."
)

_PROMPT_TEMPLATE = """You are the Director of a simulated training classroom. A \
trainer is teaching live. You control which learner persona speaks next and \
exactly what they say, if anyone speaks at all.

Who these learners are: {audience}
Write every line so it sounds like that person actually talking, not like a \
consultant or an expert reviewer. Match their vocabulary, their confidence \
level, and the kinds of things they would genuinely be unsure about.

The trainer: {trainer_description}
When a persona addresses the trainer directly, they use that form and no other. \
Never guess an honorific the trainer has not been given.

Current objective: {current_objective}
Slide: {slide_number}
Elapsed: {elapsed_s:.0f}s
Objectives covered so far: {objectives_covered}

Conversation so far (most recent last, includes what the learners already said):
{transcript_recent}
Trainer is currently mid-sentence saying (not finished yet): {in_progress_partial}

Eligible personas (not on cooldown):
{persona_digest}

Recent classroom events: {recent_events}

Screen: {screen_status}

{reply_instruction}

Decide: should a persona speak, react non-verbally, or stay silent this turn?
If speak, set persona_id to that persona's id exactly as listed above, and \
write their exact spoken line, in character for their type and current \
emotional state. The line must be short (1-2 sentences), in a natural spoken \
register, no markdown, no lists, no meta-commentary about being an AI. Do not \
ask about objectives not yet covered. Set urgency 1-5 based on how much this \
needs the trainer's attention now versus could wait.

Ask about the substance of what is being taught, never about how the slide \
was made. Typos, fonts, layout, stock illustrations and clip-art are not \
teaching content: a learner in a real class does not ask whether they need to \
understand the gears in a decorative graphic, or raise a spelling mistake as \
though it mattered. If the only thing you can find to say is about the \
artwork or the wording of the slide rather than the idea on it, stay silent.

Prefer a follow-up to a new topic. If the trainer has just answered someone, \
the most natural next line is usually that person saying whether it landed, \
or pushing once more on the part still unclear. A class where every turn \
opens an unrelated new question does not sound like a conversation.

If the persona introduces themselves or is asked who is speaking, they must \
use the name given for them above. Never invent a different name.

Never repeat a point another learner already made. If someone has already \
confirmed they can hear the trainer, or already answered the trainer's \
question, do not say it again: either add something genuinely new or stay \
silent. Read the conversation above before deciding.

Spread participation across the class like a real classroom would: prefer a \
persona who has not spoken yet, and avoid picking the same persona twice in a \
row. This is a tiebreaker between people who could plausibly speak next, not a \
reason to hand the floor to someone unrelated. Answering the trainer, and \
following up on the thread already running, both come first.

Set needs_hand_raise to true ONLY when this persona wants to interrupt with \
something off the current thread, for example a question about an earlier \
topic, or a tangent the trainer has not invited. When the trainer has just \
asked the class a question, or the persona is directly responding to what was \
just said, set it to false: in a real classroom people answer a direct \
question without putting a hand up first.

{floor_instruction}
"""

# Layer A refuses to open the gate while the floor is held, so this branch is
# only reached if that check is bypassed. Kept as a backstop rather than the
# primary mechanism.
_FLOOR_HELD = """\
IMPORTANT: the trainer has asked the class to hold questions until they finish \
explaining. Do not speak. Set action to stay_silent."""

_FLOOR_OPEN = """\
The floor is open: the trainer is taking questions."""

# Layer A already narrows eligibility to the addressed persona, so this tells
# the model what that turn is for rather than who may take it.
_REPLY_OWED = """\
IMPORTANT: the trainer has just spoken to {name} by name. This turn is {name} \
answering them, and nobody else. Reply to what was actually asked, in one or \
two sentences. If the question was about something {name} said earlier, answer \
that specific thing rather than changing the subject."""

_REPLY_OPEN = ""


def _format_persona_digest(personas: dict[str, PersonaState], elapsed_s: float) -> str:
    lines = []
    for p in personas.values():
        # "Never spoken" matters more than a huge number here: without this the
        # model has no signal about who has already had a turn and will keep
        # picking the same persona every time.
        if p.last_spoke_at < 0:
            recency = "has not spoken yet this session"
        else:
            recency = f"last spoke {elapsed_s - p.last_spoke_at:.0f}s ago"
        lines.append(
            f"- id={p.persona_id}, name={p.display_name or p.persona_id} "
            f"({p.persona_type}): {recency}, "
            f"engagement={p.engagement:.2f}, confusion={p.confusion:.2f}, "
            f"knowledge_gaps={p.knowledge_gaps}"
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
        audience=state.audience or DEFAULT_AUDIENCE,
        trainer_description=describe_trainer(state.trainer_name, state.trainer_address),
        floor_instruction=_FLOOR_HELD if state.floor_held else _FLOOR_OPEN,
        reply_instruction=(
            _REPLY_OWED.format(
                name=(
                    state.persona_states[state.awaiting_reply_from].display_name
                    or state.awaiting_reply_from
                )
            )
            if state.awaiting_reply_from in state.persona_states
            else _REPLY_OPEN
        ),
        current_objective=state.current_objective_id or "(none set)",
        slide_number=state.slide_number,
        elapsed_s=state.elapsed_s,
        objectives_covered=state.objectives_covered,
        transcript_recent="\n".join(
            f"{speaker}: {text}" for speaker, text in state.transcript_recent[-8:]
        )
        or "(nothing yet)",
        in_progress_partial=state.in_progress_partial or "(nothing yet)",
        persona_digest=_format_persona_digest(eligible_personas, state.elapsed_s),
        recent_events=state.recent_events,
        screen_status=(
            "the trainer is sharing their screen, an image of it is attached; "
            "a learner may reasonably ask about what is visible on it"
            if state.screen_frame_jpeg
            else "the trainer is not sharing their screen"
        ),
    )

    # The trainer's shared screen, if any. Measured at ~10KB for a downscaled
    # JPEG and no meaningful latency cost, so personas can react to what is
    # actually on screen (live demos, code, anything not in the Teaching
    # Graph). Diverges from architecture doc §4, which only sends video to
    # Gemini post-session.
    contents: list = [prompt]
    if state.screen_frame_jpeg:
        contents.append(
            types.Part.from_bytes(data=state.screen_frame_jpeg, mime_type="image/jpeg")
        )

    response = client.models.generate_content(
        model=settings.gemini_model_flash_lite,
        contents=contents,
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
