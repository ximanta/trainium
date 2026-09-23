"""Recording upload and report retrieval."""

import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from main.agents.trainium.analysis.pipeline import schedule_analysis
from main.agents.trainium.auth import User, get_current_user
from main.agents.trainium.db_manager import (
    recordings_collection,
    reports_collection,
    simulations_collection,
)
from main.agents.trainium.storage import upload_file


def configure_routes_reports(app: FastAPI) -> None:
    @app.post("/trainium/sessions/{simulation_id}/recording")
    async def upload_recording(
        simulation_id: str,
        file: UploadFile = File(...),
        duration_s: float = Form(0.0),
        user: User = Depends(get_current_user),
    ):
        """Store the trainer's camera track once the session ends.

        The client posts this as the session closes, so analysis waits for it
        rather than starting without the video. The trainer, not the admin,
        uploads it, so this is open to any authenticated user.
        """
        simulation = await simulations_collection.find_one({"id": simulation_id})
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty recording")

        file_id = await upload_file(
            filename=f"{simulation_id}-camera.webm",
            content=content,
            content_type=file.content_type or "video/webm",
        )
        await recordings_collection.update_one(
            {"simulation_id": simulation_id, "track": "camera"},
            {
                "$set": {
                    "id": f"rec_{uuid.uuid4().hex[:12]}",
                    "simulation_id": simulation_id,
                    "track": "camera",
                    "file_id": file_id,
                    "content_type": file.content_type or "video/webm",
                    "size_bytes": len(content),
                    "duration_s": duration_s,
                }
            },
            upsert=True,
        )
        return {"stored": True, "size_bytes": len(content)}

    @app.post("/trainium/sessions/{simulation_id}/analyse")
    async def start_analysis(
        simulation_id: str, user: User = Depends(get_current_user)
    ):
        """Begin the report. Called by the client once the recording is in.

        Idempotent by report status: a reconnecting client that posts twice
        gets one report, not two analysis runs billed to the same session.
        """
        simulation = await simulations_collection.find_one({"id": simulation_id})
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")

        existing = await reports_collection.find_one(
            {"simulation_id": simulation_id, "status": {"$in": ["running", "complete"]}}
        )
        if existing:
            return {"started": False, "reason": "already analysing or done"}

        schedule_analysis(simulation_id)
        return {"started": True}

    @app.get("/trainium/sessions/{simulation_id}/report")
    async def get_report(simulation_id: str, user: User = Depends(get_current_user)):
        """The report for a session, or its progress.

        Readable by the trainer as well as the admin: the trainer is the
        person the coaching is for.
        """
        report = await reports_collection.find_one(
            {"simulation_id": simulation_id}, {"_id": 0}, sort=[("created_at", -1)]
        )
        if report is None:
            raise HTTPException(status_code=404, detail="No report for this session")
        return report
