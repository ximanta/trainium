"""The real-time turn loop: /trainium/ws/session (architecture doc §3.1).

Speech in (gemini-3.5-transcribe-live, manual activity detection) -> Layer A
policy gate -> speculative Layer B (gemini-3.5-flash-lite) -> streaming TTS
(gemini-3.1-flash-tts-preview) -> persona_audio frames back to the client.

Supersedes the M2 spike (backend/main/agents/trainium/spike/), which proved
the pipeline and measured latency but used one hardcoded persona and no
Director. This is the real multi-persona, Director-driven loop.
"""

import asyncio
import base64
import json
import math
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from main.agents.trainium.db_manager import (
    courses_collection,
    persona_templates_collection,
    simulations_collection,
)
from main.agents.trainium.director.layer_b import DirectorDecision, decide_and_speak
from main.agents.trainium.director.persistence import append_event, append_transcript_segment
from main.agents.trainium.director.policy import DirectorPolicy
from main.agents.trainium.director.reducer import (
    apply_direct_address,
    apply_floor_control,
    apply_trainer_utterance,
)
from main.agents.trainium.director.speculative import SpeculativeDirector
from main.agents.trainium.director.state import PersonaState, create_session, remove_session
from main.agents.trainium.models import TRAINER_ADDRESSES
from main.agents.trainium.voices import accent_prompt_for_voice
from main.config import settings

# Remaining-time marks that get an explicit nudge, in seconds. Ten and five
# minutes are the points where a trainer can still change what they cover; one
# minute is a warning that it is about to close. Kept few on purpose, since the
# clock is always visible and a nudge every few minutes would be nagging.
NUDGE_MARKS_S = (600, 300, 60)

# How long a persona is protected from barge-in after its turn starts. TTS
# takes a second or two to produce its first audio, so without this the
# trainer's next breath cancels a line that has not been heard at all, leaving
# transcript text with no voice behind it. Long enough to cover generation,
# short enough that interrupting a rambling persona still feels immediate.
BARGE_IN_GRACE_S = 2.5

# How long the room tolerates silence before a learner speaks up. Covers the
# opening too: a trainer who joins and says nothing gets someone asking whether
# they are starting, the way a real class fills dead air. Long enough that a
# trainer gathering their thoughts is not interrupted.
SILENCE_PROMPT_S = 25.0


async def _ws_send_json(websocket: WebSocket, payload: dict) -> None:
    """Guards against sending on a closed socket. Architecture doc §3.1:
    reuse CloseWire's _ws_send_json() guard, which is what stops a session
    from dying on a mid-flight disconnect.
    """
    if websocket.client_state.name != "CONNECTED":
        return
    await websocket.send_json(payload)


