# Trainium — Build Plan

Built standalone now, merged into Content Crafter later.
Read `00-integration-alignment.md` first.

---

## 1. Toolchain decisions (settled)

| Decision | Choice | Rationale |
|---|---|---|
| Python | **3.12, everywhere** | Already installed locally (3.12.10) — no install step. All required wheels (pymupdf, python-pptx, motor, langgraph, google-genai) are solid on 3.12. Newer than what the host ships (3.11), older than what it wrongly declares (3.13), and the likeliest target when the host does bump. |
| Dependencies | **pip + `requirements.txt`** | One file, one source of truth. Matches what the host image actually builds and avoids the pyproject/uv-lock drift documented in alignment §3.2. |
| Node | **20.11.0** (installed) | Next.js 14.2 needs 20.9+. |

Pin the interpreter and create the venv:

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

> `uv` 0.7.3 is installed and `uv pip install -r requirements.txt` works as a drop-in
> faster installer. It reads the same `requirements.txt` and produces the same venv — no
> lockfile, no `pyproject.toml`, nothing to drift. Use it or don't; it changes no contract.

`.python-version` → `3.12`. Dockerfile → `python:3.12-slim`.

---

## 2. Environment — verified state

Checked 2026-09-18.

| Tool | State | Action |
|---|---|---|
| Python | 3.12.10 | ready |
| Node | 20.11.0 / npm 10.2.4 | ready |
| git | 2.35.1 — **`D:\ai_projects\trainium` is not a repo** | `git init` |
| Bun | absent | needed only at merge time (host uses it); npm is fine standalone |
| Docker (WSL) | 29.2.1, healthy, 9 containers up | ready; **does not auto-start** — see §2.1 |
| MongoDB | **already running** — `mongo:6.0` (`scvhs-mongo`) on `0.0.0.0:27017` | reuse it; no container to add |
| Redis | **already running** — `redis:7-alpine` (`coo-redis`) on `0.0.0.0:6379`, healthy | reuse it |
| LibreOffice (WSL) | **7.3.7.2**, working | ready, but dated — see §2.2 |
| ffmpeg (WSL) | **absent** | install before M4 — §2.2 |
| `docker compose` | present | ready |

### 2.1 WSL filesystem incident — RESOLVED 2026-09-18

The distro's ext4 root had hit I/O errors and the kernel remounted it read-only
(`errors=remount-ro`). Symptoms were `touch` failing, `Input/output error` from binaries,
intermittent SIGBUS in Go binaries, and Docker unable to write to `/var/lib/docker`.
Read paths still worked, which is why `docker ps` and an interactive shell looked fine.

**Fix: `wsl --shutdown` from Windows, then reopen.** The ext4 journal replayed and root
came back `rw`. Verified: `/dev/sdb / ext4 rw,relatime,...`, writes succeed,
`soffice --version` → LibreOffice 7.3.7.2, `coo-redis` and `coo-postgres` returned to
*healthy* (their unhealthy status had been the read-only FS all along).

**Recurrence runbook**, since this can happen again:

```bash
grep " / " /proc/mounts        # look for "ro," -> filesystem is read-only
```

1. `wsl --shutdown` from Windows, reopen the distro, re-check. Usually sufficient.
2. This distro has `systemd=false` in `/etc/wsl.conf`, so **Docker does not auto-start**
   after a restart. Bring it up with the SysV script:

```bash
sudo service docker start
```

3. If root returns `ro` even after a clean restart, the filesystem needs a real `e2fsck`
   against the distro's `ext4.vhdx` with the VHD detached — do that deliberately, since a
   bad fsck on a mounted image loses the distro.

### 2.2 Remaining gap

`ffmpeg` is still absent and is required for M4 (session compositing):

```bash
sudo apt update && sudo apt install -y ffmpeg
```

> **Note for the M1 spike:** the installed LibreOffice is **7.3.7.2 (2022)**. PPTX
> rendering fidelity — particularly SmartArt and newer chart types — improved
> substantially in 7.6 and the 24.x line. If the M1 spike shows mangled decks, upgrading
> LibreOffice is the first thing to try, before abandoning the server-side render path.

---

## 3. Milestones

Each milestone has an explicit verification step. Nothing is "done" without it.

### M0 — Skeleton & plumbing (3–4 days)

