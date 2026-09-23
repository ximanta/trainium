import uuid

from fastapi import Depends, FastAPI, HTTPException

from main.agents.trainium.auth import User, get_current_user
from main.agents.trainium.db_manager import (
    courses_collection,
    persona_templates_collection,
    simulations_collection,
)
from main.agents.trainium.models import Simulation


def configure_routes_simulations(app: FastAPI) -> None:
    @app.post("/trainium/simulations")
    async def create_simulation(body: dict, user: User = Depends(get_current_user)):
        course_id = body.get("course_id")
        persona_ids = body.get("persona_ids", [])

        if course_id:
            course = await courses_collection.find_one({"id": course_id})
            if course is None:
                raise HTTPException(status_code=404, detail="Course not found")

        if persona_ids:
            count = await persona_templates_collection.count_documents(
                {"id": {"$in": persona_ids}}
            )
            if count != len(persona_ids):
                raise HTTPException(status_code=400, detail="One or more persona_ids not found")

        simulation = Simulation(
            id=str(uuid.uuid4()),
            org_id=user.org_id,
            trainer_id=user.id,
            course_id=course_id,
            rubric_id=body.get("rubric_id"),
            mode=body.get("mode", "practice"),
            persona_ids=persona_ids,
            scenario_id=body.get("scenario_id"),
            target_objective_ids=body.get("target_objective_ids", []),
            duration_min=body.get("duration_min", 30),
            min_gap_s=body.get("min_gap_s"),
            per_persona_cooldown_s=body.get("per_persona_cooldown_s"),
        )
        await simulations_collection.insert_one(simulation.model_dump())
        return simulation

    @app.get("/trainium/simulations")
    async def list_simulations(user: User = Depends(get_current_user)):
        cursor = simulations_collection.find({"trainer_id": user.id}, {"_id": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/simulations/{simulation_id}")
    async def get_simulation(simulation_id: str, user: User = Depends(get_current_user)):
        simulation = await simulations_collection.find_one(
            {"id": simulation_id, "trainer_id": user.id}, {"_id": 0}
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="Simulation not found")
        return simulation

    @app.post("/trainium/simulations/{simulation_id}/end")
    async def end_simulation(simulation_id: str, user: User = Depends(get_current_user)):
        simulation = await simulations_collection.find_one(
            {"id": simulation_id, "trainer_id": user.id}
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="Simulation not found")
        await simulations_collection.update_one(
            {"id": simulation_id}, {"$set": {"status": "recording_upload"}}
        )
        return await simulations_collection.find_one({"id": simulation_id}, {"_id": 0})