async def _load_session_personas(
    persona_ids: list[str], overrides: dict | None = None
) -> dict[str, PersonaState]:
    """Persona templates with any per-session admin overrides applied."""
    overrides = overrides or {}
    cursor = persona_templates_collection.find({"id": {"$in": persona_ids}})
    templates = await cursor.to_list(length=None)

    states = {}
    for t in templates:
        override = overrides.get(t["id"]) or {}
        states[t["id"]] = PersonaState(
            persona_id=t["id"],
            persona_type=t["type"],
            voice_id=override.get("voice_id") or t["voice_id"],
            display_name=override.get("display_name") or t.get("name", t["id"]),
            profile=override.get("profile") or t.get("profile", ""),
            speak_probability=override.get("speak_probability"),
            # Only a real configured portrait. With none, the client shows a
            # camera-off initials tile, as Teams and Zoom do.
            avatar_url=t.get("avatar_url") or "",
        )
    return states


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
    # Recorded here rather than after the audio finishes. Barge-in cancels
    # this task mid-stream, and a CancelledError raised inside the TTS loop
    # unwound past the write at the end, so every interrupted persona vanished
    # from the transcript. Three of eight utterances were lost that way in a
    # real session, and the analysis then scored a conversation that had holes
    # in it.
    await append_transcript_segment(
        simulation_id,
        speaker=decision.persona_id,
        ts_start=ts_start,
        ts_end=ts_start,
        text=decision.text,
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
        # Accent is steered by prompt: Gemini has no locale parameter and no
        # voice is natively Indian. See voices.py.
        contents=accent_prompt_for_voice(decision.text, voice_id),
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
        state.persona_states = await _load_session_personas(
            simulation.get("persona_ids", []), simulation.get("persona_overrides", {})
        )
        state.audience = simulation.get("audience", "")
        # Whoever opened the link is the trainer, so their identity comes from
        # the green room and nowhere else. Deliberately not falling back to the
        # stored value: one link is shared across trainers, so what is on the
        # document is simply whoever ran it last, and inheriting that would
        # address this trainer by the previous one's name.
        state.trainer_name = str(config.get("trainer_name") or "").strip()[:80]
        address = config.get("trainer_address") or "name"
        state.trainer_address = address if address in TRAINER_ADDRESSES else "name"
        state.duration_s = float(simulation.get("duration_min", 30)) * 60.0
        state.current_objective_id = (
            simulation.get("target_objective_ids") or [None]
        )[0]

        # Slide images were rendered to GridFS during course ingestion (M1);
        # the client fetches each by id from /trainium/assets/{file_id}.
        slides: list[dict] = []
        if simulation.get("course_id"):
            course = await courses_collection.find_one(
                {"id": simulation["course_id"]}, {"_id": 0, "slides": 1}
            )
            if course:
                slides = [
                    {
                        "slide_number": s["slide_number"],
                        "title": s.get("title", ""),
                        "image_file_id": s.get("image_file_id"),
                    }
                    for s in course.get("slides", [])
                    if s.get("image_file_id")
                ]
        # Deck size drives half the phase signal, so the Director knows a
        # trainer on slide 22 of 25 is closing however much clock is left.
        state.slides_total = len(slides)

        policy_overrides = {
            key: simulation[key]
            for key in ("min_gap_s", "per_persona_cooldown_s")
            if simulation.get(key) is not None
        }
        policy = DirectorPolicy(**policy_overrides)
        state.max_turns = policy.turn_budget(state.duration_s)
        director = SpeculativeDirector(policy)
        client = genai.Client(api_key=settings.gemini_api_key)

        session_start = time.monotonic()
        # Outside the reconnect loop: a Live API drop must not replay nudges
        # the trainer has already seen.
        nudged: set[int] = set()

        live_config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
        )

        transcript_buffer: list[str] = []
        tts_task: asyncio.Task | None = None
        # When the current persona turn began. Barge-in is suppressed for a
        # moment after that: TTS takes a second or two to produce its first
        # audio, and without a grace period the trainer's next breath cancels
        # a persona before a single word of it has been heard. That produced
        # transcript lines with no voice, which reads as the app being broken.
        tts_started_at: float = 0.0
        turn_generation = 0
        turn_start_elapsed = 0.0
        # When the trainer last finished speaking. Starts at the session's own
        # start so the opening silence counts: a trainer who joins and says
        # nothing is exactly the case a real class fills with someone asking
        # whether we are starting yet.
        last_trainer_speech = 0.0
        # True between VAD speech start and end. The watchdog needs to know the
        # trainer is talking right now, which no other state carries: a turn
        # only lands in the transcript once it finishes.
        trainer_speaking = False

        async def run_director_turn(generation: int, ts_start: float) -> None:
            nonlocal tts_task, last_trainer_speech
            # Timed end to end. Each stage is reported separately because the
            # fix differs entirely: endpointing is a tuning constant, a Layer B
            # miss means speculation is not working, and TTS is the model's own
            # floor.
            t_turn = time.monotonic()
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
            last_trainer_speech = state.elapsed_s
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

            # "Let me explain first" and "any questions?" change whether anyone
            # may speak, so the client is told and can show the state on the
            # control bar.
            # Who, if anyone, the trainer just named. Runs before the gate so
            # eligibility can narrow to that persona.
            apply_direct_address(state, full_transcript, state.last_persona_speaker)

            floor_changed = apply_floor_control(state, full_transcript)
            if floor_changed is not None:
                await _ws_send_json(
                    websocket,
                    {"type": "floor_state", "data": {"held": floor_changed, "source": "speech"}},
                )

            t_endpoint = time.monotonic()
            # One learner at a time. A persona mid-sentence keeps the floor:
            # starting another cancels the first, which produced two stacked
            # questions with the trainer never getting to answer either. The
            # trainer interrupting is different and still cancels, because a
            # real room falls quiet when the trainer speaks.
            if tts_task is not None and not tts_task.done():
                return

            eligible = policy.eligible_personas(state)
            should_open = policy.should_open_gate(
                state,
                trainer_paused_s=state.elapsed_s - last_trainer_speech,
                trainer_asked_open_question="?" in full_transcript,
                trainer_stated_misconception=False,
                scenario_directive_due=False,
            )
            # Kept deliberately: personas staying silent is usually the Layer A
            # probability roll working as designed, not a failure. Without this
            # line a quiet classroom is indistinguishable from a broken
            # pipeline. should_open=False with a non-empty eligible list means
            # the roll simply did not fire.
            print(
                f"[ws_session] gate: should_open={should_open} eligible={eligible} "
                f"elapsed={state.elapsed_s:.0f}s",
                flush=True,
            )
            if not should_open or not eligible:
                return

            hits_before = director.hits
            t_layer_b = time.monotonic()
            decision = await director.resolve(state, eligible)
            layer_b_s = time.monotonic() - t_layer_b
            cached = director.hits > hits_before
            # One line per turn, so a real session shows where the wait went
            # instead of leaving it to be inferred from how slow it felt.
            print(
                f"[latency] endpoint={t_endpoint - t_turn:.2f}s "
                f"layer_b={layer_b_s:.2f}s ({'cached' if cached else 'MISS'}) "
                f"cache={director.hits}/{director.hits + director.misses} "
                f"speculations={director.speculations}",
                flush=True,
            )
            if decision is None or decision.action != "speak":
                return

            persona = state.persona_states[decision.persona_id]

            # Answering the trainer directly needs no hand raise, that is how
            # a real classroom works. Only an off-thread interruption waits to
            # be called on (doc's raise_hand_ack flow).
            if not decision.needs_hand_raise:
                await speak_now(decision, persona)
                return

            persona.hand_raised = True
            persona.pending_line = decision.text
            persona.pending_intent = decision.intent
            await _ws_send_json(
                websocket,
                {
                    "type": "hand_raised",
                    "data": {
                        "persona_id": decision.persona_id,
                        "intent": decision.intent,
                        "urgency": decision.urgency,
                    },
                },
            )
            await append_event(
                simulation_id,
                state.elapsed_s,
                kind="hand_raised",
                actor="director",
                persona_id=decision.persona_id,
                payload={"intent": decision.intent, "urgency": decision.urgency},
            )
            return

        async def speak_now(decision: DirectorDecision, persona) -> None:
            nonlocal tts_task, tts_started_at
            state.elapsed_s = time.monotonic() - session_start
            state.record_intervention(decision.persona_id)
            state.record_persona_utterance(persona.display_name or decision.persona_id, decision.text)
            # A persona already talking is cut off rather than overlapped: two
            # voices at once is worse than one interruption.
            if tts_task is not None and not tts_task.done():
                tts_task.cancel()
            tts_started_at = time.monotonic()
            tts_task = asyncio.create_task(
                _stream_persona_tts(
                    client, decision, persona.voice_id, websocket, simulation_id, state.elapsed_s
                )
            )

        async def speak_pending(persona_id: str) -> None:
            """Trainer called on a persona with a raised hand."""
            persona = state.persona_states.get(persona_id)
            if persona is None or not persona.hand_raised or not persona.pending_line:
                return

            decision = DirectorDecision(
                action="speak",
                persona_id=persona_id,
                intent=persona.pending_intent,
                text=persona.pending_line,
                urgency=1,
            )
            persona.hand_raised = False
            persona.pending_line = ""
            persona.pending_intent = ""
            await speak_now(decision, persona)

        client_gone = False
        roster_sent = False
        while not client_gone:
            try:
                async with client.aio.live.connect(
                    model=settings.gemini_model_live, config=live_config
                ) as live_session:
                    # Send the full roster up front so the participant sidebar
                    # can show everyone from the start, not just personas who
                    # happen to have spoken already. Only once per client
                    # connection: a transcription reconnect must not reset the
                    # trainer's slide position or mute states.
                    if not roster_sent:
                        await _ws_send_json(
                            websocket,
                            {
                                "type": "roster",
                                "data": {
                                    "personas": [
                                        {
                                            "persona_id": p.persona_id,
                                            "display_name": p.display_name,
                                            "persona_type": p.persona_type,
                                            "avatar_url": p.avatar_url,
                                            "muted": p.muted,
                                        }
                                        for p in state.persona_states.values()
                                    ],
                                    "slides": slides,
                                },
                            },
                        )
                        await _ws_send_json(websocket, {"type": "ready", "data": {}})
                        roster_sent = True
                        # Connecting to the Live API takes a few seconds, and
                        # charging those to the trainer would end the session
                        # early. Push the deadline out by the setup cost once,
                        # rather than rebasing session_start, which every other
                        # timing site measures against.
                        state.duration_s += time.monotonic() - session_start

                    async def run_silence_watch():
                        """Let a learner break a long silence.

                        Without this the room only ever reacts to speech, so a
                        trainer who joins and says nothing sits in a silent
                        classroom. A real one does not stay quiet: someone asks
                        whether we are starting, or whether they should wait for
                        others. The Layer A policy already treats a long pause
                        as a hard trigger; nothing was ever measuring the pause.
                        """
                        nonlocal last_trainer_speech
                        while True:
                            await asyncio.sleep(2.0)
                            state.elapsed_s = time.monotonic() - session_start
                            # Mid-sentence is not silence. last_trainer_speech
                            # only updates when a turn settles, so a trainer
                            # two minutes into an explanation still looked
                            # quiet and got interrupted by a learner asking
                            # whether they were starting yet.
                            if trainer_speaking:
                                continue
                            quiet_for = state.elapsed_s - last_trainer_speech
                            if quiet_for < SILENCE_PROMPT_S:
                                continue
                            # Someone already talking, or the floor deliberately
                            # held, is not an awkward silence.
                            if state.floor_held or (tts_task and not tts_task.done()):
                                continue
                            eligible = policy.eligible_personas(state)
                            if not eligible or state.out_of_budget():
                                continue

                            # Layer B directly, not the speculative cache: a
                            # decision computed while the trainer was speaking
                            # was made without the silence instruction, so it
                            # would answer a question nobody asked.
                            state.breaking_silence = True
                            try:
                                decision = await decide_and_speak(state, eligible)
                            finally:
                                state.breaking_silence = False
                            if decision is None or decision.action != "speak":
                                continue
                            persona = state.persona_states.get(decision.persona_id)
                            if persona is None:
                                continue
                            # Counts as the trainer having been addressed, so
                            # the room does not pile on with a second prompt
                            # two seconds later.
                            last_trainer_speech = state.elapsed_s
                            await speak_now(decision, persona)

                    async def run_clock():
                        """Push the remaining time and end the session at zero.

                        Server-authoritative on purpose: a client-side timer is
                        bypassed by a page reload, and the whole point is a cost
                        ceiling that holds regardless of what the browser does.
                        """
                        # Marks at or above the session length are retired
                        # silently. A 20-minute session must not open by
                        # announcing "10 minutes remaining", and a session
                        # shorter than a mark can never meaningfully cross it.
                        for mark in NUDGE_MARKS_S:
                            if state.duration_s <= mark:
                                nudged.add(mark)

                        # Tick on whole seconds of the session, counted from
                        # the shared origin rather than by adding 1.0 each
                        # time, so neither a late start nor a slow send lets
                        # the deadline drift.
                        next_tick = math.floor(time.monotonic() - session_start) + 1
                        while True:
                            delay = next_tick - (time.monotonic() - session_start)
                            if delay > 0:
                                await asyncio.sleep(delay)
                            next_tick += 1
                            state.elapsed_s = time.monotonic() - session_start
                            remaining = state.remaining_s

                            # Only the largest mark just crossed, so a slow
                            # tick cannot stack two nudges into one moment.
                            due = [m for m in NUDGE_MARKS_S if remaining <= m and m not in nudged]
                            if due:
                                nudged.update(due)
                                await _ws_send_json(
                                    websocket,
                                    {
                                        "type": "time_nudge",
                                        "data": {"remaining_s": int(max(due))},
                                    },
                                )

                            # One tick a second is cheap and keeps the client
                            # honest even if it was reloaded mid-session.
                            # Rounded up so the clock reads 1:00 rather than
                            # 0:59 for most of the final minute.
                            await _ws_send_json(
                                websocket,
                                {
                                    "type": "time",
                                    "data": {
                                        "remaining_s": math.ceil(remaining),
                                        "duration_s": int(state.duration_s),
                                    },
                                },
                            )

                            if remaining <= 0:
                                state.ended = True
                                if tts_task is not None and not tts_task.done():
                                    tts_task.cancel()
                                await _ws_send_json(
                                    websocket,
                                    {
                                        "type": "session_ended",
                                        "data": {
                                            "reason": "time",
                                            "turns": state.turns_taken,
                                        },
                                    },
                                )
                                return

                    async def relay_client_to_live():
                        nonlocal turn_generation, tts_task, turn_start_elapsed, trainer_speaking
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
                                    trainer_speaking = True
                                    director.on_speech_start()
                                    # The trainer started talking. If a persona is
                                    # mid-sentence, that is a real interruption, so
                                    # cancel its audio rather than letting the two
                                    # talk over each other. This is the automatic
                                    # barge-in the manual button was standing in for.
                                    #
                                    # Except in the first moments of a turn: the
                                    # persona has not been heard yet, so cancelling
                                    # is not an interruption, it is a line that
                                    # never plays.
                                    speaking_for = time.monotonic() - tts_started_at
                                    if (
                                        tts_task is not None
                                        and not tts_task.done()
                                        and speaking_for > BARGE_IN_GRACE_S
                                    ):
                                        tts_task.cancel()
                                        await _ws_send_json(
                                            websocket, {"type": "barge_in_ack", "data": {}}
                                        )
                                    await live_session.send_realtime_input(
                                        activity_start=types.ActivityStart()
                                    )
                                    transcript_buffer.clear()
                                elif control_type == "activity_end":
                                    trainer_speaking = False
                                    director.on_speech_end()
                                    await live_session.send_realtime_input(
                                        activity_end=types.ActivityEnd()
                                    )
                                    asyncio.create_task(
                                        run_director_turn(turn_generation, turn_start_elapsed)
                                    )
                                elif control_type == "slide_change":
                                    previous = state.slide_number
                                    slide = control.get("data", {}).get("slide")
                                    state.slide_number = slide
                                    if isinstance(slide, int):
                                        # Progress is the furthest point
                                        # reached, not the current slide:
                                        # going back to re-explain something
                                        # does not undo what was covered.
                                        state.furthest_slide = max(
                                            state.furthest_slide, slide
                                        )
                                        # Going back is a real classroom
                                        # signal, usually that something did
                                        # not land. The Director cannot infer
                                        # it from the slide number alone, so
                                        # it is recorded as an event.
                                        if isinstance(previous, int) and slide < previous:
                                            state.record_event(
                                                "slide_back",
                                                {"from": previous, "to": slide},
                                            )
                                elif control_type == "screen_share":
                                    if not control.get("data", {}).get("on"):
                                        # Sharing stopped, drop the stale frame so
                                        # personas do not keep referring to a
                                        # screen that is no longer up.
                                        state.screen_frame_jpeg = None
                                elif control_type == "screen_frame":
                                    b64 = control.get("data", {}).get("b64", "")
                                    state.screen_frame_jpeg = base64.b64decode(b64) if b64 else None
                                elif control_type == "barge_in":
                                    if tts_task is not None and not tts_task.done():
                                        tts_task.cancel()
                                elif control_type == "raise_hand_ack":
                                    # Trainer called on a persona whose hand is up.
                                    await speak_pending(control.get("data", {}).get("persona_id", ""))
                                elif control_type == "set_floor_held":
                                    # Manual override of the same state the
                                    # trainer's speech sets automatically.
                                    state.floor_held = bool(
                                        control.get("data", {}).get("held")
                                    )
                                    await _ws_send_json(
                                        websocket,
                                        {
                                            "type": "floor_state",
                                            "data": {
                                                "held": state.floor_held,
                                                "source": "manual",
                                            },
                                        },
                                    )
                                elif control_type == "set_muted":
                                    data = control.get("data", {})
                                    persona = state.persona_states.get(data.get("persona_id", ""))
                                    if persona is not None:
                                        persona.muted = bool(data.get("muted"))
                                        if persona.muted:
                                            # Drop any line it was waiting to say;
                                            # a muted persona should not keep a
                                            # raised hand the trainer cannot act on.
                                            persona.hand_raised = False
                                            persona.pending_line = ""
                                            persona.pending_intent = ""
                                        await _ws_send_json(
                                            websocket,
                                            {
                                                "type": "persona_muted",
                                                "data": {
                                                    "persona_id": persona.persona_id,
                                                    "muted": persona.muted,
                                                },
                                            },
                                        )

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

                    # If the Live transcription session dies (Google aborts these
                    # periodically, and they have a hard duration cap), only that
                    # task should fail. Reconnecting is handled by the outer loop;
                    # the trainer's own WebSocket must survive it, because losing
                    # the class mid-sentence is far worse than a brief gap in
                    # transcription.
                    relay_up = asyncio.create_task(relay_client_to_live())
                    relay_down = asyncio.create_task(relay_live_to_client())
                    clock = asyncio.create_task(run_clock())
                    silence = asyncio.create_task(run_silence_watch())
                    done, pending = await asyncio.wait(
                        [relay_up, relay_down, clock, silence],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()

                    if clock in done and not clock.cancelled():
                        # Time is up. The session is over for good, so this
                        # must not fall through to the reconnect branch.
                        clock.result()
                        client_gone = True
                    elif relay_up in done and not relay_up.cancelled():
                        # The client hung up, so the session is genuinely over.
                        relay_up.result()
                        client_gone = True
                    else:
                        # The Live session dropped. Tell the client we are
                        # reconnecting and let the outer loop do it.
                        if relay_down in done and relay_down.exception() is not None:
                            await _ws_send_json(
                                websocket,
                                {
                                    "type": "debug",
                                    "data": {"msg": "transcription reconnecting"},
                                },
                            )

            except WebSocketDisconnect:
                client_gone = True
            except Exception as exc:
                # Any other failure in the Live session, reconnect rather than
                # ending the class. Only give up if the client has gone.
                await _ws_send_json(
                    websocket,
                    {"type": "debug", "data": {"msg": f"reconnecting after: {type(exc).__name__}"}},
                )
                if websocket.client_state.name != "CONNECTED":
                    client_gone = True

        if tts_task is not None and not tts_task.done():
            tts_task.cancel()

        # Record how the session finished. Without this a simulation stays
        # "scheduled" forever and there is no way to tell a completed session
        # from one whose tab was closed after thirty seconds.
        await simulations_collection.update_one(
            {"id": simulation_id},
            {
                "$set": {
                    "status": "complete" if state.ended else "scheduled",
                    "ended_at": datetime.now(timezone.utc),
                    "actual_duration_s": round(state.elapsed_s),
                    "turns_taken": state.turns_taken,
                    # Recorded from the green room rather than the admin form,
                    # so the report names whoever actually taught.
                    "trainer_name": state.trainer_name,
                    "trainer_address": state.trainer_address,
                }
            },
        )
        remove_session(simulation_id)