Build:
- `backend/main/agents/trainium/` per alignment §7
- `auth.py` with the `get_current_user()` stub seam (alignment §6)
- `configure_routes_trainium(app)`; standalone `app.py` for now
- `db_manager.py` — motor client + `ensure_indexes()` for all nine collections
- `GET /trainium/health`, `/trainium/personas`, `/trainium/scenarios`
- Seed 9 persona templates (spec §12) with Gemini TTS voice IDs (architecture §7.2)
- `frontend/src/app/trainium/` + `components/agents/trainium/` shell

**Verify:** `/trainium/health` returns 200; `/trainium/personas` returns 9 personas each
with a distinct `voice_id`; the Next.js page lists them via `src/api/axios.ts`; every
route already carries the `Depends(get_current_user)` parameter.

---

### M1 — Course ingestion → Teaching Graph (1.5 weeks)

The riskiest non-obvious piece. No longer blocked — §2.1 is resolved.

Build:
- Presigned S3 upload + `POST /trainium/courses`
- `python-pptx` extraction of slide text and speaker notes
- Slide rendering: LibreOffice headless → PDF → PNG per slide
- `gemini-3.8-flash` windowed multimodal pass → Teaching Graph (architecture §2.2)
- Teaching-graph review/edit UI + `POST .../publish`

**Verify:** a real 60-slide deck yields, within 5 minutes, a Teaching Graph with ≥1
learning objective per module and ≥3 expected questions per objective, where every
`source_slides` reference resolves to a real slide. An edit increments the version.

**Spike first (half a day):** LibreOffice is installed and working, so this is a quick
answer — does `soffice --headless --convert-to pdf` render *your
actual decks* correctly, including fonts, embedded diagrams and SmartArt? If it mangles
them, the fallback is client-side rendering via the frontend's existing `pptxgenjs`/
`sharp` stack, which is a materially different design. Find out before building on it.

---

### M2 — Voice loop spike (1 week, mostly measurement)

**A spike, not a feature.** Prove the latency budget before building the Director on it.
This is the gate for the whole project.

Build a throwaway page: mic → client-side Silero VAD → WS → `gemini-3.8-live` (VAD
disabled, `input_audio_transcription` on) → `gemini-3.8-flash` (one hardcoded persona) →
`gemini-3.1-flash-tts-preview` streaming → browser playback.

**Verify:**
- p95 end-of-speech → first learner audio **< 2.5s**, over 20 real turns
- 5 Gemini voices are distinguishable in a blind check by 3 colleagues
- Barge-in cancels TTS within 200ms
- A Live session survives 30 minutes via `session_resumption`
- Gemini cost per 30-minute session measured and written down, split across Live / Flash /
  TTS
- API quota headroom checked against 5 concurrent sessions

**If p95 lands above ~3.5s, stop and re-plan.** The realism of the product depends on this
number. Fallbacks, in order of preference: drop the Live API for per-utterance batch STT
on `gemini-3.8-flash` (simpler, ~400ms slower); or the browser Web Speech API as CloseWire
uses (fast and free, but costs you recorded persona audio and voice identity — a
product-level trade-off, not an implementation detail).

---

### M3 — Classroom Director + personas (2 weeks)

Build:
- Layer A deterministic policy gate; Layer B merged select-and-speak call (architecture §3.3)
- Speculative pre-computation on partial transcripts
- 5 persona agents with knowledge/emotional state + deterministic state reducer
- Session state in Redis (or the documented single-worker fallback)
- Full WS envelope (architecture §3.1), lifting CloseWire's `_ws_send_json` guard
- Classroom UI: persona tiles, reactions, transcript rail, slide sync

**Verify:** a 10-minute session produces 4–7 interventions; no persona speaks twice inside
180s; no question references an objective the trainer has not yet covered; disconnect and
reconnect mid-session loses no transcript. Three trainers rate realism ≥3/5.

---

### M4 — Recording & transcript (1 week)

Build:
- Dual `MediaRecorder` (camera + screen), 5s chunks, resumable upload
- `t0` alignment via `performance.timeOrigin`
- Per-utterance persona audio archive
- ffmpeg composite → `session.mp4` (screen + webcam PiP + mixed audio)
- Offline authoritative transcript via `gemini-3.8-flash` over full session audio
  (architecture §7.3)

**Verify:** a 30-minute session yields a playable `session.mp4` with A/V drift < 200ms at
the end; speaker labels are 100% correct (they are logged, not inferred); killing the
browser tab at minute 20 still leaves 20 minutes recovered.

---

### M5 — Analysis pipeline & report (2 weeks)

