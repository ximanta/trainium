"""Where a session is in its arc, and what that means for the room.

A class is not a uniform conversation. It opens with people settling in and
checking they can be heard, works through the material in the middle, and
winds down at the end. Without this the Director reacts only to the last few
turns, so a persona will ask a deep mid-lesson question thirty seconds in and
open a brand new topic with two minutes left.

Derived, never configured or inferred by a model. Everything needed is already
measured: how long the session has run against its allotted time, and how far
through the deck it has reached. Both are used, whichever is further along,
because either alone misreads a common case: a trainer who races the deck is
near the end regardless of the clock, and one who lingers on slide three is
not closing just because time is short.
"""

from dataclasses import dataclass
from typing import Literal

Phase = Literal["opening", "teaching", "closing"]

# Fractions of the session, by time or by deck position. Opening is short: it
# is the settling-in window, not the first third of the material.
OPENING_UNTIL = 0.12
CLOSING_FROM = 0.80


@dataclass
class PhaseView:
    phase: Phase
    progress: float  # 0..1, the further along of time and deck
    # True before anyone has spoken at all, which is a distinct situation from
    # being early: there is no material to ask about yet.
    nothing_said_yet: bool


def observe(
    elapsed_s: float,
    duration_s: float,
    furthest_slide: int | None,
    slides_total: int,
    has_spoken: bool,
) -> PhaseView:
    by_time = elapsed_s / duration_s if duration_s > 0 else 0.0
    by_deck = (furthest_slide or 0) / slides_total if slides_total > 0 else 0.0
    progress = min(1.0, max(by_time, by_deck))

    if progress >= CLOSING_FROM:
        phase: Phase = "closing"
    elif progress <= OPENING_UNTIL:
        phase = "opening"
    else:
        phase = "teaching"

    return PhaseView(
        phase=phase, progress=progress, nothing_said_yet=not has_spoken
    )


# What each phase sounds like, as direction rather than description. Written
# for the Director, so each says what a learner would plausibly do now and
# what would be out of place.
_GUIDANCE: dict[Phase, str] = {
    "opening": (
        "The session is just beginning. Learners are settling in: checking they "
        "can be heard, asking what will be covered, or saying hello. Questions "
        "about the material itself are premature, since almost nothing has been "
        "taught. Keep anything said here short and light."
    ),
    "teaching": (
        "The session is in its main stretch. This is where real questions "
        "belong: asking about what is on screen, pushing on something that was "
        "not clear, connecting a point back to something covered earlier."
    ),
    "closing": (
        "The session is near its end. A learner would not open a new topic "
        "now. What fits is tying off: asking about something from earlier that "
        "still does not sit right, checking a practical detail, or asking what "
        "to do next. Keep it brief, as people do when time is nearly up."
    ),
}


def guidance(view: PhaseView) -> str:
    """One paragraph of direction for the Director, or nothing.

    Returns empty during teaching when the session is well underway: that is
    the default state the prompt already describes, and repeating it would add
    tokens and dilute the instructions that do change behaviour.
    """
    if view.phase == "teaching":
        return ""
    return _GUIDANCE[view.phase]
