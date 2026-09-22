"""The real-time turn loop: /trainium/ws/session (architecture doc §3.1).

Speech in (gemini-3.5-transcribe-live, manual activity detection) -> Layer A
policy gate -> speculative Layer B (gemini-3.5-flash-lite) -> streaming TTS
(gemini-3.1-flash-tts-preview) -> persona_audio frames back to the client.

Supersedes the M2 spike (backend/main/agents/trainium/spike/), which proved
the pipeline and measured latency but used one hardcoded persona and no
Director. This is the real multi-persona, Director-driven loop.
"""

import asyncio
import json
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from main.agents.trainium.db_manager import persona_templates_collection, simulations_collection
from main.agents.trainium.director.layer_b import DirectorDecision
from main.agents.trainium.director.persistence import append_event, append_transcript_segment
from main.agents.trainium.director.policy import DirectorPolicy
from main.agents.trainium.director.reducer import apply_trainer_utterance
from main.agents.trainium.director.speculative import SpeculativeDirector
from main.agents.trainium.director.state import PersonaState, create_session, remove_session
from main.config import settings


async def _ws_send_json(websocket: WebSocket, payload: dict) -> None:
    """Guards against sending on a closed socket. Architecture doc §3.1:
    reuse CloseWire's _ws_send_json() guard, which is what stops a session
    from dying on a mid-flight disconnect.
    """
    if websocket.client_state.name != "CONNECTED":
        return
    await websocket.send_json(payload)


async def _load_session_personas(persona_ids: list[str]) -> dict[str, PersonaState]:
    cursor = persona_templates_collection.find({"id": {"$in": persona_ids}})
    templates = await cursor.to_list(length=None)
    return {
        t["id"]: PersonaState(persona_id=t["id"], persona_type=t["type"], voice_id=t["voice_id"])
        for t in templates
    }


async def _stream_persona_tts(
    client: genai.Client,
    decision: DirectorDecision,
    voice_id: str,
    websocket: WebSocket,
    simulation_id: str,
    ts_start: float,
) -> None:
    utterance_id = str(uuid.uuid4())
    await _ws_send_json(
        websocket,
        {
            "type": "persona_speaking",
            "data": {
                "persona_id": decision.persona_id,
                "utterance_id": utterance_id,
                "text": decision.text,
                "intent": decision.intent,
            },
        },
    )
    await append_event(
        simulation_id,
        ts_start,
        kind="persona_speaking",
        actor="persona",
        persona_id=decision.persona_id,
        payload={"text": decision.text, "intent": decision.intent, "urgency": decision.urgency},
    )

    seq = 0
    stream = client.models.generate_content_stream(
        model=settings.gemini_model_tts,
        contents=decision.text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
                )
            ),
        ),
    )
    for chunk in stream:
        if not chunk.candidates or not chunk.candidates[0].content.parts:
            continue
        for part in chunk.candidates[0].content.parts:
            if part.inline_data:
                import base64

                await _ws_send_json(
                    websocket,
                    {
                        "type": "persona_audio",
                        "data": {
                            "utterance_id": utterance_id,
                            "seq": seq,
                            "b64": base64.b64encode(part.inline_data.data).decode("ascii"),
                        },
                    },
                )
                seq += 1

    await _ws_send_json(websocket, {"type": "persona_done", "data": {"utterance_id": utterance_id}})
    await append_transcript_segment(
        simulation_id,
        speaker=decision.persona_id,
        ts_start=ts_start,
        ts_end=ts_start,  # persona utterance duration is not tracked client-side; refine when recording lands (M4)
        text=decision.text,
    )


