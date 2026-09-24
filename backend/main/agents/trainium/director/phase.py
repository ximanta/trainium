"""Where a session is in its arc, and what that means for the room.

A class is not a uniform conversation. It opens with people settling in and
checking they can be heard, works through the material in the middle, and
winds down at the end. Without this the Director reacts only to the last few
turns, so a persona will ask a deep mid-lesson question thirty seconds in and
open a brand new topic with two minutes left.

Derived, never configured or inferred by a model, from two signals used
together: elapsed time against the allotted duration, and how far through the
deck the trainer has reached.

The two are not equivalent, and the difference matters. Learners in a real
room cannot see the deck: they see one slide at a time and have no idea
whether it is a third of the way through or a tenth. What they can see is the
clock. So time is the signal they genuinely have.

The deck still belongs here, but for a narrower reason than it first appears.
A trainer who has raced to slide 22 of 25 in ten minutes gives it away through
pace and content, wrapping topics up and saying "and finally", which learners
do notice. That is the case the deck signal is for, and it only runs one way:
being far through the deck can bring the closing phase forward, but being
early in the deck never holds it back, because the clock keeps running
whatever the trainer has covered. Taking the further along of the two is what
encodes that.

What the deck must never become is knowledge a learner could not have. See
layer_b's prompt: the Director is told the slide number so personas can talk
about what is on screen, and told explicitly not to reason aloud about how
many slides remain.
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
        "The session is near its end, and the learners can tell: time is "
        "nearly up and the trainer is wrapping topics off rather than opening "
        "them. A learner would not start a new topic now. What fits is tying "
        "off: asking about something from earlier that still does not sit "
        "right, checking a practical detail, or asking what to do next. Keep "
        "it brief, as people do when time is nearly up. They sense this from "
        "the clock and the trainer's pace, never from knowing the deck."
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
