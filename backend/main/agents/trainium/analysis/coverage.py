"""How much of the deck the session actually got through.

Computed rather than inferred. The transcript already records which slide was
on screen for each segment, and the course knows how many slides exist, so
coverage is arithmetic. Handing the raw numbers to the model and asking it to
judge pacing is both cheaper and harder to get wrong than asking it to guess
how far a session progressed.

Without this, Time Management has nothing to grade: the anchors talk about
covering planned material and the model was never told what was planned, so it
landed in undetermined on nearly every run.
"""

from dataclasses import dataclass

from main.config import settings


@dataclass
class Coverage:
    slides_total: int
    slides_reached: int
    furthest_slide: int
    elapsed_min: float
    planned_min: int

    @property
    def fraction(self) -> float:
        if not self.slides_total:
            return 0.0
        return self.furthest_slide / self.slides_total

    @property
    def met_threshold(self) -> bool:
        return self.fraction >= settings.trainium_coverage_threshold

    def as_prompt_line(self) -> str:
        """Plain facts for the scoring prompt, with no judgement attached.

        The verdict is left to the model against the rubric anchors; this only
        states what happened, including the threshold it is being measured
        against so the same numbers cannot be read two ways.
        """
        if not self.slides_total:
            return (
                f"The session ran {self.elapsed_min:.0f} of {self.planned_min} planned "
                "minutes. No slide deck was attached, so there is no material coverage "
                "to measure."
            )

        pct = round(self.fraction * 100)
        target = round(settings.trainium_coverage_threshold * 100)
        used = round(self.elapsed_min / self.planned_min * 100) if self.planned_min else 0

        if self.met_threshold:
            verdict = f"which meets the {target}% expected"
        elif self.fraction < settings.trainium_coverage_threshold / 2:
            # Far short, not marginally short. Said plainly, because a model
            # given only "below target" will treat covering a tenth of the
            # deck as a minor pacing note rather than the defining fact of
            # the session.
            verdict = (
                f"far short of the {target}% expected. Most of the planned material "
                "was never reached, which is the most significant fact about this "
                "session"
            )
        else:
            verdict = f"short of the {target}% expected"

        return (
            f"The session ran {self.elapsed_min:.0f} of {self.planned_min} planned "
            f"minutes ({used}% of the time allowed). It reached slide "
            f"{self.furthest_slide} of {self.slides_total}, which is {pct}% of the deck, "
            f"{verdict}. {self.slides_reached} slides were actually discussed."
        )


def measure(segments: list[dict], slides_total: int, planned_min: int) -> Coverage:
    """Derive coverage from what the transcript recorded.

    `furthest_slide` drives the fraction rather than the count of distinct
    slides: skipping ahead is still progress through the deck, whereas a
    trainer who lingers on three slides and stops has not covered the material
    however many segments they spoke.
    """
    seen = {s["slide"] for s in segments if isinstance(s.get("slide"), int)}
    elapsed = max((s.get("ts_end", 0.0) for s in segments), default=0.0)

    return Coverage(
        slides_total=slides_total,
        slides_reached=len(seen),
        furthest_slide=max(seen) if seen else 0,
        elapsed_min=elapsed / 60.0,
        planned_min=planned_min,
    )
