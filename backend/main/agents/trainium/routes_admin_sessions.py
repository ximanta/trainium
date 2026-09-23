"""Admin-configured sessions.

The admin sets a session up completely (course material, personas, pacing) and
publishes it. Publishing mints an unguessable join token; the trainer opens
that link and lands directly in the classroom with everything already chosen.
The trainer never picks personas or uploads material.
"""

import secrets
import uuid

from fastapi import Depends, FastAPI, HTTPException

from main.agents.trainium.auth import User, get_current_admin
from main.agents.trainium.db_manager import (
    courses_collection,
    persona_templates_collection,
    simulations_collection,
)
from main.agents.trainium.models import (
    CUSTOM_PERSONA_PREFIX,
    CUSTOM_PERSONA_TYPE,
    PersonaOverride,
    Simulation,
)
from main.agents.trainium.voices import DEFAULT_VOICE_ID


async def _resolve_personas(persona_ids: list[str], overrides: dict) -> list[dict]:
    """Persona templates with any per-session overrides applied, in the order
    the admin listed them.

    A custom learner has no template: it exists only as an override, so the
    override supplies the whole character and the template lookup is skipped.
    """
    cursor = persona_templates_collection.find({"id": {"$in": persona_ids}}, {"_id": 0})
    by_id = {t["id"]: t for t in await cursor.to_list(length=None)}

    resolved = []
    for pid in persona_ids:
        template = by_id.get(pid) or {}
        override = overrides.get(pid) or {}
        resolved.append(
            {
                "id": pid,
                "type": template.get("type", CUSTOM_PERSONA_TYPE),
                "name": override.get("display_name") or template.get("name", pid),
                "profile": override.get("profile") or template.get("profile", ""),
                "voice_id": override.get("voice_id") or template.get("voice_id", DEFAULT_VOICE_ID),
                "speak_probability": override.get("speak_probability"),
            }
        )
    return resolved


def configure_routes_admin_sessions(app: FastAPI) -> None:
    @app.post("/trainium/admin/sessions")
    async def create_session(body: dict, user: User = Depends(get_current_admin)):
        course_id = body.get("course_id")
        persona_ids = body.get("persona_ids", [])

        if not persona_ids:
            raise HTTPException(status_code=400, detail="At least one persona is required")

        if course_id:
            course = await courses_collection.find_one({"id": course_id})
            if course is None:
                raise HTTPException(status_code=404, detail="Course not found")

        raw_overrides = body.get("persona_overrides", {})

        # Custom learners are defined by the session rather than a template, so
        # they are exempt from the template check but must carry a profile:
        # without one the Director has no character to act on.
        custom_ids = [pid for pid in persona_ids if pid.startswith(CUSTOM_PERSONA_PREFIX)]
        for pid in custom_ids:
            if not (raw_overrides.get(pid) or {}).get("profile", "").strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Custom learner {pid} needs a profile describing how they behave",
                )

        template_ids = [pid for pid in persona_ids if pid not in custom_ids]
        if template_ids:
            found = await persona_templates_collection.count_documents(
                {"id": {"$in": template_ids}}
            )
            if found != len(template_ids):
                raise HTTPException(status_code=400, detail="One or more persona_ids not found")
        overrides = {
            pid: PersonaOverride(**data) for pid, data in raw_overrides.items() if pid in persona_ids
        }

        simulation = Simulation(
            id=str(uuid.uuid4()),
            org_id=user.org_id,
            # No real trainer identity until Auth0; whoever opens the join
            # link is the trainer. Recorded as unassigned rather than
            # pretending the admin will run the session.
            trainer_id="",
            title=body.get("title", "Untitled session"),
            audience=body.get("audience", ""),
            course_id=course_id,
            rubric_id=body.get("rubric_id"),
            mode=body.get("mode", "practice"),
            persona_ids=persona_ids,
            persona_overrides=overrides,
            target_objective_ids=body.get("target_objective_ids", []),
            duration_min=body.get("duration_min", 30),
            min_gap_s=body.get("min_gap_s"),
            per_persona_cooldown_s=body.get("per_persona_cooldown_s"),
        )
        await simulations_collection.insert_one(simulation.model_dump())
        return simulation

    @app.get("/trainium/admin/sessions")
    async def list_sessions(user: User = Depends(get_current_admin)):
        cursor = simulations_collection.find({"org_id": user.org_id}, {"_id": 0}).sort(
            "created_at", -1
        )
        return await cursor.to_list(length=None)

    @app.get("/trainium/admin/sessions/{session_id}")
    async def get_session(session_id: str, user: User = Depends(get_current_admin)):
        simulation = await simulations_collection.find_one(
            {"id": session_id, "org_id": user.org_id}, {"_id": 0}
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return simulation

    @app.patch("/trainium/admin/sessions/{session_id}")
    async def update_session(
        session_id: str, body: dict, user: User = Depends(get_current_admin)
    ):
        existing = await simulations_collection.find_one(
            {"id": session_id, "org_id": user.org_id}
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Session not found")

        allowed = {
            "title",
            "audience",
            "course_id",
            "rubric_id",
            "persona_ids",
            "persona_overrides",
            "target_objective_ids",
            "duration_min",
            "min_gap_s",
            "per_persona_cooldown_s",
        }
        update = {k: v for k, v in body.items() if k in allowed}
        if update:
            await simulations_collection.update_one({"id": session_id}, {"$set": update})
        return await simulations_collection.find_one({"id": session_id}, {"_id": 0})

    @app.post("/trainium/admin/sessions/{session_id}/publish")
    async def publish_session(session_id: str, user: User = Depends(get_current_admin)):
        simulation = await simulations_collection.find_one(
            {"id": session_id, "org_id": user.org_id}
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if not simulation.get("persona_ids"):
            raise HTTPException(
                status_code=400, detail="Cannot publish a session with no personas"
            )

        # Keep an existing token so republishing does not invalidate a link
        # already shared with a trainer.
        token = simulation.get("join_token") or secrets.token_urlsafe(12)
        await simulations_collection.update_one(
            {"id": session_id}, {"$set": {"join_token": token}}
        )
        return {"join_token": token, "join_path": f"/trainium/join/{token}"}

    @app.get("/trainium/join/{join_token}")
    async def resolve_join_token(join_token: str):
        """Public: the trainer's link resolves to the session to join. No auth
        in V1, the unguessable token is what protects the session.
        """
        simulation = await simulations_collection.find_one(
            {"join_token": join_token}, {"_id": 0}
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session link not found")

        personas = await _resolve_personas(
            simulation.get("persona_ids", []), simulation.get("persona_overrides", {})
        )
        return {
            "simulation_id": simulation["id"],
            "title": simulation.get("title", ""),
            "course_id": simulation.get("course_id"),
            "personas": personas,
        }
