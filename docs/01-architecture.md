# Trainium — Architecture (V1 / MVP)

Expands `AI_Trainer_Simulator_Full_Implementation_Spec.md` into buildable detail.
Stack: **Next.js 14 frontend, FastAPI + MongoDB backend**, shipped as an agent module
inside Content Crafter. **Read `00-integration-alignment.md` first** — it overrides the
original spec's PostgreSQL / LangSmith / Azure-Speech choices, and records the current
Gemini model IDs. V1 has **no authentication** — see its §6.

---

## 1. System shape

Three planes, deliberately separated because they have different latency budgets:

```
+- CONTROL PLANE --------------- (ms-seconds, request/response) --+
|  Next.js 14 --axios--> FastAPI --> MongoDB / Redis / S3         |
|  (no auth in V1 — single stub user)                              |
|  auth, course library, upload, session setup, report viewing    |
+-----------------------------------------------------------------+

+- REAL-TIME PLANE ------------- (<2.5s p95, streaming) ----------+
|  Browser --WS(PCM16)--> FastAPI /trainium/ws/session            |
|     ^                              |                            |
|     |                              +-> Gemini Live API  (STT)   |
|     |                              +-> Director gate + selector  |
|     |                              +-> gemini-3.8-flash (line)  |
|     +----audio + events-------------+-> Gemini TTS (streaming)  |
+-----------------------------------------------------------------+

+- ANALYSIS PLANE -------------- (minutes, offline, durable) -----+
|  worker --> LangGraph analysis_graph --> gemini-3.8-flash       |
|  ffmpeg composite -> transcript -> video -> pedagogy -> evidence|
|  -> scoring -> report.json -> MongoDB                            |
+-----------------------------------------------------------------+
```

**Rule:** nothing in the real-time plane may block on anything that can take >800ms.
All scoring is offline (spec §4, "Post Session Analysis").

---

## 2. Course Ingestion Pipeline

`POST /trainium/courses` → S3 upload → queued job `ingest_course`.

### 2.1 Extraction (deterministic, no LLM)

| Asset | Tool | Output |
|---|---|---|
| PPTX text + speaker notes | `python-pptx` | per-slide text runs, notes, title, layout name |
| PPTX slide images | LibreOffice headless → PDF → `pypdfium2` | one PNG per slide @ 1280px |
| Instructor Guide / Lab PDF | `pymupdf` + `pdfplumber` | text + page images |
| Assessments | `python-pptx` / `pypdf` | Q/A pairs |

> LibreOffice headless is the only reliable cross-platform PPTX renderer. It is a
> **container dependency, not a pip dependency** — see build plan §3. This is the
> single most annoying piece of infrastructure in the project; validate it early.

### 2.2 LLM processing (`gemini-3.8-flash`, multimodal)

One call per slide window (8 slides + notes + rendered images), then a reduce pass.
Structured output enforced via a Pydantic model passed as `response_schema`.

Produces the **Teaching Graph**:

```json
{
  "course_id": "uuid",
  "version": 3,
  "modules": [{
    "id": "m1",
    "title": "Agent Memory",
    "slide_range": [12, 24],
    "learning_objectives": [{
      "id": "lo1",
      "statement": "Explain the difference between semantic and episodic memory",
      "bloom_level": "understand",
      "must_cover": ["semantic memory", "episodic memory", "retrieval"],
      "source_slides": [13, 14]
    }],
    "concepts": [{"id": "c1", "name": "Semantic memory", "depends_on": []}],
    "misconceptions": [{
      "id": "mc1", "concept_id": "c1",
      "claim": "Semantic memory stores conversation history",
      "correction": "That is episodic memory; semantic stores generalized facts"
    }],
    "expected_questions": [{
      "id": "q1", "concept_id": "c1", "persona_fit": ["Curious", "Skeptic"],
      "text": "How do you stop semantic memory going stale?",
      "difficulty": 3
    }],
    "difficulty": 3
  }]
}
```

The Teaching Graph is the **single shared contract** between Director, Personas and
Evaluation. It is versioned and immutable once a session starts — otherwise a course
edit mid-flight silently invalidates a report.

### 2.3 Human-in-the-loop

Ingestion output lands as `status='draft'`. The Curriculum Owner reviews and edits
objectives in the Next.js UI, then publishes. Ungated LLM-generated objectives are
the largest source of garbage scores downstream, because every later stage trusts them.

---

## 3. Real-time plane — the turn loop

### 3.1 Wire protocol (`/trainium/ws/session`)

