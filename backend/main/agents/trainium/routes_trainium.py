from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect

from main.agents.trainium.auth import User, get_current_admin, get_current_user
from main.agents.trainium.db_manager import persona_templates_collection, scenarios_collection


def configure_routes_trainium(app: FastAPI) -> None:
    @app.get("/trainium/health")
    async def health():
        return {"status": "ok", "agent": "trainium"}

    @app.get("/trainium/personas")
    async def list_personas(user: User = Depends(get_current_user)):
        cursor = persona_templates_collection.find({}, {"_id": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/scenarios")
    async def list_scenarios(user: User = Depends(get_current_user)):
        cursor = scenarios_collection.find({}, {"_id": 0})
        return await cursor.to_list(length=None)

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
