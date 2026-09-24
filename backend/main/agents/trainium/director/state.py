from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PersonaState:
    persona_id: str
    persona_type: str
    voice_id: str
    display_name: str = ""
    avatar_url: str = ""
    profile: str = ""
    # Per-session override of this persona type's default speak probability.
    # None means use the type default from DirectorPolicy.
    speak_probability: float | None = None
    engagement: float = 0.5  # 0..1
    confusion: float = 0.0  # 0..1
    last_spoke_at: float = -999.0  # elapsed_s at last utterance, far in the past initially
    knowledge_gaps: list[str] = field(default_factory=list)
    # Trainer-controlled classroom state. A muted persona is excluded from the
    # Director's eligible list entirely, so it cannot be selected to speak.
    muted: bool = False
    # Set when the Director wants this persona to speak but the trainer has
    # not called on them yet. The pending line is held here until the trainer
    # acknowledges, matching the doc's raise_hand_ack flow.
    hand_raised: bool = False
    pending_line: str = ""
    pending_intent: str = ""


@dataclass
class SessionState:
    session_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_objective_id: str | None = None
    objectives_covered: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    # The recent conversation, trainer AND personas, as (speaker, text) pairs.
    # Personas must see what has already been said, including by each other:
    # without this every persona independently answers the same question and
    # the class repeats itself.
    transcript_recent: list[tuple[str, str]] = field(default_factory=list)
    # The current, still-being-spoken utterance, updated live as partial
    # transcript arrives. Cleared once the turn settles and its final text
    # is appended to transcript_recent instead. Exists so speculative Layer B
    # runs can see what is being said right now, not just prior turns.
    in_progress_partial: str = ""
    slide_number: int | None = None
    # How many slides the deck has, so progress through the material can be
    # measured. Zero when no deck is attached, which the phase logic treats as
    # "time is the only signal" rather than as a finished deck.
    slides_total: int = 0
    # Who the learners are, as free text. Drives how the personas talk, so a
    # cohort of fresh graduates does not sound like senior consultants.
    audience: str = ""
    # How personas address the trainer. Without this every persona defaults to
    # "Sir", which is wrong for half of all trainers.
    trainer_name: str = ""
    trainer_address: str = "name"
    # True while the trainer has asked to hold questions. Personas stay silent
    # but may still raise a hand, so the queue builds visibly and the trainer
    # can see who is waiting.
    floor_held: bool = False
    # The persona the trainer just spoke to by name, if any. While this is set
    # the floor belongs to them: a real classroom does not let a third person
    # answer a question put directly to someone else, which is what made the
    # conversation feel like unrelated people talking past each other.
    awaiting_reply_from: str | None = None
    # The persona who spoke most recently, by id. The transcript keeps display
    # names for the prompt's benefit, which cannot be matched back to a
    # persona, so the id is kept separately: an unnamed follow-up question
    # belongs to whoever just spoke.
    last_persona_speaker: str | None = None
    # Set while a learner is speaking into a silence rather than responding to
    # something. The Director needs to know, because the natural line differs:
    # before anything is taught there is no subject to ask about.
    breaking_silence: bool = False
    # How long the admin allotted. The session ends itself at this point so an
    # abandoned tab cannot keep spending on LLM calls.
    duration_s: float = 1800.0
    # Total persona turns this session, and the ceiling on them. Duration
    # bounds spend by proxy; this bounds it directly, so a Director that
    # somehow fires every few seconds still cannot run the bill up.
    turns_taken: int = 0
    max_turns: int = 0
    ended: bool = False

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.duration_s - self.elapsed_s)

    def out_of_budget(self) -> bool:
        """True once the session should stop generating, for either reason."""
        return self.elapsed_s >= self.duration_s or (
            self.max_turns > 0 and self.turns_taken >= self.max_turns
        )
    # Latest frame of the trainer's shared screen as JPEG bytes, or None when
    # not sharing. The client only sends a new frame when the screen actually
    # changed, so this is refreshed rarely rather than every turn.
    screen_frame_jpeg: bytes | None = None
    persona_states: dict[str, PersonaState] = field(default_factory=dict)
    recent_events: list[dict] = field(default_factory=list)
    intervention_count_window: list[float] = field(default_factory=list)  # elapsed_s timestamps, last 10min

    def record_event(self, kind: str, data: dict) -> None:
        self.recent_events.append({"kind": kind, "data": data, "elapsed_s": self.elapsed_s})
        self.recent_events = self.recent_events[-5:]

    def record_trainer_utterance(self, text: str) -> None:
        self._append_utterance("Trainer", text)
        self.in_progress_partial = ""

    def record_persona_utterance(self, speaker: str, text: str) -> None:
        self._append_utterance(speaker, text)

    def _append_utterance(self, speaker: str, text: str) -> None:
        self.transcript_recent.append((speaker, text))
        # Keep roughly the last few utterances as a proxy for "last 90s" —
        # exact time-windowing needs per-utterance timestamps, deferred until
        # real session timing is wired in.
        self.transcript_recent = self.transcript_recent[-12:]

    def interventions_in_last_10min(self) -> int:
        cutoff = self.elapsed_s - 600
        self.intervention_count_window = [t for t in self.intervention_count_window if t >= cutoff]
        return len(self.intervention_count_window)

    def record_intervention(self, persona_id: str) -> None:
        self.intervention_count_window.append(self.elapsed_s)
        self.last_persona_speaker = persona_id
        # Counted here because this is the one place every speaking path goes
        # through, including a persona called on after raising a hand.
        self.turns_taken += 1
        if persona_id in self.persona_states:
            self.persona_states[persona_id].last_spoke_at = self.elapsed_s


# In-process session registry. Redis is documented as the target (architecture
# doc §3.5) but is not set up for this project; the doc explicitly names an
# in-process dict as an acceptable MVP fallback, capping the deployment at one
# WS worker per session (sticky routing). Revisit before scaling past that.
_sessions: dict[str, SessionState] = {}


def create_session(session_id: str) -> SessionState:
    state = SessionState(session_id=session_id)
    _sessions[session_id] = state
    return state


def get_session(session_id: str) -> SessionState | None:
    return _sessions.get(session_id)


def remove_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
