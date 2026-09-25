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
    # Deck formats, both ingested as one slide per page. Distinct from
    # "lab_pdf", which is reference material rather than something taught from.
    "pptx",
    "pdf",
    "instructor_guide",
    "lab_pdf",
    "assessment",
    "demo_guide",
    "objectives",
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

# The same values as a runtime set, for validating what a client sends.
TRAINER_ADDRESSES = frozenset(("sir", "maam", "name"))


def describe_trainer(name: str, address: str) -> str:
    """How personas address the trainer, written for the Director.

    The hard part is not which form to use but how often. Telling a model to
    use a name "sparingly" does not work: a real session came back with almost
    every line ending in the trainer's name, which reads as a form letter
    rather than a classroom. So the instruction leads with the frequency, gives
    a concrete ceiling, and says plainly that most lines should carry no
    address at all, which is how people actually speak.
    """
    name = (name or "").strip()
    first = name.split()[0] if name else ""

    # Most lines address nobody. This is stated first and in absolute terms
    # because it is the rule that keeps being broken.
    frequency = (
        "Most lines should not address the trainer at all. People in a real "
        "room say a name when they want attention, when answering after "
        "someone else, or when thanking someone, not in every sentence. At "
        "most one line in four should name them, and never two in a row."
    )

    if address == "sir":
        forms = f'"Sir" is the usual form' + (
            f', with "{first}" occasionally instead' if first else ""
        )
    elif address == "maam":
        forms = f'"Ma\'am" is the usual form' + (
            f', with "{first}" occasionally instead' if first else ""
        )
    elif first:
        forms = f'"{first}" is the form to use, never the full name'
    else:
        # Nothing configured. No honorific is safer than guessing one, since
        # guessing wrong misgenders someone in front of a class.
        return (
            f"The trainer's name is not known. Never use Sir or Ma'am, and "
            f"never invent a name. Address them with no form of address at "
            f"all. {frequency}"
        )

    who = f"{name}. " if name else ""
    return f"{who}{forms}. {frequency}"


class Simulation(BaseModel):
    id: str
    org_id: str
    trainer_id: str
    # Who the admin expects to deliver this. A link can be forwarded, so the
    # person who actually joins confirms or corrects it in the green room and
    # the truth is recorded on the run.
    assigned_trainer_name: str = ""
    assigned_trainer_email: str = ""
    # Legacy: whoever ran it last. Superseded by SessionRun, kept so existing
    # documents still load.
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


class Recording(BaseModel):
    """The trainer's camera track for one session.

    Camera only, deliberately: body language lives there, while what was on
    screen is already recoverable from the slide number on each transcript
    segment. Keeping one track also means WebM goes from MediaRecorder to
    GridFS to Gemini untouched, with no compositing step to install or fail.
    """

    id: str
    simulation_id: str
    track: Literal["camera"] = "camera"
    file_id: str
    content_type: str = "video/webm"
    size_bytes: int = 0
    duration_s: float = 0.0
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Evidence(BaseModel):
    """One observed moment, tied to the competency it speaks to.

    Extracted before any score exists. Scoring then reads only these, which
    is what makes a score traceable rather than a number with quotes found to
    justify it afterwards.
    """

    competency_key: str
    quote: str
    # Seconds from session start, so the report can point at the moment.
    ts_start: float
    ts_end: float
    speaker: str = "trainer"
    # Whether this came from the transcript or from watching the video.
    source: Literal["transcript", "video"] = "transcript"
    # True when the moment shows the competency done well.
    positive: bool = True


class CompetencyScore(BaseModel):
    competency_key: str
    label: str
    score: int = Field(ge=1, le=5)
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)


class Undetermined(BaseModel):
    """A competency that could not be judged, and why.

    Stored but not shown in the report body. It exists for traceability: an
    admin reviewing a certification needs to know a criterion was skipped and
    on what grounds, without that absence masquerading as a mid-range score.
    """

    competency_key: str
    label: str
    reason: str
    source: Literal["transcript", "video"] = "transcript"


class Report(BaseModel):
    id: str
    simulation_id: str
    rubric_id: str
    # Transcript and video competencies are scored and shown apart, so a
    # session recorded with the camera off is not penalised on delivery
    # criteria it never had a chance to demonstrate.
    scores: list[CompetencyScore] = Field(default_factory=list)
    video_scores: list[CompetencyScore] = Field(default_factory=list)
    # Competencies with no basis to judge, kept for the record rather than
    # rendered. Covers both rubrics; `source` says which.
    undetermined: list[Undetermined] = Field(default_factory=list)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    # False when no usable camera track existed, so the UI can say why the
    # delivery section is missing instead of showing an empty panel.
    video_analysed: bool = False
    status: Literal["pending", "running", "complete", "failed"] = "pending"
    error: str = ""
    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionRun(BaseModel):
    """One trainer's delivery of a session.

    A simulation is the setup, reusable and shared; a run is a single
    performance of it. Everything a session produces belongs to the run, not
    the simulation, because the same link is deliberately shared across
    trainers.
    """

    id: str
    simulation_id: str
    org_id: str
    # Who the admin expected, and who actually turned up. Both are kept: the
    # admin's assignment is the record of intent, and a forwarded link means
    # the person teaching may not be that person.
    assigned_trainer_name: str = ""
    assigned_trainer_email: str = ""
    trainer_name: str = ""
    trainer_email: str = ""
    trainer_address: TrainerAddress = "name"
    status: Literal["live", "complete", "failed"] = "live"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    actual_duration_s: int = 0
    turns_taken: int = 0
    schema_version: int = 1
