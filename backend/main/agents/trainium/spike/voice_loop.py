"""M2 spike: measure end-of-speech to first-learner-audio latency.

Throwaway code, not part of the production Director/persona pipeline (that is
M3). One hardcoded persona, one Live API session, one TTS voice. Delete this
module once the latency numbers are captured and written down in the build
plan per its verification gate.
"""

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from google import genai
from google.genai import types

from main.config import settings

STATIC_DIR = Path(__file__).parent / "static"

HARDCODED_PERSONA_VOICE = "Puck"
HARDCODED_PERSONA_PROMPT = (
    "You are Priya, a curious learner in a training session. The trainer just "
    "said something. Respond with a short, natural, single-sentence reaction "
    "or question, as if you are listening live. Keep it under 20 words. Do "
    "not use markdown."
)


async def _ws_send_json(websocket: WebSocket, payload: dict) -> None:
    if websocket.client_state.name != "CONNECTED":
        return
    await websocket.send_json(payload)


async def _generate_persona_line(client: genai.Client, transcript: str) -> str:
    # gemini-3.8-flash measured 1.4-3.9s for this call, 3-6x the architecture
    # doc's 500ms budget, and the dominant cost in the pipeline (see project
    # memory: trainium-m2-latency-findings). gemini-3.5-flash-lite measured
    # roughly half that, consistently, with clean completions. It does not
    # accept thinking_config (400 error), so it is omitted here, not needed
    # for a call this simple anyway.
    response = client.models.generate_content(
        model=settings.gemini_model_flash_lite,
        contents=f"Trainer said: \"{transcript}\"",
        config=types.GenerateContentConfig(
            system_instruction=HARDCODED_PERSONA_PROMPT,
            temperature=0.4,
            max_output_tokens=150,
        ),
    )
    return response.text.strip()


async def _stream_tts(
    client: genai.Client, text: str, websocket: WebSocket, t_speech_end: float, stage_timings: dict
) -> None:
    first_chunk_sent = False
    t_tts_start = time.monotonic()
    stream = client.models.generate_content_stream(
        model=settings.gemini_model_tts,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=HARDCODED_PERSONA_VOICE
                    )
                )
            ),
        ),
    )
    for chunk in stream:
        if not chunk.candidates or not chunk.candidates[0].content.parts:
            continue
        for part in chunk.candidates[0].content.parts:
            if part.inline_data:
                if not first_chunk_sent:
                    first_chunk_sent = True
                    t_first_audio = time.monotonic()
                    stage_timings["tts_first_byte_ms"] = (t_first_audio - t_tts_start) * 1000
                    stage_timings["total_ms"] = (t_first_audio - t_speech_end) * 1000
                    await _ws_send_json(
                        websocket, {"type": "latency", "data": stage_timings}
                    )
                await websocket.send_bytes(part.inline_data.data)
    await _ws_send_json(websocket, {"type": "turn_complete", "data": {}})


