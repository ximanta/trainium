from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PersonaState:
    persona_id: str
    persona_type: str
    voice_id: str
    engagement: float = 0.5  # 0..1
    confusion: float = 0.0  # 0..1
    last_spoke_at: float = -999.0  # elapsed_s at last utterance, far in the past initially
    knowledge_gaps: list[str] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_objective_id: str | None = None
    objectives_covered: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    transcript_recent: list[str] = field(default_factory=list)  # last ~90s of trainer speech
    slide_number: int | None = None
    persona_states: dict[str, PersonaState] = field(default_factory=dict)
    recent_events: list[dict] = field(default_factory=list)
    intervention_count_window: list[float] = field(default_factory=list)  # elapsed_s timestamps, last 10min

    def record_event(self, kind: str, data: dict) -> None:
        self.recent_events.append({"kind": kind, "data": data, "elapsed_s": self.elapsed_s})
        self.recent_events = self.recent_events[-5:]

    def record_trainer_utterance(self, text: str) -> None:
        self.transcript_recent.append(text)
        # Keep roughly the last few utterances as a proxy for "last 90s" —
        # exact time-windowing needs per-utterance timestamps, deferred until
        # real session timing is wired in.
        self.transcript_recent = self.transcript_recent[-10:]

    def interventions_in_last_10min(self) -> int:
        cutoff = self.elapsed_s - 600
        self.intervention_count_window = [t for t in self.intervention_count_window if t >= cutoff]
        return len(self.intervention_count_window)

    def record_intervention(self, persona_id: str) -> None:
        self.intervention_count_window.append(self.elapsed_s)
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
