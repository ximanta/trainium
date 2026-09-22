from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from main.agents.trainium.db_manager import ensure_indexes, seed_reference_data
from main.agents.trainium.routes_trainium import configure_routes_trainium
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


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_reference_data()


@app.get("/health")
async def health():
    return {"status": "ok"}
