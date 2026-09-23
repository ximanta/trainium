"""Render the voice preview samples to static files.

The preview line and the voice list are both fixed, so there is no reason to
call Gemini when an admin clicks play: the same twelve clips are produced every
time. Generating them ahead of time makes the button instant and takes the cost
off the request path.

Run from the backend directory after changing PREVIEW_LINE or VOICE_CATALOGUE:

    .venv/Scripts/python.exe scripts/pregenerate_voice_previews.py

Writes .wav files into the frontend's public/voice-previews/, which Next serves
directly.
"""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from main.agents.trainium.voices import (  # noqa: E402
    PREVIEW_LINE,
    VOICE_CATALOGUE,
    accent_prompt_for_voice,
)
from main.config import settings  # noqa: E402

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
    "public",
    "voice-previews",
)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    client = genai.Client(api_key=settings.gemini_api_key)

    failed = []
    for voice in VOICE_CATALOGUE:
        path = os.path.join(OUT_DIR, f"{voice.id}.wav")
        try:
            result = client.models.generate_content(
                model=settings.gemini_model_tts,
                contents=accent_prompt_for_voice(PREVIEW_LINE, voice.id),
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice.id
                            )
                        )
                    ),
                ),
            )
            parts = result.candidates[0].content.parts if result.candidates else []
            pcm = next((p.inline_data.data for p in parts if p.inline_data), None)
            if not pcm:
                raise RuntimeError("no audio returned")

            # Gemini returns headerless 24kHz mono 16-bit PCM.
            with wave.open(path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(pcm)
            print(f"  {voice.id:<14} {voice.label:<12} {len(pcm):>8} bytes")
        except Exception as exc:
            failed.append(voice.id)
            print(f"  {voice.id:<14} FAILED: {exc}")

    print(f"\n{len(VOICE_CATALOGUE) - len(failed)}/{len(VOICE_CATALOGUE)} written to {OUT_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
