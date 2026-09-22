# Trainium — Integration Alignment with Content Crafter

Trainium is built **standalone now** and merges into **Content Crafter**
(`D:\ai_projects\content-crafter-new`) later. This document records what that host
platform actually is, which spec decisions it overrides, and — equally important —
where Trainium **deliberately diverges** from it for V1. Read this before
`01-architecture.md`.

Audited 2026-09-18 against `content-crafter-new` @ working tree.

---

## 1. What Content Crafter actually runs

### Frontend (`content-crafter-new/frontend`)
| Thing | Version / choice |
|---|---|
| Framework | **Next.js 14.2.18**, App Router, RSC enabled, `next dev --turbo` |
| React | 18.3.1 |
| TypeScript | **4.9.5** (old — see §3) |
| Package manager | **Bun** (`bun.lock`) |
| Styling | Tailwind 3.4.1 + **shadcn/ui** (`components.json`, baseColor `gray`, CSS vars) |
| Also present | MUI 5, Chakra 3, NextUI, Bootstrap 5, Ant Design icons |
| State | **Zustand 5** |
| HTTP | **axios** singleton at `src/api/axios.ts`, base `NEXT_PUBLIC_API_URL` |
| Auth | **Auth0** (`@auth0/auth0-react`) + `next-auth` v4; hooks in `src/hooks/useUnifiedAuth.ts`, `useAuth0Token.ts` |
| RBAC | `src/roles/roleBasedAccess.ts` |
| Charts | recharts 2.12 |
| E2E | Playwright 1.51 |
| Avatars | `@heygen/streaming-avatar` 2.0.16 — **installed, token route exists at `src/app/api/get-access-token/route.ts`, not yet used in any component** |

Per-agent layout convention:
```
src/app/<agent-slug>/…              # route
src/components/agents/<agent-slug>/ # the actual UI
```

### Backend (`content-crafter-new/backend`)
| Thing | Version / choice |
|---|---|
| Framework | **FastAPI** (pyproject `>=0.68`, requirements pins `==0.132.0`) |
| Python | pyproject + `.python-version` say **3.13**; **Dockerfile.dev builds on `python:3.11-slim`** (see §3) |
| Dep management | `pyproject.toml` + **`uv.lock` present**, but the image installs `requirements.txt` with **pip** (see §3) |
| Database | **MongoDB** via `motor` (async) / `pymongo` (sync). `asyncpg` is listed but unused. |
| Large binaries | **MongoDB GridFS** (`AsyncIOMotorGridFSBucket`) — used by `animation_agent` for video |
| Agents | LangGraph 1.0.1 + LangChain 0.3.x |
| LLM | Gemini via `langchain_google_genai` and `google-generativeai`; **`gemini-2.5-flash` is the default** (`GEMINI_MODEL_NAME`). Azure OpenAI (`gpt-4o-mini`) as secondary. |
| Speech | **`azure-cognitiveservices-speech` 1.42+** — `AzureTextToSpeech` at `main/agents/engage_coach/test_to_audio/tts.py` |
| Auth | **Auth0** (`AUTH0_DOMAIN`, `AUTH0_AUDIENCE`), `main/auth_middleware.py` |
| Observability | **Langfuse** (primary, `main/agents/langfuse_utils.py`, `@observe()` decorator) + LangSmith config present but `LANGSMITH_TRACING=false` |
| Docs/PPT | `python-pptx`, `pymupdf`, `pdfplumber`, `pytesseract`, `python-docx`, `openpyxl` |
| Streaming | `sse-starlette`, plus raw FastAPI `WebSocket` |

Registration convention — every agent exposes `configure_routes_<name>(app)` and is wired
in `backend/app.py`:
```python
from main.agents.<name>.routes_<name> import configure_routes_<name>
configure_routes_<name>(app)
```

Per-agent layout convention (from `engage_coach`, the cleanest example):
```
main/agents/<name>/
  routes_<name>.py        # configure_routes_<name>(app)
  <name>_service.py       # business logic
  <name>_db_manager.py    # motor client + collection access
  models.py               # pydantic
  prompts/ + prompt_manager.py
```

### Deployment
GitLab CI → Docker → **AWS ECR `079554103221.dkr.ecr.ap-south-1.amazonaws.com`**.
Separate pipelines and compose files for `development` / `production`, env injected from
`docker_env/<env>/`. **The cloud is AWS (ap-south-1).**

---

## 2. The two precedents you should copy

### `closewire` — Negotiation Arena (the closest analogue)
`backend/main/agents/closewire/routes_closewire.py` (3,407 lines) +
`frontend/src/components/agents/closewire-arena/CloseWireArena.tsx` (106 KB).

It already implements, end to end, the exact shape Trainium needs:

- `@router.websocket("/negotiate")` — live multi-turn role-play session
- A `{"type": "...", "data": {...}}` **JSON envelope** — this is the house WS convention
  (`message_complete`, `metrics_update`, `intent_update`, `copilot_update`, `error`)
