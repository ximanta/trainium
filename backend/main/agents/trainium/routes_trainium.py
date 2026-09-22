import uuid

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect

from main.agents.trainium.auth import User, get_current_admin, get_current_user
from main.agents.trainium.db_manager import sessions_collection
from main.agents.trainium.models import Session


def configure_routes_trainium(app: FastAPI) -> None:
    @app.get("/trainium/health")
    async def health():
        return {"status": "ok", "agent": "trainium"}

    @app.post("/trainium/sessions")
    async def create_session(user: User = Depends(get_current_user)):
        session = Session(id=str(uuid.uuid4()), org_id=user.org_id, trainer_id=user.id)
        await sessions_collection.insert_one(session.model_dump())
        return session

    @app.get("/trainium/admin/whoami")
    async def admin_whoami(user: User = Depends(get_current_admin)):
        return user

    @app.websocket("/trainium/ws/session")
    async def ws_session(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                await websocket.send_json({"type": "echo", "data": data})
        except WebSocketDisconnect:
            pass
