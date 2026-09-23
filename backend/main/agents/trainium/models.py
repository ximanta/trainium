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
    # A learner an admin wrote for one session. It has no template, so its
    # behaviour comes entirely from the profile text on the override.
    "custom",
]

# Session-scoped learners use this id prefix, which is how the session routes
# tell them apart from template personas.
CUSTOM_PERSONA_PREFIX = "custom_"
CUSTOM_PERSONA_TYPE = "custom"

ScenarioKind = Literal[
    "difficult_learner",
    "demo_failure",
    "silent_classroom",
    "time_pressure",
    "confused_group",
    "dominant_learner",
    "off_topic",
]


AssetKind = Literal[
    "pptx", "instructor_guide", "lab_pdf", "assessment", "demo_guide", "objectives"
]


class CourseAsset(BaseModel):
    kind: AssetKind
    file_id: str
    filename: str
    size_bytes: int
    sha256: str
    page_count: Optional[int] = None


class SlideContent(BaseModel):
    slide_number: int
    title: str
    body: str
    notes: str
    image_file_id: Optional[str] = None


class Course(BaseModel):
    id: str
    org_id: str
    owner_id: str
    title: str
    description: str = ""
    status: Literal["uploading", "ingesting", "draft", "published", "failed"] = "uploading"
    ingest_error: Optional[str] = None
    assets: list[CourseAsset] = Field(default_factory=list)
    slides: list[SlideContent] = Field(default_factory=list)
    rubric_id: Optional[str] = None
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


class TranscriptSegment(BaseModel):
    id: str
    speaker: str  # "trainer" or a persona_id
    ts_start: float
    ts_end: float
    text: str
    confidence: Optional[float] = None
    objective_id: Optional[str] = None
    slide: Optional[int] = None


class Transcript(BaseModel):
    simulation_id: str
    version: int = 1
    stt_provider: str = "gemini-3.5-transcribe-live"
    segments: list[TranscriptSegment] = Field(default_factory=list)
    word_count: int = 0


EventActor = Literal["trainer", "persona", "director", "system"]


class Event(BaseModel):
    simulation_id: str
    ts_s: float
    kind: str
    actor: EventActor
    persona_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)


class PersonaOverride(BaseModel):
    """Per-session tweaks to a persona template. Every field is optional; only
    what the admin actually changed is stored, so template edits still flow
    through for everything else.
    """

    display_name: Optional[str] = None
    profile: Optional[str] = None
    voice_id: Optional[str] = None
    speak_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# How learners address the trainer. Indian classroom register leans heavily on
# an honorific, so the alternative to picking one is not neutrality: it is every
# persona calling a female trainer "Sir".
TrainerAddress = Literal["sir", "maam", "name"]


def describe_trainer(name: str, address: str) -> str:
    """One line telling the Director how personas should address the trainer."""
    name = (name or "").strip()
    if address == "sir":
        return f"{name or 'The trainer'}, addressed as Sir." if name else "Addressed as Sir."
    if address == "maam":
        return f"{name or 'The trainer'}, addressed as Ma'am." if name else "Addressed as Ma'am."
    if name:
        return f"{name}, addressed by name as {name}, with no Sir or Ma'am."
    # Nothing configured: no honorific is safer than guessing one.
    return "Name unknown. Address them directly without any honorific, never Sir or Ma'am."


class Simulation(BaseModel):
    id: str
    org_id: str
    trainer_id: str
    # Who is teaching, so personas address them correctly. Set by the admin when
    # the session is created; the trainer only opens the link.
    trainer_name: str = ""
    trainer_address: TrainerAddress = "name"
    course_id: Optional[str] = None
    rubric_id: Optional[str] = None
    mode: Literal["practice", "certification", "scenario"] = "practice"
    status: Literal[
        "scheduled", "live", "recording_upload", "analyzing", "complete", "failed"
    ] = "scheduled"
    persona_ids: list[str] = Field(default_factory=list)
    scenario_id: Optional[str] = None
    target_objective_ids: list[str] = Field(default_factory=list)
    duration_min: int = 30
    # Director pacing overrides. Defaults (in DirectorPolicy) are tuned for a
    # realistic 30-minute class: a persona waits 180s before speaking again
    # and there is a 45s floor between any two interventions. Short demo or
    # test sessions, especially with only one or two personas, look dead
    # under those values, so they can be overridden per simulation without
    # changing real classroom behaviour.
    min_gap_s: Optional[float] = None
    per_persona_cooldown_s: Optional[float] = None
    # Per-session persona overrides, keyed by persona template id. Lets an
    # admin rename or retune a learner for one session without creating a new
    # template. Only the keys present are overridden.
    persona_overrides: dict[str, "PersonaOverride"] = Field(default_factory=dict)
    # Unguessable token the trainer's join link carries. The simulation id
    # identifies the session; this grants access to it, so they are kept
    # separate rather than overloading the id.
    join_token: Optional[str] = None
    title: str = ""
    # Who the learners are. Shapes how personas speak; blank falls back
    # to the Director's default cohort.
    audience: str = ""
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
