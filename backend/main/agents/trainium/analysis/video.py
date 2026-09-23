"""Delivery analysis from the trainer's camera track.

Gemini samples video at one frame per second by default, which is enough to
see posture, framing, gesture and where someone is looking, and not enough to
see micro-expressions. The prompt says so explicitly, because a model asked
about fleeting expressions at 1fps will describe them anyway.

The recording is uploaded through the File API rather than inline: a session
of any real length is far past the 100MB inline ceiling.
"""

import asyncio
import io

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from main.config import settings


class VideoMoment(BaseModel):
    competency_key: str
    # What is visible, in the model's own words: there is no transcript to
    # quote here, so this describes rather than cites.
    observation: str
    # Seconds from the start of the recording.
    ts_s: float
    positive: bool


class VideoResult(BaseModel):
    moments: list[VideoMoment] = Field(default_factory=list)


_PROMPT = """You are reviewing a recording of a trainer delivering a session, \
to assess how they came across on camera.

The delivery competencies:
{competency_list}

Watch the recording and note specific moments that evidence these. For each, \
give the competency key exactly as listed, what is visible, the timestamp in \
seconds from the start, and whether it shows the competency done well.

Rules:
- Describe only what is actually visible. Never infer mood or intent that the \
picture does not show.
- The video is sampled at roughly one frame per second, so fleeting facial \
movements are not reliably observable. Do not report micro-expressions or \
anything that would need continuous video to see.
- If the trainer is out of frame, the picture is too dark, or the camera was \
off for most of the recording, say so by returning no moments rather than \
guessing.
- Judge only delivery and presence. Ignore what is being said: the words are \
assessed separately from the transcript.
"""


def _format_competencies(competencies: list[dict]) -> str:
    lines = []
    for c in competencies:
        anchors = c.get("anchors", {})
        best = anchors.get(str(c.get("scale_max", 5)), "")
        lines.append(f"- {c['key']} ({c['label']}): strong looks like, {best}")
    return "\n".join(lines)


async def analyse_video(
    video_bytes: bytes, content_type: str, competencies: list[dict]
) -> list[VideoMoment]:
    """Watch a recording and return the delivery moments it shows.

    Returns an empty list on anything unusable rather than raising: a failed
    video pass should cost the delivery section of a report, not the whole
    report, which is still perfectly good from the transcript alone.
    """
    if not video_bytes:
        return []

    client = genai.Client(api_key=settings.gemini_api_key)
    uploaded = None

    try:
        uploaded = await client.aio.files.upload(
            file=io.BytesIO(video_bytes),
            config=types.UploadFileConfig(mime_type=content_type),
        )

        # Video files are processed asynchronously and cannot be referenced
        # until they leave the PROCESSING state.
        for _ in range(60):
            current = await client.aio.files.get(name=uploaded.name)
            if current.state.name != "PROCESSING":
                uploaded = current
                break
            await asyncio.sleep(2.0)

        if uploaded.state.name != "ACTIVE":
            return []

        response = await client.aio.models.generate_content(
            model=settings.gemini_model_analysis,
            contents=[
                _PROMPT.format(competency_list=_format_competencies(competencies)),
                uploaded,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoResult,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        result = response.parsed
        if result is None:
            return []

        valid_keys = {c["key"] for c in competencies}
        moments = [m for m in result.moments if m.competency_key in valid_keys]
    except Exception:
        return []
    finally:
        # The uploaded file counts against storage quota and is of no use once
        # analysed, so it does not outlive the call that made it.
        if uploaded is not None:
            try:
                await client.aio.files.delete(name=uploaded.name)
            except Exception:
                pass

    return moments
