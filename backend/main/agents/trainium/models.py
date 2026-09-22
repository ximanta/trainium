from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Session(BaseModel):
    id: str
    org_id: str
    trainer_id: str
    status: str = "created"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
