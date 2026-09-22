import re

from main.agents.trainium.director.state import PersonaState, SessionState

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def apply_trainer_utterance(
    state: SessionState, utterance: str, must_cover_terms: list[str]
) -> None:
    """Deterministic reducer: updates each persona's knowledge/emotional
    state after a trainer utterance, using term overlap rather than an LLM
    call. Architecture doc §3.4: "not by an extra LLM call, which would cost
    latency for no realism gain."

    - engagement rises slightly whenever the trainer says something relevant
      to the current objective (keeps personas from decaying to disinterest
      during a well-taught session).
    - confusion falls when a persona's tracked knowledge_gaps are covered by
      the utterance (a gap is "addressed" once its terms appear); confusion
      does not rise here, since we have no signal the trainer said something
      wrong, only that unaddressed gaps persist.
    """
    utterance_tokens = _tokenize(utterance)
    covered_terms = {term for term in must_cover_terms if _tokenize(term) <= utterance_tokens}

    state.record_trainer_utterance(utterance)

    if not covered_terms:
        return

    for persona in state.persona_states.values():
        _update_persona(persona, utterance_tokens)


def _update_persona(persona: PersonaState, utterance_tokens: set[str]) -> None:
    remaining_gaps = []
    gap_closed = False
    for gap in persona.knowledge_gaps:
        # Require every word of the gap phrase to appear, not just any one
        # word: "episodic memory" sharing only "memory" with an utterance
        # about "semantic memory" is not the same concept being addressed.
        if _tokenize(gap) <= utterance_tokens:
            gap_closed = True
        else:
            remaining_gaps.append(gap)
    persona.knowledge_gaps = remaining_gaps

    if gap_closed:
        persona.confusion = max(0.0, persona.confusion - 0.2)
    persona.engagement = min(1.0, persona.engagement + 0.05)


def mark_objective_covered(state: SessionState, objective_id: str) -> None:
    if objective_id not in state.objectives_covered:
        state.objectives_covered.append(objective_id)
