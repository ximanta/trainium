from datetime import datetime, timezone
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from main.agents.trainium.thinking import minimal_thinking
from main.config import settings
from main.agents.trainium.storage import download_file

BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]


class LearningObjective(BaseModel):
    id: str
    statement: str
    bloom_level: BloomLevel
    must_cover: list[str] = Field(default_factory=list)
    source_slides: list[int] = Field(default_factory=list)


class Concept(BaseModel):
    id: str
    name: str
    depends_on: list[str] = Field(default_factory=list)


class Misconception(BaseModel):
    id: str
    concept_id: str
    claim: str
    correction: str


class ExpectedQuestion(BaseModel):
    id: str
    concept_id: str
    persona_fit: list[str] = Field(default_factory=list)
    text: str
    difficulty: int = Field(ge=1, le=5)


class Module(BaseModel):
    # difficulty comes right after the title, not after four nested list
    # fields: an unconstrained trailing int made the model's constrained
    # decoding unstable on long generations (see project memory:
    # trainium-gemini-sdk-thinking-leak). A bounded range plus an earlier
    # position fixed it.
    id: str
    title: str
    difficulty: int = Field(ge=1, le=5)
    slide_range: list[int]
    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    misconceptions: list[Misconception] = Field(default_factory=list)
    expected_questions: list[ExpectedQuestion] = Field(default_factory=list)


class ModuleWindowResult(BaseModel):
    """Structured output shape for one windowed Gemini call."""

    modules: list[Module] = Field(default_factory=list)


class TeachingGraph(BaseModel):
    course_id: str
    version: int
    modules: list[Module] = Field(default_factory=list)
    generated_by_model: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


WINDOW_SIZE = 8

_PROMPT_TEMPLATE = """You are analyzing slides from a training course to build a \
Teaching Graph: the structure a Director agent will use to run a simulated \
classroom session.

For the slides in this window, identify one or more modules. Each module needs:
- learning_objectives: what a learner should be able to do after this module, \
with a Bloom's taxonomy level, terms that must be covered, and which slides \
support it
- concepts: the named ideas taught, with dependencies on earlier concepts if any
- misconceptions: a plausible wrong belief a learner might form, and the correction
- expected_questions: questions a learner persona might plausibly ask, tagged \
with which persona type would ask it (curious, beginner, skeptic, silent, \
confused, fast_learner, distracted, hacker, senior_practitioner) and a \
difficulty from 1 to 5
- difficulty: overall module difficulty from 1 to 5

Slide window (slides {start}-{end}):
{slide_text}

Give ids as short slugs unique within this window (e.g. "m1", "lo1", "c1").
"""


def _format_slide_text(slides: list[dict]) -> str:
    lines = []
    for slide in slides:
        lines.append(f"--- Slide {slide['slide_number']} ---")
        if slide.get("title"):
            lines.append(f"Title: {slide['title']}")
        if slide.get("body"):
            lines.append(f"Body: {slide['body']}")
        if slide.get("notes"):
            lines.append(f"Speaker notes: {slide['notes']}")
    return "\n".join(lines)


async def _generate_window(
    client: genai.Client, slides: list[dict], include_images: bool
) -> ModuleWindowResult:
    prompt = _PROMPT_TEMPLATE.format(
        start=slides[0]["slide_number"],
        end=slides[-1]["slide_number"],
        slide_text=_format_slide_text(slides),
    )

    parts: list = [prompt]
    if include_images:
        for slide in slides:
            if slide.get("image_file_id"):
                image_bytes = await download_file(slide["image_file_id"])
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))

    # thinking_budget=0: this model's reasoning trace leaks into constrained
    # JSON output fields (a repetition loop that burns the token budget and
    # never closes valid JSON) unless thinking is disabled. Found by testing
    # against a real deck; see project memory if this needs revisiting.
    response = client.models.generate_content(
        model=settings.gemini_model_flash,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ModuleWindowResult,
            temperature=0,
            max_output_tokens=8192,
            thinking_config=minimal_thinking(settings.gemini_model_flash),
        ),
    )

    if response.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS:
        raise RuntimeError(
            f"Gemini hit the token limit generating the Teaching Graph for slides "
            f"{slides[0]['slide_number']}-{slides[-1]['slide_number']}, likely a "
            f"generation loop. Retry, or narrow the window."
        )

    return ModuleWindowResult.model_validate_json(response.text)


async def generate_teaching_graph(
    course_id: str, slides: list[dict], version: int, include_images: bool = True
) -> TeachingGraph:
    """Windowed multimodal pass over slides, producing a Teaching Graph.
    One Gemini call per window of WINDOW_SIZE slides; results are
    concatenated, not merged, since modules are independent per window in v1.
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    all_modules: list[Module] = []
    for i in range(0, len(slides), WINDOW_SIZE):
        window = slides[i : i + WINDOW_SIZE]
        result = await _generate_window(client, window, include_images)
        all_modules.extend(result.modules)

    return TeachingGraph(
        course_id=course_id,
        version=version,
        modules=all_modules,
        generated_by_model=settings.gemini_model_flash,
    )