Build:
- LangGraph `analysis_graph`, three parallel review branches (architecture §5)
- Deterministic `objective_coverage`
- `evidence_extraction` → `scoring` → `report_synthesis`
- The evidence-citation invariant enforced in code
- `prompts/rubrics/v1.yaml` — written with a training manager
- Report UI: summary, competency breakdown, timeline replay with video seek

**Verify:** a report completes in < 20 minutes; **every** score cites ≥1 resolvable
evidence id; clicking an evidence item seeks the video to the right moment; the same
session scored twice at temperature 0 lands within ±0.5.

---

### M6 — Calibration & hardening (1.5 weeks)

Build:
- Golden set of 20 sessions, each scored by 2 humans
- Agreement measurement per competency
- Manager review/override flow for certification mode
- Per-session cost ledger
- CORS tightening, presigned-URL TTLs

**Verify (ship gate):** model-vs-human agreement ≥ 0.6 per competency. Below that,
certification mode stays disabled and the product ships as Practice mode only. If the gate
is missed on reasoning-heavy competencies specifically, escalate those nodes to
`gemini-3.1-pro-preview` and re-measure before redesigning.

---

## 4. Timeline

~9 weeks of build for MVP scope (spec §34), assuming 2 backend + 1 frontend engineer.

M2 and M1's LibreOffice spike are the two places the estimate can break. Both are
front-loaded deliberately, so a bad result reshapes the plan in week 2 rather than week 7.

---

## 5. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| ~~WSL filesystem read-only~~ | *Resolved 2026-09-18* | Runbook kept at §2.1 in case it recurs |
| **Voice latency > 3.5s** | Kills realism; product is not credible | M2 spike gates everything; two documented fallbacks |
| **`gemini-3.1-flash-tts-preview` is preview** | Only streaming TTS; could be renamed or pulled | Model ID from env; non-streaming fallback behind `TTSProvider` |
| **Live API session limits** | Session dies mid-class | Implement `session_resumption` in M2, not later |
| **Single-vendor dependency** | No fallback if Gemini has an outage mid-session | Accepted for V1; revisit before certification goes live |
| **LibreOffice mangles real decks** | Ingestion quality collapses | Day-one spike; fallback to client-side render |
| **LLM scores do not match humans** | Certification is indefensible | Evidence-before-scoring, golden set, ≥0.6 gate, human sign-off in V1 |
| **Auth logic leaks outside the stub** | Cheap deferral becomes an expensive retrofit | Single `get_current_user()` seam; ownership filters written now (alignment §6) |
| **Redis is new infrastructure *in production*** | Platform team may refuse at merge | Already running locally, so V1 is unblocked; documented single-worker fallback for prod (architecture §3.5) |
| **Gemini video cost per session** | Unit economics fail at scale | Measure in M5; consider frame sampling over full video |
| **16MB Mongo doc limit on long transcripts** | Silent failure past ~60min | Explicit guard + split-collection path |

---

## 6. Open questions

Auth, Python version, packaging and the WSL environment are **settled** and no longer
listed. Each question below carries a recommendation so work is not blocked waiting for
a meeting — but each is a real decision someone should confirm.

### Q1. Gemini API quota — *blocks M2 sign-off*

**The question.** Every live session uses Gemini three ways at once: a Live connection
held open for the full 30 minutes, a Flash call each time a learner speaks, and a TTS call
for each of those lines. Google caps requests per minute and concurrent Live sessions.
What tier is our key on, and how many simultaneous classes can it carry?

This matters more than a typical quota question because the failure is *visible*: a
throttled batch job retries quietly, a throttled classroom goes silent mid-sentence.

| Option | Trade-off |
|---|---|
| A. Stay on the current key, discover limits by hitting them | No effort; you find the ceiling during a demo |
| B. Read the quota now, request an increase with measured numbers before pilot | One hour of work; quota requests backed by real data get approved |
| C. Move to Vertex AI (GCP project + service account) | Enterprise quotas and per-project billing, but Content Crafter uses plain API keys today — a new auth path |

**Recommendation: B now, plan C before pilot.** Check the current limits today, then let M2
measure one real session's consumption and multiply by target concurrency. Ask specifically
about **concurrent Live sessions** — that ceiling usually binds before tokens-per-minute
does, and it is the one that maps directly to "how many trainers can practise at once."

### Q2. Worker image — *shapes M1 and M4*

