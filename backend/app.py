import sys

# Windows defaults stdout/stderr to the system codepage (cp1252), which
# raises UnicodeEncodeError on non-ASCII output. Real training content
# (course text, transcripts, persona lines) is not ASCII-only, so any log
# line containing it would crash the process. Force UTF-8 unconditionally.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from main.agents.trainium.db_manager import ensure_indexes, seed_reference_data
from main.agents.trainium.routes_trainium import configure_routes_trainium
from main.agents.trainium.spike.voice_loop import configure_routes_voice_spike
from main.config import settings

app = FastAPI(title="Trainium")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

configure_routes_trainium(app)
configure_routes_voice_spike(app)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_reference_data()


@app.get("/health")
async def health():
    return {"status": "ok"}
