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
**AI** Gemini only, one API key. `gemini-3.8-live` for speech in,
`gemini-3.8-flash` for director, personas, and analysis,
`gemini-3.1-flash-tts-preview` for speech out.

**No authentication in V1.** Identity goes through a single `get_current_user()` stub so
auth can be added later without a rewrite. See alignment doc §6. Keep deployments on
localhost or a private network until it lands.

**Database is MongoDB

## Local development

### Prerequisites

- Python 3.12
- Node 20.9 or newer
- MongoDB running locally on `27017`
- Redis running locally on `6379` (used for live session state, see architecture doc §3.5)

MongoDB and Redis can run as plain Docker containers, or reuse ones already running on
your machine. Neither needs an init script. If you use WSL for Docker, remember it does
not auto-start containers after a WSL restart, bring it up with `sudo service docker start`
if `docker ps` comes back empty.

```bash
docker run -d --name trainium-mongo -p 27017:27017 mongo:6.0
docker run -d --name trainium-redis -p 6379:6379 redis:7-alpine
```

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS or Linux
pip install -r requirements.txt
cp .env.example .env          # fill in GEMINI_API_KEY at minimum
uvicorn app:app --reload --port 8000
```

Verify: `curl http://localhost:8000/trainium/health` returns `{"status": "ok", "agent": "trainium"}`.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Verify: open `http://localhost:3000`. The frontend calls the backend at
`NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`), set in `.env.local`.

### Running both together

Start MongoDB and Redis first, then the backend, then the frontend, each in its own
terminal. There is no single command that starts all of it yet, add one if this becomes
frequent enough to be worth it.