def configure_routes_voice_spike(app: FastAPI) -> None:
    @app.get("/trainium/spike/voice-session/ui")
    async def voice_spike_ui():
        return FileResponse(STATIC_DIR / "voice_spike.html")

    @app.websocket("/trainium/spike/voice-session")
    async def voice_session(websocket: WebSocket):
        await websocket.accept()
        client = genai.Client(api_key=settings.gemini_api_key)

        # gemini-3.8-live rejects response_modalities=[TEXT] and, forced to
        # AUDIO, speaks back regardless of system instructions (see project
        # memory: trainium-live-model-correction). gemini-3.5-transcribe-live
        # is the correct model for a silent transcription sink and accepts
        # TEXT modality as originally specified in the architecture doc.
        live_config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
        )

        tts_task: asyncio.Task | None = None
        reply_task: asyncio.Task | None = None
        transcript_buffer: list[str] = []
        # Turn boundary is owned by us (manual activity detection). Rather
        # than block the receive loop waiting for a reply, or race reading
        # transcript_buffer against relay_live_to_client still appending to
        # it, activity_end bumps a generation counter and hands off to a
        # separate task that waits until no new transcript text has arrived
        # for a short quiet period before treating the turn as settled.
        turn_generation = 0

        async def handle_turn_settle(generation: int, t_speech_end: float):
            nonlocal tts_task
            last_len = 0
            settled = False
            for i in range(30):  # up to ~3s, in 100ms steps
                await asyncio.sleep(0.1)
                if generation != turn_generation:
                    await _ws_send_json(
                        websocket, {"type": "debug", "data": {"msg": "turn abandoned, newer turn started"}}
                    )
                    return
                current_len = len(transcript_buffer)
                # Require the buffer to have had content at least once, and
                # then stop growing, before treating it as settled. Buffer
                # staying at 0 just means transcription has not arrived yet,
                # not that the turn is done.
                if current_len > 0 and current_len == last_len:
                    settled = True
                    break
                last_len = current_len
            t_transcript_settled = time.monotonic()
            stage_timings = {"transcript_wait_ms": (t_transcript_settled - t_speech_end) * 1000}

            full_transcript = "".join(transcript_buffer).strip()
            transcript_buffer.clear()
            await _ws_send_json(
                websocket,
                {
                    "type": "debug",
                    "data": {"msg": f"turn settled={settled} after {i+1} checks, transcript={full_transcript!r}"},
                },
            )
            if not full_transcript:
                return
            try:
                line = await _generate_persona_line(client, full_transcript)
                t_flash_done = time.monotonic()
                stage_timings["flash_reply_ms"] = (t_flash_done - t_transcript_settled) * 1000
                await _ws_send_json(
                    websocket,
                    {"type": "persona_line", "data": {"transcript": full_transcript, "text": line}},
                )
                tts_task = asyncio.create_task(
                    _stream_tts(client, line, websocket, t_speech_end, stage_timings)
                )
            except Exception as exc:
                await _ws_send_json(websocket, {"type": "error", "data": {"message": str(exc)}})

        try:
            async with client.aio.live.connect(
                model=settings.gemini_model_live, config=live_config
            ) as live_session:
                await _ws_send_json(websocket, {"type": "ready", "data": {}})

                async def relay_client_to_live():
                    nonlocal tts_task, reply_task, turn_generation
                    while True:
                        message = await websocket.receive()
                        if message.get("type") == "websocket.disconnect":
                            break

                        if "bytes" in message and message["bytes"] is not None:
                            await live_session.send_realtime_input(
                                audio=types.Blob(
                                    data=message["bytes"], mime_type="audio/pcm;rate=16000"
                                )
                            )
                        elif "text" in message and message["text"] is not None:
                            import json

                            control = json.loads(message["text"])
                            if control["type"] == "activity_start":
                                turn_generation += 1
                                await live_session.send_realtime_input(activity_start=types.ActivityStart())
                                transcript_buffer.clear()
                            elif control["type"] == "activity_end":
                                t_speech_end = time.monotonic()
                                await live_session.send_realtime_input(activity_end=types.ActivityEnd())
                                await _ws_send_json(
                                    websocket, {"type": "speech_end_marker", "data": {"t": t_speech_end}}
                                )
                                reply_task = asyncio.create_task(
                                    handle_turn_settle(turn_generation, t_speech_end)
                                )
                            elif control["type"] == "barge_in":
                                if tts_task is not None and not tts_task.done():
                                    tts_task.cancel()
                                    await _ws_send_json(
                                        websocket, {"type": "barge_in_ack", "data": {}}
                                    )

                async def relay_live_to_client():
                    async for response in live_session.receive():
                        if response.server_content and response.server_content.input_transcription:
                            text = response.server_content.input_transcription.text
                            if text:
                                transcript_buffer.append(text)

                await asyncio.gather(relay_client_to_live(), relay_live_to_client())

        except WebSocketDisconnect:
            pass
        finally:
            if tts_task is not None and not tts_task.done():
                tts_task.cancel()