Follows the **CloseWire envelope** (`{"type": str, "data": dict}`) — see
`00-integration-alignment.md` §2. Two frame kinds on one socket:

- **Binary frames** = 20ms PCM16 mono 16kHz mic audio, client -> server.
- **Text frames** = JSON envelopes, both directions.

```jsonc
// server -> client
{"type":"partial_transcript","data":{"text":"so semantic memory is...","ts":124.3}}
{"type":"final_transcript","data":{"text":"...","ts":124.3,"dur":6.1}}
{"type":"persona_speaking","data":{"persona_id":"ravi","utterance_id":"u88",
  "text":"Does that go stale over time?","intent":"question","objective_id":"lo1"}}
{"type":"persona_audio","data":{"utterance_id":"u88","seq":0,"b64":"..."}}  // 24kHz PCM16
{"type":"persona_done","data":{"utterance_id":"u88"}}
{"type":"reaction","data":{"persona_id":"meera","kind":"confused"}}   // non-verbal, UI only
{"type":"director_note","data":{"text":"Good recovery"}}              // Practice mode only
{"type":"metrics_update","data":{"objectives_covered":3,"elapsed_s":740}}
{"type":"error","data":{"message":"..."}}

// client -> server
{"type":"slide_change","data":{"slide":14,"ts":130.0}}
{"type":"screen_share","data":{"on":true}}
{"type":"barge_in","data":{}}                 // trainer talked over a persona -> cancel TTS
{"type":"raise_hand_ack","data":{"persona_id":"ravi"}}
```

Session config is sent as the **first** text frame after `accept()`, matching
CloseWire's `negotiate_websocket` opener. Reuse its `_ws_send_json()` guard — it checks
`websocket.client_state` before every send, which is what stops the 20-minute session
from dying on a mid-flight disconnect.

### 3.2 Latency budget (target p95 < 2.5s to first learner audio)

| Stage | Budget | Provider |
|---|---|---|
| VAD endpointing (client-side Silero WASM) | 350 ms | browser, §7.1 |
| STT finalize (partials already streaming) | 100 ms | `gemini-3.8-live` |
| Director select **+ line**, first token | 500 ms | `gemini-3.8-flash`, §3.3 |
| TTS first audio chunk (streaming) | 350 ms | `gemini-3.1-flash-tts-preview` |
| Network + jitter buffer | 200 ms | — |
| **Total** | **~1.5 s** | |

The merged select-and-speak call (§3.3) removes one ~400ms LLM hop that the earlier
two-call design spent. Speculation (below) can hide most of the remaining 500ms.

**Speculative Director.** The Director runs on *partial* transcript roughly every 4s
of trainer speech, pre-computing "if they stop now, who speaks and about what." On
endpointing we only validate the cached decision. This removes 400–700ms from the
critical path, and is the reason the Director is *not* a per-turn LangGraph invocation.

### 3.3 Classroom Director

Two layers. **Do not make this one big LLM call.**

**Layer A — deterministic policy gate (pure Python, ~0ms).** Rejects most turns:

```python
class DirectorPolicy:
    min_gap_s: float = 45              # silence floor between interventions
    max_interventions_per_10min: int = 6
    per_persona_cooldown_s: float = 180
    speak_probability_by_type: dict    # Silent=0.05 ... Curious=0.35
    objective_gate: bool = True        # never ask about an un-taught objective
    multi_learner_p: float = 0.12      # spec §18 "Rare"
    group_discussion_p: float = 0.03   # spec §18 "Very Rare"
```

Hard triggers that bypass the probability roll: trainer asks an open question,
trainer pauses >8s, trainer states a known misconception, scenario script event due.

**Layer B — LLM selection *and* line generation (`gemini-3.8-flash`, temp 0.4).**
Only invoked when Layer A opens the gate. Input is a compact state digest, never the
raw transcript:

```
current_objective, last_90s_transcript_summary, slide_number, elapsed,
persona_states[5] (engagement / confusion / last_spoke_at / knowledge_gaps),
objectives_covered[], recent_events[5], scenario_directives[]
```

Output (structured): `{action: speak|react|silent, persona_id, intent, text, urgency}`.

**`text` is the final spoken line, not a hint.** The earlier draft split this into a
Director call (pick who) then a Persona call (say it in voice). That is one extra LLM
round trip — roughly 400ms — on the critical path. Since Layer A already provides the
hard guarantee that personas cannot self-select, Layer B can safely do both in one call:
the selected persona's profile, emotional state and session memory are injected into the
same prompt. Merge them.

Keep them separable behind a config flag so M3 can A/B realism if the combined prompt
produces flatter voices.