**The question.** Trainium needs two heavy tools nothing else in Content Crafter needs:
ffmpeg (stitch the video) and LibreOffice (render slides). Together roughly 1–1.5 GB of
image. Content Crafter builds one image for all ~45 agents. Do these go in the shared
image, or does Trainium get a second one?

| Option | Trade-off |
|---|---|
| A. One fat image | No CI changes; every agent's deploy gets slower, and a 20-minute video job shares a process pool with health checks |
| B. Two images, one codebase | Web container stays lean, video jobs scale independently; costs one extra CI pipeline |
| C. Managed services (MediaConvert, hosted slide conversion) | Least infrastructure; new vendors, per-job cost, less control |

**Recommendation: B.** The reason is isolation, not image size — a 20-minute Gemini video
analysis and a 100ms health check should not compete for the same workers. You need a
queue and a worker process for the analysis pipeline regardless, so giving it its own
Dockerfile is a small increment on work already planned.

For local development, keep running both in one container. The split only needs to exist
at deploy time, so this does not slow anyone down day to day.

### Q3. Redis in production — *affects M3*

**The question.** Live sessions hold fast-changing state: who spoke last, each persona's
mood, what has been taught. Reading and writing that to MongoDB every turn puts database
latency into the one loop where the budget is tightest. Redis is running locally, but
Content Crafter's production has none, so someone must add it — or we avoid needing it.

| Option | Trade-off |
|---|---|
| A. Add Redis to production (ElastiCache or a container) | Standard, survives multi-container scaling; a new production dependency to negotiate |
| B. In-process state + snapshot to Mongo every ~10s | No new infrastructure; needs sticky routing, and a crash costs ~10 seconds of state |
| C. MongoDB only, no cache | Simplest; puts DB round-trips in the critical path we are already fighting |

**Recommendation: B for V1, A before scaling out.** One session is one WebSocket held by
one process, so in-process state is a genuine fit rather than a compromise.

The argument that usually favours Redis — surviving a deploy — does not apply here: the
WebSocket itself dies with the container either way, so Redis would not save the session.
And because recordings are captured client-side and the transcript flushes to Mongo, a
reconnecting client can rebuild. Move to A when you run more than one backend container.

**Avoid C.** It trades a small amount of setup for latency in exactly the wrong place.

### Q4. Certification governance — *blocks M6*

**The question.** The product exists to certify trainers. The AI produces a score with
timestamped evidence — but does that score *certify* someone on its own? If a trainer
fails and disputes it, what happens? This is a policy decision, not a technical one, and
it determines how much review and audit UI gets built.

| Option | Trade-off |
|---|---|
| A. AI recommends, human approves | Defensible; costs manager time and a review queue |
| B. AI decides, human can appeal | Scales best; needs an appeals workflow and a track record we do not have |
| C. AI for practice only; certification stays manual | Lowest risk; gives up the business outcomes in spec §2 |

**Recommendation: A for V1.** It is the only option that is defensible when someone's
career progression is affected and the system has zero track record. It is also the
cheapest to build — `POST /trainium/reports/{id}/review` is already in the API contract.

Revisit B once M6 calibration plus a few hundred real sessions show sustained agreement.
C wastes the product.

**This one needs a business or HR owner, not engineering**, and should be raised early —
automated decisions affecting employment carry compliance obligations in some
jurisdictions.

### Q5. Avatars — confirm they stay Phase 2

**The question.** HeyGen streaming avatars are already a Content Crafter dependency with a
token route at `src/app/api/get-access-token/route.ts`, though no component uses them yet.
Since the plumbing is half there, should AI learners get realistic video faces in MVP?

| Option | Trade-off |
|---|---|
| A. Keep Phase 2 — persona tiles with name, image, speaking indicator | Ships MVP on time |
| B. Add HeyGen avatars to MVP | Far more immersive; new per-minute vendor cost, extra latency, nine concurrent streams |
| C. Cheap middle ground — static image with an animated speaking state | Most of the presence, near-zero cost |

**Recommendation: A, firmly.** Avatars add latency and per-minute cost on top of a turn
loop whose budget is not yet proven (M2), and nine simultaneous avatar streams is a very
different bandwidth and cost profile from the one-avatar demos HeyGen is sold on. The
product's value is the evidence-backed report, not the faces.

If M3 realism testing says trainers cannot suspend disbelief without faces, revisit — and
try C first. Let the realism data drive it, not the fact that the package is already in
`package.json`.
