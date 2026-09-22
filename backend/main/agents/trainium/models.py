from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

PersonaType = Literal[
    "curious",
    "beginner",
    "skeptic",
    "silent",
    "confused",
    "fast_learner",
    "distracted",
    "hacker",
    "senior_practitioner",
]

ScenarioKind = Literal[
    "difficult_learner",
    "demo_failure",
    "silent_classroom",
    "time_pressure",
    "confused_group",
    "dominant_learner",
    "off_topic",
]


class PersonaTemplate(BaseModel):
    id: str
    org_id: Optional[str] = None
    name: str
    type: PersonaType
    profile: str
    voice_id: str
    avatar_url: Optional[str] = None
    schema_version: int = 1


class Scenario(BaseModel):
    id: str
    name: str
    kind: ScenarioKind
    script: str
    schema_version: int = 1


class RubricCompetency(BaseModel):
    key: str
    label: str
    scale_min: int = 1
    scale_max: int = 5
    anchors: dict[str, str] = Field(default_factory=dict)


class Rubric(BaseModel):
    id: str
    org_id: Optional[str] = None
    name: str
    description: str = ""
    competencies: list[RubricCompetency] = Field(default_factory=list)
    status: Literal["draft", "published"] = "draft"
    version: int = 1
    created_by: Optional[str] = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Simulation(BaseModel):
    id: str
    org_id: str
    trainer_id: str
    course_id: Optional[str] = None
    rubric_id: Optional[str] = None
    mode: Literal["practice", "certification", "scenario"] = "practice"
    status: Literal[
        "scheduled", "live", "recording_upload", "analyzing", "complete", "failed"
    ] = "scheduled"
    persona_ids: list[str] = Field(default_factory=list)
    scenario_id: Optional[str] = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