### 3.4 Persona voice and state

Persona rendering happens inside the Layer B call (§3.3). The prompt is composed from:
persona profile +
emotional state + knowledge state + session memory ("the trainer has already
explained X and Y") + speech-style constraints (max 2 sentences, spoken register,
no markdown, no lists, no meta-commentary).

Each persona gets a fixed TTS voice ID assigned at session start.
Knowledge and emotional state are updated by a **deterministic reducer** after each
trainer utterance (objective/keyword overlap, question-answered flags) — not by an
extra LLM call, which would cost latency for no realism gain.

### 3.5 Session state

Redis, key `trainium:session:{id}`: one hash + one append-only stream.
The hash holds the `SessionState` snapshot (hot path). The stream holds `events`
(append-only audit log, becomes `events.json`). Flushed to MongoDB/S3 on session
end and every 30s as a crash guard.

> Redis is **new infrastructure** for Content Crafter — the platform has no Redis today.
> If the platform team rejects it, fall back to an in-process dict plus a 10s write-behind
> to `trainium_sessions`. That caps you at one WS worker per session (sticky routing),
> which is acceptable for MVP but must be a conscious choice, not an accident.

---

## 4. Recording

The client records **two** `MediaRecorder` streams:

1. `camera.webm` — webcam video + trainer mic (VP8/Opus)
2. `screen.webm` — `getDisplayMedia` video only

Both chunked at 5s → `PUT /trainium/sessions/{id}/chunks/{track}/{seq}` → S3 multipart
upload. `t=0` alignment comes from a single `performance.timeOrigin` captured at
session start and sent with chunk 0 of each track — do not try to align from
wall-clock timestamps per chunk.

A post-session `ffmpeg` job produces `session.mp4`: screen as the main canvas,
webcam as a 240p picture-in-picture bottom-right, mixed audio (trainer mic +
persona TTS). This composite is what Gemini video analysis consumes — one file, so
facial/energy signals and slide context sit in the same frame.

> Persona TTS audio is also archived per-utterance, so the transcript has
> ground-truth speaker attribution with no diarization guessing.

---

## 5. Analysis plane — `analysis_graph` (LangGraph)

```
                      +--> transcript_review --+
 prepare_media --+----+--> video_review -------+--> evidence_extraction
 (ffmpeg,        |    +--> pedagogy_review ----+          |
  Files API      |                                        v
  upload)        +--> objective_coverage (deterministic) -+--> scoring
                                                              |
                                                              v
                                                       report_synthesis
```

- The three review branches run **in parallel** — they are independent, and this is
  where LangGraph earns its place (checkpointing + retry on a ~20-minute job).
- `evidence_extraction` runs **before** `scoring`. Scores are derived from evidence,
  never the reverse. This is the entire anti-hallucination mechanism (spec §4, §26).
- `objective_coverage` is deterministic: match transcript spans against `must_cover`
  terms from the Teaching Graph. Gives a hard, auditable number that does not drift.
- `scoring` runs at temperature 0 with anchored rubric descriptors per competency per
  level, and must cite ≥1 `evidence_id` per score or the node retries.

Speaker attribution is trivial here: trainer audio is a known track and persona
utterances are logged with exact timestamps. No diarization model required.

---

## 6. Trust & calibration (the biggest product risk)

LLM scores drift, and they will not be defensible for *certification* without
calibration. Plan for it from day one, not after launch:

1. Freeze a **golden set**: 20 recorded sessions, each scored independently by 2 humans.
2. Report Krippendorff alpha between model and human, per competency. Ship gate: ≥ 0.6.
3. Every report carries `rubric_version` + `model_version`. Re-scoring is replayable
   from the stored transcript and evidence without re-running the session.
4. In V1, Certification mode requires human sign-off. The AI produces evidence and a
   recommendation — not a pass/fail verdict.

---

## 7. Voice layer — Gemini only

No Azure, no Deepgram. Three Gemini surfaces, one API key (`GEMINI_API_KEY`).

### 7.1 Speech in — Live API as a controllable STT

`gemini-3.8-live` over a WebSocket, configured at setup with:

```python
config = {
    "response_modalities": ["TEXT"],
    "input_audio_transcription": {},          # the transcript we actually want
    "realtime_input_config": {
        "automatic_activity_detection": {"disabled": True},   # WE own turn-taking
    },
    "system_instruction": "You are a transcription sink. Never reply.",
}
```