def configure_routes_ws_session(app: FastAPI) -> None:
    @app.websocket("/trainium/ws/session")
    async def ws_session(websocket: WebSocket):
        await websocket.accept()

        # Session config is the first text frame, per architecture doc §3.1.
        config_raw = await websocket.receive_text()
        config = json.loads(config_raw)
        simulation_id = config.get("simulation_id")

        simulation = await simulations_collection.find_one({"id": simulation_id})
        if simulation is None:
            await _ws_send_json(
                websocket, {"type": "error", "data": {"message": "simulation not found"}}
            )
            await websocket.close()
            return

        state = create_session(simulation_id)
        state.persona_states = await _load_session_personas(simulation.get("persona_ids", []))
        state.current_objective_id = (
            simulation.get("target_objective_ids") or [None]
        )[0]

        policy = DirectorPolicy()
        director = SpeculativeDirector(policy)
        client = genai.Client(api_key=settings.gemini_api_key)

        session_start = time.monotonic()

        live_config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
        )

        transcript_buffer: list[str] = []
        tts_task: asyncio.Task | None = None
        turn_generation = 0
        turn_start_elapsed = 0.0

        async def run_director_turn(generation: int, ts_start: float) -> None:
            nonlocal tts_task
            last_len = 0
            for _ in range(30):
                await asyncio.sleep(0.1)
                if generation != turn_generation:
                    return
                current_len = len(transcript_buffer)
                if current_len > 0 and current_len == last_len:
                    break
                last_len = current_len

            full_transcript = "".join(transcript_buffer).strip()
            transcript_buffer.clear()
            if not full_transcript:
                return

            state.elapsed_s = time.monotonic() - session_start
            await _ws_send_json(
                websocket,
                {
                    "type": "final_transcript",
                    "data": {"text": full_transcript, "ts": state.elapsed_s},
                },
            )
            await append_transcript_segment(
                simulation_id,
                speaker="trainer",
                ts_start=ts_start,
                ts_end=state.elapsed_s,
                text=full_transcript,
                slide=state.slide_number,
            )
            await append_event(
                simulation_id,
                state.elapsed_s,
                kind="final_transcript",
                actor="trainer",
                persona_id=None,
                payload={"text": full_transcript},
            )

            apply_trainer_utterance(state, full_transcript, must_cover_terms=[])

            eligible = policy.eligible_personas(state)
            should_open = policy.should_open_gate(
                state,
                trainer_paused_s=0,
                trainer_asked_open_question="?" in full_transcript,
                trainer_stated_misconception=False,
                scenario_directive_due=False,
            )
            if not should_open or not eligible:
                return

            decision = await director.resolve(state, eligible)
            if decision is None or decision.action != "speak":
                return

            state.record_intervention(decision.persona_id)
            voice_id = state.persona_states[decision.persona_id].voice_id
            tts_task = asyncio.create_task(
                _stream_persona_tts(
                    client, decision, voice_id, websocket, simulation_id, state.elapsed_s
                )
            )

        try:
            async with client.aio.live.connect(
                model=settings.gemini_model_live, config=live_config
            ) as live_session:
                await _ws_send_json(websocket, {"type": "ready", "data": {}})

                async def relay_client_to_live():
                    nonlocal turn_generation, tts_task, turn_start_elapsed
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
                            control = json.loads(message["text"])
                            control_type = control.get("type")

                            if control_type == "activity_start":
                                turn_generation += 1
                                turn_start_elapsed = time.monotonic() - session_start
                                director.on_speech_start()
                                await live_session.send_realtime_input(
                                    activity_start=types.ActivityStart()
                                )
                                transcript_buffer.clear()
                            elif control_type == "activity_end":
                                director.on_speech_end()
                                await live_session.send_realtime_input(
                                    activity_end=types.ActivityEnd()
                                )
                                asyncio.create_task(
                                    run_director_turn(turn_generation, turn_start_elapsed)
                                )
                            elif control_type == "slide_change":
                                state.slide_number = control.get("data", {}).get("slide")
                            elif control_type == "barge_in":
                                if tts_task is not None and not tts_task.done():
                                    tts_task.cancel()

                async def relay_live_to_client():
                    async for response in live_session.receive():
                        sc = response.server_content
                        if sc and sc.input_transcription and sc.input_transcription.text:
                            transcript_buffer.append(sc.input_transcription.text)
                            state.elapsed_s = time.monotonic() - session_start
                            # Layer B's prompt reads state.transcript_recent,
                            # which normally only gains the finished, settled
                            # utterance (via apply_trainer_utterance once a
                            # turn ends). Speculation needs to see what is
                            # being said right now, not stale prior-turn
                            # context, so the in-progress partial is exposed
                            # separately and appended to the digest at call
                            # time rather than mutating transcript_recent
                            # itself, which stays the authoritative finished
                            # history.
                            state.in_progress_partial = "".join(transcript_buffer).strip()
                            director.note_partial_transcript(
                                state, policy.eligible_personas(state)
                            )

                await asyncio.gather(relay_client_to_live(), relay_live_to_client())

        except WebSocketDisconnect:
            pass
        finally:
            if tts_task is not None and not tts_task.done():
                tts_task.cancel()
            remove_session(simulation_id)
