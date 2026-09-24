"""Human review and model-vs-human agreement.

The product risk this addresses is stated plainly in the architecture doc: an
LLM score nobody has checked is indefensible for certification. These routes
let humans score the same sessions the model scored, and measure whether the
two agree well enough to trust.
"""

import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException

from main.agents.trainium.analysis.agreement import measure_agreement
from main.agents.trainium.auth import User, get_current_admin
from main.agents.trainium.db_manager import (
    reports_collection,
    reviews_collection,
    rubrics_collection,
    simulations_collection,
)
from main.config import settings

# The ship gate from the architecture doc §6. Certification mode stays off
# until every competency clears it.
AGREEMENT_GATE = 0.6


def configure_routes_calibration(app: FastAPI) -> None:
    @app.post("/trainium/admin/sessions/{simulation_id}/review")
    async def submit_review(
        simulation_id: str, body: dict, user: User = Depends(get_current_admin)
    ):
        """Record one human's scores for a session.

        Keyed by reviewer, so a second reviewer adds an opinion rather than
        replacing the first. Agreement is measured between raters, so
        collapsing them into one consensus score would destroy the signal.
        """
        simulation = await simulations_collection.find_one({"id": simulation_id})
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")

        scores = body.get("scores") or {}
        if not scores:
            raise HTTPException(status_code=400, detail="No scores submitted")

        for key, value in scores.items():
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise HTTPException(
                    status_code=400, detail=f"Score for {key} must be a whole number 1 to 5"
                )

        reviewer = body.get("reviewer") or user.id
        await reviews_collection.update_one(
            {"simulation_id": simulation_id, "reviewer": reviewer},
            {
                "$set": {
                    "id": f"rev_{uuid.uuid4().hex[:12]}",
                    "simulation_id": simulation_id,
                    "reviewer": reviewer,
                    "scores": scores,
                    "note": body.get("note", ""),
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        return {"recorded": True, "reviewer": reviewer}

    @app.get("/trainium/admin/sessions/{simulation_id}/reviews")
    async def list_reviews(simulation_id: str, user: User = Depends(get_current_admin)):
        cursor = reviews_collection.find({"simulation_id": simulation_id}, {"_id": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/admin/calibration")
    async def calibration(user: User = Depends(get_current_admin)):
        """Agreement per competency across every reviewed session.

        Reports the gate verdict alongside the numbers, because the decision
        this exists to inform is binary: can certification mode be turned on.
        """
        reviews = await reviews_collection.find({}, {"_id": 0}).to_list(length=None)
        if not reviews:
            return {
                "gate": AGREEMENT_GATE,
                "sessions_reviewed": 0,
                "competencies": [],
                "certification_ready": False,
                "blocker": "No sessions have been reviewed yet.",
            }

        reviewed_ids = {r["simulation_id"] for r in reviews}
        reports = await reports_collection.find(
            {"simulation_id": {"$in": list(reviewed_ids)}, "status": "complete"},
            {"_id": 0, "simulation_id": 1, "scores": 1, "video_scores": 1},
        ).to_list(length=None)

        # The model is folded in as one rater among the humans, which is what
        # makes this model-vs-human agreement rather than human-vs-human.
        ratings: list[dict] = []
        for rep in reports:
            for s in (rep.get("scores") or []) + (rep.get("video_scores") or []):
                ratings.append(
                    {
                        "simulation_id": rep["simulation_id"],
                        "competency_key": s["competency_key"],
                        "rater": "model",
                        "score": s["score"],
                    }
                )
        for rev in reviews:
            for key, value in (rev.get("scores") or {}).items():
                ratings.append(
                    {
                        "simulation_id": rev["simulation_id"],
                        "competency_key": key,
                        "rater": rev["reviewer"],
                        "score": value,
                    }
                )

        results = measure_agreement(ratings, AGREEMENT_GATE)

        rubrics = await rubrics_collection.find({}, {"_id": 0}).to_list(length=None)
        labels = {
            c["key"]: c["label"] for r in rubrics for c in r.get("competencies", [])
        }

        competencies = [
            {
                "competency_key": r.competency_key,
                "label": labels.get(r.competency_key, r.competency_key),
                # NaN does not survive JSON, so an unmeasurable competency is
                # null rather than a number that looks real.
                "alpha": round(r.alpha, 3) if r.alpha == r.alpha else None,
                "sessions": r.units,
                "passes": r.passes,
            }
            for r in results
        ]

        failing = [c for c in competencies if not c["passes"]]
        # The golden set size is a spec requirement, not a statistical one, but
        # a gate cleared on three sessions is not a gate.
        too_few = len(reviewed_ids) < settings.trainium_golden_set_size

        blocker = ""
        if too_few:
            blocker = (
                f"{len(reviewed_ids)} of {settings.trainium_golden_set_size} golden set "
                "sessions reviewed."
            )
        elif failing:
            blocker = "Below the gate: " + ", ".join(
                c["label"] for c in failing
            )

        return {
            "gate": AGREEMENT_GATE,
            "sessions_reviewed": len(reviewed_ids),
            "golden_set_size": settings.trainium_golden_set_size,
            "competencies": competencies,
            "certification_ready": not failing and not too_few,
            "blocker": blocker,
        }