With automatic VAD disabled the model **cannot** decide to speak — turns only begin and
end when we send `activityStart` / `activityEnd`. That is what makes the Live API
compatible with the spec's Director-controlled principle (`00-integration-alignment.md`
§5.1), and it is the only streaming speech-in path Gemini offers.

Input is raw 16-bit PCM, 16kHz, little-endian, mime `audio/pcm;rate=16000` — identical to
what the browser sends on the binary channel (§3.1), so no server-side resampling.

**Endpointing is ours to implement**, since we disabled Gemini's. Use client-side Silero
VAD in WASM (`@ricky0123/vad-web`): it runs in the browser, costs nothing, and gives a
350ms endpoint. The client emits `activity_end` on the JSON channel; the server relays it
to the Live session and simultaneously fires the Director. Doing VAD client-side also
means silence never crosses the network.

**Session duration.** Live sessions have a finite lifetime and need resumption handling
for a 30-minute class. Implement `session_resumption` from the start — discovering this
at minute 12 of a demo is a bad afternoon.

### 7.2 Speech out — streaming TTS

`gemini-3.1-flash-tts-preview`. It is the **only** Gemini TTS model that supports
streaming; the 2.5 TTS models return audio only after full synthesis, which would add
roughly a second to every learner turn. This model choice is load-bearing, not incidental.

Output is 24kHz PCM16 mono, chunked straight onto the `persona_audio` frames (§3.1).

30 prebuilt voices, so all nine persona types get a distinct one. Suggested seed mapping:

| Persona | Voice | Persona | Voice |
|---|---|---|---|
| Curious | `Puck` | Confused | `Despina` |
| Beginner | `Leda` | Fast Learner | `Fenrir` |
| Skeptic | `Charon` | Distracted | `Aoede` |
| Silent | `Vindemiatrix` | Hacker | `Orus` |
| Senior Practitioner | `Kore` | | |

Voice assignment is persisted per simulation (`trainium_simulations.personas[].voice_id`)
so a persona sounds the same in the recording as it did live.

> Multi-speaker TTS caps at **2 speakers per request**. That covers spec §18's "rare"
> two-learner exchange but not "very rare" group discussion. For group discussion,
> sequence separate single-speaker calls rather than waiting for a capability that
> is not there.

### 7.3 Post-session transcript — batch, not streaming

The real-time transcript is a **control signal for the Director**, not the record of
truth. The authoritative transcript is generated offline in the analysis plane by sending
the full session audio to `gemini-3.8-flash` (32 tokens/sec of audio; a 30-minute session
is ~58k audio tokens, and the limit is 9.5 hours).

This split is worth stating plainly because it relaxes a requirement: **real-time STT
accuracy can be mediocre without damaging the report.** Only the offline pass needs to be
good. Do not over-tune the live path.

### 7.4 Keep the seam

Two narrow Protocols, so the provider stays swappable and unit-testable without a network:

```python
class STTProvider(Protocol):
    def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript]: ...

class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str) -> AsyncIterator[bytes]: ...
```

Object storage is **AWS S3, ap-south-1**, via presigned URLs — not GridFS
(`00-integration-alignment.md` §4).

### 7.5 Risks specific to this design

- **`gemini-3.1-flash-tts-preview` is a preview model.** It can be renamed or retired with
  short notice, and it is the only streaming TTS available. Read the ID from env, and keep
  a non-streaming fallback path to `gemini-2.5-flash-preview-tts` behind the same
  `TTSProvider` interface.
- **Three Gemini surfaces share one quota.** The Live session, the per-turn Flash calls
  and the TTS calls all draw on the same API key. A rate limit during a live class is
  user-visible in a way a batch job never is. Measure headroom in M2 and get quota raised
  before pilot.
- **Everything is one vendor.** Simpler and cheaper, but there is no fallback if Gemini
  has an outage mid-session. Acceptable for V1; revisit before certification goes live.

---

## 8. Observability

- **Langfuse**, optional in V1: wrap LLM calls with `@observe()` and tag `session_id` and
  `persona_id`. Without `LANGFUSE_*` keys it no-ops, so local development needs no
  account. Matches the host platform (`main/agents/langfuse_utils.py`).
- Structured logs with the §3.2 stages as named timing fields — this is how you find which
  stage blew the latency budget. Log every turn's stage timings from day one; retrofitting
  latency instrumentation after a bad demo is guesswork.
- Per-session cost ledger: tokens x model, written to `trainium_simulations.cost_cents`.
  Track the Live session, Flash turns and TTS separately — they scale differently (Live
  with wall-clock, Flash with turn count, TTS with words spoken). A 30-minute session plus
  video analysis is the expensive unit; watch it from day one.
