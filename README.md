# Trainium — AI Trainer Simulator

Trainers rehearse instructor-led sessions in a simulated classroom of AI learner
personas. The session is recorded, analysed with Gemini, and turned into an
evidence-backed coaching and certification report.

Ships as an agent module inside **Content Crafter** (`../content-crafter-new`).

## Docs — read in order

| Doc | What it covers |
|---|---|
| [00-integration-alignment.md](docs/00-integration-alignment.md) | Content Crafter's real stack, and the six spec decisions it overrides. **Start here.** |
| [01-architecture.md](docs/01-architecture.md) | Three-plane architecture, ingestion, Director, turn loop, recording, analysis graph |
| [02-data-and-api.md](docs/02-data-and-api.md) | MongoDB collections, JSON contracts, REST + WS API, auth |
| [03-build-plan.md](docs/03-build-plan.md) | Environment gaps, 6 milestones with verification gates, risks, open questions |

The original brief is [AI_Trainer_Simulator_Full_Implementation_Spec.md](AI_Trainer_Simulator_Full_Implementation_Spec.md).
Where it and the docs above disagree, the docs win — they reflect an audit of the
host platform.

## Stack

**Frontend** Next.js 14 (App Router) · React 18 · TypeScript · Tailwind + shadcn/ui · Zustand
**Backend** Python 3.12 · FastAPI · MongoDB (motor) · Redis · S3 · LangGraph · pip
**AI** Gemini only, one API key — `gemini-3.8-live` (speech in),
`gemini-3.8-flash` (director, personas, analysis),
`gemini-3.1-flash-tts-preview` (speech out)

**No authentication in V1.** Identity goes through a single `get_current_user()` stub so
auth can be added later without a rewrite — see alignment doc §6. Keep deployments on
localhost or a private network until it lands.
