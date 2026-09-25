"""Admin views over runs: who taught what, and what came of it.

A simulation is a reusable setup; a run is one trainer's delivery of it. The
admin needs the second, because the same link is deliberately shared and
"the report for this session" is ambiguous the moment two people use it.
"""

import csv
import io

from fastapi import Depends, FastAPI, HTTPException, Response

from main.agents.trainium.auth import User, get_current_admin
from main.agents.trainium.db_manager import (
    recordings_collection,
    reports_collection,
    runs_collection,
    simulations_collection,
    transcripts_collection,
)


def _clock(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def configure_routes_runs(app: FastAPI) -> None:
    @app.get("/trainium/admin/runs")
    async def list_runs(
        simulation_id: str = "",
        trainer: str = "",
        user: User = Depends(get_current_admin),
    ):
        """Every delivery, newest first.

        `simulation_id` narrows to one configured training; `trainer` matches
        the name or email of whoever taught, case-insensitively, so an admin
        can answer "how did Anjali do" without knowing which session she ran.
        """
        query: dict = {"org_id": user.org_id}
        if simulation_id:
            query["simulation_id"] = simulation_id
        if trainer:
            query["$or"] = [
                {"trainer_name": {"$regex": trainer, "$options": "i"}},
                {"trainer_email": {"$regex": trainer, "$options": "i"}},
                {"assigned_trainer_name": {"$regex": trainer, "$options": "i"}},
                {"assigned_trainer_email": {"$regex": trainer, "$options": "i"}},
            ]

        runs = await runs_collection.find(query, {"_id": 0}).sort("started_at", -1).to_list(
            length=None
        )
        if not runs:
            return []

        # One lookup each rather than per row, so a long list stays cheap.
        sim_ids = {r["simulation_id"] for r in runs}
        sims = {
            s["id"]: s
            for s in await simulations_collection.find(
                {"id": {"$in": list(sim_ids)}}, {"_id": 0, "id": 1, "title": 1}
            ).to_list(length=None)
        }
        run_ids = [r["id"] for r in runs]
        reports = {
            rep["run_id"]: rep
            for rep in await reports_collection.find(
                {"run_id": {"$in": run_ids}}, {"_id": 0, "run_id": 1, "status": 1}
            ).to_list(length=None)
        }
        recorded = {
            rec["run_id"]
            for rec in await recordings_collection.find(
                {"run_id": {"$in": run_ids}}, {"_id": 0, "run_id": 1}
            ).to_list(length=None)
        }

        return [
            {
                **r,
                "session_title": sims.get(r["simulation_id"], {}).get("title", ""),
                "report_status": reports.get(r["id"], {}).get("status"),
                "has_recording": r["id"] in recorded,
            }
            for r in runs
        ]

    @app.get("/trainium/admin/runs/{run_id}/transcript")
    async def get_run_transcript(run_id: str, user: User = Depends(get_current_admin)):
        transcript = await transcripts_collection.find_one({"run_id": run_id}, {"_id": 0})
        if transcript is None:
            raise HTTPException(status_code=404, detail="No transcript for this run")
        return transcript

    @app.get("/trainium/admin/runs/{run_id}/transcript.csv")
    async def download_run_transcript(
        run_id: str, user: User = Depends(get_current_admin)
    ):
        """The transcript as a spreadsheet, timestamped.

        CSV rather than JSON: this is for a person reviewing a session, and it
        opens in Excel. Timestamps are mm:ss as well as raw seconds, because
        one is readable and the other sorts and filters.
        """
        run = await runs_collection.find_one({"id": run_id}, {"_id": 0})
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        transcript = await transcripts_collection.find_one({"run_id": run_id}, {"_id": 0})
        if transcript is None:
            raise HTTPException(status_code=404, detail="No transcript for this run")

        simulation = await simulations_collection.find_one(
            {"id": run["simulation_id"]}, {"_id": 0, "title": 1}
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Session", (simulation or {}).get("title", "")])
        writer.writerow(["Trainer", run.get("trainer_name", "")])
        writer.writerow(["Email", run.get("trainer_email", "")])
        writer.writerow(["Started", str(run.get("started_at", ""))])
        writer.writerow([])
        writer.writerow(["Time", "Seconds", "Speaker", "Slide", "Text"])
        for seg in transcript.get("segments", []):
            writer.writerow(
                [
                    _clock(seg.get("ts_start", 0)),
                    round(seg.get("ts_start", 0), 1),
                    seg.get("speaker", ""),
                    seg.get("slide", ""),
                    seg.get("text", ""),
                ]
            )

        name = (run.get("trainer_name") or "trainer").lower().replace(" ", "-")
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="transcript-{name}-{run_id}.csv"'
            },
        )
