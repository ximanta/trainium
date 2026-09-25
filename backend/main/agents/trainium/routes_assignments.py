import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException

from main.agents.trainium.auth import User, get_current_admin
from main.agents.trainium.db_manager import (
    assignments_collection,
    runs_collection,
    simulations_collection,
)

# No I, O, 0 or 1. These codes are read off a screen and typed back in by
# hand, and those four are the pairs people get wrong.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalise_code(raw: str) -> str:
    """What the trainer typed, reduced to what it was meant to be.

    Case and the separating dash carry no meaning, so accepting "trn 4k2p" for
    "TRN-4K2P" costs nothing and saves a support mail.
    """
    return "".join(c for c in raw.upper() if c.isalnum())


async def _generate_code() -> str:
    """A code unique across every assignment, so it resolves to its session
    on its own and the trainer needs only the code, not a link as well.
    """
    for _ in range(20):
        body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        code = f"TRN{body}"
        if await assignments_collection.find_one({"code": code}) is None:
            return code
    # 32^4 is a million codes, so twenty collisions means something is wrong
    # with the collection rather than with our luck.
    raise HTTPException(status_code=500, detail="Could not allocate a trainer code")


def format_code(code: str) -> str:
    """Stored bare, shown dashed. The dash is for reading, not identity."""
    return f"{code[:3]}-{code[3:]}" if len(code) > 3 else code


async def resolve_assignment(code: str) -> dict | None:
    """The assignment a code belongs to, or None. Shared with the join route
    and the websocket, which must agree on what a code means.
    """
    normalised = normalise_code(code)
    if not normalised:
        return None
    return await assignments_collection.find_one({"code": normalised}, {"_id": 0})


def attempts_left(assignment: dict) -> int:
    return max(
        0, int(assignment.get("max_attempts", 3)) - int(assignment.get("attempts_used", 0))
    )


def configure_routes_assignments(app: FastAPI) -> None:
    @app.get("/trainium/admin/sessions/{session_id}/assignments")
    async def list_assignments(session_id: str, user: User = Depends(get_current_admin)):
        cursor = assignments_collection.find(
            {"simulation_id": session_id, "org_id": user.org_id}, {"_id": 0}
        ).sort("created_at", 1)
        assignments = await cursor.to_list(length=None)

        # Attempt counts come from the runs themselves rather than only the
        # counter on the assignment. The counter is what the cap is enforced
        # against; this is what the admin is shown, and a mismatch would mean
        # a run was recorded without its attempt being claimed.
        for a in assignments:
            a["code_display"] = format_code(a["code"])
            a["attempts_left"] = attempts_left(a)
            a["runs"] = await runs_collection.count_documents({"assignment_id": a["id"]})
        return assignments

    @app.post("/trainium/admin/sessions/{session_id}/assignments")
    async def create_assignment(
        session_id: str, body: dict, user: User = Depends(get_current_admin)
    ):
        simulation = await simulations_collection.find_one(
            {"id": session_id, "org_id": user.org_id}
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="Session not found")

        name = str(body.get("trainer_name") or "").strip()[:80]
        email = str(body.get("trainer_email") or "").strip().lower()[:120]
        if not name or not email:
            raise HTTPException(
                status_code=400, detail="A trainer needs both a name and an email"
            )

        # One assignment per person per session: a second one would issue a
        # second code and split their attempts across two counters, which is
        # exactly the accounting the cap exists to prevent.
        existing = await assignments_collection.find_one(
            {"simulation_id": session_id, "trainer_email": email}
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"{email} is already assigned to this session",
            )

        max_attempts = int(body.get("max_attempts", 3))
        if not 1 <= max_attempts <= 3:
            raise HTTPException(
                status_code=400, detail="Attempts must be between 1 and 3"
            )

        assignment = {
            "id": f"asg_{uuid.uuid4().hex[:12]}",
            "simulation_id": session_id,
            "org_id": user.org_id,
            "trainer_name": name,
            "trainer_email": email,
            "code": await _generate_code(),
            "max_attempts": max_attempts,
            "attempts_used": 0,
            "created_at": datetime.now(timezone.utc),
            "schema_version": 1,
        }
        await assignments_collection.insert_one(dict(assignment))
        assignment.pop("_id", None)
        return {
            **assignment,
            "code_display": format_code(assignment["code"]),
            "attempts_left": max_attempts,
            "runs": 0,
        }

    @app.patch("/trainium/admin/assignments/{assignment_id}")
    async def update_assignment(
        assignment_id: str, body: dict, user: User = Depends(get_current_admin)
    ):
        """Raise or lower the cap, or correct a name.

        Lowering below what has already been used is allowed and simply means
        no attempts remain. Refusing it would be pedantic: the admin's intent
        is to stop this trainer, and the runs already delivered are unaffected.
        """
        assignment = await assignments_collection.find_one(
            {"id": assignment_id, "org_id": user.org_id}
        )
        if assignment is None:
            raise HTTPException(status_code=404, detail="Assignment not found")

        update: dict = {}
        if "max_attempts" in body:
            max_attempts = int(body["max_attempts"])
            if not 1 <= max_attempts <= 3:
                raise HTTPException(
                    status_code=400, detail="Attempts must be between 1 and 3"
                )
            update["max_attempts"] = max_attempts
        if "trainer_name" in body:
            name = str(body["trainer_name"]).strip()[:80]
            if not name:
                raise HTTPException(status_code=400, detail="A trainer needs a name")
            update["trainer_name"] = name
        if not update:
            raise HTTPException(status_code=400, detail="Nothing to update")

        await assignments_collection.update_one({"id": assignment_id}, {"$set": update})
        updated = await assignments_collection.find_one({"id": assignment_id}, {"_id": 0})
        return {
            **updated,
            "code_display": format_code(updated["code"]),
            "attempts_left": attempts_left(updated),
            "runs": await runs_collection.count_documents({"assignment_id": assignment_id}),
        }

    @app.delete("/trainium/admin/assignments/{assignment_id}")
    async def delete_assignment(
        assignment_id: str, user: User = Depends(get_current_admin)
    ):
        """Withdraw an invitation. Deliveries already made are kept: they
        carry their own copy of the identity, so the reports stay attributable
        after the assignment is gone.
        """
        result = await assignments_collection.delete_one(
            {"id": assignment_id, "org_id": user.org_id}
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Assignment not found")
        return {"deleted": True}
