import re

from main.agents.trainium.director.state import PersonaState, SessionState

_WORD_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


# Phrases that mean "stop interrupting me" and "you can ask now". Matched on the
# trainer's transcript, deterministically: a real classroom runs on these and
# spending an LLM call to notice them would cost latency on every turn.
_HOLD_PHRASES = (
    "let me explain first",
    "let me finish",
    "hold your questions",
    "hold the questions",
    "save your questions",
    "questions at the end",
    "questions later",
    "no questions for now",
    "let me complete",
    "i will take questions",
    "i'll take questions",
    "before you ask",
)

_OPEN_PHRASES = (
    "questions now",
    "over to you",
    "you can ask",
    "go ahead and ask",
    "open for questions",
    "open the floor",
    "anyone have",
    "what do you think",
    "does anyone",
)


# Questions put to the room rather than to one person. A trainer checking
# comprehension is inviting anyone to answer, so the floor must stay open.
_OPEN_TO_ROOM = (
    "anybody",
    "anyone",
    # "any query", "any queries", "any question", "any doubt": matched as a
    # stem so a missing plural does not slip through. "Yeah, any query here?"
    # was read as a follow-up and handed the floor back to the same learner,
    # who then asked two questions in a row.
    "any quer",
    "any question",
    "any doubt",
    "everyone",
    "everybody",
    "all clear",
    "is this clear",
    "is that clear",
    "am i clear",
    "am i audible",
    "make sense",
    "makes sense",
    "understood",
    "following me",
    "with me",
    "so far",
    "till now",
    "questions on this",
)


def _is_open_to_room(utterance: str) -> bool:
    text = utterance.lower()
    return any(p in text for p in _OPEN_TO_ROOM)


def apply_direct_address(
    state: SessionState, utterance: str, last_persona_speaker: str | None = None
) -> str | None:
    """Note who owes the trainer a reply.

    Two ways that happens, and the second matters more than it looks:

    - The trainer names someone. Matched on roster first names with word
      boundaries, so "same" cannot match "Sam".
    - The trainer asks a question straight after a persona spoke, without
      naming anyone. Real trainers do this constantly: "what typo do you
      mean?" needs no name because everyone knows who is being asked. Early
      testing missed this entirely and a third learner answered instead,
      which is what made the class read as people talking past each other.

    Clears on any trainer turn that is neither, since an unanswered question
    should not hold the floor forever.
    """
    text = utterance.lower()

    for pid, persona in state.persona_states.items():
        name = (persona.display_name or "").strip()
        if not name:
            continue
        if re.search(rf"\b{re.escape(name.split()[0].lower())}\b", text):
            state.awaiting_reply_from = pid
            return pid

    # An unnamed question right after someone spoke usually belongs to them,
    # but only if it is actually a follow-up. "Anybody have questions?" and
    # "is this clear?" are addressed to the whole room, and treating them as
    # follow-ups handed the floor to the same learner every single turn: one
    # real session had Priya answering eleven times in a row while seven other
    # learners never spoke.
    if last_persona_speaker and "?" in utterance:
        if last_persona_speaker in state.persona_states and not _is_open_to_room(
            utterance
        ):
            state.awaiting_reply_from = last_persona_speaker
            return last_persona_speaker

    state.awaiting_reply_from = None
    return None


def apply_floor_control(state: SessionState, utterance: str) -> bool | None:
    """Hold or release the floor when the trainer says so.

    Returns the new value when it changed, else None, so the caller can tell the
    client without re-deriving it. Opening wins over holding when a single
    utterance somehow contains both, because "let me finish, then any questions"
    ends with the floor open.
    """
    text = utterance.lower()
    opens = any(p in text for p in _OPEN_PHRASES)
    holds = any(p in text for p in _HOLD_PHRASES)

    if opens:
        target = False
    elif holds:
        target = True
    else:
        return None

    if state.floor_held == target:
        return None
    state.floor_held = target
    return target


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
