"""Recording upload and report retrieval."""

import re
import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from main.agents.trainium.analysis.pipeline import schedule_analysis
from main.agents.trainium.auth import User, get_current_user
from main.agents.trainium.db_manager import (
    recordings_collection,
    reports_collection,
    runs_collection,
    simulations_collection,
)
from main.agents.trainium.storage import file_size, open_range, upload_file


def configure_routes_reports(app: FastAPI) -> None:
    @app.post("/trainium/sessions/{simulation_id}/recording")
    async def upload_recording(
        simulation_id: str,
        file: UploadFile = File(...),
        duration_s: float = Form(0.0),
        run_id: str = Form(""),
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
            # Keyed on the run so a second trainer does not overwrite the
            # first one's recording.
            {"run_id": run_id or simulation_id, "track": "camera"},
            {
                "$set": {
                    "id": f"rec_{uuid.uuid4().hex[:12]}",
                    "simulation_id": simulation_id,
                    "run_id": run_id or simulation_id,
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
        simulation_id: str, run_id: str = "", user: User = Depends(get_current_user)
    ):
        """Begin the report. Called by the client once the recording is in.

        Idempotent by report status: a reconnecting client that posts twice
        gets one report, not two analysis runs billed to the same session.
        """
        simulation = await simulations_collection.find_one({"id": simulation_id})
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # Scoped to the run. Keyed on the simulation this refused to analyse a
        # second trainer's session at all, because a report already existed:
        # they taught a full session and silently got nothing.
        key = run_id or simulation_id
        existing = await reports_collection.find_one(
            {"run_id": key, "status": {"$in": ["running", "complete"]}}
        )
        if existing:
            return {"started": False, "reason": "already analysing or done"}

        schedule_analysis(simulation_id, key)
        return {"started": True}

    @app.get("/trainium/sessions/{simulation_id}/recording")
    async def stream_recording(
        simulation_id: str, request: Request, download: bool = False
    ):
        """Stream the session recording, honouring Range requests.

        No auth dependency, deliberately: a <video> element cannot attach the
        role header the rest of the API uses, and Range requests come from the
        browser's media stack rather than from fetch. The unguessable
        simulation id is what protects it, the same reasoning as the join
        token. Revisit when Auth0 lands and signed URLs become available.
        """
        recording = await recordings_collection.find_one(
            {"simulation_id": simulation_id, "track": "camera"}, {"_id": 0}
        )
        if recording is None:
            raise HTTPException(status_code=404, detail="No recording for this session")

        file_id = recording["file_id"]
        content_type = recording.get("content_type", "video/webm")
        total = await file_size(file_id)

        range_header = request.headers.get("range")
        if not range_header:
            headers = {
                "Content-Length": str(total),
                "Accept-Ranges": "bytes",
                "Cache-Control": "private, max-age=3600",
            }
            if download:
                # Named after the session rather than the id, so a trainer who
                # saves several can tell them apart. Extension follows the
                # stored type: the file is whatever the browser recorded, and
                # renaming it .mp4 would only produce a file that will not play.
                simulation = await simulations_collection.find_one(
                    {"id": simulation_id}, {"_id": 0, "title": 1}
                )
                title = ((simulation or {}).get("title") or "session").strip()
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "session"
                ext = "mp4" if "mp4" in content_type else "webm"
                headers["Content-Disposition"] = (
                    f'attachment; filename="trainium-{slug}.{ext}"'
                )
            return StreamingResponse(
                open_range(file_id, 0, total),
                media_type=content_type,
                headers=headers,
            )

        # "bytes=START-END", either end optional.
        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if not match:
            raise HTTPException(status_code=400, detail="Malformed Range header")
        raw_start, raw_end = match.groups()
        start = int(raw_start) if raw_start else 0
        end = int(raw_end) if raw_end else total - 1
        end = min(end, total - 1)

        if start > end or start >= total:
            raise HTTPException(
                status_code=416,
                detail="Range not satisfiable",
                headers={"Content-Range": f"bytes */{total}"},
            )

        length = end - start + 1
        return StreamingResponse(
            open_range(file_id, start, length),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
                "Cache-Control": "private, max-age=3600",
            },
        )

    @app.get("/trainium/sessions/{simulation_id}/report")
    async def get_report(
        simulation_id: str, run_id: str = "", user: User = Depends(get_current_user)
    ):
        """The report for one delivery of a session.

        Readable by the trainer as well as the admin: the trainer is the
        person the coaching is for. Without a run_id this returns the most
        recent, which is what a trainer wants right after teaching; an admin
        reviewing a particular person passes the run explicitly.
        """
        query = {"run_id": run_id} if run_id else {"simulation_id": simulation_id}
        report = await reports_collection.find_one(
            query, {"_id": 0}, sort=[("created_at", -1)]
        )
        if report is None:
            raise HTTPException(status_code=404, detail="No report for this session")

        # The session details ride along, because the report page needs them to
        # head the document and the trainer cannot reach the admin route that
        # would otherwise supply them.
        simulation = await simulations_collection.find_one(
            {"id": simulation_id},
            {"_id": 0, "title": 1, "duration_min": 1, "persona_ids": 1},
        ) or {}
        # Trainer identity comes from the run, since the simulation is shared
        # and its copy is only ever whoever taught most recently.
        run = await runs_collection.find_one(
            {"id": report.get("run_id", "")},
            {"_id": 0, "trainer_name": 1, "trainer_email": 1, "started_at": 1},
        ) or {}
        report["session"] = {**simulation, **run}

        # Whether there is anything to play. Sent as a flag rather than a URL
        # so the client never renders a player over a 404.
        recording = await recordings_collection.find_one(
            {"simulation_id": simulation_id, "track": "camera"},
            {"_id": 0, "duration_s": 1, "size_bytes": 1},
        )
        report["recording"] = recording or None
        return report
