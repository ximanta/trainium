# Trainium — Data Model & API Contract (V1)

Expands spec §28 (Database Schema) and §29 (API Endpoints) into an implementable
contract, **aligned to Content Crafter's MongoDB + FastAPI stack**.
Read `00-integration-alignment.md` first — it supersedes the spec's PostgreSQL choice
and records that **V1 ships without authentication** (§5 below).

Persistence: **MongoDB** via `motor` (async). Validation: **Pydantic v2**.
All collections prefixed `trainium_`. All large binaries in **S3**, never in the document.

---

## 1. Collections

Conventions, applied everywhere:
- `_id`: `ObjectId` (the host's `CustomJSONEncoder` in `main/app.py` already serialises it)
- Every doc carries `created_at`, `updated_at` (UTC datetimes), and `org_id`
- Cross-references store `ObjectId`, not DBRefs
- Soft delete via `deleted_at` on `trainium_courses` and `trainium_simulations` only

> Mongo has no migrations. Every collection needs an explicit **index creation call on
> startup** (`db_manager.ensure_indexes()`), and every reader must tolerate missing
> fields from older documents. Put a `schema_version: int` on every document from day
> one — retrofitting it later is painful.

### `trainium_courses`
`org_id`, `title`, `description`, `status` (`uploading|ingesting|draft|published|failed`),
`owner_id`, `ingest_error`, `assets[]` (embedded: `kind`, `s3_key`, `filename`,
`size_bytes`, `sha256`, `page_count`), `schema_version`

`kind` ∈ `pptx | instructor_guide | lab_pdf | assessment | demo_guide | objectives`.
Assets are embedded rather than a separate collection — bounded (<20 per course) and
always read together.

**Indexes:** `{org_id: 1, status: 1}`, `{owner_id: 1}`

### `trainium_teaching_graphs`
`course_id`, `version`, `graph` (the full document from architecture §2.2),
`generated_by_model`, `approved_by`, `approved_at`

Never mutated. An edit creates `version + 1`.
**Indexes:** `{course_id: 1, version: -1}` unique

### `trainium_persona_templates`
`org_id` (null = system default), `name`, `type`, `profile`, `voice_id`, `avatar_url`

`type` ∈ `curious | beginner | skeptic | silent | confused | fast_learner | distracted |
hacker | senior_practitioner` (spec §12).
`voice_id` is a **Gemini TTS voice name** (e.g. `Puck`, `Kore`) — 30 available; see
`01-architecture.md` §7.2 for the persona→voice seed mapping.

### `trainium_scenarios`
`name`, `kind`, `script` (timed directives the Director must honour)

`kind` ∈ `difficult_learner | demo_failure | silent_classroom | time_pressure |
confused_group | dominant_learner | off_topic` (spec §16).

### `trainium_simulations`
`org_id`, `course_id`, `teaching_graph_version`, `trainer_id`, `mode`
(`practice|certification|scenario`), `scenario_id`, `status`
(`scheduled|live|recording_upload|analyzing|complete|failed`), `started_at`, `ended_at`,
`duration_s`, `target_objective_ids[]`, `cost_cents`, `failure_reason`,
`personas[]` (embedded snapshot: `template_id`, `display_name`, `voice_id`, `final_state`)

Personas are embedded as a **snapshot**, so later template edits never rewrite history.

**Indexes:** `{trainer_id: 1, started_at: -1}`, `{org_id: 1, status: 1}`, `{course_id: 1}`

### `trainium_recordings`
`simulation_id`, `track` (`camera|screen|composite|persona_audio`), `s3_key`, `mime`,
`duration_s`, `size_bytes`, `chunk_count`, `t0_offset_ms`, `status`

**Indexes:** `{simulation_id: 1, track: 1}`

### `trainium_transcripts`
`simulation_id`, `version`, `stt_provider`, `segments[]` (see §2), `word_count`

A 30-minute transcript is roughly 300–500 segments — comfortably inside Mongo's 16MB
document limit. **If a session exceeds ~60 minutes, split segments into their own
collection.** Note the limit in code with an explicit guard rather than discovering it in
production.

### `trainium_events`
`simulation_id`, `ts_s` (float, seconds from session start), `kind`,
`actor` (`trainer|persona|director|system`), `persona_id`, `payload`

Separate collection, not embedded — this is append-only, high-volume, and drives timeline
replay. **Indexes:** `{simulation_id: 1, ts_s: 1}`

### `trainium_evidence`
`simulation_id`, `competency`, `ts_start_s`, `ts_end_s`, `modality`
(`transcript|video|event`), `quote`, `observation`, `valence`
(`positive|negative|neutral`)

Separate collection so each row is independently addressable; reports cite `_id`.
**Indexes:** `{simulation_id: 1, competency: 1}`

### `trainium_reports`
`simulation_id` (unique), `rubric_version`, `model_version`, `overall_score`,
`competency_scores`, `payload` (full report, see §2), `human_reviewed_by`,
`human_override`, `generated_at`, `generation_ms`

**Indexes:** `{simulation_id: 1}` unique

### `trainium_analysis_jobs`
`simulation_id`, `graph_node`, `status`, `attempt`, `error`, `langfuse_trace_id`

Makes a stuck 20-minute pipeline debuggable without reading worker logs.
**Indexes:** `{simulation_id: 1}`, `{status: 1, updated_at: 1}`

---

## 2. Canonical JSON shapes

### Transcript segment
```json
{
  "id": "seg_0142",
  "speaker": "trainer",
  "ts_start": 124.30,
  "ts_end": 130.41,
  "text": "Semantic memory stores generalised facts, not conversations.",
  "confidence": 0.94,
  "objective_id": "lo1",
  "slide": 14
}
```
`speaker` is `"trainer"` or a `persona_id`. Attribution is exact, not inferred — the
trainer track and each persona utterance are logged separately (architecture §4).

### Evidence (spec §26, expanded so it is actually citable)
```json
{
  "_id": "ev_31",
  "competency": "question_handling",
  "ts_start": 765.0,
  "ts_end": 792.5,
  "modality": "transcript",
  "quote": "Think of it like the difference between remembering a fact and remembering a conversation.",
  "observation": "Used a concrete analogy to resolve Ravi's confusion between memory types.",
  "valence": "positive"
}
```

### Report payload (spec §27)
```json
{
  "executive_summary": "...",
  "overall_score": 3.7,
  "competencies": [{
    "key": "concept_explanation",
    "score": 4,
    "rubric_anchor": "Explanations are accurate and use at least one concrete analogy...",
    "evidence_ids": ["ev_31", "ev_44"],
    "rationale": "..."
  }],
  "objective_coverage": [{"objective_id": "lo1", "covered": true, "depth": "full", "ts": 120.0}],
  "strengths": [{"text": "...", "evidence_ids": ["ev_31"]}],
  "improvement_areas": [{"text": "...", "evidence_ids": ["ev_58"], "severity": "medium"}],
  "timeline": [{"ts": 765.0, "kind": "question_handled", "label": "Ravi — memory types"}],
  "coaching_plan": [{"action": "...", "why": "...", "practice_scenario": "confused_group"}]
}
```

**Invariant enforced in code, not in the prompt:** every `competencies[].score` and every
`strengths` / `improvement_areas` item must carry at least one `evidence_id` resolving to
a real `trainium_evidence` document. A report failing this is rejected and the `scoring`
node retries. Spec §4 says "evidence based" — this check is what makes that true rather
than aspirational.

---

## 3. Competency keys (spec §24)

`concept_explanation`, `learner_engagement`, `question_handling`, `demo_delivery`,
`lab_facilitation`, `classroom_management`, `time_management`

Scores 1–5 (spec §25). Each `(competency, level)` pair needs a written anchor descriptor
in `prompts/rubrics/v1.yaml` — 35 short paragraphs.

This file is the most important prompt asset in the system. **Write it with a real
training manager, not with an LLM.** `engage_coach/evaluation/prompts/` has the house
format to copy.

---

## 4. REST API

Mounted under `/trainium` on the shared FastAPI app, registered via
`configure_routes_trainium(app)` in `backend/app.py`.
Auth: **none in V1** — every route takes a stub user dependency (§5).

### Courses
| Method | Path | Notes |
|---|---|---|
| `POST` | `/trainium/courses` | create shell → returns `course_id` + presigned S3 upload URLs |
| `POST` | `/trainium/courses/{id}/assets` | register uploaded asset; triggers ingest once a PPTX is present |
| `GET` | `/trainium/courses` | list; filter by `status`, `owner_id` |
| `GET` | `/trainium/courses/{id}` | includes latest teaching-graph version + ingest status |
| `GET` | `/trainium/courses/{id}/teaching-graph` | `?version=` defaults to latest |
| `PATCH` | `/trainium/courses/{id}/teaching-graph` | curriculum owner edit → creates version+1 |
| `POST` | `/trainium/courses/{id}/publish` | requires an approved teaching graph |

### Simulations
| Method | Path | Notes |
|---|---|---|
| `POST` | `/trainium/simulations` | body: `course_id`, `mode`, `persona_ids[]`, `scenario_id?`, `target_objective_ids[]`, `duration_min`. Returns `session_id` (uuid4); `ws_ticket` reserved, unused in V1 |
| `WS` | `/trainium/ws/session` | the real-time loop (architecture §3.1); config sent as first text frame |
| `POST` | `/trainium/simulations/{id}/end` | finalize, flush state, enqueue analysis |
| `PUT` | `/trainium/simulations/{id}/chunks/{track}/{seq}` | recording chunk upload |
| `GET` | `/trainium/simulations` | trainer sees own; manager sees org |
| `GET` | `/trainium/simulations/{id}` | status + analysis pipeline progress |

### Reports
| Method | Path | Notes |
|---|---|---|
| `POST` | `/trainium/reports/generate` | `{simulation_id, force?}` — idempotent; returns existing unless `force` |
| `GET` | `/trainium/reports/{id}` | full payload, evidence hydrated |
| `GET` | `/trainium/reports/{id}/media` | presigned S3 URLs for `session.mp4` + transcript, TTL 15 min |
| `POST` | `/trainium/reports/{id}/review` | manager sign-off / override (certification mode) |
| `GET` | `/trainium/reports/{id}/export` | PDF |

### Reference data
`GET /trainium/personas`, `GET /trainium/scenarios`, `GET /trainium/rubric`

> The spec's flat `POST /simulation/start|end` is replaced by resource-shaped routes.
> Same operations; the `/trainium` prefix is required to avoid collisions with ~45 other
> agents already mounted on the same app.

---

## 5. Identity model — V1 has no auth

Authentication is deliberately deferred (`00-integration-alignment.md` §6). What matters
is that deferring it does not cost a rewrite later.

**One seam.** Every route depends on `get_current_user()`, which today returns a fixed
`DEV_USER`. That is the only function that changes when auth lands.

```python
@router.post("/trainium/simulations")
async def create_simulation(
    body: CreateSimulation,
    user: User = Depends(get_current_user),   # always DEV_USER in V1
): ...
```

**Write the multi-tenant fields now, even though they are constant.** They are free in a
schemaless store today and a painful backfill once there is real data:

- Every document carries `org_id` and, where relevant, `trainer_id`, populated from the
  stub user.
- Every read query carries its ownership filter — `{"trainer_id": user.id}` — even though
  it currently matches everything. These become load-bearing the moment the stub is
  replaced. Adding them later means auditing every query under time pressure.
- Role values (`trainer`, `training_manager`, `curriculum_owner`, `coach`) are stored and
  returned in API responses. The frontend can build the right UI per role immediately;
  enforcement arrives with auth.

**WebSocket.** No `ws_ticket` in V1. `POST /trainium/simulations` returns a `session_id`
that is a `uuid4`, so the endpoint is not enumerable, and the field stays reserved in the
contract so adding the ticket is additive rather than breaking.

**Frontend.** Calls go through `src/api/axios.ts` with no `Authorization` header. When
auth lands, one axios interceptor adds it — no component touches auth directly.

> **Deployment constraint:** these endpoints are unauthenticated and the product records
> webcam, microphone and screen. Keep V1 on localhost or a private network. Also fix the
> `allow_origins=[..., "*"]` + `allow_credentials=True` combination inherited from
> `backend/app.py` before anything is exposed — it is invalid per the CORS spec and
> signals the origin list is not actually enforced.

S3 recording URLs are presigned and short-lived (spec §31) regardless of auth state —
that is what keeps the media itself private even while the API is open.

---

## 6. What lives where

| Data | Store | Why |
|---|---|---|
| Live session state, director cache | Redis (**new dep**, see architecture §3.5) | hot path, TTL, ephemeral |
| Event stream during session | Redis stream → flushed to `trainium_events` | append-only |
| Metadata, transcripts, evidence, reports | MongoDB | queryable, durable, host standard |
| Media, slide PNGs, raw assets | **S3 (ap-south-1)** | large, immutable, presigned access |
| LLM traces | Langfuse | debugging, not a system of record |