- `_stream_agent_response()` — token-streamed AI turns over the socket
- `_classify_human_input()` — intent classification of the human's turn
- `_generate_coaching_tips()` — live coaching (Trainium's Practice mode)
- `_judge_outcome()` + `_run_post_session_jobs_safe()` — **post-session async evaluation**
- `POST /generate-report` returning a `StreamingResponse`
- Defensive `_ws_send_json()` that checks `websocket.client_state` before every send

**Trainium's Director/Persona/Report loop is CloseWire with a classroom skin.** Lift the
skeleton; do not reinvent the envelope, the disconnect handling, or the post-session job
pattern.

### `engage_coach` — scenario + evaluation
Gives you the reusable halves: `scenario_generator/`, `evaluation/` (with rubric prompts
and a Mongo `evaluation_db_manager`), `content_based_scenario/` (generate a scenario
*from uploaded content* — which is exactly Trainium's ingestion → Teaching Graph step),
and `test_to_audio/tts.py` (Azure TTS).

---

## 3. Inconsistencies found in the host repo

These are pre-existing. Flagging, not fixing — but Trainium has to pick a side.

1. **Python version is declared three ways.** `pyproject.toml` says `>=3.13`,
   `.python-version` says `3.13`, `Dockerfile.dev` uses `python:3.11-slim`.
   *What actually ships is 3.11.*
2. **uv is not used in the build.** `uv.lock` and `pyproject.toml` are committed, but
   `Dockerfile.dev` runs `pip install -r requirements.txt`. The two dependency lists have
   drifted (e.g. `fastapi>=0.68.0` vs `fastapi==0.132.0`).
3. **`asyncpg` is a dependency with no Postgres.** Everything persists to MongoDB.
4. **Duplicate entrypoints.** `backend/app.py` is the real one (wires ~45 route modules);
   `backend/main.py` and `backend/main/app.py` are stale partial copies. `main/main.py` is
   a 1-byte file.
5. **CORS is `allow_origins=[..., "*"]` with `allow_credentials=True`** in `app.py`.
   Invalid combination per the CORS spec, and permissive in production.
6. **Two observability stacks.** Langfuse is live; LangSmith is configured but disabled.
7. **Stray files in `backend/`**: `B{Condition}n`, `C[Step`, `D[Step`, plus committed
   `cert.pem` / `key.pem`.

---

## 4. Decisions

Two groups. **Group A** are places the host platform overrides the original spec — adopt
them now, they cost nothing. **Group B** are places Trainium deliberately diverges from
the host for V1, each with a stated reconciliation cost at merge time.

### Group A — adopt the host's choice (the spec was wrong)

| # | Spec said | **Adopted** | Why |
|---|---|---|---|
| A1 | PostgreSQL + SQLAlchemy | **MongoDB + motor** | Host is Mongo-only; a second datastore doubles ops burden for no gain |
| A2 | LangSmith | **Langfuse** (optional in V1 — no-ops without keys) | LangSmith is switched off platform-wide |
| A3 | S3 *or* Azure Blob, undecided | **AWS S3, ap-south-1** | ECR is there; same account, IAM and region as the cluster |
| A4 | React SPA | **Next.js 14.2 + React 18 + Tailwind + shadcn/ui** | Trainium becomes a route in the existing app |
| A5 | Gemini 2.5 Pro / Flash | **Current Gemini models** (§5) | The 2.5 family is two generations old as of Sept 2026 |

### Group B — deliberate divergence from the host (V1 only)

| # | Host does | **Trainium V1** | Reconciliation cost at merge |
|---|---|---|---|
| B1 | Azure Speech (STT + TTS) | **Gemini only** — Live API for speech-in, Gemini TTS for speech-out | **None.** Removes a vendor. The host keeps Azure for `engage_coach`; the two coexist. |
| B2 | Auth0 everywhere | **No auth.** One stub seam (§6) | **Low, if the seam is respected** — swap one `get_current_user()` dependency and add the frontend hook. High if auth checks get scattered. |
| B3 | pip + `requirements.txt`, plus an unused `uv.lock` | **pip + `requirements.txt` only** | **None.** Matches what the host image actually builds. Trainium simply skips the dead lockfile. |
| B4 | Python 3.11 in Docker (declares 3.13) | **Python 3.12, everywhere** | **Low.** Re-verify wheels at merge; Trainium's analysis worker is a separate image anyway. |

> B2 is the one to watch. Everything else is local and reversible; scattered auth logic
> is not. See §6.

---

## 5. Model selection (verified against Google's docs, Sept 2026)

The spec's `gemini-2.5-*` IDs are two generations behind. Current lineup:

| Role | Model | Status | Notes |
|---|---|---|---|
| Speech-in (live) | `gemini-3.8-live` | GA | Live API; **automatic VAD can be disabled** — see §5.1 |
| Director + Persona | `gemini-3.8-flash` | GA | Newest GA Flash; low-latency turn generation |
| Speech-out | `gemini-3.1-flash-tts-preview` | Preview | **The only TTS model that supports streaming.** 30 voices, 24kHz PCM16 mono |
| Post-session analysis | `gemini-3.8-flash` | GA | Handles video and long audio; 32 tokens/sec of audio, up to 9.5h per prompt |
| Analysis escalation | `gemini-3.1-pro-preview` | Preview | Only if M6 calibration misses the agreement gate |

Every model ID comes from env (`GEMINI_MODEL_*`), never hardcoded — the TTS model is
still preview and **will** be renamed.

### 5.1 The finding that unblocks the voice design

My first draft rejected the Live API because it owns turn-taking, which contradicts the
spec's core principle that personas never independently decide to speak (§4).

**That objection was wrong.** The Live API lets you set
`realtimeInputConfig.automaticActivityDetection.disabled = true` and drive turns manually
with `activityStart` / `activityEnd`. Combined with `input_audio_transcription` in the
setup config, it becomes a **streaming speech-to-text engine that never speaks unless
told to** — exactly the Director-controlled behaviour the spec demands.

This matters because **Gemini has no standalone streaming STT endpoint.** The Live API is
the only streaming speech-in path; everything else is batch. Without it the Director would
wait on whole-utterance batch transcription, costing ~400ms per turn and killing the
speculative pre-computation in `01-architecture.md` §3.2.

Audio formats line up with no conversion: Live API takes 16kHz PCM16 mono in, Gemini TTS
emits 24kHz PCM16 mono out.

---

## 6. The auth seam

V1 has **no authentication**. To keep B2's reconciliation cost low, all identity flows
through exactly one function:

```python
# main/agents/trainium/auth.py
DEV_USER = User(id="dev-trainer", org_id="dev-org", role="trainer", email="dev@local")

async def get_current_user() -> User:
    """V1: fixed dev user. When auth lands, this is the ONLY function that changes."""
    return DEV_USER
```

Five rules that keep the later swap to one line:

1. Every route takes `user: User = Depends(get_current_user)`. No exceptions, even though
   it always returns the same object today.
2. **Persist `org_id` and `trainer_id` on every document from day one**, populated from
   that stub. Mongo is schemaless, so this is free now and a painful backfill later.
3. Ownership filters (`{"trainer_id": user.id}`) go into queries **now**, even though they
   currently match everything. They become real the moment the stub is replaced.
4. No `ws_ticket` in V1 — but session IDs are `uuid4`, not sequential, so the WS endpoint
   is not trivially enumerable. The ticket field stays reserved in the API contract.
5. Frontend calls `src/api/axios.ts` with no `Authorization` header. When auth arrives, an
   interceptor adds it — no component changes.

> **Operational caution, stated once:** V1 endpoints are unauthenticated and the product
> records webcam, microphone and screen. Keep deployments on localhost or a private
> network until auth lands. That is a deployment constraint, not a code change.

---

## 7. Where Trainium's code goes

```
backend/main/agents/trainium/
  routes_trainium.py          # configure_routes_trainium(app) -> wire in backend/app.py
  auth.py                     # the stub seam (§6)
  ws_session.py               # @router.websocket("/trainium/ws/session")
  speech/                     # Live API client (STT), Gemini TTS client
  director/                   # policy gate + LLM selector
  personas/
  ingestion/                  # pptx -> teaching graph
  analysis/                   # LangGraph post-session pipeline
  db_manager.py               # motor, trainium_* collections
  models.py
  prompts/ + prompt_manager.py

frontend/src/app/trainium/...
frontend/src/components/agents/trainium/
  TrainiumClassroom.tsx       # the live session (client component)
  TrainiumReport.tsx
  api.ts                      # mirrors closewire-arena/api.ts
```

Trainium needs three things the shared monolith image does not have: **ffmpeg**,
**LibreOffice headless**, and long-running (10–20 min) analysis jobs. Adding them to the
shared image inflates it for ~45 agents and lets a video job starve request workers.

Recommendation: **one codebase, two images.** `routes_trainium.py` lives in the monolith
and serves the control plane and WebSocket. Ingestion and analysis workers run from a
separate Dockerfile (same repo, ffmpeg + LibreOffice layers) pulling jobs off a queue.
Same code, same Mongo — different container, independently scalable.

---

## 8. Conventions to follow (non-negotiable for a clean merge)

1. Route registration via `configure_routes_trainium(app)`, mounted under `/trainium`.
2. WS messages use the CloseWire envelope: `{"type": str, "data": dict}`.
3. All Mongo collections prefixed `trainium_`.
4. Model IDs from env, never hardcoded (§5).
5. Frontend: shadcn/ui + Tailwind only. Do **not** add MUI/Chakra/Bootstrap usage — the
   host already carries four UI kits, and that is the problem, not the precedent.
6. axios via `src/api/axios.ts`.
7. Dependencies in `requirements.txt` only (B3). One file, one source of truth.
8. Identity only ever through `get_current_user()` (§6).
