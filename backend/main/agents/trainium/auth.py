from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

DEV_USERS = {
    "trainer": {"id": "dev-trainer", "org_id": "dev-org", "role": "trainer", "email": "dev-trainer@local"},
    "admin": {"id": "dev-admin", "org_id": "dev-org", "role": "admin", "email": "dev-admin@local"},
}


class User(BaseModel):
    id: str
    org_id: str
    role: str
    email: str


async def get_current_user(x_trainium_role: str = Header(default="trainer")) -> User:
    """V1: no auth. Role comes from a plain header the frontend sets per route group.
    When Auth0 lands, this is the only function that changes, it will decode the
    token and read the role claim instead of trusting this header.
    """
    stub = DEV_USERS.get(x_trainium_role, DEV_USERS["trainer"])
    return User(**stub)


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Same seam as get_current_user, scoped to admin only routes."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
